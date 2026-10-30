"""Dibujo vectorial del marco y de las guías de zonas sobre una página."""

import pymupdf

from componedor.formato import Formato
from componedor.transformaciones import rect_papel_a_pdf
from componedor.unidades import mm_a_pt

NEGRO = (0, 0, 0)
GRIS_GUIAS = (0.5, 0.5, 0.5)
TAMANO_ETIQUETA_PT = 6
SEPARACION_ETIQUETA_MM = 1.5
# Patrón de guión de las guías: 2 mm de trazo, 1 mm de espacio.
GUION_MM = (2.0, 1.0)


def dibujar_marco(page: pymupdf.Page, formato: Formato) -> None:
    """Dibuja el marco del formato con su grosor de línea."""
    rect = rect_papel_a_pdf(formato.marco, formato.alto_mm)
    page.draw_rect(rect, color=NEGRO, width=mm_a_pt(formato.grosores_mm["marco"]))


def dibujar_guias(page: pymupdf.Page, formato: Formato) -> None:
    """Dibuja cada zona como línea fina discontinua con su nombre en letra pequeña."""
    trazo, espacio = (mm_a_pt(v) for v in GUION_MM)
    guiones = f"[{trazo:.3f} {espacio:.3f}] 0"
    grosor = mm_a_pt(formato.grosores_mm["guias"])
    separacion = mm_a_pt(SEPARACION_ETIQUETA_MM)

    for nombre, rect_mm in formato.zonas.items():
        rect = rect_papel_a_pdf(rect_mm, formato.alto_mm)
        page.draw_rect(rect, color=GRIS_GUIAS, width=grosor, dashes=guiones)
        # Etiqueta en la esquina superior izquierda, por dentro de la zona.
        punto = pymupdf.Point(rect.x0 + separacion, rect.y0 + separacion + TAMANO_ETIQUETA_PT)
        page.insert_text(punto, nombre, fontsize=TAMANO_ETIQUETA_PT, fontname="helv",
                         color=GRIS_GUIAS)
