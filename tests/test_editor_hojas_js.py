"""Varias hojas en el editor (plano versión 7), en Node: la hoja nueva copia el rótulo sin título
ni automáticos, con notas, convenciones y revisiones «por revisar»; el editor lee y escribe la
versión 7 y Python la lee igual; los planos viejos abren como antes."""

import json

from test_editor_bloques_js import entorno_editor  # noqa: F401 (fixture)
from test_editor_js import js

from componedor.plano import leer_plano

DEF = {"campos": {
    "titulo": {"tipo": "texto"}, "hoja": {"tipo": "texto", "automatico": "hoja_actual"},
    "de": {"tipo": "texto", "automatico": "total_hojas"},
    "no_plano": {"tipo": "texto", "automatico": "numero_siguiente"},
    "escala": {"tipo": "texto", "calculado": "escala_comun"},
    "notas": {"tipo": "notas"}, "convenciones": {"tipo": "convenciones"},
    "revisiones": {"tipo": "tabla"}, "firmas": {"tipo": "tabla"}, "este": {"tipo": "texto"}}}
ROTULO = {"titulo": "PLANTA GENERAL", "hoja": "1", "de": "1", "no_plano": "ERCO-PL-106",
          "notas": {"adicionales": ["NOTA 1"]}, "revisiones": [{"ver": "0", "fecha": "2026-11-26"}],
          "firmas": {"dibujo": {"nombre": "LUIS"}}, "este": "4.700.000"}


def _h(codigo, entrada=None):
    return js("const H = require(entrada.hojas); " + codigo,
              {"hojas": str(__import__("componedor").__path__[0] + "/editor/editor_hojas.js"),
               **(entrada or {})})


def test_hoja_nueva():
    r = _h("""return H.planoNuevaHoja({version: 5, formato: "../formatos/A1_ERCO.json", plantilla: null,
        detalles: [{id: "a"}], rotulo: entrada.rotulo, rosa_vientos: {visible: false},
        ortofoto: {archivo: "f.tif"}, dxf: [{id: "d1"}]}, "Plano.json", entrada.def);""",
           {"rotulo": ROTULO, "def": DEF})
    plano = r["plano"]
    assert plano["version"] == 7 and plano["detalles"] == [] and "dxf" not in plano
    assert plano["rosa_vientos"] == {"visible": False} and plano["ortofoto"] == {"archivo": "f.tif"}
    # Sin título ni automáticos; firmas, coordenadas, notas y revisiones copiadas.
    assert plano["rotulo"] == {"notas": {"adicionales": ["NOTA 1"]}, "revisiones": ROTULO["revisiones"],
                               "firmas": {"dibujo": {"nombre": "LUIS"}}, "este": "4.700.000"}
    # Por revisar: solo los que tenían algo (sin convenciones).
    assert r["revisar"] == ["notas", "revisiones"]
    assert plano["copiado_de"] == {"hoja": "Plano.json", "revisar": ["notas", "revisiones"]}


def test_nombres_y_automaticos():
    r = _h("""return [H.nombreNuevaHoja("Plano", ["Plano.json"]), H.nombreNuevaHoja("Plano", ["plano_02.json", "x.json"]),
        H.camposAutomaticos(entrada.def), H.sinHojaNiDe(entrada.rotulo, entrada.def).hoja,
        H.sinHojaNiDe(entrada.rotulo, entrada.def).no_plano,
        H.porRevisar(["notas", "revisiones"], {notas: 1, revisiones: [1]}, (c) => (c === "notas" ? 2 : [1]))];""",
           {"rotulo": ROTULO, "def": DEF})
    assert r[0] == "Plano_02.json" and r[1] == "Plano_03.json"
    assert r[2] == {"hoja": "hoja_actual", "de": "total_hojas", "no_plano": "numero_siguiente"}
    assert r[3] is None and r[4] == "ERCO-PL-106"  # el número de la primera hoja se queda
    assert r[5] == ["revisiones"]  # las notas se cambiaron: ya no están por revisar


def test_version_7_en_el_editor_y_en_python(entorno_editor):  # noqa: F811
    carpeta, datos = entorno_editor
    hoja = {"version": 7, "formato": datos["formato"], "detalles": [], "rotulo": {"este": "1"},
            "copiado_de": {"hoja": "Plano.json", "revisar": ["notas"]}}
    r = js("""const l = L.leerPlano(JSON.stringify(entrada.hoja), entrada.datos);
      const igual = L.serializarPlano(l.colocaciones, entrada.datos, {original: l.original, copiado: l.copiado,
        rotulo: entrada.hoja.rotulo});
      const revisado = JSON.parse(L.serializarPlano(l.colocaciones, entrada.datos, {original: l.original,
        copiado: {hoja: "Plano.json", revisar: []}, rotulo: entrada.hoja.rotulo}));
      const viejo = L.leerPlano(JSON.stringify(Object.assign({}, entrada.hoja, {version: 6})), entrada.datos);
      return {errores: l.errores, copiado: l.copiado, igual: JSON.parse(igual), revisado, viejo: viejo.errores};""",
           {"hoja": hoja, "datos": datos})
    assert r["errores"] == [] and r["copiado"] == {"hoja": "Plano.json", "revisar": ["notas"]}
    assert r["igual"]["version"] == 7 and r["igual"]["copiado_de"] == hoja["copiado_de"]
    assert r["igual"]["detalles"] == []
    # Revisado todo: sin "copiado_de", y sigue en la 7 (hoja vacía).
    assert "copiado_de" not in r["revisado"] and r["revisado"]["version"] == 7
    assert any("copiado_de: solo existe en la versión 7" in e for e in r["viejo"])
    ruta = carpeta / "editor" / "hoja.json"
    ruta.write_text(json.dumps(r["igual"]), encoding="utf-8")
    leido = leer_plano(ruta)
    assert leido.version == 7 and leido.detalles == () and leido.revisar == ("notas",)
