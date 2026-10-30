import pytest

from componedor import referencia as ref
from componedor.comprobacion_dibujo import medir_limites_trazos


@pytest.fixture
def detalle():
    d = ref.generar_detalle_referencia()
    yield d
    d.doc.close()


def test_matriz_1_50_con_coordenadas_de_millones(detalle):
    m = detalle.matriz
    assert (m.a, m.b, m.c, m.d) == (20.0, 0.0, 0.0, -20.0)
    assert 1e7 < abs(m.e) < 1e9 and 1e7 < abs(m.f) < 1e9


def test_pagina_y_page_bounds(detalle):
    assert detalle.doc.page_count == 1
    assert (detalle.ancho_pagina_mm, detalle.alto_pagina_mm) == ref.PAGINA_MM
    # Márgenes asimétricos: 12,5 a la izquierda y 9 arriba; dibujo de 240 x 100 mm.
    assert detalle.limites_pagina_mm == pytest.approx((12.5, 9.0, 252.5, 109.0))
    # Los trazos reales (sin el fondo blanco) coinciden con page_bounds.
    assert medir_limites_trazos(detalle.doc[0]) == pytest.approx(detalle.limites_pagina_mm,
                                                                 abs=0.01)


def test_figuras_a_escala_1_50(detalle):
    m = detalle.matriz
    x0, y0, x1, y1 = ref.CUADRADO_CAD
    (px0, py0), (px1, py1) = m.cad_a_pagina(x0, y0), m.cad_a_pagina(x1, y1)
    assert (px1 - px0, py0 - py1) == pytest.approx((100.0, 100.0))
    x0, y0, x1, y1 = ref.RECTANGULO_CAD
    (px0, py0), (px1, py1) = m.cad_a_pagina(x0, y0), m.cad_a_pagina(x1, y1)
    assert (px1 - px0, py0 - py1) == pytest.approx((100.0, 40.0))


def test_texto_real_y_marca(detalle):
    page = detalle.doc[0]
    assert ref.TEXTO in page.get_text()
    marcas = [d for d in page.get_drawings() if d.get("fill") == ref.COLOR_MARCA]
    assert len(marcas) == 1
    assert page.get_images() == []


def test_factor_error_escala_el_dibujo():
    d = ref.generar_detalle_referencia(factor_error=1.01)
    x0, y0, x1, y1 = medir_limites_trazos(d.doc[0])
    d.doc.close()
    assert x1 - x0 == pytest.approx(240.0 * 1.01, abs=0.01)
