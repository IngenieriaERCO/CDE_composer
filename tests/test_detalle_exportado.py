"""Entrada del catálogo del editor para un paquete recién exportado: la misma forma que la del
catálogo que arma datos_editor al generar el editor (y que ahora mira las subcarpetas)."""

import pytest
from conftest import ZONA_A1, crear_paquete_real, escribir_formato

from componedor.datos_editor import construir_datos_editor
from componedor.detalle_exportado import detalle_para_editor, ruta_para_el_editor
from componedor.importador import importar_paquete


@pytest.fixture
def carpeta(tmp_path):
    escribir_formato(tmp_path / "formato.json")
    crear_paquete_real(tmp_path / "input", "suelto", sin_fondo=True)
    crear_paquete_real(tmp_path / "input" / "dxf" / "GUAMO", "BLOQUE1_1-5000", sin_fondo=True)
    crear_paquete_real(tmp_path / "input" / "dxf" / "GUAMO" / ".cde-tmp-77", "a_medias")
    (tmp_path / "editor").mkdir()
    return tmp_path


def test_el_editor_ve_los_paquetes_exportados_y_no_los_temporales(carpeta):
    datos, _ = construir_datos_editor(carpeta / "input", carpeta / "formato.json",
                                      carpeta / "editor")
    assert [d["manifiesto"] for d in datos["detalles"]] == [
        "../input/suelto.manifest.json", "../input/dxf/GUAMO/BLOQUE1_1-5000.manifest.json"]
    assert datos["rechazados"] == []


def test_misma_forma_que_el_catalogo(carpeta):
    datos, _ = construir_datos_editor(carpeta / "input", carpeta / "formato.json",
                                      carpeta / "editor")
    del_catalogo = datos["detalles"][1]
    manifiesto = carpeta / "input" / "dxf" / "GUAMO" / "BLOQUE1_1-5000.manifest.json"
    nuevo = detalle_para_editor(importar_paquete(manifiesto), "BLOQUE1_1-5000",
                                carpeta / "editor", ZONA_A1, max_px=200)
    assert set(nuevo) == set(del_catalogo)
    for clave in ("id", "manifiesto", "bloque", "escala", "tamano_pagina_mm", "limites_dibujo_mm",
                  "cabe", "tiene_fondo", "notas"):
        assert nuevo[clave] == pytest.approx(del_catalogo[clave]) if isinstance(
            nuevo[clave], list) else nuevo[clave] == del_catalogo[clave]
    m = nuevo["miniatura"]
    assert m["data_url"].startswith("data:image/png;base64,") and max(m["ancho_px"], m["alto_px"]) == 200


def test_ruta_para_el_editor(tmp_path):
    assert ruta_para_el_editor(tmp_path / "data" / "x.json", tmp_path / "editor") == "../data/x.json"
