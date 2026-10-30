import pymupdf
import pytest

from componedor.cad_a_papel import ManifiestoInvalido, leer_geometria_manifiesto
from componedor.comprobacion_dibujo import (
    comparar_con_manifiesto,
    exigir_coherencia,
    medir_limites_trazos,
    trazos_sin_fondo,
)
from conftest import (
    LIMITES_RECT_PAGINA_MM,
    crear_detalle_cad,
    escribir_json,
    manifiesto_sintetico,
)


@pytest.fixture
def pagina(tmp_path):
    doc = pymupdf.open(crear_detalle_cad(tmp_path / "d.pdf"))
    yield doc[0]
    doc.close()


def _geometria(tmp_path, datos=None):
    return leer_geometria_manifiesto(escribir_json(tmp_path / "m.json",
                                                   datos or manifiesto_sintetico()))


def test_mide_los_trazos_sin_el_fondo_blanco(pagina):
    assert medir_limites_trazos(pagina) == pytest.approx(LIMITES_RECT_PAGINA_MM, abs=0.01)


def test_coincide_con_page_bounds(tmp_path, pagina):
    comparacion = comparar_con_manifiesto(pagina, _geometria(tmp_path))
    assert comparacion.diferencia_max_mm < 0.01
    assert not comparacion.advertencia


def test_diferencia_grande_es_solo_advertencia(tmp_path, pagina):
    datos = manifiesto_sintetico()
    datos["pdf"]["drawing"]["page_bounds_mm"]["x1"] += 2.0
    comparacion = comparar_con_manifiesto(pagina, _geometria(tmp_path, datos))
    assert comparacion.diferencia_max_mm == pytest.approx(2.0, abs=0.01)
    assert comparacion.advertencia


def test_manifiesto_de_otro_pdf(tmp_path, pagina):
    datos = manifiesto_sintetico()
    datos["pdf"]["page_size_mm"] = [300.0, 120.0]
    with pytest.raises(ManifiestoInvalido, match="no corresponde al PDF del detalle"):
        exigir_coherencia(pagina, _geometria(tmp_path, datos))


def test_detalle_girado_no_soportado_con_manifiesto(tmp_path, pagina):
    pagina.set_rotation(90)
    datos = manifiesto_sintetico()
    datos["pdf"]["page_size_mm"] = [120.0, 260.0]
    with pytest.raises(ManifiestoInvalido, match="/Rotate 90"):
        exigir_coherencia(pagina, _geometria(tmp_path, datos))


def test_trazos_sin_fondo_en_otra_posicion():
    # Fondo blanco de un detalle ya colocado en una hoja: no ocupa toda la página.
    doc = pymupdf.open()
    hoja = doc.new_page(width=600, height=400)
    fondo = pymupdf.Rect(100, 50, 300, 150)
    hoja.draw_rect(fondo, color=None, fill=(1, 1, 1))
    hoja.draw_rect(pymupdf.Rect(120, 60, 200, 100), color=(0, 0, 0), width=0.5)
    assert len(hoja.get_drawings()) == 2
    assert len(trazos_sin_fondo(hoja, fondo)) == 1
    assert len(trazos_sin_fondo(hoja)) == 2  # el fondo de página completa no existe aquí
    doc.close()
