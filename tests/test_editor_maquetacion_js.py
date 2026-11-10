"""Maquetación de textos en el editor (editor_maquetacion.js, subfase 4.3e), con Node.

PARIDAD con Python: sobre las celdas reales de A1 ERCO y con Arial, `M.maquetar` da las mismas
líneas, las mismas posiciones y anchos (±1e-9 mm), la misma altura final y la misma altura
pedida que `maquetacion.maquetar`, o el MISMO texto de «no cabe»; `M.maquetarNotas`, lo mismo
contra `notas.maquetar_notas`. Casos normales y límite: vacío, justo en el borde, justo en un
paso de reducción, palabra más larga que la celda, tildes, ñ, guiones, espacio duro, 3 líneas
de título, líneas escritas a mano, notas con viñetas; y textos al azar (semilla fija).
Textos sintéticos, sin datos de personas."""

import dataclasses
import json
import random
import shutil
import subprocess
from pathlib import Path

import pytest

import componedor
from componedor.datos_rotulo_editor import CARACTERES, definicion_editor, tabla_anchos
from componedor.formato import cargar_formato
from componedor.fuente import cargar_fuente
from componedor.maquetacion import TextoNoCabe, alturas_a_probar, maquetar, partir_en_lineas
from componedor.notas import Nota, maquetar_notas
from componedor.rotulo_formato import (
    CampoConvenciones,
    CampoNotas,
    CampoTabla,
    CampoTexto,
    Celda,
)
from conftest import ARIAL, escribir_formato, requiere_arial, rotulo_a1

NODE = shutil.which("node")
pytestmark = [pytest.mark.skipif(NODE is None, reason="Node no está instalado"), requiere_arial]
CARPETA_JS = Path(componedor.__file__).parent / "editor"
TOL = 1e-9
DURO = " "  # espacio duro: para Python (str.split) también separa palabras


def js(codigo: str, entrada=None):
    """Ejecuta `codigo` con M (maquetación); devuelve su resultado."""
    script = (
        f"const M = require({json.dumps(str(CARPETA_JS / 'editor_maquetacion.js'))});"
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
    carpeta = tmp_path_factory.mktemp("maquetacion")
    ruta = escribir_formato(carpeta / "formato.json", rotulo=rotulo_a1(fuente={"archivo": str(ARIAL)}))
    definicion = cargar_formato(ruta, usar_plantilla=False).rotulo
    fuente = cargar_fuente(ARIAL)
    celdas = {}
    for campo in definicion.campos.values():
        if isinstance(campo, CampoTexto):
            celdas[campo.celda.ruta] = campo.celda
        elif isinstance(campo, CampoTabla):
            celdas.update({c.ruta: c for c in campo.celdas.values()})
        elif isinstance(campo, CampoConvenciones):
            celdas.update({c.ruta: c for c in campo.descripciones[:2]})
    notas = next(c for c in definicion.campos.values() if isinstance(c, CampoNotas))
    return {"definicion": definicion, "fuente": fuente, "celdas": celdas, "notas": notas,
            "tabla": tabla_anchos(fuente), "definicion_json": definicion_editor(definicion)}


def celda_json(c: Celda) -> dict:
    return {"ruta": c.ruta, "rect_mm": list(c.rect), "alinear": c.alinear, "altura_mm": c.altura_mm,
            "altura_min_mm": c.altura_min_mm, "lineas_max": c.lineas_max}


def py_maquetar(entorno, celda: Celda, contenido) -> dict:
    d = entorno["definicion"]
    try:
        m = maquetar(celda, contenido, entorno["fuente"], d.relleno_mm, d.interlineado)
    except TextoNoCabe as e:
        return {"problema": str(e)}
    return {"ruta": m.ruta, "lineas": [{"texto": l.texto, "base_mm": list(l.base_mm), "ancho_mm": l.ancho_mm}
                                       for l in m.lineas],
            "altura_mm": m.altura_mm, "reducido_desde": m.reducido_desde, "celda_mm": list(m.celda_mm)}


MAQUETAR = """
    return entrada.casos.map(([celda, contenido]) =>
        M.maquetar(celda, contenido, entrada.fuente, entrada.relleno, entrada.interlineado));
"""


def js_maquetar(entorno, casos: list[tuple[Celda, object]]) -> list[dict]:
    d = entorno["definicion"]
    return js(MAQUETAR, {"casos": [[celda_json(c), t] for c, t in casos], "fuente": entorno["tabla"],
                         "relleno": d.relleno_mm, "interlineado": d.interlineado})


def iguales(a, b) -> bool:
    """Igualdad de resultados: textos exactos, números con ±1e-9."""
    if isinstance(a, float) or isinstance(b, float):
        return isinstance(a, (int, float)) and isinstance(b, (int, float)) and abs(a - b) <= TOL
    if isinstance(a, dict):
        return isinstance(b, dict) and a.keys() == b.keys() and all(iguales(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return isinstance(b, list) and len(a) == len(b) and all(iguales(x, y) for x, y in zip(a, b))
    return a == b


def comparar(entorno, casos) -> list[dict]:
    """Compara Python y JavaScript caso por caso; devuelve los resultados de Python."""
    python = [py_maquetar(entorno, c, t) for c, t in casos]
    for (celda, texto), p, j in zip(casos, python, js_maquetar(entorno, casos)):
        assert iguales(p, j), f"{celda.ruta} con {texto!r}:\n  Python {p}\n  JS     {j}"
    return python


def justo(entorno, celda: Celda, altura: float, letra: str = "M") -> str:
    """El texto de una sola palabra más ancho que todavía cabe en una línea a `altura`."""
    fuente = entorno["fuente"]
    util = celda.rect[2] - celda.rect[0] - 2 * entorno["definicion"].relleno_mm
    texto = ""
    for c in letra + "i.,":
        while fuente.ancho_mm(texto + c, altura) <= util:
            texto += c
    return texto


# --- números y espacios como en Python ---------------------------------------------------------

NUMEROS = [0.0, 0.05, 0.15, 0.25, 0.35, 0.45, 0.5, 0.75, 1.25, 1.75, 12.25, 12.35, 99.95, 2.675, 1.005,
           0.125, 0.375, 2.4000000000000004, 155.9, 154.70000000000002, -0.25, -0.75, -0.04, 1e-7]


def test_numeros_como_los_escribe_python():
    r = js("return entrada.map((v) => [M.fmt(v), M.fmt(v, 2), M.redondear(v, 2)]);", NUMEROS)
    assert r == [[f"{v:.1f}", f"{v:.2f}", round(v, 2)] for v in NUMEROS]
    assert js("return [M.fmt(0.25), (0.25).toFixed(1)];") == ["0.2", "0.3"]  # por eso no se usa toFixed
    enteros = [0.5, 1.5, 2.5, 4.999999999999999, 5.000000000000001, 3.0, 2.4, 2.6]
    assert js("return entrada.map(M.redondearEntero);", enteros) == [int(round(v)) for v in enteros]


def test_espacios_como_los_de_python():
    textos = ["  A  B\tC" + DURO + "D E　F  ", "\x1cA\x85B\x1f", "﻿A B﻿", "", "   ",
              "A​B C"]
    r = js("return entrada.map((t) => [M.palabras(t), M.recortar(t)]);", textos)
    assert r == [[t.split(), t.strip()] for t in textos]


def test_alturas_a_probar(entorno):
    pares = [(2.5, 2.0), (1.8, 1.5), (2.0, 2.0), (2.5, 2.45), (3.0, 1.0), (2.05, 1.5), (1.8, 1.55), (2.5, 2.44)]
    celdas = [dataclasses.replace(entorno["celdas"]["titulo"], altura_mm=a, altura_min_mm=m) for a, m in pares]
    r = js("return entrada.map((c) => M.alturasAProbar(c));", [celda_json(c) for c in celdas])
    assert r == [alturas_a_probar(c) for c in celdas]
    assert r[0] == [2.5, 2.4, 2.3, 2.2, 2.1, 2.0]


def test_mide_igual_que_la_fuente(entorno):
    azar = random.Random(7)
    textos = ["".join(azar.choice(CARACTERES) for _ in range(azar.randint(1, 80))) for _ in range(300)]
    textos += ["ÁÉÍÓÚÜÑ áéíóúüñ", "VÍA – TRAMO “1” … € • 100 ‰", "", "Ø 3/4\" @ 0,20 m ± 5°"]
    alturas = [1.5, 1.8, 2.0, 2.2, 2.5]
    r = js("return entrada.textos.map((t) => entrada.alturas.map((h) => M.anchoMm(entrada.fuente, t, h)));",
           {"textos": textos, "alturas": alturas, "fuente": entorno["tabla"]})
    for texto, anchos in zip(textos, r):
        for h, ancho in zip(alturas, anchos):
            assert abs(ancho - entorno["fuente"].ancho_mm(texto, h)) <= TOL, (texto, h)
    # Un carácter que la tabla no trae (aunque Arial lo tenga) no se puede medir: se dice.
    assert js("return [M.sinAncho(entrada, 'AΩBΩ ✓'), M.anchoMm(entrada, 'Ω', 2)];",
              entorno["tabla"]) == [["Ω", "✓"], None]
    c = celda_json(entorno["celdas"]["titulo"])
    assert js("return M.maquetar(entrada.c, 'RESISTENCIA 10 Ω', entrada.f, 0.6, 1.6);",
              {"c": c, "f": entorno["tabla"]}) == {"sin_medir": ["Ω"]}


def test_partir_en_lineas_igual(entorno):
    parrafos = ["PLANTA GENERAL DE LA SUBESTACIÓN Y VÍA DE ACCESO – TRAMO 1", "", "  UNA   SOLA  ",
                "PALABRALARGUÍSIMAQUENOCABEENNINGUNACELDADELROTULO Y OTRA",
                "A-B-C-D-E-F-G-H-I-J-K-L-M-N-Ñ-O-P-Q-R-S-T",
                "CON" + DURO + "ESPACIO" + DURO + "DURO Y\tTABULADOR"]
    casos = [(ancho, altura) for ancho in (8.0, 20.0, 34.7, 154.7) for altura in (1.5, 2.0, 2.5)]
    r = js("return entrada.casos.map(([a, h]) => M.partirEnLineas(entrada.parrafos, a, h, entrada.fuente));",
           {"parrafos": parrafos, "casos": casos, "fuente": entorno["tabla"]})
    assert r == [partir_en_lineas(parrafos, a, h, entorno["fuente"]) for a, h in casos]
    assert ["A-B-C-D-E-F-G-H-I-J-K-L-M-N-Ñ-O-P-Q-R-S-T"] == partir_en_lineas(parrafos[4:5], 8.0, 2.0,
                                                                             entorno["fuente"])  # no parte en guiones


# --- una celda: mismas líneas, alturas y textos de «no cabe» -----------------------------------

TEXTOS = [
    "", "   ", "\n", "A", "PLANTA GENERAL", "DEFINIR", "1:50", "INDICADAS", "06/11/26", "0",
    "EMISIÓN PARA REVISIÓN Y COMENTARIOS DEL CLIENTE",
    "PLANTA GENERAL DE LA SUBESTACIÓN, VÍAS DE ACCESO Y OBRAS DE DRENAJE – SECTOR NORTE",
    "MOVIMIENTO DE TIERRAS: CORTES Y RELLENOS, SECCIONES TRANSVERSALES K0+000 A K2+350, PERFIL "
    "LONGITUDINAL Y CUADRO DE CANTIDADES DE OBRA DEL PROYECTO FOTOVOLTAICO",
    "PALABRALARGUÍSIMAQUENOCABEENNINGUNACELDADELROTULOAUNQUESEREDUZCAALMÍNIMO",
    "SUPERCALIFRAGILÍSTICO-ESPIALIDOSO–CON—GUIONES/Y_BARRAS",
    "ÑANDÚ ÁGUILA PINGÜINO CIGÜEÑA ÓRGANO ÚNICO «ÉL»",
    "LÍNEA UNO\nLÍNEA DOS", "UNO\nDOS\nTRES", "UNO\nDOS\nTRES\nCUATRO", "  CON ESPACIOS   DE MÁS  ",
    "VÍA" + DURO + "SUÁREZ" + DURO + "–" + DURO + "LA" + DURO + "GLORIA", "ING. PERSONA FICTICIA DE PRUEBA",
    "MP 00000-000000 CND", "DIRECTOR DE INGENIERÍA Y DISEÑO", "(DIRECTOR)", "x" * 200, "I" * 60,
    "W W W W W W W W W W W W W W W W",
]
LISTAS = [["UNA"], ["LÍNEA UNO", "LÍNEA DOS"], ["A", "B", "C"], ["A", "B", "C", "D"], ["", "  "],
          [" CON ", "", "HUECO"],
          ["PERSONA FICTICIA DE PRUEBA CON UN NOMBRE MUY LARGO PARA LA CELDA", "(CARGO)"]]


def test_todas_las_celdas_con_los_mismos_resultados(entorno):
    casos = [(c, t) for c in entorno["celdas"].values() for t in TEXTOS]
    casos += [(c, t) for c in entorno["celdas"].values() for t in LISTAS]
    casos += [(c, n) for c in entorno["celdas"].values() for n in (1, 12, 1234567)]
    python = comparar(entorno, casos)
    assert len(casos) > 1500
    # Hay de todo: caben, se reducen y no caben (por líneas y por ancho; en A1 ninguna celda se
    # queda sin alto: eso, con una celda baja inventada).
    assert sum(1 for p in python if p.get("reducido_desde")) >= 3
    problemas = [p["problema"] for p in python if "problema" in p]
    assert any("necesita" in p for p in problemas) and any("mide" in p for p in problemas)
    assert any(", línea " in p for p in problemas)
    baja = dataclasses.replace(entorno["celdas"]["titulo"], ruta="baja",
                               rect=(10.0, 10.0, 60.0, 15.0), alinear="der")
    centrada = dataclasses.replace(baja, ruta="centrada", alinear="centro", rect=(10.0, 10.0, 60.0, 30.0))
    r = comparar(entorno, [(baja, "UNO DOS"), (baja, ["UNO", "DOS"]), (baja, ["UNO", "DOS", "TRES"]),
                           (baja, "UNO"), (centrada, "UNO\nDOS"), (centrada, "UNO DOS TRES CUATRO CINCO SEIS")])
    assert r[1]["problema"] == ("campo 'baja': 2 líneas ocupan 5.2 mm de alto y la celda permite 3.8 mm "
                                "(altura 2.0 mm, la mínima permitida)")
    assert r[0]["altura_mm"] == 2.5 and r[3]["lineas"][0]["base_mm"][0] > 50  # a la derecha


def test_titulo_normal_reducido_y_que_no_cabe(entorno):
    titulo = entorno["celdas"]["titulo"]
    assert (titulo.altura_mm, titulo.altura_min_mm, titulo.lineas_max) == (2.5, 2.0, 3)
    fuente, util = entorno["fuente"], titulo.rect[2] - titulo.rect[0] - 2 * 0.6
    # Tres líneas llenas a 2,5 mm; con una palabra más ya son cuatro: baja hasta que quepa.
    palabras, lleno = "CORTE RELLENO DRENAJE CUNETA ALCANTARILLA TALUD BERMA".split(), ""
    while len(partir_en_lineas([lleno + " X"], util, 2.5, fuente)) <= 3:
        lleno = (lleno + " " + palabras[len(lleno) % len(palabras)]).strip()
    normal, reducido, largo = comparar(entorno, [(titulo, lleno), (titulo, lleno + " X"),
                                                 (titulo, " ".join([lleno] * 3))])
    assert normal["altura_mm"] == 2.5 and normal["reducido_desde"] is None and len(normal["lineas"]) == 3
    assert reducido["reducido_desde"] == 2.5 and 2.0 <= reducido["altura_mm"] < 2.5
    assert len(reducido["lineas"]) == 3
    assert "necesita" in largo["problema"] and "(altura 2.0 mm, la mínima permitida)" in largo["problema"]
    assert largo["problema"].startswith("campo 'titulo': «")


def test_justo_en_el_borde_y_en_cada_paso_de_reduccion(entorno):
    titulo = entorno["celdas"]["titulo"]
    casos = []
    for altura in alturas_a_probar(titulo):
        cabe = justo(entorno, titulo, altura)
        casos += [(titulo, cabe), (titulo, cabe + "."), (titulo, [cabe]), (titulo, [cabe + "."])]
    python = comparar(entorno, casos)
    for i, altura in enumerate(alturas_a_probar(titulo)):
        entra, pasa = python[4 * i + 2], python[4 * i + 3]  # una línea explícita: no se parte
        assert entra["altura_mm"] == altura  # el más ancho que cabe a esta altura se queda en ella
        if altura > titulo.altura_min_mm:
            assert pasa["altura_mm"] < altura  # un punto más y baja un paso
        else:
            assert "mide" in pasa["problema"] and "la mínima permitida" in pasa["problema"]
    # Celdas de una sola línea y sin reducción (firmas, revisiones): el borde exacto.
    for ruta in ("firmas.dibujo.nombre", "firmas.reviso.matricula", "revisiones.A.descripcion", "no_plano"):
        celda = entorno["celdas"][ruta]
        cabe = justo(entorno, celda, celda.altura_mm, letra="Ñ")
        entra, pasa = comparar(entorno, [(celda, [cabe]), (celda, [cabe + "."])])
        assert len(entra["lineas"]) == 1 and entra["reducido_desde"] is None
        assert pasa["problema"].startswith(f"campo '{ruta}': «{cabe}.» mide ")
        assert "la mínima permitida" not in pasa["problema"]


def test_textos_al_azar_en_todas_las_celdas(entorno):
    azar = random.Random(20261110)
    letras = [c for c in CARACTERES if not c.isspace()]
    celdas = list(entorno["celdas"].values())
    casos = []
    for _ in range(600):
        palabras = ["".join(azar.choice(letras) for _ in range(azar.randint(1, 14)))
                    for _ in range(azar.randint(1, 16))]
        separador = azar.choice([" ", " ", " ", "  ", "\n", DURO])
        texto = separador.join(palabras)
        if azar.random() < 0.15 and "\n" not in texto:  # rotulo.py rechaza antes listas con «\n»
            texto = texto.split(" ")
        casos.append((azar.choice(celdas), texto))
    python = comparar(entorno, casos)
    assert 50 < sum(1 for p in python if "problema" in p) < 550


# --- notas ---------------------------------------------------------------------------------------

NOTAS_JS = """
    return entrada.casos.map((notas) =>
        M.maquetarNotas(entrada.campo, notas, entrada.fuente, entrada.relleno, entrada.interlineado));
"""


def py_notas(entorno, notas: list[Nota]) -> dict:
    d = entorno["definicion"]
    try:
        m = maquetar_notas(entorno["notas"], notas, entorno["fuente"], d.relleno_mm, d.interlineado)
    except TextoNoCabe as e:
        return {"problema": str(e)}
    return {"textos": [{"ruta": t.ruta, "lineas": [{"texto": l.texto, "base_mm": list(l.base_mm),
                                                    "ancho_mm": l.ancho_mm} for l in t.lineas],
                        "altura_mm": t.altura_mm, "reducido_desde": t.reducido_desde,
                        "celda_mm": list(t.celda_mm)} for t in m.textos],
            "altura_mm": m.altura_mm, "reducido_desde": m.reducido_desde, "celda_mm": list(m.celda_mm),
            "lineas": m.lineas}


def comparar_notas(entorno, casos: list[list[Nota]]) -> list[dict]:
    d = entorno["definicion"]
    campo = entorno["definicion_json"]["campos"][entorno["notas"].nombre]
    r = js(NOTAS_JS, {"casos": [[{"texto": n.texto, "vinetas": list(n.vinetas), "origen": n.origen}
                                 for n in notas] for notas in casos],
                      "campo": campo, "fuente": entorno["tabla"], "relleno": d.relleno_mm,
                      "interlineado": d.interlineado})
    python = [py_notas(entorno, notas) for notas in casos]
    for notas, p, j in zip(casos, python, r):
        assert iguales(p, j), f"{len(notas)} notas:\n  Python {p}\n  JS     {j}"
    return python


def nota(texto: str, k: int = 0, vinetas=()) -> Nota:
    return Nota(texto, f"adicionales[{k}]", tuple(vinetas))


LARGA = ("TODAS LAS DIMENSIONES ESTÁN EN METROS, EXCEPTO DONDE SE INDIQUE LO CONTRARIO; LAS COTAS "
         "PREVALECEN SOBRE LA ESCALA DEL DIBUJO Y DEBEN VERIFICARSE EN OBRA.")


def test_notas_iguales_normales_con_vinetas_y_limites(entorno):
    campo = entorno["notas"]
    assert (campo.celda.altura_mm, campo.celda.altura_min_mm, campo.separacion_notas) == (1.8, 1.5, 0.5)
    assert entorno["definicion"].interlineado == 1.6
    casos = [
        [],
        [nota("NOTA CORTA.")],
        [nota(LARGA, 0), nota("EL CONCRETO SERÁ DE 21 MPa.", 1, ["CEMENTO TIPO UG.", LARGA]),
         nota("ÑANDÚ – «PINGÜINO».", 2)],
        [nota(LARGA, k, ["VIÑETA UNO.", "VIÑETA DOS."] if k % 3 == 0 else ()) for k in range(12)],
        [nota("PALABRA" + "X" * 150, 0)],
        [nota("BIEN.", 0, ["VIÑETA" + "Y" * 150])],
        [nota(f"NOTA {k}.", k) for k in range(9)],
        [nota(f"NOTA {k}.", k) for k in range(10)],  # dos cifras: la sangría crece
        [nota(LARGA, k) for k in range(30)],
    ]
    # Las fronteras con A1 ERCO: hasta 20 notas largas caben a 1,8 mm; 21 bajan a 1,7; 24 entran
    # justo a 1,5 (la mínima) y 25 ya no caben. (Probar todas las cantidades tarda: PyMuPDF mide
    # cada línea candidata.)
    casos += [[nota(LARGA, k) for k in range(n)] for n in (20, 21, 24, 25)]
    python = comparar_notas(entorno, casos)
    assert python[0] == {"textos": [], "altura_mm": 1.8, "reducido_desde": None,
                         "celda_mm": list(campo.celda.rect), "lineas": 0}
    assert python[2]["altura_mm"] == 1.8
    assert [t["lineas"][0]["texto"] for t in python[2]["textos"]] == ["1.", "2.", "3."]
    assert "•" in [l["texto"] for l in python[2]["textos"][1]["lineas"]]
    assert python[4]["problema"].startswith("campo 'notas', nota 1 (adicionales[0]): «PALABRA")
    assert "el ancho para el texto de las notas es" in python[4]["problema"]
    assert python[5]["problema"].startswith("campo 'notas', nota 1, viñeta 1 (adicionales[0]): «VIÑETA")
    assert "no caben desde la nota" in python[8]["problema"] and "(la mínima permitida)" in python[8]["problema"]
    assert [p.get("altura_mm") for p in python[9:]] == [1.8, 1.7, 1.5, None]
    assert [p.get("reducido_desde") for p in python[9:12]] == [None, 1.8, 1.8]
    assert python[12]["problema"].startswith("campo 'notas': 25 notas (")
    assert "no caben desde la nota 25 (adicionales[24])" in python[12]["problema"]


def test_notas_al_azar(entorno):
    azar = random.Random(4305)
    letras = [c for c in CARACTERES if not c.isspace()]

    def frase(maximo):
        return " ".join("".join(azar.choice(letras) for _ in range(azar.randint(1, 12)))
                        for _ in range(azar.randint(1, maximo)))

    casos = [[nota(frase(25), k, [frase(10) for _ in range(azar.choice([0, 0, 1, 3]))])
              for k in range(azar.randint(1, 28))] for _ in range(16)]
    python = comparar_notas(entorno, casos)
    assert 1 <= sum(1 for p in python if "problema" in p) < 15


def test_textos_de_los_avisos_de_reduccion():
    r = js("""return [M.avisoReducido({ruta: "titulo", altura_mm: 2.2, reducido_desde: 2.5}),
                      M.avisoNotasReducidas({altura_mm: 1.6, reducido_desde: 1.8})];""")
    # Los mismos de rotulo.preparar_rotulo y rotulo._notas (la paridad completa, en los pasos 2 a 4).
    assert r == ["Advertencia: en el rótulo, el campo 'titulo' se escribió a 2.2 mm de altura (pedida 2.5 mm) "
                 "para que quepa en su celda.",
                 "Advertencia: en el rótulo, las notas se escribieron a 1.6 mm de altura (pedida 1.8 mm) para "
                 "que quepan en su celda."]
