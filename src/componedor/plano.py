"""Lectura y validación del plano.json (versión 1): qué detalles van en la hoja y dónde.

Formato: docs/formato_plano.md. Todas las rutas son relativas a la carpeta del plano.json.
Las posiciones van en mm de papel (origen en la esquina inferior izquierda de la hoja, Y
hacia arriba): `posicion_mm` es la esquina inferior izquierda de la PÁGINA del detalle,
igual que `colocar --posicion`.

El plano.json lo escribirá el editor HTML (subfase 3.3), pero el componedor SIEMPRE lo
revalida: el editor nunca es la fuente de la verdad. Los campos desconocidos se rechazan
(un error de tipeo como "centar" no debe pasar en silencio). Todos los problemas se juntan
en un solo `PlanoInvalido`, uno por línea, con la ruta del campo.
"""

import json
import math
from dataclasses import dataclass
from pathlib import Path

VERSIONES_SOPORTADAS = (1,)
CLAVES_PLANO = {"version", "formato", "plantilla", "detalles"}
CLAVES_DETALLE = {"id", "manifiesto", "posicion_mm", "centrar"}


class PlanoInvalido(ValueError):
    """El plano.json no cumple el formato; el mensaje lista todos los problemas."""


@dataclass(frozen=True)
class DetallePlano:
    id: str
    manifiesto: Path  # ruta ya resuelta respecto de la carpeta del plano
    posicion_mm: tuple[float, float] | None  # esquina inferior izquierda de la página
    centrar: bool  # True: centrado en el área de dibujo (posicion_mm es None)


@dataclass(frozen=True)
class Plano:
    ruta: Path
    version: int
    formato: Path  # resuelta
    plantilla: Path | None  # None: la del formato
    detalles: tuple[DetallePlano, ...]  # en orden de apilado (el último queda encima)

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

    for clave in sorted(set(datos) - CLAVES_PLANO):
        errores.append(f"{clave}: campo no reconocido (campos válidos: "
                       f"{', '.join(sorted(CLAVES_PLANO))})")

    version = datos.get("version")
    if "version" not in datos:
        errores.append("version: falta el campo")
    elif not isinstance(version, int) or isinstance(version, bool):
        errores.append(f"version: se esperaba un número entero; tiene {_tipo(version)}")
    elif version not in VERSIONES_SOPORTADAS:
        errores.append(f"version: versión {version} no soportada; el componedor entiende la "
                       f"versión {', '.join(map(str, VERSIONES_SOPORTADAS))}")

    formato = _ruta(datos, "formato", carpeta, errores, obligatoria=True)
    plantilla = _ruta(datos, "plantilla", carpeta, errores, obligatoria=False)

    detalles = []
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
            detalle = _detalle(item, f"detalles[{i}]", carpeta, errores)
            # El id repetido se informa aunque el detalle tenga otros problemas.
            ident = item.get("id") if isinstance(item, dict) else None
            if isinstance(ident, str) and ident.strip():
                if ident in vistos:
                    errores.append(f"detalles[{i}].id: '{ident}' está repetido (ya lo usa "
                                   f"detalles[{vistos[ident]}]); cada id debe ser único")
                    continue
                vistos[ident] = i
            if detalle is not None:
                detalles.append(detalle)

    if errores:
        n = len(errores)
        raise PlanoInvalido(
            f"El plano '{ruta}' no es válido ({n} {'problema' if n == 1 else 'problemas'}):\n"
            + "\n".join(f"- {e}" for e in errores)
        )
    return Plano(ruta, version, formato, plantilla, tuple(detalles))


def _detalle(item, donde: str, carpeta: Path, errores: list[str]) -> DetallePlano | None:
    if not isinstance(item, dict):
        errores.append(f"{donde}: se esperaba un objeto {{...}}; tiene {_tipo(item)}")
        return None
    n_errores = len(errores)
    for clave in sorted(set(item) - CLAVES_DETALLE):
        errores.append(f"{donde}.{clave}: campo no reconocido (campos válidos: "
                       f"{', '.join(sorted(CLAVES_DETALLE))})")

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

    if len(errores) > n_errores:
        return None
    return DetallePlano(ident, manifiesto, posicion, bool(centrar))


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
