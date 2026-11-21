"""«Exportar» y vista previa con estilo de impresión (CTB y transparencia), con el trabajador
falso: la tabla se elige por nombre (la ruta la pone el servidor), el paquete lleva la marca y
convive con el viejo sin CTB, la caché mira el estilo y un paquete con otro estilo no vale."""

import hashlib
import json

import pytest
from conftest import ZONA_A1, comando_falso, dxf_falso
from test_estilos_impresion import ctb
from test_exportar_editor import BLOQUES, esperar, pedido
from test_servidor import HTML
from test_servidor import pedido as pedido_http

from componedor.aplicacion_editor import AplicacionEditor, ErrorAplicacion
from componedor.configuracion import ConfigExportador
from componedor.servidor import ServidorEditor

NOMBRE = "CTB_ERCO_derivada_PRGD.ctb"


def cuerpo(datos: dict) -> bytes:
    return json.dumps(datos).encode("utf-8")


@pytest.fixture
def armar(tmp_path):
    creadas = []
    tabla = ctb(tmp_path / "Exportador" / "ctb" / NOMBRE, "Derivada del PDF de AutoCAD")
    ctb(tmp_path / "Exportador" / "ctb" / "CTB_ERCO_V2.ctb", "CTB a utilizar para diseños ERCO")

    def armar(estilo_impresion=NOMBRE, imprimir_transparencia=False, carpeta="ctb", **spec):
        spec.setdefault("blocks", BLOQUES)
        ruta = dxf_falso(tmp_path / "obras" / "GUAMO prueba.dxf", **spec)
        cfg = ConfigExportador(comando_falso(), tmp_path / "trabajo", 5.0, None,
                               tmp_path / "data" / "input" / "dxf", tmp_path / "_para_borrar",
                               100, tmp_path / "Exportador" / carpeta, estilo_impresion,
                               imprimir_transparencia)
        app = AplicacionEditor(tmp_path / "editor" / "editor.html", ZONA_A1, cfg,
                               elegir=lambda inicial: ruta)
        creadas.append(app)
        foto = esperar(app, app.elegir_y_cargar()["tarea"]["id"])
        assert foto["estado"] == "terminada", foto["error"]
        return app, foto["resultado"]

    armar.sha = hashlib.sha256(tabla.read_bytes()).hexdigest()
    armar.tabla = tabla
    yield armar
    for app in creadas:
        app.cerrar()


def test_la_lista_de_estilos_y_los_valores_por_defecto(armar, tmp_path):
    app, _ = armar()
    r = app.estilos()
    assert [e["nombre"] for e in r["estilos"]] == ["CTB_ERCO_derivada_PRGD.ctb", "CTB_ERCO_V2.ctb"]
    assert r["estilos"][0]["sha256"] == armar.sha
    assert r["estilos"][0]["descripcion"] == "Derivada del PDF de AutoCAD"
    assert "ruta" not in r["estilos"][0] and str(tmp_path) not in str(r["estilos"])  # sin rutas
    assert r["por_defecto"] == {"ctb": NOMBRE, "transparencia": False} and r["aviso"] is None
    app2, _ = armar(estilo_impresion="no_esta.ctb")
    r = app2.estilos()
    assert r["por_defecto"]["ctb"] is None and "no está en la carpeta" in r["aviso"]
    app3, _ = armar(carpeta="no_existe")
    assert app3.estilos()["estilos"] == [] and "No existe la carpeta" in app3.estilos()["aviso"]


def test_exportar_con_la_ctb_y_sin_transparencia(armar, tmp_path):
    app, carpeta = armar()
    estilo = {"ctb": NOMBRE, "transparencia": False}
    (foto,) = app.exportar([pedido(carpeta)], estilo)["tareas"]
    datos = app.canal.tarea(foto["id"]).datos
    paquete = f"BLOQUE1_1-5000_p{armar.sha[:6]}_t"
    assert datos["jobs"][0]["package"] == paquete
    # La ruta de la tabla la pone el servidor (la de la carpeta de componedor.json).
    assert datos["options"]["plot_style"] == str(armar.tabla.resolve())
    assert datos["options"]["print_transparency"] is False
    foto = esperar(app, foto["id"])
    assert foto["estado"] == "terminada", foto["error"]
    r = foto["resultado"]
    assert r["paquete"] == paquete and r["movidos"] == []
    assert r["estilo"] == {"ctb": NOMBRE, "sha256": armar.sha, "transparencia": False}
    assert r["detalle"]["estilo"] == r["estilo"]
    # La segunda vez, de la caché (mismo estilo).
    (otra,) = app.exportar([pedido(carpeta)], estilo)["tareas"]
    assert otra["estado"] == "terminada" and otra["resultado"]["en_cache"] is True


def test_convive_con_el_paquete_viejo_sin_ctb(armar, tmp_path):
    app, carpeta = armar()
    sin = {"ctb": None, "transparencia": True}
    viejo = esperar(app, app.exportar([pedido(carpeta)], sin)["tareas"][0]["id"])["resultado"]
    assert viejo["paquete"] == "BLOQUE1_1-5000"
    assert viejo["estilo"] == {"ctb": None, "sha256": None, "transparencia": True}
    assert "plot_style" not in app.canal.tarea(app._exportacion[next(iter(app._exportacion))]).datos[
        "options"]  # sin CTB, el pedido de siempre
    nuevo = esperar(app, app.exportar([pedido(carpeta)], {"ctb": NOMBRE, "transparencia": False})[
        "tareas"][0]["id"])["resultado"]
    assert nuevo["paquete"] != viejo["paquete"] and nuevo["movidos"] == []  # no lo reemplaza
    salida = tmp_path / "data" / "input" / "dxf" / "GUAMO_prueba"
    assert sorted(p.name for p in salida.glob("*.manifest.json")) == [
        "BLOQUE1_1-5000.manifest.json", f"BLOQUE1_1-5000_p{armar.sha[:6]}_t.manifest.json"]
    assert not (tmp_path / "_para_borrar").exists()
    # Solo transparencia: otra marca, otro paquete.
    t = esperar(app, app.exportar([pedido(carpeta)], {"ctb": None, "transparencia": False})[
        "tareas"][0]["id"])["resultado"]
    assert t["paquete"] == "BLOQUE1_1-5000_t"


def test_si_la_ctb_cambia_sale_otro_paquete(armar):
    app, carpeta = armar()
    estilo = {"ctb": NOMBRE, "transparencia": False}
    antes = esperar(app, app.exportar([pedido(carpeta)], estilo)["tareas"][0]["id"])["resultado"]
    ctb(armar.tabla, "Derivada otra vez", relleno="aci 35 cambiado\n")
    despues = esperar(app, app.exportar([pedido(carpeta)], estilo)["tareas"][0]["id"])
    assert despues["estado"] == "terminada", despues["error"]
    assert despues["resultado"]["paquete"] != antes["paquete"]
    assert despues["resultado"]["en_cache"] is False


def test_sin_estilo_en_el_pedido_usa_el_de_componedor_json(armar):
    app, carpeta = armar()
    (foto,) = app.exportar([pedido(carpeta)])["tareas"]
    assert app.canal.tarea(foto["id"]).datos["jobs"][0]["package"].endswith(f"_p{armar.sha[:6]}_t")
    app2, carpeta2 = armar(estilo_impresion="no_esta.ctb")
    with pytest.raises(ErrorAplicacion, match="Revise exportador.estilo_impresion") as e:
        app2.exportar([pedido(carpeta2)])
    assert e.value.estado_http == 409


def test_el_editor_no_puede_mandar_rutas(armar, tmp_path):
    app, carpeta = armar()
    for estilo in ({"ctb": str(armar.tabla)}, {"ctb": "../ctb/" + NOMBRE}, {"ctb": "otra.ctb"},
                   {"ctb": NOMBRE, "transparencia": "no"}, {"ruta": "x"}, "CTB"):
        with pytest.raises(ErrorAplicacion) as e:
            app.exportar([pedido(carpeta)], estilo)
        assert e.value.estado_http == 400, estilo
        with pytest.raises(ErrorAplicacion):
            app.pedir_previa(carpeta["bloques"][0]["ref"], estilo)
    assert not list((tmp_path / "data").rglob("*.manifest.json"))


def test_un_paquete_que_no_trae_el_estilo_pedido_no_vale(armar, tmp_path):
    app, carpeta = armar(ignorar_estilo=True)  # el trabajador publica sin la CTB
    foto = esperar(app, app.exportar([pedido(carpeta)], {"ctb": NOMBRE, "transparencia": False})[
        "tareas"][0]["id"])
    assert foto["estado"] == "fallida"
    assert foto["error"]["codigo"] == "PAQUETE_NO_VALIDO"
    assert "otro estilo de impresión (sin CTB" in foto["error"]["mensaje"]
    assert not list((tmp_path / "data" / "input" / "dxf").rglob("*.manifest.json"))


def test_vista_previa_con_el_estilo(armar):
    app, carpeta = armar()
    ref = carpeta["bloques"][0]["ref"]
    con = app.pedir_previa(ref, {"ctb": NOMBRE, "transparencia": False})["tarea"]
    datos = app.canal.tarea(con["id"]).datos
    assert datos["plot_style"] == str(armar.tabla.resolve()) and datos["print_transparency"] is False
    fin = esperar(app, con["id"])
    assert fin["estado"] == "terminada", fin["error"]
    sin = esperar(app, app.pedir_previa(ref, {"ctb": None, "transparencia": True})["tarea"]["id"])
    assert "plot_style" not in app.canal.tarea(sin["id"]).datos
    assert sin["id"] != con["id"]
    # Cada estilo tiene su PNG en la caché del trabajador.
    assert app._previas[con["id"]] != app._previas[sin["id"]]
    assert app._previas[con["id"]].stem.endswith(f"_p{armar.sha[:6]}_t")


def test_por_http(armar, tmp_path):
    app, carpeta = armar()
    app.ruta_html.parent.mkdir(parents=True, exist_ok=True)
    app.ruta_html.write_text(HTML, encoding="utf-8")
    s = ServidorEditor(app)
    s.iniciar()
    try:
        estado, r = pedido_http(s, "GET", "/api/estilos")
        assert estado == 200 and r["por_defecto"] == {"ctb": NOMBRE, "transparencia": False}
        assert pedido_http(s, "GET", "/api/estilos", token=False)[0] == 403
        estado, r = pedido_http(s, "POST", "/api/exportar", cuerpo=cuerpo({
            "bloques": [pedido(carpeta)], "estilo": {"ctb": str(armar.tabla)}}))
        assert estado == 400 and "sin carpetas" in r["error"]
        estado, r = pedido_http(s, "POST", "/api/exportar", cuerpo=cuerpo({
            "bloques": [pedido(carpeta)], "estilo": {"ctb": NOMBRE, "transparencia": False}}))
        assert estado == 200
        fin = esperar(app, r["tareas"][0]["id"])
        assert fin["resultado"]["paquete"].endswith(f"_p{armar.sha[:6]}_t")
        estado, r = pedido_http(s, "POST", "/api/previa", cuerpo=cuerpo({
            "ref": carpeta["bloques"][0]["ref"], "estilo": {"ctb": None, "transparencia": False}}))
        assert estado == 200 and app.canal.tarea(r["tarea"]["id"]).datos["print_transparency"] is False
    finally:
        s.detener()
