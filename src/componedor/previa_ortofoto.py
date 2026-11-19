"""Vista previa de la ortofoto dentro de la caja de un detalle (PNG con transparencia).

La caja llega en coordenadas del DIBUJO (unidades CAD, p. ej. m) y en su sistema de coordenadas
(`crs_dibujo`). Se pasa a metros (`mm_por_unidad` ÷ 1000), se elige el tamaño de la imagen (lado
largo `lado_px`) y se pinta con `ortofoto_render.pintar`: solo la ventana necesaria, reducida y
reproyectada. Transparente donde no hay foto.

Es solo para el editor; el PDF lo arma `ortofoto_pdf`.
"""

import math
from dataclasses import dataclass

import numpy as np
import pymupdf
from rasterio.crs import CRS

from componedor.ortofoto import validar_ruta
from componedor.ortofoto_render import abrir_fuente, pintar

LADO_PX = 1500
MAX_LADO_PX = 4000


@dataclass(frozen=True)
class PreviaOrtofoto:
    png: bytes
    px: tuple[int, int]
    cobertura: float  # fracción de la caja con foto (0 a 1)


def tamano_px(caja: tuple[float, float, float, float], lado_px: int) -> tuple[int, int]:
    """(ancho, alto) en píxeles con la proporción de la caja y el lado largo = lado_px."""
    ancho, alto = caja[2] - caja[0], caja[3] - caja[1]
    if ancho >= alto:
        return lado_px, max(1, round(lado_px * alto / ancho))
    return max(1, round(lado_px * ancho / alto)), lado_px


def validar_caja(caja) -> tuple[float, float, float, float]:
    """[x0, y0, x1, y1] con 4 números finitos y x1 > x0, y1 > y0; ValueError si no."""
    if (not isinstance(caja, (list, tuple)) or len(caja) != 4
            or not all(isinstance(v, (int, float)) and not isinstance(v, bool)
                       and math.isfinite(v) for v in caja)):
        raise ValueError("la caja debe ser [x0, y0, x1, y1] con 4 números")
    x0, y0, x1, y1 = (float(v) for v in caja)
    if not (x1 > x0 and y1 > y0):
        raise ValueError("la caja está vacía (x1 ≤ x0 o y1 ≤ y0)")
    return x0, y0, x1, y1


def png_rgba(rgb: np.ndarray, alfa: np.ndarray) -> bytes:
    """rgb (3, alto, ancho) uint8 y alfa (alto, ancho) uint8 → PNG."""
    alto, ancho = alfa.shape
    muestras = np.dstack([rgb[0], rgb[1], rgb[2], alfa]).astype(np.uint8)
    return pymupdf.Pixmap(pymupdf.csRGB, ancho, alto, muestras.tobytes(), True).tobytes("png")


def hacer_previa(ruta, caja_cad, crs_dibujo: CRS, crs_ortofoto: CRS | None = None,
                 mm_por_unidad: float = 1000.0, lado_px: int = LADO_PX) -> PreviaOrtofoto:
    """El PNG de la ortofoto en la caja (coordenadas del dibujo, en `crs_dibujo`).

    crs_ortofoto: el sistema elegido por el usuario; solo se usa si el archivo no trae el suyo.
    OrtofotoInvalida si no se sabe el sistema de la ortofoto; ValueError si la caja no sirve.
    """
    ruta = validar_ruta(ruta)
    caja = validar_caja(caja_cad)
    if not (isinstance(mm_por_unidad, (int, float)) and mm_por_unidad > 0):
        raise ValueError("mm_por_unidad debe ser un número > 0")
    if not (isinstance(lado_px, int) and 16 <= lado_px <= MAX_LADO_PX):
        raise ValueError(f"lado_px debe ser un entero de 16 a {MAX_LADO_PX}")
    k = mm_por_unidad / 1000.0  # unidades CAD → m (los sistemas proyectados van en m)
    caja_m = (caja[0] * k, caja[1] * k, caja[2] * k, caja[3] * k)
    ancho, alto = tamano_px(caja_m, lado_px)
    with abrir_fuente(ruta, crs_ortofoto) as fuente:
        rgb, alfa = pintar(fuente, caja_m, ancho, alto, crs_dibujo)
    cobertura = float((alfa > 0).mean())
    return PreviaOrtofoto(png_rgba(rgb, alfa), (ancho, alto), cobertura)
