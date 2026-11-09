"""Maquetación de texto en una celda: alineación, centrado vertical, cortes, reducción y
errores claros (nunca recortar ni reducir en silencio)."""

import pytest

from componedor.fuente import cargar_fuente
from componedor.maquetacion import TextoNoCabe, maquetar
from componedor.rotulo_formato import Celda
from conftest import ARIAL, requiere_arial

pytestmark = requiere_arial
RELLENO = 0.6
INTERLINEADO = 1.6


@pytest.fixture(scope="module")
def fuente():
    return cargar_fuente(ARIAL)


def _celda(rect=(100.0, 50.0, 160.0, 60.0), alinear="izq", altura=2.0, minima=None, lineas=1):
    return Celda("campo", rect, alinear, altura, altura if minima is None else minima, lineas)


@pytest.mark.parametrize("alinear", ["izq", "centro", "der"])
def test_una_linea_alineada_y_centrada_en_alto(fuente, alinear):
    t = maquetar(_celda(alinear=alinear), "ABC", fuente, RELLENO, INTERLINEADO)
    (linea,) = t.lineas
    ancho = fuente.ancho_mm("ABC", 2.0)
    x = {"izq": 100.6, "centro": 130 - ancho / 2, "der": 160 - 0.6 - ancho}[alinear]
    assert linea.base_mm == pytest.approx((x, 54.0))  # mayúsculas de 54 a 56: centradas en 55
    assert linea.ancho_mm == pytest.approx(ancho)
    assert t.altura_mm == 2.0 and t.reducido_desde is None
    assert t.rect() == pytest.approx((x, 54.0, x + ancho, 56.0))


def test_texto_vacio_no_escribe_nada(fuente):
    assert maquetar(_celda(), "   ", fuente, RELLENO, INTERLINEADO).lineas == ()
    assert maquetar(_celda(lineas=3), ["", ""], fuente, RELLENO, INTERLINEADO).lineas == ()


def test_varias_lineas_se_parten_por_palabras(fuente):
    celda = _celda(rect=(0.0, 0.0, 40.0, 30.0), alinear="centro", lineas=3)
    texto = "PARQUE SOLAR FOTOVOLTAICO VÍA DE ACCESO"
    t = maquetar(celda, texto, fuente, RELLENO, INTERLINEADO)
    assert len(t.lineas) > 1
    assert " ".join(l.texto for l in t.lineas) == texto  # no se pierde ni se recorta nada
    assert all(l.ancho_mm <= 40 - 2 * RELLENO for l in t.lineas)
    # Bloque centrado: base a base 1,6 x 2 = 3,2 mm; mayúsculas de la 1.ª a la última.
    bases = [l.base_mm[1] for l in t.lineas]
    assert [a - b for a, b in zip(bases, bases[1:])] == pytest.approx([3.2] * (len(bases) - 1))
    assert (bases[0] + 2.0 + bases[-1]) / 2 == pytest.approx(15.0)


def test_lineas_explicitas_no_se_parten(fuente):
    celda = _celda(rect=(0.0, 0.0, 60.0, 12.0), lineas=2)
    t = maquetar(celda, ["ANDRÉS GÓMEZ", "(DIRECTOR)"], fuente, RELLENO, INTERLINEADO)
    assert [l.texto for l in t.lineas] == ["ANDRÉS GÓMEZ", "(DIRECTOR)"]


def test_salto_de_linea_en_el_texto_inicia_otra_linea(fuente):
    t = maquetar(_celda(rect=(0.0, 0.0, 60.0, 20.0), lineas=3), "UNO\nDOS", fuente, RELLENO,
                 INTERLINEADO)
    assert [l.texto for l in t.lineas] == ["UNO", "DOS"]


def test_reduce_hasta_la_minima_y_lo_informa(fuente):
    texto = "ABCDEFGHIJ"
    ancho_25 = fuente.ancho_mm(texto, 2.5)
    # Celda que deja pasar el texto a 2,2 mm pero no a 2,3.
    ancho_util = fuente.ancho_mm(texto, 2.25)
    celda = _celda(rect=(0.0, 0.0, ancho_util + 2 * RELLENO, 10.0), altura=2.5, minima=2.0)
    t = maquetar(celda, texto, fuente, RELLENO, INTERLINEADO)
    assert ancho_25 > ancho_util
    assert t.altura_mm == pytest.approx(2.2)
    assert t.reducido_desde == 2.5


def test_no_cabe_a_lo_ancho_error_con_campo_texto_y_medidas(fuente):
    celda = Celda("revisiones.A.aprobo", (816.8, 112.5, 828.2, 118.8), "centro", 2.0, 2.0, 1)
    with pytest.raises(TextoNoCabe) as e:
        maquetar(celda, "J. PÉREZ", fuente, RELLENO, INTERLINEADO)
    ancho = fuente.ancho_mm("J. PÉREZ", 2.0)
    assert str(e.value) == (f"campo 'revisiones.A.aprobo': «J. PÉREZ» mide {ancho:.1f} mm y la "
                            f"celda permite 10.2 mm (altura 2.0 mm)")


def test_no_cabe_ni_reducido_dice_que_es_la_minima(fuente):
    celda = _celda(rect=(0.0, 0.0, 10.0, 10.0), altura=2.5, minima=2.0)
    with pytest.raises(TextoNoCabe, match=r"altura 2\.0 mm, la mínima permitida\)"):
        maquetar(celda, "TEXTO DEMASIADO LARGO", fuente, RELLENO, INTERLINEADO)


def test_demasiadas_lineas(fuente):
    celda = _celda(rect=(0.0, 0.0, 30.0, 30.0), lineas=2)
    with pytest.raises(TextoNoCabe, match=r"campo 'campo': «.*» necesita \d líneas de hasta "
                                          r"28\.8 mm y la celda permite 2"):
        maquetar(celda, "UNO DOS TRES CUATRO CINCO SEIS SIETE OCHO NUEVE DIEZ", fuente, RELLENO,
                 INTERLINEADO)


def test_palabra_mas_ancha_que_la_celda_dice_la_linea(fuente):
    celda = _celda(rect=(0.0, 0.0, 20.0, 30.0), lineas=3)
    with pytest.raises(TextoNoCabe, match=r"campo 'campo', línea 2: «SUPERCALIFRAGILISTICO» mide"):
        maquetar(celda, "UNO SUPERCALIFRAGILISTICO", fuente, RELLENO, INTERLINEADO)


def test_lineas_que_no_caben_a_lo_alto(fuente):
    celda = _celda(rect=(0.0, 0.0, 60.0, 6.0), lineas=3)  # 4,8 mm útiles
    with pytest.raises(TextoNoCabe, match=r"2 líneas ocupan 5\.2 mm de alto y la celda "
                                          r"permite 4\.8 mm"):
        maquetar(celda, ["UNO", "DOS"], fuente, RELLENO, INTERLINEADO)
