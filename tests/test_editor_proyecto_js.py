"""Proyecto de varias hojas en el editor (plano versión 8, subfase 8b), en Node: leer y escribir
la versión 8 (cada hoja con la lógica de siempre), que Python lo lea igual, los planos viejos como
una hoja, automáticos por posición y nombres."""

import json

from test_editor_bloques_js import CATALOGO, SHA, entorno_editor  # noqa: F401 (fixture)
from test_editor_js import js

import componedor
from componedor.plano_proyecto import leer_proyecto

PROYECTO_JS = str(__import__("pathlib").Path(componedor.__path__[0]) / "editor" / "editor_proyecto.js")
RECT = [4736058.98, 2234185.8, 4736059.65, 2234186.45]


def _p(codigo, entrada):
    return js("const P = require(entrada.modulo); " + codigo, {"modulo": PROYECTO_JS, **entrada})


def _proyecto(datos):
    d = datos["detalles"][0]
    zona = {"dxf": "d1", "nombre": "Zona_01", "zona": RECT, "capas": None, "excluir": None,
            "escala": "1:20", "centro_mm": [342.55, 297.0], "tamano_m": [0.67, 0.65]}
    return {"version": 8, "formato": datos["formato"],
            "dxf": [{"id": "d1", "archivo": "GUAMO_prueba.dxf", "sha256": SHA, "margen_mm": 5}],
            "hojas": [
                {"nombre": "Planta", "detalles": [{"id": "a", "manifiesto": d["manifiesto"], "posicion_mm": [30, 40]}],
                 "rotulo": {"titulo": "PLANTA", "no_plano": "ERCO-PL-106"}},
                {"nombre": "Perfil", "detalles": [], "zonas": [zona], "rotulo": {"titulo": "PERFIL"}},
                {"nombre": "Vacía", "detalles": [], "rotulo": {"hoja": "C"},
                 "copiado_de": {"hoja": "Planta", "revisar": ["notas"]}}]}


def test_leer_y_escribir_igual(entorno_editor):  # noqa: F811
    carpeta, datos = entorno_editor
    proyecto = _proyecto(datos)
    r = _p("""
      const l = P.leerProyecto(JSON.stringify(entrada.proyecto), entrada.datos);
      const hojas = l.hojas.map((h) => ({nombre: h.nombre, colocaciones: h.resultado.colocaciones,
        extra: {original: h.resultado.original, rotulo: h.resultado.rotulo, copiado: h.resultado.copiado}}));
      return {errores: l.errores, nombres: l.hojas.map((h) => h.nombre),
        cuantas: l.hojas.map((h) => h.resultado.colocaciones.length),
        zona: l.hojas[1].resultado.colocaciones[0].bloque.zona.rect,
        texto: P.serializarProyecto(hojas, entrada.datos, {})};""", {"proyecto": proyecto, "datos": datos})
    assert r["errores"] == [] and r["nombres"] == ["Planta", "Perfil", "Vacía"]
    assert r["cuantas"] == [1, 1, 0] and r["zona"] == RECT  # la zona borrador es de la hoja 2
    salida = json.loads(r["texto"])
    assert salida["version"] == 8 and [h["nombre"] for h in salida["hojas"]] == ["Planta", "Perfil", "Vacía"]
    assert salida["dxf"] == [{"id": "d1", "archivo": "GUAMO_prueba.dxf", "sha256": SHA, "margen_mm": 5}]
    assert salida["hojas"][1]["zonas"][0]["dxf"] == "d1" and "zonas" not in salida["hojas"][0]
    assert salida["hojas"][2]["copiado_de"] == {"hoja": "Planta", "revisar": ["notas"]}
    assert salida["hojas"][0]["rotulo"] == {"titulo": "PLANTA", "no_plano": "ERCO-PL-106"}
    # Python lo lee igual.
    ruta = carpeta / "editor" / "obra.json"
    ruta.write_text(r["texto"], encoding="utf-8")
    p = leer_proyecto(ruta)
    assert p.problemas == [] and [h.nombre for h in p.hojas] == ["Planta", "Perfil", "Vacía"]
    assert [z.nombre for z in p.hojas[1].plano.borradores] == ["Zona_01"]


def test_errores_y_planos_viejos(entorno_editor):  # noqa: F811
    _, datos = entorno_editor
    proyecto = _proyecto(datos)
    proyecto["hojas"][2]["nombre"] = "planta"
    proyecto["hojas"][1]["zonas"].append(dict(proyecto["hojas"][1]["zonas"][0]))
    viejo = {"version": 1, "detalles": [{"id": "x", "manifiesto": datos["detalles"][0]["manifiesto"], "posicion_mm": [30, 40]}]}
    r = _p("""return [P.leerProyecto(JSON.stringify(entrada.proyecto), entrada.datos),
      P.leerProyecto(JSON.stringify(entrada.viejo), entrada.datos)].map((l) => ({errores: l.errores, version: l.version,
      nombres: l.hojas.map((h) => h.nombre)}));""", {"proyecto": proyecto, "viejo": viejo, "datos": datos})
    malo, uno = r
    assert any("Hoja 3 («planta»): el nombre está repetido" in e for e in malo["errores"])
    assert any("la zona «Zona_01» ya es de la hoja 2" in e for e in malo["errores"])
    assert malo["nombres"] == []
    assert uno == {"errores": [], "version": 1, "nombres": ["Hoja 1"]}  # un plano viejo: una hoja


def test_automaticos_y_nombres():
    r = _p("""return {
      auto: [0, 1, 2].map((i) => P.automaticosDeLista([{no_plano: "PL-106"}, {}, {hoja: "C"}], i,
        {hoja: "hoja_actual", de: "total_hojas", no_plano: "numero_siguiente"})),
      nombres: [P.nombreHojaNueva(["Planta"]), P.nombreHojaNueva(["Hoja 2", "hoja 3"])],
      guardar: [P.nombreParaGuardar("Pruebadecambio.json", true), P.nombreParaGuardar("Obra.hojas.json", true),
        P.nombreParaGuardar("Obra.json", false), P.nombreParaGuardar(null, false)],
      numero: [P.siguienteNumero("A-009"), P.siguienteNumero("X")],
      zona: P.nombreZonaLibre("Zona_01", new Set(["Zona_01", "Zona_01_2"]))};""", {})
    assert r["auto"] == [{"hoja": "1", "de": "3"}, {"hoja": "2", "de": "3", "no_plano": "PL-107"},
                         {"de": "3", "no_plano": "PL-108"}]
    assert r["nombres"] == ["Hoja 2", "Hoja 4"]
    assert r["guardar"] == ["Pruebadecambio_proyecto.json", "Obra_proyecto.json", "Obra.json", "proyecto.json"]
    assert r["numero"] == ["A-010", None] and r["zona"] == "Zona_01_3"
