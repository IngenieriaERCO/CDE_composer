import pymupdf
import pytest

from componedor.colocar import (
    DetalleInvalido,
    colocar_detalle,
    posicion_centrada,
    tamano_visible_mm,
)
from componedor.formato import cargar_formato
from componedor.hoja import crear_pagina
from componedor.transformaciones import rect_pdf_a_papel
from conftest import RUTA_A1, TEXTO_DETALLE, crear_detalle_sintetico

TOL_MM = 0.1
X, Y = 100.0, 200.0  # posición de prueba (esquina inferior izquierda), mm de papel


@pytest.fixture
def formato():
    return cargar_formato(RUTA_A1, usar_plantilla=False)


@pytest.fixture
def hoja(formato):
    doc = crear_pagina(formato.ancho_mm, formato.alto_mm)
    yield doc[0]
    doc.close()


def _cerca(obtenido, esperado):
    return all(abs(a - b) <= TOL_MM for a, b in zip(obtenido, esperado))


def _rect_y_marca_mm(page, alto_hoja_mm):
    """Lee de la hoja el rectángulo del detalle y la marca roja, en mm de papel."""
    rects, marcas = [], []
    for d in page.get_drawings():
        if d.get("fill") == (1.0, 0.0, 0.0):
            marcas.append(rect_pdf_a_papel(d["rect"], alto_hoja_mm))
        # La diagonal es un solo segmento; el rectángulo llega como "re" o, girado, 4 segmentos.
        elif len(d["items"]) > 1 or d["items"][0][0] != "l":
            rects.append(rect_pdf_a_papel(d["rect"], alto_hoja_mm))
    assert len(rects) == 1 and len(marcas) == 1
    return rects[0], marcas[0]


def test_posicion_conocida(hoja, formato, detalle):
    ocupado = colocar_detalle(hoja, formato, detalle, (X, Y))
    assert _cerca(ocupado, (X, Y, X + 120, Y + 80))

    rect, _ = _rect_y_marca_mm(hoja, formato.alto_mm)
    assert abs((rect[2] - rect[0]) - 100) <= TOL_MM
    assert abs((rect[3] - rect[1]) - 50) <= TOL_MM
    assert _cerca(rect, (X + 10, Y + 15, X + 110, Y + 65))


def test_centrado_en_la_zona(hoja, formato, detalle):
    ocupado = colocar_detalle(hoja, formato, detalle)  # sin posición -> centrar
    zona = formato.zonas["area_dibujo"]
    centro_zona = ((zona[0] + zona[2]) / 2, (zona[1] + zona[3]) / 2)
    centro_ocupado = ((ocupado[0] + ocupado[2]) / 2, (ocupado[1] + ocupado[3]) / 2)
    assert _cerca(centro_ocupado, centro_zona)
    # El rectángulo de 100 x 50 está centrado en su página, así que también queda centrado.
    rect, _ = _rect_y_marca_mm(hoja, formato.alto_mm)
    assert _cerca(((rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2), centro_zona)


def test_posicion_centrada():
    assert posicion_centrada((120, 80), (0, 0, 200, 100)) == (40, 10)


def test_vector_sin_imagenes_y_texto_como_texto(tmp_path, hoja, formato, detalle):
    colocar_detalle(hoja, formato, detalle, (X, Y))
    salida = tmp_path / "hoja.pdf"
    hoja.parent.save(salida)
    with pymupdf.open(salida) as doc:
        page = doc[0]
        assert page.get_images(full=True) == []
        assert page.get_image_info() == []
        # El detalle entró como Form XObject (show_pdf_page crea un envoltorio "fzFrm0").
        assert any(nombre.startswith("fzFrm") for _, nombre, *_ in page.get_xobjects())
        assert TEXTO_DETALLE in page.get_text()


@pytest.mark.parametrize(
    "rotacion, visible, rect_esperado, marca_esperada",
    [
        # Cálculo a mano: /Rotate gira la página en sentido horario al mostrarla.
        (0, (120, 80), (10, 15, 110, 65), (12, 55, 30, 63)),
        (90, (80, 120), (15, 10, 65, 110), (55, 90, 63, 108)),
        (180, (120, 80), (10, 15, 110, 65), (90, 17, 108, 25)),
        (270, (80, 120), (15, 10, 65, 110), (17, 12, 25, 30)),
    ],
)
def test_origen_con_rotate(tmp_path, hoja, formato, rotacion, visible, rect_esperado,
                           marca_esperada):
    ruta = crear_detalle_sintetico(tmp_path / f"rot{rotacion}.pdf", rotacion=rotacion)
    with pymupdf.open(ruta) as doc:
        assert doc[0].rotation == rotacion
        assert _cerca(tamano_visible_mm(doc[0]), visible)

    ocupado = colocar_detalle(hoja, formato, ruta, (X, Y))
    assert _cerca(ocupado, (X, Y, X + visible[0], Y + visible[1]))

    rect, marca = _rect_y_marca_mm(hoja, formato.alto_mm)
    desplazar = lambda r: (X + r[0], Y + r[1], X + r[2], Y + r[3])  # noqa: E731
    assert _cerca(rect, desplazar(rect_esperado))
    assert _cerca(marca, desplazar(marca_esperada))


def test_origen_con_cropbox(tmp_path, hoja, formato):
    # CropBox de (5, 5) a (115, 75) mm: visible 110 x 70, el rectángulo se corre 5 mm.
    ruta = crear_detalle_sintetico(tmp_path / "crop.pdf", cropbox_mm=(5, 5, 115, 75))
    ocupado = colocar_detalle(hoja, formato, ruta, (X, Y))
    assert _cerca(ocupado, (X, Y, X + 110, Y + 70))
    rect, _ = _rect_y_marca_mm(hoja, formato.alto_mm)
    assert _cerca(rect, (X + 5, Y + 10, X + 105, Y + 60))


def test_detalle_mas_grande_que_la_zona(tmp_path, hoja, formato):
    ruta = crear_detalle_sintetico(tmp_path / "grande.pdf", ancho_mm=700, alto_mm=600)
    with pytest.raises(DetalleInvalido) as e:
        colocar_detalle(hoja, formato, ruta)
    mensaje = str(e.value)
    assert "El detalle (700.0 x 600.0 mm) no cabe en la zona 'area_dibujo' (639.7 x 548.6 mm)" \
        in mensaje
    assert "se pasa 60.3 mm a lo ancho y 51.4 mm a lo alto" in mensaje


def test_posicion_que_se_sale_de_la_zona(hoja, formato, detalle):
    with pytest.raises(DetalleInvalido, match=r"se pasa 57\.6 mm por la derecha"):
        colocar_detalle(hoja, formato, detalle, (600.0, 100.0))


def test_zona_inexistente_y_pagina_inexistente(hoja, formato, detalle):
    with pytest.raises(DetalleInvalido, match="La zona 'patio' no existe"):
        colocar_detalle(hoja, formato, detalle, zona="patio")
    with pytest.raises(DetalleInvalido, match="no existe la página 3"):
        colocar_detalle(hoja, formato, detalle, pagina=3)


def test_detalle_inexistente(tmp_path, hoja, formato):
    with pytest.raises(DetalleInvalido, match="No se encontró el detalle"):
        colocar_detalle(hoja, formato, tmp_path / "no_hay.pdf")
