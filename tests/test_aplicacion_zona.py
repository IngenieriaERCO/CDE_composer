"""Vista previa de una zona del Model Space desde la aplicación del editor (trabajador falso)."""

import pytest
from conftest import comando_falso
from test_aplicacion_editor import armar, cargado, esperar_tarea  # noqa: F401 (armar: fixture)

from componedor.aplicacion_editor import ErrorAplicacion

MODELO = {"bounds": [0.0, 0.0, 1000.0, 500.0],
          "capas": [{"name": "0", "entities": 40}, {"name": "COTAS", "entities": 6},
                    {"name": "OCULTA", "entities": 2, "cad_state": "apagada"}],
          "grupos": [{"number": 1, "box": [0.0, 0.0, 100.0, 50.0], "entities": 40},
                     {"number": 2, "box": [900.0, 450.0, 1000.0, 500.0], "entities": 8}]}


def _terminada(app, r):
    foto = esperar_tarea(app, r["tarea"]["id"])
    assert foto["estado"] == "terminada", foto["error"]
    return foto["resultado"]


def test_todo_el_model_space_con_sus_grupos(armar, tmp_path):  # noqa: F811
    app, _ = cargado(armar, tmp_path, modelo=MODELO)
    r = app.pedir_previa_zona()
    assert r["tarea"]["tipo"] == "previa_zona"
    assert app.canal.tarea(r["tarea"]["id"]).datos == {
        "session": "s-1", "zone": None, "layers": None, "exclude_layers": None, "scale": None,
        "long_side_px": 1500, "include_hidden_layers": None}
    previa = _terminada(app, r)
    assert [g["numero"] for g in previa["grupos"]] == [1, 2]
    assert previa["vista"] == [0.0, 0.0, 1000.0, 500.0] and previa["zona"] is None
    assert previa["px"] == [1500, 750] and "png" not in previa
    assert previa["url"] == f"/api/previas/{r['tarea']['id']}"
    assert app.png_previa(r["tarea"]["id"]).startswith(b"\x89PNG")


def test_un_grupo_y_una_zona_con_capas_excluidas_y_escala(armar, tmp_path):  # noqa: F811
    app, _ = cargado(armar, tmp_path, modelo=MODELO)
    grupo = _terminada(app, app.pedir_previa_zona(vista=[0, 0, 100, 50]))
    assert grupo["grupos"] == [] and grupo["vista"] == [0.0, 0.0, 100.0, 50.0]
    # zona de 2 × 1 m a 1:50 = 40 × 20 mm; página con los márgenes de load (5 mm)
    zona = _terminada(app, app.pedir_previa_zona(zona=[10, 10, 12, 11], vista=[0, 0, 100, 50],
                                                 excluir=["cotas"], escala=50))
    assert zona["papel"] == {"contenido_mm": pytest.approx([40.0, 20.0]),
                             "pagina_mm": pytest.approx([50.0, 30.0]), "margen_mm": 5.0,
                             "cabe_a1": True}
    assert zona["escala"] == "1:50"
    assert {f["nombre"]: f["se_ve"] for f in zona["filas_capas"]} == {
        "0": True, "COTAS": False, "OCULTA": False}
    assert zona["entidades"] == {"en_vista": 48, "dibujadas": 40, "sin_caja": 0}


def test_solo_estas_capas_y_capa_que_no_existe(armar, tmp_path):  # noqa: F811
    app, _ = cargado(armar, tmp_path, modelo=MODELO)
    solo = _terminada(app, app.pedir_previa_zona(zona=[0, 0, 5, 5], capas=["0"]))
    assert [f["nombre"] for f in solo["filas_capas"] if f["se_ve"]] == ["0"]
    foto = esperar_tarea(app, app.pedir_previa_zona(zona=[0, 0, 5, 5],
                                                    capas=["NO_EXISTE"])["tarea"]["id"])
    assert foto["estado"] == "fallida" and foto["error"]["codigo"] == "BAD_REQUEST"


def test_pedidos_que_no_se_pueden_hacer(armar, tmp_path):  # noqa: F811
    with pytest.raises(ErrorAplicacion, match="Todavía no se cargó ningún DXF"):
        armar().pedir_previa_zona()
    app, _ = cargado(armar, tmp_path, modelo=MODELO)
    for kw, texto in (({"zona": [1, 2, 3]}, "«zona» debe ser"),
                      ({"capas": ["0"], "excluir": ["COTAS"]}, "no las dos"),
                      ({"escala": -5}, "«escala»"),
                      ({"estilo": "x"}, "«estilo» debe ser")):
        with pytest.raises(ErrorAplicacion, match=texto) as e:
            app.pedir_previa_zona(**kw)
        assert e.value.estado_http == 400
    app.reiniciar()
    with pytest.raises(ErrorAplicacion, match="vuelva a cargarlo"):
        app.pedir_previa_zona()


def test_dos_pedidos_iguales_mientras_se_hace_son_una_tarea(armar, tmp_path):  # noqa: F811
    app, _ = cargado(armar, tmp_path, modelo=MODELO, previa_demora_s=0.3)
    r = app.pedir_previa_zona(zona=[0, 0, 5, 5])
    assert app.pedir_previa_zona(zona=[0, 0, 5, 5])["tarea"]["id"] == r["tarea"]["id"]
    otra = app.pedir_previa_zona(zona=[0, 0, 6, 5])
    assert otra["tarea"]["id"] != r["tarea"]["id"]
    _terminada(app, r)
    _terminada(app, otra)


def test_exportador_con_protocolo_1_0_no_sabe_de_zonas(armar, tmp_path):  # noqa: F811
    from conftest import dxf_falso

    ruta = dxf_falso(tmp_path / "obra.dxf", blocks=[{"name": "B1", "handle": "1A"}])
    app = armar(elegido=ruta, comando=comando_falso("--protocolo", "1.0"))
    assert esperar_tarea(app, app.elegir_y_cargar()["tarea"]["id"])["estado"] == "terminada"
    with pytest.raises(ErrorAplicacion, match="habla el protocolo 1.0") as e:
        app.pedir_previa_zona()
    assert e.value.estado_http == 409
