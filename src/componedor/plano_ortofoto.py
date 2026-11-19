"""plano.json versión 4: la ortofoto de fondo del plano (una por plano).

La versión 4 es la versión 3 más, opcional:

  "ortofoto": {"archivo": "../data/input/ortofotos/Foto_tunez.tif",
               "bytes": 3445480,
               "modificado": "2026-11-18T21:26:25Z",
               "crs": null,
               "crs_dibujo": "EPSG:9377",
               "opacidad": 1,
               "extender": false,
               "cuadricula": {"visible": true, "intervalo_m": 50}}

- `archivo`: el GeoTIFF, relativo a la carpeta del plano (o absoluto, p. ej. en otro disco).
- `bytes` y `modificado` (fecha de modificación, UTC, al segundo): los del archivo cuando se
  eligió, para notar que es otro o que cambió; opcionales. `componer` usa el original solo si
  coinciden; si no, la copia reducida (ver ortofoto_fuente.py).
- `crs`: el sistema de la ortofoto elegido A MANO, solo cuando el archivo no trae el suyo
  (si lo trae, manda el del archivo y aquí va null o no va).
- `crs_dibujo`: el sistema de coordenadas del DXF (el Exportador todavía no lo informa: lo
  elige el usuario). null mientras no se elija.
- `opacidad`: de 0 a 1 (1 = opaca, por defecto).
- `extender` (versión 5): con UN solo detalle con ortofoto, la foto cubre toda el área de
  dibujo, con el mismo mapeo CAD → papel de ese detalle (solo cambia el recorte); los detalles
  sin ortofoto llevan fondo blanco del tamaño de su página. Con otro número de detalles, no
  cuenta (advertencia). Por defecto false.
- `cuadricula` (versión 5): la cuadrícula de coordenadas (`cuadricula.py`), en la página de cada
  detalle con ortofoto (o en toda el área de dibujo si se extiende). `visible` (false por
  defecto) e `intervalo_m` (m, > 0; sin él, el de componedor.json: 50).

Va detrás de todos los detalles, recortada a la caja de cada uno; fuera de los detalles, nada.
Este módulo solo valida la sección; la pone en el PDF `ortofoto_pdf` (desde `componer`).
"""

import math
import re
from dataclasses import dataclass
from pathlib import Path

CLAVES_ORTOFOTO = {"archivo", "bytes", "modificado", "crs", "crs_dibujo", "opacidad",
                   "extender", "cuadricula"}
CLAVES_CUADRICULA = {"visible", "intervalo_m"}
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
    extender: bool = False  # versión 5: a toda el área de dibujo (un solo detalle con ortofoto)
    cuadricula: bool = False  # versión 5: cuadrícula de coordenadas visible
    intervalo_m: float | None = None  # None: el de componedor.json


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
    extender = valor.get("extender", False)
    if not isinstance(extender, bool):
        errores.append(f"ortofoto.extender: se esperaba true o false; tiene {extender!r}")
    visible, intervalo = False, None
    if "cuadricula" in valor:
        c = valor["cuadricula"]
        if not isinstance(c, dict):
            errores.append(f"ortofoto.cuadricula: se esperaba un objeto {{\"visible\", "
                           f"\"intervalo_m\"}}; tiene {_tipo(c)}")
        else:
            for clave in sorted(set(c) - CLAVES_CUADRICULA):
                errores.append(f"ortofoto.cuadricula.{clave}: campo no reconocido (campos "
                               f"válidos: intervalo_m, visible)")
            visible = c.get("visible", False)
            if not isinstance(visible, bool):
                errores.append(f"ortofoto.cuadricula.visible: se esperaba true o false; tiene "
                               f"{visible!r}")
            intervalo = c.get("intervalo_m")
            if intervalo is not None and (isinstance(intervalo, bool)
                                          or not isinstance(intervalo, (int, float))
                                          or not math.isfinite(intervalo)
                                          or not 0 < intervalo <= 100000):
                errores.append(f"ortofoto.cuadricula.intervalo_m: se esperaba un número de m "
                               f"> 0; tiene {intervalo!r}")
    opacidad = valor.get("opacidad", 1)
    if (isinstance(opacidad, bool) or not isinstance(opacidad, (int, float))
            or not math.isfinite(opacidad) or not 0 <= opacidad <= 1):
        errores.append(f"ortofoto.opacidad: se esperaba un número de 0 a 1; tiene {opacidad!r}")
    if len(errores) != n:
        return None
    return OrtofotoPlano((carpeta / archivo).resolve(), tamano, valor.get("crs"),
                         valor.get("crs_dibujo"), float(opacidad), modificado, extender,
                         visible, float(intervalo) if intervalo is not None else None)
