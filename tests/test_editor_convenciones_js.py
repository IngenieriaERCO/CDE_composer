"""Convenciones del rótulo en el editor (editor_convenciones.js, subfase 4.3d), con Node:

- validación con los MISMOS textos que `rotulo._convenciones` (id inexistente con la lista de
  válidos, repetido, más de 24, campo desconocido, tipo, líneas de más, carácter sin glifo),
  comparando con `preparar_rotulo` sobre una biblioteca sintética real (extraer-simbolos);
- casilla de la leyenda por columna (1–12 izquierda, 13–24 derecha);
- marcar sin repetir, tope de 24 con aviso; "descripcion" solo si cambió; símbolo desconocido
  conservado;
- ida y vuelta sin tocar idéntica, y tras elegir, ordenar y editar solo cambia lo tocado."""

import copy
import json
import shutil
import subprocess
from pathlib import Path

import pytest

import componedor
from componedor.datos_editor import preparar_editor
from componedor.formato import cargar_formato
from componedor.fuente import cargar_fuente
from componedor.rotulo import RotuloInvalido, preparar_rotulo
from conftest import crear_paquete_real, requiere_arial
from test_datos_rotulo_editor import _formato_con_biblioteca
from test_editor_rotulo_js import ROTULO_EJEMPLO

NODE = shutil.which("node")
pytestmark = [pytest.mark.skipif(NODE is None, reason="Node no está instalado"), requiere_arial]
CARPETA_JS = Path(componedor.__file__).parent / "editor"


def js(codigo: str, entrada=None):
    script = (
        f"const L = require({json.dumps(str(CARPETA_JS / 'editor_logica.js'))});"
        f"const R = require({json.dumps(str(CARPETA_JS / 'editor_rotulo.js'))});"
        f"const C = require({json.dumps(str(CARPETA_JS / 'editor_convenciones.js'))});"
        "const entrada = JSON.parse(require('fs').readFileSync(0, 'utf8'));"
        f"const salida = (function () {{ {codigo} }})();"
        "process.stdout.write(JSON.stringify(salida === undefined ? null : salida));"
    )
    r = subprocess.run([NODE, "-e", script], input=json.dumps(entrada), capture_output=True,
                       text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


@pytest.fixture(scope="module")
def entorno(tmp_path_factory):
    carpeta = tmp_path_factory.mktemp("convenciones_editor")
    ruta = _formato_con_biblioteca(carpeta)  # símbolos "corte" (CORTE) y "panel" (PANEL)
    crear_paquete_real(carpeta / "input", "a")
    datos = preparar_editor(carpeta / "input", ruta, carpeta / "editor")
    return {"datos": datos, "definicion": cargar_formato(ruta, usar_plantilla=False).rotulo,
            "fuente": cargar_fuente(cargar_formato(ruta, usar_plantilla=False).rotulo.fuente)}


def _python(entorno, convenciones) -> list[str]:
    try:
        preparar_rotulo(entorno["definicion"], {"convenciones": convenciones}, [50.0],
                        entorno["fuente"])
    except RotuloInvalido as e:
        return e.problemas
    return []


VALIDAR = """const d = entrada.datos.rotulo;
             return C.validarConvenciones(entrada.valor, d.definicion, d.fuente, d.simbolos);"""


@pytest.mark.parametrize("valor", [
    "corte",
    {"simbolo": "corte"},
    [3, {"simbolo": "corte", "color": 1}, {"simbolo": "nope"}, {"simbolo": 5}, {"simbolo": "corte"},
     {"descripcion": "SIN SÍMBOLO"}],
    [{"simbolo": "panel", "descripcion": "PANEL 中"}, {"simbolo": "corte", "descripcion": True}],
    [{"simbolo": "corte", "descripcion": ["UNA", "DOS", "TRES"]}],          # 3 líneas en 2
    [{"simbolo": "corte", "descripcion": ["UNA", 2]}, {"simbolo": "panel", "descripcion": "A\nB"}],
    [{"simbolo": "corte"}, {"simbolo": "panel"}] + [{"simbolo": f"x{i}"} for i in range(23)],  # 25
])
def test_los_mismos_errores_que_python(entorno, valor):
    problemas = _python(entorno, valor)
    assert problemas, "el caso debe tener problemas"
    r = js(VALIDAR, {"datos": entorno["datos"], "valor": valor})
    assert sorted(r["errores"]) == sorted(problemas)


@pytest.mark.parametrize("valor", [
    [], [{"simbolo": "corte"}, {"simbolo": "panel", "descripcion": "PANEL SOLAR – TIPO “A”"}],
    [{"simbolo": "panel", "descripcion": ["PANEL", "SOLAR"]}, {"simbolo": "corte", "descripcion": None}],
])
def test_validos_sin_problemas_en_los_dos(entorno, valor):
    assert _python(entorno, valor) == []
    assert js(VALIDAR, {"datos": entorno["datos"], "valor": valor})["errores"] == []


def test_mensajes_clave(entorno):
    r = js(VALIDAR, {"datos": entorno["datos"], "valor": [{"simbolo": "nope"}, {"simbolo": "corte"},
                                                          {"simbolo": "corte"}]})
    assert r["errores"] == [
        "rotulo.convenciones[0].simbolo: texto 'nope' no está en la biblioteca (símbolos válidos: "
        "corte, panel)",
        "rotulo.convenciones[2].simbolo: 'corte' está repetido (ya está en rotulo.convenciones[1])"]


# --- casillas, marcar, guardar ----------------------------------------------------------------

def test_casilla_por_columna():
    r = js("return [0, 11, 12, 23, 24].map((i) => C.casilla(i, 24));")
    assert [(c["numero"], c["columna"], c["fila"], c["dentro"]) for c in r] == [
        (1, "izquierda", 1, True), (12, "izquierda", 12, True), (13, "derecha", 1, True),
        (24, "derecha", 12, True), (25, "derecha", 1, False)]


def test_marcar_sin_repetir_y_tope_con_aviso():
    r = js("""
        const simbolos = Array.from({length: 30}, (x, i) => ({id: "s" + i, descripcion: "S " + i}));
        let items = [];
        for (let i = 0; i < 24; i++) items = C.marcar(items, "s" + i, simbolos, 24).items;
        const repetido = C.marcar(items.slice(0, 3), "s0", simbolos, 24);
        const lleno = C.marcar(items, "s25", simbolos, 24);
        const sin = C.desmarcar(items, "s3");
        return {n: items.length, repetido: repetido.items.length, aviso: lleno.aviso, lleno: lleno.items.length,
                sin: sin.length, otra: C.marcar(sin, "s25", simbolos, 24).items.length};
    """)
    assert r["n"] == 24 and r["repetido"] == 3 and r["lleno"] == 24
    assert r["aviso"] == ("La tabla de convenciones está llena: admite 24 (dos columnas de 12). "
                          "Quite una para agregar otra.")
    assert r["sin"] == 23 and r["otra"] == 24


def test_descripcion_solo_si_cambio(entorno):
    r = js("""
        const S = entrada.datos.rotulo.simbolos;
        const nuevo = C.itemDeSimbolo("panel", S);
        const igual = C.cambiarDescripcion(nuevo, "PANEL", S);
        const otra = C.cambiarDescripcion(nuevo, "PANEL SOLAR", S);
        const vacia = C.cambiarDescripcion(otra, "   ", S);
        const lineas = C.cambiarDescripcion(C.lista([{simbolo: "corte", descripcion: ["A", "B"]}], S).items[0], "X\\nY", S);
        return [nuevo, igual, otra, vacia, lineas].map((x) => C.itemParaGuardar(x, S));
    """, {"datos": entorno["datos"]})
    assert r == [{"simbolo": "panel"}, {"simbolo": "panel"},
                 {"simbolo": "panel", "descripcion": "PANEL SOLAR"}, {"simbolo": "panel"},
                 {"simbolo": "corte", "descripcion": ["X", "Y"]}]  # sigue siendo lista


def test_desconocido_y_no_representable(entorno):
    r = js("""
        const S = entrada.datos.rotulo.simbolos;
        const l = C.lista([{simbolo: "corte"}, {simbolo: "no_existe", descripcion: "X"}], S);
        const raro = C.lista([{simbolo: "corte", color: 1}], S);
        return {conocidos: l.items.map((x) => x.conocido), desc: l.items.map((x) => x.descripcion),
                guardado: C.convencionesParaGuardar(l.items, S), raro: raro.editable,
                vacio: C.convencionesParaGuardar([], S) === undefined};
    """, {"datos": entorno["datos"]})
    assert r["conocidos"] == [True, False] and r["desc"] == ["CORTE", "X"]
    assert r["guardado"] == [{"simbolo": "corte"}, {"simbolo": "no_existe", "descripcion": "X"}]
    assert r["raro"] is False and r["vacio"] is True


# --- ida y vuelta -----------------------------------------------------------------------------

@pytest.mark.parametrize("valor", [
    ROTULO_EJEMPLO["convenciones"],  # 12 ids que la biblioteca sintética no tiene: se conservan
    [{"simbolo": "panel", "descripcion": "PANEL"}, {"simbolo": "corte", "descripcion": ["A", "B"]}],
    [],
])
def test_sin_tocar_identico(entorno, valor):
    r = js("""const S = entrada.datos.rotulo.simbolos; const l = C.lista(entrada.valor, S);
              const g = C.convencionesParaGuardar(l.items, S); return g === undefined ? null : g;""",
           {"datos": entorno["datos"], "valor": valor})
    assert r == (valor or None)


PLANO = {"version": 2, "formato": "../formato.json",
         "detalles": [{"id": "x", "manifiesto": "../input/a.manifest.json", "posicion_mm": [30, 40]}],
         "rotulo": {"titulo": "T", "convenciones": [
             {"simbolo": "panel"}, {"simbolo": "desconocido_x"},
             {"simbolo": "corte", "descripcion": "CORTE ESPECIAL"}], "hoja": 1}}


def test_elegir_ordenar_y_editar_solo_cambia_lo_tocado(entorno):
    r = js("""
        const S = entrada.datos.rotulo.simbolos;
        const p = L.leerPlano(JSON.stringify(entrada.plano), entrada.datos);
        const m = R.crearModelo(p.rotulo, entrada.datos.rotulo.definicion);
        let items = C.lista(R.valor(m, "convenciones"), S).items;
        items = C.mover(C.mover(items, 2, -1), 1, -1);             // CORTE sube al primer lugar
        items[1] = C.cambiarDescripcion(items[1], "PANEL SOLAR", S);
        R.cambiar(m, "convenciones", C.convencionesParaGuardar(items, S));
        const sinTocar = L.serializarPlano(p.colocaciones, entrada.datos,
                                           {rosa: p.rosa, rotulo: R.serializar(R.crearModelo(p.rotulo, null)), original: p.original});
        const guardado = L.objetoPlano(p.colocaciones, entrada.datos, {rosa: p.rosa, rotulo: R.serializar(m), original: p.original});
        return {guardado, sinTocar: JSON.parse(sinTocar)};
    """, {"plano": PLANO, "datos": entorno["datos"]})
    assert r["sinTocar"] == PLANO
    esperado = copy.deepcopy(PLANO)
    esperado["rotulo"]["convenciones"] = [
        {"simbolo": "corte", "descripcion": "CORTE ESPECIAL"},  # no tocada: tal como vino
        {"simbolo": "panel", "descripcion": "PANEL SOLAR"},
        {"simbolo": "desconocido_x"}]                           # desconocido: se conserva
    assert r["guardado"] == esperado
    assert list(r["guardado"]["rotulo"]) == list(PLANO["rotulo"])
    validas = [c for c in esperado["rotulo"]["convenciones"] if c["simbolo"] != "desconocido_x"]
    assert _python(entorno, validas) == []
