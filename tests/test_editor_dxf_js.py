"""Editor con servidor (JS, en Node): detectar el servidor, hablarle y los textos de la carpeta
del DXF. Y que el editor.html generado traiga el botón y siga sin URLs externas."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from conftest import ZONA_A1
from test_bloques_dxf import bloque, respuesta

import componedor
from componedor.bloques_dxf import catalogo_dxf

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node no está instalado")
CARPETA_JS = Path(componedor.__file__).parent / "editor"


def js(codigo: str, entrada=None):
    """Ejecuta `codigo` (puede usar await) con S (servidor) y D (textos del DXF)."""
    script = (
        f"const S = require({json.dumps(str(CARPETA_JS / 'editor_servidor.js'))});"
        f"const D = require({json.dumps(str(CARPETA_JS / 'editor_dxf.js'))});"
        "const entrada = JSON.parse(require('fs').readFileSync(0, 'utf8'));"
        f"(async function () {{ {codigo} }})().then((salida) => "
        "process.stdout.write(JSON.stringify(salida === undefined ? null : salida)),"
        "(e) => { process.stderr.write(String(e && e.stack || e)); process.exit(1); });"
    )
    r = subprocess.run([NODE, "-e", script], input=json.dumps(entrada), capture_output=True,
                       text=True, encoding="utf-8", check=False)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


# --- detectar y cliente ---------------------------------------------------------------------------

def test_detectar():
    r = js("""return [
      S.detectar({protocol: "file:", hostname: "", search: ""}),
      S.detectar({protocol: "http:", hostname: "127.0.0.1", search: "?t=abc"}),
      S.detectar({protocol: "http:", hostname: "127.0.0.1", search: ""}),
      S.detectar({protocol: "http:", hostname: "localhost", search: "?t=abc"}),
      S.detectar({protocol: "https:", hostname: "127.0.0.1", search: "?t=abc"}),
      S.detectar(null)];""")
    assert r == [None, {"token": "abc"}, None, None, None, None]


def test_cliente_manda_el_token_y_post_json():
    r = js("""
      const vistos = [];
      const fetchFalso = async (ruta, op) => { vistos.push({ruta, op}); return {ok: true, json: async () => ({ok: 1})}; };
      const c = S.crearCliente({token: "TK"}, fetchFalso);
      await c.estado(); await c.elegirDxf(); await c.tarea("t-3"); await c.cancelar("t-3");
      await c.reiniciar(); await c.latido();
      return vistos;""")
    assert [(v["ruta"], v["op"]["method"]) for v in r] == [
        ("/api/estado", "GET"), ("/api/dxf/elegir", "POST"), ("/api/tareas/t-3", "GET"),
        ("/api/tareas/t-3/cancelar", "POST"), ("/api/trabajador/reiniciar", "POST"),
        ("/api/latido", "POST")]
    for v in r:
        assert v["op"]["headers"]["X-Componedor-Token"] == "TK"
        assert v["op"]["cache"] == "no-store"
        if v["op"]["method"] == "POST":
            assert v["op"]["headers"]["Content-Type"] == "application/json"
            assert v["op"]["body"] == "{}"
        else:
            assert "body" not in v["op"]


def test_cliente_vista_previa_y_volver_a_cargar():
    """Etapa 2: lo único que va en un cuerpo es el ref; el PNG se baja con el token (blob)."""
    r = js("""
      const vistos = [];
      const fetchFalso = async (ruta, op) => { vistos.push({ruta, op});
        return {ok: true, json: async () => ({ok: 1}), blob: async () => "BLOB"}; };
      const c = S.crearCliente({token: "TK"}, fetchFalso);
      const png = await c.png("/api/previas/t-4");
      await c.previa("Pilar Ñ#2"); await c.recargarDxf();
      await c.exportar([{id: "B", handle: "1A"}]); await c.detener(); await c.exportados();
      return {vistos, png};""")
    assert r["png"] == "BLOB"
    assert [(v["ruta"], v["op"]["method"], v["op"].get("body")) for v in r["vistos"]] == [
        ("/api/previas/t-4", "GET", None),
        ("/api/previa", "POST", '{"ref":"Pilar Ñ#2"}'),
        ("/api/dxf/recargar", "POST", "{}"),
        ("/api/exportar", "POST", '{"bloques":[{"id":"B","handle":"1A"}]}'),
        ("/api/trabajador/detener", "POST", "{}"),
        ("/api/exportados", "GET", None)]
    assert all(v["op"]["headers"]["X-Componedor-Token"] == "TK" for v in r["vistos"])


def test_cliente_errores():
    r = js("""
      const errores = [];
      const casos = [
        async () => ({ok: false, status: 409, json: async () => ({error: "Ya hay un cuadro abierto."})}),
        async () => ({ok: false, status: 500, json: async () => { throw new Error("no json"); }}),
        async () => { throw new TypeError("Failed to fetch"); },
      ];
      for (const f of casos) {
        try { await S.crearCliente({token: "x"}, f).estado(); }
        catch (e) { errores.push([e instanceof S.ErrorServidor, e.estadoHttp, e.message]); }
      }
      return errores;""")
    assert r[0] == [True, 409, "Ya hay un cuadro abierto."]
    assert r[1] == [True, 500, "Error 500 del servidor."]
    assert r[2][:2] == [True, 0] and "se cerró la ventana de «Abrir editor.bat»" in r[2][2]


def test_seguir_tarea_hasta_que_termina():
    r = js("""
      const fotos = [{estado: "en_cola"}, {estado: "en_curso", avance: {percent: 50}},
                     {estado: "terminada", resultado: 7}];
      let i = 0; const vistas = []; const pausas = [];
      const cliente = {tarea: async (id) => Object.assign({id}, fotos[i++])};
      const fin = await S.seguirTarea(cliente, "t-1", (f) => vistas.push(f.estado), 250,
                                      async (ms) => pausas.push(ms));
      return {fin, vistas, pausas};""")
    assert r["fin"] == {"id": "t-1", "estado": "terminada", "resultado": 7}
    assert r["vistas"] == ["en_cola", "en_curso", "terminada"] and r["pausas"] == [250, 250]


# --- textos ---------------------------------------------------------------------------------------

def test_textos_de_un_bloque():
    carpeta = catalogo_dxf(respuesta(
        bloque("P", ref="P#2", occurrence=2, total_occurrences=3, layer="ESTRUCTURA"),
        bloque("aprox", bounds={"min": [0, 0], "max": [1, 1], "exact": False}),
        bloque("sin", size_m=None, units={"name": "m", "verified": False}),
        bloque("enorme", tamano=(200000.0, 1.0))), ZONA_A1)
    r = js("return entrada.bloques.map(D.lineasBloque);", carpeta)
    assert r[0] == ["ocurrencia 2 de 3 · capa ESTRUCTURA",
                    "10,000 × 4,000 m · unidades: m (verificadas)",
                    "Escala sugerida 1:50 · página 210,0 × 90,0 mm"]
    assert r[1][-1] == "Escala sugerida 1:50 · página ≤ 210,0 × 90,0 mm"  # caja aproximada
    assert r[2] == ["capa 0", "tamaño real desconocido · unidades: m, sin verificar"]
    assert r[3] == ["capa 0", "200000,000 × 1,000 m · unidades: m (verificadas)"]  # sin escala


def test_textos_de_la_carpeta():
    carpeta = catalogo_dxf(respuesta(bloque(), bloque("b")), ZONA_A1)
    r = js("""return [D.resumenDxf(entrada), D.detalleDxf(entrada),
                      D.tamanoArchivo(512), D.tamanoArchivo(20480), D.tamanoArchivo(2947027543),
                      D.tamanoArchivo(null), D.textoUnidades(null)];""", carpeta)
    assert r == ["2 bloques", "6,5 MB · unidades: m (verificadas) · margen 5 mm · leído en 1,5 s",
                 "512 bytes", "20 KB", "2,74 GB", "tamaño desconocido", "unidades desconocidas"]


def test_texto_del_avance_y_del_error():
    r = js("""return [
      D.textoAvance({estado: "en_cola", avance: {}}),
      D.textoAvance({estado: "en_curso", avance: {stage: "read", percent: 41.6}}),
      D.textoAvance({estado: "en_curso", avance: {message: "Dibujando 61 200 de 156 749", percent: 3},
                     cancelando: true}),
      D.textoAvance({estado: "en_curso", avance: {stage: "read", percent: 20}, sin_noticias_s: 45.2}),
      D.textoError({error: {mensaje: "No existe el DXF.", consejo: "Revise la ruta."}}),
      D.textoError({error: {mensaje: "Cancelado.", consejo: null}}),
      D.textoError({})];""")
    assert r[0] == "En espera"
    assert r[1] == "Leyendo el DXF — 42 %"
    assert r[2] == "Dibujando 61 200 de 156 749 — 3 % (cancelando…)"
    assert r[3].startswith("Leyendo el DXF — 20 % · sin noticias del trabajador hace 45 s")
    assert r[4:] == ["No existe el DXF. Revise la ruta.", "Cancelado.", "La tarea no terminó."]


# --- editor.html ----------------------------------------------------------------------------------

def test_editor_html_trae_el_boton_y_los_js_del_dxf(tmp_path):
    from conftest import crear_paquete_real, crear_plantilla_sintetica, escribir_formato

    from componedor.editor_html import generar_editor

    escribir_formato(tmp_path / "formato.json",
                     plantilla=crear_plantilla_sintetica(tmp_path / "rotulo.pdf"))
    crear_paquete_real(tmp_path / "input", "a")
    html = generar_editor(tmp_path / "input", tmp_path / "formato.json",
                          tmp_path / "editor").read_text(encoding="utf-8")
    assert '<button id="btn-cargar-dxf" type="button" disabled>Cargar DXF</button>' in html
    assert '<div id="panel-dxf" class="panel-dxf" hidden></div>' in html
    for funcion in ("function detectar", "function lineasBloque", "function tarjetaBloque",
                    "function paginaMm", "function dibujarBloque", "function pedirPrevia",
                    "function pedidosExportar", "function aplicarExportado",
                    "function seccionExportar"):
        assert funcion in html
    # editor_bloques.js va antes que la lógica (que lo usa para el plano versión 3).
    assert html.index("function paginaMm") < html.index("function serializarPlano")
    assert not re.search(r"https?://", html)  # tampoco ahora hay URLs en el HTML
