"""Cuadrícula de coordenadas (cuadricula.py): valores, líneas en la región, etiquetas en la franja
de afuera (como el plano de AutoCAD de PRGD), choques, avisos, dibujo y verificación."""

import pymupdf
import pytest
from conftest import MATRIZ_SINTETICA, X0_CAD, Y0_CAD

from componedor.cad_a_papel import MatrizCad
from componedor.cuadricula import (
    BANDA_MM,
    COLOR,
    EM_MM,
    GROSOR_MM,
    altura_mm,
    ancho_texto_mm,
    armar,
    dibujar,
    texto_coordenada,
    valores,
    verificar,
)
from componedor.formato import cargar_formato
from componedor.fuente import cargar_fuente
from componedor.unidades import mm_a_pt

MATRIZ = MatrizCad(*MATRIZ_SINTETICA)  # 1:50 en m: 20 mm de papel por m
OCUPADO = (100.0, 100.0, 360.0, 220.0)  # página de 260 × 120 mm: 13 × 6 m
MARCO = (12.7, 12.7, 828.3, 581.3)
ALTO = 594.0


def test_valores_y_formato():
    assert valores(4705893.2, 4706019.7, 50) == [4705900.0, 4705950.0, 4706000.0]
    assert valores(100.0, 200.0, 50) == [150.0]  # los bordes exactos no cuentan
    assert valores(0.0, 10.0, 50) == []
    assert texto_coordenada(4705900) == "4705900.000"  # como PRGD: 3 decimales, sin letras
    assert texto_coordenada(2201249.99951) == "2201250.000"


def test_lineas_cubren_la_region_y_caen_donde_dice_el_cad():
    c = armar("a", OCUPADO, OCUPADO, MATRIZ, 1000.0, 2.0)
    # La página va de X0−0,865 a X0+12,135 y de Y0+0,935 a Y0+6,935 (m): cada 2 m.
    assert c.este == [X0_CAD + v for v in (0, 2, 4, 6, 8, 10, 12)]
    assert c.norte == [Y0_CAD + v for v in (2, 4, 6)]
    x_de = {e: x for e, (x, *_) in zip(c.este, c.lineas_mm, strict=False)}
    # X0 está a 0,865 m del borde izquierdo: 17,3 mm a 1:50.
    assert x_de[X0_CAD] == pytest.approx(OCUPADO[0] + 17.3)
    assert all(lin[1] == OCUPADO[1] and lin[3] == OCUPADO[3] for lin in c.lineas_mm[:7])
    assert all(lin[0] == OCUPADO[0] and lin[2] == OCUPADO[2] for lin in c.lineas_mm[7:])
    assert c.avisos == []  # 2 m a 1:50 = 40 mm: no está apretada


def test_etiquetas_en_la_franja_de_afuera_como_prgd():
    """Este abajo y arriba (horizontal), Norte a los lados (girado), centradas en la franja de
    10 mm y en su línea, fuera de la región."""
    c = armar("a", OCUPADO, OCUPADO, MATRIZ, 1000.0, 2.0, limite=MARCO)
    h, w = altura_mm(), ancho_texto_mm("4900000.000")
    (abajo, arriba) = [e for e in c.etiquetas if e.texto == "4900000.000"]
    x = OCUPADO[0] + 17.3
    assert abajo.giro == 0 and abajo.rect_mm == pytest.approx(
        (x - w / 2, OCUPADO[1] - BANDA_MM / 2 - h / 2, x + w / 2, OCUPADO[1] - BANDA_MM / 2 + h / 2))
    assert arriba.rect_mm[1] == pytest.approx(OCUPADO[3] + BANDA_MM / 2 - h / 2)
    izquierda, derecha = [e for e in c.etiquetas if e.eje == "N"][:2]
    assert izquierda.giro == derecha.giro == 90
    assert (izquierda.rect_mm[0] + izquierda.rect_mm[2]) / 2 == pytest.approx(OCUPADO[0] - BANDA_MM / 2)
    assert (derecha.rect_mm[0] + derecha.rect_mm[2]) / 2 == pytest.approx(OCUPADO[2] + BANDA_MM / 2)
    assert len(c.etiquetas) == 2 * 7 + 2 * 3 and c.omitidas == 0  # una en cada extremo de cada línea


def test_misma_ubicacion_que_el_plano_de_prgd():
    """Medido en data/input/PRGD-26-1377-GEN-PL-101_1_V0.pdf (área de dibujo de 22,7 a 662,4 ×
    22,7 a 571,3; línea de Este 4705900 en X 117,73): etiqueta abajo de X 107,43 a 128,02 y de
    Y 15,55 a 19,08; Norte 2201100 (línea en Y 33,74) a la izquierda de Y 23,45 a 44,05 con su
    base en X 18,91. Con Arial de 10 pt, ±0,2 mm."""
    formato = cargar_formato("formatos/A1_ERCO.json", usar_plantilla=False)
    if formato.rotulo is None or not formato.rotulo.fuente.is_file():
        pytest.skip("sin la fuente del rótulo")
    fuente = cargar_fuente(formato.rotulo.fuente)
    area = (22.7, 22.7, 662.4, 571.3)
    w = ancho_texto_mm("4705900.000", fuente)
    assert w == pytest.approx(128.02 - 107.43, abs=0.05)  # 10 pt exactos
    # Un mapeo de 1:500 que pone E 4705900 en X 117,73 y N 2201100 en Y 33,74.
    a = 2.0
    m = MatrizCad(a, 0.0, 0.0, -a, -a * 4705900.0 + (117.73 - area[0]),
                  a * 2201100.0 + (area[3] - area[1]) - (33.74 - area[1]))
    c = armar("prgd", area, area, m, 1000.0, 50.0, limite=MARCO, fuente=fuente)
    (abajo,) = [e for e in c.etiquetas if e.texto == "4705900.000" and e.rect_mm[1] < 22.7]
    assert abajo.rect_mm[0] == pytest.approx(107.43, abs=0.2)
    assert abajo.rect_mm[2] == pytest.approx(128.02, abs=0.2)
    (izq,) = [e for e in c.etiquetas if e.texto == "2201100.000" and e.rect_mm[0] < 22.7]
    assert izq.rect_mm[1] == pytest.approx(23.45, abs=0.2)
    assert izq.base_mm[0] == pytest.approx(18.91, abs=0.2)


def test_choques_limite_y_avisos():
    rosa = (OCUPADO[0] + 10, OCUPADO[1] - 9, OCUPADO[0] + 25, OCUPADO[1] - 1)
    c = armar("a", OCUPADO, OCUPADO, MATRIZ, 1000.0, 2.0, obstaculos=[rosa], limite=MARCO)
    assert c.omitidas == 1 and len(c.etiquetas) == 19  # la de E X0 abajo choca con la rosa
    assert "se omitieron 1 etiqueta(s)" in c.avisos[0]
    # Contra el marco: la página pegada al borde izquierdo del marco deja sin las de Norte de
    # la izquierda.
    pegada = (15.0, 100.0, 275.0, 220.0)
    c = armar("b", pegada, pegada, MATRIZ, 1000.0, 2.0, limite=MARCO)
    assert sum(e.eje == "N" and e.rect_mm[0] < 15 for e in c.etiquetas) == 0
    assert c.omitidas == 3
    apretada = armar("c", OCUPADO, OCUPADO, MATRIZ, 1000.0, 0.5)
    assert "muy apretadas" in apretada.avisos[0]  # 0,5 m a 1:50 = 10 mm
    nada = armar("d", OCUPADO, OCUPADO, MATRIZ, 1000.0, 41.0)  # ningún múltiplo de 41 m cae
    assert nada.lineas_mm == [] and "no cae ninguna línea" in nada.avisos[0]
    demasiadas = armar("e", OCUPADO, OCUPADO, MATRIZ, 1000.0, 0.01)
    assert demasiadas.lineas_mm == [] and "no se dibuja" in demasiadas.avisos[0]
    girada = armar("f", OCUPADO, OCUPADO, MatrizCad(0.0, 20.0, -20.0, 0.0, 0.0, 0.0), 1000.0, 2.0)
    assert girada.lineas_mm == [] and "girado" in girada.avisos[0]


def test_dibujar_y_verificar(tmp_path):
    c = armar("a", OCUPADO, OCUPADO, MATRIZ, 1000.0, 2.0, limite=MARCO)
    doc = pymupdf.open()
    page = doc.new_page(width=mm_a_pt(841), height=mm_a_pt(ALTO))
    dibujar(page, ALTO, c)
    doc.save(tmp_path / "c.pdf")
    with pymupdf.open(tmp_path / "c.pdf") as d:
        p = d[0]
        (lineas,) = p.get_drawings()  # una sola forma, sin fondos ni halos
        assert len(lineas["items"]) == 10
        assert lineas["color"] == COLOR and lineas["width"] == pytest.approx(mm_a_pt(GROSOR_MM))
        assert verificar(p, [c], ALTO) == []
        palabras = {w[4] for w in p.get_text("words")}
        assert {"4900000.000", "5100004.000"} <= palabras
        # El Norte se lee de abajo hacia arriba (como en PRGD).
        tramo = next(s for b in p.get_text("rawdict")["blocks"] for linea in b.get("lines", [])
                     for s in linea["spans"] if "".join(ch["c"] for ch in s["chars"]) == "5100004.000")
        assert tramo["chars"][0]["origin"][1] > tramo["chars"][-1]["origin"][1]  # Y del PDF baja
        assert tramo["size"] == pytest.approx(10.0)
    c.etiquetas.append(type(c.etiquetas[0])("E", "1.000", (500, 500, 510, 503), (500, 500), 0))
    with pymupdf.open(tmp_path / "c.pdf") as d:
        assert "falta la etiqueta 1.000" in verificar(d[0], [c], ALTO)[0]


def test_em_de_10_pt():
    assert EM_MM == pytest.approx(3.5278, abs=1e-4)
    assert ancho_texto_mm("4705900.000") == pytest.approx(5.838 * EM_MM, abs=1e-3)  # Helvetica
