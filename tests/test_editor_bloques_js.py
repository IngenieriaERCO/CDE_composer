"""Bloques de un DXF sin exportar en el editor (editor_bloques.js, en Node): la caja exacta, las
escalas, el tirador, el PNG en la hoja y el plano.json versión 3. Se comparan con Python."""

import json
import random
import shutil
import subprocess
from pathlib import Path

import pytest
from conftest import ZONA_A1, comando_falso, dxf_falso

import componedor
from componedor.bloques_dxf import escala_sugerida, pagina_mm
from componedor.colocar import exceso_de_tamano
from componedor.inventario import ESCALAS_ESTANDAR
from componedor.plano import leer_plano
from componedor.previa_dxf import leer_previa, pedido_previa
from componedor.trabajador import Trabajador

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node no está instalado")
CARPETA_JS = Path(componedor.__file__).parent / "editor"
SHA = "4b1d" + "0" * 60


def js(codigo: str, entrada=None):
    """Ejecuta `codigo` con B (editor_bloques.js), L (editor_logica.js) y `entrada`."""
    script = (
        f"const B = require({json.dumps(str(CARPETA_JS / 'editor_bloques.js'))});"
        f"const L = require({json.dumps(str(CARPETA_JS / 'editor_logica.js'))});"
        "const entrada = JSON.parse(require('fs').readFileSync(0, 'utf8'));"
        f"const salida = (function () {{ {codigo} }})();"
        "process.stdout.write(JSON.stringify(salida === undefined ? null : salida));"
    )
    r = subprocess.run([NODE, "-e", script], input=json.dumps(entrada), capture_output=True,
                       text=True, encoding="utf-8", check=False)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


# --- paridad con Python -------------------------------------------------------------------------

def test_escalas_iguales_a_python():
    assert js("return B.ESCALAS;") == list(ESCALAS_ESTANDAR)


def test_pagina_exceso_y_sugerida_iguales_a_python():
    azar = random.Random(7)
    casos = [((10.0, 4.0), 5.0), ((31.0, 4.0), 5.0), ((32.0, 4.0), 5.0),
             ((957.18, 1350.019), 5.0), ((200000.0, 1.0), 5.0), ((0.0, 0.0), 0.0)]
    casos += [((azar.uniform(0, 3000), azar.uniform(0, 3000)), azar.choice([0, 5, 12.5]))
              for _ in range(200)]
    r = js("""return entrada.casos.map(([t, m]) => ({
        paginas: B.ESCALAS.map((n) => B.paginaMm(t, n, m)),
        excesos: B.ESCALAS.map((n) => B.excesoDeTamano(B.paginaMm(t, n, m), entrada.zona)),
        sugerida: B.escalaSugerida(t, m, entrada.zona)}));""",
           {"casos": casos, "zona": ZONA_A1})
    for (t, m), x in zip(casos, r):
        assert x["sugerida"] == escala_sugerida(t, m, ZONA_A1)
        for n, p, e in zip(ESCALAS_ESTANDAR, x["paginas"], x["excesos"]):
            assert p == pytest.approx(pagina_mm(t, n, m), abs=1e-9)
            assert e == pytest.approx(exceso_de_tamano(pagina_mm(t, n, m), ZONA_A1), abs=1e-9)


def test_escala_vecina_texto_y_lectura():
    r = js("""return [B.escalaVecina(100, +1), B.escalaVecina(100, -1), B.escalaVecina(50, +1),
                      B.escalaVecina(10000, -1), B.escalaVecina(300, +1), B.escalaVecina(300, -1),
                      B.textoEscala(2000), B.leerEscala("1:2000"), B.leerEscala("1:0"),
                      B.leerEscala("1/50"), B.leerEscala("1:12.5")];""")
    assert r == [75, 200, 25, 10000, 250, 500, "1:2000", 2000, None, None, None]


# --- la caja en la hoja ---------------------------------------------------------------------------

def test_caja_centro_fijo_y_limite():
    r = js("""
      const z = entrada.zona, t = [10, 4], m = 5;
      const p50 = B.paginaMm(t, 50, m), p100 = B.paginaMm(t, 100, m);
      const centro = [300, 200];
      return {
        r50: B.rectCentrado(centro, p50), r100: B.rectCentrado(centro, p100),
        dibujo: B.rectDibujo(centro, p50, m),
        pegado: B.centroLimitado([0, 1000], p50, z),
        grande: B.centroLimitado([0, 1000], [700, 90], z),
        estados: [B.estadoCaja(centro, p50, z), B.estadoCaja([30, 200], p50, z),
                  B.estadoCaja(centro, B.paginaMm([32, 4], 50, m), z)],
        tirador: [B.escalaPorTirador(centro, [405, 245], t, m), B.escalaPorTirador(centro, [355, 222], t, m),
                  B.escalaPorTirador(centro, [301, 201], t, m)],
      };""", {"zona": ZONA_A1})
    assert r["r50"] == pytest.approx([195, 155, 405, 245])  # 210 × 90 mm centrada en (300, 200)
    assert r["r100"] == pytest.approx([245, 175, 355, 225])  # mismo centro, 110 × 50 mm
    assert r["dibujo"] == pytest.approx([200, 160, 400, 240])
    assert r["pegado"] == pytest.approx([22.7 + 105, 571.3 - 45])  # página dentro del área
    assert r["grande"] == pytest.approx([22.7, 571.3 - 45])  # no cabe en X: centro en el área
    ok, fuera, no_cabe = r["estados"]
    assert ok == {"cabe": True, "dentro": True, "exceso": [0, 0]}
    assert fuera["cabe"] is True and fuera["dentro"] is False
    assert no_cabe["cabe"] is False and no_cabe["exceso"] == pytest.approx([10.3, 0])
    assert r["tirador"] == [50, 100, 10000]  # la esquina más cerca del puntero


# --- el PNG en la hoja ----------------------------------------------------------------------------

def test_la_vista_previa_cae_sobre_la_caja(tmp_path):
    """Un punto CAD conocido (la marca del PNG del trabajador falso) cae en el mismo lugar del
    papel por la fórmula de la caja y por la imagen estirada en su rectángulo (< medio píxel),
    a dos escalas y aunque lo dibujado sea menor que la caja de load (sin los 3DSOLID)."""
    import pymupdf

    marca = [1031.0, 2007.0]
    ruta = dxf_falso(tmp_path / "a.dxf", blocks=[
        {"name": "B", "size_cad": [40.0, 20.0], "min": [1000.0, 2000.0], "marca": marca,
         "bounds_previa": {"min": [1002.0, 2001.0], "max": [1040.0, 2019.0]}}])
    t = Trabajador(comando_falso(), tmp_path / "trabajo")
    t.iniciar()
    try:
        carga = t.pedir("load", {"dxf": str(ruta), "units": None, "margin_mm": 5.0})
        previa = leer_previa(t.pedir("preview", pedido_previa(carga["session"], "B#1")),
                             tmp_path / "trabajo" / "previews")
    finally:
        t.cerrar()
    pix = pymupdf.Pixmap(str(previa["png"]))
    negros = [(x, y) for x in range(pix.width) for y in range(pix.height)
              if pix.pixel(x, y)[3] == 255]
    cx = sum(x for x, _ in negros) / len(negros) + 0.5  # centro del cuadrito, en px
    cy = sum(y for _, y in negros) / len(negros) + 0.5
    previa.pop("png")
    for n in (50, 200):
        r = js("""
          const caja = {min: [1000, 2000], max: [1040, 2020]};
          const k = B.mmPorUnidadCad(1000, entrada.n);
          return {rect: B.imagenEnPapel(entrada.previa, B.centroCaja(caja), [300, 250], k),
                  punto: B.cadAPapel(entrada.marca, B.centroCaja(caja), [300, 250], k), k};
        """, {"previa": previa, "marca": marca, "n": n})
        x0, y0, x1, y1 = r["rect"]
        en_imagen = (x0 + cx / pix.width * (x1 - x0), y1 - cy / pix.height * (y1 - y0))
        medio_px = 0.5 * r["k"] / previa["cad_a_px"][0]
        assert en_imagen[0] == pytest.approx(r["punto"][0], abs=medio_px)
        assert en_imagen[1] == pytest.approx(r["punto"][1], abs=medio_px)
        # Y cae donde dice la fórmula de la caja: 20 mm por m a 1:50 desde el centro (1020, 2010).
        assert r["punto"] == pytest.approx([300 + r["k"] * 11, 250 - r["k"] * 3])


# --- plano.json versión 3 -------------------------------------------------------------------------

CATALOGO = {"dxf": {"nombre": "GUAMO_prueba.dxf", "ruta": "C:\\obras\\GUAMO_prueba.dxf",
                    "archivo_plano": "../dxf/GUAMO_prueba.dxf", "sha256": SHA, "bytes": 6781020},
            "unidades": {"nombre": "m"}, "margen_mm": 5.0}


def colocado(id_, nombre, handle, escala, centro, tamano=(10.0, 4.0), ocurrencia=1):
    return {"id": id_, "escala": escala, "centro": list(centro),
            "bloque": {"nombre": nombre, "handle": handle, "ocurrencia": ocurrencia,
                       "tamano_m": list(tamano), "caja_exacta": True}}


def test_el_editor_escribe_la_version_3_y_python_la_lee(entorno_editor):
    carpeta, datos = entorno_editor
    texto = js("""
      const dxf = B.entradaDxf(entrada.catalogo);
      const cs = entrada.colocados.map((c) => Object.assign(c, {bloque: Object.assign(c.bloque, {dxf})}));
      return L.serializarPlano(cs, entrada.datos);""", {
        "catalogo": CATALOGO, "datos": datos,
        "colocados": [colocado("BLOQUE1", "BLOQUE1", "50CA", 5000, (342.554, 296.996),
                               (957.18, 1350.019)),
                      colocado("Carro", "Carro frontal 1", "1A3", 50, (100, 100), ocurrencia=2)]})
    plano = json.loads(texto)
    assert list(plano) == ["version", "formato", "plantilla", "dxf", "detalles"]
    assert plano["version"] == 3
    assert plano["dxf"] == [{"id": "d1", "archivo": "../dxf/GUAMO_prueba.dxf", "sha256": SHA,
                             "bytes": 6781020, "unidades": "m", "margen_mm": 5.0}]
    assert plano["detalles"][0] == {
        "id": "BLOQUE1", "origen": {"dxf": "d1", "bloque": "BLOQUE1", "handle": "50CA",
                                    "ocurrencia": 1, "escala": "1:5000",
                                    "tamano_m": [957.18, 1350.019], "caja_exacta": True},
        "centro_mm": [342.55, 297.0]}
    ruta = carpeta / "editor" / "plano.json"
    ruta.write_text(texto, encoding="utf-8")
    leido = leer_plano(ruta)
    assert [b.id for b in leido.pendientes] == ["BLOQUE1", "Carro"]
    assert leido.pendientes[1].ocurrencia == 2 and leido.pendientes[1].escala == 50.0
    assert leido.dxf[0].archivo == carpeta / "editor" / "../dxf/GUAMO_prueba.dxf"


def test_abrir_y_guardar_un_plano_v3_sin_tocar_nada_es_identico(entorno_editor):
    _, datos = entorno_editor
    original = {"version": 3, "formato": "../formato.json", "plantilla": None,
                "dxf": [{"id": "dA", "archivo": "C:/x/GUAMO_prueba.dxf", "sha256": SHA,
                         "margen_mm": 5}],
                "detalles": [
                    {"id": "listo", "manifiesto": "../input/a.manifest.json", "posicion_mm": [30, 40]},
                    {"id": "B", "origen": {"dxf": "dA", "bloque": "B", "handle": "1A",
                                           "ocurrencia": 1, "escala": "1:50", "tamano_m": [10, 4]},
                     "centro_mm": [300, 200], "etiqueta_escala": False}]}
    texto = json.dumps(original, indent=2) + "\n"
    r = js("""
      const leido = L.leerPlano(entrada.texto, entrada.datos);
      const igual = L.serializarPlano(leido.colocaciones, entrada.datos, {original: leido.original});
      const b = leido.colocaciones[1];
      b.escala = 100;  // cambia solo la escala: el centro queda igual
      const otro = JSON.parse(L.serializarPlano(leido.colocaciones, entrada.datos, {original: leido.original}));
      return {errores: leido.errores, avisos: leido.avisos, igual, otro,
              b: {centro: b.centro, nombre: b.bloque.nombre, margen: b.bloque.dxf.margen_mm}};
    """, {"texto": texto, "datos": datos})
    assert r["errores"] == [] and r["avisos"] == []
    assert r["igual"] == texto
    assert r["b"] == {"centro": [300, 200], "nombre": "B", "margen": 5}
    assert r["otro"]["dxf"] == original["dxf"]  # la entrada del DXF, tal como vino
    assert r["otro"]["detalles"][1] == {
        "id": "B", "origen": {"dxf": "dA", "bloque": "B", "handle": "1A", "ocurrencia": 1,
                              "escala": "1:100", "tamano_m": [10, 4], "caja_exacta": True},
        "centro_mm": [300, 200], "etiqueta_escala": False}


def test_el_editor_rechaza_un_plano_v3_mal_escrito(entorno_editor):
    _, datos = entorno_editor
    bloque = {"id": "B", "origen": {"dxf": "d1", "bloque": "B", "handle": "1A", "ocurrencia": 1,
                                    "escala": "1:50", "tamano_m": [10, 4]}, "centro_mm": [300, 200]}
    planos = {
        "sin_v3": {"version": 2, "dxf": [], "detalles": [bloque]},
        "dxf_ajeno": {"version": 3, "dxf": [], "detalles": [bloque]},
        "escala": {"version": 3, "dxf": [{"id": "d1", "archivo": "a.dxf", "sha256": SHA,
                                          "margen_mm": 5}],
                   "detalles": [{**bloque, "origen": {**bloque["origen"], "escala": "50"}}]},
        "fuera": {"version": 3, "dxf": [{"id": "d1", "archivo": "a.dxf", "sha256": SHA,
                                         "margen_mm": 5}],
                  "detalles": [{**bloque, "centro_mm": [5000, 200]}]},
    }
    r = js("""const res = {};
      for (const [k, p] of Object.entries(entrada.planos)) res[k] = L.leerPlano(JSON.stringify(p), entrada.datos);
      return res;""", {"planos": planos, "datos": datos})
    assert "dxf: solo existe en la versión 3 del plano" in r["sin_v3"]["errores"][0]
    assert "origen.dxf: 'd1' no está en la lista" in r["dxf_ajeno"]["errores"][0]
    assert "origen.escala: se esperaba «1:N»" in r["escala"]["errores"][0]
    assert r["fuera"]["errores"] == []
    assert r["fuera"]["avisos"] == [("'B' se salía del área de dibujo: su centro se movió a "
                                     "(557.40, 200.00) mm.")]


def test_ids_de_dxf_al_guardar():
    r = js("""
      const a = {id: null, sha256: "a"}, a2 = {id: null, sha256: "a"}, b = {id: "d1", sha256: "b"},
            c = {id: null, sha256: "c"};
      B.asignarIdsDxf([a, b, a2, c]);
      return [a.id, a2.id, b.id, c.id];""")
    assert r == ["d2", "d2", "d1", "d3"]  # d1 ya era de otro DXF del plano abierto


@pytest.fixture
def entorno_editor(tmp_path):
    from conftest import crear_paquete_real, escribir_formato

    from componedor.datos_editor import construir_datos_editor

    escribir_formato(tmp_path / "formato.json")
    crear_paquete_real(tmp_path / "input", "a")
    (tmp_path / "editor").mkdir()
    datos, _ = construir_datos_editor(tmp_path / "input", tmp_path / "formato.json",
                                      tmp_path / "editor")
    return tmp_path, datos


# --- Exportar (etapa 3) --------------------------------------------------------------------------

def test_que_bloques_se_piden_al_exportar():
    catalogo = {"dxf": {"nombre": "GUAMO_prueba.dxf", "sha256": SHA}, "sesion_activa": True,
                "bloques": [{"handle": "50CA"}, {"handle": "1A3"}]}
    dxf = {"nombre": "GUAMO_prueba.dxf", "sha256": SHA, "margen_mm": 5.0}
    otro = {"nombre": "otro.dxf", "sha256": "f" * 64, "margen_mm": 5.0}
    cambiado = {"nombre": "GUAMO_prueba.dxf", "sha256": "e" * 64, "margen_mm": 5.0}

    def c(id_, handle, escala, centro, d=dxf, tamano=(957.18, 1350.019)):
        return {"id": id_, "escala": escala, "centro": list(centro),
                "bloque": {"handle": handle, "tamano_m": list(tamano), "dxf": d}}

    colocaciones = [
        {"id": "exportado", "detalle": {}, "pos": [0, 0]},
        c("ok", "50CA", 5000, (342.55, 297.0)),
        c("grande", "50CA", 2500, (342.55, 297.0)),
        c("afuera", "1A3", 50, (30, 30), tamano=(10, 4)),
        c("ajeno", "50CA", 5000, (342.55, 297.0), d=otro),
        c("viejo", "50CA", 5000, (342.55, 297.0), d=cambiado),
        c("borrado", "FF", 5000, (342.55, 297.0)),
    ]
    r = js("return B.pedidosExportar(entrada.cs, entrada.cat, entrada.zona);",
           {"cs": colocaciones, "cat": catalogo, "zona": ZONA_A1})
    assert r["pedidos"] == [{"id": "ok", "handle": "50CA", "sha256": SHA, "escala": 5000,
                             "centro_mm": [342.55, 297.0]}]
    assert {o["id"]: o["motivo"] for o in r["omitidos"]} == {
        "grande": "no cabe a 1:2500: cambie la escala",
        "afuera": "se sale del área de dibujo: muévalo",
        "ajeno": "es de «otro.dxf» y el cargado es «GUAMO_prueba.dxf»",
        "viejo": "el DXF cambió desde que se colocó: «Volver a cargar» primero",
        "borrado": "el bloque ya no está en el DXF"}
    sin = js("return [B.pedidosExportar(entrada.cs, null, entrada.zona).omitidos[0].motivo, "
             "B.pedidosExportar(entrada.cs, Object.assign({}, entrada.cat, {sesion_activa: false}),"
             " entrada.zona).omitidos[0].motivo, B.posicionExportada([342.55, 297], [100.718, 140.0019])];",
             {"cs": colocaciones[1:2], "cat": catalogo, "zona": ZONA_A1})
    assert sin[:2] == ["cargue «GUAMO_prueba.dxf» con «Cargar DXF»",
                       "vuelva a cargar el DXF («Volver a cargar»)"]
    assert sin[2] == pytest.approx([241.832, 156.9981])


# --- escalas escritas a mano y «Ajustar a la hoja» -----------------------------------------------

def test_escala_escrita():
    r = js("""return ["1:3500", "3500", " 1 : 3500 ", "1:3000", "1", "100000",
                      "0", "100001", "1:12.5", "abc", "", "-50", "1/50"].map((t) => B.leerEscalaEscrita(t));""")
    assert r[:6] == [{"n": 3500, "aviso": "escala no normalizada"}] * 3 + [
        {"n": 3000, "aviso": None}, {"n": 1, "aviso": "escala no normalizada"},
        {"n": 100000, "aviso": "escala no normalizada"}]
    for x in r[6:]:
        assert x == {"error": "Escala no válida: escriba 1:N o N, con N entero de 1 a 100000 "
                              "(por ejemplo 1:3500)."}


def test_teclas_desde_una_escala_escrita():
    r = js("return [B.escalaVecina(3500, +1), B.escalaVecina(3500, -1), B.escalaVecina(3, +1), "
           "B.escalaVecina(3, -1), B.escalaVecina(50000, +1)];")
    assert r == [3000, 4000, 3, 5, 10000]  # a la anterior o siguiente de la lista


def test_ajustar_a_la_hoja_es_la_exacta_mas_grande():
    """N entero más chico con el que cabe (contra Python: a N cabe y a N − 1 no)."""
    casos = [(957.18, 1350.019), (10.0, 4.0), (31.0, 4.0), (0.398, 0.768), (5000.0, 10.0)]
    r = js("return entrada.casos.map((t) => B.escalaAjustada(t, 5, entrada.zona));",
           {"casos": casos, "zona": ZONA_A1})
    assert r[0] == 2507  # BLOQUE1: más grande que 1:3000, la normalizada
    for t, n in zip(casos, r):
        assert exceso_de_tamano(pagina_mm(t, n, 5.0), ZONA_A1) == (0.0, 0.0)
        if n > 1:
            assert exceso_de_tamano(pagina_mm(t, n - 1, 5.0), ZONA_A1) != (0.0, 0.0)
    assert js("return B.escalaAjustada([1e9, 1], 5, entrada);", ZONA_A1) is None


def test_escala_no_normalizada_en_el_plano_v3(entorno_editor):
    carpeta, datos = entorno_editor
    texto = js("""
      const dxf = B.entradaDxf(entrada.catalogo);
      const c = Object.assign(entrada.c, {bloque: Object.assign(entrada.c.bloque, {dxf})});
      return L.serializarPlano([c], entrada.datos);""", {
        "catalogo": CATALOGO, "datos": datos,
        "c": colocado("BLOQUE1", "BLOQUE1", "50CA", 3500, (342.55, 297.0), (957.18, 1350.019))})
    assert json.loads(texto)["detalles"][0]["origen"]["escala"] == "1:3500"  # tal cual
    ruta = carpeta / "editor" / "plano.json"
    ruta.write_text(texto, encoding="utf-8")
    assert leer_plano(ruta).pendientes[0].escala == 3500.0
    r = js("return L.leerPlano(entrada.texto, entrada.datos).colocaciones[0].escala;",
           {"texto": texto, "datos": datos})
    assert r == 3500
