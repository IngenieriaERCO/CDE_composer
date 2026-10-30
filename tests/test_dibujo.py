from pathlib import Path

import pymupdf
import pytest

from componedor.cli import hoja_formato
from componedor.transformaciones import rect_pdf_a_papel
from componedor.unidades import mm_a_pt

RUTA_A1 = Path(__file__).parent.parent / "formatos" / "A1_ERCO.json"
TOL_MM = 0.1
MARCO_MM = (12.7, 12.7, 828.3, 581.3)


@pytest.fixture(params=[False, True], ids=["sin_guias", "con_guias"])
def pdf_generado(request, tmp_path):
    salida = tmp_path / "a1_erco.pdf"
    hoja_formato(RUTA_A1, salida, guias=request.param, usar_plantilla=False)
    with pymupdf.open(salida) as doc:
        yield doc, request.param


def _trazos_marco(page):
    grosor_marco = mm_a_pt(0.5)
    return [d for d in page.get_drawings() if d["width"] == pytest.approx(grosor_marco)]


def test_marco_en_su_posicion(pdf_generado):
    page = pdf_generado[0][0]
    alto_mm = 594.0
    marcos = _trazos_marco(page)
    assert len(marcos) == 1
    # El marco se dibuja como un rectángulo ("re"); se lee su geometría, no la caja con grosor.
    (tipo, rect, *_), = marcos[0]["items"]
    assert tipo == "re"
    for obtenido, esperado in zip(rect_pdf_a_papel(rect, alto_mm), MARCO_MM):
        assert abs(obtenido - esperado) <= TOL_MM


def test_guias_presentes_solo_si_se_piden(pdf_generado):
    doc, con_guias = pdf_generado
    page = doc[0]
    guias = [d for d in page.get_drawings() if d.get("dashes") not in (None, "[] 0")]
    texto = page.get_text()
    if con_guias:
        assert len(guias) == 6
        for nombre in ("area_dibujo", "rotulo", "localizacion", "notas", "convenciones", "cajetin"):
            assert nombre in texto
    else:
        assert guias == []
        assert texto.strip() == ""


def test_pdf_sin_imagenes(pdf_generado):
    doc, _ = pdf_generado
    page = doc[0]
    assert page.get_images(full=True) == []
    assert page.get_image_info() == []
    assert page.rotation == 0
    assert doc.page_count == 1
