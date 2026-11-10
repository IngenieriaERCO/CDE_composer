"""«No cabe» y «se reducirá» en el editor (subfase 4.3e), con Node, comparando con Python.

La validación del editor (`F.validarRotulo`, `C.validarConvenciones`, `N.validarNotas`) maquetea
cada texto con editor_maquetacion.js y da los MISMOS errores («no cabe») y las MISMAS
advertencias («se escribió a X mm») que `rotulo.preparar_rotulo` sobre los mismos valores: título
(hasta 3 líneas, 2,5 -> 2,0 mm), revisiones, firmas (nombre, matrícula, cargo), descripciones de
convenciones y notas. Textos sintéticos; las personas son ficticias."""

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

NODE = shutil.which("node")
pytestmark = [pytest.mark.skipif(NODE is None, reason="Node no está instalado"), requiere_arial]
CARPETA_JS = Path(componedor.__file__).parent / "editor"

# En tres líneas a 2,5 mm no cabe; baja a 2,1 mm.
LARGO = ("PLANTA GENERAL DE LA SUBESTACIÓN ELÉCTRICA, VÍAS DE ACCESO INTERNAS, OBRAS DE DRENAJE "
         "PLUVIAL Y CERRAMIENTO PERIMETRAL DEL PARQUE SOLAR FOTOVOLTAICO SECTOR NORTE ETAPA DOS CON "
         "SUS REDES DE MEDIA TENSIÓN Y CANALIZACIONES SUBTERRÁNEAS, CAJAS")
MUY_LARGO = " ".join([LARGO] * 3)


def js(codigo: str, entrada=None):
    script = (
        f"const M = require({json.dumps(str(CARPETA_JS / 'editor_maquetacion.js'))});"
        f"const F = require({json.dumps(str(CARPETA_JS / 'editor_formularios.js'))});"
        f"const C = require({json.dumps(str(CARPETA_JS / 'editor_convenciones.js'))});"
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
    carpeta = tmp_path_factory.mktemp("cabe")
    ruta = _formato_con_biblioteca(carpeta)  # símbolos "corte" (CORTE) y "panel" (PANEL)
    crear_paquete_real(carpeta / "input", "a")
    datos = preparar_editor(carpeta / "input", ruta, carpeta / "editor")
    formato = cargar_formato(ruta, usar_plantilla=False)
    return {"datos": datos, "definicion": formato.rotulo, "fuente": cargar_fuente(formato.rotulo.fuente),
            "carpeta": carpeta}


def python(entorno, valores, carpeta=None) -> dict:
    """{"errores", "avisos"} de Python (sin errores, las advertencias del rótulo)."""
    try:
        r = preparar_rotulo(entorno["definicion"], valores, [50.0], entorno["fuente"], carpeta)
    except RotuloInvalido as e:
        return {"errores": sorted(e.problemas), "avisos": None}
    return {"errores": [], "avisos": r.advertencias}


VALIDAR_ROTULO = """
    const d = entrada.datos.rotulo;
    const r = F.validarRotulo(entrada.rotulo, d.definicion, d.fuente, null);
    return {errores: r.errores.slice().sort(), avisos: r.avisos};
"""


def editor_rotulo(entorno, valores) -> dict:
    return js(VALIDAR_ROTULO, {"datos": entorno["datos"], "rotulo": valores})


def mismos(entorno, valores, editor) -> dict:
    """Compara: mismos errores; si no hay errores, mismas advertencias."""
    p = python(entorno, valores)
    e = editor(entorno, valores)
    assert e["errores"] == p["errores"]
    if p["avisos"] is not None:
        assert e["avisos"] == p["avisos"]
    return p


# --- título, revisiones y firmas -----------------------------------------------------------------

def test_titulo_que_cabe_que_se_reduce_y_que_no_cabe(entorno):
    assert mismos(entorno, {"titulo": "PLANTA GENERAL"}, editor_rotulo) == {"errores": [], "avisos": []}
    reducido = mismos(entorno, {"titulo": LARGO}, editor_rotulo)
    assert reducido["errores"] == [] and len(reducido["avisos"]) == 1
    assert reducido["avisos"] == ["Advertencia: en el rótulo, el campo 'titulo' se escribió a 2.1 mm de altura "
                                  "(pedida 2.5 mm) para que quepa en su celda."]
    largo = mismos(entorno, {"titulo": MUY_LARGO}, editor_rotulo)
    assert len(largo["errores"]) == 1
    assert largo["errores"][0].startswith("campo 'titulo': «PLANTA GENERAL")
    assert "(altura 2.0 mm, la mínima permitida)" in largo["errores"][0]


@pytest.mark.parametrize("titulo", [
    ["PLANTA GENERAL", "SUBESTACIÓN", "SECTOR NORTE"],  # tres líneas a mano
    ["PLANTA GENERAL", "SUBESTACIÓN", "SECTOR", "NORTE"],  # cuatro: no caben a ninguna altura
    [LARGO, "B"],  # una línea a mano más ancha que la celda (no se parte)
    "LÍNEA UNO\nLÍNEA DOS\nLÍNEA TRES\nLÍNEA CUATRO",  # saltos de línea: 4 párrafos
    "PALABRAINTERMINABLESINESPACIOSQUENOCABEENELTITULODELROTULOJAMÁS",
    "ÑANDÚ – CIGÜEÑA — PINGÜINO «ÉL» … 100 ‰",
    "   ",
    12345,
])
def test_titulos_limite_iguales(entorno, titulo):
    mismos(entorno, {"titulo": titulo}, editor_rotulo)


def test_revisiones_y_firmas_iguales(entorno):
    valores = {
        "revisiones": [
            {"ver": "A", "fecha": "06/11/26", "descripcion": "EMISIÓN PARA REVISIÓN Y COMENTARIOS DEL CLIENTE"},
            {"ver": "B", "descripcion": "AJUSTE", "dibujo": "PERSONA FICTICIA CON NOMBRE LARGUÍSIMO"},
            {"ver": 0, "fecha": "06/11/2026 Y MÁS TEXTO", "aprobo": "XX"},
        ],
        "firmas": {
            "dibujo": {"nombre": "PERSONA FICTICIA DE PRUEBA CON NOMBRE MUY LARGO", "matricula": "MP 00000"},
            "diseno": {"nombre": "PERSONA FICTICIA", "matricula": "MATRÍCULA PROFESIONAL 00000-000000 CND"},
            "reviso": {"nombre": ["PERSONA FICTICIA DE PRUEBA", "(DIRECTOR DE INGENIERÍA Y DISEÑO)"],
                       "matricula": "00000"},
            "aprobo": {"nombre": "PERSONA FICTICIA", "fecha": "06/11/26"},
        },
    }
    p = mismos(entorno, valores, editor_rotulo)
    assert len(p["errores"]) >= 4  # cada celda que no cabe, con su campo
    assert all(e.startswith("campo '") for e in p["errores"])
    assert any(e.startswith("campo 'firmas.reviso.nombre'") for e in p["errores"])
    # Lo mismo, pero que quepa: sin errores ni avisos en los dos.
    cortos = {"revisiones": [{"ver": "A", "fecha": "06/11/26", "descripcion": "EMISIÓN INICIAL"}],
              "firmas": {"reviso": {"nombre": ["PERSONA FICTICIA", "(DIRECTOR)"], "matricula": "00000"}}}
    assert mismos(entorno, cortos, editor_rotulo) == {"errores": [], "avisos": []}


def test_por_defecto_y_caracteres_sin_ancho(entorno):
    # Sin valores: se maquetan los por defecto («DEFINIR») y caben.
    assert mismos(entorno, {}, editor_rotulo) == {"errores": [], "avisos": []}
    # Ω está en Arial pero no en la tabla del editor: no se puede medir; se avisa y componer decide.
    r = editor_rotulo(entorno, {"titulo": "RESISTENCIA 10 Ω"})
    assert r == {"errores": [], "avisos": [
        "campo 'titulo': el editor no puede medir los caracteres 'Ω'; componer dirá si el texto cabe"]}
    assert python(entorno, {"titulo": "RESISTENCIA 10 Ω"}) == {"errores": [], "avisos": []}


# --- descripciones de convenciones ---------------------------------------------------------------

VALIDAR_CONVENCIONES = """
    const d = entrada.datos.rotulo;
    const r = C.validarConvenciones(entrada.convenciones, d.definicion, d.fuente, d.simbolos);
    return {errores: r.errores.slice().sort(), avisos: r.avisos};
"""


def editor_convenciones(entorno, valores) -> dict:
    return js(VALIDAR_CONVENCIONES, {"datos": entorno["datos"], "convenciones": valores["convenciones"]})


DESCRIPCION_LARGA = "RELLENO COMPACTADO CON MATERIAL SELECCIONADO PROVENIENTE DE CANTERA"  # baja a 1,7 mm
DESCRIPCION_ENORME = DESCRIPCION_LARGA + " AUTORIZADA"  # no cabe ni a 1,5 mm


@pytest.mark.parametrize("convenciones", [
    [{"simbolo": "corte"}, {"simbolo": "panel"}],  # las del índice: caben
    [{"simbolo": "corte", "descripcion": "CORTE EN TERRENO NATURAL"}],
    [{"simbolo": "corte", "descripcion": DESCRIPCION_LARGA}],
    [{"simbolo": "corte", "descripcion": DESCRIPCION_ENORME}, {"simbolo": "panel", "descripcion": "PANEL SOLAR"}],
    [{"simbolo": "corte", "descripcion": ["LÍNEA UNO", "LÍNEA DOS"]}],
    [{"simbolo": "corte", "descripcion": ["UNA", "DOS", "TRES"]}],  # 3 líneas en una celda de 2
    [{"simbolo": "panel", "descripcion": "PALABRAQUENOCABEENLACASILLADELACONVENCION"}],
    [{"simbolo": "corte", "descripcion": "ÑANDÚ – CIGÜEÑA"}, {"simbolo": "panel", "descripcion": ""}],
])
def test_descripciones_de_convenciones_iguales(entorno, convenciones):
    p = mismos(entorno, {"convenciones": convenciones}, editor_convenciones)
    if convenciones[0].get("descripcion") == DESCRIPCION_LARGA:
        assert p["errores"] == [] and p["avisos"] == [
            "Advertencia: en el rótulo, el campo 'convenciones.1.descripcion' se escribió a 1.7 mm de altura "
            "(pedida 1.8 mm) para que quepa en su celda."]
    if convenciones[0].get("descripcion") == DESCRIPCION_ENORME:
        assert len(p["errores"]) == 1
        assert p["errores"][0].startswith("campo 'convenciones.1.descripcion': «RELLENO COMPACTADO")
        assert "(altura 1.5 mm, la mínima permitida)" in p["errores"][0]


# --- notas ---------------------------------------------------------------------------------------

NOTA_LARGA = ("TODAS LAS DIMENSIONES ESTÁN EN METROS, EXCEPTO DONDE SE INDIQUE LO CONTRARIO; LAS COTAS "
              "PREVALECEN SOBRE LA ESCALA DEL DIBUJO Y DEBEN VERIFICARSE EN OBRA.")


@pytest.fixture(scope="module")
def entorno_notas(tmp_path_factory, entorno):
    """El mismo formato, con un catálogo de notas típicas: generales.txt (con viñetas) y
    vias/largas.txt (15 notas largas). El plano.json va en la carpeta del editor."""
    carpeta = tmp_path_factory.mktemp("cabe_notas")
    (carpeta / "notas" / "vias").mkdir(parents=True)
    (carpeta / "notas" / "generales.txt").write_text(
        "# notas típicas de prueba\nEL CONCRETO SERÁ DE 21 MPa.\n- CEMENTO TIPO UG.\n- AGREGADO DE 3/4\".\n"
        "3. EL ACERO DE REFUERZO SERÁ DE 420 MPa.\nÑANDÚ – «PINGÜINO» … 100 ‰.\n", encoding="utf-8")
    (carpeta / "notas" / "vias" / "largas.txt").write_text(
        "".join(f"{NOTA_LARGA} ({k})\n" for k in range(15)), encoding="utf-8")
    formato = carpeta / "formato.json"
    shutil.copy(entorno["carpeta"] / "formato.json", formato)
    crear_paquete_real(carpeta / "input", "a")
    datos = preparar_editor(carpeta / "input", formato, carpeta / "editor", carpeta_notas=carpeta / "notas")
    return dict(entorno, datos=datos, plano=carpeta / "editor")


VALIDAR_NOTAS = """
    const d = entrada.datos.rotulo;
    const r = N.validarNotas(entrada.notas, d.fuente, d.notas, d.definicion);
    return {errores: r.errores.slice().sort(), avisos: r.avisos};
"""


def editor_notas(entorno, valores) -> dict:
    return js(VALIDAR_NOTAS, {"datos": entorno["datos"], "notas": valores["notas"]})


def mismas_notas(entorno, notas) -> dict:
    p = python(entorno, {"notas": notas}, entorno["plano"])
    e = editor_notas(entorno, {"notas": notas})
    assert e["errores"] == p["errores"]
    if p["avisos"] is not None:
        # Primero los de Python, iguales y en el mismo orden; al final, los propios del editor
        # (nota vacía, nota repetida), que Python no da.
        assert e["avisos"][:len(p["avisos"])] == p["avisos"]
        assert not any(a.startswith("Advertencia") for a in e["avisos"][len(p["avisos"]):])
    return p


AVISO_NOTAS = ("Advertencia: en el rótulo, las notas se escribieron a {:.1f} mm de altura (pedida 1.8 mm) para "
               "que quepan en su celda.")


@pytest.mark.parametrize("cantidad, altura", [(20, None), (21, 1.7), (24, 1.5), (25, "no")])
def test_notas_adicionales_que_caben_se_reducen_y_no_caben(entorno_notas, cantidad, altura):
    notas = {"adicionales": [f"{NOTA_LARGA} ({k})" for k in range(cantidad)]}
    p = mismas_notas(entorno_notas, notas)
    if altura is None:
        assert p == {"errores": [], "avisos": []}
    elif altura == "no":
        assert len(p["errores"]) == 1 and p["errores"][0].startswith("campo 'notas': 25 notas (")
        assert "no caben desde la nota 25 (adicionales[24])" in p["errores"][0]
    else:
        assert p == {"errores": [], "avisos": [AVISO_NOTAS.format(altura)]}


@pytest.mark.parametrize("notas", [
    {"adicionales": []},
    {"adicionales": ["NOTA CORTA.", {"texto": "CON VIÑETAS:", "vinetas": ["UNA.", "DOS.", NOTA_LARGA]}]},
    {"adicionales": ["PALABRA" + "X" * 150]},  # más ancha que el texto de las notas
    {"adicionales": [{"texto": "BIEN.", "vinetas": ["VIÑETA" + "Y" * 150]}]},  # más ancha que las viñetas
    {"adicionales": ["4. NOTA CON SU PROPIO NÚMERO.", "   ", "ÑANDÚ – CIGÜEÑA."]},
    {"archivos": ["../notas/generales.txt"]},
    {"archivos": ["../notas/generales.txt", "../notas/vias/largas.txt"], "adicionales": ["UNA MÁS."]},
    {"archivos": ["../notas/vias/largas.txt"], "adicionales": [f"{NOTA_LARGA} ({k})" for k in range(6)]},
    {"archivos": ["../notas/vias/largas.txt"], "adicionales": [f"{NOTA_LARGA} ({k})" for k in range(9)]},
    {"archivos": ["../notas/vias/largas.txt", "../notas/vias/largas.txt"]},  # dos veces: van dos veces
])
def test_notas_iguales_con_archivos_del_catalogo_y_limites(entorno_notas, notas):
    mismas_notas(entorno_notas, notas)


def test_notas_de_un_archivo_fuera_del_catalogo_no_se_miden(entorno_notas):
    notas = {"archivos": ["../otra/notas.txt"], "adicionales": [f"{NOTA_LARGA} ({k})" for k in range(30)]}
    r = editor_notas(entorno_notas, {"notas": notas})
    # Aviso informativo (ámbar), no error: sin conocer esas notas no se puede medir.
    assert r == {"errores": [], "avisos": [
        "el editor no puede medir las notas: '../otra/notas.txt' no está en el catálogo; componer lo "
        "comprobará"]}
    # Sin «archivos», esas mismas 30 notas sí se miden: no caben.
    r = editor_notas(entorno_notas, {"notas": {"adicionales": notas["adicionales"]}})
    assert len(r["errores"]) == 1 and "no caben desde la nota 25" in r["errores"][0]


def test_sin_definicion_no_se_mide(entorno_notas):
    """Llamadas de antes de la 4.3e (sin la definición): no se mide, como hasta ahora."""
    r = js("return N.validarNotas(entrada.notas, entrada.datos.rotulo.fuente, entrada.datos.rotulo.notas);",
           {"datos": entorno_notas["datos"], "notas": {"adicionales": [NOTA_LARGA] * 30}})
    assert r["errores"] == [] and r["avisos"] == []


# --- mensajes junto al campo (paso 5) --------------------------------------------------------------

def test_mensajes_de_cada_campo(entorno):
    r = js("""
        const d = entrada.datos.rotulo;
        const v = F.validarRotulo(entrada.rotulo, d.definicion, d.fuente, null);
        return {titulo: F.mensajesDeCampo(v, ["rotulo.titulo", "campo 'titulo'"]),
                firma: F.mensajesDeCampo(v, ["rotulo.firmas.dibujo.nombre", "campo 'firmas.dibujo.nombre'",
                                             "rotulo.firmas.dibujo:"]),
                otro: F.mensajesDeCampo(v, ["rotulo.no_plano", "campo 'no_plano'"]),
                titulo2: F.mensajeDeCampo("campo 'titulo2': x", ["campo 'titulo'"]),
                linea: F.mensajeDeCampo("campo 'titulo', línea 2: «X» mide", ["campo 'titulo'"])};
    """, {"datos": entorno["datos"], "rotulo": {
        "titulo": LARGO, "firmas": {"dibujo": {"nombre": "PERSONA FICTICIA DE PRUEBA CON NOMBRE MUY LARGO"}}}})
    assert r["titulo"] == {"errores": [], "avisos": [
        "Advertencia: en el rótulo, el campo 'titulo' se escribió a 2.1 mm de altura (pedida 2.5 mm) para que "
        "quepa en su celda."]}
    assert len(r["firma"]["errores"]) == 1 and r["firma"]["errores"][0].startswith("campo 'firmas.dibujo.nombre': «")
    assert r["otro"] == {"errores": [], "avisos": []}
    assert r["titulo2"] is False and r["linea"] is True  # otro campo con el mismo comienzo: no


def test_mensajes_de_tamano_de_las_notas_repartidos(entorno_notas):
    r = js("""
        const d = entrada.datos.rotulo;
        const v = N.validarNotas(entrada.notas, d.fuente, d.notas, d.definicion);
        const t = N.mensajesTamano(v);
        return {porNota: [...t.porNota.entries()], generales: t.generales};
    """, {"datos": entorno_notas["datos"], "notas": {
        "archivos": ["../notas/generales.txt"],
        "adicionales": ["CORTA.", {"texto": "BIEN.", "vinetas": ["VIÑETA" + "Y" * 150]}]}})
    assert r["generales"] == {"errores": [], "avisos": []}
    [(indice, mensajes)] = r["porNota"]
    assert indice == 1 and mensajes["errores"][0].startswith("campo 'notas', nota 5, viñeta 1 (adicionales[1]): «VIÑETA")
    r = js("""
        const d = entrada.datos.rotulo;
        const t = N.mensajesTamano(N.validarNotas(entrada.notas, d.fuente, d.notas, d.definicion));
        return {porNota: [...t.porNota.entries()], generales: t.generales};
    """, {"datos": entorno_notas["datos"], "notas": {"adicionales": [f"{NOTA_LARGA} ({k})" for k in range(21)]}})
    assert r == {"porNota": [], "generales": {"errores": [], "avisos": [AVISO_NOTAS.format(1.7)]}}
