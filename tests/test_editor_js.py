"""Funciones puras del editor (editor_logica.js) ejecutadas con Node.

Comparan el JS con Python: centrado igual a `posicion_centrada`, advertencias iguales a las
de `componer`, y un plano.json escrito por el editor que `leer_plano` + `componer_plano`
aceptan. Si Node no está instalado, se saltan.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

import componedor
from componedor.advertencias import PLANTILLAS
from componedor.colocar import motivo_fuera_de_zona, posicion_centrada
from componedor.componer import componer_plano
from componedor.datos_editor import construir_datos_editor
from componedor.plano import leer_plano
from conftest import crear_paquete_real, crear_plantilla_sintetica, escribir_formato

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node no está instalado")

LOGICA = Path(componedor.__file__).parent / "editor" / "editor_logica.js"
AREA = [22.7, 22.7, 662.4, 571.3]
ROSA = [612.0, 51.0, 652.0, 91.0]


def js(codigo: str, entrada=None):
    """Ejecuta `codigo` (cuerpo de función; usa L y `entrada`) y devuelve su resultado."""
    script = (
        f"const L = require({json.dumps(str(LOGICA))});"
        "const entrada = JSON.parse(require('fs').readFileSync(0, 'utf8'));"
        f"const salida = (function () {{ {codigo} }})();"
        "process.stdout.write(JSON.stringify(salida === undefined ? null : salida));"
    )
    resultado = subprocess.run([NODE, "-e", script], input=json.dumps(entrada),
                               capture_output=True, text=True, encoding="utf-8")
    assert resultado.returncode == 0, resultado.stderr
    return json.loads(resultado.stdout)


@pytest.fixture
def entorno(tmp_path):
    """Formato con plantilla sintética y una «rosa»; paquetes a (260 x 120 mm) y uno rechazado."""
    plantilla = crear_plantilla_sintetica(tmp_path / "rotulo.pdf", elementos_mm=[ROSA])
    escribir_formato(tmp_path / "formato.json", plantilla=plantilla,
                     elementos_plantilla=[{"nombre": "rosa_vientos", "rect_mm": ROSA}])
    crear_paquete_real(tmp_path / "input", "a")
    crear_paquete_real(tmp_path / "input", "malo",
                       cambiar={"scale.physical_scale_guaranteed": False})
    (tmp_path / "editor").mkdir()
    datos, _ = construir_datos_editor(tmp_path / "input", tmp_path / "formato.json",
                                      tmp_path / "editor")
    datos["advertencias"] = PLANTILLAS
    return tmp_path, datos


# --- coordenadas -----------------------------------------------------------------------------

def test_papel_a_pantalla_invierte_y_una_sola_vez():
    r = js("""
        const e = L.escalaDeImagen({ancho_mm: 841, alto_mm: 594}, {ancho_px: 1600, alto_px: 1131});
        const ida = L.papelAPantalla(100, 200, e);
        return {
          origen: L.papelAPantalla(0, 0, e),              // abajo-izquierda del papel
          esquina: L.papelAPantalla(841, 594, e),         // arriba-derecha del papel
          vuelta: L.pantallaAPapel(ida.x, ida.y, e),
          rect: L.rectPapelAPantalla([10, 20, 110, 70], e),
        };
    """)
    assert r["origen"] == {"x": 0, "y": 1131}
    assert r["esquina"]["x"] == pytest.approx(1600) and r["esquina"]["y"] == pytest.approx(0)
    assert r["vuelta"]["x"] == pytest.approx(100) and r["vuelta"]["y"] == pytest.approx(200)
    # X e Y con su propia escala: 1600/841 y 1131/594 px por mm.
    assert r["rect"]["ancho"] == pytest.approx(100 * 1600 / 841)
    assert r["rect"]["alto"] == pytest.approx(50 * 1131 / 594)
    assert r["rect"]["y"] == pytest.approx((594 - 70) * 1131 / 594)  # arriba del rectángulo


# --- área de dibujo --------------------------------------------------------------------------

@pytest.mark.parametrize("pos, esperado", [
    ([100, 100], [100, 100]),            # dentro: no cambia
    ([0, 100], [22.7, 100]),             # por la izquierda
    ([600, 100], [662.4 - 260, 100]),    # por la derecha
    ([100, 0], [100, 22.7]),             # por abajo
    ([100, 560], [100, 571.3 - 120]),    # por arriba
    ([-50, 900], [22.7, 571.3 - 120]),   # esquina
])
def test_clamp_a_la_zona(pos, esperado):
    r = js("return L.clampAZona(entrada.pos, [260, 120], entrada.area);", {"pos": pos, "area": AREA})
    assert r == pytest.approx(esperado)
    ocupado = (r[0], r[1], r[0] + 260, r[1] + 120)
    assert motivo_fuera_de_zona(ocupado, "area_dibujo", tuple(AREA)) is None  # regla de componer


def test_clamp_detalle_que_no_cabe():
    assert js("return L.clampAZona([30, 30], [700, 120], entrada);", AREA) is None


@pytest.mark.parametrize("tamano", [(260, 120), (416.9798451741536, 119.40286466810437),
                                    (639.7, 548.6), (10.123, 3.21)])
def test_centrado_igual_que_python(tamano):
    r = js("return L.posicionCentrada(entrada.t, entrada.z);", {"t": tamano, "z": AREA})
    assert tuple(r) == posicion_centrada(tamano, tuple(AREA))  # exactamente igual


def test_redondeo_hacia_dentro_en_los_bordes():
    # Pegado a la derecha y arriba: x = 662,4 - 416,9798…; redondear al más cercano lo
    # sacaría unas milésimas. El editor redondea hacia dentro.
    tam = [416.9798451741536, 119.40286466810437]
    r = js("""
        const max = L.clampAZona([9999, 9999], entrada.t, entrada.z);
        const min = L.clampAZona([-9999, -9999], entrada.t, entrada.z);
        return {max: L.redondearDentro(max, entrada.t, entrada.z),
                min: L.redondearDentro(min, entrada.t, entrada.z),
                medio: L.redondearDentro([100.004999, 200.005001], entrada.t, entrada.z)};
    """, {"t": tam, "z": AREA})
    for x, y in (r["max"], r["min"]):
        assert round(x * 100) == pytest.approx(x * 100) and round(y * 100) == pytest.approx(y * 100)
        ocupado = (x, y, x + tam[0], y + tam[1])
        assert motivo_fuera_de_zona(ocupado, "area_dibujo", tuple(AREA)) is None
    assert r["max"] == [245.42, 451.89]
    assert r["min"] == [22.7, 22.7]
    assert r["medio"] == [100.0, 200.01]


def test_ajustar_a_paso_e_id_unico():
    r = js("""return {paso: [L.ajustarAPaso(12.34, 1), L.ajustarAPaso(12.34, 5), L.ajustarAPaso(12.36, 0.1)],
                      ids: [L.idUnico('a', new Set()), L.idUnico('a', new Set(['a'])),
                            L.idUnico('a', new Set(['a', 'a_2', 'a_3']))]};""")
    assert r["paso"] == pytest.approx([12, 10, 12.4])
    assert r["ids"] == ["a", "a_2", "a_4"]


# --- advertencias: mismos criterios, orden y textos que componer -----------------------------

def test_advertencias_iguales_que_componer(entorno):
    carpeta, datos = entorno
    # Página 260 x 120; dibujo X +37,3..+237,3, Y +21,3..+101,3. Rosa: X 612..652, Y 51..91.
    # d1-d2: dibujos traslapados; d2-d3: solo páginas; d4: su dibujo sobre la rosa;
    # d5 (x = 360: página hasta 620 > 612, dibujo hasta 597,3 < 612): solo su página toca la rosa.
    posiciones = {"d1": [30, 300], "d2": [130, 320], "d3": [360, 300], "d4": [400, 40],
                  "d5": [360, 40]}
    plano = carpeta / "plano.json"
    plano.write_text(json.dumps({"version": 1, "formato": "formato.json", "detalles": [
        {"id": i, "manifiesto": "input/a.manifest.json", "posicion_mm": p}
        for i, p in posiciones.items()]}), encoding="utf-8")
    resultado = componer_plano(leer_plano(plano), carpeta / "p.pdf")
    colocados = [{"id": c.id, "pagina": list(c.ocupado), "dibujo": list(c.dibujo)}
                 for c in resultado.detalles]
    r = js("return L.advertencias(entrada.c, entrada.e, entrada.p);",
           {"c": colocados, "e": datos["elementos_plantilla"], "p": PLANTILLAS})
    assert [a["texto"] for a in r] == resultado.advertencias
    assert {a["clave"] for a in r} == set(PLANTILLAS)  # los cuatro tipos aparecen
    assert {a["nivel"] for a in r} == {"aviso", "fuerte", "muy_fuerte"}


# --- plano.json: el editor escribe, Python lee y compone -------------------------------------

def test_plano_guardado_por_el_editor_lo_acepta_componer(entorno):
    carpeta, datos = entorno
    texto = js("""
        const d = entrada.datos.detalles[0];
        const zona = L.zonaEditable(entrada.datos);
        const colocaciones = [
          {id: d.id, detalle: d, pos: L.clampAZona([9999, 9999], d.tamano_pagina_mm, zona)},
          {id: L.idUnico(d.id, new Set([d.id])), detalle: d, pos: [30.123456, 430.98765]},
        ];
        return L.serializarPlano(colocaciones, entrada.datos);
    """, {"datos": datos})
    assert texto.endswith("\n") and "\r" not in texto
    ruta = carpeta / "editor" / "plano.json"  # junto a editor.html, como pide el editor
    ruta.write_bytes(texto.encode("utf-8"))
    plano = leer_plano(ruta)
    assert [d.id for d in plano.detalles] == ["a", "a_2"]
    assert plano.detalles[1].posicion_mm == (30.12, 430.99)
    assert plano.plantilla is None
    resultado = componer_plano(plano, carpeta / "editor" / "plano.pdf")
    assert (carpeta / "editor" / "plano.pdf").is_file()
    # Pegado al borde derecho y superior, sin salirse (redondeo hacia dentro).
    assert resultado.detalles[0].ocupado[2] <= 662.4 and resultado.detalles[0].ocupado[3] <= 571.3


def test_leer_plano(entorno):
    _, datos = entorno
    planos = {
        "ok": {"version": 1, "formato": "../formato.json", "detalles": [
            {"id": "x", "manifiesto": "../input/a.manifest.json", "posicion_mm": [30, 40]},
            {"id": "c", "manifiesto": "..\\input\\a.manifest.json", "centrar": True}]},
        "version": {"version": 2, "detalles": [
            {"id": "x", "manifiesto": "../input/a.manifest.json", "posicion_mm": [30, 40]}]},
        "desconocido": {"version": 1, "detalles": [
            {"id": "x", "manifiesto": "../input/otro.manifest.json", "posicion_mm": [30, 40]}]},
        "rechazado": {"version": 1, "detalles": [
            {"id": "x", "manifiesto": "../input/malo.manifest.json", "posicion_mm": [30, 40]}]},
        "repetido": {"version": 1, "detalles": [
            {"id": "x", "manifiesto": "../input/a.manifest.json", "posicion_mm": [30, 40]},
            {"id": "x", "manifiesto": "../input/a.manifest.json", "posicion_mm": [330, 40]}]},
        "fuera": {"version": 1, "detalles": [
            {"id": "x", "manifiesto": "../input/a.manifest.json", "posicion_mm": [600, 40]}]},
        "roto": "{ esto no es json",
    }
    r = js("""
        const res = {};
        for (const [k, v] of Object.entries(entrada.planos)) {
          res[k] = L.leerPlano(typeof v === 'string' ? v : JSON.stringify(v), entrada.datos);
        }
        return res;
    """, {"planos": planos, "datos": datos})
    assert r["ok"]["errores"] == [] and r["ok"]["avisos"] == []
    assert [c["pos"] for c in r["ok"]["colocaciones"]] == [
        [30, 40], list(posicion_centrada((260.0, 120.0), tuple(AREA)))]
    assert r["version"]["errores"] == ["version: versión 2 no soportada; el editor entiende la versión 1."]
    assert "no está en el catálogo del editor" in r["desconocido"]["errores"][0]
    assert "el paquete 'malo' está rechazado" in r["rechazado"]["errores"][0]
    assert "'x' está repetido" in r["repetido"]["errores"][0]
    assert r["fuera"]["errores"] == []
    assert r["fuera"]["colocaciones"][0]["pos"] == pytest.approx([662.4 - 260, 40])
    assert "se salía del área de dibujo" in r["fuera"]["avisos"][0]
    assert r["roto"]["errores"][0].startswith("El archivo no es un JSON válido")
    for clave in ("version", "desconocido", "rechazado", "repetido", "roto"):
        assert r[clave]["colocaciones"] == []  # con errores no se carga nada
