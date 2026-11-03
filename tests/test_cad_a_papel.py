import pytest

from componedor.cad_a_papel import (
    MatrizCad,
    MatrizNoInvertible,
    cad_a_papel,
    limites_dibujo_en_papel,
    origen_para_ancla,
)
from conftest import LIMITES_RECT_PAGINA_MM, MATRIZ_SINTETICA, PAGINA_CAD_MM, X0_CAD, Y0_CAD

M = MatrizCad(*MATRIZ_SINTETICA)
ALTO = PAGINA_CAD_MM[1]


def test_matriz_sintetica_como_la_del_exportador():
    assert (M.a, M.d) == (20.0, -20.0)
    assert 1e7 < abs(M.e) < 1e9 and 1e7 < abs(M.f) < 1e9


@pytest.mark.parametrize("dx, dy", [(0, 0), (1, 2), (11, 6), (5.123456, 3.987654), (-3, 9)])
def test_ida_y_vuelta_cad_pagina_cad(dx, dy):
    x, y = X0_CAD + dx, Y0_CAD + dy
    x2, y2 = M.pagina_a_cad(*M.cad_a_pagina(x, y))
    # Error expresado en mm de papel (1 unidad CAD = 20 mm en la página).
    assert abs(x2 - x) * 20 < 0.001 and abs(y2 - y) * 20 < 0.001


@pytest.mark.parametrize("xp, yp", [(0, 0), (37.3, 98.7), (130.0, 60.0), (260.0, 120.0)])
def test_ida_y_vuelta_pagina_cad_pagina(xp, yp):
    x2, y2 = M.cad_a_pagina(*M.pagina_a_cad(xp, yp))
    assert abs(x2 - xp) < 0.001 and abs(y2 - yp) < 0.001


def test_cad_a_pagina_con_la_matriz():
    # Esquina inferior izquierda del rectángulo CAD -> (37,3; 98,7) mm de página, Y abajo.
    assert M.cad_a_pagina(X0_CAD + 1, Y0_CAD + 2) == pytest.approx((37.3, 98.7), abs=1e-6)


def test_matriz_no_invertible():
    with pytest.raises(MatrizNoInvertible, match=r"no es invertible \(determinante"):
        MatrizCad(2.0, 4.0, 1.0, 2.0, 0.0, 0.0).pagina_a_cad(1.0, 1.0)


def test_cad_a_papel_con_origen():
    # La página del detalle con su esquina inferior izquierda en (100, 50) mm de papel.
    x, y = cad_a_papel(X0_CAD + 1, Y0_CAD + 2, (100.0, 50.0), ALTO, M)
    assert (x, y) == pytest.approx((100 + 37.3, 50 + ALTO - 98.7), abs=1e-6)


@pytest.mark.parametrize("ancla_cad, ancla_papel", [
    ((X0_CAD + 1, Y0_CAD + 2), (150.0, 200.0)),
    ((X0_CAD + 6.25, Y0_CAD + 4.5), (342.55, 297.0)),
])
def test_ancla_cae_exactamente_en_el_punto_pedido(ancla_cad, ancla_papel):
    origen = origen_para_ancla(ancla_cad, ancla_papel, M, ALTO)
    assert cad_a_papel(*ancla_cad, origen, ALTO, M) == pytest.approx(ancla_papel, abs=1e-6)


def test_limites_dibujo_en_papel():
    # page_bounds (37,3; 18,7; 237,3; 98,7) con la página en (100, 100) y alto 120.
    # (La lectura del manifiesto se prueba en test_manifiesto.py.)
    assert limites_dibujo_en_papel(LIMITES_RECT_PAGINA_MM, ALTO, (100.0, 100.0)) ==         pytest.approx((137.3, 121.3, 337.3, 201.3), abs=1e-9)
