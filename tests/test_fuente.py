"""Fuente del rótulo: altura de mayúsculas (OS/2), medidas y errores claros."""

import struct

import pytest

from componedor.fuente import (
    ALTURA_MAYUSCULAS_POR_DEFECTO,
    FuenteInvalida,
    altura_mayusculas,
    cargar_fuente,
)
from componedor.unidades import mm_a_pt
from conftest import ARIAL, requiere_arial


@requiere_arial
def test_arial_altura_de_mayusculas_leida_de_os2():
    f = cargar_fuente(ARIAL)
    assert f.altura_mayusculas_leida
    assert f.altura_mayusculas == pytest.approx(1467 / 2048)  # sCapHeight / unitsPerEm
    assert f.nombre.startswith("Arial")


@requiere_arial
def test_tamano_en_puntos_para_una_altura_de_mayusculas():
    f = cargar_fuente(ARIAL)
    # 2,5 mm de mayúsculas = 7,087 pt / 0,716 = 9,90 pt de fuente.
    assert f.tamano_pt(2.5) == pytest.approx(mm_a_pt(2.5) / (1467 / 2048))


@requiere_arial
def test_ancho_proporcional_a_la_altura_y_caracteres_faltantes():
    f = cargar_fuente(ARIAL)
    assert f.ancho_mm("ESC: 1:1.000", 5.0) == pytest.approx(2 * f.ancho_mm("ESC: 1:1.000", 2.5))
    assert f.ancho_mm("", 2.5) == 0
    assert f.caracteres_faltantes("DISEÑÓ ÁÉÍÓÚ ü ° ± ²") == []  # tildes, eñe y símbolos
    assert f.caracteres_faltantes("a中b中") == ["中"]
    assert f.glifo("A") > 0 and f.glifo("中") == 0


def _ttf(cap: int, unidades: int = 2048, version_os2: int = 4) -> bytes:
    """TrueType mínimo con solo las tablas head y OS/2 (para leer la altura de mayúsculas)."""
    head = bytearray(54)
    struct.pack_into(">H", head, 18, unidades)
    os2 = bytearray(96)
    struct.pack_into(">H", os2, 0, version_os2)
    struct.pack_into(">h", os2, 88, cap)
    cabecera = struct.pack(">IHHHH", 0x00010000, 2, 0, 0, 0)
    inicio = 12 + 2 * 16
    directorio = (struct.pack(">4sIII", b"OS/2", 0, inicio + len(head), len(os2))
                  + struct.pack(">4sIII", b"head", 0, inicio, len(head)))
    return cabecera + directorio + bytes(head) + bytes(os2)


def test_altura_de_mayusculas_de_las_tablas():
    assert altura_mayusculas(_ttf(1467)) == pytest.approx(1467 / 2048)
    assert altura_mayusculas(_ttf(700, unidades=1000)) == pytest.approx(0.7)
    assert altura_mayusculas(_ttf(1467, version_os2=1)) is None  # OS/2 v1 no trae el dato
    assert altura_mayusculas(_ttf(0)) is None
    assert altura_mayusculas(b"no es una fuente") is None
    assert ALTURA_MAYUSCULAS_POR_DEFECTO == pytest.approx(0.716)


def test_errores_claros(tmp_path):
    with pytest.raises(FuenteInvalida, match="No se encontró la fuente .*rotulo.fuente.archivo"):
        cargar_fuente(tmp_path / "no_existe.ttf")
    coleccion = tmp_path / "cambria.ttc"
    coleccion.write_bytes(b"x")
    with pytest.raises(FuenteInvalida, match=r"\.ttf u \.otf"):
        cargar_fuente(coleccion)
    rota = tmp_path / "rota.ttf"
    rota.write_bytes(b"esto no es una fuente")
    with pytest.raises(FuenteInvalida, match="No se pudo leer la fuente"):
        cargar_fuente(rota)
