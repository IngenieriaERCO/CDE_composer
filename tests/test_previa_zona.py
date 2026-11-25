"""Vista previa de una zona del Model Space: lo que manda el editor y la respuesta (§4.1)."""

import re

import pytest

from componedor.previa_dxf import PreviaInvalida
from componedor.previa_zona import (
    PedidoZonaInvalido,
    leer_previa_zona,
    pedido_previa_zona,
)
from componedor.trabajador import admite_zonas


def test_pedido_de_todo_el_model_space():
    assert pedido_previa_zona("s-1") == {
        "session": "s-1", "zone": None, "layers": None, "exclude_layers": None, "scale": None,
        "long_side_px": 1500, "include_hidden_layers": None}


def test_pedido_de_una_zona_con_vista_capas_excluidas_y_escala():
    d = pedido_previa_zona("s-1", [1, 2, 3, 4], [0, 0, 10, 10], None, ["COTAS", "TEXTO*"], 50)
    assert d["zone"] == [1.0, 2.0, 3.0, 4.0] and d["view"] == [0.0, 0.0, 10.0, 10.0]
    assert d["layers"] is None and d["exclude_layers"] == ["COTAS", "TEXTO*"]
    assert d["scale"] == 50 and isinstance(d["scale"], int)
    assert "view" not in pedido_previa_zona("s-1", [1, 2, 3, 4])  # sin vista: no se manda


@pytest.mark.parametrize("args, texto", [
    (([1, 2, 3],), "«zona» debe ser [xmin, ymin, xmax, ymax]"),
    (([1, 2, 1, 4],), "xmax > xmin"),
    (([1, 2, 3, True],), "«zona» debe ser"),
    ((None, [0, 0, float("nan"), 1]), "«vista» debe ser"),
    ((None, None, ["A,B"]), "lleva una coma"),
    ((None, None, [""]), "«capas» debe ser una lista"),
    ((None, None, "COTAS"), "«capas» debe ser una lista"),
    ((None, None, ["0"], ["COTAS"]), "no las dos"),
    ((None, None, None, None, 0), "«escala» debe ser el N de 1:N"),
    ((None, None, None, None, 50.5), "«escala»"),
    ((None, None, None, None, "1:50"), "«escala»"),
    ((None, None, None, None, 100001), "«escala»"),
])
def test_pedido_que_no_vale(args, texto):
    with pytest.raises(PedidoZonaInvalido, match=re.escape(texto)):
        pedido_previa_zona("s-1", *args)


@pytest.mark.parametrize("listo, si", [
    ({"protocol_version": "1.1"}, True), ({"protocol_version": "1.12"}, True),
    ({"protocol_version": "1.0"}, False), ({"protocol_version": "2.1"}, False),
    ({"protocol_version": "1"}, False), ({}, False), (None, False),
])
def test_admite_zonas(listo, si):
    assert admite_zonas(listo) is si


# --- respuesta ----------------------------------------------------------------------------

@pytest.fixture
def respuesta(tmp_path):
    png = tmp_path / "previews" / "h" / "ms-0123456789_1500_visible.png"
    png.parent.mkdir(parents=True)
    png.write_bytes(b"\x89PNG")
    return tmp_path / "previews", {
        "png": str(png), "kind": "zone", "ref": None, "handle": None, "px": [1500, 1455],
        "bounds": {"min": [1000.0, 2000.0], "max": [1000.67, 2000.65]},
        "cad_to_px": [2209.55, 0.0, 0.0, -2209.55, -2209540.0, 4420546.5],
        "zone": [1000.0, 2000.0, 1000.67, 2000.65], "view": [1000.0, 2000.0, 1000.67, 2000.65],
        "layers": [], "exclude_layers": ["EDD_COTAS"],
        "layer_rows": [{"name": "EDD_COTAS", "entities_in_view": 6, "cad_state": None,
                        "shown": False},
                       {"name": "OCULTA", "entities_in_view": 2, "cad_state": "congelada",
                        "shown": False}],
        "entities": {"in_view": 25, "drawn": 19, "without_bounds": 3}, "groups": [],
        "scale": "1:10",
        "paper": {"content_mm": [67.0, 65.0], "page_mm": [77.0, 75.0], "margin_mm": 5.0,
                  "fits_a1": True},
        "omitted": {"3DSOLID": 0, "REGION": 0}, "include_hidden_layers": None,
        "plot_style": None, "print_transparency": True, "cached": False, "seconds": 3.2}


def test_lee_la_respuesta_del_contrato(respuesta):
    carpeta, datos = respuesta
    r = leer_previa_zona(datos, carpeta)
    assert r["zona"] == r["vista"] == [1000.0, 2000.0, 1000.67, 2000.65]
    assert r["excluir"] == ["EDD_COTAS"] and r["capas"] == []
    assert r["filas_capas"][1] == {"nombre": "OCULTA", "entidades": 2,
                                   "estado_cad": "congelada", "se_ve": False}
    assert r["entidades"] == {"en_vista": 25, "dibujadas": 19, "sin_caja": 3}
    assert r["escala"] == "1:10"
    assert r["papel"] == {"contenido_mm": [67.0, 65.0], "pagina_mm": [77.0, 75.0],
                          "margen_mm": 5.0, "cabe_a1": True}
    assert r["grupos"] == [] and r["px"] == [1500, 1455] and r["png"].name.startswith("ms-")
    assert r["preparada"] is False  # sin «prepared» (exportador 1.1)
    datos["prepared"] = True
    assert leer_previa_zona(datos, carpeta)["preparada"] is True


def test_lee_los_grupos_y_sin_papel(respuesta):
    carpeta, datos = respuesta
    datos.update(zone=None, scale=None, paper=None, groups=[
        {"number": 1, "box": [0, 0, 10, 5], "entities": 900},
        {"number": 2, "box": [500000, 0, 500010, 5], "entities": 12}])
    r = leer_previa_zona(datos, carpeta)
    assert r["papel"] is None and r["zona"] is None
    assert r["grupos"][1] == {"numero": 2, "caja": [500000.0, 0.0, 500010.0, 5.0],
                              "entidades": 12}


@pytest.mark.parametrize("cambio, texto", [
    ({"kind": None}, "no es de una zona"),
    ({"bounds": None, "cad_to_px": None}, "no hay nada que dibujar"),
    ({"layer_rows": None}, "«layer_rows» debe ser una lista"),
    ({"layer_rows": [{"name": "0"}]}, "cada fila de «layer_rows»"),
    ({"groups": [{"number": 1, "entities": 3}]}, "no trae «box»"),
    ({"entities": {"in_view": 1}}, "«entities» debe traer"),
    ({"paper": {"content_mm": [1, 2]}}, "«paper» debe traer"),
    ({"zone": [1, 2]}, "«zone» debe ser"),
])
def test_respuesta_que_no_cumple_el_contrato(respuesta, cambio, texto):
    carpeta, datos = respuesta
    datos.update(cambio)
    with pytest.raises(PreviaInvalida, match=texto):
        leer_previa_zona(datos, carpeta)
