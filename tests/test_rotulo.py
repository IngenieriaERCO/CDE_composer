"""Llenar el rótulo: valores del plano, por defecto, ESCALA y REV. calculadas, revisiones en
la fila de su letra y errores con TODOS los problemas."""

from pathlib import Path

import pytest

from componedor.fuente import cargar_fuente
from componedor.rotulo import (
    RotuloInvalido,
    escala_comun,
    preparar_rotulo,
    ultima_revision,
)
from componedor.rotulo_formato import leer_definicion_rotulo
from conftest import ARIAL, requiere_arial, rotulo_a1

ZONA = (672.4, 12.7, 828.3, 581.3)


@pytest.fixture(scope="module")
def definicion():
    return leer_definicion_rotulo(rotulo_a1(), ZONA, Path("."))


@pytest.fixture(scope="module")
def fuente():
    if not ARIAL.is_file():
        pytest.skip("Arial no está instalada")
    return cargar_fuente(ARIAL)


def _textos(preparado) -> dict[str, list[str]]:
    return {t.ruta: [l.texto for l in t.lineas] for t in preparado.textos}


def test_escala_comun_e_indicadas():
    assert escala_comun([50.0, 50.0]) == "1:50"
    assert escala_comun([1000.0]) == "1:1.000"
    assert escala_comun([50.0, 1000.0]) == "INDICADAS"
    assert escala_comun([]) == ""


def test_ultima_revision_por_orden_no_por_llegada():
    orden = ("A", "B", "C", "0")  # A1 ERCO: la emisión final «0» manda sobre A, B, C
    assert ultima_revision(["0", "A", "B"], orden) == "0"  # 0 + A + B
    assert ultima_revision(["B", "0", "A"], orden) == "0"  # mismo caso, otro orden de llegada
    assert ultima_revision(["A", "B"], orden) == "B"  # solo A + B
    assert ultima_revision(["B", "A"], orden) == "B"
    assert ultima_revision(["0"], orden) == "0"  # solo 0
    assert ultima_revision(["C", "A"], orden) == "C"
    assert ultima_revision(["A"], orden) == "A"
    assert ultima_revision([], orden) == ""  # ninguna


@requiere_arial
def test_sin_valores_quedan_defectos_y_calculados(definicion, fuente):
    p = preparar_rotulo(definicion, None, [50.0], fuente)
    assert _textos(p) == {"localizacion_escala": ["DEFINIR"], "escala": ["1:50"]}
    assert p.valores["rev"] == "" and p.valores["titulo"] == ""
    assert p.advertencias == []


@requiere_arial
def test_valores_simples_tablas_y_calculados(definicion, fuente):
    valores = {
        "titulo": "PLANTA GENERAL",
        "localizacion_escala": "1:25.000",
        "hoja": 2, "de": "5", "no_plano": "ERCO-PL-001",
        "revisiones": [
            {"ver": "B", "fecha": "2026-11-06", "descripcion": "AJUSTE"},
            {"ver": "0", "fecha": "2026-10-01", "descripcion": "EMISIÓN"},
        ],
        "firmas": {"reviso": {"nombre": ["ANDRÉS GÓMEZ", "(DIRECTOR)"], "fecha": "2026-11-06"},
                   "dibujo": {"nombre": "LANP", "firma": "L.N."}},
    }
    p = preparar_rotulo(definicion, valores, [50.0, 1000.0], fuente)
    t = _textos(p)
    assert t["titulo"] == ["PLANTA GENERAL"]
    assert t["hoja"] == ["2"] and t["de"] == ["5"]
    assert t["escala"] == ["INDICADAS"]
    assert t["rev"] == ["0"]  # hay emisión final «0»: manda sobre B
    # Cada revisión en la fila de SU letra, con la letra en la columna VER.
    assert t["revisiones.B.ver"] == ["B"] and t["revisiones.B.descripcion"] == ["AJUSTE"]
    assert t["revisiones.0.ver"] == ["0"] and t["revisiones.0.fecha"] == ["2026-10-01"]
    assert not any(r.startswith(("revisiones.A.", "revisiones.C.")) for r in t)
    assert t["firmas.reviso.nombre"] == ["ANDRÉS GÓMEZ", "(DIRECTOR)"]
    assert t["firmas.dibujo.firma"] == ["L.N."]
    # Una revisión de fila B queda en la Y de la fila B (118,8 a 125,2), centrada en alto.
    (fila_b,) = [x for x in p.textos if x.ruta == "revisiones.B.fecha"]
    assert fila_b.lineas[0].base_mm[1] == pytest.approx((118.8 + 125.2) / 2 - 1.0)
    assert p.valores["localizacion_escala"] == "1:25.000"


@requiere_arial
def test_valor_vacio_o_null_deja_la_celda_vacia(definicion, fuente):
    p = preparar_rotulo(definicion, {"localizacion_escala": "", "titulo": None}, [50.0], fuente)
    assert "localizacion_escala" not in _textos(p) and "titulo" not in _textos(p)


@requiere_arial
def test_titulo_largo_se_parte_y_si_hace_falta_se_reduce_con_advertencia(definicion, fuente):
    palabras = ("PARQUE SOLAR FOTOVOLTAICO VÍA DE ACCESO PRINCIPAL PLANTA GENERAL PERFIL "
                "LONGITUDINAL Y SECCIONES TÍPICAS DE PAVIMENTO CUNETAS Y OBRAS DE DRENAJE "
                "ALCANTARILLAS BOX CULVERT EN CONCRETO REFORZADO MUROS DE CONTENCIÓN").split() * 3
    # Se agregan palabras hasta que a 2,5 mm ya no quepa en 3 líneas (pero sí reducido).
    for n in range(10, len(palabras)):
        p = preparar_rotulo(definicion, {"titulo": " ".join(palabras[:n])}, [50.0], fuente)
        (titulo,) = [x for x in p.textos if x.ruta == "titulo"]
        if titulo.reducido_desde is not None:
            break
    assert len(titulo.lineas) == 3
    assert titulo.altura_mm < 2.5 and titulo.reducido_desde == 2.5
    assert p.advertencias == [
        f"Advertencia: en el rótulo, el campo 'titulo' se escribió a {titulo.altura_mm:.1f} mm "
        f"de altura (pedida 2.5 mm) para que quepa en su celda."]


@requiere_arial
def test_todos_los_problemas_juntos(definicion, fuente):
    valores = {
        "titulos": "x",  # error de tipeo
        "escala": "1:50",  # calculado
        "rev": "A",  # calculado
        "hoja": True,
        "no_plano": "ERCO\nPL",
        "este": ["a", "b"],  # lista en celda de una línea
        "titulo": "X" * 400,
        "revisiones": [{"ver": "A", "fecha": "1"}, {"ver": "A"}, {"ver": "D"}, {"ver": 0, "firma": "x"}],
        "firmas": {"revisor": {"nombre": "x"}, "dibujo": {"nombre": "LANP", "cedula": "1"}},
        "de": "中国",
    }
    with pytest.raises(RotuloInvalido) as e:
        preparar_rotulo(definicion, valores, [50.0], fuente)
    m = str(e.value)
    for esperado in [
        "- rotulo.titulos: campo no reconocido (campos válidos: localizacion_escala, este,",
        "- rotulo.escala: se calcula automáticamente (la escala de los detalles, o INDICADAS si "
        "son distintas); no se escribe en el plano",
        "- rotulo.rev: se calcula automáticamente (0 si hay emisión final; si no, la mayor "
        "letra llena entre C, B y A); no se escribe en el plano",
        "- rotulo.hoja: se esperaba un texto; tiene un booleano (true)",
        "- rotulo.no_plano: la celda es de una sola línea y el texto trae un salto de línea",
        "- rotulo.este: se esperaba un texto; tiene una lista",
        "- rotulo.revisiones[1].ver: la revisión 'A' está repetida (ya está en rotulo.revisiones[0])",
        "- rotulo.revisiones[2].ver: se esperaba una de A, B, C, 0; tiene texto 'D'",
        "- rotulo.revisiones[3].firma: campo no reconocido",
        "- rotulo.firmas.revisor: fila no reconocida (filas válidas: dibujo, diseno, reviso, aprobo)",
        "- rotulo.firmas.dibujo.cedula: campo no reconocido",
        "- campo 'titulo': «XXXX",
        "- campo 'de': la fuente Arial",
    ]:
        assert esperado in m, esperado
    assert m.startswith("El rótulo tiene ")


@requiere_arial
def test_revision_con_ver_numerico_y_tipos_de_tabla(definicion, fuente):
    p = preparar_rotulo(definicion, {"revisiones": [{"ver": 0, "fecha": "2026"}]}, [50.0], fuente)
    assert _textos(p)["revisiones.0.ver"] == ["0"] and _textos(p)["rev"] == ["0"]
    with pytest.raises(RotuloInvalido, match=r"rotulo.revisiones: se esperaba una lista"):
        preparar_rotulo(definicion, {"revisiones": {"ver": "A"}}, [50.0], fuente)
    with pytest.raises(RotuloInvalido, match=r"rotulo.firmas: se esperaba un objeto con las filas"):
        preparar_rotulo(definicion, {"firmas": ["LANP"]}, [50.0], fuente)
