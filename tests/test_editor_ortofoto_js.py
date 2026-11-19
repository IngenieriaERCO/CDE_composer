"""Ortofoto en el editor (editor_ortofoto.js, en Node): la caja CAD de cada detalle, la ficha y
sus avisos, y el plano.json versión 4. Se comparan con Python."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from conftest import MATRIZ_SINTETICA, crear_paquete_real, escribir_formato
from ortofoto_sintetica import crear_geotiff

import componedor
from componedor.datos_editor import construir_datos_editor
from componedor.ortofoto import leer_cabecera
from componedor.plano import leer_plano
from componedor.plano_ortofoto import leer_ortofoto

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node no está instalado")
CARPETA_JS = Path(componedor.__file__).parent / "editor"


def js(codigo: str, entrada=None):
    """Ejecuta `codigo` con O (editor_ortofoto.js), B (bloques), L (lógica) y `entrada`."""
    script = (
        f"const O = require({json.dumps(str(CARPETA_JS / 'editor_ortofoto.js'))});"
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


def cerca(a, b, tol=1e-6):
    return all(abs(x - y) <= tol for x, y in zip(a, b, strict=True))


def test_leer_sistema():
    r = js("""return ["EPSG:9377", "epsg:3116", " 9377 ", "EPSG : 6247", "MAGNA", "", null, "EPSG:12"]
      .map(O.leerSistema);""")
    assert r == ["EPSG:9377", "EPSG:3116", "EPSG:9377", "EPSG:6247", None, None, None, None]


def test_caja_cad_de_un_detalle_exportado_vuelve_a_su_pagina():
    """La caja CAD de la página (con la matriz del paquete sintético), llevada otra vez al papel
    con la misma fórmula que componer (cad_to_page y la Y invertida), da la página."""
    pos, (ancho, alto) = (30.0, 40.0), (260.0, 120.0)
    pagina = [pos[0], pos[1], pos[0] + ancho, pos[1] + alto]
    caja = js("return O.cajaCadDetalle(entrada.pagina, entrada.m);",
              {"pagina": pagina, "m": MATRIZ_SINTETICA})
    a, b, c, d, e, f = MATRIZ_SINTETICA

    def a_papel(x, y):
        xp, yp = a * x + c * y + e, b * x + d * y + f  # mm de página, Y abajo
        return pos[0] + xp, pos[1] + (alto - yp)

    esquinas = [a_papel(caja[0], caja[1]), a_papel(caja[2], caja[3])]
    xs, ys = sorted(p[0] for p in esquinas), sorted(p[1] for p in esquinas)
    assert cerca([xs[0], ys[0], xs[1], ys[1]], pagina)
    # Moverlo en la hoja no cambia la caja CAD (la ortofoto se mueve con el detalle).
    movida = js("return O.cajaCadDetalle(entrada.pagina, entrada.m);",
                {"pagina": [100, 200, 360, 320], "m": MATRIZ_SINTETICA})
    assert cerca(movida, caja)


def test_caja_cad_girada_o_rara_no_se_dibuja():
    r = js("""return [O.cajaCadDetalle([0, 0, 10, 10], [0, 20, -20, 0, 0, 0]),
                     O.cajaCadDetalle([0, 0, 10, 10], [0, 0, 0, 0, 0, 0]),
                     O.cajaCadDetalle([0, 0, 10, 10], null),
                     O.cajaCadBloque([0, 0, 10, 10], [5, 5], [0, 0], 0)];""")
    assert r == [None, None, None, None]


def test_caja_cad_de_un_bloque_es_la_inversa_de_cad_a_papel():
    r = js("""
      const centro = [300, 200], centroCad = [4705600, 2201000], k = B.mmPorUnidadCad(1000, 2000);
      const pagina = B.rectCentrado(centro, B.paginaMm([957.18, 1350.019], 2000, 5));
      const caja = O.cajaCadBloque(pagina, centro, centroCad, k);
      const ida = [B.cadAPapel([caja[0], caja[1]], centroCad, centro, k),
                   B.cadAPapel([caja[2], caja[3]], centroCad, centro, k)];
      return {pagina, caja, ida};""")
    assert cerca(r["ida"][0] + r["ida"][1], r["pagina"], 1e-6)
    ancho_m = r["caja"][2] - r["caja"][0]
    assert ancho_m == pytest.approx(957.18 + 2 * 5 * 2000 / 1000)  # página a 1:2000 en m


def test_ficha_y_avisos_con_la_cabecera_de_python(tmp_path):
    ficha = leer_cabecera(crear_geotiff(tmp_path / "a.tif", ancho=1024, alto=768, pixel=0.25,
                                        mosaicos=True, compresion="lzw", piramides=(2, 4)))
    sin = leer_cabecera(crear_geotiff(tmp_path / "s.tif", crs=None, nodata=0))
    r = js("""return {
      lineas: O.lineasFicha(entrada.ficha), sin: O.lineasFicha(entrada.sin),
      nada: O.avisos(entrada.ficha, {crs: null, crs_dibujo: null}, false),
      listo: O.avisos(entrada.ficha, {crs: null, crs_dibujo: "EPSG:9377"}, false),
      reproy: O.avisos(entrada.ficha, {crs: null, crs_dibujo: "EPSG:3116"}, false),
      cambio: O.avisos(entrada.ficha, {crs: null, crs_dibujo: "EPSG:9377"}, true),
      sinElegir: O.avisos(entrada.sin, {crs: null, crs_dibujo: "EPSG:9377"}, false),
      elegido: O.avisos(entrada.sin, {crs: "EPSG:9377", crs_dibujo: "EPSG:9377"}, false),
      listas: [O.listaParaPrevias(entrada.ficha, {crs: null, crs_dibujo: "EPSG:9377"}, false),
               O.listaParaPrevias(entrada.ficha, {crs: null, crs_dibujo: null}, false),
               O.listaParaPrevias(entrada.sin, {crs: null, crs_dibujo: "EPSG:9377"}, false),
               O.listaParaPrevias(entrada.sin, {crs: "EPSG:9377", crs_dibujo: "EPSG:9377"}, false),
               O.listaParaPrevias(entrada.ficha, {crs: null, crs_dibujo: "EPSG:9377"}, true)]};""",
           {"ficha": ficha, "sin": sin})
    assert r["lineas"][1] == "1\u202f024 × 768 px · RGB · uint8 (3 bandas)"
    assert r["lineas"][2] == "Sistema: EPSG:9377 · MAGNA-SIRGAS 2018 / Origen-Nacional"
    assert r["lineas"][3] == "Píxel: 0,250 m"
    assert r["lineas"][4] == "Cubre: 256 × 192 m"
    assert r["lineas"][5] == "Pirámides: 2, 4 · mosaicos 256 × 256 · compresión lzw"
    assert r["lineas"][6] == "Fondo transparente: no"
    assert r["sin"][2] == "Sistema: el archivo no lo dice"
    assert r["sin"][6] == "Fondo transparente: valor nodata 0"
    assert [a["nivel"] for a in r["nada"]] == ["elegir"] and "del dibujo" in r["nada"][0]["texto"]
    assert r["listo"] == []
    assert r["reproy"] == [{"nivel": "info", "texto": "La ortofoto está en EPSG:9377 y el dibujo "
                                                      "en EPSG:3116: se reproyecta."}]
    assert r["cambio"][0]["nivel"] == "error"
    assert [a["nivel"] for a in r["sinElegir"]] == ["elegir"]  # el de la ortofoto
    assert r["elegido"] == []  # ya elegido: el aviso amarillo se va
    assert r["listas"] == [True, False, False, True, False]


def test_diferencias_con_la_del_plano():
    """«Cargar ortofoto» avisa si lo elegido no coincide (nombre, tamaño, fecha) con el plano."""
    r = js("""
      const e = {archivo_plano: "../fotos/Foto.tif", ficha: {bytes: 3445480, modificado: "2026-11-18T21:26:25Z"}};
      return [
        O.diferencias({archivo: "C:/x/foto.TIF", bytes: 3445480, modificado: "2026-11-18T21:26:25Z"}, e),
        O.diferencias({archivo: "otra.tif", bytes: 1000, modificado: "2026-01-02T03:04:05Z"}, e),
        O.diferencias({archivo: "Foto.tif", bytes: null, modificado: null}, e),
        O.esLaDelPlano({archivo: "Foto.tif", bytes: 3445480, modificado: "2026-11-18T21:26:26Z"}, e)];""")
    assert r[0] == [] and r[2] == []
    assert r[1] == ["nombre: el plano usa «otra.tif» y la elegida es «Foto.tif»",
                    "tamaño: el plano dice 1 000 bytes y la elegida tiene 3 445 480",
                    ("fecha: el plano dice 2026-01-02 03:04:05 UTC y la elegida es del "
                     "2026-11-18 21:26:25 UTC")]
    assert r[3] is False  # un segundo de diferencia en la fecha: no es la misma


def test_aviso_del_sistema_que_dio_el_dxf(tmp_path):
    ficha = leer_cabecera(crear_geotiff(tmp_path / "a.tif"))
    r = js("""const dxf = {codigo: "EPSG:9377", nombre: null, oficial: "x", aviso: null};
      const mal = {codigo: "EPSG:3115", nombre: "CTM12", oficial: "y", aviso: "no coinciden", sugerido: "EPSG:9377"};
      const autoridad = Object.assign({}, mal, {prellenar: false});
      return [O.avisos(entrada.ficha, {crs: null, crs_dibujo: null}, false, autoridad),
              O.avisos(entrada.ficha, {crs: null, crs_dibujo: "EPSG:9377"}, false, autoridad),
              O.avisos(entrada.ficha, {crs: null, crs_dibujo: "EPSG:3115"}, false, mal),
      O.avisos(entrada.ficha, {crs: null, crs_dibujo: "EPSG:9377"}, false, dxf),
      O.avisos(entrada.ficha, {crs: null, crs_dibujo: "EPSG:3116"}, false, dxf),
      O.avisos(entrada.ficha, {crs: null, crs_dibujo: "EPSG:9377"}, false, null)];""",
           {"ficha": ficha})
    # De la autoridad (PRGD): sin preseleccionar, se pide elegir y se mantiene el aviso amarillo.
    assert [a["nivel"] for a in r[0]] == ["elegir", "aviso"] and r[0][1]["texto"] == "no coinciden"
    # Elegido 9377 a mano: solo el aviso del DXF (no «el DXF dice 3115 pero el plano usa…»).
    assert r[1] == [{"nivel": "aviso", "texto": "no coinciden"}]
    r = r[2:]
    assert r[0] == [{"nivel": "aviso", "texto": "no coinciden"},
                    {"nivel": "info", "texto": "Sistema del dibujo tomado del DXF (EPSG:3115): se "
                                               "puede cambiar."},
                    {"nivel": "info", "texto": "La ortofoto está en EPSG:9377 y el dibujo en "
                                               "EPSG:3115: se reproyecta."}]
    r = r[1:]
    assert r[0] == [{"nivel": "info", "texto": "Sistema del dibujo tomado del DXF (EPSG:9377): se "
                                               "puede cambiar."}]
    assert r[1][0] == {"nivel": "aviso", "texto": "El DXF dice EPSG:9377, pero el plano usa "
                                                  "EPSG:3116 para el dibujo: revise cuál es el "
                                                  "correcto."}
    assert r[2] == []


def test_textos_de_cobertura_bytes_y_la_del_plano():
    r = js("""return {
      c: [0, 0.004, 0.4, 0.9996, 1].map(O.textoCobertura),
      b: [2048, 3445480, 5 * 1024 ** 3].map(O.textoBytes),
      p: [O.esLaDelPlano({archivo: "../data/Foto.TIF", bytes: 10}, {archivo_plano: "C:/x/foto.tif", ficha: {bytes: 10}}),
          O.esLaDelPlano({archivo: "a.tif", bytes: null}, {archivo_plano: "b/a.tif", ficha: {bytes: 9}}),
          O.esLaDelPlano({archivo: "a.tif", bytes: 10}, {archivo_plano: "a.tif", ficha: {bytes: 9}}),
          O.esLaDelPlano({archivo: "a.tif"}, {archivo_plano: "otra.tif", ficha: {bytes: 9}}),
          O.esLaDelPlano(null, {archivo_plano: "a.tif", ficha: {bytes: 9}})]};""")
    assert r["c"] == ["la ortofoto no cubre este detalle", "la ortofoto cubre el 1 % del detalle",
                      "la ortofoto cubre el 40 % del detalle", "la ortofoto cubre todo el detalle",
                      "la ortofoto cubre todo el detalle"]
    assert r["b"] == ["2 kB", "3,3 MB", "5,00 GB"]
    assert r["p"] == [True, True, False, False, False]


SECCIONES = [
    {"archivo": "a.tif"},
    {"archivo": "../x/Foto.TIFF", "bytes": 10, "modificado": "2026-11-18T21:26:25Z",
     "crs": "EPSG:9377", "crs_dibujo": "EPSG:3116", "opacidad": 0.5},
    {"archivo": "a.tif", "modificado": "ayer"},
    {"archivo": "a.tif", "modificado": None},
    {"archivo": "a.tif", "crs": None, "crs_dibujo": None, "opacidad": 0},
    {"archivo": ""},
    {"archivo": "a.png"},
    {"archivo": "a.tif", "bytes": -3},
    {"archivo": "a.tif", "bytes": 1.5},
    {"archivo": "a.tif", "crs": "9377"},
    {"archivo": "a.tif", "crs_dibujo": 9377},
    {"archivo": "a.tif", "opacidad": 2},
    {"archivo": "a.tif", "opacidad": True},
    {"archivo": "a.tif", "otra": 1},
    "a.tif",
]


def test_la_seccion_ortofoto_se_valida_igual_que_en_python(tmp_path):
    r = js("""return entrada.secciones.map((s) => {
      const errores = []; const o = O.leerOrtofoto(s, errores); return {o, n: errores.length};});""",
           {"secciones": SECCIONES})
    for seccion, res in zip(SECCIONES, r, strict=True):
        errores = []
        o = leer_ortofoto(seccion, tmp_path, errores) if isinstance(seccion, dict) else None
        if not isinstance(seccion, dict):
            errores = ["no es objeto"]
        assert (res["o"] is None) == (o is None), seccion
        assert (res["n"] == 0) == (not errores), seccion
        if o is not None:
            assert (res["o"]["crs"], res["o"]["crs_dibujo"], res["o"]["opacidad"],
                    res["o"]["modificado"]) == (o.crs, o.crs_dibujo, o.opacidad, o.modificado)


@pytest.fixture
def entorno_editor(tmp_path):
    escribir_formato(tmp_path / "formato.json")
    crear_paquete_real(tmp_path / "input", "a")
    (tmp_path / "editor").mkdir()
    datos, _ = construir_datos_editor(tmp_path / "input", tmp_path / "formato.json",
                                      tmp_path / "editor")
    return tmp_path, datos


def test_el_catalogo_trae_la_matriz_para_la_ortofoto(entorno_editor):
    _, datos = entorno_editor
    (d,) = datos["detalles"]
    assert d["cad_a_pagina"] == pytest.approx(list(MATRIZ_SINTETICA))
    assert d["mm_por_unidad"] > 0


def test_el_editor_escribe_la_version_4_y_python_la_lee(entorno_editor):
    carpeta, datos = entorno_editor
    orto = {"archivo": "../data/ortofotos/Foto_tunez.tif", "bytes": 3445480,
            "modificado": "2026-11-18T21:26:25Z", "crs": None, "crs_dibujo": "EPSG:9377",
            "opacidad": 0.654}
    texto = js("""
      const d = entrada.datos.detalles[0];
      return L.serializarPlano([{id: "a", detalle: d, pos: [30, 40]}], entrada.datos,
                               {ortofoto: entrada.orto});""", {"datos": datos, "orto": orto})
    plano = json.loads(texto)
    assert plano["version"] == 4
    assert list(plano) == ["version", "formato", "plantilla", "detalles", "ortofoto"]
    assert plano["ortofoto"] == {**orto, "opacidad": 0.65}
    ruta = carpeta / "editor" / "plano.json"
    ruta.write_text(texto, encoding="utf-8")
    leido = leer_plano(ruta)
    assert leido.ortofoto.archivo == (carpeta / "data" / "ortofotos" / "Foto_tunez.tif").resolve()
    assert (leido.ortofoto.crs_dibujo, leido.ortofoto.opacidad) == ("EPSG:9377", 0.65)


def test_abrir_y_guardar_un_plano_v4_sin_tocar_nada_es_identico(entorno_editor):
    _, datos = entorno_editor
    original = {"version": 4, "formato": "../formato.json", "plantilla": None,
                "ortofoto": {"archivo": "C:/fotos/a.tif", "crs_dibujo": "EPSG:9377"},
                "detalles": [{"id": "a", "manifiesto": "../input/a.manifest.json",
                              "posicion_mm": [30, 40]}]}
    texto = json.dumps(original, indent=2) + "\n"
    r = js("""
      const leido = L.leerPlano(entrada.texto, entrada.datos);
      const igual = L.serializarPlano(leido.colocaciones, entrada.datos,
                                      {original: leido.original, ortofoto: leido.ortofoto});
      const otra = JSON.parse(L.serializarPlano(leido.colocaciones, entrada.datos,
          {original: leido.original, ortofoto: Object.assign({}, leido.ortofoto, {opacidad: 0.5})}));
      const quitada = JSON.parse(L.serializarPlano(leido.colocaciones, entrada.datos,
          {original: leido.original, ortofoto: null}));
      return {errores: leido.errores, ortofoto: leido.ortofoto, igual, otra, quitada};""",
           {"texto": texto, "datos": datos})
    assert r["errores"] == []
    assert r["ortofoto"] == {"archivo": "C:/fotos/a.tif", "bytes": None, "modificado": None,
                             "crs": None, "crs_dibujo": "EPSG:9377", "opacidad": 1}
    assert r["igual"] == texto  # tal como vino (sin agregar claves)
    assert r["otra"]["ortofoto"] == {"archivo": "C:/fotos/a.tif", "bytes": None,
                                     "modificado": None, "crs": None,
                                     "crs_dibujo": "EPSG:9377", "opacidad": 0.5}
    assert "ortofoto" not in r["quitada"] and r["quitada"]["version"] == 4  # no se baja


def test_el_editor_rechaza_la_ortofoto_mal_escrita(entorno_editor):
    _, datos = entorno_editor
    detalle = {"id": "a", "manifiesto": "../input/a.manifest.json", "posicion_mm": [30, 40]}
    planos = {"v3": {"version": 3, "ortofoto": {"archivo": "a.tif"}, "detalles": [detalle]},
              "mala": {"version": 4, "ortofoto": {"archivo": "a.tif", "opacidad": 3},
                       "detalles": [detalle]},
              "v5": {"version": 5, "detalles": [detalle]}}
    r = js("""const res = {};
      for (const [k, p] of Object.entries(entrada.planos)) res[k] = L.leerPlano(JSON.stringify(p), entrada.datos).errores;
      return res;""", {"planos": planos, "datos": datos})
    assert r["v3"] == ['ortofoto: solo existe en la versión 4 del plano (use "version": 4).']
    assert r["mala"] == ["ortofoto.opacidad: se esperaba un número de 0 a 1."]
    assert "versiones 1, 2, 3 y 4" in r["v5"][0]
