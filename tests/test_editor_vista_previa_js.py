"""Vista previa del rótulo en el editor (subfase 4.3f), con Node, comparando con Python.

`EditorVistaPrevia` (editor_vista_previa.js) debe decir lo MISMO que `componer` (±1e-6 mm):
- `piezasRotulo` = `rotulo.preparar_rotulo`: los mismos textos (ruta, líneas, base, ancho,
  altura, celda) en el mismo orden, los símbolos de convenciones (casilla, escala, página y
  dibujo) y la caja de cada firma en imagen;
- `colocarSimbolo` = `simbolos.colocar_simbolo`; `cajaFirma` = `firmas.caja_firma`;
- `etiquetasEscala` = `etiquetas_escala.colocar_etiquetas` (textos y avisos).
Un campo con problema no se dibuja y sale en `problemas` con el mismo texto que el error de
Python; los demás campos se dibujan igual que si ese campo no estuviera.
Textos sintéticos; las personas son ficticias."""

import json
import random
import shutil
import subprocess
from pathlib import Path

import pytest

import componedor
from componedor.datos_editor import preparar_editor
from componedor.etiquetas_escala import DetalleParaEtiqueta, colocar_etiquetas
from componedor.firmas import caja_firma
from componedor.formato import cargar_formato
from componedor.fuente import cargar_fuente
from componedor.rotulo import RotuloInvalido, preparar_rotulo
from componedor.rotulo_formato import Celda
from componedor.simbolos import Simbolo, colocar_simbolo
from conftest import crear_paquete_real, requiere_arial
from test_datos_rotulo_editor import _formato_con_biblioteca
from test_firmas import garabato

NODE = shutil.which("node")
pytestmark = [pytest.mark.skipif(NODE is None, reason="Node no está instalado"), requiere_arial]
CARPETA_JS = Path(componedor.__file__).parent / "editor"
TOL = 1e-6
AREA = (22.7, 22.7, 662.4, 571.3)

LARGO = ("PLANTA GENERAL DE LA SUBESTACIÓN ELÉCTRICA, VÍAS DE ACCESO INTERNAS, OBRAS DE DRENAJE "
         "PLUVIAL Y CERRAMIENTO PERIMETRAL DEL PARQUE SOLAR FOTOVOLTAICO SECTOR NORTE ETAPA DOS CON "
         "SUS REDES DE MEDIA TENSIÓN Y CANALIZACIONES SUBTERRÁNEAS, CAJAS")


def js(codigo: str, entrada=None):
    script = (
        f"const V = require({json.dumps(str(CARPETA_JS / 'editor_vista_previa.js'))});"
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
    carpeta = tmp_path_factory.mktemp("vista_previa")
    ruta = _formato_con_biblioteca(carpeta)  # símbolos "corte" (CORTE) y "panel" (PANEL)
    garabato(carpeta / "firmas" / "Persona Ficticia" / "firma.png", semilla=3)
    garabato(carpeta / "firmas" / "Otra Persona" / "firma.png", ancho_px=300, alto_px=200, semilla=4)
    notas = carpeta / "notas"
    (notas / "vias").mkdir(parents=True)
    (notas / "generales.txt").write_text("LAS COTAS ESTÁN EN METROS.\nNIVELES REFERIDOS AL IGAC.\n",
                                         encoding="utf-8")
    (notas / "vias" / "pavimentos.txt").write_text(
        "PAVIMENTO FLEXIBLE:\n- BASE GRANULAR DE 0,30 M.\n- CARPETA ASFÁLTICA MDC-19.\n",
        encoding="utf-8")
    crear_paquete_real(carpeta / "input", "a")
    editor = carpeta / "editor"
    datos = preparar_editor(carpeta / "input", ruta, editor, carpeta_notas=notas)
    formato = cargar_formato(ruta, usar_plantilla=False)
    return {"datos": datos, "definicion": formato.rotulo, "fuente": cargar_fuente(formato.rotulo.fuente),
            "carpeta": editor}


PIEZAS = """
    const d = entrada.datos.rotulo;
    return V.piezasRotulo({rotulo: entrada.rotulo, definicion: d.definicion, fuente: d.fuente,
        simbolos: d.simbolos, catalogo: d.notas, escalas: entrada.escalas});
"""


def editor(entorno, valores, escalas=(50.0,)) -> dict:
    return js(PIEZAS, {"datos": entorno["datos"], "rotulo": valores, "escalas": list(escalas)})


def python(entorno, valores, escalas=(50.0,)):
    return preparar_rotulo(entorno["definicion"], valores, list(escalas), entorno["fuente"],
                           entorno["carpeta"])


def _iguales(a, b, donde):
    assert len(a) == len(b), donde
    for x, y in zip(a, b):
        assert x == pytest.approx(y, abs=TOL), donde


def comparar_textos(textos_js: list, textos_py: list) -> None:
    assert [t["ruta"] for t in textos_js] == [t.ruta for t in textos_py]
    for tj, tp in zip(textos_js, textos_py):
        assert tj["altura_mm"] == pytest.approx(tp.altura_mm, abs=TOL), tp.ruta
        _iguales(tj["celda_mm"], tp.celda_mm, tp.ruta)
        assert [l["texto"] for l in tj["lineas"]] == [l.texto for l in tp.lineas], tp.ruta
        for lj, lp in zip(tj["lineas"], tp.lineas):
            _iguales(lj["base_mm"], lp.base_mm, f"{tp.ruta}: {lp.texto}")
            assert lj["ancho_mm"] == pytest.approx(lp.ancho_mm, abs=TOL), lp.texto


def comparar_todo(entorno, valores, escalas=(50.0,)) -> dict:
    e = editor(entorno, valores, escalas)
    p = python(entorno, valores, escalas)
    assert e["problemas"] == []
    comparar_textos(e["textos"], p.textos)
    assert [s["id"] for s in e["simbolos"]] == [s.simbolo.id for s in p.simbolos]
    for sj, sp in zip(e["simbolos"], p.simbolos):
        assert sj["posicion"] == sp.posicion
        assert sj["escala"] == pytest.approx(sp.escala, abs=1e-9)
        _iguales(sj["casilla"], sp.casilla, sp.simbolo.id)
        _iguales(sj["pagina_mm"], sp.destino_pagina, sp.simbolo.id)
        _iguales(sj["dibujo_mm"], sp.destino_dibujo, sp.simbolo.id)
    assert [f["ruta"] for f in e["firmas"]] == [f.ruta_celda for f in p.firmas]
    for fj, fp in zip(e["firmas"], p.firmas):
        _iguales(fj["caja_mm"], fp.caja, fp.ruta_celda)
        _iguales(fj["celda_mm"], fp.celda, fp.ruta_celda)
    return e


COMPLETO = {
    "titulo": LARGO,
    "disenador": "PERSONA FICTICIA",
    "este": "1.234.567,89", "norte": "987.654,32",
    "no_plano": "ERCO-PSF-CIV-PL-0001",
    "hoja": 3, "de": 12,
    "revisiones": [
        {"ver": "A", "fecha": "01/10/26", "descripcion": "EMISIÓN PARA REVISIÓN INTERNA", "dibujo": "PF", "reviso": "OP"},
        {"ver": "0", "fecha": "10/11/26", "descripcion": "PARA CONSTRUCCIÓN"},
        {"ver": "B", "descripcion": "AJUSTES"},
    ],
    "firmas": {
        "dibujo": {"nombre": "PERSONA FICTICIA", "firma": {"imagen": "Persona Ficticia"}, "matricula": "12345"},
        "reviso": {"nombre": ["OTRA PERSONA", "INGENIERA CIVIL"], "firma": {"imagen": "Otra Persona"}},
        "diseno": {"nombre": "TERCERA PERSONA", "firma": "T.P."},
    },
    "convenciones": [{"simbolo": "panel"}, {"simbolo": "corte", "descripcion": "CORTE TRANSVERSAL TÍPICO DE LA VÍA"}],
    "notas": {"archivos": ["../notas/vias/pavimentos.txt", "../notas/generales.txt"],
              "adicionales": ["NOTA ESCRITA A MANO EN EL EDITOR.",
                              {"texto": "DRENAJE:", "vinetas": ["CUNETAS EN CONCRETO.", "ALCANTARILLAS DE 36\"."]}]},
}


def _validos(entorno, valores):
    """Quita las claves que la definición del formato de prueba no tiene."""
    campos = entorno["definicion"].campos
    return {k: v for k, v in valores.items() if k in campos}


def test_plano_completo_igual_que_componer(entorno):
    valores = _validos(entorno, COMPLETO)
    assert {"titulo", "revisiones", "firmas", "convenciones", "notas"} <= set(valores)
    e = comparar_todo(entorno, valores)
    rutas = [t["ruta"] for t in e["textos"]]
    assert "convenciones.2.descripcion" in rutas and "escala" in rutas and "notas.5" in rutas
    assert [f["persona"] for f in e["firmas"]] == ["Persona Ficticia", "Otra Persona"]


@pytest.mark.parametrize("valores, escalas", [
    ({}, (50.0,)),  # solo los por defecto («DEFINIR») y ESCALA
    ({}, (50.0, 100.0)),  # INDICADAS
    ({}, ()),  # sin detalles: ESCALA vacía
    ({"titulo": ["LÍNEA UNO", "LÍNEA DOS", "LÍNEA TRES"]}, (1000.0,)),
    ({"titulo": "PLANTA\nY PERFIL"}, (500.0,)),
    ({"titulo": None, "disenador": ""}, (50.0,)),
    ({"revisiones": [{"ver": "C", "descripcion": "TERCERA"}, {"ver": "A"}]}, (50.0,)),
    ({"convenciones": [{"simbolo": "corte", "descripcion": ""}]}, (50.0,)),
    ({"notas": {"adicionales": [LARGO] * 3}}, (50.0,)),
    ({"notas": {"archivos": ["../notas/generales.txt"]}}, (50.0,)),
    ({"firmas": {"aprobo": {"nombre": "PERSONA FICTICIA", "firma": {"imagen": "Persona Ficticia"}}}}, (50.0,)),
])
def test_variaciones_iguales_que_componer(entorno, valores, escalas):
    comparar_todo(entorno, _validos(entorno, valores), escalas)


def test_veinte_notas_reducidas_igual_que_componer(entorno):
    notas = [f"NOTA NÚMERO {k} CON UN TEXTO LARGO PARA OCUPAR VARIAS LÍNEAS EN LA CELDA DE LAS NOTAS DEL RÓTULO."
             for k in range(1, 21)]
    e = comparar_todo(entorno, {"notas": {"adicionales": notas}})
    alturas = {t["altura_mm"] for t in e["textos"] if t["ruta"].startswith("notas.")}
    assert len(alturas) == 1 and alturas.pop() < 2.0


@pytest.mark.parametrize("malo, ruta", [
    ({"titulo": " ".join([LARGO] * 3)}, "titulo"),  # no cabe
    ({"no_plano": "ERCO-PSF-CIV-PL-0001-REVISION-EXTRA-MUY-LARGA-QUE-NO-CABE"}, "no_plano"),
    ({"no_plano": "PRIMERA\nSEGUNDA"}, "no_plano"),  # salto de línea en celda de una línea
    ({"norte": 2.5}, "norte"),  # tipo no válido
    ({"disenador": "ÁNGULO ☃"}, "disenador"),  # carácter que Arial no tiene
    ({"notas": {"adicionales": [LARGO] * 30}}, "notas"),
    ({"convenciones": [{"simbolo": "corte", "descripcion": " ".join([LARGO] * 2)}]}, "convenciones.1.descripcion"),
    ({"firmas": {"dibujo": {"nombre": "NOMBRE DE UNA PERSONA FICTICIA MUCHO MÁS LARGO QUE SU CELDA"}}},
     "firmas.dibujo.nombre"),
])
def test_campo_con_problema_no_se_dibuja_y_lo_demas_si(entorno, malo, ruta):
    base = _validos(entorno, {"titulo": "PLANTA GENERAL", "disenador": "PERSONA FICTICIA",
                              "revisiones": [{"ver": "A", "descripcion": "PRIMERA"}],
                              "convenciones": [{"simbolo": "panel"}]})
    valores = dict(base, **_validos(entorno, malo))
    e = editor(entorno, valores)
    with pytest.raises(RotuloInvalido) as error:
        python(entorno, valores)
    errores = [p for p in e["problemas"] if p["nivel"] == "error"]
    assert [p["ruta"] for p in errores] == [ruta]
    assert errores[0]["mensaje"] in error.value.problemas
    assert errores[0]["rect_mm"] and len(errores[0]["rect_mm"]) == 4
    assert ruta not in [t["ruta"] for t in e["textos"]]
    # Lo demás, igual que componer sin el campo malo (por defecto, si lo tiene).
    clave = next(iter(malo))
    sin_malo = {k: v for k, v in valores.items() if k != clave}
    if clave == "convenciones":
        sin_malo["convenciones"] = [{"simbolo": "corte", "descripcion": ""}]  # mismo símbolo, sin texto
    p = python(entorno, sin_malo)
    esperados = [t for t in p.textos if t.ruta != ruta]
    comparar_textos(e["textos"], esperados)


def test_simbolo_que_no_esta_en_la_biblioteca(entorno):
    e = editor(entorno, {"convenciones": [{"simbolo": "no_existe"}, {"simbolo": "corte"}]})
    assert [p["ruta"] for p in e["problemas"]] == ["convenciones.1.descripcion"]
    assert [s["id"] for s in e["simbolos"]] == ["corte"] and e["simbolos"][0]["posicion"] == 2


def test_nota_de_un_archivo_fuera_del_catalogo_solo_avisa(entorno):
    e = editor(entorno, {"notas": {"archivos": ["no_esta.txt"], "adicionales": ["UNA NOTA."]}})
    assert [(p["ruta"], p["nivel"]) for p in e["problemas"]] == [("notas", "aviso")]
    assert not [t for t in e["textos"] if t["ruta"].startswith("notas.")]


# --- colocar_simbolo, caja_firma y etiquetas: comparación directa ---------------------------

def test_colocar_simbolo_igual_que_python():
    azar = random.Random(43)
    casos = []
    for _ in range(400):
        x0, y0 = azar.uniform(600, 800), azar.uniform(100, 300)
        casilla = (x0, y0, x0 + azar.uniform(3, 30), y0 + azar.uniform(2, 15))
        tamano = (azar.choice([0.0, azar.uniform(0.5, 40)]), azar.choice([0.0, azar.uniform(0.5, 20)]))
        casos.append({"tamano": tamano, "casilla": casilla, "relleno": azar.choice([0.0, 0.6, 1.0]),
                      "margen": azar.choice([0.0, 0.5, 1.0]), "posicion": azar.randint(1, 24)})
    salida = js("return entrada.map((c) => V.colocarSimbolo(c.tamano, c.posicion, c.casilla, c.relleno, c.margen));", casos)
    for c, s in zip(casos, salida):
        simbolo = Simbolo("x", "X", 1, 1, (0.0, 0.0, *c["tamano"]), 0)
        assert simbolo.tamano_mm == pytest.approx(c["tamano"])
        p = colocar_simbolo(simbolo, c["posicion"], c["casilla"], c["relleno"], c["margen"])
        assert s["escala"] == pytest.approx(p.escala, abs=1e-12)
        _iguales(s["pagina_mm"], p.destino_pagina, c)
        _iguales(s["dibujo_mm"], p.destino_dibujo, c)


def test_caja_de_firma_igual_que_python(entorno):
    tabla = entorno["datos"]["rotulo"]["definicion"]["campos"]["firmas"]
    casos = []
    for campo in entorno["definicion"].campos["firmas"].celdas.values():
        for alto_max in (0.0, 3.3, 5.0, 9.0, 40.0):
            for relleno in (0.0, 0.6, 1.5):
                casos.append({"rect": list(campo.rect), "alto_max": alto_max, "relleno": relleno,
                              "cuerpo": list(campo.cuerpo_y) if campo.cuerpo_y else None})
    casos.append({"rect": [700.0, 40.0, 720.0, 44.5], "alto_max": 5.0, "relleno": 0.6, "cuerpo": None})
    assert tabla["cuerpo_y"] is not None
    salida = js("return entrada.map((c) => V.cajaFirma(c.rect, c.alto_max, c.cuerpo, c.relleno));", casos)
    for c, s in zip(casos, salida):
        celda = Celda("firmas.x.firma", tuple(c["rect"]), "cen", 2.0, 1.5, 1, True, c["alto_max"],
                      tuple(c["cuerpo"]) if c["cuerpo"] else None)
        _iguales(s, caja_firma(celda, c["relleno"]), c)


ETIQUETAS = """
    return entrada.casos.map((c) => V.etiquetasEscala({detalles: c.detalles, area_mm: c.area,
        elementos: c.elementos, fuente: entrada.fuente}));
"""


def _caso_etiquetas(azar):
    detalles = []
    for i in range(azar.randint(1, 6)):
        x0, y0 = azar.uniform(10, 600), azar.uniform(10, 540)
        dibujo = (x0, y0, x0 + azar.uniform(20, 250), y0 + azar.uniform(10, 200))
        detalles.append({"id": f"d{i}", "dibujo_mm": dibujo,
                         "denominador": azar.choice([20.0, 50.0, 100.0, 1000.0, 12.5, 25000.0]),
                         "con_etiqueta": azar.random() > 0.15})
    elementos = [["ROSA DE LOS VIENTOS", (x := azar.uniform(30, 600), y := azar.uniform(30, 500), x + 40, y + 40)]]
    return {"detalles": detalles, "area": AREA, "elementos": elementos if azar.random() > 0.3 else []}


def test_etiquetas_escala_iguales_que_python(entorno):
    azar = random.Random(7)
    casos = [_caso_etiquetas(azar) for _ in range(250)]
    # Casos puntuales: debajo, encima (debajo se sale), ninguno (aviso), sin etiqueta.
    casos += [
        {"detalles": [{"id": "a", "dibujo_mm": (100, 200, 300, 260), "denominador": 1000.0, "con_etiqueta": True}],
         "area": AREA, "elementos": []},
        {"detalles": [{"id": "a", "dibujo_mm": (100, 23, 300, 260), "denominador": 50.0, "con_etiqueta": True}],
         "area": AREA, "elementos": []},
        {"detalles": [{"id": "a", "dibujo_mm": (100, 23, 300, 570), "denominador": 50.0, "con_etiqueta": True}],
         "area": AREA, "elementos": []},
        {"detalles": [{"id": "a", "dibujo_mm": (100, 200, 300, 260), "denominador": 50.0, "con_etiqueta": False}],
         "area": AREA, "elementos": []},
    ]
    salida = js(ETIQUETAS, {"casos": casos, "fuente": entorno["datos"]["rotulo"]["fuente"]})
    avisos_vistos = 0
    for c, s in zip(casos, salida):
        textos, avisos = colocar_etiquetas(
            [DetalleParaEtiqueta(d["id"], tuple(d["dibujo_mm"]), d["denominador"], d["con_etiqueta"])
             for d in c["detalles"]],
            c["area"], [(n, tuple(r)) for n, r in c["elementos"]], entorno["fuente"])
        comparar_textos(s["textos"], textos)
        assert s["avisos"] == avisos
        avisos_vistos += len(avisos)
    assert avisos_vistos > 10  # el azar sí produjo etiquetas que no caben
