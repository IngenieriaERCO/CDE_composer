"""Muestras de línea y relleno en el editor (editor_muestras.js y editor_convenciones.js,
subfase 9a), con Node, comparando con Python:

- los MISMOS errores que `rotulo._convenciones` / `muestras_leyenda.leer_muestra`;
- la misma ubicación en la casilla que `colocar_muestra`;
- la lista: valores por defecto, qué se guarda, ida y vuelta sin tocar idéntica, y los
  renglones de símbolo de siempre siguen igual."""

import json

import pytest
from test_editor_convenciones_js import CARPETA_JS, VALIDAR, _python, entorno, js  # noqa: F401

from componedor.muestras_leyenda import Muestra, colocar_muestra

PARECIDO = 1e-9


@pytest.mark.parametrize("valor", [
    [{"tipo": "circulo", "descripcion": "X"}, {"tipo": 3}],
    [{"tipo": "linea", "color": "rojo", "trazo": "punteada", "grosor_mm": 0.01, "descripcion": "A"}],
    [{"tipo": "linea", "grosor_mm": True, "descripcion": "A"}, {"tipo": "linea", "grosor_mm": 2.5, "descripcion": "B"}],
    [{"tipo": "linea"}, {"tipo": "relleno", "descripcion": "  "}, {"tipo": "relleno", "descripcion": ["", " "]}],
    [{"tipo": "relleno", "descripcion": "A", "opacidad": 0, "simbolo": "corte"},
     {"tipo": "relleno", "descripcion": "B", "color": "#12345"}],
    [{"tipo": "simbolo", "simbolo": "corte", "color": "#FF0000"}, {"tipo": "linea", "descripcion": "中"}],
    [{"tipo": "linea", "descripcion": ["UNA", "DOS", "TRES"]}, {"tipo": "relleno", "descripcion": True}],
    [{"tipo": "linea", "descripcion": "L"}] * 25,
])
def test_los_mismos_errores_que_python(entorno, valor):  # noqa: F811
    problemas = _python(entorno, valor)
    assert problemas, "el caso debe tener problemas"
    r = js(VALIDAR, {"datos": entorno["datos"], "valor": valor})
    assert sorted(r["errores"]) == sorted(problemas)


@pytest.mark.parametrize("valor", [
    [{"tipo": "linea", "descripcion": "RED ELÉCTRICA", "color": "#ff0000", "grosor_mm": 0.35, "trazo": "discontinua"},
     {"tipo": "relleno", "descripcion": ["ZONA", "VERDE"], "opacidad": 0.5},
     {"simbolo": "corte"}, {"tipo": "simbolo", "simbolo": "panel"},
     {"tipo": "linea", "descripcion": "LÍMITE"}, {"tipo": "linea", "descripcion": "LÍMITE"}],
])
def test_validos_sin_problemas_en_los_dos(entorno, valor):  # noqa: F811
    assert _python(entorno, valor) == []
    assert js(VALIDAR, {"datos": entorno["datos"], "valor": valor}) == {"errores": [], "avisos": []}


@pytest.mark.parametrize("muestra, casilla", [
    (Muestra("linea", "#000000"), (672.4, 249.39, 693.84, 259.88)),
    (Muestra("relleno", "#808080"), (750.32, 137.71, 771.82, 147.28)),
    (Muestra("linea", "#000000"), (0, 0, 10, 4)),
    (Muestra("relleno", "#000000"), (0, 0, 10, 4)),
])
def test_misma_ubicacion_que_python(muestra, casilla):
    r = js("const MU = require(require('path').join(" + json.dumps(str(CARPETA_JS)) + ", 'editor_muestras.js'));"
           "return MU.colocarMuestra(entrada.m, 7, entrada.c, 0.6);",
           {"m": {"tipo": muestra.tipo, "color": muestra.color}, "c": list(casilla)})
    esperado = colocar_muestra(muestra, 7, casilla, 0.6)
    assert r["posicion"] == 7 and r["casilla"] == list(casilla)
    assert r["dibujo_mm"] == pytest.approx(list(esperado.dibujo), abs=PARECIDO)


def test_nuevas_con_valores_por_defecto_y_lo_que_se_guarda(entorno):  # noqa: F811
    r = js("""const d = entrada.datos.rotulo;
        let items = C.lista(undefined, d.simbolos).items;
        items = C.agregarMuestra(items, "linea", 24).items;
        items = C.agregarMuestra(items, "relleno", 24).items;
        const nuevas = C.convencionesParaGuardar(items, d.simbolos);
        items[0] = C.cambiarDescripcion(items[0], "RED DE MEDIA TENSIÓN", d.simbolos);
        items[0] = C.cambiarMuestra(items[0], {color: "#FF0000", grosor_mm: 0.5, trazo: "discontinua"});
        items[1] = C.cambiarDescripcion(items[1], "AGUA\\nSUPERFICIAL", d.simbolos);
        items[1] = C.cambiarMuestra(items[1], {opacidad: 0.4});
        const llenas = C.convencionesParaGuardar(items, d.simbolos);
        const tope = C.agregarMuestra(new Array(24).fill(items[0]), "linea", 24);
        return {nuevas, llenas, aviso: tope.aviso, cuantas: tope.items.length,
                errores: C.validarConvenciones(nuevas, d.definicion, d.fuente, d.simbolos).errores};""",
           {"datos": entorno["datos"]})
    assert r["nuevas"] == [{"tipo": "linea", "color": "#000000", "grosor_mm": 0.25, "trazo": "continua"},
                           {"tipo": "relleno", "color": "#808080"}]
    # Una muestra recién agregada pide su descripción (no tiene por defecto).
    assert r["errores"] == [
        ("rotulo.convenciones[0].descripcion: falta la descripción (una línea o un relleno no tiene "
        "descripción por defecto)"),
        ("rotulo.convenciones[1].descripcion: falta la descripción (una línea o un relleno no tiene "
        "descripción por defecto)")]
    assert r["llenas"] == [
        {"tipo": "linea", "descripcion": "RED DE MEDIA TENSIÓN", "color": "#FF0000", "grosor_mm": 0.5,
         "trazo": "discontinua"},
        {"tipo": "relleno", "descripcion": "AGUA\nSUPERFICIAL", "color": "#808080", "opacidad": 0.4}]
    assert _python(entorno, r["llenas"]) == []
    assert r["cuantas"] == 24 and r["aviso"].startswith("La tabla de convenciones está llena: admite 24")


def test_sin_tocar_identico_y_lista_con_valores_puestos(entorno):  # noqa: F811
    valor = [{"tipo": "linea", "descripcion": "A", "color": "#00ff00"},  # sin grosor ni trazo
             {"simbolo": "corte", "descripcion": "MÍO"}, {"tipo": "relleno", "descripcion": ["B", "C"]}]
    r = js("""const d = entrada.datos.rotulo;
        const l = C.lista(entrada.valor, d.simbolos);
        return {editable: l.editable, items: l.items.map((x) => ({tipo: x.tipo, color: x.color,
                grosor_mm: x.grosor_mm, trazo: x.trazo, opacidad: x.opacidad, simbolo: x.simbolo})),
                guardado: C.convencionesParaGuardar(l.items, d.simbolos),
                malo: C.lista([{"tipo": "linea", "descripcion": "A", "color": "verde"}], d.simbolos).editable};""",
           {"datos": entorno["datos"], "valor": valor})
    assert r["editable"] and r["guardado"] == valor
    assert r["items"][0] == {"tipo": "linea", "color": "#00FF00", "grosor_mm": 0.25, "trazo": "continua"}
    assert r["items"][1] == {"tipo": "simbolo", "simbolo": "corte"}
    assert r["items"][2] == {"tipo": "relleno", "color": "#808080", "opacidad": 1}
    # Un valor que el formulario no sabe mostrar (color «verde») deja la lista sin editar, como antes.
    assert r["malo"] is False
