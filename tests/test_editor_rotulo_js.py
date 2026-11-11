"""Modelo del rótulo del editor (editor_rotulo.js) e IDA Y VUELTA de plano.json (subfase
4.3a), ejecutados con Node: abrir un plano.json y guardarlo sin tocar nada debe dar un JSON
idéntico (igualdad profunda). Planos sintéticos (el de ejemplo replica la estructura del
ejemplo real: notas con viñetas, 12 convenciones y firmas con imagen)."""

import copy
import json
import shutil
import subprocess
from pathlib import Path

import pytest

import componedor
from componedor.datos_editor import construir_datos_editor
from conftest import (
    ARIAL,
    crear_paquete_real,
    crear_plantilla_sintetica,
    escribir_formato,
    rotulo_a1,
)

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node no está instalado")
CARPETA_JS = Path(componedor.__file__).parent / "editor"
ROSA = [612.0, 51.0, 652.0, 91.0]


def js(codigo: str, entrada=None):
    """Ejecuta `codigo` con L (lógica) y R (rótulo) cargados; devuelve su resultado."""
    script = (
        f"const L = require({json.dumps(str(CARPETA_JS / 'editor_logica.js'))});"
        f"const R = require({json.dumps(str(CARPETA_JS / 'editor_rotulo.js'))});"
        "const entrada = JSON.parse(require('fs').readFileSync(0, 'utf8'));"
        f"const salida = (function () {{ {codigo} }})();"
        "process.stdout.write(JSON.stringify(salida === undefined ? null : salida));"
    )
    r = subprocess.run([NODE, "-e", script], input=json.dumps(entrada), capture_output=True,
                       text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


@pytest.fixture(scope="module")
def datos(tmp_path_factory):
    carpeta = tmp_path_factory.mktemp("editor_rotulo")
    plantilla = crear_plantilla_sintetica(carpeta / "rotulo.pdf", elementos_mm=[ROSA])
    escribir_formato(carpeta / "formato.json", plantilla=plantilla,
                     elementos_plantilla=[{"nombre": "rosa_vientos", "rect_mm": ROSA}],
                     rotulo=rotulo_a1(fuente={"archivo": str(ARIAL)}))
    crear_paquete_real(carpeta / "input", "a")
    crear_paquete_real(carpeta / "input", "b", sin_fondo=True)
    (carpeta / "editor").mkdir()
    datos, _ = construir_datos_editor(carpeta / "input", carpeta / "formato.json",
                                      carpeta / "editor")
    return datos


# --- planos para la ida y vuelta ----------------------------------------------------------------

D_A = "../input/a.manifest.json"
D_B = "../input/b.manifest.json"

ROTULO_EJEMPLO = {  # misma estructura que data/pruebas/planos/ejemplo_rotulo_v2.json (datos ficticios)
    "localizacion_escala": "1:25.000",
    "este": "4.876.543,21",
    "norte": "2.012.345,67",
    "convenciones": [
        {"simbolo": "limite_predio"}, {"simbolo": "curvas_nivel"}, {"simbolo": "cuerpos_agua"},
        {"simbolo": "linea_electrica"},
        {"simbolo": "via_existente", "descripcion": "VÍA SUÁREZ – LA GLORIA"},
        {"simbolo": "via_carreteable"}, {"simbolo": "limite_predio_proyectado"},
        {"simbolo": "gps"}, {"simbolo": "panel_3vx8"}, {"simbolo": "panel_3vx24"},
        {"simbolo": "corte"}, {"simbolo": "relleno"}],
    "notas": {
        "archivos": ["../notas/generales_vias.txt", "../notas/drenaje.txt",
                     "../notas/referencias.txt"],
        "adicionales": [
            "EL PERFIL K0+010 SE MUESTRA A ESCALA 1:50.",
            {"texto": "LOS MATERIALES CUMPLIRÁN:", "vinetas": ["NORMA A.", "NORMA B."]}]},
    "revisiones": [
        {"ver": "0", "fecha": "06/11/26", "descripcion": "EMISIÓN PARA CONSTRUCCIÓN",
         "dibujo": "LANP", "diseno": "LANP", "reviso": "A. GÓMEZ", "aprobo": "JP"},
        {"ver": "A", "fecha": "20/10/26", "descripcion": "EMISIÓN PARA REVISIÓN INTERNA"},
        {"ver": "B", "fecha": "28/10/26", "descripcion": "AJUSTE DE COTAS Y ABSCISADO"}],
    "disenador": "INGENIERÍA DE DISEÑO S.A.S.",
    "revisor": "INTERVENTORÍA ÑANDÚ LTDA.",
    "titulo": "PARQUE SOLAR FOTOVOLTAICO — VÍA DE ACCESO PRINCIPAL MA: PLANTA GENERAL",
    "firmas": {
        "dibujo": {"nombre": "LUIS Á. NÚÑEZ P.", "matricula": "PRACTICANTE",
                   "firma": {"imagen": "Ficticia Núñez"}, "fecha": "06/11/26"},
        "diseno": {"nombre": "MARÍA JOSÉ OCAÑA", "matricula": "25202-123456",
                   "firma": {"imagen": "Ficticia Ocaña/azul"}, "fecha": "06/11/26"},
        "reviso": {"nombre": ["ANDRÉS GÓMEZ", "(DIRECTOR TÉCNICO)"], "matricula": "25202-654321",
                   "firma": {"imagen": "Ficticia Gómez"}, "fecha": "06/11/26"},
        "aprobo": {"nombre": "JULIÁN PÉREZ", "matricula": "25202-111222", "firma": "JP",
                   "fecha": "06/11/26"}},
    "hoja": 1,
    "de": 3,
    "no_plano": "ERCO-PSF-CIV-PL-0001",
}

PLANOS = {
    "v1_simple_con_centrar": {
        "version": 1, "formato": "../formato.json", "plantilla": None,
        "detalles": [{"id": "x", "manifiesto": D_A, "posicion_mm": [30.123456, 40]},
                     {"id": "c", "manifiesto": "..\\input\\b.manifest.json", "centrar": True}]},
    "v1_sin_plantilla_ni_rosa": {
        "version": 1, "formato": "./../formato.json",
        "detalles": [{"id": "x", "manifiesto": D_A, "posicion_mm": [100, 200], "centrar": False}]},
    "v2_rosa_oculta_y_etiqueta": {
        "version": 2, "formato": "../formato.json", "plantilla": "../rotulo.pdf",
        "detalles": [{"id": "x", "manifiesto": D_A, "posicion_mm": [30, 40],
                      "etiqueta_escala": False}],
        "rosa_vientos": {"visible": False}},
    "v2_rosa_vacia_y_por_defecto": {
        "version": 2, "formato": "../formato.json",
        "detalles": [{"id": "x", "manifiesto": D_B, "posicion_mm": [30, 40]}],
        "rosa_vientos": {}},
    "v2_ejemplo_completo": {
        "version": 2, "formato": "../formato.json", "plantilla": None,
        "detalles": [{"id": "via", "manifiesto": D_A, "posicion_mm": [30, 175]},
                     {"id": "perfil", "manifiesto": D_B, "posicion_mm": [30, 30]}],
        "rosa_vientos": {"visible": True, "posicion_mm": [100, 450]},
        "rotulo": ROTULO_EJEMPLO},
    "v2_rotulo_raro": {
        "rotulo": {"titulo": ["LÍNEA 1", "LÍNEA 2"], "hoja": 2, "notas": {"archivos": ["a.txt"]},
                   "campo_futuro": {"x": 1}},
        "detalles": [{"id": "x", "manifiesto": D_A, "posicion_mm": [30, 40]}],
        "formato": "../formato.json", "version": 2},
}

IDA_Y_VUELTA = """
    const res = {};
    for (const [nombre, plano] of Object.entries(entrada.planos)) {
      const r = L.leerPlano(JSON.stringify(plano, null, 2), entrada.datos);
      if (r.errores.length) { res[nombre] = {errores: r.errores}; continue; }
      const origen = entrada.datos.rosa_vientos.rect_mm;
      const rosa = r.rosa || {visible: true, pos: [origen[0], origen[1]]};  // como el editor
      const modelo = R.crearModelo(r.rotulo, entrada.datos.rotulo.definicion);
      const texto = L.serializarPlano(r.colocaciones, entrada.datos,
                                      {rosa: rosa, rotulo: R.serializar(modelo), original: r.original});
      const guardado = JSON.parse(texto);
      res[nombre] = {igual: R.igualProfundo(guardado, plano), guardado: guardado,
                     claves: Object.keys(guardado), clavesOriginal: Object.keys(plano)};
    }
    return res;
"""


def test_ida_y_vuelta_sin_tocar_nada_deja_el_json_identico(datos):
    r = js(IDA_Y_VUELTA, {"planos": PLANOS, "datos": datos})
    for nombre, plano in PLANOS.items():
        assert "errores" not in r[nombre], (nombre, r[nombre].get("errores"))
        assert r[nombre]["guardado"] == plano, nombre  # igualdad profunda (también en Python)
        assert r[nombre]["igual"] is True, nombre
        assert r[nombre]["claves"] == r[nombre]["clavesOriginal"], nombre  # mismo orden


def test_ida_y_vuelta_del_ejemplo_real_si_esta_disponible(datos):
    """El plano de ejemplo real (data/, no versionado) con sus manifiestos cambiados al
    catálogo sintético: el rótulo y todo lo demás salen idénticos."""
    ruta = Path(__file__).parent.parent / "data" / "pruebas" / "planos" / "ejemplo_rotulo_v2.json"
    if not ruta.is_file():
        pytest.skip("no está el ejemplo real (data/ no se versiona)")
    plano = json.loads(ruta.read_text(encoding="utf-8"))
    plano["formato"] = "../formato.json"
    for d, m in zip(plano["detalles"], [D_A, D_B]):
        d["manifiesto"] = m
    r = js(IDA_Y_VUELTA, {"planos": {"real": plano}, "datos": datos})
    assert r["real"]["guardado"] == plano


def test_solo_cambia_lo_que_se_toca(datos):
    plano = PLANOS["v2_ejemplo_completo"]
    r = js("""
        const r = L.leerPlano(JSON.stringify(entrada.plano), entrada.datos);
        r.colocaciones[1].pos = [40, 30];                       // se mueve UN detalle
        const modelo = R.crearModelo(r.rotulo, entrada.datos.rotulo.definicion);
        R.cambiar(modelo, "titulo", "OTRO TÍTULO");             // se cambia UN campo
        const g = L.objetoPlano(r.colocaciones, entrada.datos,
                                {rosa: r.rosa, rotulo: R.serializar(modelo), original: r.original});
        return g;
    """, {"plano": plano, "datos": datos})
    assert r["detalles"][0] == plano["detalles"][0]  # el otro, tal como vino
    assert r["detalles"][1] == {"id": "perfil", "manifiesto": D_B, "posicion_mm": [40, 30]}
    esperado = copy.deepcopy(plano["rotulo"])
    esperado["titulo"] = "OTRO TÍTULO"
    assert r["rotulo"] == esperado
    assert list(r["rotulo"]) == list(plano["rotulo"])  # mismo orden de claves
    assert r["rosa_vientos"] == plano["rosa_vientos"]


def test_plano_nuevo_con_la_rosa_en_su_sitio_no_la_escribe(datos):
    r = js("""
        const d = entrada.datos.detalles[0];
        const origen = entrada.datos.rosa_vientos.rect_mm;
        const sin = L.objetoPlano([{id: "x", detalle: d, pos: [30, 40]}], entrada.datos,
                                  {rosa: {visible: true, pos: [origen[0], origen[1]]}});
        const movida = L.objetoPlano([{id: "x", detalle: d, pos: [30, 40]}], entrada.datos,
                                     {rosa: {visible: true, pos: [100, 300]}});
        return {sin, movida};
    """, {"datos": datos})
    assert "rosa_vientos" not in r["sin"] and r["sin"]["version"] == 1
    assert r["movida"]["rosa_vientos"] == {"visible": True, "posicion_mm": [100, 300]}
    assert r["movida"]["version"] == 2


# --- modelo del rótulo ------------------------------------------------------------------------

def test_modelo_cambiar_y_volver_atras_no_deja_cambios():
    r = js("""
        const m = R.crearModelo(entrada.rotulo, null);
        const inicial = R.serializar(m);
        R.cambiar(m, "hoja", 5);
        const cambiado = R.serializar(m);
        R.cambiar(m, "hoja", 1);                       // vuelve al valor original
        const vuelto = R.serializar(m);
        R.cambiar(m, "revisor", undefined);           // quitar un campo
        const sin = R.serializar(m);
        R.cambiar(m, "nuevo", "X");
        return {inicial, cambiado, hay: R.hayCambios(R.crearModelo(entrada.rotulo, null)),
                vuelto, sin, final: Object.keys(R.serializar(m))};
    """, {"rotulo": ROTULO_EJEMPLO})
    assert r["inicial"] == ROTULO_EJEMPLO and r["vuelto"] == ROTULO_EJEMPLO
    assert r["cambiado"]["hoja"] == 5 and r["hay"] is False
    assert "revisor" not in r["sin"]
    assert r["final"][-1] == "nuevo"
    assert js("return R.serializar(R.crearModelo(null, null)) === undefined;") is True


def test_notas_adicionales_con_vinetas_conservan_los_archivos():
    r = js("""
        const m = R.crearModelo(entrada.rotulo, null);
        const vista = R.notas(m);
        R.cambiarNotasAdicionales(m, [
          {texto: "PRIMERA.", vinetas: []},
          {texto: "CON VIÑETAS:", vinetas: ["UNA.", "  ", "DOS."]},
          vista.adicionales[1]]);
        const despues = R.valor(m, "notas");
        R.cambiarNotasAdicionales(m, []);
        return {vista, despues, vacia: R.valor(m, "notas")};
    """, {"rotulo": ROTULO_EJEMPLO})
    assert r["vista"]["archivos"] == ROTULO_EJEMPLO["notas"]["archivos"]
    assert r["vista"]["adicionales"] == [
        {"texto": "EL PERFIL K0+010 SE MUESTRA A ESCALA 1:50.", "vinetas": []},
        {"texto": "LOS MATERIALES CUMPLIRÁN:", "vinetas": ["NORMA A.", "NORMA B."]}]
    assert r["despues"] == {"archivos": ROTULO_EJEMPLO["notas"]["archivos"], "adicionales": [
        "PRIMERA.", {"texto": "CON VIÑETAS:", "vinetas": ["UNA.", "DOS."]},
        {"texto": "LOS MATERIALES CUMPLIRÁN:", "vinetas": ["NORMA A.", "NORMA B."]}]}
    assert r["vacia"] == {"archivos": ROTULO_EJEMPLO["notas"]["archivos"]}


def test_lo_que_no_se_puede_editar_se_avisa(datos):
    r = js("""
        return R.noRepresentable(R.crearModelo(entrada.rotulo, entrada.datos.rotulo.definicion));
    """, {"rotulo": {**ROTULO_EJEMPLO, "titulo": ["A", "B"], "campo_futuro": 1,
                     "revisor": {"raro": 1}}, "datos": datos})
    # Desde la 4.3b las listas de líneas (título, REVISÓ) sí se editan: ya no se avisan.
    assert r == ["notas.archivos (3 archivo(s) .txt referidos)",
                 "rotulo.revisor (valor que el formulario no sabe mostrar)",
                 "rotulo.campo_futuro (el formato no tiene ese campo)"]


def test_resumen_del_catalogo():
    catalogo = {"grupos": [{"titulo": "General", "archivos": [
        {"notas": [{"texto": "A", "vinetas": ["x", "y"]}, {"texto": "B", "vinetas": []}],
         "problemas": ["p"]}]}, {"titulo": "vias", "archivos": []}]}
    assert js("return R.resumenCatalogo(entrada);", catalogo) == {
        "grupos": 2, "archivos": 1, "notas": 2, "vinetas": 2, "problemas": 1}
