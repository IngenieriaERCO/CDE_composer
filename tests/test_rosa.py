"""Rosa de los vientos: quitarla de la plantilla sin tocar nada más y volver a dibujarla como
vector (en su sitio, movida u oculta)."""

import pymupdf
import pytest

from componedor.composicion import MANTENER, hoja_base, hoja_base_con_rosa
from componedor.formato import ElementoPlantilla, cargar_formato
from componedor.rosa import (
    RosaInvalida,
    documento_rosa_sola,
    elementos_visibles,
    rect_destino,
    verificar_rosa,
)
from componedor.transformaciones import rect_papel_a_pdf
from componedor.unidades import pt_a_mm
from conftest import crear_plantilla_sintetica, escribir_formato

ROSA = (612.0, 51.0, 652.0, 91.0)
OTRO = (500.0, 400.0, 540.0, 440.0)  # otro elemento fijo (no se mueve)


@pytest.fixture
def formato(tmp_path):
    plantilla = crear_plantilla_sintetica(tmp_path / "rotulo.pdf", elementos_mm=[ROSA, OTRO],
                                          letra_en_elementos="N")
    ruta = escribir_formato(tmp_path / "formato.json", plantilla=plantilla, elementos_plantilla=[
        {"nombre": "otro", "rect_mm": list(OTRO)}, {"nombre": "rosa_vientos", "rect_mm": list(ROSA)}])
    return cargar_formato(ruta)


def _geometria(page):
    """(rects de trazos en mm de papel, ordenados; palabras ordenadas)."""
    alto = pt_a_mm(page.rect.height)
    rects = sorted(tuple(round(v, 3) for v in (pt_a_mm(d["rect"].x0), alto - pt_a_mm(d["rect"].y1),
                                               pt_a_mm(d["rect"].x1), alto - pt_a_mm(d["rect"].y0)))
                   for d in page.get_drawings())
    return rects, sorted(w[4] for w in page.get_text("words"))


def _dentro(rects, caja):
    return [r for r in rects if r[0] >= caja[0] - 2 and r[1] >= caja[1] - 2
            and r[2] <= caja[2] + 2 and r[3] <= caja[3] + 2]


def test_rect_destino_y_elementos_visibles(formato):
    assert rect_destino(ROSA, None) == ROSA
    assert rect_destino(ROSA, (100.0, 200.0)) == (100.0, 200.0, 140.0, 240.0)
    movida = (100.0, 200.0, 140.0, 240.0)
    assert elementos_visibles(formato, movida) == [ElementoPlantilla("otro", OTRO),
                                                   ElementoPlantilla("rosa_vientos", movida)]
    assert elementos_visibles(formato, None) == [ElementoPlantilla("otro", OTRO)]  # oculta


def test_en_su_sitio_es_igual_a_la_plantilla_sin_tocar(formato):
    sin_tocar, _ = hoja_base(formato)
    con_rosa, _, informe = hoja_base_con_rosa(formato, rosa=ROSA)
    a, b = _geometria(sin_tocar[0]), _geometria(con_rosa[0])
    assert len(a[0]) == len(b[0])
    assert max(abs(x - y) for p, q in zip(a[0], b[0]) for x, y in zip(p, q)) <= 0.1
    assert a[1] == b[1] == ["N", "N"]
    assert informe.quitados == 2 and informe.textos_original == ("N",)
    assert verificar_rosa(con_rosa[0], informe, formato, len(con_rosa[0].get_drawings())) == []


def test_movida_el_resto_identico_y_la_rosa_trasladada(formato):
    sin_tocar, _ = hoja_base(formato)
    destino = rect_destino(ROSA, (100.0, 300.0))
    movida, _, informe = hoja_base_con_rosa(formato, rosa=destino)
    antes, despues = _geometria(sin_tocar[0]), _geometria(movida[0])
    assert _dentro(despues[0], ROSA) == []  # el sitio viejo quedó vacío
    rosa_antes = _dentro(antes[0], ROSA)
    rosa_despues = _dentro(despues[0], destino)
    assert len(rosa_despues) == len(rosa_antes) == 2
    for r0, r1 in zip(rosa_antes, rosa_despues):
        assert [r1[0] - r0[0], r1[1] - r0[1], r1[2] - r0[2], r1[3] - r0[3]] == pytest.approx(
            [-512.0, 249.0, -512.0, 249.0], abs=0.1)
    resto_antes = [r for r in antes[0] if r not in rosa_antes]
    resto_despues = [r for r in despues[0] if r not in rosa_despues]
    assert resto_antes == resto_despues  # marco, columna del rótulo, el otro elemento, ...
    assert despues[1] == ["N", "N"]  # la letra de la rosa viajó con ella
    assert len(movida[0].get_image_info()) == 1  # el logo sigue (y no hay imágenes nuevas)
    assert verificar_rosa(movida[0], informe, formato, len(movida[0].get_drawings())) == []


def test_oculta(formato):
    sin_tocar, _ = hoja_base(formato)
    oculta, _, informe = hoja_base_con_rosa(formato, rosa=None)
    antes, despues = _geometria(sin_tocar[0]), _geometria(oculta[0])
    assert _dentro(despues[0], ROSA) == []
    assert despues[0] == [r for r in antes[0] if r not in _dentro(antes[0], ROSA)]
    assert despues[1] == ["N"]  # solo la del otro elemento
    assert informe.destino is None
    assert verificar_rosa(oculta[0], informe, formato, len(oculta[0].get_drawings())) == []


def test_mantener_no_toca_la_plantilla(formato):
    doc, _, informe = hoja_base_con_rosa(formato, rosa=MANTENER)
    assert informe is None
    assert _geometria(doc[0]) == _geometria(hoja_base(formato)[0][0])


def test_rosa_sola(formato):
    doc = documento_rosa_sola(formato)
    rects, palabras = _geometria(doc[0])
    assert len(rects) == 2 and palabras == ["N"]
    assert doc[0].get_image_info() == []


def test_si_la_redaccion_no_quita_la_rosa_es_error(formato, monkeypatch):
    # Si algo de la plantilla no quedara como estaba, se detiene (aquí: no se borró nada).
    monkeypatch.setattr(pymupdf.Page, "apply_redactions", lambda self, **kw: True)
    with pytest.raises(RosaInvalida, match=r"al quitar la rosa de la plantilla cambió algo más:\n"
                                           r"- trazos: quedaron \d+ y debían quedar \d+"):
        hoja_base_con_rosa(formato, rosa=ROSA)


def test_verificar_detecta_la_rosa_corrida(formato):
    destino = rect_destino(ROSA, (100.0, 300.0))
    doc, _, informe = hoja_base_con_rosa(formato, rosa=destino)
    corrido = type(informe)(informe.original, rect_destino(ROSA, (100.5, 300.0)),
                            informe.trazos_original, informe.textos_original, informe.quitados)
    problemas = verificar_rosa(doc[0], corrido, formato, len(doc[0].get_drawings()))
    assert problemas and "la rosa quedó corrida 0.500 mm" in problemas[0]
    oculta = type(informe)(informe.original, None, (), (), 2)
    hoja, _ = hoja_base(formato)  # la rosa sigue en su sitio
    assert verificar_rosa(hoja[0], oculta, formato, len(hoja[0].get_drawings())) == [
        "la rosa está oculta, pero quedan 2 trazo(s) en su sitio original"]


def test_la_copia_es_vectorial(formato):
    doc, _, _ = hoja_base_con_rosa(formato, rosa=rect_destino(ROSA, (100.0, 300.0)))
    pagina = doc[0]
    # Ninguna imagen nueva: el logo de la plantilla es la única.
    assert len(pagina.get_image_info()) == 1
    caja = rect_papel_a_pdf((99.0, 299.0, 141.0, 341.0), 594.0)
    assert sum(caja.contains(d["rect"]) for d in pagina.get_drawings()) == 2
