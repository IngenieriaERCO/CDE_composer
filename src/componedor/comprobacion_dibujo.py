"""Medición de los trazos de un PDF de detalle, sin el fondo blanco del exportador.

La usan la coherencia del paquete (coherencia.py, comprobación h: trazos vs
page_bounds_mm) y la validación con geometría de referencia (validacion.py).
"""

import pymupdf

from componedor.formato import RectMM
from componedor.unidades import pt_a_mm


def es_fondo_blanco(trazo: dict, rect: pymupdf.Rect, tolerancia_pt: float = 0.05) -> bool:
    """True si el trazo es un relleno blanco sin borde que ocupa exactamente `rect` (pt).

    El exportador pinta un fondo blanco de página completa debajo del dibujo; no es parte
    del dibujo. En la página del detalle `rect` es la página; en la hoja final, el
    rectángulo donde quedó colocada esa página.
    """
    return (
        trazo.get("type") == "f"
        and trazo.get("fill") == (1.0, 1.0, 1.0)
        and all(abs(a - b) < tolerancia_pt for a, b in zip(trazo["rect"], rect))
    )


def es_fondo_de_pagina(trazo: dict, pagina: pymupdf.Page) -> bool:
    """True si el trazo es el fondo blanco que cubre toda la página."""
    return es_fondo_blanco(trazo, pagina.rect)


def trazos_sin_fondo(pagina: pymupdf.Page, rect_fondo: pymupdf.Rect | None = None) -> list[dict]:
    """Trazos de la página (`get_drawings()`) sin el fondo blanco en `rect_fondo` (pt).

    Por defecto el fondo buscado es el de página completa.
    """
    fondo = pagina.rect if rect_fondo is None else rect_fondo
    return [d for d in pagina.get_drawings() if not es_fondo_blanco(d, fondo)]


def medir_limites_trazos(pagina: pymupdf.Page) -> RectMM | None:
    """Límites de los trazos de la página (mm de página, origen arriba-izq., Y abajo).

    Ignora el fondo blanco de página completa (ver `es_fondo_blanco`). No incluye texto
    ni el grosor de línea. Devuelve None si no hay trazos.
    """
    rects = [d["rect"] for d in trazos_sin_fondo(pagina)]
    if not rects:
        return None
    # Mínimos y máximos a mano: un segmento vertical u horizontal es un Rect "vacío" y
    # la unión de PyMuPDF lo ignoraría.
    return (
        pt_a_mm(min(r.x0 for r in rects)),
        pt_a_mm(min(r.y0 for r in rects)),
        pt_a_mm(max(r.x1 for r in rects)),
        pt_a_mm(max(r.y1 for r in rects)),
    )
