"""«Exportar» desde el servidor del editor (etapa 3), con el trabajador falso: un trabajo por
pedido, caché de paquetes publicados, paquetes viejos a _para_borrar, verificación, colocación
por el centro CAD, DXF_CHANGED, cancelar y detener a la fuerza."""

import time

import pytest
from conftest import ZONA_A1, comando_falso, dxf_falso

from componedor.aplicacion_editor import AplicacionEditor, ErrorAplicacion
from componedor.canal_trabajador import FINALES
from componedor.configuracion import ConfigExportador

BLOQUES = [
    {"name": "BLOQUE1", "size_cad": [957.18, 1350.019], "min": [899699.777, 937885.353],
     "handle": "50CA"},
    {"name": "Viga", "size_cad": [10.0, 4.0], "min": [100.0, 200.0], "handle": "1A1"},
]


def esperar(app, id_tarea, segundos=30):
    fin = time.monotonic() + segundos
    while True:
        foto = app.tarea(id_tarea)
        if foto["estado"] in FINALES:
            return foto
        assert time.monotonic() < fin, foto
        time.sleep(0.02)


@pytest.fixture
def armar(tmp_path):
    creadas = []

    def armar(**spec):
        spec.setdefault("blocks", BLOQUES)
        ruta = dxf_falso(tmp_path / "obras" / "GUAMO prueba.dxf", **spec)
        cfg = ConfigExportador(comando_falso(), tmp_path / "trabajo", 5.0, None,
                               tmp_path / "data" / "input" / "dxf", tmp_path / "_para_borrar")
        app = AplicacionEditor(tmp_path / "editor" / "editor.html", ZONA_A1, cfg,
                               elegir=lambda inicial: ruta)
        creadas.append(app)
        foto = esperar(app, app.elegir_y_cargar()["tarea"]["id"])
        assert foto["estado"] == "terminada", foto["error"]
        return app, ruta, foto["resultado"]

    yield armar
    for app in creadas:
        app.cerrar()


def pedido(carpeta, ident="BLOQUE1", handle="50CA", escala=5000, centro=(342.55, 297.0)):
    return {"id": ident, "handle": handle, "sha256": carpeta["dxf"]["sha256"], "escala": escala,
            "centro_mm": list(centro)}


def test_exportar_un_bloque(armar, tmp_path):
    app, _, carpeta = armar()
    (foto,) = app.exportar([pedido(carpeta)])["tareas"]
    assert foto["tipo"] == "exportar"
    datos = app.canal.tarea(foto["id"]).datos
    salida = tmp_path / "data" / "input" / "dxf" / "GUAMO_prueba"
    assert datos == {"session": "s-1", "output_dir": str(salida.resolve()),
                     "jobs": [{"job": "j1", "ref": "BLOQUE1#1", "scale": "1:5000",
                               "package": "BLOQUE1_1-5000"}],
                     "options": {"solids": "footprint", "omit_unsupported": True,
                                 "overwrite": False, "write_summary": False}}
    foto = esperar(app, foto["id"])
    assert foto["estado"] == "terminada", foto["error"]
    r = foto["resultado"]
    assert r["paquete"] == "BLOQUE1_1-5000" and r["en_cache"] is False and r["movidos"] == []
    assert r["manifiesto"] == "../data/input/dxf/GUAMO_prueba/BLOQUE1_1-5000.manifest.json"
    # Por el centro CAD: caja exacta → la página centrada en centro_mm.
    assert r["posicion_mm"] == pytest.approx([342.55 - 201.436 / 2, 297.0 - 280.0038 / 2])
    assert r["desde_centro_mm"] == pytest.approx([201.436 / 2, 280.0038 / 2])
    assert app.exportados() == {"detalles": [r["detalle"]]}  # para el editor que se recarga
    d = r["detalle"]
    assert d["manifiesto"] == r["manifiesto"] and d["escala"] == 5000.0 and d["cabe"] is True
    assert d["tamano_pagina_mm"] == pytest.approx([201.436, 280.0038])
    assert d["tiene_fondo"] is False and d["miniatura"]["data_url"].startswith("data:image/png;base64,")
    assert sorted(p.name for p in salida.iterdir()) == [
        "BLOQUE1_1-5000.manifest.json", "BLOQUE1_1-5000.pdf", "BLOQUE1_1-5000.txt"]


def test_avance_de_la_exportacion(armar):
    app, _, carpeta = armar(export_demora_s=0.15)
    (foto,) = app.exportar([pedido(carpeta)])["tareas"]
    etapas = set()
    while (f := app.tarea(foto["id"]))["estado"] not in FINALES:
        if f["avance"].get("stage"):
            etapas.add(f["avance"]["stage"])
        time.sleep(0.02)
    assert {"extract", "draw", "publish"} <= etapas


def test_la_segunda_vez_sale_de_la_cache_sin_trabajador(armar):
    app, _, carpeta = armar()
    esperar(app, app.exportar([pedido(carpeta)])["tareas"][0]["id"])
    pedidos_antes = len(app.canal._tareas)
    (foto,) = app.exportar([pedido(carpeta, centro=(300.0, 300.0))])["tareas"]
    assert foto["estado"] == "terminada" and foto["resultado"]["en_cache"] is True
    assert foto["resultado"]["posicion_mm"] == pytest.approx([300 - 100.718, 300 - 140.0019])
    assert all(t.comando != "export" for t in list(app.canal._tareas.values())[pedidos_antes:])


def test_paquete_viejo_de_otra_version_va_a_para_borrar(armar, tmp_path):
    app, ruta, carpeta = armar()
    esperar(app, app.exportar([pedido(carpeta)])["tareas"][0]["id"])
    viejo = (tmp_path / "data" / "input" / "dxf" / "GUAMO_prueba" / "BLOQUE1_1-5000.pdf").read_bytes()
    # AutoCAD guarda el DXF: otra versión (otro SHA-256). Se vuelve a cargar y a exportar.
    ruta.write_text(ruta.read_text(encoding="utf-8") + " ", encoding="utf-8")
    nueva = esperar(app, app.recargar()["tarea"]["id"])["resultado"]
    assert nueva["dxf"]["sha256"] != carpeta["dxf"]["sha256"]
    foto = esperar(app, app.exportar([pedido(nueva)])["tareas"][0]["id"])
    assert foto["estado"] == "terminada", foto["error"]
    movidos = foto["resultado"]["movidos"]
    assert len(movidos) == 3 and all(m.startswith("../_para_borrar/paquetes_") for m in movidos)
    assert any(m.endswith("/GUAMO_prueba/BLOQUE1_1-5000.pdf") for m in movidos)
    (pdf_movido,) = (tmp_path / "_para_borrar").rglob("BLOQUE1_1-5000.pdf")
    assert pdf_movido.read_bytes() == viejo  # se movió, no se borró
    assert foto["resultado"]["en_cache"] is False


def test_dos_veces_el_mismo_bloque_y_escala_es_una_tarea(armar):
    app, _, carpeta = armar(export_demora_s=0.05)
    a, b = app.exportar([pedido(carpeta), pedido(carpeta, ident="BLOQUE1_2")])["tareas"]
    assert a["id"] == b["id"]
    otra = app.exportar([pedido(carpeta, escala=10000)])["tareas"][0]
    assert otra["id"] != a["id"]  # otra escala: otro paquete
    assert esperar(app, otra["id"])["resultado"]["paquete"] == "BLOQUE1_1-10000"


def test_pedidos_que_no_se_atienden(armar):
    app, _, carpeta = armar()
    casos = [
        (None, 400, "Se esperaba la lista «bloques»"),
        ([{"id": "x"}], 400, "Cada bloque lleva"),
        ([pedido(carpeta, escala=2500)], 400, "no cabe en el área de dibujo a 1:2500"),
        ([{**pedido(carpeta), "sha256": "0" * 64}], 409, "es de otro DXF"),
        ([pedido(carpeta, handle="FFFF")], 404, "no está en el DXF cargado"),
    ]
    for bloques, codigo, motivo in casos:
        with pytest.raises(ErrorAplicacion, match=motivo) as e:
            app.exportar(bloques)
        assert e.value.estado_http == codigo
    assert app.canal.estado()["en_cola"] == 0  # nada se encoló a medias
    app.reiniciar()
    with pytest.raises(ErrorAplicacion, match="vuelva a cargarlo") as e:
        app.exportar([pedido(carpeta)])
    assert e.value.estado_http == 409


def test_falla_del_exportador_y_paquete_que_no_pasa_la_verificacion(armar):
    app, _, carpeta = armar(blocks=[{**BLOQUES[0], "falla_export": "entidad no soportada"},
                                    {**BLOQUES[1], "escala_no_garantizada": True}])
    a, b = app.exportar([pedido(carpeta), pedido(carpeta, "Viga", "1A1", 50, (100, 100))])["tareas"]
    fa, fb = esperar(app, a["id"]), esperar(app, b["id"])
    assert fa["estado"] == "fallida" and fa["error"]["codigo"] == "EXPORT_FAILED"
    assert "entidad no soportada" in fa["error"]["mensaje"]
    assert fb["estado"] == "fallida" and fb["error"]["codigo"] == "PAQUETE_NO_VALIDO"
    assert "escala física" in fb["error"]["mensaje"]


def test_dxf_cambiado_antes_de_exportar(armar):
    """Cambió en el disco antes del pedido: ni caché ni trabajador; hay que volver a cargar."""
    app, ruta, carpeta = armar()
    esperar(app, app.exportar([pedido(carpeta)])["tareas"][0]["id"])  # queda en la caché
    ruta.write_text(ruta.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(ErrorAplicacion, match="El DXF cambió en el disco") as e:
        app.exportar([pedido(carpeta)])
    assert e.value.estado_http == 409


def test_dxf_cambiado_mientras_espera_turno(armar):
    """Cambió mientras el pedido esperaba en la cola: lo dice el trabajador (DXF_CHANGED)."""
    app, ruta, carpeta = armar(previa_demora_s=0.5)
    previa = app.pedir_previa("BLOQUE1#1")["tarea"]["id"]
    (foto,) = app.exportar([pedido(carpeta)])["tareas"]
    ruta.write_text(ruta.read_text(encoding="utf-8") + " ", encoding="utf-8")
    esperar(app, previa)
    foto = esperar(app, foto["id"])
    assert foto["estado"] == "fallida" and foto["error"]["codigo"] == "DXF_CHANGED"


def test_cancelar_una_exportacion(armar, tmp_path):
    app, _, carpeta = armar(export_demora_s=0.3)
    a, b = app.exportar([pedido(carpeta), pedido(carpeta, "Viga", "1A1", 50, (100, 100))])["tareas"]
    while app.tarea(a["id"])["estado"] != "en_curso":
        time.sleep(0.02)
    app.cancelar(b["id"])  # en cola: se quita
    app.cancelar(a["id"])  # en curso: cancel al trabajador
    assert esperar(app, b["id"])["estado"] == "cancelada"
    assert esperar(app, a["id"])["estado"] == "cancelada"
    salida = tmp_path / "data" / "input" / "dxf" / "GUAMO_prueba"
    assert [p.name for p in salida.iterdir() if not p.name.startswith(".cde-tmp-")] == []


def test_detener_a_la_fuerza(armar):
    """Un paso que no mira la cancelación: «Detener a la fuerza» no espera; la cola se vacía y
    la sesión se pierde (hay que volver a cargar)."""
    app, _, carpeta = armar(export_no_cancelable_s=30)
    a, b = app.exportar([pedido(carpeta), pedido(carpeta, "Viga", "1A1", 50, (100, 100))])["tareas"]
    while app.tarea(a["id"])["avance"].get("stage") != "analyze":
        time.sleep(0.02)
    inicio = time.monotonic()
    assert app.detener() == {"detenido": True}
    fa, fb = esperar(app, a["id"], 10), esperar(app, b["id"], 10)
    assert time.monotonic() - inicio < 10
    assert fa["estado"] == "cancelada" and fa["error"]["mensaje"] == "Detenido a la fuerza por el usuario."
    assert fb["estado"] == "cancelada" and "no llegó a empezar" in fb["error"]["mensaje"]
    assert app.estado()["dxf"]["sesion_activa"] is False
    assert app.estado()["exportador"]["trabajador"]["estado"] == "sin_iniciar"  # no es una caída
    # Volver a cargar arranca un trabajador nuevo; detenerlo sin nada en curso también vale.
    esperar(app, app.recargar()["tarea"]["id"])
    assert app.estado()["dxf"]["sesion_activa"] is True
    assert app.detener() == {"detenido": True}
    assert app.estado()["dxf"]["sesion_activa"] is False


def test_detener_sin_trabajador(tmp_path):
    cfg = ConfigExportador(comando_falso(), tmp_path / "trabajo")
    app = AplicacionEditor(tmp_path / "editor.html", ZONA_A1, cfg, elegir=lambda i: None)
    assert app.detener() == {"detenido": False}


@pytest.mark.skipif(not __import__("os").environ.get("COMPONEDOR_PRUEBA_LARGA"),
                    reason="tarda minutos: COMPONEDOR_PRUEBA_LARGA=1 para correrla")
def test_exportar_con_el_exportador_real_y_guamo(tmp_path):
    """Con el cde-exporter real y GUAMO_prueba.dxf (fuera de git; otra ruta con
    COMPONEDOR_DXF_REAL): exporta BLOQUE1 a la escala sugerida, verifica el paquete, lo coloca
    por el centro CAD y la segunda vez sale de la caché."""
    import os
    import shutil
    from pathlib import Path

    if shutil.which("cde-exporter") is None:
        pytest.skip("cde-exporter no instalado")
    dxf = Path(os.environ.get("COMPONEDOR_DXF_REAL", Path(__file__).parents[2]
                              / "Exportador Vectorial" / "data" / "input" / "GUAMO_prueba.dxf"))
    if not dxf.is_file():
        pytest.skip(f"no está {dxf}")
    cfg = ConfigExportador(("cde-exporter",), tmp_path / "trabajo", 5.0, None,
                           tmp_path / "paquetes", tmp_path / "_para_borrar")
    app = AplicacionEditor(tmp_path / "editor" / "editor.html", ZONA_A1, cfg,
                           elegir=lambda inicial: dxf)
    try:
        carga = esperar(app, app.elegir_y_cargar()["tarea"]["id"], 300)
        assert carga["estado"] == "terminada", carga["error"]
        carpeta = carga["resultado"]
        b = next(x for x in carpeta["bloques"] if x["escala_sugerida"])
        p = {"id": b["nombre"], "handle": b["handle"], "sha256": carpeta["dxf"]["sha256"],
             "escala": b["escala_sugerida"], "centro_mm": [342.55, 297.0]}
        (foto,) = app.exportar([p])["tareas"]
        if (foto := esperar(app, foto["id"], 1800))["estado"] != "terminada" and \
                foto["error"]["codigo"] == "UNKNOWN_COMMAND":
            pytest.skip("el trabajador real todavía no tiene «export»")
        assert foto["estado"] == "terminada", foto["error"]
        r = foto["resultado"]
        assert r["en_cache"] is False and r["detalle"]["cabe"] is True
        ancho, alto = r["detalle"]["tamano_pagina_mm"]
        x, y = r["posicion_mm"]
        # La página real no pasa de la caja del editor y el centro CAD queda en centro_mm.
        assert ancho <= b["pagina_sugerida_mm"][0] + 0.1 and alto <= b["pagina_sugerida_mm"][1] + 0.1
        if b["caja_exacta"]:
            assert (x + ancho / 2, y + alto / 2) == pytest.approx((342.55, 297.0), abs=0.1)
        (otra,) = app.exportar([p])["tareas"]
        assert otra["estado"] == "terminada" and otra["resultado"]["en_cache"] is True
    finally:
        app.cerrar()


def test_el_plano_con_el_paquete_exportado_se_compone(armar, tmp_path):
    """De punta a punta: exportar, poner el detalle donde dice el resultado y componer."""
    import json

    from conftest import escribir_formato

    from componedor.componer import componer_plano
    from componedor.plano import leer_plano

    app, _, carpeta = armar()
    r = esperar(app, app.exportar([pedido(carpeta)])["tareas"][0]["id"])["resultado"]
    escribir_formato(tmp_path / "formato.json")
    plano = tmp_path / "editor" / "plano.json"
    plano.parent.mkdir(exist_ok=True)
    plano.write_text(json.dumps({"version": 1, "formato": "../formato.json", "detalles": [
        {"id": "BLOQUE1", "manifiesto": r["manifiesto"],
         "posicion_mm": [round(v, 2) for v in r["posicion_mm"]]}]}), encoding="utf-8")
    resultado = componer_plano(leer_plano(plano), tmp_path / "plano.pdf")
    (colocado,) = resultado.detalles
    x0, y0, x1, y1 = colocado.ocupado
    assert ((x0 + x1) / 2, (y0 + y1) / 2) == pytest.approx((342.55, 297.0), abs=0.01)
