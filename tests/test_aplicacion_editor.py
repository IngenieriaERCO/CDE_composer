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

    def armar(elegido=None, comando=None, config=True, anonimos=100):
        cfg = (ConfigExportador(comando or comando_falso(), tmp_path / "trabajo",
                                anonimos_min_entidades=anonimos) if config else None)
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


ANONIMOS = [
    {"name": "Viga", "size_cad": [10.0, 4.0], "handle": "1A1", "visible_entities": 12},
    {"name": "*U76", "anonimo": True, "layer": "I1.M1.PV1", "handle": "12900",
     "size_cad": [10.0, 4.0], "visible_entities": 250},
    {"name": "*U80", "anonimo": True, "layer": "TABLAS", "handle": "13A0",
     "size_cad": [6.0, 3.0], "visible_entities": 60},
    {"name": "*U81", "anonimo": True, "layer": "COTAS", "handle": "13B0",
     "visible_entities": 3},
]


@pytest.mark.parametrize("umbral, ofrecidos, pequenos, mayor", [
    (100, ["Viga", "I1.M1.PV1_12900"], 2, 60),
    (50, ["Viga", "I1.M1.PV1_12900", "TABLAS_13A0"], 1, 3),
    (300, ["Viga"], 3, 250),
])
def test_el_umbral_de_anonimos_sale_de_la_configuracion(armar, tmp_path, umbral, ofrecidos,
                                                        pequenos, mayor):
    """El Componedor manda anonymous_min_entities (componedor.json); el trabajador ofrece los
    *U que llegan al umbral y deja los demás en omitted, que la carpeta solo cuenta."""
    ruta = dxf_falso(tmp_path / "PRGD.dxf", blocks=ANONIMOS,
                     omitted=[{"name": "XR", "occurrence": 1, "total_occurrences": 1,
                               "handle": "F", "reason": "XREF"}])
    app = armar(elegido=ruta, anonimos=umbral)
    tarea = app.elegir_y_cargar()["tarea"]
    assert app.canal.tarea(tarea["id"]).datos["anonymous_min_entities"] == umbral
    carpeta = esperar_tarea(app, tarea["id"])["resultado"]
    assert [b["etiqueta"] for b in carpeta["bloques"]] == ofrecidos
    assert [b["anonimo"] for b in carpeta["bloques"]] == [False] + [True] * (len(ofrecidos) - 1)
    assert carpeta["anonimos_min_entidades"] == umbral
    assert carpeta["anonimos_omitidos"] == {"cantidad": pequenos, "max_entidades_visibles": mayor}
    assert [o["nombre"] for o in carpeta["omitidos"]] == ["XR"]  # los *U pequeños no se listan


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
    # Lo que se pide a load: la ruta validada, el margen de la sesión, sin tabla de capas y el
    # umbral de los anónimos (100 por defecto).
    assert app.canal.tarea(r["tarea"]["id"]).datos == {
        "dxf": str(ruta.resolve()), "units": None, "margin_mm": 5.0, "include_layers": False,
        "anonymous_min_entities": 100,
        # Protocolo 1.2: preparar la vista previa con el estilo del editor (sin CTB aquí).
        "prepare_preview": {"plot_style": None, "print_transparency": True}}
    foto = esperar_tarea(app, r["tarea"]["id"])
    assert foto["estado"] == "terminada", foto["error"]
    carpeta = foto["resultado"]
    assert carpeta["dxf"]["nombre"] == "GUAMO.dxf"
    # La sugerida mide el dibujo y 1 mm de margen en la hoja (Fase 11), no la página con 5 mm.
    assert [(b["nombre"], b["escala_sugerida"]) for b in carpeta["bloques"]] == [
        ("BLOQUE1", 2500), ("Detalle", 20)]
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
    # La sugerida usa el margen de la HOJA (1 mm): 31 m a 1:50 = 620 + 2 = 622 mm ≤ 639,7.
    assert foto["resultado"]["bloques"][0]["escala_sugerida"] == 50
    # Con 20 mm en la hoja: 620 + 40 = 660 mm > 639,7: ya no cabe a 1:50; a 1:75 sí.
    app.margen_hoja_mm = 20.0
    foto = esperar_tarea(app, app.elegir_y_cargar()["tarea"]["id"])
    assert foto["resultado"]["bloques"][0]["escala_sugerida"] == 75


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


# --- vista previa y «Volver a cargar» (etapa 2) ----------------------------------------------

def cargado(armar, tmp_path, **spec):
    spec.setdefault("blocks", [{"name": "B1", "size_cad": [10.0, 4.0], "handle": "1A"},
                               {"name": "B2", "size_cad": [2.0, 1.0], "handle": "2B"}])
    ruta = dxf_falso(tmp_path / "obras" / "obra.dxf", **spec)
    app = armar(elegido=ruta)
    foto = esperar_tarea(app, app.elegir_y_cargar()["tarea"]["id"])
    assert foto["estado"] == "terminada", foto["error"]
    return app, ruta


def test_la_carpeta_dice_la_ruta_del_dxf_para_el_plano(armar, tmp_path):
    """Relativa a la carpeta del editor (el plano.json va ahí o en planos/), con «/»."""
    app, _ = cargado(armar, tmp_path)
    assert app.estado()["dxf"]["dxf"]["archivo_plano"] == "obras/obra.dxf"
    app.ruta_html = tmp_path / "editor" / "editor.html"
    assert app.archivo_para_plano(tmp_path / "data" / "x.dxf") == "../data/x.dxf"


def test_vista_previa_de_un_bloque(armar, tmp_path):
    app, _ = cargado(armar, tmp_path)
    r = app.pedir_previa("B1#1")
    assert r["tarea"]["tipo"] == "previa"
    # Al trabajador va el handle solo (el ref de un *U cambia entre sesiones).
    assert app.canal.tarea(r["tarea"]["id"]).datos == {
        "session": "s-1", "handle": "1A", "long_side_px": 1500, "include_hidden_layers": None}
    foto = esperar_tarea(app, r["tarea"]["id"])
    assert foto["estado"] == "terminada", foto["error"]
    previa = foto["resultado"]
    assert previa["ref"] == "B1#1" and previa["url"] == f"/api/previas/{r['tarea']['id']}"
    assert previa["px"] == [1500, 600] and previa["cad_a_px"][1:3] == [0.0, 0.0]
    assert "png" not in previa  # el editor nunca ve rutas del disco
    assert app.png_previa(r["tarea"]["id"]).startswith(b"\x89PNG")
    # Otra vez, ya terminada: otra tarea, que el trabajador responde desde su caché.
    otra = app.pedir_previa("B1#1")["tarea"]["id"]
    assert otra != r["tarea"]["id"]
    assert esperar_tarea(app, otra)["resultado"]["en_cache"] is True


def test_dos_pedidos_del_mismo_bloque_mientras_se_hace_son_una_tarea(armar, tmp_path):
    app, _ = cargado(armar, tmp_path, previa_demora_s=0.3)
    r = app.pedir_previa("B1#1")
    assert app.pedir_previa("B1#1")["tarea"]["id"] == r["tarea"]["id"]
    assert esperar_tarea(app, r["tarea"]["id"])["estado"] == "terminada"


def test_vista_previa_que_no_se_puede_pedir(armar, tmp_path):
    app = armar()
    with pytest.raises(ErrorAplicacion, match="Todavía no se cargó ningún DXF"):
        app.pedir_previa("B1#1")
    app, _ = cargado(armar, tmp_path)
    for ref, codigo, motivo in ((None, 400, "Falta «ref»"),
                                ("NO#1", 404, "no está en la carpeta")):
        with pytest.raises(ErrorAplicacion, match=motivo) as e:
            app.pedir_previa(ref)
        assert e.value.estado_http == codigo
    with pytest.raises(ErrorAplicacion) as e:
        app.png_previa("t-99")
    assert e.value.estado_http == 404
    app.reiniciar()  # otra sesión: hay que volver a cargar
    with pytest.raises(ErrorAplicacion, match="vuelva a cargarlo") as e:
        app.pedir_previa("B1#1")
    assert e.value.estado_http == 409


def test_png_fuera_de_la_carpeta_de_previas_no_se_entrega(armar, tmp_path):
    otro = tmp_path / "firmas" / "persona" / "firma.png"
    otro.parent.mkdir(parents=True)
    otro.write_bytes(b"\x89PNG secreto")
    app, _ = cargado(armar, tmp_path, respuesta_previa={
        "png": str(otro), "px": [10, 10], "bounds": {"min": [0, 0], "max": [1, 1]},
        "cad_to_px": [10, 0, 0, -10, 0, 10], "omitted": {}, "cached": False, "seconds": 0})
    r = app.pedir_previa("B1#1")
    foto = esperar_tarea(app, r["tarea"]["id"])
    assert foto["estado"] == "fallida" and "no está en la carpeta de vistas previas" in \
        foto["error"]["mensaje"]
    with pytest.raises(ErrorAplicacion):
        app.png_previa(r["tarea"]["id"])


def test_dxf_cambiado_y_volver_a_cargar(armar, tmp_path):
    app, ruta = cargado(armar, tmp_path)
    with pytest.raises(ErrorAplicacion, match="Todavía no se cargó"):
        armar().recargar()
    ruta.write_text(ruta.read_text(encoding="utf-8").replace("B2", "B3"), encoding="utf-8")
    foto = esperar_tarea(app, app.pedir_previa("B1#1")["tarea"]["id"])
    assert foto["estado"] == "fallida" and foto["error"]["codigo"] == "DXF_CHANGED"
    r = app.recargar()  # con la ruta que ya conoce el servidor (el editor no manda rutas)
    assert r["elegido"] == "obra.dxf"
    assert app.canal.tarea(r["tarea"]["id"]).datos["dxf"] == str(ruta.resolve())
    foto = esperar_tarea(app, r["tarea"]["id"])
    assert [b["nombre"] for b in foto["resultado"]["bloques"]] == ["B1", "B3"]
    assert app.estado()["dxf"]["sesion"] == "s-2"
    foto = esperar_tarea(app, app.pedir_previa("B1#1")["tarea"]["id"])
    assert foto["estado"] == "terminada", foto["error"]


def test_cargar_otro_dxf_cancela_las_previas_en_cola(armar, tmp_path):
    app, _ = cargado(armar, tmp_path, previa_demora_s=0.5)
    primera = app.pedir_previa("B1#1")["tarea"]["id"]
    segunda = app.pedir_previa("B2#1")["tarea"]["id"]
    recarga = app.recargar()["tarea"]["id"]
    assert esperar_tarea(app, segunda)["estado"] == "cancelada"  # esperaba turno: ya no sirve
    assert esperar_tarea(app, primera)["estado"] == "cancelada"  # en curso: se le manda cancel
    assert esperar_tarea(app, recarga)["estado"] == "terminada"


def test_cache_de_previas_de_componedor_json(armar, tmp_path):
    cfg = ConfigExportador(comando_falso(), tmp_path / "trabajo", cache_previas_mb=7)
    app = AplicacionEditor(tmp_path / "editor.html", ZONA_A1, cfg, elegir=lambda i: None)
    trabajador = app._fabrica()
    assert trabajador.opciones == ["--preview-cache-mb", "7"]
    assert ConfigExportador(comando_falso(), tmp_path).opciones_trabajador() == ()
