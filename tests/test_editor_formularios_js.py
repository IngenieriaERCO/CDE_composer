"""Formularios del rótulo del editor (editor_formularios.js, subfase 4.3b), con Node:

- la validación da EXACTAMENTE los mismos problemas que `rotulo.preparar_rotulo` (se comparan
  con Python sobre los mismos valores);
- REV. (0 si existe; si no la letra más alta; vacía) y ESCALA como en Python;
- fechas en `formato_fecha`;
- editar campos, revisiones y firmas solo cambia lo tocado y respeta la forma (listas, enteros);
- proyecto.json prellena un plano NUEVO y queda copiado al guardar; un plano abierto no se toca.
Planos y valores sintéticos."""

import copy
import json
import shutil
import subprocess
from pathlib import Path

import pytest

import componedor
from componedor.datos_editor import construir_datos_editor
from componedor.formato import cargar_formato
from componedor.fuente import cargar_fuente
from componedor.rotulo import RotuloInvalido, escala_comun, preparar_rotulo
from componedor.rotulo_formato import AVISO_CAMPOS_RETIRADOS

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
# Mismo texto en Python y en el editor (el editor lo recibe en la definición del rótulo).
AVISO_RETIRADOS = AVISO_CAMPOS_RETIRADOS.format(campos="rotulo.disenador, rotulo.revisor")
pytestmark = [pytest.mark.skipif(NODE is None, reason="Node no está instalado"), requiere_arial]
CARPETA_JS = Path(componedor.__file__).parent / "editor"


def js(codigo: str, entrada=None):
    """Ejecuta `codigo` con L (lógica), R (rótulo) y F (formularios); devuelve su resultado."""
    script = (
        f"const L = require({json.dumps(str(CARPETA_JS / 'editor_logica.js'))});"
        f"const R = require({json.dumps(str(CARPETA_JS / 'editor_rotulo.js'))});"
        f"const F = require({json.dumps(str(CARPETA_JS / 'editor_formularios.js'))});"
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
    carpeta = tmp_path_factory.mktemp("formularios")
    plantilla = crear_plantilla_sintetica(carpeta / "rotulo.pdf", elementos_mm=[ROSA])
    ruta = escribir_formato(carpeta / "formato.json", plantilla=plantilla,
                            elementos_plantilla=[{"nombre": "rosa_vientos", "rect_mm": ROSA}],
                            rotulo=rotulo_a1(fuente={"archivo": str(ARIAL)}))
    crear_paquete_real(carpeta / "input", "a")
    crear_paquete_real(carpeta / "input", "b", sin_fondo=True)
    (carpeta / "editor").mkdir()
    datos, _ = construir_datos_editor(carpeta / "input", ruta, carpeta / "editor")
    return {"datos": datos, "definicion": cargar_formato(ruta, usar_plantilla=False).rotulo,
            "fuente": cargar_fuente(ARIAL)}


VALIDAR = """
    const d = entrada.datos.rotulo;
    return F.validarRotulo(entrada.rotulo, d.definicion, d.fuente, entrada.personas || null);
"""


def _python(entorno, valores) -> list[str]:
    try:
        preparar_rotulo(entorno["definicion"], valores, [50.0], entorno["fuente"])
    except RotuloInvalido as e:
        return e.problemas
    return []


# --- misma validación que Python --------------------------------------------------------------

MALOS = {
    "titulos": "x",
    "escala": "1:50",
    "rev": "A",
    "hoja": True,
    "de": 2.5,
    "no_plano": "ERCO\nPL",
    "este": ["a", "b"],
    "norte": {"x": 1},
    "disenador": "INGENIERÍA 中国",
    "revisor": ["UNO", "DOS\nTRES"],
    "titulo": ["A", "B", "C", "D"],  # 4 líneas explícitas en una celda de 3
    "revisiones": [{"ver": "A", "fecha": "1"}, {"ver": "A"}, {"ver": "D"}, {"ver": 0, "firma": "x"},
                   "x", {"ver": "B", "descripcion": "AJUSTE Ω ✓"}],
    "firmas": {"revisor": {}, "dibujo": {"nombre": "LANP", "cedula": "1"},
               "diseno": {"nombre": {"imagen": "x"}}, "aprobo": {"firma": {"imagen": "../x"}},
               "reviso": {"firma": {"imagen": "Ficticia", "otra": 1}, "nombre": ["A", "B", "C"]}},
}


def test_los_mismos_problemas_que_python(entorno):
    python = _python(entorno, MALOS)
    r = js(VALIDAR, {"datos": entorno["datos"], "rotulo": MALOS})
    assert sorted(r["errores"]) == sorted(python)  # mismos textos, ni uno más ni uno menos
    assert len(python) == 20  # disenador y revisor ya no son error: se retiraron del rótulo
    assert r["avisos"] == [AVISO_RETIRADOS]


@pytest.mark.parametrize("valores", [
    {"titulo": "PLANTA GENERAL", "hoja": 1, "de": "3", "revisor": ["A", "B"]},
    {"revisiones": [{"ver": 0, "fecha": "06/11/26"}, {"ver": "C"}]},
    {"firmas": {"reviso": {"nombre": ["ANDRÉS GÓMEZ", "(DIRECTOR)"], "firma": "AG"}}},
    {"titulo": "VÍA SUÁREZ – LA GLORIA “TRAMO 1” … €"},
])
def test_valores_validos_sin_problemas_en_los_dos(entorno, valores):
    assert _python(entorno, valores) == []
    assert js(VALIDAR, {"datos": entorno["datos"], "rotulo": valores})["errores"] == []


def test_caracteres_faltantes_con_los_rangos_de_la_fuente(entorno):
    r = js("""
        const f = entrada.datos.rotulo.fuente;
        return {chino: F.caracteresFaltantes("A中B国中 \\t", f), tilde: F.caracteresFaltantes("ÑÁÉ–€Ω", f),
                tiene: ["Ñ", "中", "😀", " "].map((c) => F.fuenteTiene(f, c)),
                viejo: F.caracteresFaltantes("A中", {anchos_em: {A: 0.6}})};
    """, {"datos": entorno["datos"]})
    assert r["chino"] == {"faltan": ["中", "国"], "desconocidos": []}
    assert r["tilde"] == {"faltan": [], "desconocidos": []}
    assert r["tiene"] == [True, False, False, True]
    assert r["viejo"] == {"faltan": [], "desconocidos": ["中"]}  # datos sin rangos: no se sabe
    assert js("""return F.validarTexto("A中", {ruta: "titulo", lineas_max: 1}, "rotulo.titulo",
                                        {anchos_em: {A: 1}}, 0.6).avisos;""") == [
        "campo 'titulo': el editor no sabe si la fuente tiene los caracteres '中'; componer lo "
        "comprobará"]


def test_firma_de_persona_que_no_esta_en_la_lista_es_aviso(entorno):
    rotulo = {"firmas": {"dibujo": {"firma": {"imagen": "Persona Uno"}},
                         "diseno": {"firma": {"imagen": "persona dos/azul"}},
                         "reviso": {"firma": {"imagen": "Otra Persona"}}}}
    r = js(VALIDAR, {"datos": entorno["datos"], "rotulo": rotulo,
                     "personas": ["Persona Uno", "Persona Dos"]})
    assert r["errores"] == []
    assert r["avisos"] == ["rotulo.firmas.reviso.firma.imagen: 'Otra Persona' no está en la lista "
                           "de firmas del editor; componer la buscará en las carpetas de firmas "
                           "del formato"]


# --- calculados -------------------------------------------------------------------------------

@pytest.mark.parametrize("vers, esperada", [
    (["0", "A", "B"], "0"), (["B", "0", "A"], "0"), (["A", "B"], "B"), (["0"], "0"),
    (["C", "A"], "C"), ([], ""), ([0, "A"], "0"), (["D", "A", "A"], "A"),
])
def test_rev_como_python(entorno, vers, esperada):
    revisiones = [{"ver": v} for v in vers]
    r = js("""
        const t = entrada.datos.rotulo.definicion.campos.revisiones;
        return F.ultimaRevision(F.letrasValidas(entrada.revisiones, t), t.orden);
    """, {"datos": entorno["datos"], "revisiones": revisiones})
    assert r == esperada
    if not {"D"} & set(vers) and len(set(map(str, vers))) == len(vers):  # Python acepta la lista
        python = preparar_rotulo(entorno["definicion"], {"revisiones": revisiones} if vers else {},
                                 [50.0], entorno["fuente"])
        assert python.valores["rev"] == esperada


@pytest.mark.parametrize("escalas", [[50], [50, 50], [50, 1000], [1000], [12.5], [10000], []])
def test_escala_como_python(escalas):
    assert js("return F.escalaComun(entrada);", escalas) == escala_comun([float(e) for e in escalas])


# --- fechas -----------------------------------------------------------------------------------

def test_fechas_en_el_formato_del_rotulo():
    r = js("""
        const formatos = ["dd/mm/aa", "aaaa-mm-dd", "mm.dd.aaaa", "aa/mm/dd"];
        return {
          escritas: formatos.map((f) => F.formatearFecha("2026-11-09", f)),
          leidas: formatos.map((f) => F.fechaIso(F.formatearFecha("2026-03-07", f), f)),
          malas: [F.fechaIso("31/02/26", "dd/mm/aa"), F.fechaIso("9/11/26", "dd/mm/aa"),
                  F.fechaIso("09-11-26", "dd/mm/aa"), F.fechaIso("", "dd/mm/aa"),
                  F.formatearFecha("2026-11-09", "dd/mm"), F.formatearFecha("", "dd/mm/aa")],
          hoy: F.hoyIso(new Date(2026, 0, 5)),
        };
    """)
    assert r["escritas"] == ["09/11/26", "2026-11-09", "11.09.2026", "26/11/09"]
    assert r["leidas"] == ["2026-03-07"] * 4
    assert r["malas"] == [""] * 6
    assert r["hoy"] == "2026-01-05"


# --- valores del formulario -------------------------------------------------------------------

def test_texto_del_formulario_respeta_la_forma():
    r = js("""
        return {
          lista: F.valorDeTexto("ANDRÉS\\r\\n(DIRECTOR)", ["X", "Y"]),
          entero: F.valorDeTexto(" 2 ", 1), entero_texto: F.valorDeTexto("2A", 1),
          texto: F.valorDeTexto("2", "1"), nuevo: F.valorDeTexto("UNO\\nDOS", undefined),
          vacio: F.valorDeTexto("   ", "X") === undefined,
          mostrar: [F.textoDeValor(["A", "B"]), F.textoDeValor(3), F.textoDeValor(null), F.textoDeValor(undefined)],
          representables: [F.representable(["A"]), F.representable(1.5), F.representable({}), F.representable(true)],
        };
    """)
    assert r["lista"] == ["ANDRÉS", "(DIRECTOR)"] and r["entero"] == 2
    assert r["entero_texto"] == "2A" and r["texto"] == "2" and r["nuevo"] == "UNO\nDOS"
    assert r["vacio"] is True
    assert r["mostrar"] == ["A\nB", "3", "", ""]
    assert r["representables"] == [True, False, False, False]


def test_campos_simples_del_formulario(entorno):
    r = js("return F.camposSimples(entrada.rotulo.definicion);", entorno["datos"])
    assert [c["campo"] for c in r] == ["titulo", "no_plano", "hoja", "de", "este", "norte",
                                       "localizacion_escala"]  # sin diseñador ni revisor
    assert r[0]["etiqueta"] == "Título" and r[0]["celda"]["lineas_max"] == 3
    assert r[6]["por_defecto"] == "DEFINIR"


def test_revisiones_agregar_cambiar_quitar(entorno):
    r = js("""
        const t = entrada.datos.rotulo.definicion.campos.revisiones;
        let lista = F.agregarRevision(undefined, t);            // A
        lista = F.agregarRevision(lista, t);                      // B
        lista = F.cambiarCeldaRevision(lista, 1, "ver", "0");     // B -> 0
        lista = F.cambiarCeldaRevision(lista, 0, "fecha", "06/11/26");
        const libres = F.letrasLibres(lista, t, 0);
        let llena = lista;
        for (let i = 0; i < 3; i++) llena = F.agregarRevision(llena, t) || llena;
        const sin = F.quitarRevision(lista, 0);
        return {lista, libres, completa: llena.map((x) => x.ver), otra: F.agregarRevision(llena, t),
                sin, vacia: F.revisionesParaGuardar(F.quitarRevision(sin, 0)) === undefined,
                borrada: F.cambiarCeldaRevision(lista, 0, "fecha", undefined)[0]};
    """, {"datos": entorno["datos"]})
    assert r["lista"] == [{"ver": "A", "fecha": "06/11/26"}, {"ver": "0"}]
    assert r["libres"] == ["A", "B", "C"]  # sin la «0», que ya usa la otra
    assert r["completa"] == ["A", "0", "B", "C"] and r["otra"] is None
    assert r["sin"] == [{"ver": "0"}] and r["vacia"] is True
    assert r["borrada"] == {"ver": "A"}


def test_firmas_cambiar_celdas(entorno):
    r = js("""
        let f = F.cambiarCeldaFirma(undefined, "reviso", "nombre", ["A", "B"]);
        f = F.cambiarCeldaFirma(f, "reviso", "firma", {imagen: "Persona Uno"});
        const conImagen = f;
        f = F.cambiarCeldaFirma(f, "reviso", "firma", undefined);
        const sinFirma = f;
        f = F.cambiarCeldaFirma(f, "reviso", "nombre", undefined);
        const d = entrada.datos.rotulo.definicion;
        return {conImagen, sinFirma, vacia: f === undefined,
                rep: [F.firmasRepresentables(conImagen, d), F.firmasRepresentables({reviso: "x"}, d),
                      F.firmasRepresentables({reviso: {firma: {imagen: "a", otra: 1}}}, d),
                      F.firmasRepresentables({reviso: {nombre: {imagen: "a"}}}, d)]};
    """, {"datos": entorno["datos"]})
    assert r["conImagen"] == {"reviso": {"nombre": ["A", "B"], "firma": {"imagen": "Persona Uno"}}}
    assert r["sinFirma"] == {"reviso": {"nombre": ["A", "B"]}} and r["vacia"] is True
    assert r["rep"] == [True, False, False, False]


# --- ida y vuelta tras EDITAR -----------------------------------------------------------------

EDITAR = """
    const plano = entrada.plano;
    const r = L.leerPlano(JSON.stringify(plano, null, 2), entrada.datos);
    const m = R.crearModelo(r.rotulo, entrada.datos.rotulo.definicion);
    const v = (c) => R.valor(m, c);
    // Campos simples: título (texto), HOJA (entero), REVISOR (texto) y uno nuevo.
    R.cambiar(m, "titulo", F.valorDeTexto("PLANTA GENERAL", v("titulo")));
    R.cambiar(m, "hoja", F.valorDeTexto("2", v("hoja")));
    R.cambiar(m, "norte", F.valorDeTexto("", v("norte")));           // vaciar = quitar
    // Revisiones: descripción de la B y una revisión C nueva.
    const t = entrada.datos.rotulo.definicion.campos.revisiones;
    let rev = F.cambiarCeldaRevision(v("revisiones"), 2, "descripcion", "AJUSTE FINAL");
    rev = F.agregarRevision(rev, t);
    rev = F.cambiarCeldaRevision(rev, 3, "fecha", F.formatearFecha("2026-11-09", "dd/mm/aa"));
    R.cambiar(m, "revisiones", F.revisionesParaGuardar(rev));
    // Firmas: REVISÓ sigue siendo lista de líneas; APROBÓ pasa de texto a persona.
    let f = F.cambiarCeldaFirma(v("firmas"), "reviso", "nombre",
                                F.valorDeTexto("ANDRÉS GÓMEZ\\n(DIRECTOR)", v("firmas").reviso.nombre));
    f = F.cambiarCeldaFirma(f, "aprobo", "firma", {imagen: "Persona Uno"});
    R.cambiar(m, "firmas", f);
    const texto = L.serializarPlano(r.colocaciones, entrada.datos,
                                    {rosa: r.rosa, rotulo: R.serializar(m), original: r.original});
    const val = F.validarRotulo(R.serializar(m), entrada.datos.rotulo.definicion,
                                entrada.datos.rotulo.fuente, entrada.personas);
    return {guardado: JSON.parse(texto), validacion: val};
"""


def test_editar_campos_solo_cambia_lo_tocado(entorno):
    plano = PLANOS["v2_ejemplo_completo"]
    personas = ["Persona Uno", "Ficticia Núñez", "Ficticia Ocaña", "Ficticia Gómez"]
    r = js(EDITAR, {"plano": plano, "datos": entorno["datos"], "personas": personas})
    esperado = copy.deepcopy(plano)
    rot = esperado["rotulo"]
    rot["titulo"] = "PLANTA GENERAL"
    rot["hoja"] = 2  # sigue siendo entero
    del rot["norte"]
    rot["revisiones"][2]["descripcion"] = "AJUSTE FINAL"
    rot["revisiones"].append({"ver": "C", "fecha": "09/11/26"})
    rot["firmas"]["reviso"]["nombre"] = ["ANDRÉS GÓMEZ", "(DIRECTOR)"]  # sigue siendo lista
    rot["firmas"]["aprobo"]["firma"] = {"imagen": "Persona Uno"}
    assert r["guardado"] == esperado
    assert list(r["guardado"]["rotulo"]) == [k for k in plano["rotulo"] if k != "norte"]
    assert list(r["guardado"]) == list(plano)  # mismo orden de claves del plano
    # El plano de ejemplo es anterior: trae disenador y revisor, que se ignoran con un aviso.
    assert r["validacion"] == {"errores": [], "avisos": [AVISO_RETIRADOS]}
    # Y Python acepta el rótulo guardado (sin notas ni convenciones, que no son de esta subfase).
    valores = {k: v for k, v in r["guardado"]["rotulo"].items()
               if k not in ("notas", "convenciones", "firmas")}
    assert _python(entorno, valores) == []


def test_ida_y_vuelta_sin_tocar_sigue_identica(entorno):
    """La de la 4.3a, con los datos que ahora traen rangos de la fuente y personas."""
    datos = copy.deepcopy(entorno["datos"])
    datos["rotulo"]["personas_firmas"] = ["Ficticia Núñez"]
    r = js(IDA_Y_VUELTA, {"planos": PLANOS, "datos": datos})
    for nombre, plano in PLANOS.items():
        assert r[nombre]["guardado"] == plano, nombre


# --- proyecto.json ----------------------------------------------------------------------------

PROYECTO = {"version": 1, "nombre": "FICTICIO", "disenador": "DISEÑO S.A.S.",
            "revisor": ["INTERVENTORÍA", "ÑANDÚ"], "prefijo_no_plano": "ERCO-PSF-CIV-PL-",
            "firmas": {"dibujo": {"nombre": "LANP", "matricula": "PRACTICANTE"},
                       "reviso": {"nombre": ["A. GÓMEZ", "(DIRECTOR)"]}}}


def test_proyecto_prellena_un_plano_nuevo_y_queda_copiado(entorno):
    r = js("""
        const d = entrada.datos;
        const valores = F.valoresProyecto(entrada.proyecto, d.rotulo.definicion);
        const nuevo = R.crearModelo(null, d.rotulo.definicion);
        const puestos = R.prellenar(nuevo, valores);
        R.cambiar(nuevo, "no_plano", R.valor(nuevo, "no_plano") + "0007");  // el usuario completa
        const plano = L.objetoPlano([{id: "x", detalle: d.detalles[0], pos: [30, 40]}], d,
                                    {rotulo: R.serializar(nuevo)});
        const abierto = R.crearModelo({titulo: "YA TIENE RÓTULO"}, d.rotulo.definicion);
        const nada = R.prellenar(abierto, valores);
        return {valores, puestos, plano, abierto: R.serializar(abierto), nada};
    """, {"datos": entorno["datos"], "proyecto": PROYECTO})
    # El proyecto trae disenador y revisor, pero el rótulo ya no los tiene: no se prellenan.
    assert r["valores"] == {"no_plano": "ERCO-PSF-CIV-PL-", "firmas": PROYECTO["firmas"]}
    assert r["puestos"] == ["no_plano", "firmas"]
    assert r["plano"]["version"] == 2
    assert r["plano"]["rotulo"] == {**r["valores"], "no_plano": "ERCO-PSF-CIV-PL-0007"}
    assert r["abierto"] == {"titulo": "YA TIENE RÓTULO"} and r["nada"] == []
    assert _python(entorno, r["plano"]["rotulo"]) == []  # componer lo aceptaría


def test_proyecto_vacio_o_sin_definicion_no_prellena(entorno):
    assert js("""return [F.valoresProyecto(null, entrada.rotulo.definicion),
                         F.valoresProyecto({version: 1}, entrada.rotulo.definicion),
                         F.valoresProyecto({disenador: "X"}, null)];""",
              entorno["datos"]) == [{}, {}, {}]
