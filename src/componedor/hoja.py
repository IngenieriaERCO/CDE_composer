"""Creación de la hoja (página PDF) en su orientación real, sin /Rotate."""

import pymupdf

from componedor.unidades import mm_a_pt

# A1 en horizontal: ancho x alto en mm.
A1_MM = (841.0, 594.0)

ORIENTACIONES = ("horizontal", "vertical")


def tamano_hoja_mm(orientacion: str) -> tuple[float, float]:
    """Devuelve (ancho, alto) en mm de la hoja A1 según la orientación."""
    if orientacion not in ORIENTACIONES:
        raise ValueError(
            f"Orientación no válida: '{orientacion}'. "
            f"Use 'horizontal' (841 x 594 mm) o 'vertical' (594 x 841 mm)."
        )
    ancho, alto = A1_MM
    if orientacion == "vertical":
        ancho, alto = alto, ancho
    return ancho, alto


def crear_pagina(ancho_mm: float, alto_mm: float) -> pymupdf.Document:
    """Crea un documento PDF con una sola página vacía del tamaño dado, rotación 0."""
    doc = pymupdf.open()
    doc.new_page(width=mm_a_pt(ancho_mm), height=mm_a_pt(alto_mm))
    return doc


def crear_hoja(orientacion: str = "horizontal") -> pymupdf.Document:
    """Crea un documento PDF con una sola página A1 vacía, rotación 0."""
    return crear_pagina(*tamano_hoja_mm(orientacion))
