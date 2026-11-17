"""crear-plantilla-v3: la v2 sin la fila DISEÑADOR | REVISOR y con el logo centrado.

Plantilla sintética con la misma geometría de la franja del rótulo A1 ERCO (la real no se
versiona): líneas largas de la fila, letras como trazos cortos, línea vertical al medio, las dos
anotaciones invisibles y un «logo» (imagen) con su parte visible corrida a la derecha.
"""

import hashlib

import pymupdf
import pytest

from componedor.cli import main
from componedor.plantilla_v3 import (
    FRANJA_X_MM,
    PlantillaV3Invalida,
    _rect_pdf,
    _x_visible,
    crear_plantilla_v3,
)

CENTRO_FRANJA = sum(FRANJA_X_MM) / 2  # 750,35
LOGO_MM = (715.5, 75.6, 788.7, 98.3)
# Letras: trazos cortos dentro de la fila (Y 101,2 a 103,2), como el texto SHX de AutoCAD.
LETRAS_X = [702.7, 705.4, 707.4, 709.2, 711.0, 713.0, 714.9, 717.1,  # DISEÑADOR
            782.7, 784.7, 786.2, 788.9, 790.8, 793.0]  # REVISOR
N_ANCHO, BLOQUE = 300, (40, 280)  # columnas del logo con tinta: centro visible 754,5 mm


def _linea(pagina, x0, y0, x1, y1, ancho=0.72):
    a, b = _rect_pdf((x0, y0, x1, y1)).bl, _rect_pdf((x0, y0, x1, y1)).tr
    pagina.draw_line(a, b, width=ancho)


def _logo_png() -> bytes:
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, N_ANCHO, 100), False)
    pix.clear_with(255)
    pix.set_rect(pymupdf.IRect(BLOQUE[0], 20, BLOQUE[1], 80), (20, 140, 40))
    return pix.tobytes("png")


def _plantilla(ruta, fila=True, logos=1):
    doc = pymupdf.open()
    p = doc.new_page(width=2384, height=1684)
    p.draw_rect(_rect_pdf((12.7, 12.7, 828.3, 581.3)), width=0.72)  # marco
    for y in (74.3, 99.4, 106.2, 112.0):  # líneas largas: siguen fuera de la fila
        _linea(p, 672.4, y, 828.3, y)
    _linea(p, 690.0, 106.2, 690.0, 112.0)  # una división de la fila de encabezados (se queda)
    if fila:
        _linea(p, 750.3, 99.4, 750.3, 106.2)  # la línea vertical del medio
        for x in LETRAS_X:  # verticales: su caja es ajustada, como la de las letras SHX reales
            _linea(p, x, 101.2, x, 103.2)
        for texto, rect in (("DISEÑADOR", (701.3, 100.1, 719.3, 104.3)),
                            ("REVISOR", (781.4, 100.1, 795.2, 104.0))):
            a = p.add_rect_annot(_rect_pdf(rect))
            a.set_info(content=texto)
            a.set_border(width=0)
            a.update()
    png = _logo_png()
    for k in range(logos):
        x0, y0, x1, y1 = LOGO_MM
        p.insert_image(_rect_pdf((x0, y0 - 40 * k, x1, y1 - 40 * k)), stream=png,
                       keep_proportion=False)
    doc.save(ruta)
    return ruta


def _md5(ruta):
    return hashlib.md5(ruta.read_bytes()).hexdigest()


@pytest.fixture
def v2(tmp_path):
    return _plantilla(tmp_path / "rotulo_v2.pdf")


def test_quita_la_fila_centra_el_logo_y_no_toca_el_origen(v2, tmp_path):
    antes = _md5(v2)
    i = crear_plantilla_v3(v2, tmp_path / "v3.pdf")
    assert _md5(v2) == antes == i.md5_origen  # la v2 no cambia
    assert len(i.trazos_quitados) == len(LETRAS_X) + 1  # letras + línea vertical, nada más
    assert all(99.1 <= y0 and y1 <= 106.5 for _, y0, _, y1 in i.trazos_quitados)
    assert sorted(i.anotaciones_quitadas) == ["DISEÑADOR", "REVISOR"]
    visible = (LOGO_MM[0] + (BLOQUE[0] + BLOQUE[1]) / 2 / N_ANCHO * (LOGO_MM[2] - LOGO_MM[0]))
    assert i.centro_logo_antes_mm == pytest.approx(visible, abs=0.05)
    assert i.desplazamiento_logo_mm == pytest.approx(CENTRO_FRANJA - visible, abs=0.05)
    assert i.centro_logo_despues_mm == pytest.approx(CENTRO_FRANJA, abs=0.1)

    nuevo = pymupdf.open(tmp_path / "v3.pdf")
    p = nuevo[0]
    assert [a.info["content"] for a in p.annots()] == []
    largas = [d for d in p.get_drawings() if d["rect"].width > mm(150)]
    assert len(largas) == 5  # marco + 4 líneas largas: intactas
    assert any(abs(d["rect"].x0 - mm(690.0)) < 1 for d in p.get_drawings())  # la división sigue
    # La misma imagen (byte a byte), del mismo tamaño, corrida solo en X.
    original = pymupdf.open(v2)
    crudo = original.xref_stream_raw(original[0].get_images()[0][0])
    xref = p.get_images()[0][0]
    assert nuevo.xref_stream_raw(xref) == crudo
    (dibujada,) = [pymupdf.Rect(r) for t, r in p.get_bboxlog() if "image" in t]
    pedida = _rect_pdf(LOGO_MM)
    assert dibujada.width == pytest.approx(pedida.width, abs=0.01)
    assert dibujada.y0 == pytest.approx(pedida.y0, abs=0.01)
    x0, x1 = _x_visible(nuevo, xref, dibujada)
    assert (x0 + x1) / 2 == pytest.approx(CENTRO_FRANJA, abs=0.1)


def mm(v):
    return v * 72 / 25.4


def test_no_sobrescribe_sin_permiso(v2, tmp_path):
    crear_plantilla_v3(v2, tmp_path / "v3.pdf")
    with pytest.raises(PlantillaV3Invalida, match="ya existe. Use --sobrescribir"):
        crear_plantilla_v3(v2, tmp_path / "v3.pdf")
    crear_plantilla_v3(v2, tmp_path / "v3.pdf", sobrescribir=True)


def test_no_escribe_sobre_el_origen(v2):
    with pytest.raises(PlantillaV3Invalida, match="no puede ser la misma"):
        crear_plantilla_v3(v2, v2, sobrescribir=True)


def test_plantilla_sin_la_fila_no_deja_archivo(tmp_path):
    origen = _plantilla(tmp_path / "otra.pdf", fila=False)
    with pytest.raises(PlantillaV3Invalida, match="no hay trazos dentro de la fila"):
        crear_plantilla_v3(origen, tmp_path / "v3.pdf")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["otra.pdf"]  # ni v3 ni temporal


def test_dos_imagenes_no_se_adivina_cual_es_el_logo(tmp_path):
    origen = _plantilla(tmp_path / "otra.pdf", logos=2)
    with pytest.raises(PlantillaV3Invalida, match="una sola imagen"):
        crear_plantilla_v3(origen, tmp_path / "v3.pdf")
    assert not (tmp_path / "v3.pdf").exists()


def test_origen_que_no_existe(tmp_path):
    with pytest.raises(PlantillaV3Invalida, match="No existe la plantilla de origen"):
        crear_plantilla_v3(tmp_path / "no.pdf", tmp_path / "v3.pdf")


def test_cli(v2, tmp_path, capsys):
    args = ["crear-plantilla-v3", "--origen", str(v2), "--salida", str(tmp_path / "v3.pdf")]
    assert main(args) == 0
    out = capsys.readouterr().out
    assert "Plantilla v3 creada" in out and "igual antes y después" in out
    assert f"{len(LETRAS_X) + 1} trazo(s) borrado(s)" in out and "DISEÑADOR, REVISOR" in out
    assert "Misma imagen, sin recomprimir" in out
    assert main(args) == 1
    assert "Use --sobrescribir" in capsys.readouterr().err
