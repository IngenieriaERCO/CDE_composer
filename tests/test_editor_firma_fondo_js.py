"""Firma: sombras e iluminación despareja (mejora de la subfase 4.3b2), con Node.

«Foto» SINTÉTICA: papel con degradado (luminosidad 245 a la izquierda y 135 a la derecha), una
sombra suave en la esquina inferior derecha (×0,6) y ruido; la tinta oscurece su papel ×0,12.
Se prueba: fondo local estimado, papel transparente con «Compensar sombras…» y fondo opaco
(con aviso) sin ella; umbral de Otsu igual a una implementación de referencia en Python; rango
y dirección del umbral (bajar = más transparente); el aviso de más del 25 % opaco."""

import json
import random

import pytest

from test_editor_firma_js import NODE, js

pytestmark = pytest.mark.skipif(NODE is None, reason="Node no está instalado")

FOTO = """
  function foto(ancho, alto, semilla) {
    const r = azar(semilla || 5);
    const img = E.imagen(ancho, alto);
    const tinta = new Uint8Array(ancho * alto);
    const papel = new Float32Array(ancho * alto);
    for (let y = 0; y < alto; y++) for (let x = 0; x < ancho; x++) {
      let v = 245 - 110 * (x / (ancho - 1));                                   // degradado
      const sx = Math.min(1, Math.max(0, (x - ancho * 0.55) / 80));           // sombra suave
      const sy = Math.min(1, Math.max(0, (y - alto * 0.55) / 60));
      v *= 1 - 0.4 * sx * sy;
      papel[y * ancho + x] = v;
    }
    const marca = (cx, cy) => { for (let dy = -3; dy < 3; dy++) for (let dx = -3; dx < 3; dx++) {
      const x = Math.round(cx) + dx, y = Math.round(cy) + dy;
      if (x >= 0 && y >= 0 && x < ancho && y < alto) tinta[y * ancho + x] = 1; } };
    for (let k = 0; k < 4; k++) {
      const p = Array.from({length: 4}, () => [ancho * (0.1 + 0.8 * r()), alto * (0.15 + 0.7 * r())]);
      for (let t = 0; t <= 1; t += 0.0007) { const u = 1 - t;
        marca(u*u*u*p[0][0] + 3*u*u*t*p[1][0] + 3*u*t*t*p[2][0] + t*t*t*p[3][0],
              u*u*u*p[0][1] + 3*u*u*t*p[1][1] + 3*u*t*t*p[2][1] + t*t*t*p[3][1]); }
    }
    for (let k = 0, i = 0; k < papel.length; k++, i += 4) {
      const v = Math.max(0, Math.min(255, papel[k] * (tinta[k] ? 0.12 : 1) + (r() - 0.5) * 16));
      img.datos[i] = img.datos[i + 1] = img.datos[i + 2] = v; img.datos[i + 3] = 255;
    }
    return {img, tinta, papel};
  }
  // Píxeles opacos (alfa >= 128) que NO son tinta (ni su borde de 1 px) y tinta conservada.
  function cuenta(limpia, tinta, ancho, alto) {
    let fondo = 0, nFondo = 0, conservada = 0, nTinta = 0;
    for (let y = 0; y < alto; y++) for (let x = 0; x < ancho; x++) {
      const k = y * ancho + x; let cerca = false;
      for (let dy = -1; dy <= 1 && !cerca; dy++) for (let dx = -1; dx <= 1; dx++) {
        const xx = x + dx, yy = y + dy;
        if (xx >= 0 && yy >= 0 && xx < ancho && yy < alto && tinta[yy * ancho + xx]) { cerca = true; break; } }
      const opaco = limpia.datos[k * 4 + 3] >= 128;
      if (tinta[k]) { nTinta++; if (opaco) conservada++; }
      else if (!cerca) { nFondo++; if (opaco) fondo++; }
    }
    return {fondo: fondo / nFondo, tinta: conservada / nTinta};
  }
"""


def jsf(codigo, entrada=None):
    return js(FOTO + codigo, entrada)


def test_fondo_local_sigue_al_degradado_y_a_la_sombra():
    r = jsf("""
        const f = foto(800, 300);
        const fondo = E.estimarFondo(f.img);
        const err = [], papel = [];
        for (let k = 0; k < fondo.length; k++) if (!f.tinta[k]) {
          err.push(Math.abs(fondo[k] - f.papel[k])); papel.push(f.papel[k] / fondo[k] * 255); }
        err.sort((a, b) => a - b);
        return {p50: err[err.length >> 1], p99: err[Math.floor(err.length * 0.99)], papelMin: papel.reduce((a, b) => Math.min(a, b), Infinity),
                umbral: E.umbralAutomatico(f.img), bloque: E.bloqueFondo(f.img)};
    """)
    assert r["bloque"] == 20  # 800 / 40
    # Sigue al papel: la mitad de los píxeles con un error del orden del ruido (±8); el 99 %
    # bajo 25 niveles (el máximo por bloque toma el lado claro de la rampa de la sombra).
    assert r["p50"] < 12 and r["p99"] < 25
    # Lo que importa: el papel compensado más oscuro queda transparente con el umbral automático.
    assert r["papelMin"] > r["umbral"] + 20
    assert 90 < r["umbral"] < 160  # centro del hueco entre tinta (~31) y papel (~196)


def test_compensar_deja_el_papel_transparente_y_sin_compensar_no():
    r = jsf("""
        const f = foto(800, 300);
        const conU = E.umbralAutomatico(f.img, {compensar: true});
        const sinU = E.umbralAutomatico(f.img, {compensar: false});
        const con = cuenta(E.limpiar(E.compensarFondo(f.img), conU, "negro"), f.tinta, 800, 300);
        const sin = cuenta(E.limpiar(f.img, sinU, "negro"), f.tinta, 800, 300);
        const zlib = require("zlib");
        const deflate = (b) => zlib.deflateSync(Buffer.from(b));
        const gCon = await E.generar(f.img, {umbral: conU, tinta: "negro", compensar: true}, deflate);
        const gSin = await E.generar(f.img, {umbral: sinU, tinta: "negro", compensar: false}, deflate);
        return {conU, sinU, con, sin, avisoCon: gCon.avisoFondo, avisoSin: gSin.avisoFondo,
                opacosCon: gCon.opacos, opacosSin: gSin.opacos, problemas: gCon.revision.problemas};
    """)
    assert r["con"]["fondo"] < 0.001  # papel con degradado y sombra: transparente
    assert r["con"]["tinta"] > 0.97  # y el trazo se conserva
    assert r["sin"]["fondo"] > 0.05  # sin compensar, la parte oscura del papel queda opaca
    assert r["avisoCon"] == "" and r["opacosCon"] < 0.25 and r["problemas"] == []
    assert r["opacosSin"] > 0.25 and r["avisoSin"].startswith("Parece que queda fondo: el ")


def _otsu(valores: list[int]) -> int:
    """Otsu de referencia (Python): el umbral t que maximiza la varianza entre clases ≤t / >t;
    si varios t empatan (un hueco sin píxeles), el centro del empate."""
    hist = [0] * 256
    for v in valores:
        hist[v] += 1
    total = len(valores)
    suma = sum(t * h for t, h in enumerate(hist))
    peso0 = suma0 = 0
    mejor = ultimo = 0
    varianza = -1.0
    for t in range(256):
        peso0 += hist[t]
        if not peso0:
            continue
        peso1 = total - peso0
        if not peso1:
            break
        suma0 += t * hist[t]
        m0, m1 = suma0 / peso0, (suma - suma0) / peso1
        v = peso0 * peso1 * (m0 - m1) ** 2
        if v > varianza:
            varianza, mejor, ultimo = v, t, t
        elif v == varianza:
            ultimo = t
    return int((mejor + ultimo) / 2 + 0.5)  # como Math.round (las mitades hacia arriba)


@pytest.mark.parametrize("semilla", [1, 2, 3])
def test_otsu_como_la_referencia(semilla):
    azar = random.Random(semilla)
    # Dos poblaciones (tinta y papel) con mezcla al azar, en gris (luminosidad = valor).
    valores = [max(0, min(255, round(azar.gauss(azar.choice([45, 60]), 15)))) for _ in range(1500)] + \
              [max(0, min(255, round(azar.gauss(azar.choice([200, 235]), 12)))) for _ in range(6000)]
    r = js("""const img = E.imagen(entrada.length, 1);
              entrada.forEach((v, i) => { img.datos.set([v, v, v, 255], i * 4); });
              return E.umbralOtsu(img);""", valores)
    assert r == _otsu(valores)
    assert 60 < r < 200


def test_rango_del_umbral_y_su_direccion():
    r = jsf("""
        const f = foto(600, 220);
        const aplanada = E.compensarFondo(f.img);
        const transparentes = [250, 200, 150, 100, 70, 40].map((u) => {
          const l = E.limpiar(aplanada, u, "negro"); let n = 0;
          for (let i = 3; i < l.datos.length; i += 4) if (l.datos[i] === 0) n++; return n; });
        const blanca = E.imagen(50, 50); blanca.datos.fill(255);
        return {min: E.UMBRAL_MIN, max: E.UMBRAL_MAX, transparentes, blanca: E.umbralAutomatico(blanca)};
    """)
    assert (r["min"], r["max"]) == (40, 250)
    t = r["transparentes"]
    assert all(a <= b for a, b in zip(t, t[1:]))  # bajar el valor = más fondo transparente
    assert t[-1] > t[0]
    assert r["blanca"] == 40  # sin tinta, el automático se queda en el mínimo


def test_aviso_de_fondo_opaco():
    r = js("return [0.37, 0.25, 0.251, 0.1].map(E.avisoFondo);")
    assert r[0] == ("Parece que queda fondo: el 37 % de los píxeles de la firma quedó opaco (una firma "
                    "limpia rara vez pasa del 25 %). Revise el umbral o repita la foto con más luz.")
    assert r[1] == "" and r[3] == "" and r[2].startswith("Parece que queda fondo: el 25 %")
    assert js("""const img = E.imagen(10, 10);
                 for (let i = 0; i < 30; i++) img.datos[i * 4 + 3] = 255;
                 return E.fraccionOpaca(img);""") == pytest.approx(0.30)
    assert json.dumps(r, ensure_ascii=False).count("más luz") == 2
