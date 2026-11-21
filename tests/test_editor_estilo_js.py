"""Estilo de impresión en el editor (JS, en Node): lo que manda el cliente (solo el nombre de
la tabla, nunca rutas), los textos, la clave de la vista previa y la comparación con el estilo
de un detalle exportado. Y que editor.html traiga el selector."""

import pytest
from test_editor_dxf_js import CARPETA_JS, NODE, js

pytestmark = pytest.mark.skipif(NODE is None, reason="Node no está instalado")

SHA = "b4a909ea7f22" + "0" * 52


def test_el_cliente_manda_el_estilo_por_nombre():
    r = js("""
      const vistos = [];
      const fetchFalso = async (ruta, op) => { vistos.push({ruta, op});
        return {ok: true, json: async () => ({ok: 1})}; };
      const c = S.crearCliente({token: "TK"}, fetchFalso);
      const estilo = {ctb: "CTB_ERCO_derivada_PRGD.ctb", transparencia: false};
      await c.estilos(); await c.previa("*U76#1", estilo); await c.exportar([{id: "B"}], estilo);
      await c.previa("*U76#1"); await c.exportar([{id: "B"}]);
      return vistos.map((v) => [v.ruta, v.op.method, v.op.body || null]);""")
    estilo = '"estilo":{"ctb":"CTB_ERCO_derivada_PRGD.ctb","transparencia":false}'
    assert r == [
        ["/api/estilos", "GET", None],
        ["/api/previa", "POST", '{"ref":"*U76#1",' + estilo + "}"],
        ["/api/exportar", "POST", '{"bloques":[{"id":"B"}],' + estilo + "}"],
        ["/api/previa", "POST", '{"ref":"*U76#1"}'],  # sin estilo: el de componedor.json
        ["/api/exportar", "POST", '{"bloques":[{"id":"B"}]}']]


def test_textos_clave_y_comparacion():
    r = js("""
      const ctb = {ctb: "CTB_ERCO_derivada_PRGD.ctb", sha256: entrada.sha, transparencia: false};
      const sin = {ctb: null, sha256: null, transparencia: true};
      return {
        textos: [D.textoEstilo(ctb), D.textoEstilo(sin), D.textoEstilo({ctb: null, transparencia: false}),
                 D.textoEstilo(null)],
        claves: [D.claveEstilo(ctb), D.claveEstilo(sin), D.claveEstilo({ctb: "A.ctb", transparencia: true}),
                 D.claveEstilo(null)],
        mismo: [D.mismoEstilo(ctb, ctb), D.mismoEstilo(sin, ctb), D.mismoEstilo(sin, sin),
                D.mismoEstilo({...ctb, sha256: "otro"}, ctb), D.mismoEstilo({...ctb, transparencia: true}, ctb),
                D.mismoEstilo(null, ctb), D.mismoEstilo(ctb, null)],
      };""", {"sha": SHA})
    assert r["textos"] == ["CTB_ERCO_derivada_PRGD.ctb (b4a909…), sin transparencia", "sin CTB",
                           "sin CTB, sin transparencia", "desconocido"]
    assert r["claves"] == ["CTB_ERCO_derivada_PRGD.ctb|t", "-|", "A.ctb|", ""]
    # Por el SHA-256: si la tabla cambió en el disco, ya no es el mismo estilo.
    assert r["mismo"] == [True, False, True, False, False, None, None]


def test_el_panel_trae_el_selector_y_manda_el_estilo():
    panel = (CARPETA_JS / "editor_panel_dxf.js").read_text(encoding="utf-8")
    for texto in ('id: "estilo-ctb"', 'id: "imprimir-transparencia"', "Sin CTB", "Imprimir transparencia",
                  "cliente.estilos()", "cliente.exportar(pedidos, vista.estilo"):
        assert texto in panel, texto
