"""Textos en el PDF: se escriben como texto real con la fuente embebida, se buscan bien
(guion y espacio correctos) y la verificación detecta un texto corrido."""

from dataclasses import replace

import pymupdf
import pytest

from componedor.fuente import cargar_fuente
from componedor.hoja import crear_pagina
from componedor.maquetacion import Linea, TextoMaquetado
from componedor.textos_pdf import (
    cmap_tounicode,
    escribir_textos,
    fuera_de_celda,
    verificar_textos,
)
from conftest import ARIAL, requiere_arial

ALTO = 594.0


def _texto(ruta, texto, base, fuente, altura=2.5, celda=None):
    return TextoMaquetado(ruta, (Linea(texto, base, fuente.ancho_mm(texto, altura)),), altura,
                          celda_mm=celda)


def test_fuera_de_celda():
    celda = (100.0, 50.0, 160.0, 60.0)
    assert fuera_de_celda((100.0, 50.0, 160.0, 60.0), celda) == []
    assert fuera_de_celda((99.95, 49.95, 160.08, 60.1), celda) == []  # dentro de ±0,1 mm
    assert fuera_de_celda((99.0, 50.0, 160.3, 60.2), celda) == [
        "1.00 mm por la izquierda", "0.30 mm por la derecha", "0.20 mm por arriba"]
    assert fuera_de_celda((100.0, 49.5, 150.0, 55.0), celda) == ["0.50 mm por abajo"]


@requiere_arial
def test_caja_vertical_de_la_fuente():
    fuente = cargar_fuente(ARIAL)
    descenso, ascenso = fuente.caja_vertical_mm(2.0)
    # Arial: ascender 0,905 y descender 0,212 em; em = 2,0 / 0,716 mm.
    assert ascenso == pytest.approx(0.905 * 2.0 / (1467 / 2048), abs=0.005)
    assert descenso == pytest.approx(0.212 * 2.0 / (1467 / 2048), abs=0.005)


def _pdf_con(textos, fuente, tmp_path):
    doc = crear_pagina(841, ALTO)
    escribir_textos(doc[0], textos, fuente, ALTO)
    ruta = tmp_path / "t.pdf"
    doc.save(ruta)
    doc.close()
    return pymupdf.open(ruta)


@requiere_arial
def test_textos_dentro_de_su_celda_pasan(tmp_path):
    fuente = cargar_fuente(ARIAL)
    # Celdas reales del rótulo v2 (no_plano, hoja) con su texto maquetado.
    textos = [_texto("no_plano", "ERCO-PSF-CIV-PL-0001", (691.5, 15.55), fuente,
                     celda=(690.9, 13.5, 807.0, 20.1)),
              _texto("hoja", "1", (820.0, 40.25), fuente, 2.0, celda=(812.9, 38.3, 827.4, 43.6))]
    with _pdf_con(textos, fuente, tmp_path) as d:
        assert verificar_textos(d[0], textos, ALTO) == []


@requiere_arial
def test_texto_que_se_sale_0_3_mm_de_su_celda_falla(tmp_path):
    fuente = cargar_fuente(ARIAL)
    texto = "ERCO-PSF-CIV-PL-0001"
    puesto = _texto("no_plano", texto, (691.5, 15.55), fuente, celda=(690.9, 13.5, 807.0, 20.1))
    with _pdf_con([puesto], fuente, tmp_path) as d:
        assert verificar_textos(d[0], [puesto], ALTO) == []  # en su celda real, pasa
        # Fin del texto medido en el PDF (bbox del último carácter, mm de papel).
        ultimo = d[0].get_text("rawdict")["blocks"][0]["lines"][0]["spans"][-1]["chars"][-1]
        fin_mm = ultimo["bbox"][2] * 25.4 / 72
        # Se manipula la celda esperada: termina 0,3 mm antes del final del texto.
        celda = (690.9, 13.5, fin_mm - 0.3, 20.1)
        (problema,) = verificar_textos(d[0], [replace(puesto, celda_mm=celda)], ALTO)
    assert problema.startswith(
        f"texto 'no_plano': «{texto}» se sale de su celda X 690.90 a {celda[2]:.2f}, "
        f"Y 13.50 a 20.10 0.30 mm por la derecha (medido en el PDF: X 691.50 a ")
    assert problema.endswith("tolerancia ±0.1 mm)")


def test_cmap_tounicode_por_glifo():
    cmap = cmap_tounicode({16: "-", 3: " ", 0x24: "A", 200: "Ñ"}).decode("ascii")
    assert "4 beginbfchar" in cmap
    assert "<0003> <0020>" in cmap and "<0010> <002d>" in cmap and "<00c8> <00d1>" in cmap


def test_cmap_tounicode_bloques_de_100():
    cmap = cmap_tounicode({i: "A" for i in range(1, 251)}).decode("ascii")
    assert cmap.count("beginbfchar") == 3 and "50 beginbfchar" in cmap


@requiere_arial
def test_escribir_y_verificar(tmp_path):
    fuente = cargar_fuente(ARIAL)
    textos = [_texto("no_plano", "ERCO-PSF-CIV-PL-0001", (100.0, 50.0), fuente),
              _texto("titulo", "DISEÑÓ: ÁNGELA NÚÑEZ ±0,5 °C", (100.0, 60.0), fuente, 2.0)]
    doc = crear_pagina(841, ALTO)
    assert escribir_textos(doc[0], textos, fuente, ALTO) == 2
    ruta = tmp_path / "t.pdf"
    doc.save(ruta)
    doc.close()
    with pymupdf.open(ruta) as d:
        page = d[0]
        assert verificar_textos(page, textos, ALTO) == []
        texto = page.get_text()
        # Se lee y se busca con el guion y los espacios normales (no U+00AD ni U+00A0).
        assert "ERCO-PSF-CIV-PL-0001" in texto and "DISEÑÓ: ÁNGELA NÚÑEZ ±0,5 °C" in texto
        assert "­" not in texto and " " not in texto
        assert len(page.search_for("ERCO-PSF")) == 1
        fuentes = d.get_page_fonts(0)
        assert len(fuentes) == 1 and fuentes[0][1] == "ttf"  # una sola, embebida
        assert page.get_images() == []  # texto, no imagen
        # El primer carácter escrito es la «E» de ERCO, con su origen en la base pedida.
        caracter = page.get_text("rawdict")["blocks"][0]["lines"][0]["spans"][0]["chars"][0]
        assert caracter["c"] == "E"
        assert caracter["origin"][0] == pytest.approx(100.0 * 72 / 25.4, abs=0.01)


@requiere_arial
def test_la_verificacion_detecta_un_texto_corrido(tmp_path):
    fuente = cargar_fuente(ARIAL)
    puesto = _texto("hoja", "1", (800.0, 40.0), fuente)
    esperado = _texto("hoja", "1", (800.0, 40.3), fuente)  # 0,3 mm más arriba
    doc = crear_pagina(841, ALTO)
    escribir_textos(doc[0], [puesto], fuente, ALTO)
    problemas = verificar_textos(doc[0], [esperado], ALTO)
    assert problemas == ["texto 'hoja': se esperaba «1» con su base en X 800.00, Y 40.30 mm "
                         "(±0.1 mm) y allí se lee «»"]
    assert verificar_textos(doc[0], [_texto("hoja", "1", (800.05, 40.05), fuente)], ALTO) == []


@requiere_arial
def test_altura_real_de_las_mayusculas(tmp_path):
    fuente = cargar_fuente(ARIAL)
    doc = crear_pagina(841, ALTO)
    escribir_textos(doc[0], [_texto("x", "H", (100.0, 100.0), fuente, 5.0)], fuente, ALTO)
    pix = doc[0].get_pixmap(dpi=600, clip=pymupdf.Rect(270, 1380, 300, 1410))
    # Filas con tinta: la "H" va de la base (Y = 100 mm) a 105 mm de papel.
    filas = [y for y in range(pix.height)
             if any(pix.pixel(x, y)[0] < 128 for x in range(pix.width))]
    alto_mm = (filas[-1] - filas[0] + 1) / 600 * 25.4
    assert alto_mm == pytest.approx(5.0, abs=0.05)
