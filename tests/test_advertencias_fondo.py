"""Advertencias de `componer` con paquetes con y sin fondo de página (sintéticos).

Paquete: página 260 x 120 mm; dibujo X +37,3..+237,3, Y +21,3..+101,3 (relativo a la
página). Rosa de la plantilla: X 612..652, Y 51..91. Lo que tapa es el detalle de ENCIMA
(el que va después en el plano).
"""

import json

import pytest

from componedor.advertencias import (
    PLANTILLAS,
    clave_sobre_elemento,
    clave_traslape_detalles,
    texto_advertencia,
)
from componedor.componer import componer_plano
from componedor.plano import leer_plano
from conftest import crear_paquete_real, crear_plantilla_sintetica, escribir_formato

ROSA = [612.0, 51.0, 652.0, 91.0]


@pytest.fixture
def entorno(tmp_path):
    plantilla = crear_plantilla_sintetica(tmp_path / "rotulo.pdf", elementos_mm=[ROSA])
    escribir_formato(tmp_path / "formato.json", plantilla=plantilla,
                     elementos_plantilla=[{"nombre": "rosa_vientos", "rect_mm": ROSA}])
    crear_paquete_real(tmp_path / "input", "con")  # paquete antiguo, con fondo
    crear_paquete_real(tmp_path / "input", "sin", sin_fondo=True)  # paquete nuevo
    return tmp_path


def _componer(carpeta, detalles):
    plano = carpeta / "plano.json"
    plano.write_text(json.dumps({"version": 1, "formato": "formato.json", "detalles": [
        {"id": i, "manifiesto": f"input/{p}.manifest.json", "posicion_mm": pos}
        for i, p, pos in detalles]}), encoding="utf-8")
    return componer_plano(leer_plano(plano), carpeta / "p.pdf", sobrescribir=True)


def test_textos_nuevos_no_mencionan_el_fondo():
    assert texto_advertencia("dibujos_sin_fondo", 12.34, 5, a="d1", b="d2") == (
        "ADVERTENCIA FUERTE: los DIBUJOS de 'd1' y 'd2' se traslapan (12.3 x 5.0 mm): en el "
        "plano sus líneas quedarán superpuestas.")
    assert texto_advertencia("dibujo_sobre_elemento_sin_fondo", 3, 4, a="d1",
                             elemento="rosa_vientos") == (
        "ADVERTENCIA MUY FUERTE: el dibujo 'd1' se monta sobre 'rosa_vientos' de la plantilla "
        "(3.0 x 4.0 mm): sus líneas quedarán encima.")
    for clave in ("dibujos_sin_fondo", "dibujo_sobre_elemento_sin_fondo"):
        assert "fondo" not in PLANTILLAS[clave]["texto"]
    assert PLANTILLAS["dibujos_sin_fondo"]["nivel"] == "fuerte"
    assert PLANTILLAS["dibujo_sobre_elemento_sin_fondo"]["nivel"] == "muy_fuerte"


@pytest.mark.parametrize("dibujos, paginas, fondo, esperado", [
    (True, True, True, "dibujos"), (True, True, False, "dibujos_sin_fondo"),
    (False, True, True, "paginas"), (False, True, False, None), (False, False, True, None),
])
def test_tabla_detalles(dibujos, paginas, fondo, esperado):
    assert clave_traslape_detalles(dibujos, paginas, fondo) == esperado


@pytest.mark.parametrize("dibujo, pagina, fondo, esperado", [
    (True, True, True, "dibujo_sobre_elemento"),
    (True, True, False, "dibujo_sobre_elemento_sin_fondo"),
    (False, True, True, "pagina_sobre_elemento"), (False, True, False, None),
    (False, False, False, None),
])
def test_tabla_elementos(dibujo, pagina, fondo, esperado):
    assert clave_sobre_elemento(dibujo, pagina, fondo) == esperado


def test_sin_fondo_traslape_solo_de_paginas_no_avisa(entorno):
    # Páginas X 30..290 y 280..540 (10 mm); dibujos 67,3..267,3 y 317,3..517,3: no se tocan.
    r = _componer(entorno, [("d1", "sin", [30, 300]), ("d2", "sin", [280, 300])])
    assert r.advertencias == []
    assert [c.tiene_fondo for c in r.detalles] == [False, False]


def test_sin_fondo_dibujos_traslapados(entorno):
    r = _componer(entorno, [("d1", "sin", [30, 300]), ("d2", "sin", [130, 320])])
    assert r.advertencias == [
        "ADVERTENCIA FUERTE: los DIBUJOS de 'd1' y 'd2' se traslapan (100.0 x 60.0 mm): en el "
        "plano sus líneas quedarán superpuestas."]


def test_solo_tapa_el_de_encima_si_tiene_fondo(entorno):
    paginas = [[30, 300], [280, 300]]  # solo se traslapan las páginas
    # El de encima (d2) sin fondo: no tapa nada, aunque el de abajo tenga fondo.
    assert _componer(entorno, [("d1", "con", paginas[0]), ("d2", "sin", paginas[1])]).advertencias == []
    # El de encima con fondo: su margen tapa una franja del de abajo (texto de siempre).
    r = _componer(entorno, [("d1", "sin", paginas[0]), ("d2", "con", paginas[1])])
    assert r.advertencias == [texto_advertencia("paginas", 10, 120, a="d1", b="d2")]


def test_dibujos_traslapados_depende_del_de_encima(entorno):
    pos = [[30, 300], [130, 320]]
    con_encima = _componer(entorno, [("d1", "sin", pos[0]), ("d2", "con", pos[1])])
    sin_encima = _componer(entorno, [("d1", "con", pos[0]), ("d2", "sin", pos[1])])
    assert con_encima.advertencias[0].endswith("tapa parte del dibujo de 'd1'.")
    assert sin_encima.advertencias[0].endswith("en el plano sus líneas quedarán superpuestas.")


def test_sin_fondo_sobre_la_rosa(entorno):
    # Solo la página toca la rosa: sin fondo no avisa.
    assert _componer(entorno, [("d1", "sin", [360, 40])]).advertencias == []
    # El dibujo se monta sobre la rosa.
    r = _componer(entorno, [("d1", "sin", [400, 40])])
    assert r.advertencias == [
        "ADVERTENCIA MUY FUERTE: el dibujo 'd1' se monta sobre 'rosa_vientos' de la plantilla "
        "(25.3 x 29.7 mm): sus líneas quedarán encima."]


def test_con_fondo_sigue_como_antes(entorno):
    r = _componer(entorno, [("d1", "con", [360, 40])])
    assert r.advertencias == [
        "ADVERTENCIA FUERTE: el detalle 'd1' tapa 'rosa_vientos' de la plantilla con su fondo "
        "blanco (8.0 x 40.0 mm), aunque su dibujo no lo toca."]
    assert r.detalles[0].tiene_fondo is True
