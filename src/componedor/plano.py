"""Lectura y validación del plano.json (versiones 1, 2 y 3): qué detalles van en la hoja y dónde.

Formato: docs/formato_plano.md. Todas las rutas son relativas a la carpeta del plano.json.
Las posiciones van en mm de papel (origen en la esquina inferior izquierda de la hoja, Y
hacia arriba): `posicion_mm` es la esquina inferior izquierda de la PÁGINA del detalle,
igual que `colocar --posicion`.

Versión 2 (subfase 4.1) = versión 1 más, todo opcional:
  - "rotulo": {...} valores de los campos del rótulo. Aquí solo se exige que sea un objeto;
    sus claves las define el formato y las valida `componer` (rotulo.py).
  - "rosa_vientos": {"visible": true|false, "posicion_mm": [x, y]} (esquina inferior
    izquierda del rectángulo de la rosa). Por defecto visible y en su lugar.
  - en cada detalle, "etiqueta_escala": false para no poner su etiqueta "ESC: 1:N".
La versión 1 sigue siendo válida (sin esas claves).

Versión 3 (etapa 2 de la integración con el exportador) = versión 2 más la lista "dxf" y, en
"detalles", bloques de un DXF todavía SIN exportar ("origen" + "centro_mm", sin "manifiesto"):
ver plano_dxf.py. Se lee igual, pero `componer` no la compone hasta que estén exportados.

El plano.json lo escribe el editor HTML, pero el componedor SIEMPRE lo revalida: el editor
nunca es la fuente de la verdad. Los campos desconocidos se rechazan (un error de tipeo como
"centar" no debe pasar en silencio). Todos los problemas se juntan en un solo
`PlanoInvalido`, uno por línea, con la ruta del campo.
"""

import json
import math
from dataclasses import dataclass
from pathlib import Path

from componedor.plano_dxf import (
    BloquePendiente,
    DxfPlano,
    leer_lista_dxf,
    leer_pendiente,
)

VERSIONES_SOPORTADAS = (1, 2, 3)
CLAVES_PLANO = {"version", "formato", "plantilla", "detalles"}
CLAVES_DETALLE = {"id", "manifiesto", "posicion_mm", "centrar"}
CLAVES_PLANO_V2 = CLAVES_PLANO | {"rotulo", "rosa_vientos"}
CLAVES_DETALLE_V2 = CLAVES_DETALLE | {"etiqueta_escala"}
CLAVES_PLANO_V3 = CLAVES_PLANO_V2 | {"dxf"}
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

    @property
    def carpeta(self) -> Path:
        return self.ruta.parent


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
    v3 = datos.get("version") == 3
    v2 = datos.get("version") == 2 or v3  # la versión 3 incluye todo lo de la 2
    validas = CLAVES_PLANO_V3 if v3 else CLAVES_PLANO_V2 if v2 else CLAVES_PLANO

    for clave in sorted(set(datos) - validas):
        if clave == "dxf":
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
                       f"versiones 1, 2 y 3")

    formato = _ruta(datos, "formato", carpeta, errores, obligatoria=True)
    plantilla = _ruta(datos, "plantilla", carpeta, errores, obligatoria=False)

    dxfs = leer_lista_dxf(datos["dxf"], carpeta, errores) if v3 and "dxf" in datos else {}
    detalles, pendientes = [], []
    lista = datos.get("detalles")
    if "detalles" not in datos:
        errores.append("detalles: falta el campo")
    elif not isinstance(lista, list):
        errores.append(f"detalles: se esperaba una lista; tiene {_tipo(lista)}")
    elif not lista:
        errores.append("detalles: la lista está vacía; el plano necesita al menos un detalle")
    else:
        vistos: dict[str, int] = {}
        for i, item in enumerate(lista):
            if v3 and isinstance(item, dict) and "origen" in item:
                detalle = leer_pendiente(item, f"detalles[{i}]", dxfs, errores)
            else:
                detalle = _detalle(item, f"detalles[{i}]", carpeta, errores, v2)
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

    if errores:
        n = len(errores)
        raise PlanoInvalido(
            f"El plano '{ruta}' no es válido ({n} {'problema' if n == 1 else 'problemas'}):\n"
            + "\n".join(f"- {e}" for e in errores)
        )
    return Plano(ruta, version, formato, plantilla, tuple(detalles), rotulo, rosa,
                 tuple(dxfs.values()), tuple(pendientes))


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
             v2: bool = False) -> DetallePlano | None:
    if not isinstance(item, dict):
        errores.append(f"{donde}: se esperaba un objeto {{...}}; tiene {_tipo(item)}")
        return None
    n_errores = len(errores)
    validas = CLAVES_DETALLE_V2 if v2 else CLAVES_DETALLE
    for clave in sorted(set(item) - validas):
        if clave in CLAVES_DETALLE_V2:
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

    if len(errores) > n_errores:
        return None
    return DetallePlano(ident, manifiesto, posicion, bool(centrar), etiqueta)


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
