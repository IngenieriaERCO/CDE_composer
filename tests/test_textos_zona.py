"""La escala del dibujo de una zona: la orden `texts` del trabajador (protocolo 1.3, §4.3)."""

import time

import pytest
from conftest import comando_falso, dxf_falso
from test_aplicacion_editor import armar, cargado, esperar_tarea  # noqa: F401 (armar: fixture)

from componedor.aplicacion_editor import ErrorAplicacion
from componedor.previa_zona import PedidoZonaInvalido
from componedor.textos_zona import RespuestaTextosInvalida, leer_textos, pedido_textos
from componedor.trabajador import admite_textos

ZONA = [0.0, 0.0, 10.0, 10.0]
TEXTOS = [
    {"text": "SECCIÓN-PEDESTAL 0.40 X 0.40\nESC-1:10", "x": 2.0, "y": 1.0, "layer": "TEXTOS", "scales": ["1:10"]},
    {"text": "VISTA EN PLANTA\nEsc: 1:20", "x": 30.0, "y": 5.0, "layer": "TEXTOS", "scales": ["1:20"]},
    {"text": "PERFIL ESC. H 1:1000 V 1:100", "x": 60.0, "y": 5.0, "layer": "PERFIL", "scales": ["1:1000"], "axis": "H"},
    {"text": "PERFIL ESC. H 1:1000 V 1:100", "x": 60.0, "y": 5.0, "layer": "PERFIL", "scales": ["1:100"], "axis": "V"},
    {"text": "Cota 1:2 (pendiente)", "x": 3.0, "y": 3.0, "layer": "0", "scales": []},
]
MODELO = {"bounds": [0.0, 0.0, 100.0, 20.0], "capas": [{"name": "0"}, {"name": "TEXTOS"}, {"name": "PERFIL"}],
          "textos": TEXTOS}


# --- pedido y respuesta, sin trabajador ---------------------------------------------------

def test_pedido():
    assert pedido_textos("s-1", ZONA, None, ["COTAS"]) == {
        "session": "s-1", "zone": ZONA, "layers": None, "exclude_layers": ["COTAS"],
        "include_hidden_layers": None, "max_texts": 200}
    for args, texto in (((None,), "Falta «zona»"), (([1, 2, 3],), "«zona» debe ser"),
                        ((ZONA, ["0"], ["COTAS"]), "no las dos")):
        with pytest.raises(PedidoZonaInvalido, match=texto):
            pedido_textos("s-1", *args)


def _respuesta(candidatos, propuesta=None):
    return {"total": 4, "scale_candidates": candidatos, "proposed_scale": propuesta, "seconds": 0.2}


def _c(escala, veces, eje=None, texto="ESC 1:10", capa="TEXTOS"):
    return {"scale": escala, "denominator": float(escala.split(":")[1]), "axis": eje, "count": veces,
            "sources": [{"text": texto, "x": 1.0, "y": 2.0, "layer": capa, "handle": "1A"}] * 5}


def test_leer_una_varias_ninguna():
    una = leer_textos(_respuesta([_c("1:10", 1)], "1:10"))
    assert una["propuesta"] == 10.0 and una["total"] == 4
    assert una["candidatos"] == [{"escala": "1:10", "n": 10.0, "eje": None, "veces": 1, "fuentes": [
        {"texto": "ESC 1:10", "x": 1.0, "y": 2.0, "capa": "TEXTOS"}] * 3}]  # hasta 3 fuentes
    varias = leer_textos(_respuesta([_c("1:10", 11), _c("1:20", 5)]))
    assert varias["propuesta"] is None and [c["n"] for c in varias["candidatos"]] == [10.0, 20.0]
    ejes = leer_textos(_respuesta([_c("1:1000", 1, "H"), _c("1:100", 1, "V")]))
    assert ejes["propuesta"] is None and [c["eje"] for c in ejes["candidatos"]] == ["H", "V"]
    assert leer_textos(_respuesta([]))["candidatos"] == []
    # Una propuesta con eje, o con más de una escala, no se toma (el editor pide elegir).
    assert leer_textos(_respuesta([_c("1:10", 1, "H")], "1:10"))["propuesta"] is None


@pytest.mark.parametrize("datos, texto", [
    ([], "no es un objeto"),
    ({"scale_candidates": None}, "debe ser una lista"),
    ({"scale_candidates": [{"scale": "1:10"}]}, "debe traer scale, denominator y count"),
])
def test_respuesta_que_no_vale(datos, texto):
    with pytest.raises(RespuestaTextosInvalida, match=texto):
        leer_textos(datos)


@pytest.mark.parametrize("version, si", [("1.3", True), ("1.4", True), ("1.2", False), ("1.0", False), (None, False)])
def test_admite_textos(version, si):
    assert admite_textos({"protocol_version": version} if version else None) is si


# --- con el trabajador falso --------------------------------------------------------------

def _textos(app, **kw):
    foto = esperar_tarea(app, app.pedir_textos_zona(**kw)["tarea"]["id"])
    assert foto["estado"] == "terminada", foto["error"]
    return foto["resultado"]


def test_una_escala_la_propone(armar, tmp_path):  # noqa: F811
    app, _ = cargado(armar, tmp_path, modelo=MODELO)
    r = _textos(app, zona=ZONA)
    assert r["propuesta"] == 10.0
    assert r["candidatos"][0]["fuentes"][0]["texto"] == "SECCIÓN-PEDESTAL 0.40 X 0.40\nESC-1:10"
    assert app.canal.tarea(app.pedir_textos_zona(zona=ZONA)["tarea"]["id"]).datos["max_texts"] == 200


def test_varias_y_ejes_no_proponen(armar, tmp_path):  # noqa: F811
    app, _ = cargado(armar, tmp_path, modelo=MODELO)
    varias = _textos(app, zona=[0, 0, 40, 10])
    assert varias["propuesta"] is None and sorted(c["n"] for c in varias["candidatos"]) == [10.0, 20.0]
    ejes = _textos(app, zona=[50, 0, 70, 10])
    assert ejes["propuesta"] is None and {c["eje"] for c in ejes["candidatos"]} == {"H", "V"}


def test_con_la_capa_excluida_no_la_encuentra(armar, tmp_path):  # noqa: F811
    """El filtro de capas es el de la exportación: si la capa del texto se excluye, la escala no
    sale (el editor pide también sin filtro para avisar «hay ESC 1:10 en una capa excluida»)."""
    app, _ = cargado(armar, tmp_path, modelo=MODELO)
    assert _textos(app, zona=ZONA, excluir=["textos"])["candidatos"] == []
    assert _textos(app, zona=ZONA, capas=["0"])["candidatos"] == []
    assert _textos(app, zona=ZONA)["propuesta"] == 10.0


def test_pedidos_que_no_se_pueden_hacer(armar, tmp_path):  # noqa: F811
    with pytest.raises(ErrorAplicacion, match="Todavía no se cargó"):
        armar().pedir_textos_zona(zona=ZONA)
    app, _ = cargado(armar, tmp_path, modelo=MODELO)
    with pytest.raises(ErrorAplicacion) as e:
        app.pedir_textos_zona(zona=[1, 2])
    assert e.value.estado_http == 400


def test_exportador_1_2_no_lee_la_escala(armar, tmp_path):  # noqa: F811
    ruta = dxf_falso(tmp_path / "obra.dxf", blocks=[{"name": "B1", "handle": "1A"}], modelo=MODELO)
    app = armar(elegido=ruta, comando=comando_falso("--protocolo", "1.2"))
    assert esperar_tarea(app, app.elegir_y_cargar()["tarea"]["id"])["estado"] == "terminada"
    time.sleep(0.1)
    with pytest.raises(ErrorAplicacion, match="no lee la escala escrita en el dibujo") as e:
        app.pedir_textos_zona(zona=ZONA)
    assert e.value.estado_http == 409
