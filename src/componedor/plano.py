"""Lectura y validación del plano.json (versiones 1 a 7): qué detalles van en la hoja y dónde.

Formato: docs/formato_plano.md. Todas las rutas son relativas a la carpeta del plano.json.
Las posiciones van en mm de papel (origen en la esquina inferior izquierda de la hoja, Y
hacia arriba): `posicion_mm` es la esquina inferior izquierda de la PÁGINA del detalle,
igual que `colocar --posicion`.

Versión 2 (subfase 4.1) = versión 1 más, todo opcional:
  - "rotulo": {...} valores de los campos del rótulo. Aquí solo se exige que sea un objeto;
    sus claves las define el formato y las valida `componer` (rotulo.py).
  - "rosa_vientos": {"visible": true|false, "posicion_mm": [x, y]} (esquina inferior
    izquierda del rectángulo de la rosa). Por defecto visible y en su lugar.
  - en cada detalle, "etiqueta_escala": false para no poner su etiqueta "ESC: 1:N";
  - en cada detalle, "margen_mm": N (0 a 50) para recortar su página a su dibujo más N mm
    (sin la clave: el margen de componedor.json, 1 mm; ver recorte_detalle.py).
La versión 1 sigue siendo válida (sin esas claves).

Versión 3 (etapa 2 de la integración con el exportador) = versión 2 más la lista "dxf" y, en
"detalles", bloques de un DXF todavía SIN exportar ("origen" + "centro_mm", sin "manifiesto"):
ver plano_dxf.py. Se lee igual, pero `componer` no la compone hasta que estén exportados.

Versión 4 (ortofoto) = versión 3 más "ortofoto": la ortofoto de fondo (plano_ortofoto.py),
detrás de TODOS los detalles.

Versión 6 (zonas del Model Space, Fase 10e3) = versión 5 más "zonas" en las entradas de "dxf"
y, en un detalle exportado desde una zona, "origen": {"zona": "<nombre>"}: ver plano_zonas.py.
Una zona que ningún detalle nombra es un borrador: `componer` no compone el plano hasta
exportarla.

Versión 7 (varias hojas de un proyecto, «Nueva hoja a partir de esta») = versión 6 más:
  - "detalles" puede ir vacío: una hoja con solo el rótulo (`componer` la compone, con aviso);
  - "copiado_de": {"hoja": "<plano.json>", "revisar": ["notas", ...]}: la hoja se hizo a partir
    de otra y esos campos del rótulo se copiaron sin revisar todavía (el editor y `componer`
    lo avisan hasta que se toquen). Las hojas de un proyecto se listan en <proyecto>.hojas.json
    (hojas_proyecto.py), que da «hoja», «de» y el número de plano automáticos.

Versión 5 (ortofoto por detalle) = versión 4 más, en cada detalle (exportado o pendiente),
"ortofoto": true para que lleve la ortofoto detrás (sin la clave: false). Un plano versión 4
con ortofoto se lee como si todos los detalles la usaran (lo que hacía la versión 4): así se
migra. Un detalle con "ortofoto": true en un plano sin la sección "ortofoto" es error.

El plano.json lo escribe el editor HTML, pero el componedor SIEMPRE lo revalida: el editor
nunca es la fuente de la verdad. Los campos desconocidos se rechazan (un error de tipeo como
"centar" no debe pasar en silencio). Todos los problemas se juntan en un solo
`PlanoInvalido`, uno por línea, con la ruta del campo.
"""

import json
import math
from dataclasses import dataclass, replace
from pathlib import Path

from componedor.plano_dxf import (
    BloquePendiente,
    DxfPlano,
    leer_lista_dxf,
    leer_pendiente,
)
from componedor.plano_ortofoto import OrtofotoPlano, leer_ortofoto
from componedor.plano_zonas import ZonaPlano, leer_origen_zona, leer_zonas
from componedor.recorte_detalle import MARGEN_MAXIMO_MM, margen_valido

VERSIONES_SOPORTADAS = (1, 2, 3, 4, 5, 6, 7)
CLAVES_PLANO = {"version", "formato", "plantilla", "detalles"}
CLAVES_DETALLE = {"id", "manifiesto", "posicion_mm", "centrar"}
CLAVES_PLANO_V2 = CLAVES_PLANO | {"rotulo", "rosa_vientos"}
CLAVES_DETALLE_V2 = CLAVES_DETALLE | {"etiqueta_escala", "margen_mm"}
CLAVES_DETALLE_V5 = CLAVES_DETALLE_V2 | {"ortofoto"}
CLAVES_DETALLE_V6 = CLAVES_DETALLE_V5 | {"origen"}  # exportado desde una zona: {"zona": nombre}
CLAVES_PLANO_V3 = CLAVES_PLANO_V2 | {"dxf"}
CLAVES_PLANO_V4 = CLAVES_PLANO_V3 | {"ortofoto"}
CLAVES_PLANO_V7 = CLAVES_PLANO_V4 | {"copiado_de"}
CLAVES_COPIADO = {"hoja", "revisar"}
CLAVES_ROSA = {"visible", "posicion_mm"}


class PlanoInvalido(ValueError):
    """El plano.json no cumple el formato; el mensaje lista todos los problemas."""


@dataclass(frozen=True)
class DetallePlano:
    id: str
    manifiesto: Path  # ruta ya resuelta respecto de la carpeta del plano
    posicion_mm: tuple[float, float] | None  # esquina inferior izquierda de la página
    centrar: bool  # True: centrado en el área de dibujo (posicion_mm es None)
    etiqueta_escala: bool = True  # versión 2: false = sin etiqueta "ESC: 1:N"
    ortofoto: bool = False  # versión 5: lleva la ortofoto detrás (versión 4: todos)
    zona: str | None = None  # versión 6: exportado desde esa zona (su nombre)
    margen_mm: float | None = None  # versión 2: margen del recorte; None: el de componedor.json


@dataclass(frozen=True)
class RosaPlano:
    visible: bool = True
    posicion_mm: tuple[float, float] | None = None  # None: en su lugar original


@dataclass(frozen=True)
class Plano:
    ruta: Path
    version: int
    formato: Path  # resuelta
    plantilla: Path | None  # None: la del formato
    detalles: tuple[DetallePlano, ...]  # en orden de apilado (el último queda encima)
    rotulo: dict | None = None  # versión 2: valores del rótulo (los valida componer)
    rosa: RosaPlano | None = None  # versión 2: None = la rosa como viene (visible, en su sitio)
    dxf: tuple[DxfPlano, ...] = ()  # versión 3: los DXF de los bloques pendientes
    pendientes: tuple[BloquePendiente, ...] = ()  # versión 3: bloques sin exportar
    ortofoto: OrtofotoPlano | None = None  # versión 4: la ortofoto de fondo
    zonas: tuple[ZonaPlano, ...] = ()  # versión 6: las zonas del Model Space del plano
    copiado_de: str | None = None  # versión 7: el plano.json de la hoja de donde se copió
    revisar: tuple[str, ...] = ()  # versión 7: campos del rótulo copiados sin revisar

    @property
    def carpeta(self) -> Path:
        return self.ruta.parent

    @property
    def borradores(self) -> tuple[ZonaPlano, ...]:
        """Las zonas que ningún detalle nombra: todavía sin exportar."""
        exportadas = {d.zona for d in self.detalles if d.zona}
        return tuple(z for z in self.zonas if z.nombre not in exportadas)


def leer_plano(ruta: Path | str) -> Plano:
    """Lee el plano.json y valida su estructura. Lanza `PlanoInvalido`."""
    ruta = Path(ruta)
    if not ruta.is_file():
        raise PlanoInvalido(f"No se encontró el plano '{ruta}'.")
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except UnicodeDecodeError as e:
        raise PlanoInvalido(f"El plano '{ruta}' no está en UTF-8: {e}") from e
    except json.JSONDecodeError as e:
        raise PlanoInvalido(
            f"El plano '{ruta}' no es un JSON válido (línea {e.lineno}, columna {e.colno}): "
            f"{e.msg}."
        ) from e
    if not isinstance(datos, dict):
        raise PlanoInvalido(f"El plano '{ruta}' debe ser un objeto JSON {{...}}.")

    errores: list[str] = []
    carpeta = ruta.parent
    v7 = datos.get("version") == 7  # varias hojas: detalles vacíos y "copiado_de"
    v6 = datos.get("version") == 6 or v7  # zonas del Model Space (plano_zonas.py)
    v5 = datos.get("version") == 5 or v6
    v4 = datos.get("version") == 4 or v5
    v3 = datos.get("version") == 3 or v4  # cada versión incluye todo lo de la anterior
    v2 = datos.get("version") == 2 or v3
    validas = (CLAVES_PLANO_V7 if v7 else CLAVES_PLANO_V4 if v4 else CLAVES_PLANO_V3 if v3
               else CLAVES_PLANO_V2 if v2 else CLAVES_PLANO)

    for clave in sorted(set(datos) - validas):
        if clave == "copiado_de":
            errores.append("copiado_de: solo existe en la versión 7 del plano (use \"version\": 7)")
        elif clave == "ortofoto":
            errores.append("ortofoto: solo existe en la versión 4 del plano (use \"version\": 4)")
        elif clave == "dxf":
            errores.append("dxf: solo existe en la versión 3 del plano (use \"version\": 3)")
        elif clave in CLAVES_PLANO_V2:
            errores.append(f"{clave}: solo existe en la versión 2 del plano (use \"version\": 2)")
        else:
            errores.append(f"{clave}: campo no reconocido (campos válidos: "
                           f"{', '.join(sorted(validas))})")

    version = datos.get("version")
    if "version" not in datos:
        errores.append("version: falta el campo")
    elif not isinstance(version, int) or isinstance(version, bool):
        errores.append(f"version: se esperaba un número entero; tiene {_tipo(version)}")
    elif version not in VERSIONES_SOPORTADAS:
        errores.append(f"version: versión {version} no soportada; el componedor entiende las "
                       f"versiones 1 a 7")

    formato = _ruta(datos, "formato", carpeta, errores, obligatoria=True)
    plantilla = _ruta(datos, "plantilla", carpeta, errores, obligatoria=False)

    dxfs = leer_lista_dxf(datos["dxf"], carpeta, errores, v6) if v3 and "dxf" in datos else {}
    zonas = _zonas(datos.get("dxf"), dxfs, errores) if v6 else []
    nombres_zonas = {z.nombre for z in zonas}
    detalles, pendientes = [], []
    lista = datos.get("detalles")
    if "detalles" not in datos:
        errores.append("detalles: falta el campo")
    elif not isinstance(lista, list):
        errores.append(f"detalles: se esperaba una lista; tiene {_tipo(lista)}")
    elif not lista and not (v6 and zonas) and not v7:  # v6: solo borradores; v7: hoja vacía
        errores.append("detalles: la lista está vacía; el plano necesita al menos un detalle "
                       "(una hoja con solo el rótulo es de la versión 7)")
    else:
        vistos: dict[str, int] = {}
        for i, item in enumerate(lista):
            exportada = isinstance(item, dict) and "manifiesto" in item
            if v3 and isinstance(item, dict) and "origen" in item and not (v6 and exportada):
                detalle = leer_pendiente(item, f"detalles[{i}]", dxfs, errores, v5)
            else:
                detalle = _detalle(item, f"detalles[{i}]", carpeta, errores, v2, v5,
                                   nombres_zonas if v6 else None)
            # El id repetido se informa aunque el detalle tenga otros problemas.
            ident = item.get("id") if isinstance(item, dict) else None
            if isinstance(ident, str) and ident.strip():
                if ident in vistos:
                    errores.append(f"detalles[{i}].id: '{ident}' está repetido (ya lo usa "
                                   f"detalles[{vistos[ident]}]); cada id debe ser único")
                    continue
                vistos[ident] = i
            if isinstance(detalle, BloquePendiente):
                pendientes.append(detalle)
            elif detalle is not None:
                detalles.append(detalle)

    rotulo = None
    if v2 and "rotulo" in datos:
        rotulo = datos["rotulo"]
        if not isinstance(rotulo, dict):
            errores.append(f"rotulo: se esperaba un objeto {{...}} con los valores del rótulo; "
                           f"tiene {_tipo(rotulo)}")
    rosa = _rosa(datos["rosa_vientos"], errores) if v2 and "rosa_vientos" in datos else None
    ortofoto = (leer_ortofoto(datos["ortofoto"], carpeta, errores)
                if v4 and "ortofoto" in datos else None)
    if "ortofoto" not in datos:
        for d in [*detalles, *pendientes]:
            if d.ortofoto:
                errores.append(f"detalle '{d.id}': lleva \"ortofoto\": true, pero el plano no "
                               f"tiene la sección \"ortofoto\" (qué ortofoto usar)")
    elif version == 4:  # la versión 4 la ponía detrás de todos: se migra así
        detalles = [replace(d, ortofoto=True) for d in detalles]
        pendientes = [replace(d, ortofoto=True) for d in pendientes]

    copiado_de, revisar = _copiado(datos["copiado_de"], errores) if v7 and "copiado_de" in datos \
        else (None, ())

    vistas: dict[str, str] = {}
    for d in detalles:
        if d.zona in vistas:
            errores.append(f"detalle '{d.id}': la zona '{d.zona}' ya la usa el detalle "
                           f"'{vistas[d.zona]}' (cada zona da un solo paquete)")
        elif d.zona:
            vistas[d.zona] = d.id
    if errores:
        n = len(errores)
        raise PlanoInvalido(
            f"El plano '{ruta}' no es válido ({n} {'problema' if n == 1 else 'problemas'}):\n"
            + "\n".join(f"- {e}" for e in errores)
        )
    return Plano(ruta, version, formato, plantilla, tuple(detalles), rotulo, rosa,
                 tuple(dxfs.values()), tuple(pendientes), ortofoto, tuple(zonas), copiado_de,
                 revisar)


def _copiado(valor, errores: list[str]) -> tuple[str | None, tuple[str, ...]]:
    """"copiado_de": {"hoja": "<plano.json>", "revisar": [campos del rótulo]} (versión 7)."""
    if not isinstance(valor, dict):
        errores.append("copiado_de: se esperaba {\"hoja\": \"<plano.json>\", \"revisar\": [...]}")
        return None, ()
    for clave in sorted(set(valor) - CLAVES_COPIADO):
        errores.append(f"copiado_de.{clave}: campo no reconocido (campos válidos: hoja, revisar)")
    hoja = valor.get("hoja")
    if not (isinstance(hoja, str) and hoja.strip()):
        errores.append("copiado_de.hoja: se esperaba el nombre del plano.json de la otra hoja")
        hoja = None
    revisar = valor.get("revisar", [])
    if not (isinstance(revisar, list) and all(isinstance(c, str) and c.strip() for c in revisar)):
        errores.append("copiado_de.revisar: se esperaba una lista de campos del rótulo")
        revisar = []
    return hoja, tuple(revisar)


def _zonas(lista, dxfs: dict, errores: list[str]) -> list[ZonaPlano]:
    """Las "zonas" de las entradas de "dxf" (versión 6), con nombres únicos en el plano."""
    zonas: list[ZonaPlano] = []
    if not isinstance(lista, list):
        return zonas
    for i, item in enumerate(lista):
        if isinstance(item, dict) and "zonas" in item and item.get("id") in dxfs:
            zonas += leer_zonas(item["zonas"], item["id"], f"dxf[{i}].zonas", errores)
    vistos: set[str] = set()
    for z in zonas:
        if z.nombre in vistos:
            errores.append(f"zonas: el nombre '{z.nombre}' está repetido (cada zona es un paquete)")
        vistos.add(z.nombre)
    return zonas


def _rosa(valor, errores: list[str]) -> RosaPlano | None:
    """"rosa_vientos": {"visible": bool, "posicion_mm": [x, y]}, ambos opcionales."""
    if not isinstance(valor, dict):
        errores.append(f"rosa_vientos: se esperaba un objeto {{\"visible\": ..., "
                       f"\"posicion_mm\": [x, y]}}; tiene {_tipo(valor)}")
        return None
    n = len(errores)
    for clave in sorted(set(valor) - CLAVES_ROSA):
        errores.append(f"rosa_vientos.{clave}: campo no reconocido (campos válidos: "
                       f"{', '.join(sorted(CLAVES_ROSA))})")
    visible = valor.get("visible", True)
    if not isinstance(visible, bool):
        errores.append(f"rosa_vientos.visible: se esperaba true o false; tiene {_tipo(visible)}")
    posicion = None
    if "posicion_mm" in valor:
        p = valor["posicion_mm"]
        if not isinstance(p, list) or len(p) != 2 or not all(_es_numero(v) for v in p):
            errores.append(f"rosa_vientos.posicion_mm: se esperaba [x, y] con 2 números finitos "
                           f"en mm; tiene {p!r}")
        else:
            posicion = (float(p[0]), float(p[1]))
    return RosaPlano(visible, posicion) if len(errores) == n else None


def _detalle(item, donde: str, carpeta: Path, errores: list[str],
             v2: bool = False, v5: bool = False,
             zonas: set[str] | None = None) -> DetallePlano | None:
    """Un detalle exportado. `zonas`: los nombres de las zonas del plano (versión 6; con ellas
    se admite "origen": {"zona": nombre})."""
    if not isinstance(item, dict):
        errores.append(f"{donde}: se esperaba un objeto {{...}}; tiene {_tipo(item)}")
        return None
    n_errores = len(errores)
    validas = (CLAVES_DETALLE_V6 if zonas is not None else CLAVES_DETALLE_V5 if v5
               else CLAVES_DETALLE_V2 if v2 else CLAVES_DETALLE)
    for clave in sorted(set(item) - validas):
        if clave == "ortofoto":
            errores.append(f"{donde}.ortofoto: solo existe en la versión 5 del plano "
                           f"(use \"version\": 5)")
        elif clave in CLAVES_DETALLE_V2:
            errores.append(f"{donde}.{clave}: solo existe en la versión 2 del plano "
                           f"(use \"version\": 2)")
        else:
            errores.append(f"{donde}.{clave}: campo no reconocido (campos válidos: "
                           f"{', '.join(sorted(validas))})")

    ident = item.get("id")
    if "id" not in item:
        errores.append(f"{donde}.id: falta el campo")
    elif not isinstance(ident, str) or not ident.strip():
        errores.append(f"{donde}.id: se esperaba un texto no vacío; tiene {_tipo(ident)}")

    manifiesto = _ruta(item, "manifiesto", carpeta, errores, obligatoria=True, donde=donde)

    tiene_posicion = "posicion_mm" in item
    centrar = item.get("centrar", False)
    if "centrar" in item and not isinstance(centrar, bool):
        errores.append(f"{donde}.centrar: se esperaba true o false; tiene {_tipo(centrar)}")
        centrar = False
    if tiene_posicion and centrar:
        errores.append(f"{donde}: lleva posicion_mm y centrar: true a la vez; use solo uno")
    elif not tiene_posicion and not centrar:
        errores.append(f"{donde}: falta posicion_mm [x, y] o centrar: true (uno de los dos)")

    posicion = None
    if tiene_posicion:
        valor = item["posicion_mm"]
        if (not isinstance(valor, list) or len(valor) != 2
                or not all(_es_numero(v) for v in valor)):
            errores.append(f"{donde}.posicion_mm: se esperaba [x, y] con 2 números finitos en "
                           f"mm; tiene {valor!r}")
        else:
            posicion = (float(valor[0]), float(valor[1]))

    etiqueta = item.get("etiqueta_escala", True)
    if not isinstance(etiqueta, bool):
        errores.append(f"{donde}.etiqueta_escala: se esperaba true o false; tiene {_tipo(etiqueta)}")

    usa = item.get("ortofoto", False)
    if not isinstance(usa, bool):
        errores.append(f"{donde}.ortofoto: se esperaba true o false; tiene {_tipo(usa)}")

    margen = item.get("margen_mm")
    if margen is not None and not margen_valido(margen):
        errores.append(f"{donde}.margen_mm: se esperaba un número de 0 a {MARGEN_MAXIMO_MM:g} mm "
                       f"(el borde blanco alrededor del dibujo); tiene {margen!r}")

    zona = None
    if zonas is not None and "origen" in item:
        zona = leer_origen_zona(item["origen"], f"{donde}.origen", zonas, errores)

    if len(errores) > n_errores:
        return None
    return DetallePlano(ident, manifiesto, posicion, bool(centrar), etiqueta, usa, zona,
                        float(margen) if margen is not None else None)


def _ruta(datos: dict, clave: str, carpeta: Path, errores: list[str], obligatoria: bool,
          donde: str = "") -> Path | None:
    nombre = f"{donde}.{clave}" if donde else clave
    if clave not in datos:
        if obligatoria:
            errores.append(f"{nombre}: falta el campo")
        return None
    valor = datos[clave]
    if valor is None and not obligatoria:
        return None
    if not isinstance(valor, str) or not valor.strip():
        errores.append(f"{nombre}: se esperaba una ruta (texto); tiene {_tipo(valor)}")
        return None
    ruta = Path(valor)
    return ruta if ruta.is_absolute() else carpeta / ruta


def _es_numero(valor) -> bool:
    return (isinstance(valor, (int, float)) and not isinstance(valor, bool)
            and math.isfinite(valor))


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
