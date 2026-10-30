import pytest

from componedor.cad_a_papel import (
    ManifiestoInvalido,
    MatrizCad,
    MatrizNoInvertible,
    cad_a_papel,
    leer_geometria_manifiesto,
    limites_dibujo_en_papel,
    origen_para_ancla,
)
from conftest import (
    LIMITES_RECT_PAGINA_MM,
    MATRIZ_SINTETICA,
    PAGINA_CAD_MM,
    X0_CAD,
    Y0_CAD,
    escribir_json,
    manifiesto_sintetico,
)

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


def test_limites_dibujo_en_papel(tmp_path):
    geometria = leer_geometria_manifiesto(escribir_json(tmp_path / "m.json",
                                                        manifiesto_sintetico()))
    assert geometria.limites_pagina_mm == LIMITES_RECT_PAGINA_MM
    # page_bounds (37,3; 18,7; 237,3; 98,7) con la página en (100, 100) y alto 120.
    assert limites_dibujo_en_papel(geometria, (100.0, 100.0)) == pytest.approx(
        (137.3, 121.3, 337.3, 201.3), abs=1e-9)


def _quitar(camino):
    def cambio(datos):
        *ruta, ultimo = camino.split(".")
        nodo = datos
        for parte in ruta:
            nodo = nodo[parte]
        del nodo[ultimo]
    return cambio


@pytest.mark.parametrize("cambio, mensaje", [
    (_quitar("pdf.page_size_mm"), r"Falta el campo 'pdf\.page_size_mm'"),
    (_quitar("pdf.drawing.page_bounds_mm"), r"Falta el campo 'pdf\.drawing\.page_bounds_mm'"),
    (_quitar("pdf.drawing.cad_to_page.matrix"), r"Falta el campo 'pdf\.drawing\.cad_to_page\.matrix'"),
    (_quitar("pdf.drawing.cad_to_page.units"), r"Falta el campo 'pdf\.drawing\.cad_to_page\.units'"),
    (lambda d: d["pdf"]["drawing"]["cad_to_page"].update(units="m"),
     r"'pdf\.drawing\.cad_to_page\.units' debe ser 'mm'; tiene 'm'"),
    (lambda d: d["pdf"]["drawing"]["cad_to_page"].update(origin="bottom-left"),
     r"'pdf\.drawing\.cad_to_page\.origin' debe ser 'top-left'"),
    (lambda d: d["pdf"]["drawing"]["cad_to_page"].update(y_axis="up"),
     r"'pdf\.drawing\.cad_to_page\.y_axis' debe ser 'down'"),
    (lambda d: d["pdf"]["drawing"]["cad_to_page"].update(matrix=[20, 0, 0, -20, 1e8]),
     r"debe tener 6 números \[a, b, c, d, e, f\]; tiene 5"),
    (lambda d: d["pdf"]["drawing"]["cad_to_page"].update(matrix=[20, 0, 0, -20, 1e8, "x"]),
     r"debe tener 6 números"),
    (lambda d: d["pdf"].update(page_size_mm=[260]), r"'pdf\.page_size_mm' debe ser \[ancho, alto\]"),
    (lambda d: d["pdf"]["drawing"]["page_bounds_mm"].update(x1=1.0),
     r"page_bounds_mm' debe ser un rectángulo con x1 > x0"),
])
def test_manifiesto_invalido(tmp_path, cambio, mensaje):
    datos = manifiesto_sintetico()
    cambio(datos)
    with pytest.raises(ManifiestoInvalido, match=mensaje):
        leer_geometria_manifiesto(escribir_json(tmp_path / "m.json", datos))


def test_manifiesto_inexistente_o_mal_escrito(tmp_path):
    with pytest.raises(ManifiestoInvalido, match="No se encontró el manifiesto"):
        leer_geometria_manifiesto(tmp_path / "no_hay.json")
    malo = tmp_path / "malo.json"
    malo.write_text("{ roto", encoding="utf-8")
    with pytest.raises(ManifiestoInvalido, match="no es un JSON válido"):
        leer_geometria_manifiesto(malo)
