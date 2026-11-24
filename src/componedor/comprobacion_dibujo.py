"""Medición de los trazos de un PDF de detalle, sin el fondo blanco del exportador.

La usan la coherencia del paquete (coherencia.py, comprobación h: trazos vs
page_bounds_mm) y la validación con geometría de referencia (validacion.py).
"""

import pymupdf

from componedor.formato import RectMM
from componedor.unidades import mm_a_pt, pt_a_mm


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


def tiene_fondo_de_pagina(pagina: pymupdf.Page) -> bool:
    """True si la página trae el fondo blanco de página completa (paquetes antiguos del
    exportador). Misma regla con la que `medir_limites_trazos` lo ignora."""
    return any(es_fondo_de_pagina(d, pagina) for d in pagina.get_drawings())


def trazos_sin_fondo(pagina: pymupdf.Page, rect_fondo: pymupdf.Rect | None = None) -> list[dict]:
    """Trazos de la página (`get_drawings()`) sin el fondo blanco en `rect_fondo` (pt).

    Por defecto el fondo buscado es el de página completa.
    """
    fondo = pagina.rect if rect_fondo is None else rect_fondo
    return [d for d in pagina.get_drawings() if not es_fondo_blanco(d, fondo)]


def medir_limites_trazos(pagina: pymupdf.Page, mascara_mm: RectMM | None = None) -> RectMM | None:
    """Límites de los trazos de la página (mm de página, origen arriba-izq., Y abajo).

    Ignora el fondo blanco de página completa (ver `es_fondo_blanco`). No incluye texto
    ni el grosor de línea. Devuelve None si no hay trazos.

    `mascara_mm`: la zona de la máscara de recorte del manifiesto 1.5
    (`pdf.drawing.mask.zone_page_mm`, mm, Y abajo). `get_drawings()` no aplica la máscara,
    así que cada trazo se recorta a esa zona antes de medir (ver `recortar_a_zona`).
    """
    trazos = trazos_sin_fondo(pagina)
    if mascara_mm is not None:
        trazos = recortar_a_zona(trazos, mascara_mm)
    return limites_de_trazos(trazos)


def recortar_a_zona(trazos: list[dict], zona_mm: RectMM) -> list[dict]:
    """Los trazos con su `rect` recortado a `zona_mm` (mm de página, Y abajo).

    Como pide docs/manifiesto.md del exportador («Cómo medir los trazos con máscara»): el
    recorte es a mano (máximos y mínimos), no con `Rect.intersect` ni `&` de PyMuPDF, que
    tratan como vacío el `rect` de alto o ancho cero de un segmento horizontal o vertical.
    Se descartan los trazos que quedan enteros fuera (x0 > x1 o y0 > y1); el que solo toca
    el borde se queda. Devuelve copias: no cambia los trazos recibidos.
    """
    zx0, zy0, zx1, zy1 = (mm_a_pt(v) for v in zona_mm)
    recortados = []
    for trazo in trazos:
        r = trazo["rect"]
        x0, y0 = max(r.x0, zx0), max(r.y0, zy0)
        x1, y1 = min(r.x1, zx1), min(r.y1, zy1)
        if x0 > x1 or y0 > y1:
            continue
        recortados.append({**trazo, "rect": pymupdf.Rect(x0, y0, x1, y1)})
    return recortados


def limites_de_trazos(trazos: list[dict]) -> RectMM | None:
    """Límites (mm, Y abajo, como los da PyMuPDF) de una lista de trazos de `get_drawings()`.

    No quita el fondo blanco: eso lo decide quien arma la lista. None si está vacía.
    """
    rects = [d["rect"] for d in trazos]
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
