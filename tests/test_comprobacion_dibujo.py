"""Medición de trazos sin el fondo blanco. La comparación con el manifiesto (rotación,
tamaño de página, trazos vs page_bounds_mm) se prueba en test_coherencia.py."""

import pymupdf
import pytest

from componedor.comprobacion_dibujo import (
    es_fondo_de_pagina,
    medir_limites_trazos,
    tiene_fondo_de_pagina,
    trazos_sin_fondo,
)
from conftest import LIMITES_RECT_PAGINA_MM, crear_detalle_cad, crear_paquete_real


@pytest.fixture
def pagina(tmp_path):
    doc = pymupdf.open(crear_detalle_cad(tmp_path / "d.pdf"))
    yield doc[0]
    doc.close()


def test_mide_los_trazos_sin_el_fondo_blanco(pagina):
    assert medir_limites_trazos(pagina) == pytest.approx(LIMITES_RECT_PAGINA_MM, abs=0.01)


def test_reconoce_el_fondo_de_pagina(pagina):
    fondos = [d for d in pagina.get_drawings() if es_fondo_de_pagina(d, pagina)]
    assert len(fondos) == 1
    assert len(trazos_sin_fondo(pagina)) == len(pagina.get_drawings()) - 1


def test_tiene_fondo_de_pagina(tmp_path):
    con = pymupdf.open(crear_paquete_real(tmp_path / "con", "c"))
    sin = pymupdf.open(crear_paquete_real(tmp_path / "sin", "s", sin_fondo=True))
    assert tiene_fondo_de_pagina(con[0]) is True
    assert tiene_fondo_de_pagina(sin[0]) is False
    # Con o sin fondo, el dibujo medido es el mismo (el fondo se ignora con la misma regla).
    assert medir_limites_trazos(sin[0]) == pytest.approx(medir_limites_trazos(con[0]))
    con.close()
    sin.close()


def test_rectangulo_blanco_que_no_es_toda_la_pagina_no_es_fondo():
    doc = pymupdf.open()
    pagina = doc.new_page(width=300, height=200)
    pagina.draw_rect(pymupdf.Rect(10, 10, 100, 100), color=None, fill=(1, 1, 1))
    assert tiene_fondo_de_pagina(pagina) is False
    doc.close()


def test_pagina_sin_trazos():
    doc = pymupdf.open()
    pagina = doc.new_page()
    pagina.draw_rect(pagina.rect, color=None, fill=(1, 1, 1))  # solo el fondo
    assert medir_limites_trazos(pagina) is None
    doc.close()


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
