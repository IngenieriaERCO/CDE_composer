"""Muestras de línea y relleno en las convenciones (subfase 9a): se leen, se ubican, se dibujan
como vector, se verifican en el PDF y conviven con los símbolos de siempre."""

import shutil
from dataclasses import replace

import pymupdf
import pytest
from conftest import casilla_conv, requiere_arial
from test_simbolos import _plano, biblioteca, entorno  # noqa: F401 (fixtures)

from componedor import componer as modulo_componer
from componedor.cli import main
from componedor.componer import PlanoNoComponible, componer_plano
from componedor.muestras_leyenda import (
    Muestra,
    colocar_muestra,
    dibujar_muestras,
    leer_muestra,
    verificar_muestras,
)
from componedor.rotulo import _tipo
from componedor.unidades import PT_POR_MM

CASILLA = (672.4, 249.39, 693.84, 259.88)
ROJO = (1.0, 0.0, 0.0)


def _leer(item):
    problemas = []
    return leer_muestra(item, "x", problemas, _tipo), problemas


def test_leer_con_valores_por_defecto_y_normaliza_el_color():
    linea, p1 = _leer({"tipo": "linea"})
    relleno, p2 = _leer({"tipo": "relleno", "color": "#00a000", "opacidad": 0.5})
    assert p1 == p2 == []
    assert linea == Muestra("linea", "#000000", 0.25, "continua")
    assert relleno == Muestra("relleno", "#00A000", opacidad=0.5)
    assert relleno.rgb == pytest.approx((0, 160 / 255, 0))


@pytest.mark.parametrize("item, mensaje", [
    ({"tipo": "linea", "color": "rojo"},
     "x.color: se esperaba un color «#RRGGBB» (p. ej. «#FF0000» = rojo); tiene texto 'rojo'"),
    ({"tipo": "linea", "color": "#FF00"}, "x.color: se esperaba un color «#RRGGBB»"),
    ({"tipo": "linea", "grosor_mm": 3}, "x.grosor_mm: se esperaba un número de 0.05 a 2 mm; tiene int 3"),
    ({"tipo": "linea", "grosor_mm": True}, "tiene un booleano (true)"),
    ({"tipo": "linea", "trazo": "punteada"},
     "x.trazo: se esperaba «continua» o «discontinua»; tiene texto 'punteada'"),
    ({"tipo": "relleno", "opacidad": 0},
     "x.opacidad: se esperaba un número mayor que 0 y hasta 1 (1 = opaco); tiene int 0"),
])
def test_valores_malos_con_mensaje_claro(item, mensaje):
    muestra, problemas = _leer(item)
    assert muestra is None and len(problemas) == 1 and mensaje in problemas[0]


def test_colocar_centrada_y_recortada_si_no_cabe():
    linea = colocar_muestra(Muestra("linea", "#000000"), 1, CASILLA, 0.6)
    cx, cy = (CASILLA[0] + CASILLA[2]) / 2, (CASILLA[1] + CASILLA[3]) / 2
    assert linea.dibujo == pytest.approx((cx - 6.5, cy, cx + 6.5, cy))
    relleno = colocar_muestra(Muestra("relleno", "#808080"), 1, CASILLA, 0.6)
    assert relleno.dibujo == pytest.approx((cx - 6.5, cy - 3, cx + 6.5, cy + 3))
    chica = (0, 0, 10, 4)  # útil 8,8 x 2,8 mm
    assert colocar_muestra(Muestra("linea", "#000000"), 1, chica, 0.6).dibujo == pytest.approx((0.6, 2, 9.4, 2))
    assert colocar_muestra(Muestra("relleno", "#000000"), 1, chica, 0.6).dibujo == pytest.approx((0.6, 0.6, 9.4, 3.4))


def test_dibujar_y_verificar_detecta_cada_diferencia():
    doc = pymupdf.open()
    page = doc.new_page(width=841 * PT_POR_MM, height=594 * PT_POR_MM)
    c = colocar_muestra(Muestra("linea", "#FF0000", 0.35, "discontinua"), 1, CASILLA, 0.6)
    dibujar_muestras(page, [c], 594)
    assert verificar_muestras(page, [c], 594) == []
    d = page.get_drawings()[0]
    assert d["color"] == ROJO and d["width"] == pytest.approx(0.35 * PT_POR_MM)
    assert d["dashes"] != "[] 0"
    otras = [replace(c, muestra=Muestra("linea", "#0000FF", 0.5, "continua")),
             replace(c, dibujo=(c.dibujo[0] + 0.3, c.dibujo[1], c.dibujo[2] + 0.3, c.dibujo[3]))]
    problemas = verificar_muestras(page, otras, 594)
    assert "convenciones, casilla 1 (línea): el grosor es 0.350 mm y debía ser 0.5 mm" in problemas
    assert "convenciones, casilla 1 (línea): el trazo debía ser continua y en el PDF es discontinuo" in problemas
    assert "convenciones, casilla 1 (línea): el color en el PDF no es #0000FF" in problemas
    assert any("la muestra quedó en" in p and "diferencia máx. 0.300 mm" in p for p in problemas)


def _dibujos_en(ruta, casilla):
    k = PT_POR_MM
    caja = pymupdf.Rect(casilla[0] * k - 0.3, (594 - casilla[3]) * k - 0.3, casilla[2] * k + 0.3,
                        (594 - casilla[1]) * k + 0.3)
    with pymupdf.open(ruta) as doc:
        return [d for d in doc[0].get_drawings() if caja.contains(d["rect"])]


MEZCLA = [
    {"simbolo": "corte"},  # el renglón de siempre (sin tipo)
    {"tipo": "linea", "descripcion": "RED DE MEDIA TENSIÓN", "color": "#FF0000", "grosor_mm": 0.35,
     "trazo": "discontinua"},
    {"tipo": "relleno", "descripcion": "ZONA VERDE", "color": "#00A000", "opacidad": 0.5},
    {"tipo": "simbolo", "simbolo": "via", "descripcion": "VÍA"},  # tipo explícito
    {"tipo": "linea", "descripcion": ["LÍMITE DE OBRA", "(PROVISIONAL)"]},  # por defecto
    {"tipo": "linea", "descripcion": "OTRA IGUAL"},  # las muestras pueden repetirse
]


@requiere_arial
def test_componer_mezcla_simbolos_y_muestras_en_vector(entorno):  # noqa: F811
    r = componer_plano(_plano(entorno, MEZCLA), entorno / "p.pdf")
    assert [s.posicion for s in r.simbolos] == [1, 4]
    assert [(m.posicion, m.muestra.tipo) for m in r.muestras] == [
        (2, "linea"), (3, "relleno"), (5, "linea"), (6, "linea")]
    assert r.rotulo["convenciones"] == "6 convención(es)" and r.advertencias == []
    roja = _dibujos_en(entorno / "p.pdf", casilla_conv(2))
    assert len(roja) == 1 and roja[0]["color"] == ROJO and roja[0]["dashes"] != "[] 0"
    assert roja[0]["width"] == pytest.approx(0.35 * PT_POR_MM, abs=1e-4)
    verde = _dibujos_en(entorno / "p.pdf", casilla_conv(3))
    assert len(verde) == 1 and verde[0]["type"] == "f" and verde[0]["fill_opacity"] == 0.5
    negra = _dibujos_en(entorno / "p.pdf", casilla_conv(5))
    assert negra[0]["color"] == (0, 0, 0) and negra[0]["dashes"] == "[] 0"
    with pymupdf.open(entorno / "p.pdf") as doc:
        texto = doc[0].get_text()
        # Nada rasterizado en las convenciones (la única imagen es la de la plantilla sintética).
        zona = pymupdf.Rect(672.4 * PT_POR_MM, (594 - 270.5) * PT_POR_MM, 828.3 * PT_POR_MM,
                            (594 - 137.7) * PT_POR_MM)
        assert not [i for i in doc[0].get_image_info() if pymupdf.Rect(i["bbox"]).intersects(zona)]
    for t in ("RED DE MEDIA TENSIÓN", "ZONA VERDE", "LÍMITE DE OBRA", "(PROVISIONAL)", "VÍA",
              "DESCRIPCIÓN CORTE"):
        assert t in texto


@requiere_arial
def test_solo_muestras_no_necesita_la_biblioteca(entorno):  # noqa: F811
    shutil.rmtree(entorno / "simbolos" / "biblioteca")
    r = componer_plano(_plano(entorno, [{"tipo": "relleno", "descripcion": "AGUA"}]), entorno / "p.pdf")
    assert len(r.muestras) == 1 and r.simbolos == []


@requiere_arial
def test_todos_los_problemas_de_las_muestras_juntos(entorno):  # noqa: F811
    convenciones = [
        {"tipo": "circulo", "descripcion": "X"},
        {"tipo": "linea", "color": "rojo", "trazo": "punteada", "descripcion": "A"},
        {"tipo": "linea"},
        {"tipo": "relleno", "descripcion": "  ", "simbolo": "corte", "opacidad": 2},
        {"tipo": "simbolo", "simbolo": "corte", "color": "#FF0000"},
    ]
    with pytest.raises(PlanoNoComponible) as e:
        componer_plano(_plano(entorno, convenciones), entorno / "p.pdf")
    m = str(e.value)
    for texto in [
        "- rotulo.convenciones[0].tipo: se esperaba «simbolo», «linea» o «relleno»; tiene texto 'circulo'",
        "- rotulo.convenciones[1].color: se esperaba un color «#RRGGBB» (p. ej. «#FF0000» = rojo); tiene texto 'rojo'",
        "- rotulo.convenciones[1].trazo: se esperaba «continua» o «discontinua»; tiene texto 'punteada'",
        ("- rotulo.convenciones[2].descripcion: falta la descripción (una línea o un relleno no tiene "
        "descripción por defecto)"),
        "- rotulo.convenciones[3].simbolo: campo no reconocido (campos válidos: color, descripcion, opacidad, tipo)",
        "- rotulo.convenciones[3].opacidad: se esperaba un número mayor que 0 y hasta 1",
        "- rotulo.convenciones[3].descripcion: falta la descripción",
        "- rotulo.convenciones[4].color: campo no reconocido (campos válidos: descripcion, simbolo, tipo)",
    ]:
        assert texto in m
    assert not (entorno / "p.pdf").exists()


@requiere_arial
def test_falla_forzada_si_la_muestra_sale_de_otro_color(entorno, monkeypatch):  # noqa: F811
    original = modulo_componer.dibujar_muestras

    def azul(page, colocaciones, alto):
        return original(page, [replace(c, muestra=replace(c.muestra, color="#0000FF"))
                               for c in colocaciones], alto)

    monkeypatch.setattr(modulo_componer, "dibujar_muestras", azul)
    with pytest.raises(PlanoNoComponible) as e:
        componer_plano(_plano(entorno, [{"tipo": "linea", "descripcion": "A", "color": "#FF0000"}]),
                       entorno / "p.pdf")
    assert "- convenciones, casilla 1 (línea): el color en el PDF no es #FF0000" in str(e.value)
    assert not (entorno / "p.pdf").exists()


@requiere_arial
def test_cli_resume_las_muestras(entorno, capsys):  # noqa: F811
    _plano(entorno, MEZCLA)
    assert main(["componer", str(entorno / "plano.json"), "--salida", str(entorno / "p.pdf")]) == 0
    out = capsys.readouterr().out
    assert "Convenciones: 3 línea(s) y 1 relleno(s) dibujados como vector." in out
    assert "cada muestra de línea o relleno de las convenciones está en su casilla" in out
