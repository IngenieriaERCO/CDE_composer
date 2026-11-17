"""Lo que hace el servidor del editor, sin HTTP: «Cargar DXF» con el trabajador falso."""

import threading
import time

import pytest
from conftest import ZONA_A1, comando_falso, dxf_falso

from componedor.aplicacion_editor import SIN_SECCION, AplicacionEditor, ErrorAplicacion
from componedor.canal_trabajador import FINALES
from componedor.configuracion import ConfigExportador


def esperar_tarea(app, id_tarea, segundos=20):
    fin = time.monotonic() + segundos
    while True:
        foto = app.tarea(id_tarea)
        if foto["estado"] in FINALES:
            return foto
        assert time.monotonic() < fin
        time.sleep(0.02)


@pytest.fixture
def armar(tmp_path):
    creadas = []

    def armar(elegido=None, comando=None, config=True):
        cfg = ConfigExportador(comando or comando_falso(), tmp_path / "trabajo") if config else None
        app = AplicacionEditor(tmp_path / "editor.html", ZONA_A1, cfg,
                               elegir=lambda inicial: elegido(inicial) if callable(elegido)
                               else elegido)
        creadas.append(app)
        return app

    yield armar
    for app in creadas:
        app.cerrar()


def test_sin_seccion_exportador(armar):
    app = armar(config=False)
    e = app.estado()
    assert e["exportador"] == {"disponible": False, "mensaje": SIN_SECCION, "trabajador": None}
    assert e["servidor"] is True and e["dxf"] is None and e["tarea"] is None
    with pytest.raises(ErrorAplicacion) as error:
        app.elegir_y_cargar()
    assert error.value.estado_http == 409 and error.value.mensaje == SIN_SECCION


def test_comando_que_no_existe(armar):
    app = armar(comando=("no-existe-xyz",))
    assert not app.estado()["exportador"]["disponible"]
    assert "No se encontró el comando «no-existe-xyz»" in app.motivo_sin_exportador()


def test_cargar_un_dxf_hasta_la_carpeta(armar, tmp_path):
    ruta = dxf_falso(tmp_path / "obras" / "GUAMO.dxf",
                     blocks=[{"name": "BLOQUE1", "size_cad": [957.18, 1350.019], "handle": "50CA"},
                             {"name": "Detalle", "size_cad": [10.0, 4.0], "handle": "51"}])
    vistos = []
    app = armar(elegido=lambda inicial: vistos.append(inicial) or ruta)
    assert app.estado()["exportador"]["disponible"] is True
    r = app.elegir_y_cargar()
    assert r["elegido"] == "GUAMO.dxf" and r["tarea"]["tipo"] == "cargar_dxf"
    # Lo que se pide a load: la ruta validada, el margen de la sesión y sin tabla de capas.
    assert app.canal.tarea(r["tarea"]["id"]).datos == {
        "dxf": str(ruta.resolve()), "units": None, "margin_mm": 5.0, "include_layers": False}
    foto = esperar_tarea(app, r["tarea"]["id"])
    assert foto["estado"] == "terminada", foto["error"]
    carpeta = foto["resultado"]
    assert carpeta["dxf"]["nombre"] == "GUAMO.dxf"
    assert [(b["nombre"], b["escala_sugerida"]) for b in carpeta["bloques"]] == [
        ("BLOQUE1", 5000), ("Detalle", 50)]
    e = app.estado()
    assert e["dxf"]["bloques"] == carpeta["bloques"] and e["dxf"]["sesion_activa"] is True
    assert e["tarea"]["id"] == r["tarea"]["id"]
    assert e["exportador"]["trabajador"]["estado"] == "listo"
    # El cuadro se abre la segunda vez en la carpeta del DXF anterior.
    esperar_tarea(app, app.elegir_y_cargar()["tarea"]["id"])
    assert vistos == [None, ruta.parent.resolve()]
    # Si el trabajador se reinicia, la carpeta se sigue viendo pero su sesión ya no existe.
    app.reiniciar()
    assert app.estado()["dxf"]["sesion_activa"] is False


def test_el_margen_de_componedor_json_va_en_load(armar, tmp_path):
    ruta = dxf_falso(tmp_path / "a.dxf", blocks=[{"name": "X", "size_cad": [31.0, 4.0]}])
    app = armar(elegido=ruta)
    app.config = ConfigExportador(comando_falso(), tmp_path / "trabajo", margen_mm=20.0)
    foto = esperar_tarea(app, app.elegir_y_cargar()["tarea"]["id"])
    assert foto["resultado"]["margen_mm"] == 20.0
    # 31 m a 1:50 = 620 mm + 2 × 20 = 660 mm > 639,7: ya no cabe a 1:50.
    assert foto["resultado"]["bloques"][0]["escala_sugerida"] == 100


def test_cancelado_en_el_cuadro(armar):
    app = armar(elegido=None)
    assert app.elegir_y_cargar() == {"elegido": None, "tarea": None}
    assert app.canal is None  # no se lanzó el trabajador


def test_ruta_elegida_que_no_es_dxf(armar, tmp_path):
    otro = tmp_path / "plano.pdf"
    otro.write_text("x")
    app = armar(elegido=otro)
    with pytest.raises(ErrorAplicacion) as e:
        app.elegir_y_cargar()
    assert e.value.estado_http == 400 and "no es un archivo .dxf" in e.value.mensaje


def test_no_se_cargan_dos_a_la_vez(armar, tmp_path):
    lento = dxf_falso(tmp_path / "lento.dxf", demora_s=0.5)
    app = armar(elegido=lento)
    r = app.elegir_y_cargar()
    with pytest.raises(ErrorAplicacion, match="Ya se está cargando un DXF"):
        app.elegir_y_cargar()
    assert app.cancelar(r["tarea"]["id"]) == {"cancelando": True}
    assert esperar_tarea(app, r["tarea"]["id"])["estado"] == "cancelada"


def test_un_solo_cuadro_abierto(armar, tmp_path):
    abierto, soltar = threading.Event(), threading.Event()

    def elegir(inicial):
        abierto.set()
        soltar.wait(5)

    app = armar(elegido=elegir)
    hilo = threading.Thread(target=app.elegir_y_cargar)
    hilo.start()
    abierto.wait(5)
    with pytest.raises(ErrorAplicacion, match="Ya hay un cuadro abierto"):
        app.elegir_y_cargar()
    soltar.set()
    hilo.join(5)


def test_respuesta_invalida_del_trabajador(armar, tmp_path):
    ruta = dxf_falso(tmp_path / "a.dxf", respuesta={"session": "s-1", "dxf": {"name": "a.dxf"}})
    app = armar(elegido=ruta)
    foto = esperar_tarea(app, app.elegir_y_cargar()["tarea"]["id"])
    assert foto["estado"] == "fallida" and foto["error"]["codigo"] == "RESPUESTA_INVALIDA"
    assert "no trae la lista «blocks»" in foto["error"]["mensaje"]
    assert app.estado()["dxf"] is None


def test_tarea_que_no_existe(armar):
    app = armar()
    for accion in (app.tarea, app.cancelar):
        with pytest.raises(ErrorAplicacion) as e:
            accion("t-7")
        assert e.value.estado_http == 404


def test_latido(armar):
    app = armar()
    app.ultimo_latido = 0.0
    assert app.latido() == {"ok": True}
    assert time.monotonic() - app.ultimo_latido < 5
