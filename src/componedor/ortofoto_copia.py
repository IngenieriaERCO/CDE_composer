"""Copia reducida de la ortofoto, en la carpeta del plano: `<plano>_ortofoto/`.

Para componer el plano otra vez sin la ortofoto original (que puede pesar varios GB o estar en
otro disco). La escribe `componer` cada vez que compone CON el original; si después el original
no está o cambió, `componer` usa la copia y lo avisa.

Un GeoTIFF por detalle, ya en el sistema del DIBUJO:

- cubre la página del detalle más un margen (`MARGEN`, 10 % por lado: aguanta mover el detalle
  o cambiarle algo la escala);
- con la resolución que pide el PDF (`ppp` a la escala del detalle), pero nunca más fina que la
  ortofoto original (agrandarla no agrega nada: el PDF la agranda al componer);
- JPEG (calidad `calidad_jpeg`) en mosaicos de 512 px, con máscara interna donde no hay foto;
  se escribe por mosaicos (la memoria no depende del tamaño).

`indice.json` dice de qué ortofoto salió (nombre, bytes, fecha), en qué sistema está y qué caja
cubre cada archivo. Si la copia ya está al día (mismo original, mismas cajas y resoluciones), no
se vuelve a escribir. Si cambió, la nueva se escribe aparte y recién entonces reemplaza a la
vieja (que es un archivo generado, como el PDF: se borra).
"""

import json
import math
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import rasterio
from rasterio.crs import CRS
from rasterio.windows import Window

from componedor.ortofoto_pdf import (
    DetalleOrtofoto,
    caja_cad,
    cuadricula,
    en_metros,
)
from componedor.ortofoto_render import Fuente, destino, pintar

MARGEN = 0.10
LADO_ESCRITURA_PX = 1024
VERSION = 1
INDICE = "indice.json"


@dataclass(frozen=True)
class InformeCopia:
    carpeta: Path
    escrita: bool  # False: ya estaba al día
    archivos: int
    bytes: int


def carpeta_copia(ruta_plano: Path) -> Path:
    ruta_plano = Path(ruta_plano)
    return ruta_plano.parent / f"{ruta_plano.stem}_ortofoto"


def leer_indice(carpeta: Path) -> dict | None:
    """El índice de la copia, o None si no hay copia (o está rota)."""
    try:
        datos = json.loads((Path(carpeta) / INDICE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(datos, dict) or datos.get("version") != VERSION:
        return None
    return datos


def _nombre(i: int, ident: str) -> str:
    return f"{i:02d}_{re.sub(r'[^A-Za-z0-9._-]+', '_', ident)[:60]}.tif"


def plan_de_copia(detalles: list[DetalleOrtofoto], fuente: Fuente, crs_dibujo: CRS,
                  ppp: int) -> list[dict]:
    """Qué se escribirá por detalle: {id, archivo, caja_m, px}."""
    plan = []
    for i, det in enumerate(detalles, start=1):
        caja = caja_cad(det.recorte, det.ocupado, det.matriz)
        if caja is None:
            continue
        caja_m = en_metros(caja, det.mm_por_unidad)
        (ancho_pdf, _), _ = cuadricula(det.recorte, ppp)
        res_pdf = (caja_m[2] - caja_m[0]) / ancho_pdf
        mx, my = (caja_m[2] - caja_m[0]) * MARGEN, (caja_m[3] - caja_m[1]) * MARGEN
        ampliada = (caja_m[0] - mx, caja_m[1] - my, caja_m[2] + mx, caja_m[3] + my)
        res = max(res_pdf, fuente.resolucion_en_dibujo(ampliada, crs_dibujo))
        px = (max(1, math.ceil((ampliada[2] - ampliada[0]) / res)),
              max(1, math.ceil((ampliada[3] - ampliada[1]) / res)))
        plan.append({"id": det.id, "archivo": _nombre(i, det.id),
                     "caja_m": [round(v, 4) for v in ampliada], "px": list(px)})
    return plan


def escribir_copia(carpeta: Path, original: dict, detalles: list[DetalleOrtofoto],
                   fuente: Fuente, crs_dibujo: CRS, ppp: int, calidad: int) -> InformeCopia:
    """Escribe (o deja, si está al día) la copia. original: {nombre, bytes, modificado}."""
    carpeta = Path(carpeta)
    plan = plan_de_copia(detalles, fuente, crs_dibujo, ppp)
    indice = {"version": VERSION, "original": original, "crs_dibujo": crs_dibujo.to_string(),
              "ppp": ppp, "calidad_jpeg": calidad, "detalles": plan}
    if leer_indice(carpeta) == indice and all((carpeta / p["archivo"]).is_file() for p in plan):
        return InformeCopia(carpeta, False, len(plan), _peso(carpeta))
    nueva = carpeta.with_name(carpeta.name + ".nueva")
    if nueva.exists():
        shutil.rmtree(nueva)
    nueva.mkdir(parents=True)
    try:
        for p in plan:
            _escribir_tif(nueva / p["archivo"], fuente, p["caja_m"], p["px"], crs_dibujo,
                          calidad)
        (nueva / INDICE).write_text(json.dumps(indice, ensure_ascii=False, indent=2) + "\n",
                                    encoding="utf-8")
        if carpeta.exists():
            vieja = carpeta.with_name(carpeta.name + ".vieja")
            if vieja.exists():
                shutil.rmtree(vieja)
            carpeta.rename(vieja)
            nueva.rename(carpeta)
            shutil.rmtree(vieja, ignore_errors=True)
        else:
            nueva.rename(carpeta)
    finally:
        if nueva.exists():
            shutil.rmtree(nueva, ignore_errors=True)
    return InformeCopia(carpeta, True, len(plan), _peso(carpeta))


def _escribir_tif(ruta: Path, fuente: Fuente, caja_m, px, crs_dibujo: CRS, calidad: int) -> None:
    ancho, alto = px
    factor = fuente.factor(caja_m, ancho, alto, crs_dibujo)
    perfil = {"driver": "GTiff", "width": ancho, "height": alto, "count": 3, "dtype": "uint8",
              "crs": crs_dibujo, "transform": destino(caja_m, ancho, alto), "tiled": True,
              "blockxsize": 512, "blockysize": 512, "compress": "JPEG",
              "jpeg_quality": calidad, "photometric": "YCBCR", "BIGTIFF": "IF_SAFER"}
    with rasterio.Env(GDAL_TIFF_INTERNAL_MASK=True), rasterio.open(ruta, "w", **perfil) as d:
        for f0 in range(0, alto, LADO_ESCRITURA_PX):
            f1 = min(alto, f0 + LADO_ESCRITURA_PX)
            for c0 in range(0, ancho, LADO_ESCRITURA_PX):
                c1 = min(ancho, c0 + LADO_ESCRITURA_PX)
                rx = (caja_m[2] - caja_m[0]) / ancho
                ry = (caja_m[3] - caja_m[1]) / alto
                sub = (caja_m[0] + c0 * rx, caja_m[3] - f1 * ry,
                       caja_m[0] + c1 * rx, caja_m[3] - f0 * ry)
                rgb, alfa = pintar(fuente, sub, c1 - c0, f1 - f0, crs_dibujo, factor)
                ventana = Window(c0, f0, c1 - c0, f1 - f0)
                d.write(rgb, window=ventana)
                d.write_mask(alfa, window=ventana)


def _peso(carpeta: Path) -> int:
    return sum(p.stat().st_size for p in Path(carpeta).iterdir() if p.is_file())


def archivo_de(carpeta: Path, indice: dict, ident: str) -> Path | None:
    """El GeoTIFF de la copia para ese detalle, o None si la copia no lo tiene."""
    for p in indice.get("detalles", []):
        if p.get("id") == ident and (Path(carpeta) / p["archivo"]).is_file():
            return Path(carpeta) / p["archivo"]
    return None
