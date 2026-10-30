"""Utilidades compartidas por las pruebas.

Las pruebas NO dependen del rótulo real (plantillas/*.pdf no se versiona): usan copias del
JSON del formato sin plantilla o con una plantilla sintética.
"""

import json
from pathlib import Path

import pymupdf
import pytest

from componedor.unidades import mm_a_pt, pt_a_mm

RUTA_A1 = Path(__file__).parent.parent / "formatos" / "A1_ERCO.json"
TEXTO_DETALLE = "DETALLE A"
MARCO_A1 = (12.7, 12.7, 828.3, 581.3)


def escribir_formato(destino: Path, plantilla: Path | None = None, **cambios) -> Path:
    """Copia de A1_ERCO.json sin la plantilla real; opcionalmente con otra plantilla."""
    datos = json.loads(RUTA_A1.read_text(encoding="utf-8"))
    datos.pop("plantilla", None)
    if plantilla is not None:
        datos["plantilla"] = str(plantilla)
    datos.update(cambios)
    destino.write_text(json.dumps(datos), encoding="utf-8")
    return destino


def crear_plantilla_sintetica(ruta: Path, ancho_pt: float = 2384, alto_pt: float = 1684,
                              rotacion: int = 0, marco_mm=MARCO_A1) -> Path:
    """Rótulo de prueba: marco, columna del rótulo y un "logo" (imagen RGB pequeña).

    Por defecto 2384 x 1684 pt (841,02 x 594,08 mm), como redondea AutoCAD el A1.
    Las medidas van en mm de papel (origen inferior izquierdo de la plantilla tal como se
    ve). Con /Rotate 90 o 270 la página se crea vertical y se dibuja de modo que se vea
    horizontal, como un plot de AutoCAD en hoja vertical girada.
    """
    doc = pymupdf.open()
    if rotacion in (90, 270):
        page = doc.new_page(width=alto_pt, height=ancho_pt)
    else:
        page = doc.new_page(width=ancho_pt, height=alto_pt)
    page.set_rotation(rotacion)
    alto_mm = pt_a_mm(alto_pt)

    def r(xmin, ymin, xmax, ymax):  # mm de papel -> coordenadas sin girar de la página
        visible = pymupdf.Rect(mm_a_pt(xmin), mm_a_pt(alto_mm - ymax),
                               mm_a_pt(xmax), mm_a_pt(alto_mm - ymin))
        return visible * page.derotation_matrix

    page.draw_rect(r(*marco_mm), color=(0, 0, 0), width=0.72)
    page.draw_line(r(672.4, 12.7, 672.4, 581.3).tl, r(672.4, 12.7, 672.4, 581.3).br,
                   color=(0, 0, 0), width=0.72)
    logo = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 40, 12), False)
    logo.set_rect(logo.irect, (0, 150, 60))
    page.insert_image(r(761.0, 79.4, 817.2, 96.7), pixmap=logo)
    doc.save(ruta)
    doc.close()
    return ruta


def crear_detalle_sintetico(ruta: Path, ancho_mm: float = 120, alto_mm: float = 80,
                            rotacion: int = 0, cropbox_mm=None) -> Path:
    """PDF de prueba de una página: rectángulo de 100 x 50 mm, diagonal, texto y marca.

    Coordenadas propias de PyMuPDF (pt, Y hacia abajo) en la página de 120 x 80 mm:
    - rectángulo de (10, 15) a (110, 65) mm  -> centrado en la página;
    - diagonal de (10, 15) a (110, 65) mm;
    - texto "DETALLE A";
    - marca de orientación rellena de (12, 17) a (30, 25) mm, en la esquina superior
      izquierda del rectángulo, para distinguir hacia dónde se giró.
    """
    def r(x0, y0, x1, y1):
        return pymupdf.Rect(mm_a_pt(x0), mm_a_pt(y0), mm_a_pt(x1), mm_a_pt(y1))

    doc = pymupdf.open()
    page = doc.new_page(width=mm_a_pt(ancho_mm), height=mm_a_pt(alto_mm))
    page.draw_rect(r(10, 15, 110, 65), color=(0, 0, 0), width=0.7)
    page.draw_line(pymupdf.Point(mm_a_pt(10), mm_a_pt(15)),
                   pymupdf.Point(mm_a_pt(110), mm_a_pt(65)), color=(0, 0, 0), width=0.7)
    page.draw_rect(r(12, 17, 30, 25), color=(1, 0, 0), fill=(1, 0, 0), width=0.3)
    page.insert_text(pymupdf.Point(mm_a_pt(40), mm_a_pt(45)), TEXTO_DETALLE, fontsize=12)
    if cropbox_mm:
        page.set_cropbox(r(*cropbox_mm))
    page.set_rotation(rotacion)
    doc.save(ruta)
    doc.close()
    return ruta


# --- Detalle con matriz cad_to_page sintética (no son datos de ERCO) -----------------------
# Escala 20 mm por unidad CAD (1:50 en metros), Y CAD hacia arriba -> d = -20.
# Coordenadas CAD de millones -> e y f de magnitud ~1e8. Márgenes a propósito distintos de
# 5 mm: la matriz ya los incluye.
X0_CAD, Y0_CAD = 4_900_000.0, 5_100_000.0
MATRIZ_SINTETICA = (20.0, 0.0, 0.0, -20.0, 17.3 - 20 * X0_CAD, 20 * (Y0_CAD + 6) + 18.7)
RECT_CAD = (X0_CAD + 1, Y0_CAD + 2, X0_CAD + 11, Y0_CAD + 6)  # 10 x 4 unidades CAD
PAGINA_CAD_MM = (260.0, 120.0)
LIMITES_RECT_PAGINA_MM = (37.3, 18.7, 237.3, 98.7)  # el rectángulo en la página, Y abajo


def _cad_a_pagina_mm(x, y):
    a, b, c, d, e, f = MATRIZ_SINTETICA
    return a * x + c * y + e, b * x + d * y + f


def crear_detalle_cad(ruta: Path) -> Path:
    """PDF de 260 x 120 mm con fondo blanco (como el exportador) y el rectángulo RECT_CAD
    dibujado con MATRIZ_SINTETICA."""
    doc = pymupdf.open()
    page = doc.new_page(width=mm_a_pt(PAGINA_CAD_MM[0]), height=mm_a_pt(PAGINA_CAD_MM[1]))
    page.draw_rect(page.rect, color=None, fill=(1, 1, 1))  # fondo de página
    x0, y0, x1, y1 = RECT_CAD
    esquinas = [_cad_a_pagina_mm(x, y) for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
    puntos = [pymupdf.Point(mm_a_pt(x), mm_a_pt(y)) for x, y in esquinas]
    page.draw_polyline(puntos + [puntos[0]], color=(0, 0, 0), width=0.5)
    doc.save(ruta)
    doc.close()
    return ruta


def manifiesto_sintetico(**cambios_cad_to_page) -> dict:
    """Manifiesto mínimo con la geometría del detalle de `crear_detalle_cad`."""
    x0, y0, x1, y1 = LIMITES_RECT_PAGINA_MM
    cad_to_page = {"units": "mm", "origin": "top-left", "y_axis": "down",
                   "matrix": list(MATRIZ_SINTETICA)}
    cad_to_page.update(cambios_cad_to_page)
    return {
        "document_type": "cde-detail-manifest",
        "pdf": {
            "page_size_mm": list(PAGINA_CAD_MM),
            "drawing": {
                "page_bounds_mm": {"x0": x0, "y0": y0, "x1": x1, "y1": y1},
                "cad_to_page": cad_to_page,
            },
        },
    }


def escribir_json(ruta: Path, datos: dict) -> Path:
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    return ruta


@pytest.fixture
def detalle(tmp_path):
    """Detalle sintético estándar de 120 x 80 mm sin rotación."""
    return crear_detalle_sintetico(tmp_path / "detalle.pdf")
