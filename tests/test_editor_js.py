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
    crear_paquete_real(tmp_path / "input", "s", sin_fondo=True)  # exportador nuevo, sin fondo
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

def _paridad(carpeta, datos, detalles):
    """Compone con Python y calcula las advertencias en JS para el mismo plano. El dato
    `tiene_fondo` del JS sale del catálogo del editor (editor_datos.json), no de Python."""
    plano = carpeta / "plano.json"
    plano.write_text(json.dumps({"version": 1, "formato": "formato.json", "detalles": [
        {"id": i, "manifiesto": f"input/{p}.manifest.json", "posicion_mm": pos}
        for i, p, pos in detalles]}), encoding="utf-8")
    resultado = componer_plano(leer_plano(plano), carpeta / "p.pdf", sobrescribir=True)
    catalogo = {d["id"]: d for d in datos["detalles"]}
    colocados = [{"id": c.id, "pagina": list(c.ocupado), "dibujo": list(c.dibujo),
                  "tiene_fondo": catalogo[c.prefijo]["tiene_fondo"]} for c in resultado.detalles]
    assert [x["tiene_fondo"] for x in colocados] == [c.tiene_fondo for c in resultado.detalles]
    r = js("return L.advertencias(entrada.c, entrada.e, entrada.p);",
           {"c": colocados, "e": datos["elementos_plantilla"], "p": PLANTILLAS})
    return r, resultado.advertencias


def test_advertencias_iguales_que_componer(entorno):
    carpeta, datos = entorno
    # Página 260 x 120; dibujo X +37,3..+237,3, Y +21,3..+101,3. Rosa: X 612..652, Y 51..91.
    # Con fondo ("a"): d1-d2 dibujos traslapados; d2-d3 solo páginas; d4 dibujo sobre la rosa;
    # d5 (x = 360: página hasta 620 > 612, dibujo hasta 597,3 < 612) solo su página la toca.
    # Sin fondo ("s"): s1-s2 dibujos traslapados; s2-s3 solo páginas (no avisa); s4 dibujo
    # sobre la rosa; mezclas: d1 (con) bajo s1 (sin) y s2 (sin) bajo d2 (con), etc.
    r, python = _paridad(carpeta, datos, [
        ("d1", "a", [30, 300]), ("d2", "a", [130, 320]), ("d3", "a", [360, 300]),
        ("d4", "a", [400, 40]), ("d5", "a", [360, 40]),
        ("s1", "s", [30, 160]), ("s2", "s", [130, 180]), ("s3", "s", [380, 160]),
        ("s4", "s", [390, 30]),
    ])
    assert [a["texto"] for a in r] == python
    assert {a["clave"] for a in r} == set(PLANTILLAS)  # los seis tipos aparecen
    assert {a["nivel"] for a in r} == {"aviso", "fuerte", "muy_fuerte"}


@pytest.mark.parametrize("detalles", [
    [("d1", "s", [30, 300]), ("d2", "s", [280, 300])],  # solo páginas, sin fondo: nada
    [("d1", "a", [30, 300]), ("d2", "s", [280, 300])],  # de encima sin fondo: nada
    [("d1", "s", [30, 300]), ("d2", "a", [280, 300])],  # de encima con fondo: aviso
    [("d1", "s", [360, 40])],                           # página sin fondo sobre la rosa: nada
    [("d1", "a", [360, 40])],                           # página con fondo sobre la rosa
])
def test_paridad_casos_con_y_sin_fondo(entorno, detalles):
    carpeta, datos = entorno
    r, python = _paridad(carpeta, datos, detalles)
    assert [a["texto"] for a in r] == python


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
        "version": {"version": 9, "detalles": [
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
    assert r["version"]["errores"] == [
        "version: versión 9 no soportada; el editor entiende las versiones 1 a 6."]
    assert "no está en el catálogo del editor" in r["desconocido"]["errores"][0]
    assert "el paquete 'malo' está rechazado" in r["rechazado"]["errores"][0]
    assert "'x' está repetido" in r["repetido"]["errores"][0]
    assert r["fuera"]["errores"] == []
    assert r["fuera"]["colocaciones"][0]["pos"] == pytest.approx([662.4 - 260, 40])
    assert "se salía del área de dibujo" in r["fuera"]["avisos"][0]
    assert r["roto"]["errores"][0].startswith("El archivo no es un JSON válido")
    for clave in ("version", "desconocido", "rechazado", "repetido", "roto"):
        assert r[clave]["colocaciones"] == []  # con errores no se carga nada


# --- rosa de los vientos movible y plano.json versión 2 (subfase 4.1) ------------------------

def test_datos_traen_la_rosa(entorno):
    _, datos = entorno
    assert datos["rosa_vientos"] == {"nombre": "rosa_vientos", "rect_mm": ROSA,
                                     "imagen": {"archivo": "rosa.png"}}


@pytest.mark.parametrize("rosa", [None, {"visible": True, "pos": [100, 300]},
                                  {"visible": False, "pos": [612, 51]}])
def test_elementos_visibles_igual_que_python(entorno, rosa):
    from componedor.formato import cargar_formato
    from componedor.rosa import elementos_visibles, rect_destino
    carpeta, datos = entorno
    elementos = [{"nombre": "otro", "rect_mm": [30, 30, 40, 40]}] + datos["elementos_plantilla"]
    r = js("""
        const rosa = entrada.rosa && {visible: entrada.rosa.visible,
                                      rect: L.rectRosa(entrada.original, entrada.rosa.pos)};
        return L.elementosVisibles(entrada.e, rosa);
    """, {"e": elementos, "rosa": rosa, "original": ROSA})
    if rosa is None:
        assert r == elementos  # sin rosa en el formato: sin cambios
        return
    formato = cargar_formato(carpeta / "formato.json")
    destino = rect_destino(tuple(ROSA), tuple(rosa["pos"])) if rosa["visible"] else None
    python = [{"nombre": e.nombre, "rect_mm": list(e.rect)}
              for e in elementos_visibles(formato, destino)]
    assert r[1:] == python and r[0]["nombre"] == "otro"


@pytest.mark.parametrize("rosa_plano, detalles", [
    ({"posicion_mm": [100, 300]}, [("d1", "a", [400, 40]), ("d2", "s", [40, 260])]),
    ({"visible": False}, [("d1", "a", [400, 40]), ("d2", "a", [360, 40])]),
    ({"posicion_mm": [500, 200]}, [("d1", "a", [300, 150]), ("d2", "s", [380, 160])]),
])
def test_advertencias_con_la_rosa_movida_u_oculta_iguales_que_componer(entorno, rosa_plano,
                                                                       detalles):
    carpeta, datos = entorno
    plano = carpeta / "plano.json"
    plano.write_text(json.dumps({"version": 2, "formato": "formato.json",
                                 "rosa_vientos": rosa_plano, "detalles": [
        {"id": i, "manifiesto": f"input/{p}.manifest.json", "posicion_mm": pos}
        for i, p, pos in detalles]}), encoding="utf-8")
    resultado = componer_plano(leer_plano(plano), carpeta / "p.pdf", sobrescribir=True)
    catalogo = {d["id"]: d for d in datos["detalles"]}
    colocados = [{"id": c.id, "pagina": list(c.ocupado), "dibujo": list(c.dibujo),
                  "tiene_fondo": catalogo[c.prefijo]["tiene_fondo"]} for c in resultado.detalles]
    r = js("""
        const v = entrada.rosa.visible !== false;
        const pos = entrada.rosa.posicion_mm || [entrada.datos.rosa_vientos.rect_mm[0],
                                                 entrada.datos.rosa_vientos.rect_mm[1]];
        const rosa = {visible: v, rect: L.rectRosa(entrada.datos.rosa_vientos.rect_mm, pos)};
        const elementos = L.elementosVisibles(entrada.datos.elementos_plantilla, rosa);
        return L.advertencias(entrada.c, elementos, entrada.p).map((a) => a.texto);
    """, {"c": colocados, "datos": datos, "rosa": rosa_plano, "p": PLANTILLAS})
    assert r == resultado.advertencias
    if rosa_plano.get("visible", True):
        assert any("rosa_vientos" in a for a in r)  # la rosa movida sí avisa
    else:
        assert not any("rosa_vientos" in a for a in r)  # oculta: nunca avisa


def test_editor_guarda_version_2_con_rosa_rotulo_y_etiqueta_y_componer_lo_acepta(entorno):
    carpeta, datos = entorno
    rotulo = {"titulo": "PLANTA", "revisiones": [{"ver": "A", "fecha": "2026-11-06"}]}
    texto = js("""
        const d = entrada.datos.detalles[0];
        const colocaciones = [{id: "x", detalle: d, pos: [40, 300], etiqueta_escala: false},
                              {id: "y", detalle: d, pos: [40, 100]}];
        return L.serializarPlano(colocaciones, entrada.datos,
                                 {rosa: {visible: true, pos: [100.004, 450.006]},
                                  rotulo: entrada.rotulo});
    """, {"datos": datos, "rotulo": rotulo})
    guardado = json.loads(texto)
    assert guardado["version"] == 2
    assert guardado["rosa_vientos"] == {"visible": True, "posicion_mm": [100.0, 450.01]}
    assert guardado["rotulo"] == rotulo
    assert guardado["detalles"][0]["etiqueta_escala"] is False
    assert "etiqueta_escala" not in guardado["detalles"][1]
    ruta = carpeta / "editor" / "plano.json"
    ruta.write_text(texto, encoding="utf-8")
    plano = leer_plano(ruta)
    assert plano.rosa.posicion_mm == (100.0, 450.01) and plano.rotulo == rotulo
    resultado = componer_plano(plano, carpeta / "editor" / "plano.pdf")
    assert resultado.rosa.destino == (100.0, 450.01, 140.0, 490.01)


def test_sin_nada_nuevo_el_editor_guarda_version_1(entorno):
    _, datos = entorno
    sin_rosa = dict(datos, rosa_vientos=None)
    texto = js("""
        const d = entrada.detalles[0];
        return L.serializarPlano([{id: "x", detalle: d, pos: [40, 300]}], entrada, {});
    """, sin_rosa)
    assert json.loads(texto)["version"] == 1 and "rosa_vientos" not in json.loads(texto)


def test_leer_plano_version_2(entorno):
    _, datos = entorno
    d = {"id": "x", "manifiesto": "../input/a.manifest.json", "posicion_mm": [30, 40]}
    planos = {
        "ok": {"version": 2, "detalles": [dict(d, etiqueta_escala=False)],
               "rosa_vientos": {"visible": False, "posicion_mm": [100, 300]},
               "rotulo": {"titulo": "PLANTA"}},
        "sin_rosa": {"version": 2, "detalles": [d]},
        "rosa_fuera": {"version": 2, "detalles": [d], "rosa_vientos": {"posicion_mm": [650, 300]}},
        "rosa_mala": {"version": 2, "detalles": [d], "rosa_vientos": {"visble": True}},
        "rotulo_malo": {"version": 2, "detalles": [d], "rotulo": "PLANTA"},
        "v1_con_rosa": {"version": 1, "detalles": [d], "rosa_vientos": {}},
        "etiqueta_mala": {"version": 2, "detalles": [dict(d, etiqueta_escala="no")]},
    }
    r = js("""
        const res = {};
        for (const [k, v] of Object.entries(entrada.planos)) res[k] = L.leerPlano(JSON.stringify(v), entrada.datos);
        return res;
    """, {"planos": planos, "datos": datos})
    ok = r["ok"]
    assert ok["errores"] == [] and ok["rosa"] == {"visible": False, "pos": [100, 300]}
    assert ok["rotulo"] == {"titulo": "PLANTA"}
    assert ok["colocaciones"][0]["etiqueta_escala"] is False
    assert r["sin_rosa"]["rosa"] is None and r["sin_rosa"]["rotulo"] is None
    assert r["rosa_fuera"]["rosa"]["pos"] == pytest.approx([662.4 - 40, 300])
    assert "La rosa de los vientos se salía del área de dibujo" in r["rosa_fuera"]["avisos"][0]
    assert r["rosa_mala"]["errores"] == [
        "rosa_vientos.visble: campo no reconocido (campos válidos: posicion_mm, visible)."]
    assert r["rotulo_malo"]["errores"] == ["rotulo: se esperaba un objeto {...} con los valores del rótulo."]
    assert r["v1_con_rosa"]["errores"] == [
        "rosa_vientos: solo existe en la versión 2 del plano (use \"version\": 2)."]
    assert r["etiqueta_mala"]["errores"] == ["detalles[0].etiqueta_escala: se esperaba true o false."]
