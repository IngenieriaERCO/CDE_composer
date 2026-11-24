"""Servidor local del editor: solo 127.0.0.1, token, Host y Origin (trabajador falso)."""

import http.client
import json
import time

import pytest
from conftest import ZONA_A1, comando_falso, dxf_falso

from componedor.aplicacion_editor import AplicacionEditor
from componedor.cli import main
from componedor.configuracion import ConfigExportador
from componedor.servidor import (
    CABECERA_TOKEN,
    LIMITE_CUERPO,
    ServidorEditor,
    motivo_rechazo,
)

HTML = "<!DOCTYPE html><html><body>editor de prueba</body></html>"


@pytest.fixture
def servidor(tmp_path):
    (tmp_path / "editor.html").write_text(HTML, encoding="utf-8")
    ruta = dxf_falso(tmp_path / "obra.dxf")
    app = AplicacionEditor(tmp_path / "editor.html", ZONA_A1,
                           ConfigExportador(comando_falso(), tmp_path / "trabajo"),
                           elegir=lambda inicial: ruta)
    s = ServidorEditor(app, registro=tmp_path / "trabajo" / "servidor.log")
    s.iniciar()
    yield s
    s.detener()
    app.cerrar()


def pedido(s, metodo, ruta, cabeceras=None, cuerpo=None, token=True, origen=True):
    c = http.client.HTTPConnection("127.0.0.1", s.puerto, timeout=20)
    h = {"Host": f"127.0.0.1:{s.puerto}"}
    if token and not ruta.startswith("/?"):
        h[CABECERA_TOKEN] = s.token
    if metodo == "POST":
        if origen:
            h["Origin"] = s.origen
        h["Content-Type"] = "application/json"
        cuerpo = b"{}" if cuerpo is None else cuerpo
        h["Content-Length"] = str(len(cuerpo))
    h.update(cabeceras or {})
    c.putrequest(metodo, ruta, skip_host=True)
    for k, v in h.items():
        if v is not None:
            c.putheader(k, v)
    c.endheaders(cuerpo)
    r = c.getresponse()
    datos = r.read()
    c.close()
    if r.getheader("Content-Type") == "image/png":
        return r.status, datos  # los bytes del PNG
    try:
        return r.status, json.loads(datos)
    except json.JSONDecodeError:
        return r.status, datos.decode("utf-8")


def esperar(s, id_tarea):
    fin = time.monotonic() + 20
    while True:
        estado, foto = pedido(s, "GET", f"/api/tareas/{id_tarea}")
        assert estado == 200
        if foto["estado"] in ("terminada", "fallida", "cancelada"):
            return foto
        assert time.monotonic() < fin
        time.sleep(0.05)


def test_escucha_solo_en_127_0_0_1(servidor):
    assert servidor._http.server_address[0] == "127.0.0.1"
    assert servidor.url == f"http://127.0.0.1:{servidor.puerto}/?t={servidor.token}"
    assert len(servidor.token) >= 40


def test_la_pagina_con_token_es_el_mismo_editor_html(servidor):
    estado, html = pedido(servidor, "GET", f"/?t={servidor.token}")
    assert estado == 200 and html == HTML  # el servidor no agrega nada (ni firmas ni rutas)
    assert pedido(servidor, "GET", "/?t=otro")[0] == 403
    assert pedido(servidor, "GET", "/")[0] == 403


@pytest.mark.parametrize("host", ["localhost:{p}", "127.0.0.1", "evil.example:{p}",
                                  "127.0.0.1:1", None])
def test_host_distinto_se_rechaza(servidor, host):
    h = host.format(p=servidor.puerto) if host else None
    estado, datos = pedido(servidor, "GET", "/api/estado", {"Host": h})
    assert estado == 403 and datos == {"error": "Host no permitido."}


def test_api_exige_el_token_en_la_cabecera(servidor):
    assert pedido(servidor, "GET", "/api/estado", token=False)[0] == 403
    assert pedido(servidor, "GET", "/api/estado", {CABECERA_TOKEN: "x"})[0] == 403
    # El token en la dirección no sirve para la API (solo para abrir la página).
    assert pedido(servidor, "GET", f"/api/estado?t={servidor.token}", token=False)[0] == 403
    estado, datos = pedido(servidor, "GET", "/api/estado")
    assert estado == 200 and datos["servidor"] is True
    assert datos["exportador"]["disponible"] is True


def test_post_exige_origin_propio_y_json(servidor):
    assert pedido(servidor, "POST", "/api/latido", origen=False)[0] == 403
    estado, datos = pedido(servidor, "POST", "/api/latido", {"Origin": "http://otro.sitio"})
    assert (estado, datos) == (403, {"error": "Origen no permitido."})
    assert pedido(servidor, "POST", "/api/latido", {"Origin": "null"})[0] == 403  # file://
    assert pedido(servidor, "POST", "/api/latido", {"Content-Type": "text/plain"})[0] == 415
    assert pedido(servidor, "POST", "/api/latido", cuerpo=b"no json")[0] == 400
    grande = b'{"x": "' + b"a" * LIMITE_CUERPO + b'"}'
    assert pedido(servidor, "POST", "/api/latido", cuerpo=grande)[0] == 413
    assert pedido(servidor, "POST", "/api/latido", {"Sec-Fetch-Site": "cross-site"})[0] == 403
    assert pedido(servidor, "POST", "/api/latido", {"Sec-Fetch-Site": "same-origin"}) == (
        200, {"ok": True})


def test_rutas_desconocidas_y_metodos(servidor):
    assert pedido(servidor, "GET", "/editor.html")[0] == 404
    assert pedido(servidor, "GET", "/../componedor.json")[0] == 404
    assert pedido(servidor, "GET", "/api/tareas/t-1/../../x")[0] == 404
    assert pedido(servidor, "POST", "/api/estado")[0] == 404
    assert pedido(servidor, "GET", "/api/dxf/elegir")[0] == 404
    assert pedido(servidor, "PUT", "/api/estado")[0] == 405
    assert pedido(servidor, "GET", "/api/tareas/t-9")[0] == 404  # ruta válida, tarea no


def test_cargar_dxf_de_punta_a_punta(servidor):
    estado, r = pedido(servidor, "POST", "/api/dxf/elegir")
    assert estado == 200 and r["elegido"] == "obra.dxf"
    fin = time.monotonic() + 20
    while True:
        estado, foto = pedido(servidor, "GET", f"/api/tareas/{r['tarea']['id']}")
        assert estado == 200
        if foto["estado"] in ("terminada", "fallida", "cancelada"):
            break
        assert time.monotonic() < fin
        time.sleep(0.05)
    assert foto["estado"] == "terminada", foto["error"]
    assert [b["nombre"] for b in foto["resultado"]["bloques"]] == ["B1"]
    _, e = pedido(servidor, "GET", "/api/estado")
    assert e["dxf"]["dxf"]["nombre"] == "obra.dxf" and e["dxf"]["sesion_activa"] is True
    estado, c = pedido(servidor, "POST", f"/api/tareas/{r['tarea']['id']}/cancelar")
    assert (estado, c) == (200, {"cancelando": False})  # ya había terminado


def test_el_registro_no_guarda_el_token(servidor, tmp_path):
    pedido(servidor, "GET", f"/?t={servidor.token}")
    pedido(servidor, "GET", "/api/estado")
    registro = (tmp_path / "trabajo" / "servidor.log").read_text(encoding="utf-8")
    assert "GET /?t=***" in registro and servidor.token not in registro


def test_cada_pedido_de_la_api_cuenta_como_latido(servidor):
    servidor.app.ultimo_latido = 0.0
    pedido(servidor, "GET", "/api/estado")
    assert time.monotonic() - servidor.app.ultimo_latido < 5


def test_se_apaga_por_inactividad(servidor):
    servidor.app.ultimo_latido = time.monotonic() - 10
    assert servidor.esperar(5, cada_s=0.01) == "inactividad"


def test_falta_editor_html(servidor, tmp_path):
    (tmp_path / "editor.html").unlink()
    estado, datos = pedido(servidor, "GET", f"/?t={servidor.token}")
    assert estado == 500 and "genere el editor" in datos["error"]


@pytest.mark.parametrize("metodo, url, cabeceras, esperado", [
    ("GET", "/?t=T", {"Host": "127.0.0.1:8"}, None),
    ("GET", "/?t=T", {"Host": "127.0.0.1:8", "Sec-Fetch-Site": "none"}, None),
    ("GET", "/api/estado", {"Host": "127.0.0.1:8", CABECERA_TOKEN: "T",
                            "Sec-Fetch-Site": "none"}, (403, "Pedido desde otro sitio.")),
    ("GET", "/api/estado", {"Host": "127.0.0.1:8", CABECERA_TOKEN: "T",
                            "Origin": "http://127.0.0.1:8"}, None),
    ("POST", "/api/latido", {"Host": "127.0.0.1:8", CABECERA_TOKEN: "T",
                             "Origin": "http://127.0.0.1:8", "Content-Type": "application/json",
                             "Content-Length": "x"}, (400, "Content-Length inválido.")),
    ("POST", "/api/tareas/t-3/cancelar", {"Host": "127.0.0.1:8", CABECERA_TOKEN: "T",
                                          "Origin": "http://127.0.0.1:8",
                                          "Content-Type": "application/json; charset=utf-8"},
     None),
])
def test_motivo_rechazo(metodo, url, cabeceras, esperado):
    assert motivo_rechazo(metodo, url, cabeceras, "T", 8) == esperado


# --- comando servidor ---------------------------------------------------------------------------

def _config(tmp_path, exportador=True):
    from conftest import RUTA_A1

    datos = {"version": 1, "formato": str(RUTA_A1),
             "editor": {"paquetes": "input", "salida": "editor"},
             "componer": {"resultados": "resultados"}}
    if exportador:
        datos["exportador"] = {"comando": list(comando_falso()), "trabajo": "trabajo"}
    (tmp_path / "input").mkdir(exist_ok=True)
    ruta = tmp_path / "componedor.json"
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    return ruta


def test_cli_servidor_sin_editor_generado(tmp_path, capsys):
    assert main(["servidor", "--config", str(_config(tmp_path)), "--no-abrir"]) == 1
    assert "genere primero el editor" in capsys.readouterr().err


def test_cli_servidor_arranca_y_se_apaga_por_inactividad(tmp_path, capsys):
    ruta = _config(tmp_path)
    (tmp_path / "editor").mkdir()
    (tmp_path / "editor" / "editor.html").write_text(HTML, encoding="utf-8")
    assert main(["servidor", "--config", str(ruta), "--no-abrir",
                 "--inactividad-min", "0.0005"]) == 0
    salida = capsys.readouterr().out
    assert "Editor con servidor local: http://127.0.0.1:" in salida and "/?t=" in salida
    assert "«Cargar DXF»: disponible." in salida
    assert "No cierre esta ventana" in salida and "sin señal del editor" in salida
    assert (tmp_path / "trabajo").is_dir() is False  # sin «Cargar DXF» no se lanzó nada


def test_cli_servidor_sin_seccion_exportador(tmp_path, capsys):
    ruta = _config(tmp_path, exportador=False)
    (tmp_path / "editor").mkdir()
    (tmp_path / "editor" / "editor.html").write_text(HTML, encoding="utf-8")
    assert main(["servidor", "--config", str(ruta), "--no-abrir",
                 "--inactividad-min", "0.0005"]) == 0
    assert "«Cargar DXF»: no disponible. componedor.json no tiene la sección" in (
        capsys.readouterr().out)


def test_vista_previa_y_su_png(servidor):
    """Etapa 2: el editor pide la vista previa de un ref y baja el PNG con el token."""
    assert pedido(servidor, "POST", "/api/previa", cuerpo=b'{"ref": "B1#1"}')[0] == 409  # sin DXF
    _, r = pedido(servidor, "POST", "/api/dxf/elegir")
    assert esperar(servidor, r["tarea"]["id"])["estado"] == "terminada"
    assert pedido(servidor, "POST", "/api/previa", cuerpo=b"[1, 2]") == (
        400, {"error": "El cuerpo no es un objeto JSON."})
    assert pedido(servidor, "POST", "/api/previa", cuerpo=b'{"ref": "NO#1"}')[0] == 404
    estado, r = pedido(servidor, "POST", "/api/previa", cuerpo=b'{"ref": "B1#1"}')
    assert estado == 200 and r["tarea"]["tipo"] == "previa"
    foto = esperar(servidor, r["tarea"]["id"])
    assert foto["estado"] == "terminada", foto["error"]
    url = foto["resultado"]["url"]
    assert url == f"/api/previas/{r['tarea']['id']}"
    estado, png = pedido(servidor, "GET", url)
    assert estado == 200 and png[:4] == bytes([0x89]) + b"PNG"
    assert pedido(servidor, "GET", url, token=False)[0] == 403  # también con token
    assert pedido(servidor, "GET", "/api/previas/t-99")[0] == 404
    assert pedido(servidor, "GET", "/api/previas/../../firmas")[0] == 404
    # «Volver a cargar»: con la ruta que ya conoce el servidor.
    estado, r = pedido(servidor, "POST", "/api/dxf/recargar")
    assert estado == 200 and r["elegido"] == "obra.dxf"
    assert esperar(servidor, r["tarea"]["id"])["estado"] == "terminada"


def test_vista_previa_de_una_zona(servidor):
    """Protocolo 1.1: todo el Model Space o una zona, y el PNG por la misma ruta."""
    assert pedido(servidor, "POST", "/api/previa/zona", cuerpo=b"{}")[0] == 409  # sin DXF
    _, r = pedido(servidor, "POST", "/api/dxf/elegir")
    assert esperar(servidor, r["tarea"]["id"])["estado"] == "terminada"
    estado, r = pedido(servidor, "POST", "/api/previa/zona", cuerpo=b'{"zona": [1, 2]}')
    assert estado == 400 and "«zona» debe ser" in r["error"]
    cuerpo = json.dumps({"zona": [1000, 2000, 1005, 2002], "excluir": ["COTAS"],
                         "escala": 50}).encode()
    estado, r = pedido(servidor, "POST", "/api/previa/zona", cuerpo=cuerpo)
    assert estado == 200 and r["tarea"]["tipo"] == "previa_zona"
    foto = esperar(servidor, r["tarea"]["id"])
    assert foto["estado"] == "terminada", foto["error"]
    assert foto["resultado"]["papel"]["contenido_mm"] == [100.0, 40.0]
    estado, png = pedido(servidor, "GET", foto["resultado"]["url"])
    assert estado == 200 and png[:4] == bytes([0x89]) + b"PNG"


def test_exportar_una_zona(tmp_path):
    """Fase 10c: POST /api/exportar/zona con el trabajador falso; el paquete queda en
    paquetes/<dxf>/ y aparece en /api/exportados."""
    ruta = dxf_falso(tmp_path / "obra.dxf", blocks=[{"name": "B1", "handle": "1A"}])
    cfg = ConfigExportador(comando_falso(), tmp_path / "trabajo", 5.0, None,
                           tmp_path / "paquetes", tmp_path / "_para_borrar")
    app = AplicacionEditor(tmp_path / "editor" / "editor.html", ZONA_A1, cfg,
                           elegir=lambda inicial: ruta)
    s = ServidorEditor(app, token="t" * 32)
    s.iniciar()
    try:
        _, r = pedido(s, "POST", "/api/dxf/elegir")
        assert esperar(s, r["tarea"]["id"])["estado"] == "terminada"
        estado, r = pedido(s, "POST", "/api/exportar/zona", cuerpo=b'{"zona": [0, 0, 1, 1]}')
        assert estado == 400 and "Falta «escala»" in r["error"]
        cuerpo = json.dumps({"zona": [1000, 2000, 1002, 2001], "escala": 50,
                             "nombre": ""}).encode()
        estado, r = pedido(s, "POST", "/api/exportar/zona", cuerpo=cuerpo)
        assert estado == 200 and r["tarea"]["tipo"] == "exportar"
        foto = esperar(s, r["tarea"]["id"])
        assert foto["estado"] == "terminada", foto["error"]
        assert foto["resultado"]["nombre"] == "Zona_01"
        assert (tmp_path / "paquetes" / "obra" / "Zona_01_1-50.manifest.json").is_file()
        _, exportados = pedido(s, "GET", "/api/exportados")
        assert [d["manifiesto"] for d in exportados["detalles"]] == [
            foto["resultado"]["manifiesto"]]
    finally:
        s.detener()
        app.cerrar()


def test_exportar_y_detener(tmp_path):
    """Etapa 3: POST /api/exportar con la lista de bloques; POST /api/trabajador/detener."""
    (tmp_path / "editor.html").write_text(HTML, encoding="utf-8")
    ruta = dxf_falso(tmp_path / "obra.dxf", blocks=[
        {"name": "B1", "size_cad": [10.0, 4.0], "handle": "1A"}])
    app = AplicacionEditor(tmp_path / "editor.html", ZONA_A1,
                           ConfigExportador(comando_falso(), tmp_path / "trabajo", 5.0, None,
                                            tmp_path / "dxf", tmp_path / "_para_borrar"),
                           elegir=lambda inicial: ruta)
    s = ServidorEditor(app)
    s.iniciar()
    try:
        _, r = pedido(s, "POST", "/api/dxf/elegir")
        carpeta = esperar(s, r["tarea"]["id"])["resultado"]
        bloque = {"id": "B1", "handle": "1A", "sha256": carpeta["dxf"]["sha256"], "escala": 50,
                  "centro_mm": [300, 200]}
        estado, r = pedido(s, "POST", "/api/exportar",
                           cuerpo=json.dumps({"bloques": [bloque]}).encode())
        assert estado == 200 and len(r["tareas"]) == 1
        foto = esperar(s, r["tareas"][0]["id"])
        assert foto["estado"] == "terminada", foto["error"]
        assert foto["resultado"]["manifiesto"] == "dxf/obra/B1_1-50.manifest.json"
        assert pedido(s, "POST", "/api/exportar", cuerpo=b'{"bloques": []}')[0] == 400
        _, ex = pedido(s, "GET", "/api/exportados")
        assert [d["manifiesto"] for d in ex["detalles"]] == ["dxf/obra/B1_1-50.manifest.json"]
        assert pedido(s, "POST", "/api/trabajador/detener") == (200, {"detenido": True})
        _, e = pedido(s, "GET", "/api/estado")
        assert e["dxf"]["sesion_activa"] is False
    finally:
        s.detener()
        app.cerrar()


# --- ortofoto ---------------------------------------------------------------------------------

@pytest.fixture
def servidor_ortofoto(tmp_path):
    from ortofoto_sintetica import crear_geotiff

    (tmp_path / "editor.html").write_text(HTML, encoding="utf-8")
    tif = crear_geotiff(tmp_path / "orto.tif")
    # Sin sección «exportador»: la ortofoto no usa el trabajador y funciona igual.
    app = AplicacionEditor(tmp_path / "editor.html", ZONA_A1, None,
                           elegir_ortofoto=lambda inicial: tif)
    s = ServidorEditor(app)
    s.iniciar()
    yield s
    s.detener()
    app.cerrar()


def test_ortofoto_por_http(servidor_ortofoto):
    from ortofoto_sintetica import ORIGEN

    s = servidor_ortofoto
    assert pedido(s, "GET", "/api/ortofoto") == (200, {"ortofoto": None})
    estado, r = pedido(s, "POST", "/api/ortofoto/elegir")
    assert estado == 200 and r["elegida"] == "orto.tif"
    assert r["ortofoto"]["archivo_plano"] == "orto.tif"
    assert pedido(s, "GET", "/api/estado")[1]["ortofoto"]["ficha"]["px"] == [400, 300]
    x0, y1 = ORIGEN
    cuerpo = json.dumps({"caja_cad": [x0 + 100, y1 - 200, x0 + 200, y1 - 100],
                         "mm_por_unidad": 1000, "crs_dibujo": "EPSG:9377", "px": 64}).encode()
    estado, previa = pedido(s, "POST", "/api/ortofoto/previa", cuerpo=cuerpo)
    assert estado == 200 and previa["px"] == [64, 64] and previa["cobertura"] == 1.0
    estado, png = pedido(s, "GET", previa["url"])
    assert estado == 200 and png.startswith(b"\x89PNG")
    assert pedido(s, "GET", previa["url"], token=False)[0] == 403  # también con token
    assert pedido(s, "GET", "/api/ortofoto/previas/o-99")[0] == 404
    assert pedido(s, "GET", "/api/ortofoto/previas/../x")[0] == 404
    malo = json.dumps({"caja_cad": [0, 0, 1, 1], "crs_dibujo": "EPSG:4326"}).encode()
    estado, r = pedido(s, "POST", "/api/ortofoto/previa", cuerpo=malo)
    assert estado == 400 and "proyectado" in r["error"]
    assert pedido(s, "POST", "/api/ortofoto/quitar") == (200, {"quitada": True})
    estado, r = pedido(s, "POST", "/api/ortofoto/previa", cuerpo=cuerpo)
    assert estado == 409 and "Cargar ortofoto" in r["error"]


def test_las_rutas_de_la_ortofoto_piden_token_y_origen(servidor_ortofoto):
    s = servidor_ortofoto
    assert pedido(s, "GET", "/api/ortofoto", token=False)[0] == 403
    assert pedido(s, "POST", "/api/ortofoto/elegir", origen=False)[0] == 403
    assert pedido(s, "POST", "/api/ortofoto/elegir",
                  cabeceras={"Origin": "http://evil.example"})[0] == 403
    assert pedido(s, "GET", "/api/ortofoto/elegir")[0] == 404  # solo POST
