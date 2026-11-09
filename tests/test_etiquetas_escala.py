"""Etiqueta "ESC: 1:N" por detalle: debajo del dibujo, si no encima, si no se avisa."""

import pytest

from componedor.etiquetas_escala import (
    DetalleParaEtiqueta,
    colocar_etiquetas,
    texto_etiqueta,
)
from componedor.fuente import cargar_fuente
from conftest import ARIAL, requiere_arial

pytestmark = requiere_arial
AREA = (22.7, 22.7, 662.4, 571.3)


@pytest.fixture(scope="module")
def fuente():
    return cargar_fuente(ARIAL)


def test_texto_con_punto_de_miles():
    assert texto_etiqueta(50.0) == "ESC: 1:50"
    assert texto_etiqueta(1000.0) == "ESC: 1:1.000"
    assert texto_etiqueta(10000.0) == "ESC: 1:10.000"


def test_debajo_del_dibujo_centrada_a_3_mm(fuente):
    d = DetalleParaEtiqueta("a", (100.0, 200.0, 300.0, 260.0), 1000.0)
    textos, avisos = colocar_etiquetas([d], AREA, [], fuente)
    (t,) = textos
    (linea,) = t.lineas
    assert avisos == [] and t.ruta == "etiqueta_escala.a" and t.altura_mm == 2.5
    assert linea.texto == "ESC: 1:1.000"
    ancho = fuente.ancho_mm("ESC: 1:1.000", 2.5)
    # Mayúsculas de 194,5 a 197: su tope a 3 mm del borde inferior del dibujo (200).
    assert linea.base_mm == pytest.approx((200 - ancho / 2, 200 - 3 - 2.5))
    assert t.rect()[0] + t.rect()[2] == pytest.approx(400)  # centrada en el dibujo


def test_encima_si_debajo_se_sale_del_area(fuente):
    d = DetalleParaEtiqueta("a", (100.0, 25.0, 300.0, 100.0), 50.0)
    (t,), avisos = colocar_etiquetas([d], AREA, [], fuente)
    assert avisos == []
    assert t.lineas[0].base_mm[1] == pytest.approx(103.0)


def test_no_se_monta_sobre_otro_dibujo_un_elemento_ni_otra_etiqueta(fuente):
    a = DetalleParaEtiqueta("a", (100.0, 300.0, 300.0, 400.0), 50.0)
    b = DetalleParaEtiqueta("b", (100.0, 200.0, 300.0, 296.0), 50.0)  # justo debajo de a
    rosa = ("rosa_vientos", (180.0, 403.0, 220.0, 450.0))  # justo encima de a
    textos, avisos = colocar_etiquetas([a, b], AREA, [rosa], fuente)
    assert [t.ruta for t in textos] == ["etiqueta_escala.b"]
    assert avisos == [
        "Advertencia: no se dibujó la etiqueta «ESC: 1:50» del detalle 'a': no cabe a 3 mm de "
        "su dibujo (debajo: se monta sobre el dibujo de 'b'; encima: se monta sobre "
        "'rosa_vientos'). Mueva el detalle o ponga \"etiqueta_escala\": false."]
    # Dos detalles con el mismo dibujo en X, uno sobre otro: la segunda etiqueta no pisa la 1.ª.
    c = DetalleParaEtiqueta("c", (100.0, 100.0, 300.0, 150.0), 50.0)
    # d: debajo se sale del área (24 - 5,5 < 22,7) y encima (95 a 97,5) pisa la de c (94,5 a 97).
    d = DetalleParaEtiqueta("d", (100.0, 24.0, 300.0, 92.0), 50.0)
    textos, avisos = colocar_etiquetas([c, d], AREA, [], fuente)
    assert [t.ruta for t in textos] == ["etiqueta_escala.c"]
    assert "encima: se monta sobre la etiqueta de 'c'" in avisos[0]


def test_sin_etiqueta_si_el_plano_lo_pide(fuente):
    d = DetalleParaEtiqueta("a", (100.0, 200.0, 300.0, 260.0), 50.0, con_etiqueta=False)
    assert colocar_etiquetas([d], AREA, [], fuente) == ([], [])
