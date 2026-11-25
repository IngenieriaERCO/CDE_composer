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
                    "Escala sugerida 1:20 · página 510,0 × 210,0 mm"]
    assert r[1][-1] == "Escala sugerida 1:20 · página ≤ 510,0 × 210,0 mm"  # caja aproximada
    assert r[2] == ["capa 0", "tamaño real desconocido · unidades: m, sin verificar"]
    assert r[3] == ["capa 0", "200000,000 × 1,000 m · unidades: m (verificadas)"]  # sin escala


def test_textos_de_la_carpeta():
    carpeta = catalogo_dxf(respuesta(bloque(), bloque("b")), ZONA_A1)
    r = js("""return [D.resumenDxf(entrada), D.detalleDxf(entrada),
                      D.tamanoArchivo(512), D.tamanoArchivo(20480), D.tamanoArchivo(2947027543),
                      D.tamanoArchivo(null), D.textoUnidades(null)];""", carpeta)
    assert r == ["2 bloques", "6,5 MB · unidades: m (verificadas) · margen 5 mm · leído en 1,5 s",
                 "512 bytes", "20 KB", "2,74 GB", "tamaño desconocido", "unidades desconocidas"]


def _anonimo(handle, capa="I1.M1.PV1", visibles=250, nombre="*U76"):
    return bloque(nombre, ref=f"{nombre}#1", handle=handle, layer=capa, anonymous=True,
                  label=f"{capa}_{handle}", visible_entities=visibles,
                  file_stem=f"{capa}_{handle}")


def _carpeta_con_anonimos(omitidos=0, umbral=100):
    pequenos = [{"name": f"*U{i}", "anonymous": True, "visible_entities": 5} for i in range(omitidos)]
    return catalogo_dxf(respuesta(bloque("Viga", anonymous=False, label="Viga"),
                                  _anonimo("12900", visibles=12345),
                                  _anonimo("12A0", capa="Tablas Cálculo", nombre="*U80"),
                                  _anonimo("12900B", capa="I1.M2.PV1", nombre="*U81"),
                                  omitted=pequenos),
                        ZONA_A1, anonimos_min=umbral)


def test_textos_de_un_anonimo():
    carpeta = _carpeta_con_anonimos()
    r = js("""return entrada.bloques.map((b) => [D.nombreBloque(b), D.lineasBloque(b)]);""", carpeta)
    assert r[0] == ["Viga", ["capa 0", "10,000 × 4,000 m · unidades: m (verificadas)",
                             "Escala sugerida 1:20 · página 510,0 × 210,0 mm"]]
    # Se muestra por la etiqueta (capa + handle); el *U y las entidades visibles, en la línea.
    assert r[1] == ["I1.M1.PV1_12900", ["bloque anónimo *U76 · 12 345 entidades visibles",
                                        "10,000 × 4,000 m · unidades: m (verificadas)",
                                        "Escala sugerida 1:20 · página 510,0 × 210,0 mm"]]
    assert js("return [D.nombreBloque({nombre: '*U1'}), D.nombreBloque(null)];") == ["*U1", "?"]


def test_separar_y_resumen_con_anonimos():
    carpeta = _carpeta_con_anonimos()
    r = js("""const s = D.separarBloques(entrada);
              return [s.nombrados.map(D.nombreBloque), s.anonimos.map(D.nombreBloque),
                      D.resumenDxf(entrada), D.separarBloques(null)];""", carpeta)
    assert r == [["Viga"], ["I1.M1.PV1_12900", "Tablas Cálculo_12A0", "I1.M2.PV1_12900B"],
                 "1 bloque · 3 anónimos", {"nombrados": [], "anonimos": []}]


@pytest.mark.parametrize("filtro, esperados", [
    ("", ["I1.M1.PV1_12900", "Tablas Cálculo_12A0", "I1.M2.PV1_12900B"]),
    ("   ", ["I1.M1.PV1_12900", "Tablas Cálculo_12A0", "I1.M2.PV1_12900B"]),
    ("12900", ["I1.M1.PV1_12900", "I1.M2.PV1_12900B"]),
    ("pv1 m2", ["I1.M2.PV1_12900B"]),          # todas las palabras, en cualquier orden
    ("CALCULO", ["Tablas Cálculo_12A0"]),      # sin mayúsculas ni tildes
    ("*u80", ["Tablas Cálculo_12A0"]),         # también por el *U
    ("12a0", ["Tablas Cálculo_12A0"]),         # por el handle
    ("mesa", []),
])
def test_filtro_de_anonimos(filtro, esperados):
    carpeta = _carpeta_con_anonimos()
    r = js("""return D.filtrarBloques(D.separarBloques(entrada.c).anonimos, entrada.f)
                .map(D.nombreBloque);""", {"c": carpeta, "f": filtro})
    assert r == esperados


def test_textos_de_la_subseccion_de_anonimos():
    carpeta = _carpeta_con_anonimos(omitidos=3318)
    t = js("return [D.textosAnonimos(entrada), D.textosAnonimos(entrada, 2, 2), "
           "D.textosAnonimos(entrada, 3, 1), D.LIMITE_TARJETAS];", carpeta)
    assert t[0]["titulo"] == "Anónimos (opcionales) (3)"
    assert t[0]["explicacion"].startswith(
        "Bloques anónimos (*U) del Model Space con 100 entidades visibles o más")
    assert t[0]["pequenos"] == ("Otros 3 318 anónimos más pequeños no se ofrecen (menos de "
                                "100 entidades visibles): etiquetas, cotas y piezas que AutoCAD o "
                                "Civil 3D crean por montones.")
    assert t[0]["mostrando"] is None
    assert t[1]["mostrando"] == "Mostrando 2 de 2 que coinciden (3 en total)."
    assert t[2]["mostrando"] == "Mostrando 1 de 3: escriba en el filtro para encontrar los demás."
    assert t[3] == 200
    # Uno solo pequeño, y sin umbral conocido.
    carpeta = _carpeta_con_anonimos(omitidos=1, umbral=None)
    t = js("return D.textosAnonimos(entrada);", carpeta)
    assert t["pequenos"].startswith("Otro anónimo más pequeño no se ofrece: etiquetas")
    assert "que el exportador ofrece" in t["explicacion"]
    # Sin anónimos pequeños: no hay texto.
    assert js("return D.textosAnonimos(entrada).pequenos;", _carpeta_con_anonimos()) is None


def test_texto_del_avance_y_del_error():
    r = js("""return [
      D.textoAvance({estado: "en_cola", avance: {}}),
      D.textoAvance({estado: "en_curso", avance: {stage: "read", percent: 41.6}}),
      D.textoAvance({estado: "en_curso", avance: {message: "Dibujando 61 200 de 156 749", percent: 3},
                     cancelando: true}),
      D.textoAvance({estado: "en_curso", avance: {stage: "read", percent: 20}, sin_noticias_s: 45.2}),
      D.textoError({error: {mensaje: "No existe el DXF.", consejo: "Revise la ruta."}}),
      D.textoError({error: {mensaje: "Cancelado.", consejo: null}}),
      D.textoError({}),
      D.textoDetalle({error: {mensaje: "x", detalle: "TypeError: …", registro: "data/cache_exportador/trabajador.log"}}),
      D.textoDetalle({error: {mensaje: "x", detalle: null}})];""")
    assert r[0] == "En espera"
    assert r[1] == "Leyendo el DXF — 42 %"
    assert r[2] == "Dibujando 61 200 de 156 749 — 3 % (cancelando…)"
    assert r[3].startswith("Leyendo el DXF — 20 % · sin noticias del trabajador hace 45 s")
    assert r[4:7] == ["No existe el DXF. Revise la ruta.", "Cancelado.", "La tarea no terminó."]
    assert r[7] == "TypeError: …\n\nRegistro del trabajador: data/cache_exportador/trabajador.log"
    assert r[8] is None


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
                    "function seccionExportar", "function seccionAnonimos",
                    "function filtrarBloques", "function pintarMiniatura"):
        assert funcion in html
    # editor_bloques.js va antes que la lógica (que lo usa para el plano versión 3).
    assert html.index("function paginaMm") < html.index("function serializarPlano")
    assert not re.search(r"https?://", html)  # tampoco ahora hay URLs en el HTML


# --- vista previa preparada (exportador 1.2) -------------------------------------------------

def test_cargar_manda_el_estilo_del_editor():
    r = js("""
      const vistos = [];
      const fetchFalso = async (ruta, op) => { vistos.push([ruta, op.body]); return {ok: true, json: async () => ({})}; };
      const c = S.crearCliente({token: "TK"}, fetchFalso);
      await c.elegirDxf({ctb: "CTB_ERCO.ctb", transparencia: false});
      await c.recargarDxf({ctb: null, transparencia: true});
      await c.elegirDxf();
      return vistos;""")
    assert r == [
        ["/api/dxf/elegir", '{"estilo":{"ctb":"CTB_ERCO.ctb","transparencia":false}}'],
        ["/api/dxf/recargar", '{"estilo":{"ctb":null,"transparencia":true}}'],
        ["/api/dxf/elegir", "{}"]]


def test_texto_de_la_preparacion():
    r = js("""return [
      D.textoPreparacion(null),
      D.textoPreparacion({estado: "preparando", porcentaje: 61.4, transcurrido_s: 32.7}),
      D.textoPreparacion({estado: "preparando", porcentaje: null, transcurrido_s: 75}),
      D.textoPreparacion({estado: "lista", segundos: 49.9}),
      D.textoPreparacion({estado: "fallida", error: "MemoryError"}),
      D.textoPreparacion({estado: "detenida"}),
      D.transcurrido(3725)];""")
    nada, prep, sin_por, lista, falla, detenida, largo = r
    assert nada is None and detenida is None
    assert prep["clase"] == "preparando" and prep["porcentaje"] == 61.4
    assert prep["texto"].startswith("Preparando la vista previa del Model Space… 61 % · lleva 32 s.")
    assert "el zoom de «Zonas del modelo» irá rápido" in prep["texto"]
    assert sin_por["porcentaje"] is None and "· lleva 1 min 15 s" in sin_por["texto"]
    assert lista == {"clase": "lista", "porcentaje": 100, "texto": "Vista previa lista (se preparó "
                     "en 49 s): el zoom de «Zonas del modelo» ya va rápido."}
    assert falla["clase"] == "fallida"
    assert falla["texto"] == ("No se pudo preparar la vista previa: MemoryError. Todo sigue "
                              "funcionando; las vistas lejanas tardan más.")
    assert largo == "62 min 05 s"
