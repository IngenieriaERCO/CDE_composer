"""Lectura del manifiesto del Exportador Vectorial (`<prefijo>.manifest.json`).

Contrato: docs/contrato_paquete.md. Aquí solo se valida la ESTRUCTURA de lo que el
componedor necesita para componer (campos presentes, tipos, números finitos y positivos,
enumerados, versión mayor del esquema). No se calcula el hash ni se compara con el PDF
(subfases 2.3 y 2.4). Los campos informativos (exporter, source, entities, fonts,
dependencies, notices, options) no se validan y los campos desconocidos se ignoran.
`pdf.drawing.mask` (esquema 1.5) es opcional; si viene, su `zone_page_mm` se valida.

Todos los problemas se juntan en un solo `ManifiestoInvalido`, uno por línea, con la ruta
del campo (p. ej. «pdf.page_size_mm: falta el campo»).
"""

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

from componedor.cad_a_papel import MatrizCad

TIPO_DOCUMENTO = "cde-detail-manifest"
VERSION_MAYOR_SOPORTADA = 1
ESTADOS_VALIDACION = ("complete", "complete_with_warnings")

# Lo que el componedor necesita para componer (ver docs/contrato_paquete.md).
CAMPOS_OBLIGATORIOS = (
    "document_type",
    "schema_version",
    "model_version",
    "units.millimeters_per_unit",
    "scale.denominator",
    "scale.factor_mm_per_cad_unit",
    "scale.physical_scale_guaranteed",
    "pdf.file_name",
    "pdf.bytes",
    "pdf.sha256",
    "pdf.page_count",
    "pdf.page_size_mm",
    "pdf.expected_page_size_mm",
    "pdf.drawing.cad_bounds.min",
    "pdf.drawing.cad_bounds.max",
    "pdf.drawing.page_bounds_mm.x0",
    "pdf.drawing.page_bounds_mm.y0",
    "pdf.drawing.page_bounds_mm.x1",
    "pdf.drawing.page_bounds_mm.y1",
    "pdf.drawing.cad_to_page.units",
    "pdf.drawing.cad_to_page.origin",
    "pdf.drawing.cad_to_page.y_axis",
    "pdf.drawing.cad_to_page.matrix",
    "validation.status",
)

# Campos que el exportador puede dejar en null y por qué; el componedor los exige con valor.
MOTIVOS_NULL = {
    "units.millimeters_per_unit": "el exportador no pudo determinar las unidades del dibujo",
    "scale.denominator": "el detalle se exportó sin escala nominal 1:N",
    "scale.factor_mm_per_cad_unit": "el detalle se exportó sin escala nominal 1:N",
    "pdf.expected_page_size_mm": "sin escala nominal no hay tamaño de página esperado",
    "pdf.drawing": "el exportador no dibujó nada en el PDF",
}

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_VERSION = re.compile(r"^(\d+)(\.\d+)*$")
_FALTA = object()  # marcador: el campo no está (distinto de null)


class ManifiestoInvalido(ValueError):
    """El manifiesto no cumple el contrato; el mensaje lista todos los problemas."""


@dataclass(frozen=True)
class Unidades:
    milimetros_por_unidad: float  # mm reales por unidad CAD (m -> 1000)


@dataclass(frozen=True)
class Escala:
    denominador: float  # el N de 1:N
    factor_mm_por_unidad_cad: float  # mm de papel por unidad CAD
    fisica_garantizada: bool  # regla de uso en coherencia.py (comprobación i)
    motivo_no_garantizada: str | None = None  # scale.physical_scale_reason (informativo)


@dataclass(frozen=True)
class Dibujo:
    limites_cad: tuple[float, float, float, float]  # (xmin, ymin, xmax, ymax) en unidades CAD
    limites_pagina_mm: tuple[float, float, float, float]  # (x0, y0, x1, y1), mm, Y abajo
    matriz: MatrizCad  # cad_to_page: CAD -> mm de página, origen arriba-izquierda, Y abajo
    # pdf.drawing.mask.zone_page_mm (desde el esquema 1.5): la zona del Model Space en la
    # página (x0, y0, x1, y1; mm, Y abajo), sin el bleed_mm. None sin máscara de recorte.
    mascara_mm: tuple[float, float, float, float] | None = None


@dataclass(frozen=True)
class GeometriaPdf:
    nombre_archivo: str
    bytes: int
    sha256: str
    paginas: int
    tamano_pagina_mm: tuple[float, float]
    tamano_esperado_mm: tuple[float, float]
    margen_mm: float | None  # informativo (pdf.margin_mm); None si falta o no es válido
    dibujo: Dibujo


@dataclass(frozen=True)
class Manifiesto:
    ruta: Path
    tipo_documento: str
    version_esquema: str
    version_modelo: str
    unidades: Unidades
    escala: Escala
    pdf: GeometriaPdf
    estado_validacion: str
    bloque: str | None = None  # source.block_name, informativo (puede faltar)


def leer_manifiesto(ruta: Path | str) -> Manifiesto:
    """Lee el manifiesto y valida su estructura. Lanza `ManifiestoInvalido`."""
    ruta = Path(ruta)
    if not ruta.is_file():
        raise ManifiestoInvalido(f"No se encontró el manifiesto '{ruta}'.")
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except UnicodeDecodeError as e:
        raise ManifiestoInvalido(f"El manifiesto '{ruta}' no está en UTF-8: {e}") from e
    except json.JSONDecodeError as e:
        raise ManifiestoInvalido(
            f"El manifiesto '{ruta}' no es un JSON válido (línea {e.lineno}, columna {e.colno}): "
            f"{e.msg}."
        ) from e
    if not isinstance(datos, dict):
        raise ManifiestoInvalido(f"El manifiesto '{ruta}' debe ser un objeto JSON {{...}}.")

    lector = _Lector(datos)
    manifiesto = _construir(lector, ruta)
    if lector.errores:
        n = len(lector.errores)
        raise ManifiestoInvalido(
            f"El manifiesto '{ruta}' no es válido ({n} {'problema' if n == 1 else 'problemas'}):\n"
            + "\n".join(f"- {e}" for e in lector.errores)
        )
    return manifiesto


def _construir(lec: "_Lector", ruta: Path) -> Manifiesto | None:
    tipo = lec.texto("document_type")
    if tipo is not None and tipo != TIPO_DOCUMENTO:
        lec.error("document_type", f"debe ser '{TIPO_DOCUMENTO}'; tiene {tipo!r}")
    version = lec.texto("schema_version")
    if version is not None:
        coincide = _VERSION.match(version)
        if not coincide:
            lec.error("schema_version", f"formato de versión no reconocido: {version!r}")
        elif int(coincide.group(1)) != VERSION_MAYOR_SOPORTADA:
            lec.error("schema_version",
                    f"versión {version} no soportada; el componedor entiende la versión mayor "
                    f"{VERSION_MAYOR_SOPORTADA} ({VERSION_MAYOR_SOPORTADA}.x)")
    modelo = lec.texto("model_version")

    unidades = Unidades(lec.numero("units.millimeters_per_unit", positivo=True))
    escala = Escala(
        lec.numero("scale.denominator", positivo=True),
        lec.numero("scale.factor_mm_per_cad_unit", positivo=True),
        lec.booleano("scale.physical_scale_guaranteed"),
        lec.opcional_texto("scale.physical_scale_reason"),
    )

    nombre = lec.texto("pdf.file_name")
    if nombre is not None and (not nombre or "/" in nombre or "\\" in nombre):
        lec.error("pdf.file_name", f"debe ser un nombre de archivo sin ruta (sin \\ ni /); "
                                 f"tiene {nombre!r}")
    sha = lec.texto("pdf.sha256")
    if sha is not None and not _SHA256.match(sha):
        lec.error("pdf.sha256", "debe ser un SHA-256 en hexadecimal (64 caracteres 0-9, a-f)")
    tamano = lec.numeros("pdf.page_size_mm", 2, positivos=True)
    esperado = lec.numeros("pdf.expected_page_size_mm", 2, positivos=True)
    margen = lec.opcional_numero("pdf.margin_mm")  # informativo: no se usa para componer
    paginas = lec.entero("pdf.page_count", minimo=1)
    tamano_bytes = lec.entero("pdf.bytes", minimo=1)

    dibujo = None
    if lec.objeto("pdf.drawing"):
        cmin = lec.numeros("pdf.drawing.cad_bounds.min", 2)
        cmax = lec.numeros("pdf.drawing.cad_bounds.max", 2)
        if cmin and cmax and (cmax[0] <= cmin[0] or cmax[1] <= cmin[1]):
            lec.error("pdf.drawing.cad_bounds", "max debe ser mayor que min en X y en Y")
        limites = tuple(lec.numero(f"pdf.drawing.page_bounds_mm.{k}") for k in ("x0", "y0", "x1", "y1"))
        if None not in limites and (limites[2] <= limites[0] or limites[3] <= limites[1]):
            lec.error("pdf.drawing.page_bounds_mm", "debe cumplir x1 > x0 e y1 > y0")
        for clave, esperado_ctp in (("units", "mm"), ("origin", "top-left"), ("y_axis", "down")):
            valor = lec.texto(f"pdf.drawing.cad_to_page.{clave}")
            if valor is not None and valor != esperado_ctp:
                lec.error(f"pdf.drawing.cad_to_page.{clave}",
                        f"debe ser '{esperado_ctp}'; tiene {valor!r}")
        matriz = lec.numeros("pdf.drawing.cad_to_page.matrix", 6)
        mascara = _leer_mascara(lec)
        if cmin and cmax and None not in limites and matriz:
            dibujo = Dibujo((*cmin, *cmax), limites, MatrizCad(*matriz), mascara)

    estado = lec.texto("validation.status")
    if estado is not None and estado not in ESTADOS_VALIDACION:
        lec.error("validation.status",
                f"debe ser uno de {', '.join(ESTADOS_VALIDACION)}; tiene {estado!r}")

    bloque = lec.opcional_texto("source.block_name")
    if lec.errores:
        return None
    return Manifiesto(
        ruta=ruta, tipo_documento=tipo, version_esquema=version, version_modelo=modelo,
        unidades=unidades, escala=escala,
        pdf=GeometriaPdf(nombre, tamano_bytes, sha, paginas, tamano, esperado, margen, dibujo),
        estado_validacion=estado, bloque=bloque,
    )


def _leer_mascara(lec: "_Lector") -> tuple[float, float, float, float] | None:
    """`pdf.drawing.mask.zone_page_mm` (esquema 1.5). Falta (1.0–1.4) o es null: sin máscara.

    Si hay máscara, su zona se usa en la comprobación h (coherencia.py), así que se valida:
    cuatro números finitos con x1 > x0 e y1 > y0.
    """
    dibujo = lec.datos.get("pdf", {}).get("drawing")
    if not isinstance(dibujo, dict) or dibujo.get("mask") is None:
        return None
    if not lec.objeto("pdf.drawing.mask"):
        return None
    zona = tuple(lec.numero(f"pdf.drawing.mask.zone_page_mm.{k}") for k in ("x0", "y0", "x1", "y1"))
    if None in zona:
        return None
    if zona[2] <= zona[0] or zona[3] <= zona[1]:
        lec.error("pdf.drawing.mask.zone_page_mm", "debe cumplir x1 > x0 e y1 > y0")
        return None
    return zona


class _Lector:
    """Recorre el diccionario por rutas con puntos y acumula los problemas encontrados."""

    def __init__(self, datos: dict):
        self.datos = datos
        self.errores: list[str] = []
        self._reportados: set[str] = set()

    def error(self, ruta: str, mensaje: str) -> None:
        if ruta not in self._reportados:
            self._reportados.add(ruta)
            self.errores.append(f"{ruta}: {mensaje}")

    def _buscar(self, ruta: str):
        """Valor del campo, o _FALTA. Si falta o es null un objeto intermedio, lo reporta
        una sola vez (no se repite por cada campo hijo)."""
        nodo, recorrido = self.datos, []
        for parte in ruta.split("."):
            if recorrido:
                padre = ".".join(recorrido)
                if nodo is None:
                    self._nulo(padre)
                    return _FALTA
                if not isinstance(nodo, dict):
                    self.error(padre, f"se esperaba un objeto {{...}}; tiene {_tipo(nodo)}")
                    return _FALTA
            recorrido.append(parte)
            if parte not in nodo:
                self.error(".".join(recorrido), "falta el campo")
                return _FALTA
            nodo = nodo[parte]
        return nodo

    def _nulo(self, ruta: str) -> None:
        motivo = MOTIVOS_NULL.get(ruta, "el componedor necesita un valor")
        self.error(ruta, f"es null ({motivo})")

    def _valor(self, ruta: str):
        valor = self._buscar(ruta)
        if valor is None:
            self._nulo(ruta)
            return _FALTA
        return valor

    def objeto(self, ruta: str) -> bool:
        valor = self._valor(ruta)
        if valor is _FALTA:
            return False
        if not isinstance(valor, dict):
            self.error(ruta, f"se esperaba un objeto {{...}}; tiene {_tipo(valor)}")
            return False
        return True

    def texto(self, ruta: str) -> str | None:
        valor = self._valor(ruta)
        if valor is _FALTA:
            return None
        if not isinstance(valor, str):
            self.error(ruta, f"se esperaba texto; tiene {_tipo(valor)}")
            return None
        return valor

    def opcional_texto(self, ruta: str) -> str | None:
        nodo = self.datos
        for parte in ruta.split("."):
            if not isinstance(nodo, dict) or parte not in nodo:
                return None
            nodo = nodo[parte]
        return nodo if isinstance(nodo, str) else None

    def opcional_numero(self, ruta: str) -> float | None:
        """Campo informativo: número finito >= 0, o None si falta, es null o no es válido."""
        nodo = self.datos
        for parte in ruta.split("."):
            if not isinstance(nodo, dict) or parte not in nodo:
                return None
            nodo = nodo[parte]
        return None if _problema_numero(nodo, False, True) else float(nodo)

    def booleano(self, ruta: str) -> bool | None:
        valor = self._valor(ruta)
        if valor is _FALTA:
            return None
        if not isinstance(valor, bool):
            self.error(ruta, f"se esperaba true o false; tiene {_tipo(valor)}")
            return None
        return valor

    def entero(self, ruta: str, minimo: int) -> int | None:
        valor = self._valor(ruta)
        if valor is _FALTA:
            return None
        if not isinstance(valor, int) or isinstance(valor, bool):
            self.error(ruta, f"se esperaba un número entero; tiene {_tipo(valor)}")
            return None
        if valor < minimo:
            self.error(ruta, f"debe ser al menos {minimo}; tiene {valor}")
            return None
        return valor

    def numero(self, ruta: str, positivo: bool = False, no_negativo: bool = False) -> float | None:
        valor = self._valor(ruta)
        if valor is _FALTA:
            return None
        problema = _problema_numero(valor, positivo, no_negativo)
        if problema:
            self.error(ruta, problema)
            return None
        return float(valor)

    def numeros(self, ruta: str, n: int, positivos: bool = False) -> tuple[float, ...] | None:
        valor = self._valor(ruta)
        if valor is _FALTA:
            return None
        if not isinstance(valor, list) or len(valor) != n:
            cuantos = f"{len(valor)} elementos" if isinstance(valor, list) else _tipo(valor)
            self.error(ruta, f"se esperaba una lista de {n} números; tiene {cuantos}")
            return None
        for i, item in enumerate(valor):
            problema = _problema_numero(item, positivos, False)
            if problema:
                self.error(ruta, f"elemento {i}: {problema}")
                return None
        return tuple(float(v) for v in valor)


def _problema_numero(valor, positivo: bool, no_negativo: bool) -> str | None:
    if not isinstance(valor, (int, float)) or isinstance(valor, bool):
        return f"se esperaba un número; tiene {_tipo(valor)}"
    if not math.isfinite(valor):
        return f"se esperaba un número finito; tiene {valor}"
    if positivo and valor <= 0:
        return f"debe ser mayor que 0; tiene {valor}"
    if no_negativo and valor < 0:
        return f"no puede ser negativo; tiene {valor}"
    return None


def _tipo(valor) -> str:
    if valor is None:
        return "null"
    if isinstance(valor, bool):
        return f"un booleano ({str(valor).lower()})"
    if isinstance(valor, str):
        return f"texto {valor!r}"
    if isinstance(valor, list):
        return "una lista"
    if isinstance(valor, dict):
        return "un objeto"
    return f"{type(valor).__name__} {valor!r}"
