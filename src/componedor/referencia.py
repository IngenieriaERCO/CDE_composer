"""Detalle de referencia sintético para validar la composición.

Se genera EN MEMORIA (no lee archivos) un PDF de detalle como los del exportador, con
una matriz cad_to_page conocida, escala 1:50 en metros (a = 20, d = -20) y coordenadas
CAD INVENTADAS de millones (e y f de magnitud ~1e8). Contiene:

- fondo blanco de página completa (como el exportador);
- cuadrado de 5 x 5 m CAD  -> debe medir 100 x 100 mm en papel;
- rectángulo de 5 x 2 m CAD -> 100 x 40 mm;
- una diagonal (encima del rectángulo) y el texto «REFERENCIA 1:50» como texto real;
- marca de orientación: rectángulo rojo relleno de 1 x 0,25 m en la esquina superior
  izquierda del cuadrado. Un giro o un espejo la mueve a otra esquina.

Márgenes de la página a propósito asimétricos (12,5 / 17,5 / 9 / 11 mm): la matriz los
incluye, no se supone un margen fijo.
"""

from dataclasses import dataclass

import pymupdf

from componedor.cad_a_papel import MatrizCad
from componedor.formato import RectMM
from componedor.unidades import mm_a_pt

ESCALA = 50  # 1:50
MM_POR_UNIDAD = 1000 / ESCALA  # metros CAD -> mm de papel
TEXTO = "REFERENCIA 1:50"
COLOR_MARCA = (1.0, 0.0, 0.0)

# Coordenadas CAD inventadas (no son de ningún proyecto).
X0, Y0 = 5_000_000.0, 6_000_000.0
CUADRADO_CAD = (X0 + 1, Y0 + 1, X0 + 6, Y0 + 6)
RECTANGULO_CAD = (X0 + 8, Y0 + 1, X0 + 13, Y0 + 3)
DIAGONAL_CAD = ((X0 + 8, Y0 + 4), (X0 + 13, Y0 + 6))
MARCA_CAD = (X0 + 1.25, Y0 + 5.25, X0 + 2.25, Y0 + 5.5)
TEXTO_CAD = (X0 + 8, Y0 + 3.5)  # línea base del texto

PAGINA_MM = (270.0, 120.0)
MARGEN_IZQUIERDO_MM, MARGEN_SUPERIOR_MM = 12.5, 9.0


@dataclass(frozen=True)
class DetalleReferencia:
    """El PDF en memoria y los datos que traería su manifiesto."""

    doc: pymupdf.Document
    matriz: MatrizCad
    ancho_pagina_mm: float
    alto_pagina_mm: float
    limites_pagina_mm: RectMM  # como page_bounds_mm: mm de página, Y abajo


def matriz_referencia() -> MatrizCad:
    """Matriz CAD (m) -> página (mm, Y abajo) del detalle de referencia."""
    a = MM_POR_UNIDAD
    e = MARGEN_IZQUIERDO_MM - a * CUADRADO_CAD[0]  # X mínima del dibujo -> margen izquierdo
    f = MARGEN_SUPERIOR_MM + a * CUADRADO_CAD[3]  # Y máxima del dibujo -> margen superior
    return MatrizCad(a, 0.0, 0.0, -a, e, f)


def generar_detalle_referencia(factor_error: float = 1.0) -> DetalleReferencia:
    """Crea en memoria el PDF de referencia. El llamador debe cerrar `doc`.

    `factor_error` es SOLO para pruebas negativas: dibuja el contenido escalado por ese
    factor (respecto de la esquina inferior izquierda del cuadrado) mientras la matriz
    declarada sigue siendo la correcta.
    """
    matriz = matriz_referencia()
    base = matriz.cad_a_pagina(CUADRADO_CAD[0], CUADRADO_CAD[1])

    def punto(x_cad: float, y_cad: float) -> pymupdf.Point:
        x, y = matriz.cad_a_pagina(x_cad, y_cad)
        x = base[0] + (x - base[0]) * factor_error
        y = base[1] + (y - base[1]) * factor_error
        return pymupdf.Point(mm_a_pt(x), mm_a_pt(y))

    def rect(r: RectMM) -> pymupdf.Rect:
        return pymupdf.Rect(punto(r[0], r[3]), punto(r[2], r[1]))  # arriba-izq., abajo-der.

    doc = pymupdf.open()
    page = doc.new_page(width=mm_a_pt(PAGINA_MM[0]), height=mm_a_pt(PAGINA_MM[1]))
    page.draw_rect(page.rect, color=None, fill=(1, 1, 1))  # fondo, como el exportador
    page.draw_rect(rect(CUADRADO_CAD), color=(0, 0, 0), width=0.5)
    page.draw_rect(rect(RECTANGULO_CAD), color=(0, 0, 0), width=0.5)
    page.draw_line(punto(*DIAGONAL_CAD[0]), punto(*DIAGONAL_CAD[1]), color=(0, 0, 0), width=0.5)
    page.draw_rect(rect(MARCA_CAD), color=None, fill=COLOR_MARCA)
    page.insert_text(punto(*TEXTO_CAD), TEXTO, fontsize=10, fontname="helv")

    x0, y0 = matriz.cad_a_pagina(CUADRADO_CAD[0], CUADRADO_CAD[3])
    x1, y1 = matriz.cad_a_pagina(RECTANGULO_CAD[2], RECTANGULO_CAD[1])
    return DetalleReferencia(
        doc=doc,
        matriz=matriz,
        ancho_pagina_mm=PAGINA_MM[0],
        alto_pagina_mm=PAGINA_MM[1],
        limites_pagina_mm=(x0, y0, x1, y1),
    )
