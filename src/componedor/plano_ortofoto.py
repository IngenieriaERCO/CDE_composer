"""plano.json versión 4: la ortofoto de fondo del plano (una por plano).

La versión 4 es la versión 3 más, opcional:

  "ortofoto": {"archivo": "../data/input/ortofotos/Foto_tunez.tif",
               "bytes": 3445480,
               "modificado": "2026-11-18T21:26:25Z",
               "crs": null,
               "crs_dibujo": "EPSG:9377",
               "opacidad": 1}

- `archivo`: el GeoTIFF, relativo a la carpeta del plano (o absoluto, p. ej. en otro disco).
- `bytes` y `modificado` (fecha de modificación, UTC, al segundo): los del archivo cuando se
  eligió, para notar que es otro o que cambió; opcionales. `componer` usa el original solo si
  coinciden; si no, la copia reducida (ver ortofoto_fuente.py).
- `crs`: el sistema de la ortofoto elegido A MANO, solo cuando el archivo no trae el suyo
  (si lo trae, manda el del archivo y aquí va null o no va).
- `crs_dibujo`: el sistema de coordenadas del DXF (el Exportador todavía no lo informa: lo
  elige el usuario). null mientras no se elija.
- `opacidad`: de 0 a 1 (1 = opaca, por defecto).

Va detrás de todos los detalles, recortada a la caja de cada uno; fuera de los detalles, nada.
Este módulo solo valida la sección; la pone en el PDF `ortofoto_pdf` (desde `componer`).
"""

import math
import re
from dataclasses import dataclass
from pathlib import Path

CLAVES_ORTOFOTO = {"archivo", "bytes", "modificado", "crs", "crs_dibujo", "opacidad"}
RE_EPSG = re.compile(r"^EPSG:\d{4,6}$")  # igual que ortofoto.RE_EPSG
RE_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


@dataclass(frozen=True)
class OrtofotoPlano:
    archivo: Path  # resuelta respecto de la carpeta del plano
    bytes: int | None = None
    crs: str | None = None
    crs_dibujo: str | None = None
    opacidad: float = 1.0
    modificado: str | None = None  # "AAAA-MM-DDTHH:MM:SSZ"


def _tipo(v) -> str:
    return {dict: "un objeto", list: "una lista", str: "un texto", bool: "true/false",
            type(None): "null"}.get(type(v), "un número")


def leer_ortofoto(valor, carpeta: Path, errores: list[str]) -> OrtofotoPlano | None:
    """La sección "ortofoto" (o None, con sus problemas en `errores`)."""
    if not isinstance(valor, dict):
        errores.append(f"ortofoto: se esperaba un objeto {{\"archivo\": ...}}; tiene "
                       f"{_tipo(valor)}")
        return None
    n = len(errores)
    for clave in sorted(set(valor) - CLAVES_ORTOFOTO):
        errores.append(f"ortofoto.{clave}: campo no reconocido (campos válidos: "
                       f"{', '.join(sorted(CLAVES_ORTOFOTO))})")
    archivo = valor.get("archivo")
    if not isinstance(archivo, str) or not archivo.strip():
        errores.append("ortofoto.archivo: se esperaba la ruta del GeoTIFF (texto no vacío)")
    elif Path(archivo).suffix.lower() not in (".tif", ".tiff"):
        errores.append(f"ortofoto.archivo: '{archivo}' no es un .tif ni un .tiff")
    tamano = valor.get("bytes")
    if tamano is not None and (isinstance(tamano, bool) or not isinstance(tamano, int)
                               or tamano < 0):
        errores.append(f"ortofoto.bytes: se esperaba un entero ≥ 0; tiene {tamano!r}")
    modificado = valor.get("modificado")
    if modificado is not None and not (isinstance(modificado, str) and RE_FECHA.match(modificado)):
        errores.append(f"ortofoto.modificado: se esperaba la fecha «AAAA-MM-DDTHH:MM:SSZ» o "
                       f"null; tiene {modificado!r}")
    for clave in ("crs", "crs_dibujo"):
        v = valor.get(clave)
        if v is not None and not (isinstance(v, str) and RE_EPSG.match(v)):
            errores.append(f"ortofoto.{clave}: se esperaba «EPSG:<código>» (p. ej. EPSG:9377) "
                           f"o null; tiene {v!r}")
    opacidad = valor.get("opacidad", 1)
    if (isinstance(opacidad, bool) or not isinstance(opacidad, (int, float))
            or not math.isfinite(opacidad) or not 0 <= opacidad <= 1):
        errores.append(f"ortofoto.opacidad: se esperaba un número de 0 a 1; tiene {opacidad!r}")
    if len(errores) != n:
        return None
    return OrtofotoPlano((carpeta / archivo).resolve(), tamano, valor.get("crs"),
                         valor.get("crs_dibujo"), float(opacidad), modificado)
