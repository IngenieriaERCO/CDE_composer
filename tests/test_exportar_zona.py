"""Exportar una ZONA del Model Space (Fase 10c) con el trabajador falso: el pedido, el nombre
(escrito o Zona_NN generado), la caché, la verificación de la zona, el paquete viejo a
_para_borrar, el catálogo del editor y la composición con máscara."""

import json

import pymupdf
import pytest
from conftest import ZONA_A1, comando_falso, dxf_falso, escribir_formato
from test_exportar_editor import BLOQUES, esperar

from componedor.aplicacion_editor import AplicacionEditor, ErrorAplicacion
from componedor.componer import componer_plano
from componedor.configuracion import ConfigExportador
from componedor.exportar_dxf import Pedido, motivos_de_otro_pedido
from componedor.exportar_zona import (
    leer_zona,
    nombre_de_zona,
    nombre_libre,
    pagina_de_zona,
    trabajo_de_zona,
)
from componedor.plano import leer_plano
from componedor.previa_zona import PedidoZonaInvalido

MODELO = {"capas": [{"name": "0"}, {"name": "COTAS"}, {"name": "_001_ACERO"}]}
ZONA = [100.0, 200.0, 102.0, 201.0]  # 2 × 1 m: a 1:50, 40 × 20 mm; página 50 × 30 mm


@pytest.fixture
def armar(tmp_path):
    creadas = []

    def armar(comando=None, **spec):
        spec.setdefault("blocks", BLOQUES)
        spec.setdefault("modelo", MODELO)
        ruta = dxf_falso(tmp_path / "obras" / "PRGD prueba.dxf", **spec)
        cfg = ConfigExportador(comando or comando_falso(), tmp_path / "trabajo", 5.0, None,
                               tmp_path / "data" / "input" / "dxf", tmp_path / "_para_borrar")
        app = AplicacionEditor(tmp_path / "editor" / "editor.html", ZONA_A1, cfg,
                               elegir=lambda inicial: ruta)
        creadas.append(app)
        foto = esperar(app, app.elegir_y_cargar()["tarea"]["id"])
        assert foto["estado"] == "terminada", foto["error"]
        return app

    yield armar
    for app in creadas:
        app.cerrar()


def _hecha(app, r):
    foto = esperar(app, r["tarea"]["id"])
    assert foto["estado"] == "terminada", foto["error"]
    return foto["resultado"]


# --- exportar_zona.py (sin trabajador) ----------------------------------------------------

def test_nombre_de_zona():
    assert nombre_de_zona(None) is None and nombre_de_zona("  ") is None
    assert nombre_de_zona(" Sección VF ") == "Seccion_VF"
    for malo, texto in ((5, "debe ser un texto"), ("¿¡!?", "ninguna letra"),
                        ("x" * 41, "muy largo")):
        with pytest.raises(PedidoZonaInvalido, match=texto):
            nombre_de_zona(malo)


def test_nombre_libre_salta_lo_publicado_y_lo_reservado(tmp_path):
    assert nombre_libre(tmp_path / "no_existe") == "Zona_01"
    (tmp_path / "Zona_01_1-50.manifest.json").write_text("{}", encoding="utf-8")
    (tmp_path / "zona_02_1-20_t.pdf").write_bytes(b"%PDF")  # sin distinguir mayúsculas
    (tmp_path / "Zona_03.txt").write_text("", encoding="utf-8")  # no es un paquete «_1-N»
    assert nombre_libre(tmp_path) == "Zona_03"
    assert nombre_libre(tmp_path, ["ZONA_03"]) == "Zona_04"


def test_leer_zona_y_trabajo():
    z = leer_zona(ZONA, None, ["COTAS"], 50)
    assert z == {"zona": ZONA, "capas": [], "excluir": ["COTAS"], "n": 50}
    assert pagina_de_zona(ZONA, 1000.0, 50, 5.0) == pytest.approx((50.0, 30.0))
    assert trabajo_de_zona(z, "Z_1-50") == {
        "job": "z1", "zone": ZONA, "layers": None, "exclude_layers": ["COTAS"],
        "scale": "1:50", "package": "Z_1-50"}
    for args, texto in (((None, None, None, 50), "Falta «zona»"),
                        ((ZONA, None, None, None), "Falta «escala»"),
                        ((ZONA, ["0"], ["COTAS"], 50), "no las dos")):
        with pytest.raises(PedidoZonaInvalido, match=texto):
            leer_zona(*args)


def test_pedido_de_zona_compara_ventana_y_capas():
    pedido = Pedido("ab" * 32, "", 50.0, 5.0, (50.0, 30.0), zona=tuple(ZONA),
                    excluir=("COTAS",))
    datos = {"source": {"dxf_sha256": "ab" * 32, "block_name": "Model_Space",
                        "reference": {"handle": "112"}},
             "selection": {"kind": "modelspace", "window": ZONA, "layers": [],
                           "exclude_layers": ["cotas"]},
             "scale": {"denominator": 50}, "pdf": {"margin_mm": 5.0, "page_size_mm": [50, 30]},
             "options": {}}
    assert motivos_de_otro_pedido(datos, pedido) == []  # el handle no cuenta en una zona
    datos["selection"]["window"] = [100.0, 200.0, 102.5, 201.0]
    datos["selection"]["exclude_layers"] = []
    motivos = motivos_de_otro_pedido(datos, pedido)
    assert any("es de otra zona" in m for m in motivos)
    assert any("otras capas excluidas" in m for m in motivos)
    datos["source"]["block_name"] = "BLOQUE1"
    assert "no es una zona del Model Space" in motivos_de_otro_pedido(datos, pedido)


# --- con el trabajador falso --------------------------------------------------------------

def test_exportar_una_zona_con_nombre(armar, tmp_path):
    app = armar()
    r = app.exportar_zona(ZONA, excluir=["COTAS"], escala=50, nombre="Sección VF",
                          centro_mm=[300.0, 300.0])
    salida = tmp_path / "data" / "input" / "dxf" / "PRGD_prueba"
    assert app.canal.tarea(r["tarea"]["id"]).datos["jobs"] == [
        {"job": "z1", "zone": ZONA, "layers": None, "exclude_layers": ["COTAS"],
         "scale": "1:50", "package": "Seccion_VF_1-50"}]
    res = _hecha(app, r)
    assert res["tipo"] == "zona" and res["nombre"] == "Seccion_VF"
    assert res["nombre_generado"] is False and res["handle"] is None
    assert res["zona"] == ZONA and res["excluir"] == ["COTAS"] and res["capas"] == []
    assert res["manifiesto"] == "../data/input/dxf/PRGD_prueba/Seccion_VF_1-50.manifest.json"
    assert (salida / "Seccion_VF_1-50.pdf").is_file()
    # El centro de la zona queda en centro_mm (página 50 × 30, centrada).
    assert res["posicion_mm"] == pytest.approx([275.0, 285.0])
    # «Detalles disponibles»: la entrada de catálogo, también para el editor que se recarga.
    d = res["detalle"]
    assert d["bloque"] == "Model_Space" and d["escala"] == 50.0 and d["cabe"] is True
    assert d["tamano_pagina_mm"] == pytest.approx([50.0, 30.0])
    assert d["limites_dibujo_mm"] == pytest.approx([5.0, 5.0, 45.0, 25.0])  # lo que se ve
    assert app.exportados() == {"detalles": [d]}


def test_nombre_vacio_genera_zona_01_02(armar):
    app = armar()
    a = _hecha(app, app.exportar_zona(ZONA, escala=50))
    b = _hecha(app, app.exportar_zona([0, 0, 1, 1], escala=50, nombre=""))
    assert (a["nombre"], a["nombre_generado"], a["paquete"]) == ("Zona_01", True, "Zona_01_1-50")
    assert (b["nombre"], b["nombre_generado"]) == ("Zona_02", True)
    # Con su nombre (como la guardará el plano), la misma zona sale de la caché.
    c = _hecha(app, app.exportar_zona(ZONA, escala=50, nombre="Zona_01"))
    assert c["en_cache"] is True and c["nombre_generado"] is False


def test_dos_zonas_generadas_a_la_vez_no_toman_el_mismo_nombre(armar):
    app = armar(export_demora_s=0.05)
    r1 = app.exportar_zona(ZONA, escala=50)
    r2 = app.exportar_zona([0, 0, 1, 1], escala=50)
    assert {_hecha(app, r1)["nombre"], _hecha(app, r2)["nombre"]} == {"Zona_01", "Zona_02"}


def test_otras_capas_no_salen_de_la_cache_y_el_viejo_va_a_para_borrar(armar, tmp_path):
    app = armar()
    _hecha(app, app.exportar_zona(ZONA, escala=50, nombre="Z"))
    otra = _hecha(app, app.exportar_zona(ZONA, escala=50, nombre="Z", capas=["0"]))
    assert otra["en_cache"] is False and otra["capas"] == ["0"]
    assert len(otra["movidos"]) == 3 and all("_para_borrar" in m for m in otra["movidos"])


def test_paquete_de_otra_ventana_no_pasa_la_verificacion(armar, tmp_path):
    app = armar(zona_otra_ventana=True)
    foto = esperar(app, app.exportar_zona(ZONA, escala=50, nombre="Z")["tarea"]["id"])
    assert foto["estado"] == "fallida"
    assert foto["error"]["codigo"] == "PAQUETE_NO_VALIDO"
    assert "es de otra zona" in foto["error"]["mensaje"]
    assert not (tmp_path / "data" / "input" / "dxf" / "PRGD_prueba" / "Z_1-50.pdf").exists()


def test_pedidos_de_zona_que_no_se_atienden(armar):
    app = armar()
    for kw, codigo, texto in (
            ({"escala": 50}, 400, "Falta «zona»"),
            ({"zona": ZONA}, 400, "Falta «escala»"),
            ({"zona": ZONA, "escala": 50, "nombre": "¿?"}, 400, "ninguna letra"),
            ({"zona": ZONA, "escala": 50, "centro_mm": [1]}, 400, "«centro_mm»"),
            ({"zona": [0, 0, 100, 100], "escala": 50}, 400, "no cabe en el área de dibujo"),
            ({"zona": ZONA, "escala": 50, "estilo": "x"}, 400, "«estilo» debe ser")):
        with pytest.raises(ErrorAplicacion, match=texto) as e:
            app.exportar_zona(**kw)
        assert e.value.estado_http == codigo
    foto = esperar(app, app.exportar_zona(ZONA, escala=50, capas=["NO_EXISTE"])["tarea"]["id"])
    assert foto["estado"] == "fallida" and foto["error"]["codigo"] == "BAD_REQUEST"


def test_exportador_1_0_no_exporta_zonas(armar):
    app = armar(comando=comando_falso("--protocolo", "1.0"))
    with pytest.raises(ErrorAplicacion, match="no sabe exportar zonas") as e:
        app.exportar_zona(ZONA, escala=50)
    assert e.value.estado_http == 409


def test_la_zona_exportada_se_compone_con_su_mascara(armar, tmp_path):
    """El PDF de la zona trae una línea que sale de la zona y de la página (la oculta la
    máscara): la verificación final de componer la mide recortada y el plano se compone."""
    app = armar()
    r = _hecha(app, app.exportar_zona(ZONA, escala=50, nombre="Seccion",
                                      centro_mm=[300.0, 300.0]))
    escribir_formato(tmp_path / "formato.json")
    plano = tmp_path / "editor" / "plano.json"
    plano.parent.mkdir(exist_ok=True)
    plano.write_text(json.dumps({"version": 1, "formato": "../formato.json", "detalles": [
        {"id": "Seccion", "manifiesto": r["manifiesto"],
         "posicion_mm": [round(v, 2) for v in r["posicion_mm"]]}]}), encoding="utf-8")
    resultado = componer_plano(leer_plano(plano), tmp_path / "plano.pdf")
    (colocado,) = resultado.detalles
    assert colocado.mascara == pytest.approx((280.0, 290.0, 320.0, 310.0))
    assert colocado.dibujo == pytest.approx((280.0, 290.0, 320.0, 310.0))
    with pymupdf.open(tmp_path / "plano.pdf") as doc:  # sigue siendo vector, nada rasterizado
        assert doc[0].get_images() == []


def test_sin_el_recorte_la_verificacion_final_fallaria(armar, tmp_path, monkeypatch):
    """La prueba de arriba no pasa por casualidad: sin recortar a la máscara, la línea que
    sale de la zona hace fallar la verificación final de componer."""
    from componedor import componer

    app = armar()
    r = _hecha(app, app.exportar_zona(ZONA, escala=50, nombre="Seccion"))
    monkeypatch.setattr(componer, "recortar_a_zona", lambda trazos, zona: trazos)
    escribir_formato(tmp_path / "formato.json")
    plano = tmp_path / "editor" / "plano.json"
    plano.parent.mkdir(exist_ok=True)
    plano.write_text(json.dumps({"version": 1, "formato": "../formato.json", "detalles": [
        {"id": "Seccion", "manifiesto": r["manifiesto"],
         "posicion_mm": [round(v, 2) for v in r["posicion_mm"]]}]}), encoding="utf-8")
    with pytest.raises(Exception, match="el dibujo quedó en"):
        componer_plano(leer_plano(plano), tmp_path / "plano.pdf")
