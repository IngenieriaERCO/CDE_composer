"""Notas del rótulo en el editor (editor_notas.js, subfase 4.3c), con Node:

- validación con los MISMOS textos que Python (notas.leer_notas y rotulo._notas): se comparan
  con `preparar_rotulo` sobre los mismos valores, errores y avisos de número propio;
- catálogo real (`catalogo_notas` sobre .txt sintéticos): enlazar, marcar sin repetir, desmarcar;
- lista: subir, bajar, quitar, editar, notas a mano con viñetas;
- ida y vuelta: sin tocar, idéntica; tras elegir, ordenar y editar, solo cambia "adicionales"
  ("archivos" y las notas no tocadas quedan tal como venían) y Python acepta el resultado.
También el orden de las revisiones en el panel (0, C, B, A)."""

import copy
import json
import shutil
import subprocess
from pathlib import Path

import pytest

import componedor
from componedor.datos_editor import construir_datos_editor
from componedor.datos_rotulo_editor import catalogo_notas
from componedor.formato import cargar_formato
from componedor.fuente import cargar_fuente
from componedor.rotulo import RotuloInvalido, preparar_rotulo
from conftest import (
    ARIAL,
    crear_paquete_real,
    crear_plantilla_sintetica,
    escribir_formato,
    requiere_arial,
    rotulo_a1,
)
from test_editor_rotulo_js import IDA_Y_VUELTA, PLANOS, ROSA

NODE = shutil.which("node")
pytestmark = [pytest.mark.skipif(NODE is None, reason="Node no está instalado"), requiere_arial]
CARPETA_JS = Path(componedor.__file__).parent / "editor"


def js(codigo: str, entrada=None):
    """Ejecuta `codigo` con L, R, F y N (notas); devuelve su resultado."""
    script = (
        f"const L = require({json.dumps(str(CARPETA_JS / 'editor_logica.js'))});"
        f"const R = require({json.dumps(str(CARPETA_JS / 'editor_rotulo.js'))});"
        f"const F = require({json.dumps(str(CARPETA_JS / 'editor_formularios.js'))});"
        f"const N = require({json.dumps(str(CARPETA_JS / 'editor_notas.js'))});"
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
    carpeta = tmp_path_factory.mktemp("notas_editor")
    plantilla = crear_plantilla_sintetica(carpeta / "rotulo.pdf", elementos_mm=[ROSA])
    ruta = escribir_formato(carpeta / "formato.json", plantilla=plantilla,
                            elementos_plantilla=[{"nombre": "rosa_vientos", "rect_mm": ROSA}],
                            rotulo=rotulo_a1(fuente={"archivo": str(ARIAL)}))
    crear_paquete_real(carpeta / "input", "a")
    crear_paquete_real(carpeta / "input", "b", sin_fondo=True)
    notas = carpeta / "notas"
    (notas / "vias").mkdir(parents=True)
    (notas / "generales.txt").write_text(
        "# notas generales\nEL PERFIL K0+010 SE MUESTRA A ESCALA 1:50.\n2. COTAS EN METROS.\n",
        encoding="utf-8")
    (notas / "vias" / "pavimentos.txt").write_text(
        "LOS MATERIALES CUMPLIRÁN:\n- NORMA A.\n- NORMA B.\nSUBRASANTE COMPACTADA AL 95 %.\n",
        encoding="utf-8")
    (carpeta / "editor").mkdir()
    datos, _ = construir_datos_editor(carpeta / "input", ruta, carpeta / "editor",
                                      carpeta_notas=notas)
    return {"datos": datos, "definicion": cargar_formato(ruta, usar_plantilla=False).rotulo,
            "fuente": cargar_fuente(ARIAL), "catalogo": catalogo_notas(notas)}


def _python(entorno, notas) -> tuple[list[str], list[str]]:
    """(problemas, advertencias) de `componer` para {"notas": notas}."""
    try:
        r = preparar_rotulo(entorno["definicion"], {"notas": notas}, [50.0], entorno["fuente"])
    except RotuloInvalido as e:
        return e.problemas, []
    return [], r.advertencias


VALIDAR = "return N.validarNotas(entrada.notas, entrada.datos.rotulo.fuente);"


# --- misma validación que Python --------------------------------------------------------------

@pytest.mark.parametrize("notas", [
    {"archivos": [1], "adicionales": [
        "UNA\nDOS", 3, True, None,
        {"texto": "", "vinetas": "x", "otra": 1},
        {"texto": "OK", "vinetas": ["a\nb"]},
        {"vinetas": ["SIN TEXTO"]},
        {"texto": "UNA\nLÍNEA"},
        "NOTA CON 中.",
        {"texto": "CON VIÑETA RARA:", "vinetas": ["x 国", "  "]},
        "BIEN.", "3. CON NÚMERO 😀"],
     "titulo": "x"},
    {"adicionales": "no es lista", "archivos": "tampoco"},
    "texto suelto",
    ["lista"],
    {"adicionales": [{"texto": 5}, {"texto": "X", "vinetas": [1, 2]}]},
])
def test_los_mismos_errores_que_python(entorno, notas):
    problemas, _ = _python(entorno, notas)
    r = js(VALIDAR, {"datos": entorno["datos"], "notas": notas})
    assert problemas, "el caso debe tener problemas"
    assert sorted(r["errores"]) == sorted(problemas)


def test_avisos_de_numero_propio_como_python(entorno):
    notas = {"adicionales": ["3. PRIMERA.", "10) SEGUNDA.", "3.5 M NO ES NÚMERO.",
                             {"texto": "  7.  CON VIÑETAS:", "vinetas": ["A."]}]}
    problemas, advertencias = _python(entorno, notas)
    assert problemas == []
    r = js(VALIDAR, {"datos": entorno["datos"], "notas": notas})
    assert r["errores"] == []
    assert r["avisos"] == [a for a in advertencias if "traía su propio número" in a]
    assert len(r["avisos"]) == 3
    assert r["avisos"][0] == ("Advertencia: la nota de adicionales[0] traía su propio número «3.»; "
                              "se quitó: el componedor numera las notas solo.")
    assert [n["texto"] for n in r["notas"]] == ["PRIMERA.", "SEGUNDA.", "3.5 M NO ES NÚMERO.",
                                               "CON VIÑETAS:"]


def test_nota_vacia_python_la_omite_y_el_editor_avisa(entorno):
    notas = {"adicionales": ["   ", "BIEN."]}
    assert _python(entorno, notas) == ([], [])  # Python: sin mensaje, la omite
    r = js(VALIDAR, {"datos": entorno["datos"], "notas": notas})
    assert r["errores"] == []
    assert r["avisos"] == ["rotulo.notas.adicionales[0]: la nota está vacía; componer la omite "
                           "(no se numera)"]


# --- catálogo y lista -------------------------------------------------------------------------

def test_catalogo_marcar_desmarcar_sin_repetir(entorno):
    r = js("""
        const cat = entrada.catalogo;
        const indice = N.indiceCatalogo(cat);
        let items = [];
        items = N.marcar(items, "vias/pavimentos.txt, línea 1", cat);
        items = N.marcar(items, "generales.txt, línea 3", cat);
        const repetida = N.marcar(items, "vias/pavimentos.txt, línea 1", cat).length;
        const marcadas = items.map((x) => x.clave);
        const sin = N.desmarcar(items, "vias/pavimentos.txt, línea 1");
        return {claves: [...indice.keys()], aviso: indice.get("generales.txt, línea 3").avisos,
                items, repetida, marcadas, sin: sin.map((x) => x.texto),
                guardado: N.notasParaGuardar(undefined, items)};
    """, {"catalogo": entorno["catalogo"]})
    assert r["claves"] == ["generales.txt, línea 2", "generales.txt, línea 3",
                           "vias/pavimentos.txt, línea 1", "vias/pavimentos.txt, línea 4"]
    assert r["aviso"] == ["Advertencia: la nota de generales.txt, línea 3 traía su propio número "
                          "«2.»; se quitó: el componedor numera las notas solo."]
    assert r["repetida"] == 2 and r["marcadas"] == ["vias/pavimentos.txt, línea 1",
                                                     "generales.txt, línea 3"]
    assert r["sin"] == ["COTAS EN METROS."]
    assert r["guardado"] == {"adicionales": [
        {"texto": "LOS MATERIALES CUMPLIRÁN:", "vinetas": ["NORMA A.", "NORMA B."]},
        "COTAS EN METROS."]}


def test_lista_enlaza_las_notas_del_plano_con_el_catalogo(entorno):
    valor = {"archivos": ["../notas/x.txt"], "adicionales": [
        "COTAS  EN METROS.", {"texto": "LOS MATERIALES CUMPLIRÁN:", "vinetas": ["NORMA A.", "NORMA B."]},
        "COTAS EN METROS.", "A MANO."]}
    r = js("return N.lista(entrada.valor, entrada.catalogo);",
           {"valor": valor, "catalogo": entorno["catalogo"]})
    assert r["editable"] is True and r["archivos"] == ["../notas/x.txt"]
    assert [x["clave"] for x in r["items"]] == [
        "generales.txt, línea 3", "vias/pavimentos.txt, línea 1", None, None]  # sin repetir
    assert [x["tocado"] for x in r["items"]] == [False] * 4


def test_operaciones_y_notas_a_mano():
    r = js("""
        const a = N.itemAMano("  PRIMERA  ", "");
        const b = N.itemAMano("CON VIÑETAS:\\n", "UNA.\\n\\n  DOS.  \\n");
        const vacia = N.itemAMano("   ", "x");
        let items = [a, b, N.itemAMano("TERCERA.", "")];
        const subida = N.mover(items, 2, -1).map((x) => x.texto);
        const tope = N.mover(items, 0, -1).map((x) => x.texto);
        const sin = N.quitar(items, 1).map((x) => x.texto);
        return {a: N.itemParaGuardar(a), b: N.itemParaGuardar(b), vacia, subida, tope, sin,
                numeros: N.numeros(items)};
    """)
    assert r["a"] == "PRIMERA" and r["b"] == {"texto": "CON VIÑETAS:", "vinetas": ["UNA.", "DOS."]}
    assert r["vacia"] is None
    assert r["subida"] == ["PRIMERA", "TERCERA.", "CON VIÑETAS:"]
    assert r["tope"] == ["PRIMERA", "CON VIÑETAS:", "TERCERA."]
    assert r["sin"] == ["PRIMERA", "TERCERA."]
    assert r["numeros"] == [1, 2, 3]  # las viñetas no se numeran


def test_adicionales_que_la_lista_no_sabe_mostrar_se_conservan(entorno):
    valor = {"adicionales": ["BIEN.", {"texto": "X", "color": "rojo"}]}
    r = js("""const l = N.lista(entrada.valor, null);
              return {editable: l.editable, items: l.items.length,
                      rep: [N.adicionalRepresentable("A\\nB"), N.adicionalRepresentable({texto: "A"}),
                            N.adicionalRepresentable({texto: "A", vinetas: [1]})]};""",
           {"valor": valor})
    assert r == {"editable": False, "items": 0, "rep": [False, True, False]}


# --- ida y vuelta -----------------------------------------------------------------------------

def test_sin_tocar_las_notas_salen_identicas(entorno):
    r = js("""
        const res = {};
        for (const [nombre, plano] of Object.entries(entrada.planos)) {
          const valor = plano.rotulo ? plano.rotulo.notas : undefined;
          const l = N.lista(valor, entrada.catalogo);
          const g = l.editable ? N.notasParaGuardar(valor, l.items) : "no editable";
          res[nombre] = g === undefined ? null : g;
        }
        return res;
    """, {"planos": PLANOS, "catalogo": entorno["catalogo"]})
    for nombre, plano in PLANOS.items():
        assert r[nombre] == (plano.get("rotulo") or {}).get("notas"), nombre
    datos = copy.deepcopy(entorno["datos"])  # la ida y vuelta completa, con catálogo incrustado
    vuelta = js(IDA_Y_VUELTA, {"planos": PLANOS, "datos": datos})
    for nombre, plano in PLANOS.items():
        assert vuelta[nombre]["guardado"] == plano, nombre


EDITAR = """
    const plano = entrada.plano;
    const r = L.leerPlano(JSON.stringify(plano, null, 2), entrada.datos);
    const m = R.crearModelo(r.rotulo, entrada.datos.rotulo.definicion);
    const cat = entrada.datos.rotulo.notas;
    let l = N.lista(R.valor(m, "notas"), cat);
    let items = l.items;
    items = N.marcar(items, "vias/pavimentos.txt, línea 4", cat);      // elegir una típica
    items = N.mover(N.mover(items, 2, -1), 1, -1);                        // subirla dos veces
    items[1].texto = "EL PERFIL K0+010 SE MUESTRA A ESCALA 1:100.";      // editar una (copiada)
    items[1].tocado = true;
    items = items.concat([N.itemAMano("NOTA A MANO:", "PRIMERA VIÑETA.\\nSEGUNDA VIÑETA.")]);
    R.cambiar(m, "notas", N.notasParaGuardar(R.valor(m, "notas"), items));
    const texto = L.serializarPlano(r.colocaciones, entrada.datos,
                                    {rosa: r.rosa, rotulo: R.serializar(m), original: r.original});
    return {guardado: JSON.parse(texto), validacion: N.validarNotas(R.valor(m, "notas"), entrada.datos.rotulo.fuente)};
"""


def test_elegir_ordenar_y_editar_solo_cambia_adicionales(entorno):
    plano = PLANOS["v2_ejemplo_completo"]
    r = js(EDITAR, {"plano": plano, "datos": entorno["datos"]})
    esperado = copy.deepcopy(plano)
    original = plano["rotulo"]["notas"]["adicionales"]
    esperado["rotulo"]["notas"]["adicionales"] = [
        "SUBRASANTE COMPACTADA AL 95 %.",
        "EL PERFIL K0+010 SE MUESTRA A ESCALA 1:100.",
        original[1],  # la de viñetas, no tocada: tal como venía
        {"texto": "NOTA A MANO:", "vinetas": ["PRIMERA VIÑETA.", "SEGUNDA VIÑETA."]},
    ]
    assert r["guardado"] == esperado  # "archivos", el resto del rótulo y el plano, intactos
    assert list(r["guardado"]["rotulo"]) == list(plano["rotulo"])
    assert r["validacion"]["errores"] == [] and r["validacion"]["avisos"] == []
    # Python acepta las notas guardadas (sin "archivos": son .txt que aquí no existen).
    notas = {"adicionales": r["guardado"]["rotulo"]["notas"]["adicionales"]}
    assert _python(entorno, notas) == ([], [])


# --- orden de las revisiones en el panel ------------------------------------------------------

def test_revisiones_se_muestran_en_el_orden_del_rotulo(entorno):
    lista = [{"ver": "A"}, {"ver": "0"}, {"ver": "D"}, {"ver": "B"}, {"ver": "A"}, {"ver": "C"}]
    r = js("return F.ordenRotulo(entrada.lista, entrada.datos.rotulo.definicion.campos.revisiones);",
           {"lista": lista, "datos": entorno["datos"]})
    assert [lista[i]["ver"] for i in r] == ["0", "C", "B", "A", "D", "A"]  # inválidas al final
    assert r == [1, 5, 3, 0, 2, 4]
