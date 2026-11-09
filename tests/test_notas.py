"""NOTAS del rótulo (subfase 4.2a): leer los .txt, numerar, sangría francesa, bloque arriba,
reducción conjunta, errores claros y verificación en el PDF."""

from dataclasses import replace
from pathlib import Path

import pymupdf
import pytest

from componedor.fuente import cargar_fuente
from componedor.hoja import crear_pagina
from componedor.maquetacion import Linea, TextoNoCabe
from componedor.notas import (
    Nota,
    leer_archivo_notas,
    leer_notas,
    maquetar_notas,
    verificar_notas,
)
from componedor.rotulo import RotuloInvalido, preparar_rotulo
from componedor.rotulo_formato import CampoNotas, Celda, leer_definicion_rotulo
from componedor.textos_pdf import escribir_textos, verificar_textos
from conftest import ARIAL, requiere_arial, rotulo_a1

CELDA = (673.2, 271.3, 827.4, 419.3)  # NOTAS del rótulo v2
ALTO = 594.0
RELLENO, INTERLINEADO = 0.6, 1.6


def _campo(rect=CELDA, altura=1.8, minima=1.5, separacion=0.5):
    return CampoNotas("notas", Celda("notas", rect, "izq", altura, minima, 1), separacion)


@pytest.fixture(scope="module")
def fuente():
    if not ARIAL.is_file():
        pytest.skip("Arial no está instalada")
    return cargar_fuente(ARIAL)


def _txt(carpeta: Path, nombre: str, texto: str, codificacion="utf-8") -> Path:
    ruta = carpeta / nombre
    ruta.write_bytes(texto.encode(codificacion))
    return ruta


# --- leer ------------------------------------------------------------------------------------

def test_archivo_una_nota_por_linea_sin_blancos_ni_comentarios(tmp_path):
    ruta = _txt(tmp_path, "generales.txt",
                "# Notas generales\n\nLAS COTAS ESTÁN EN METROS.\n   \n  # otro comentario\n"
                "3. LAS ELEVACIONES   REFERIDAS AL DATUM.\n4) VER PLANO 2.\n3.5 M DE ANCHO.\n")
    notas, avisos, problemas = leer_archivo_notas(ruta)
    assert problemas == []
    assert [n.texto for n in notas] == ["LAS COTAS ESTÁN EN METROS.",
                                        "LAS ELEVACIONES REFERIDAS AL DATUM.", "VER PLANO 2.",
                                        "3.5 M DE ANCHO."]  # "3.5 M" no es un número de nota
    assert [n.origen for n in notas] == ["generales.txt, línea 3", "generales.txt, línea 6",
                                         "generales.txt, línea 7", "generales.txt, línea 8"]
    assert avisos == [
        "Advertencia: la nota de generales.txt, línea 6 traía su propio número «3.»; se quitó: "
        "el componedor numera las notas solo.",
        "Advertencia: la nota de generales.txt, línea 7 traía su propio número «4)»; se quitó: "
        "el componedor numera las notas solo."]


def test_archivo_con_bom_y_saltos_windows(tmp_path):
    ruta = _txt(tmp_path, "a.txt", "﻿PRIMERA NOTA.\r\nSEGUNDA NOTA.\r\n")
    notas, _, problemas = leer_archivo_notas(ruta)
    assert problemas == [] and [n.texto for n in notas] == ["PRIMERA NOTA.", "SEGUNDA NOTA."]


def test_archivo_inexistente_no_utf8_o_vacio(tmp_path):
    assert "no se encontró el archivo de notas" in leer_archivo_notas(tmp_path / "x.txt")[2][0]
    ansi = _txt(tmp_path, "ansi.txt", "DISEÑO DE VÍA.\n", codificacion="cp1252")
    # «Ñ» en cp1252 es un solo byte (0xD1), inválido en UTF-8: posición 4 de "DISEÑO".
    assert "no está en UTF-8 (byte inválido en la posición 4)" in leer_archivo_notas(ansi)[2][0]
    vacio = _txt(tmp_path, "vacio.txt", "# solo comentarios\n\n")
    assert "no tiene notas (solo líneas en blanco o comentarios con #)" in \
        leer_archivo_notas(vacio)[2][0]


def test_archivos_primero_y_adicionales_despues(tmp_path):
    _txt(tmp_path, "a.txt", "A1.\nA2.\n")
    _txt(tmp_path, "b.txt", "B1.\n")
    notas, avisos, problemas = leer_notas(
        {"archivos": ["a.txt", "b.txt"], "adicionales": ["EXTRA 1.", "  ", "2. EXTRA 2."]},
        tmp_path)
    assert problemas == []
    assert [n.texto for n in notas] == ["A1.", "A2.", "B1.", "EXTRA 1.", "EXTRA 2."]
    assert notas[4].origen == "adicionales[2]" and len(avisos) == 1


def test_valor_de_notas_invalido_junta_todos_los_problemas(tmp_path):
    _, _, problemas = leer_notas({"archivos": ["no_existe.txt", 3], "adicional": [],
                                  "adicionales": ["UNA\nDOS"]}, tmp_path)
    assert problemas == [
        "rotulo.notas.adicional: campo no reconocido (campos válidos: adicionales, archivos)",
        "rotulo.notas.archivos: se esperaba una lista de textos; tiene una lista con elementos "
        "que no son texto",
        "rotulo.notas.adicionales[0]: una nota adicional va en una sola línea (trae un salto de "
        "línea); para varias notas use varios textos en la lista"]
    assert "se esperaba {" in leer_notas(["X"], tmp_path)[2][0]


# --- acomodar en la celda --------------------------------------------------------------------

@requiere_arial
def test_numeradas_arriba_con_sangria_francesa_y_medio_renglon(fuente):
    larga = "LAS COTAS ESTÁN EN METROS Y LAS ELEVACIONES REFERIDAS AL DATUM " * 3
    notas = [Nota(larga.strip(), "a"), Nota("CORTA.", "b")]
    m = maquetar_notas(_campo(), notas, fuente, RELLENO, INTERLINEADO)
    assert m.altura_mm == 1.8 and m.reducido_desde is None
    primera, segunda = m.textos
    numero, *texto = primera.lineas
    assert numero.texto == "1." and segunda.lineas[0].texto == "2."
    assert len(texto) >= 2  # la nota larga se partió
    # Bloque pegado arriba: mayúsculas de la 1.ª línea con su tope en 419,3 - 0,6.
    assert numero.base_mm == pytest.approx((673.8, 419.3 - 0.6 - 1.8))
    assert texto[0].base_mm[1] == pytest.approx(numero.base_mm[1])  # número y texto, misma base
    sangria = fuente.ancho_mm("2. ", 1.8)
    assert all(l.base_mm[0] == pytest.approx(673.8 + sangria) for l in texto)  # sangría francesa
    paso = 1.6 * 1.8
    bases = [l.base_mm[1] for l in texto]
    assert [a - b for a, b in zip(bases, bases[1:])] == pytest.approx([paso] * (len(bases) - 1))
    # Entre la última línea de la nota 1 y la nota 2: un renglón más medio renglón.
    assert bases[-1] - segunda.lineas[0].base_mm[1] == pytest.approx(paso * 1.5)
    assert m.lineas == len(texto) + 1
    assert all(t.celda_mm == CELDA for t in m.textos)


@requiere_arial
def test_sangria_segun_el_numero_mas_largo(fuente):
    m = maquetar_notas(_campo(), [Nota(f"NOTA {i}.", "x") for i in range(12)], fuente, RELLENO,
                       INTERLINEADO)
    sangria = fuente.ancho_mm("12. ", 1.8)
    assert all(t.lineas[1].base_mm[0] == pytest.approx(673.8 + sangria) for t in m.textos)
    assert [t.lineas[0].texto for t in m.textos] == [f"{k}." for k in range(1, 13)]


@requiere_arial
def test_reduccion_conjunta_hasta_1_5(fuente):
    # 40 notas cortas (40 líneas + 39 medios renglones): a 1,8 mm no caben; reducidas, sí.
    notas = [Nota(f"NOTA CORTA NÚMERO {i}.", "x") for i in range(1, 41)]
    m = maquetar_notas(_campo(), notas, fuente, RELLENO, INTERLINEADO)
    assert m.reducido_desde == 1.8 and 1.5 <= m.altura_mm < 1.8
    assert all(t.altura_mm == m.altura_mm for t in m.textos)  # todas a la misma altura
    ultima = m.textos[-1].lineas[-1].base_mm[1]
    assert ultima >= 271.3 + 0.6 - 1e-6  # la última base no baja del piso de la celda


@requiere_arial
def test_no_caben_ni_a_1_5_dice_desde_que_nota(fuente):
    notas = [Nota(f"NOTA CORTA NÚMERO {i}.", f"generales.txt, línea {i}") for i in range(1, 61)]
    with pytest.raises(TextoNoCabe) as e:
        maquetar_notas(_campo(), notas, fuente, RELLENO, INTERLINEADO)
    m = str(e.value)
    assert m.startswith("campo 'notas': 60 notas (60 líneas a 1.5 mm (la mínima permitida)) "
                        "ocupan ")
    assert "y la celda permite 146.8 mm; no caben desde la nota 4" in m
    assert "(generales.txt, línea 4" in m and "«NOTA CORTA NÚMERO 4" in m


@requiere_arial
def test_palabra_mas_ancha_que_la_celda(fuente):
    campo = _campo(rect=(673.2, 271.3, 700.0, 419.3))
    with pytest.raises(TextoNoCabe, match=r"campo 'notas', nota 1 \(a\): «SUPERCALIFRAGILISTICO»"
                                          r" mide .* y el ancho para el texto de las notas es"):
        maquetar_notas(campo, [Nota("SUPERCALIFRAGILISTICO", "a")], fuente, RELLENO, INTERLINEADO)


@requiere_arial
def test_sin_notas_no_escribe_nada(fuente):
    assert maquetar_notas(_campo(), [], fuente, RELLENO, INTERLINEADO).textos == []


# --- en el rótulo ----------------------------------------------------------------------------

@requiere_arial
def test_preparar_rotulo_con_notas_y_todos_los_problemas(fuente, tmp_path):
    definicion = leer_definicion_rotulo(rotulo_a1(), (672.4, 12.7, 828.3, 581.3), Path("."))
    _txt(tmp_path, "a.txt", "PRIMERA.\nSEGUNDA.\n")
    p = preparar_rotulo(definicion, {"notas": {"archivos": ["a.txt"],
                                               "adicionales": ["TERCERA."]}}, [50.0], fuente,
                        tmp_path)
    assert [t.lineas[0].texto for t in p.textos if t.ruta.startswith("notas.")] == ["1.", "2.", "3."]
    assert p.valores["notas"] == "3 nota(s)" and p.notas.lineas == 3
    _txt(tmp_path, "ansi.txt", "DISEÑO.\n", codificacion="cp1252")
    with pytest.raises(RotuloInvalido) as e:
        preparar_rotulo(definicion, {"notas": {
            "archivos": ["no_existe.txt", "ansi.txt"], "adicionales": ["中文 NOTA."]}},
            [50.0], fuente, tmp_path)
    m = str(e.value)
    assert m.startswith("El rótulo tiene 3 problemas")  # todos juntos
    assert "no se encontró el archivo de notas" in m and "no está en UTF-8" in m
    assert "rotulo.notas: la nota 1 (adicionales[0]) tiene caracteres que la fuente" in m


# --- verificación en el PDF ------------------------------------------------------------------

def _pdf(textos, fuente, tmp_path):
    doc = crear_pagina(841, ALTO)
    escribir_textos(doc[0], textos, fuente, ALTO)
    ruta = tmp_path / "n.pdf"
    doc.save(ruta)
    doc.close()
    return pymupdf.open(ruta)


@requiere_arial
def test_verificar_notas_en_el_pdf(fuente, tmp_path):
    larga = "UNA NOTA BASTANTE LARGA QUE OCUPA MÁS DE UNA LÍNEA EN LA CELDA DE NOTAS " * 3
    m = maquetar_notas(_campo(), [Nota(larga, "a"), Nota("CORTA.", "b"), Nota("OTRA.", "c")],
                       fuente, RELLENO, INTERLINEADO)
    with _pdf(m.textos, fuente, tmp_path) as d:
        assert verificar_textos(d[0], m.textos, ALTO) == []  # posición y dentro de la celda
        assert verificar_notas(d[0], m, ALTO) == []
        # Se esperaba una línea más de las que hay: no cuadra el conteo.
        de_mas = replace(m, textos=m.textos[:-1] + [replace(m.textos[-1], lineas=(
            *m.textos[-1].lineas, Linea("FANTASMA.", (700.0, 300.0), 15.0)))])
        assert verificar_notas(d[0], de_mas, ALTO) == [
            f"notas: se escribieron {m.lineas + 1} líneas y en la celda del PDF se leen "
            f"{m.lineas}"]


@requiere_arial
def test_verificar_notas_detecta_numeracion_con_saltos(fuente, tmp_path):
    m = maquetar_notas(_campo(), [Nota("A.", "a"), Nota("B.", "b"), Nota("C.", "c")], fuente,
                       RELLENO, INTERLINEADO)
    # Se escribe la tercera con el número 4 (salto): la verificación lo detecta.
    tercera = m.textos[2]
    salto = replace(tercera, lineas=(replace(tercera.lineas[0], texto="4."), *tercera.lineas[1:]))
    with _pdf(m.textos[:2] + [salto], fuente, tmp_path) as d:
        assert verificar_notas(d[0], m, ALTO) == [
            "notas: la numeración leída en el PDF es ['1.', '2.', '4.'] y debía ser 1. a 3. "
            "sin saltos"]
