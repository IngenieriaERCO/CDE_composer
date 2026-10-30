"""Comprobaciones entre la geometría del manifiesto y el PDF del detalle.

- `exigir_coherencia`: el PDF debe ser el del manifiesto (mismo tamaño de página, sin
  /Rotate). Si no, la matriz cad_to_page no aplica y el ancla quedaría mal: es error.
- `comparar_con_manifiesto`: compara los límites reales de los trazos con page_bounds_mm.
  Es solo informativa: una diferencia mayor que 0,5 mm se reporta como advertencia.
"""

from dataclasses import dataclass

import pymupdf

from componedor.cad_a_papel import GeometriaManifiesto, ManifiestoInvalido
from componedor.formato import RectMM
from componedor.unidades import pt_a_mm

TOLERANCIA_TAMANO_MM = 0.5
UMBRAL_ADVERTENCIA_MM = 0.5


@dataclass(frozen=True)
class ComparacionLimites:
    limites_trazos_mm: RectMM  # medidos en el PDF: mm de página, Y abajo
    limites_manifiesto_mm: RectMM  # page_bounds_mm
    diferencia_max_mm: float

    @property
    def advertencia(self) -> bool:
        return self.diferencia_max_mm > UMBRAL_ADVERTENCIA_MM


def exigir_coherencia(pagina: pymupdf.Page, geometria: GeometriaManifiesto) -> None:
    """Lanza `ManifiestoInvalido` si el PDF no corresponde a la geometría del manifiesto."""
    if pagina.rotation != 0:
        raise ManifiestoInvalido(
            f"El detalle tiene /Rotate {pagina.rotation}: la matriz cad_to_page del manifiesto "
            f"se refiere a la página sin girar y ese caso no está soportado."
        )
    ancho, alto = pt_a_mm(pagina.rect.width), pt_a_mm(pagina.rect.height)
    dif = (ancho - geometria.ancho_pagina_mm, alto - geometria.alto_pagina_mm)
    if any(abs(d) > TOLERANCIA_TAMANO_MM for d in dif):
        raise ManifiestoInvalido(
            f"El manifiesto no corresponde al PDF del detalle: page_size_mm es "
            f"{geometria.ancho_pagina_mm:.2f} x {geometria.alto_pagina_mm:.2f} mm y el PDF mide "
            f"{ancho:.2f} x {alto:.2f} mm (diferencia {dif[0]:+.2f} x {dif[1]:+.2f} mm)."
        )


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


def comparar_con_manifiesto(pagina: pymupdf.Page,
                            geometria: GeometriaManifiesto) -> ComparacionLimites | None:
    """Compara los límites de los trazos con page_bounds_mm. None si no hay trazos."""
    medidos = medir_limites_trazos(pagina)
    if medidos is None:
        return None
    diferencia = max(abs(a - b) for a, b in zip(medidos, geometria.limites_pagina_mm))
    return ComparacionLimites(medidos, geometria.limites_pagina_mm, diferencia)
