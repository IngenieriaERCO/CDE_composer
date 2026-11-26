"""Elementos fijos de la plantilla: lectura en el formato, detección y advertencias."""

import json

import pymupdf
import pytest

from componedor.cli import main
from componedor.elementos_plantilla import detectar_elementos, pdf_verificacion
from componedor.formato import FormatoInvalido, cargar_formato, validar_formato
from componedor.plano import leer_plano
from conftest import componer_pagina_entera as componer_plano  # sin recorte
from conftest import RUTA_A1, crear_paquete_real, crear_plantilla_sintetica, escribir_formato

ROSA = (612.0, 51.0, 652.0, 91.0)
CAPAS = (611.0, 25.0, 660.0, 35.0)


@pytest.fixture
def datos_a1():
    datos = json.loads(RUTA_A1.read_text(encoding="utf-8"))
    datos.pop("plantilla", None)
    return datos


# --- lectura y validación en el formato ----------------------------------------------------

def test_a1_erco_trae_los_elementos_confirmados():
    # Plantilla v2: medidos con detectar-elementos y confirmados a ojo (2026-11-06). Exactos,
    # sin holgura. El recuadro «LAYERS AUTORIZADOS» ya no existe en la v2.
    formato = cargar_formato(RUTA_A1, usar_plantilla=False)
    assert [(e.nombre, e.rect) for e in formato.elementos_plantilla] == [
        ("rosa_vientos", (615.94, 25.21, 654.92, 64.21)),
    ]


def test_sin_elementos_es_lista_vacia(datos_a1):
    datos_a1.pop("elementos_plantilla", None)
    assert validar_formato(datos_a1).elementos_plantilla == ()


def test_elementos_se_leen(datos_a1):
    datos_a1["elementos_plantilla"] = [{"nombre": "rosa_vientos", "rect_mm": list(ROSA)},
                                       {"nombre": "recuadro_capas", "rect_mm": list(CAPAS)}]
    elementos = validar_formato(datos_a1).elementos_plantilla
    assert [(e.nombre, e.rect) for e in elementos] == [("rosa_vientos", ROSA),
                                                        ("recuadro_capas", CAPAS)]


@pytest.mark.parametrize("valor, mensaje", [
    ({"nombre": "x"}, "'elementos_plantilla' debe ser una lista"),
    ([{"nombre": "x"}], r"elementos_plantilla\[0\] debe ser un objeto con exactamente"),
    ([{"nombre": "x", "rect_mm": [1, 2, 3, 4], "otro": 1}], "debe ser un objeto con exactamente"),
    ([{"nombre": "", "rect_mm": [1, 2, 3, 4]}], r"elementos_plantilla\[0\]\.nombre debe ser un texto"),
    ([{"nombre": "a", "rect_mm": [1, 2, 3, 4]}, {"nombre": "a", "rect_mm": [5, 6, 7, 8]}],
     r"elementos_plantilla\[1\]\.nombre 'a' está repetido"),
    ([{"nombre": "a", "rect_mm": [10, 10, 5, 20]}],
     r"El rectángulo de elementos_plantilla\[0\] \('a'\) debe tener ancho y alto positivos"),
    ([{"nombre": "a", "rect_mm": [1, 2, 3]}], "debe ser una lista de 4 números"),
    ([{"nombre": "a", "rect_mm": [800, 10, 900, 20]}], r"se sale de la hoja"),
])
def test_elementos_invalidos(datos_a1, valor, mensaje):
    datos_a1["elementos_plantilla"] = valor
    with pytest.raises(FormatoInvalido, match=mensaje):
        validar_formato(datos_a1)


# --- detección en la plantilla ---------------------------------------------------------------

def _formato_con_plantilla(tmp_path, elementos_mm=(ROSA, CAPAS), **cambios):
    plantilla = crear_plantilla_sintetica(tmp_path / "rotulo.pdf", elementos_mm=elementos_mm)
    return escribir_formato(tmp_path / "formato.json", plantilla=plantilla, **cambios)


def test_detecta_los_elementos_dentro_del_area(tmp_path):
    formato = cargar_formato(_formato_con_plantilla(tmp_path))
    candidatos = detectar_elementos(formato)
    # Rectángulo exacto, sin holgura; ordenados de arriba abajo. El marco, la columna del
    # rótulo y el logo quedan fuera del área de dibujo.
    assert [tuple(round(v, 2) for v in c.rect) for c in candidatos] == [ROSA, CAPAS]
    assert [c.trazos for c in candidatos] == [2, 2]  # el cuadro y su diagonal, agrupados
    assert all(c.imagenes == 0 for c in candidatos)


def test_sin_elementos_y_sin_plantilla(tmp_path):
    formato = cargar_formato(_formato_con_plantilla(tmp_path, elementos_mm=()))
    assert detectar_elementos(formato) == []
    with pytest.raises(ValueError, match="no tiene plantilla"):
        detectar_elementos(cargar_formato(escribir_formato(tmp_path / "sin.json")))


def test_pdf_de_verificacion(tmp_path):
    formato = cargar_formato(_formato_con_plantilla(tmp_path))
    salida = tmp_path / "verificacion.pdf"
    pdf_verificacion(formato, detectar_elementos(formato), salida)
    with pymupdf.open(salida) as doc:
        texto = doc[0].get_text()
    assert "1: X 612.00-652.00, Y 51.00-91.00 mm" in texto
    assert "2: X 611.00-660.00, Y 25.00-35.00 mm" in texto


def test_cli_detectar_elementos(tmp_path, capsys):
    ruta = _formato_con_plantilla(tmp_path)
    salida = tmp_path / "verificacion.pdf"
    assert main(["detectar-elementos", "--formato", str(ruta), "--salida", str(salida)]) == 0
    out = capsys.readouterr().out
    assert "Elementos de la plantilla dentro del área de dibujo (2):" in out
    assert '{"nombre": "elemento_1", "rect_mm": [612.00, 51.00, 652.00, 91.00]}' in out
    assert salida.is_file()
    assert main(["detectar-elementos", "--formato", str(ruta), "--salida", str(salida)]) == 1
    assert "Use --sobrescribir" in capsys.readouterr().err


# --- advertencias de componer ------------------------------------------------------------------

def _plano(carpeta, posicion):
    datos = {"version": 1, "formato": "formato.json", "detalles": [
        {"id": "d1", "manifiesto": "input/a.manifest.json", "posicion_mm": list(posicion)}]}
    ruta = carpeta / "plano.json"
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    return leer_plano(ruta)


@pytest.fixture
def entorno(tmp_path):
    _formato_con_plantilla(tmp_path, elementos_plantilla=[
        {"nombre": "rosa_vientos", "rect_mm": list(ROSA)},
        {"nombre": "recuadro_capas", "rect_mm": list(CAPAS)}])
    crear_paquete_real(tmp_path / "input", "a")  # página 260 x 120; dibujo 37,3..237,3 x 21,3..101,3
    return tmp_path


# Paquete sintético en (x, y): página X x..x+260, Y y..y+120; dibujo X x+37,3..x+237,3,
# Y y+21,3..y+101,3. Rosa: X 612..652, Y 51..91. Capas: X 611..660, Y 25..35.

def test_lejos_de_los_elementos_no_hay_advertencia(entorno):
    r = componer_plano(_plano(entorno, (400.0, 100.0)), entorno / "p.pdf")  # Y 100..220
    assert r.advertencias == []


def test_dibujo_encima_de_un_elemento(entorno):
    # Página Y 40..160: no toca las capas. Dibujo X 437,3..637,3, Y 61,3..141,3: sobre la rosa.
    r = componer_plano(_plano(entorno, (400.0, 40.0)), entorno / "p.pdf")
    assert r.advertencias == [
        "ADVERTENCIA MUY FUERTE: el dibujo 'd1' se monta sobre 'rosa_vientos' de la plantilla "
        "(25.3 x 29.7 mm); además su fondo blanco lo tapa."]


def test_solo_la_pagina_tapa_el_elemento(entorno):
    # Página X 360..620, Y 40..160: toca la rosa (8 x 40 mm); dibujo X 397,3..597,3: no.
    r = componer_plano(_plano(entorno, (360.0, 40.0)), entorno / "p.pdf")
    assert r.advertencias == [
        "ADVERTENCIA FUERTE: el detalle 'd1' tapa 'rosa_vientos' de la plantilla con su fondo "
        "blanco (8.0 x 40.0 mm), aunque su dibujo no lo toca."]
    assert (entorno / "p.pdf").is_file()  # advertencia, no error


def test_dibujo_sobre_dos_elementos(entorno):
    # Página X 400..660, Y 23..143: dibujo X 437,3..637,3, Y 44,3..124,3 -> sobre la rosa;
    # la página (no el dibujo) toca además el recuadro de capas (Y 25..35).
    r = componer_plano(_plano(entorno, (400.0, 23.0)), entorno / "p.pdf")
    assert r.advertencias[0].startswith("ADVERTENCIA MUY FUERTE: el dibujo 'd1' se monta sobre "
                                        "'rosa_vientos' de la plantilla (25.3 x 40.0 mm)")
    assert r.advertencias[1].startswith("ADVERTENCIA FUERTE: el detalle 'd1' tapa "
                                        "'recuadro_capas'")


def test_cli_muestra_las_advertencias(entorno, capsys):
    ruta = entorno / "plano.json"
    _plano(entorno, (400.0, 40.0))  # el dibujo sobre la rosa (la CLI recorta con 1 mm)
    assert main(["componer", str(ruta), "--salida", str(entorno / "p.pdf")]) == 0
    out = capsys.readouterr().out
    assert "Advertencias (1):" in out and "se monta sobre 'rosa_vientos'" in out


def test_con_el_recorte_la_pagina_ya_no_tapa(entorno):
    """Fase 11: con el margen de 1 mm lo que se ve es el dibujo más 1 mm; la página que tocaba
    la rosa (X 360..620) ya no está: no hay advertencia."""
    from componedor.componer import componer_plano as componer_con_recorte

    r = componer_con_recorte(_plano(entorno, (360.0, 40.0)), entorno / "p.pdf")
    assert r.advertencias == []
    assert r.detalles[0].ocupado == pytest.approx((396.3, 60.3, 598.3, 142.3))
