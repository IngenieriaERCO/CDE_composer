"""Paso entre el sistema de papel y el de PyMuPDF.

- Papel: mm, origen en la esquina inferior izquierda, Y hacia arriba (como el Layout de AutoCAD).
- PyMuPDF: pt, origen en la esquina superior izquierda, Y hacia abajo.

Este es el ÚNICO módulo donde se invierte el eje Y.
"""

import pymupdf

from componedor.unidades import mm_a_pt, pt_a_mm

RectMM = tuple[float, float, float, float]  # (xmin, ymin, xmax, ymax) en mm
PuntoMM = tuple[float, float]


def punto_pagina_a_papel(x_mm: float, y_mm: float, alto_pagina_mm: float,
                         origen_mm: PuntoMM = (0.0, 0.0)) -> PuntoMM:
    """Punto de la página de un detalle (mm, origen arriba-izquierda, Y abajo) a papel.

    `origen_mm` es dónde quedó en la hoja la esquina inferior izquierda de esa página
    (mm de papel, Y arriba). Con (0, 0) da coordenadas relativas a la propia página.
    """
    return origen_mm[0] + x_mm, origen_mm[1] + alto_pagina_mm - y_mm


def punto_papel_a_pagina(x_mm: float, y_mm: float, alto_pagina_mm: float,
                         origen_mm: PuntoMM = (0.0, 0.0)) -> PuntoMM:
    """Operación inversa de `punto_pagina_a_papel`."""
    return x_mm - origen_mm[0], alto_pagina_mm - (y_mm - origen_mm[1])


def punto_papel_a_pdf(x_mm: float, y_mm: float, alto_hoja_mm: float) -> pymupdf.Point:
    """Punto de papel (mm, Y arriba) a un Point de PyMuPDF (pt, Y abajo) en la hoja."""
    return pymupdf.Point(mm_a_pt(x_mm), mm_a_pt(alto_hoja_mm - y_mm))


def rect_papel_a_pdf(rect_mm: RectMM, alto_hoja_mm: float) -> pymupdf.Rect:
    """Convierte un rectángulo de papel (mm, Y arriba) a un Rect de PyMuPDF (pt, Y abajo)."""
    xmin, ymin, xmax, ymax = rect_mm
    return pymupdf.Rect(
        mm_a_pt(xmin),
        mm_a_pt(alto_hoja_mm - ymax),
        mm_a_pt(xmax),
        mm_a_pt(alto_hoja_mm - ymin),
    )


def rect_pdf_a_papel(rect: pymupdf.Rect, alto_hoja_mm: float) -> RectMM:
    """Operación inversa: Rect de PyMuPDF (pt, Y abajo) a rectángulo de papel (mm, Y arriba)."""
    return (
        pt_a_mm(rect.x0),
        alto_hoja_mm - pt_a_mm(rect.y1),
        pt_a_mm(rect.x1),
        alto_hoja_mm - pt_a_mm(rect.y0),
    )
