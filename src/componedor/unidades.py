"""Conversión entre milímetros (papel) y puntos PDF.

1 pulgada = 25,4 mm = 72 pt  ->  1 mm = 72 / 25,4 pt.
"""

PT_POR_MM = 72 / 25.4


def mm_a_pt(mm: float) -> float:
    """Convierte milímetros a puntos PDF."""
    return mm * PT_POR_MM


def pt_a_mm(pt: float) -> float:
    """Convierte puntos PDF a milímetros."""
    return pt / PT_POR_MM
