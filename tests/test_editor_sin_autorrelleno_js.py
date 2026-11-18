"""Que el navegador no rellene solo los cuadros del editor (editor_sin_autorrelleno.js, en Node
con un DOM mínimo de mentira) y que el módulo vaya antes que los demás en editor.html."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

import componedor

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node no está instalado")
MODULO = Path(componedor.__file__).parent / "editor" / "editor_sin_autorrelleno.js"

DOM_FALSO = """
class Nodo {
  constructor(tag, hijos = []) { this.nodeType = 1; this.tagName = tag; this.hijos = hijos; this.attrs = {}; }
  matches(sel) { return sel.split(",").map((s) => s.trim().toUpperCase()).includes(this.tagName); }
  querySelectorAll(sel) { const r = []; const ver = (n) => n.hijos.forEach((h) => { if (h.matches(sel)) r.push(h); ver(h); }); ver(this); return r; }
  getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }
  setAttribute(k, v) { this.attrs[k] = v; }
}
"""


def js(codigo: str):
    script = (f"const A = require({json.dumps(str(MODULO))});" + DOM_FALSO +
              f"const salida = (function () {{ {codigo} }})();"
              "process.stdout.write(JSON.stringify(salida));")
    r = subprocess.run([NODE, "-e", script], capture_output=True, text=True, encoding="utf-8",
                       check=False)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_apaga_los_cuadros_que_hay_y_los_que_se_agregan():
    r = js("""
      const campo = new Nodo("INPUT"), nota = new Nodo("TEXTAREA"), lista = new Nodo("SELECT");
      const panel = new Nodo("DIV", [campo, new Nodo("DIV", [nota]), lista]);
      const raiz = new Nodo("HTML", [panel]);
      let alObservar = null;
      class Observador { constructor(f) { alObservar = f; } observe() {} }
      A.vigilar({documentElement: raiz}, Observador);
      const antes = [campo, nota, lista].map((c) => c.getAttribute("autocomplete"));
      const nuevo = new Nodo("INPUT"), envoltorio = new Nodo("DIV", [new Nodo("INPUT")]);
      alObservar([{addedNodes: [nuevo, envoltorio, {nodeType: 3}]}]);  // también texto suelto
      return {antes, nuevo: nuevo.getAttribute("autocomplete"),
              dentro: envoltorio.hijos[0].getAttribute("autocomplete"),
              otraVez: A.apagar(panel), div: panel.getAttribute("autocomplete")};""")
    assert r == {"antes": ["off", "off", "off"], "nuevo": "off", "dentro": "off", "otraVez": 0,
                 "div": None}


def test_va_antes_que_los_demas_en_el_editor(tmp_path):
    from conftest import crear_paquete_real, crear_plantilla_sintetica, escribir_formato

    from componedor.editor_html import generar_editor

    escribir_formato(tmp_path / "formato.json",
                     plantilla=crear_plantilla_sintetica(tmp_path / "rotulo.pdf"))
    crear_paquete_real(tmp_path / "input", "a")
    html = generar_editor(tmp_path / "input", tmp_path / "formato.json",
                          tmp_path / "editor").read_text(encoding="utf-8")
    primero = html.index("function vigilar(documento")
    for otro in ("function paginaMm", "function serializarPlano", "EditorPanelRotulo",
                 "function dibujarBloque"):
        assert primero < html.index(otro)
