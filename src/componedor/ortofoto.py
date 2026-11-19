"""Ortofoto (GeoTIFF) del plano: leer SOLO la cabecera y armar la ficha con sus avisos.

Se lee con rasterio (GDAL) sin cargar los píxeles: sirve igual para un GeoTIFF de unos MB que
para un BigTIFF de varios GB. La ficha dice lo que importa para usarla de fondo:

- tamaño en píxeles, bandas, tipo de dato, compresión, mosaicos y pirámides (velocidad);
- sistema de coordenadas (CRS) y su origen: el del archivo o, si no lo trae, NINGUNO (no se
  supone: el usuario lo elige en el editor);
- resolución (m por píxel), límites en su sistema y si está girada;
- fondo transparente: banda alfa, máscara o valor «nodata».

Los avisos van con nivel: "error" (no se puede usar), "elegir" (falta el sistema: se usa el
selector) o "aviso" (se puede usar, pero conviene saberlo: p. ej. sin pirámides será lenta).

Sistemas de coordenadas: se escriben "EPSG:<código>". `SISTEMAS_COMUNES` son los que ofrece el
selector del editor (los de Colombia); cualquier otro EPSG proyectado se acepta si GDAL lo conoce.
"""

import math
import re
from datetime import UTC, datetime
from pathlib import Path

import rasterio
from rasterio.crs import CRS
from rasterio.errors import CRSError, RasterioIOError

EXTENSIONES = (".tif", ".tiff")
RE_EPSG = re.compile(r"^EPSG:(\d{4,6})$")
# El selector del editor (Colombia). "EPSG:9377" primero: es el oficial (Resolución IGAC 471/2020).
SISTEMAS_COMUNES = (
    ("EPSG:9377", "MAGNA-SIRGAS 2018 / Origen-Nacional (CTM12)"),
    ("EPSG:3116", "MAGNA-SIRGAS / Colombia Bogotá zone"),
    ("EPSG:3115", "MAGNA-SIRGAS / Colombia West zone"),
    ("EPSG:3117", "MAGNA-SIRGAS / Colombia East Central zone"),
    ("EPSG:3118", "MAGNA-SIRGAS / Colombia East zone"),
    ("EPSG:3114", "MAGNA-SIRGAS / Colombia Far West zone"),
)
LADO_SIN_PIRAMIDES_PX = 8000  # desde aquí, sin pirámides, la vista previa se vuelve lenta
TIPOS_8_BITS = ("uint8",)


class OrtofotoInvalida(ValueError):
    """El archivo no es una ortofoto que se pueda usar (mensaje en español)."""


class SistemaInvalido(ValueError):
    """El sistema de coordenadas escrito no es un EPSG proyectado conocido."""


def validar_ruta(ruta: Path | str) -> Path:
    """Ruta absoluta de un .tif/.tiff que existe; OrtofotoInvalida si no."""
    ruta = Path(ruta).resolve()
    if ruta.suffix.lower() not in EXTENSIONES:
        raise OrtofotoInvalida(f"«{ruta.name}» no es un GeoTIFF (.tif o .tiff).")
    if not ruta.is_file():
        raise OrtofotoInvalida(f"No existe el archivo «{ruta}».")
    return ruta


def leer_sistema(texto) -> CRS:
    """"EPSG:9377" → CRS. Solo sistemas PROYECTADOS (en metros): las cajas de los detalles van
    en las coordenadas del dibujo. SistemaInvalido si no."""
    m = RE_EPSG.match(texto.strip().upper()) if isinstance(texto, str) else None
    if m is None:
        raise SistemaInvalido(f"Sistema de coordenadas no válido: {texto!r} (se espera "
                              f"«EPSG:<código>», p. ej. EPSG:9377).")
    try:
        crs = CRS.from_epsg(int(m.group(1)))
    except CRSError:
        raise SistemaInvalido(f"GDAL no conoce el sistema {texto}.") from None
    if not crs.is_projected:
        raise SistemaInvalido(f"{texto} no es un sistema proyectado (en metros): el dibujo "
                              f"necesita uno proyectado, p. ej. EPSG:9377.")
    return crs


def texto_sistema(crs: CRS | None) -> dict | None:
    """{codigo: "EPSG:9377" | None, nombre} para la ficha (None sin sistema)."""
    if crs is None:
        return None
    epsg = crs.to_epsg()
    return {"codigo": f"EPSG:{epsg}" if epsg else None, "nombre": _nombre_crs(crs)}


def _nombre_crs(crs: CRS) -> str:
    try:
        nombre = crs.to_wkt().split('"')[1]
    except IndexError:
        nombre = crs.to_string()
    return nombre


def firma(ruta: Path) -> tuple[int, int]:
    """(bytes, fecha de modificación en ns): si cambia, la ortofoto cambió en el disco."""
    estado = Path(ruta).stat()
    return estado.st_size, estado.st_mtime_ns


def _es_bigtiff(ruta: Path) -> bool:
    with open(ruta, "rb") as f:
        cabecera = f.read(4)
    return cabecera in (b"II+\x00", b"MM\x00+")


def leer_cabecera(ruta: Path | str) -> dict:
    """La ficha de la ortofoto (solo cabecera, sin leer píxeles). OrtofotoInvalida si GDAL no
    la abre o si no tiene georreferencia (sin ella no se sabe dónde va)."""
    ruta = validar_ruta(ruta)
    try:
        with rasterio.open(ruta) as d:
            ficha = _ficha(d, ruta)
    except RasterioIOError as e:
        raise OrtofotoInvalida(f"No se pudo leer «{ruta.name}» como GeoTIFF: {e}") from None
    return ficha


def _ficha(d, ruta: Path) -> dict:
    t = d.transform
    if d.driver != "GTiff":
        raise OrtofotoInvalida(f"«{ruta.name}» no es un GeoTIFF (GDAL lo lee como {d.driver}).")
    if t.is_identity:
        raise OrtofotoInvalida(f"«{ruta.name}» no tiene georreferencia (ni coordenadas ni "
                               f"tamaño de píxel): no se sabe dónde va. Use un GeoTIFF "
                               f"georreferenciado (o con su archivo .tfw al lado).")
    bytes_, mtime = firma(ruta)
    girada = not (t.b == 0 and t.d == 0)
    res_x = math.hypot(t.a, t.d)
    res_y = math.hypot(t.b, t.e)
    piramides = d.overviews(1)
    bloque = d.block_shapes[0] if d.block_shapes else (1, d.width)
    mosaicos = bloque[0] > 1 and bloque[1] < d.width
    tipo = d.dtypes[0]
    bandas = d.count
    interpretacion = [c.name for c in d.colorinterp]
    con_alfa = "alpha" in interpretacion
    paleta = bandas == 1 and interpretacion[0] == "palette"
    crs = d.crs if d.crs else None
    sistema = texto_sistema(crs)
    avisos = []
    if crs is None:
        avisos.append({"nivel": "elegir", "texto":
                       "La ortofoto no dice su sistema de coordenadas: elíjalo abajo (no se supone "
                       "ninguno)."})
    elif not crs.is_projected:
        avisos.append({"nivel": "aviso", "texto":
                       f"Está en coordenadas geográficas ({sistema['nombre']}): se reproyecta al "
                       f"sistema del dibujo."})
    elif sistema["codigo"] is None:
        avisos.append({"nivel": "aviso", "texto":
                       f"Su sistema ({sistema['nombre']}) no tiene código EPSG: se usa tal como "
                       f"viene en el archivo."})
    if girada:
        avisos.append({"nivel": "aviso", "texto":
                       "Está girada (geotransformación con giro): se endereza al leerla."})
    lado = max(d.width, d.height)
    if not piramides and lado >= LADO_SIN_PIRAMIDES_PX:
        avisos.append({"nivel": "aviso", "texto":
                       f"No tiene pirámides ({d.width} × {d.height} px): las vistas previas serán "
                       f"lentas. Se pueden crear con «gdaladdo -r average archivo.tif»."})
    if not mosaicos and lado >= LADO_SIN_PIRAMIDES_PX:
        avisos.append({"nivel": "aviso", "texto":
                       "Está guardada por franjas, no por mosaicos: leer una zona pequeña obliga a "
                       "leer filas enteras (más lento)."})
    if bandas == 2 or bandas > 4:
        avisos.append({"nivel": "aviso", "texto":
                       f"Tiene {bandas} bandas: se usan las tres primeras como rojo, verde y azul."})
    if tipo not in TIPOS_8_BITS:
        avisos.append({"nivel": "aviso", "texto":
                       f"Sus valores son {tipo}, no de 8 bits: se ajusta el brillo (2–98 %) para "
                       f"verla."})
    return {
        "nombre": ruta.name,
        "bytes": bytes_,
        "modificado": datetime.fromtimestamp(mtime / 1e9, UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "px": [d.width, d.height],
        "bandas": bandas,
        "tipo": tipo,
        "color": ("paleta" if paleta else "gris" if bandas == 1 else
                  "RGBA" if bandas == 4 and con_alfa else "RGB" if bandas >= 3 else "gris"),
        "sistema": sistema,
        "resolucion": [res_x, res_y],
        "limites": list(d.bounds),  # (izq, abajo, der, arriba) en su sistema
        "girada": girada,
        "piramides": list(piramides),
        "compresion": d.compression.name if d.compression else None,
        "mosaicos": mosaicos,
        "bloque_px": list(bloque),
        "bigtiff": _es_bigtiff(ruta),
        "fondo": ("alfa" if con_alfa else "nodata" if d.nodata is not None else
                  "mascara" if any(f.name == "per_dataset" for f in d.mask_flag_enums[0]) else None),
        "nodata": d.nodata,
        "avisos": avisos,
    }
