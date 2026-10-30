import pytest

from componedor.hoja import crear_hoja, tamano_hoja_mm
from componedor.unidades import pt_a_mm

TOL_MM = 0.1


@pytest.mark.parametrize(
    "orientacion, ancho, alto",
    [("horizontal", 841.0, 594.0), ("vertical", 594.0, 841.0)],
)
def test_tamano_pagina(orientacion, ancho, alto):
    doc = crear_hoja(orientacion)
    rect = doc[0].rect
    assert abs(pt_a_mm(rect.width) - ancho) <= TOL_MM
    assert abs(pt_a_mm(rect.height) - alto) <= TOL_MM


@pytest.mark.parametrize("orientacion", ["horizontal", "vertical"])
def test_una_pagina_sin_rotacion(orientacion):
    doc = crear_hoja(orientacion)
    assert doc.page_count == 1
    assert doc[0].rotation == 0


def test_orientacion_invalida():
    with pytest.raises(ValueError, match="Orientación no válida: 'diagonal'"):
        tamano_hoja_mm("diagonal")
    with pytest.raises(ValueError, match="Use 'horizontal'"):
        crear_hoja("diagonal")
