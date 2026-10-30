import pymupdf
import pytest

from componedor.transformaciones import (
    punto_pagina_a_papel,
    punto_papel_a_pagina,
    rect_papel_a_pdf,
    rect_pdf_a_papel,
)
from componedor.unidades import mm_a_pt

ANCHO, ALTO = 841.0, 594.0
LADO = 10.0  # cuadrado de 10 x 10 mm en cada esquina


@pytest.mark.parametrize(
    "esquina, rect_mm, esperado_pt",
    [
        # Inferior izquierda del papel -> abajo en PyMuPDF (Y grande).
        ("inferior_izquierda", (0, 0, LADO, LADO),
         (0, ALTO - LADO, LADO, ALTO)),
        ("inferior_derecha", (ANCHO - LADO, 0, ANCHO, LADO),
         (ANCHO - LADO, ALTO - LADO, ANCHO, ALTO)),
        # Superior izquierda del papel -> arriba en PyMuPDF (Y = 0).
        ("superior_izquierda", (0, ALTO - LADO, LADO, ALTO),
         (0, 0, LADO, LADO)),
        ("superior_derecha", (ANCHO - LADO, ALTO - LADO, ANCHO, ALTO),
         (ANCHO - LADO, 0, ANCHO, LADO)),
    ],
)
def test_esquinas_de_la_hoja(esquina, rect_mm, esperado_pt):
    rect = rect_papel_a_pdf(rect_mm, ALTO)
    esperado = pymupdf.Rect(*(mm_a_pt(v) for v in esperado_pt))
    for obtenido, valor in zip(rect, esperado):
        assert obtenido == pytest.approx(valor), esquina


def test_ida_y_vuelta():
    rect_mm = (12.7, 12.7, 828.3, 581.3)
    vuelta = rect_pdf_a_papel(rect_papel_a_pdf(rect_mm, ALTO), ALTO)
    assert vuelta == pytest.approx(rect_mm)


def test_punto_pagina_a_papel_y_vuelta():
    # Página de 120 mm de alto: el punto (10, 20) desde arriba está a 100 mm del borde inferior.
    assert punto_pagina_a_papel(10.0, 20.0, 120.0) == (10.0, 100.0)
    # Con la página colocada en (300, 50) de la hoja.
    assert punto_pagina_a_papel(10.0, 20.0, 120.0, (300.0, 50.0)) == (310.0, 150.0)
    assert punto_papel_a_pagina(310.0, 150.0, 120.0, (300.0, 50.0)) == (10.0, 20.0)
    # Esquinas de la página.
    assert punto_pagina_a_papel(0.0, 0.0, 120.0) == (0.0, 120.0)  # arriba-izquierda
    assert punto_pagina_a_papel(0.0, 120.0, 120.0) == (0.0, 0.0)  # abajo-izquierda
