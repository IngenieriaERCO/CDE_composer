"""La ortofoto en el PDF (ortofoto_pdf): cuadrícula, caja CAD, mosaicos JPEG en su sitio y con la
foto donde predice el CAD, máscara y opacidad. Con el paquete sintético de conftest (1:50,
página 260 × 120 mm) y GeoTIFF sintéticos debajo."""

import numpy as np
import pymupdf
import pytest
from conftest import MATRIZ_SINTETICA, X0_CAD, Y0_CAD
from ortofoto_sintetica import crear_geotiff, error_de_posicion, imagenes_pdf

from componedor.cad_a_papel import MatrizCad
from componedor.ortofoto import leer_sistema
from componedor.ortofoto_pdf import (
    DetalleOrtofoto,
    caja_cad,
    cuadricula,
    papel_a_cad,
    poner_ortofoto,
    verificar_ortofoto,
)
from componedor.ortofoto_render import abrir_fuente
from componedor.unidades import mm_a_pt

M9377 = leer_sistema("EPSG:9377")
MATRIZ = MatrizCad(*MATRIZ_SINTETICA)
OCUPADO = (30.0, 40.0, 290.0, 160.0)  # la página de 260 × 120 mm en la hoja
ALTO_HOJA = 594.0


def detalle(**cambios):
    datos = {"id": "d1", "ocupado": OCUPADO, "matriz": MATRIZ, "mm_por_unidad": 1000.0}
    datos.update(cambios)
    return DetalleOrtofoto(**datos)


def ortofoto(tmp_path, **kw):
    """5 cm por píxel (1 mm de papel a 1:50), cubre X0−2..X0+18, Y0−2..Y0+8: toda la página."""
    datos = {"ancho": 400, "alto": 200, "origen": (X0_CAD - 2, Y0_CAD + 8), "pixel": 0.05,
             "sinusoidal": True}
    datos.update(kw)
    return crear_geotiff(tmp_path / "orto.tif", **datos)


def componer_en_blanco(tmp_path, ruta_tif, detalles, **kw):
    doc = pymupdf.open()
    page = doc.new_page(width=mm_a_pt(841), height=mm_a_pt(ALTO_HOJA))
    with abrir_fuente(ruta_tif) as f:
        informe = poner_ortofoto(page, ALTO_HOJA, detalles, {d.id: f for d in detalles}, M9377,
                                 **kw)
    salida = tmp_path / "hoja.pdf"
    doc.save(salida)
    doc.close()
    return informe, salida


def test_cuadricula_cubre_la_pagina_exacta():
    (ancho, alto), mosaicos = cuadricula(OCUPADO, 300)
    assert (ancho, alto) == (3071, 1417)  # 260 mm y 120 mm a 300 ppp
    assert len(mosaicos) == 6  # 3 columnas × 2 filas de 1024 px
    assert mosaicos[0].columnas == (0, 1024) and mosaicos[-1].columnas == (2048, 3071)
    assert mosaicos[0].filas == (0, 1024) and mosaicos[-1].filas == (1024, 1417)
    assert mosaicos[0].rect_mm[0] == OCUPADO[0] and mosaicos[0].rect_mm[3] == OCUPADO[3]
    assert mosaicos[-1].rect_mm[2] == pytest.approx(OCUPADO[2])
    assert mosaicos[-1].rect_mm[1] == pytest.approx(OCUPADO[1])
    area = sum((m.rect_mm[2] - m.rect_mm[0]) * (m.rect_mm[3] - m.rect_mm[1]) for m in mosaicos)
    assert area == pytest.approx(260 * 120)
    assert len(cuadricula(OCUPADO, 72)[1]) == 1  # a 72 ppp, 737 × 340 px: un solo mosaico


def test_caja_cad_de_la_pagina_y_vuelta():
    caja = caja_cad(OCUPADO, OCUPADO, MATRIZ)
    assert caja == pytest.approx((X0_CAD - 0.865, Y0_CAD + 0.935, X0_CAD + 12.135, Y0_CAD + 6.935))
    # La esquina superior izquierda de la página es (X mínimo, Y máximo) en CAD.
    assert papel_a_cad((OCUPADO[0], OCUPADO[3]), OCUPADO, MATRIZ) == pytest.approx(
        (caja[0], caja[3]))
    girada = MatrizCad(0.0, 20.0, -20.0, 0.0, 0.0, 0.0)
    assert caja_cad(OCUPADO, OCUPADO, girada) is None


def test_la_foto_cae_donde_predice_el_cad(tmp_path):
    ruta = ortofoto(tmp_path)
    informe, pdf = componer_en_blanco(tmp_path, ruta, [detalle()], ppp=150)
    imagenes = imagenes_pdf(pdf, ALTO_HOJA)
    assert len(imagenes) == len(informe.mosaicos) == 2  # 1535 × 709 px: 2 mosaicos
    assert all(i["filtro"] == "/DCTDecode" and i["mascara"] is None for i in imagenes)
    assert informe.cobertura == {"d1": 1.0}

    def a_cad(x, y):
        return papel_a_cad((x, y), OCUPADO, MATRIZ)

    for imagen in imagenes:
        bien = error_de_posicion(imagen, a_cad, ruta)
        corrida = error_de_posicion(imagen, a_cad, ruta, corrimiento=(1.0, 0.0))  # 1 mm = 1 px
        assert bien < 4, bien  # solo el JPEG
        assert corrida > 8 * bien, (bien, corrida)  # corrida 1 mm: el error se dispara
    assert verificar_ortofoto(pymupdf.open(pdf)[0], informe, ALTO_HOJA) == []


def test_mascara_donde_no_hay_foto_y_opacidad(tmp_path):
    # La foto empieza 5 m a la derecha del borde izquierdo de la página: lo de la izquierda
    # queda sin foto (máscara 0) y la opacidad 0,6 va en la máscara (153).
    ruta = ortofoto(tmp_path, origen=(X0_CAD + 4.135, Y0_CAD + 8))
    informe, pdf = componer_en_blanco(tmp_path, ruta, [detalle()], ppp=100, opacidad=0.6)
    assert informe.cobertura["d1"] == pytest.approx(8 / 13, abs=0.01)
    (imagen,) = imagenes_pdf(pdf, ALTO_HOJA)
    m = imagen["mascara"]
    assert m is not None and set(np.unique(m)) == {0, 153}
    ancho = m.shape[1]
    assert m[:, : int(ancho * 4.9 / 13)].max() == 0 and m[:, int(ancho * 5.1 / 13):].min() == 153


def test_mosaicos_sin_foto_no_se_ponen(tmp_path):
    lejos = ortofoto(tmp_path, origen=(X0_CAD + 500, Y0_CAD + 8))
    informe, pdf = componer_en_blanco(tmp_path, lejos, [detalle()])
    assert informe.mosaicos == [] and informe.cobertura == {"d1": 0.0}
    assert informe.avisos == ["La ortofoto no cubre el detalle 'd1'."]
    assert imagenes_pdf(pdf, ALTO_HOJA) == []


def test_girado_y_con_fondo_avisan(tmp_path):
    ruta = ortofoto(tmp_path)
    girada = detalle(id="g", matriz=MatrizCad(0.0, 20.0, -20.0, 0.0, 0.0, 0.0))
    con_fondo = detalle(id="f", tiene_fondo=True)
    informe, _ = componer_en_blanco(tmp_path, ruta, [girada, con_fondo], ppp=50)
    assert informe.avisos == [
        "Detalle 'g': su dibujo está girado en la página (matriz con giro): no lleva ortofoto.",
        ("El detalle 'f' tiene fondo blanco de página (paquete antiguo): tapa la ortofoto. "
         "Vuelva a exportarlo.")]
    assert {m.detalle for m in informe.mosaicos} == {"f"}


def test_la_verificacion_nota_un_mosaico_que_falta(tmp_path):
    ruta = ortofoto(tmp_path)
    informe, pdf = componer_en_blanco(tmp_path, ruta, [detalle()], ppp=50)
    informe.mosaicos.append(type(informe.mosaicos[0])("d1", (500, 500, 510, 510), (10, 10), 1,
                                                      False))
    (problema,) = verificar_ortofoto(pymupdf.open(pdf)[0], informe, ALTO_HOJA)
    assert "falta el mosaico en X 500.00 a 510.00" in problema
