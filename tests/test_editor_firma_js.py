"""Firma en imagen procesada en el editor (editor_firma.js, subfase 4.3b2), con Node.

Imagen SINTÉTICA: un garabato negro sobre fondo blanco con ruido (y una línea gris en el borde,
como la de un escáner). Se prueba: umbral suave, recorte al trazo con 2 px de margen,
reducción proporcional a 600 x 200 px, PNG con canal alfa, límite de 100 KB; y la PARIDAD con
Python: el PNG que genera JavaScript pasa `firmas.revisar_png` y `componer` lo acepta, y
`revisarPng` da los mismos textos que `firmas.revisar_png` / `firmas.aviso_sin_alfa`."""

import base64
import json
import shutil
import subprocess
from pathlib import Path

import pymupdf
import pytest

import componedor
from componedor.componer import componer_plano
from componedor.firmas import _partes_del_id, aviso_sin_alfa, revisar_png
from test_firmas import _plano, entorno  # noqa: F401  (fixture: formato con carpeta de firmas)

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node no está instalado")
FIRMA_JS = Path(componedor.__file__).parent / "editor" / "editor_firma.js"

# Garabato sintético: PRNG con semilla, fondo blanco con ruido de ±12, trazos negros de 6 px
# siguiendo curvas de Bézier dentro de la caja [x0, x1] x [y0, y1], y una línea gris de 3 px en
# el borde izquierdo (lo que el recorte manual deja afuera).
GARABATO = """
  function azar(semilla) { return () => { semilla = (semilla + 0x6D2B79F5) | 0; let t = semilla;
    t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
  function garabato(ancho, alto, caja, opciones) {
    opciones = opciones || {};
    const r = azar(opciones.semilla || 7);
    const img = E.imagen(ancho, alto);
    const d = img.datos;
    for (let i = 0; i < d.length; i += 4) {
      const v = 255 - Math.round(r() * 24);  // papel 231-255
      d[i] = d[i + 1] = d[i + 2] = v; d[i + 3] = 255;
    }
    const pinta = opciones.color || (() => [0, 0, 0]);
    let minx = 1e9, miny = 1e9, maxx = -1, maxy = -1;
    const punto = (x, y) => {
      for (let dy = -3; dy < 3; dy++) for (let dx = -3; dx < 3; dx++) {
        const px = Math.round(x) + dx, py = Math.round(y) + dy;
        if (px < 0 || py < 0 || px >= ancho || py >= alto) continue;
        const [cr, cg, cb] = pinta(r);
        const i = (py * ancho + px) * 4; d[i] = cr; d[i + 1] = cg; d[i + 2] = cb;
        minx = Math.min(minx, px); maxx = Math.max(maxx, px); miny = Math.min(miny, py); maxy = Math.max(maxy, py);
      }
    };
    const [x0, y0, x1, y1] = caja;
    for (let k = 0; k < (opciones.curvas || 4); k++) {
      const p = Array.from({length: 4}, () => [x0 + r() * (x1 - x0), y0 + r() * (y1 - y0)]);
      for (let t = 0; t <= 1; t += 0.0005) {
        const u = 1 - t;
        punto(u*u*u*p[0][0] + 3*u*u*t*p[1][0] + 3*u*t*t*p[2][0] + t*t*t*p[3][0],
              u*u*u*p[0][1] + 3*u*u*t*p[1][1] + 3*u*t*t*p[2][1] + t*t*t*p[3][1]);
      }
    }
    if (opciones.borde) for (let y = 0; y < alto; y++) for (let x = 0; x < 3; x++) {
      const i = (y * ancho + x) * 4; d[i] = d[i + 1] = d[i + 2] = 120;
    }
    return {img, caja: [minx, miny, maxx, maxy]};
  }
  const deflate = (b) => require("zlib").deflateSync(Buffer.from(b), {level: 9});
  const b64 = (u) => Buffer.from(u).toString("base64");
"""


def js(codigo: str, entrada=None):
    script = (f"const E = require({json.dumps(str(FIRMA_JS))});"
              "const entrada = JSON.parse(require('fs').readFileSync(0, 'utf8'));" + GARABATO +
              f"(async function () {{ {codigo} }})().then((s) => "
              "process.stdout.write(JSON.stringify(s === undefined ? null : s)));")
    r = subprocess.run([NODE, "-e", script], input=json.dumps(entrada), capture_output=True,
                       text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


# --- procesamiento ----------------------------------------------------------------------------

def test_umbral_suave_por_luminosidad():
    r = js("return [255, 240, 221, 200, 180, 179, 20].map((y) => E.alfaPorLuminosidad(y, 200));")
    assert r[:3] == [0, 0, 0]  # papel y ruido claro: transparente
    assert r[3] == pytest.approx(0.5)  # en el umbral, a mitad
    assert r[4] == pytest.approx(1.0) and r[5:] == [1, 1]  # tinta: opaca
    assert js("return E.luminosidad(255, 255, 255);") == pytest.approx(255)


def test_garabato_umbral_recorte_al_trazo_reduccion_y_alfa():
    r = js("""
        const g = garabato(1500, 500, [300, 100, 1200, 400], {borde: true});
        // Recorte manual que deja afuera la línea gris del borde.
        const recortada = E.recortar(g.img, {x: 10, y: 0, ancho: 1490, alto: 500});
        const limpia = E.limpiar(recortada, 200, "negro");
        let fondoOpaco = 0;
        for (let i = 3; i < limpia.datos.length; i += 4) if (limpia.datos[i] > 0 && limpia.datos[i - 1] !== 0) fondoOpaco++;
        const caja = E.cajaDelTrazo(limpia, 2);
        const sinRecorte = E.cajaDelTrazo(E.limpiar(g.img, 200, "negro"), 2);
        const res = await E.generar(g.img, {recorte: {x: 10, y: 0, ancho: 1490, alto: 500}, umbral: 200, tinta: "negro"}, deflate);
        return {trazo: g.caja, caja, sinRecorte, fondoOpaco, ancho: res.ancho, alto: res.alto,
                reducciones: res.reducciones, revision: res.revision, png: b64(res.png)};
    """)
    minx, miny, maxx, maxy = r["trazo"]
    # Recorte al trazo: la caja del garabato (en coordenadas del recorte, x - 10) con 2 px.
    assert r["caja"] == {"x": minx - 10 - 2, "y": miny - 2, "ancho": maxx - minx + 5, "alto": maxy - miny + 5}
    assert r["sinRecorte"]["x"] == 0  # sin recorte manual, la línea gris del borde entraba
    assert r["fondoOpaco"] == 0  # el papel con ruido quedó todo transparente
    ancho, alto = r["caja"]["ancho"], r["caja"]["alto"]
    f = min(1, 600 / ancho, 200 / alto)
    assert (r["ancho"], r["alto"]) == (round(ancho * f), round(alto * f))  # proporcional
    assert r["ancho"] <= 600 and r["alto"] <= 200 and max(r["ancho"] / 600, r["alto"] / 200) > 0.99
    assert r["reducciones"] == 0 and r["revision"]["problemas"] == [] and r["revision"]["alfa"]
    png = base64.b64decode(r["png"])
    pix = pymupdf.Pixmap(png)
    assert pix.alpha == 1 and (pix.width, pix.height) == (r["ancho"], r["alto"])
    alfas = pix.samples[3::4]
    assert alfas[0] == 0 and max(alfas) == 255  # esquina transparente, trazo opaco
    assert revisar_png(png, "firma.png", "firma")[0] == []  # pasa firmas.py


def test_tinta_original_conserva_el_color():
    r = js("""
        const g = garabato(400, 150, [40, 20, 360, 130], {color: () => [20, 40, 160]});
        const l = E.recorteAlTrazo(E.limpiar(g.img, 200, "original"), 2);
        const negro = E.recorteAlTrazo(E.limpiar(g.img, 200, "negro"), 2);
        const opaco = (img) => { for (let i = 0; i < img.datos.length; i += 4)
          if (img.datos[i + 3] === 255) return Array.from(img.datos.slice(i, i + 3)); };
        return {original: opaco(l), negro: opaco(negro)};
    """)
    assert r["original"] == [20, 40, 160] and r["negro"] == [0, 0, 0]


def test_sin_trazo_da_error_claro():
    r = js("""const img = E.imagen(50, 50); img.datos.fill(255);
              return await E.generar(img, {umbral: 200, tinta: "negro"}, deflate);""")
    assert r == {"error": "No quedó ningún trazo: suba el umbral o revise el recorte."}


def test_limite_de_peso_reduce_hasta_100_kb():
    """Peor caso: «tinta» de colores al azar en toda la imagen (casi no se comprime)."""
    r = js("""
        const g = garabato(1200, 400, [0, 0, 1200, 400], {curvas: 60,
          color: (r) => [Math.floor(r() * 120), Math.floor(r() * 120), Math.floor(r() * 120)]});
        const primero = await E.codificarPng(E.reducir(E.recorteAlTrazo(E.limpiar(g.img, 200, "original"), 2), 600, 200), deflate);
        const res = await E.generar(g.img, {umbral: 200, tinta: "original"}, deflate);
        return {primero: primero.length, reducciones: res.reducciones, ancho: res.ancho, alto: res.alto,
                revision: res.revision, png: b64(res.png)};
    """)
    assert r["primero"] > 100 * 1024  # sin achicar, se pasaba
    assert r["reducciones"] >= 1
    png = base64.b64decode(r["png"])
    assert len(png) <= 100 * 1024 and r["revision"]["problemas"] == []
    assert revisar_png(png, "firma.png", "firma")[0] == []


# --- paridad con firmas.py --------------------------------------------------------------------

def _png_python_sin_alfa(ancho=120, alto=40) -> bytes:
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, ancho, alto), False)
    pix.set_rect(pix.irect, (250, 250, 250))
    return pix.tobytes("png")


def test_revisar_png_mismos_textos_que_python():
    r = js("""
        const ruido = (w, h) => { const img = E.imagen(w, h); const az = azar(3);
          for (let i = 0; i < img.datos.length; i++) img.datos[i] = Math.floor(az() * 256); return img; };
        const ancha = E.imagen(700, 150); ancha.datos.fill(255);
        return {ancha: b64(await E.codificarPng(ancha, deflate)),
                pesada: b64(await E.codificarPng(ruido(600, 200), deflate)),
                las_dos: b64(await E.codificarPng(ruido(650, 210), deflate))};
    """)
    casos = {nombre: base64.b64decode(v) for nombre, v in r.items()}
    casos["no_png"] = b"GIF89a\x01\x00\x01\x00"
    casos["sin_alfa"] = _png_python_sin_alfa()
    archivo, donde = "firmas/Persona Uno/firma.png", "firma"
    entrada = {k: base64.b64encode(v).decode("ascii") for k, v in casos.items()}
    js_rev = js("""const res = {};
                   for (const [k, v] of Object.entries(entrada.casos))
                     res[k] = E.revisarPng(new Uint8Array(Buffer.from(v, "base64")), entrada.archivo, entrada.donde);
                   return res;""", {"casos": entrada, "archivo": archivo, "donde": donde})
    for nombre, datos in casos.items():
        problemas, pix = revisar_png(datos, archivo, donde)
        assert js_rev[nombre]["problemas"] == problemas, nombre
        if pix is not None:
            assert js_rev[nombre]["alfa"] == bool(pix.alpha), nombre
    assert len(js_rev["las_dos"]["problemas"]) == 2  # pesa más de 100 KB y mide más de 600 x 200
    assert js_rev["sin_alfa"]["problemas"] == [] and js_rev["sin_alfa"]["alfa"] is False
    assert js("return E.avisoSinAlfa('Persona Uno', 'firma.png', 'firmas.dibujo.firma');") == \
        aviso_sin_alfa("Persona Uno", "firma.png", "firmas.dibujo.firma")


@pytest.mark.parametrize("nombre", [
    "Luis Ángel Núñez", "María_José-2", "Ñandú", "A", " Luis", "Luis ", "../x", "a/b", "a.b",
    "C:\\x", "a\\b", "", "Luis  Núñez", "-x-",
])
def test_nombre_de_persona_como_firmas_py(nombre):
    problema = js("return E.problemaNombre(entrada);", nombre)
    assert (problema == "") == (_partes_del_id(nombre) is not None and "/" not in nombre), nombre


def test_componer_acepta_la_firma_generada_por_javascript(entorno):  # noqa: F811
    r = js("""
        const g = garabato(1500, 500, [300, 100, 1200, 400]);
        const res = await E.generar(g.img, {umbral: 200, tinta: "negro"}, deflate);
        return b64(res.png);
    """)
    destino = entorno / "firmas" / "Persona JS" / "firma.png"
    destino.parent.mkdir(parents=True)
    destino.write_bytes(base64.b64decode(r))
    plano = _plano(entorno, {"dibujo": {"nombre": "PERSONA JS", "firma": {"imagen": "Persona JS"}}})
    resultado = componer_plano(plano, entorno / "p.pdf")
    (firma,) = resultado.firmas
    assert firma.id == "Persona JS" and firma.alfa and firma.archivo == destino
    assert not any("canal alfa" in a for a in resultado.advertencias)
