"""Vista previa preparada en segundo plano (protocolo 1.2 del trabajador, §4.2).

El estado por sesión (preparacion_previa.py) y, con el trabajador falso, de punta a punta:
`load` lleva `prepare_preview` con el estilo del editor, los eventos llegan a `/api/estado`,
la falla se muestra y un trabajador 1.1 o 1.0 sigue funcionando (sin preparación)."""

import time

import pytest
from conftest import ZONA_A1, comando_falso, dxf_falso
from test_estilos_impresion import ctb

from componedor.aplicacion_editor import AplicacionEditor
from componedor.canal_trabajador import FINALES
from componedor.configuracion import ConfigExportador
from componedor.preparacion_previa import (
    FALLIDA,
    LISTA,
    PREPARANDO,
    PreparacionPrevia,
    pedido_preparar,
)


class Reloj:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


# --- el estado, sin trabajador ------------------------------------------------------------

def test_sin_nada_no_hay_estado():
    p = PreparacionPrevia()
    assert p.estado("s-1") is None and p.estado(None) is None
    p.al_cargar("s-1", None)  # load de un trabajador 1.0/1.1: no trae preview_preparation
    assert p.estado("s-1") is None


def test_avance_lista_y_tiempo():
    reloj = Reloj()
    p = PreparacionPrevia(reloj)
    p.al_cargar("s-1", {"state": "running", "stage": "boxes", "percent": 0.0})
    reloj.t += 12.0
    p.al_evento("preview_progress", {"session": "s-1", "stage": "draw", "percent": 61.4,
                                     "message": "Preparando la vista previa: 9 120 de 25 837"})
    e = p.estado("s-1")
    assert e["estado"] == PREPARANDO and e["porcentaje"] == 61.4 and e["etapa"] == "draw"
    assert e["mensaje"] == "Preparando la vista previa: 9 120 de 25 837"
    assert e["transcurrido_s"] == 12.0
    reloj.t += 8.0
    p.al_evento("preview_ready", {"session": "s-1", "seconds": 49.9, "print_transparency": False,
                                  "plot_style": {"name": "CTB_ERCO_derivada_PRGD.ctb", "sha256": "b4"}})
    reloj.t += 100.0  # lista: el tiempo ya no corre
    e = p.estado("s-1")
    assert e["estado"] == LISTA and e["porcentaje"] == 100.0 and e["segundos"] == 49.9
    assert e["transcurrido_s"] == 20.0
    assert e["estilo"] == {"ctb": "CTB_ERCO_derivada_PRGD.ctb", "transparencia": False}


def test_eventos_de_otra_sesion_y_desconocidos():
    p = PreparacionPrevia()
    p.al_cargar("s-2", {"state": "running"})
    p.al_evento("preview_ready", {"session": "s-1", "seconds": 1})  # de una sesión vieja
    p.al_evento("otro_evento", {"session": "s-2"})
    p.al_evento("preview_ready", {"seconds": 1})  # sin sesión
    assert p.estado("s-2")["estado"] == PREPARANDO
    assert p.estado("s-1")["estado"] == LISTA  # se guarda, pero el editor pregunta por s-2


def test_falla_y_otra_preparacion_despues():
    p = PreparacionPrevia()
    p.al_evento("preview_progress", {"session": "s-1", "percent": 30})  # antes que load: vale
    p.al_cargar("s-1", {"state": "running"})
    assert p.estado("s-1")["porcentaje"] == 30.0
    p.al_evento("preview_failed", {"session": "s-1", "message": "MemoryError al indexar"})
    e = p.estado("s-1")
    assert e["estado"] == FALLIDA and e["error"] == "MemoryError al indexar"
    # Otra configuración pedida (otra CTB): vuelve a prepararse.
    p.al_evento("preview_progress", {"session": "s-1", "percent": 5, "stage": "boxes"})
    assert p.estado("s-1")["estado"] == PREPARANDO and p.estado("s-1")["error"] is None
    assert p.estado("s-1")["porcentaje"] == 5.0


def test_load_que_ya_dice_lista_o_fallida():
    p = PreparacionPrevia()
    p.al_cargar("s-1", {"state": "ready"})
    p.al_cargar("s-2", {"state": "failed", "error": "sin memoria"})
    p.al_cargar("s-3", {"state": "rara"})
    assert p.estado("s-1")["estado"] == LISTA
    assert p.estado("s-2")["estado"] == FALLIDA and p.estado("s-2")["error"] == "sin memoria"
    assert p.estado("s-3") is None


def test_pedido_preparar(tmp_path):
    assert pedido_preparar(None, True) == {"plot_style": None, "print_transparency": True}
    assert pedido_preparar(tmp_path / "x.ctb", False) == {
        "plot_style": str(tmp_path / "x.ctb"), "print_transparency": False}


# --- con el trabajador falso --------------------------------------------------------------

def esperar(app, id_tarea, segundos=20):
    fin = time.monotonic() + segundos
    while True:
        foto = app.tarea(id_tarea)
        if foto["estado"] in FINALES:
            return foto
        assert time.monotonic() < fin
        time.sleep(0.02)


def esperar_preparacion(app, estado, segundos=10):
    fin = time.monotonic() + segundos
    while True:
        p = app.estado()["dxf"]["preparacion"]
        if p is not None and p["estado"] == estado:
            return p
        assert time.monotonic() < fin, p
        time.sleep(0.05)


@pytest.fixture
def armar(tmp_path):
    creadas = []

    def armar(protocolo=None, estilo_impresion=None, transparencia=True, **spec):
        tabla = ctb(tmp_path / "ctb" / "CTB_ERCO.ctb", "CTB de prueba")
        ruta = dxf_falso(tmp_path / "obra.dxf", blocks=[{"name": "B1", "handle": "1A"}], **spec)
        comando = comando_falso("--protocolo", protocolo) if protocolo else comando_falso()
        cfg = ConfigExportador(comando, tmp_path / "trabajo", 5.0, None, tmp_path / "paquetes",
                               tmp_path / "_para_borrar", 100, tmp_path / "ctb", estilo_impresion,
                               transparencia)
        app = AplicacionEditor(tmp_path / "editor.html", ZONA_A1, cfg, elegir=lambda i: ruta)
        creadas.append(app)
        return app, tabla

    yield armar
    for app in creadas:
        app.cerrar()


def test_load_prepara_con_el_estilo_del_editor_y_avisa_cuando_esta_lista(armar):
    app, tabla = armar(preparar_s=0.6)
    r = app.elegir_y_cargar({"ctb": "CTB_ERCO.ctb", "transparencia": False})
    assert app.canal.tarea(r["tarea"]["id"]).datos["prepare_preview"] == {
        "plot_style": str(tabla), "print_transparency": False}
    assert esperar(app, r["tarea"]["id"])["estado"] == "terminada"
    p = app.estado()["dxf"]["preparacion"]
    assert p["estado"] == PREPARANDO  # el load responde enseguida; se prepara después
    lista = esperar_preparacion(app, LISTA)
    assert lista["porcentaje"] == 100.0 and lista["segundos"] == pytest.approx(0.6)
    assert lista["estilo"] == {"ctb": "CTB_ERCO.ctb", "transparencia": False}


def test_sin_estilo_usa_el_de_componedor_json(armar):
    app, tabla = armar(estilo_impresion="CTB_ERCO.ctb", transparencia=False)
    r = app.elegir_y_cargar()
    assert app.canal.tarea(r["tarea"]["id"]).datos["prepare_preview"] == {
        "plot_style": str(tabla), "print_transparency": False}


def test_volver_a_cargar_tambien_prepara(armar):
    app, _ = armar()
    esperar(app, app.elegir_y_cargar()["tarea"]["id"])
    esperar_preparacion(app, LISTA)
    r = app.recargar({"ctb": None, "transparencia": True})
    assert app.canal.tarea(r["tarea"]["id"]).datos["prepare_preview"] == {
        "plot_style": None, "print_transparency": True}
    esperar(app, r["tarea"]["id"])
    assert app.estado()["dxf"]["sesion"] == "s-2"
    assert esperar_preparacion(app, LISTA)["estilo"] == {"ctb": None, "transparencia": True}


def test_preview_failed_se_muestra_sin_romper_nada(armar):
    app, _ = armar(preparar_falla="MemoryError: no se pudo indexar")
    esperar(app, app.elegir_y_cargar()["tarea"]["id"])
    p = esperar_preparacion(app, FALLIDA)
    assert p["error"] == "MemoryError: no se pudo indexar"
    # Las vistas se siguen pidiendo como siempre.
    foto = esperar(app, app.pedir_previa_zona()["tarea"]["id"])
    assert foto["estado"] == "terminada", foto["error"]


@pytest.mark.parametrize("protocolo", ["1.1", "1.0"])
def test_exportador_1_1_o_1_0_sigue_funcionando(armar, protocolo):
    app, _ = armar(protocolo=protocolo)
    foto = esperar(app, app.elegir_y_cargar()["tarea"]["id"])
    assert foto["estado"] == "terminada", foto["error"]
    time.sleep(0.5)  # no llega ningún evento
    assert app.estado()["dxf"]["preparacion"] is None
    if protocolo == "1.1":
        assert esperar(app, app.pedir_previa_zona()["tarea"]["id"])["estado"] == "terminada"


def test_ctb_por_defecto_que_no_existe_no_impide_cargar(armar):
    """Preparar es una ayuda: con la CTB de componedor.json mal escrita, el DXF carga igual
    (sin prepare_preview) y el aviso sale después, al pedir una vista, como antes."""
    app, _ = armar(estilo_impresion="no_esta.ctb")
    r = app.elegir_y_cargar()
    assert "prepare_preview" not in app.canal.tarea(r["tarea"]["id"]).datos
    assert esperar(app, r["tarea"]["id"])["estado"] == "terminada"


def test_estilo_que_no_vale_al_cargar(armar):
    from componedor.aplicacion_editor import ErrorAplicacion

    app, _ = armar()
    with pytest.raises(ErrorAplicacion) as e:
        app.elegir_y_cargar({"ctb": "NO_EXISTE.ctb", "transparencia": True})
    assert e.value.estado_http == 400
