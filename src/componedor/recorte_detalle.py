"""El recorte de un detalle en la hoja: el dibujo más un margen, no la página entera.

El Exportador entrega cada detalle en una página con un borde blanco alrededor del dibujo
(`margin_mm` de la carga, 5 mm). Ese borde ocupaba espacio del A1. Al componer, la página se
recorta a

    recorte = page_bounds_mm agrandado `margen_mm` por lado, sin salirse de la página

(mm de la página del detalle, origen arriba a la izquierda, Y hacia abajo, como el manifiesto).
El recorte se hace con `show_pdf_page(clip=…)`: el detalle sigue siendo vector, solo se ve
menos página. Con 0 mm el corte cae justo en el borde del dibujo (la mitad del grosor de una
línea del borde puede quedar fuera).

`posicion_mm` del plano sigue siendo la esquina inferior izquierda de la PÁGINA entera del
paquete: el dibujo no se mueve al cambiar el margen, solo cambia lo que se ve. Lo visible en la
hoja es `visible_en_papel`; eso es lo que debe quedar dentro del área de dibujo.
"""

from componedor.cad_a_papel import limites_dibujo_en_papel
from componedor.formato import RectMM

MARGEN_POR_DEFECTO_MM = 1.0
MARGEN_MAXIMO_MM = 50.0


def recorte_pagina(tamano_pagina_mm: tuple[float, float], limites_pagina_mm: RectMM,
                   margen_mm: float) -> RectMM:
    """El rectángulo de la página que se ve (mm de la página, Y abajo)."""
    ancho, alto = tamano_pagina_mm
    x0, y0, x1, y1 = limites_pagina_mm
    return (max(0.0, x0 - margen_mm), max(0.0, y0 - margen_mm),
            min(ancho, x1 + margen_mm), min(alto, y1 + margen_mm))


def visible_en_papel(recorte: RectMM, alto_pagina_mm: float,
                     posicion_mm: tuple[float, float]) -> RectMM:
    """Lo que se ve en la hoja (mm de papel, Y arriba) con la página en `posicion_mm`."""
    return limites_dibujo_en_papel(recorte, alto_pagina_mm, posicion_mm)


def posicion_centrada_recorte(recorte: RectMM, alto_pagina_mm: float,
                              zona: RectMM) -> tuple[float, float]:
    """Esquina inferior izquierda de la PÁGINA que deja lo visible centrado en la zona."""
    x0, y0, x1, y1 = visible_en_papel(recorte, alto_pagina_mm, (0.0, 0.0))
    return ((zona[0] + zona[2]) / 2 - (x0 + x1) / 2, (zona[1] + zona[3]) / 2 - (y0 + y1) / 2)


def tamano_visible(recorte: RectMM) -> tuple[float, float]:
    return recorte[2] - recorte[0], recorte[3] - recorte[1]


def cabe_recortado(tamano_pagina_mm: tuple[float, float], limites_pagina_mm: RectMM,
                   margen_mm: float, zona: RectMM) -> bool:
    """¿Cabe en la zona lo que se ve del detalle (su dibujo más el margen)?"""
    from componedor.colocar import exceso_de_tamano  # aquí: colocar importa pymupdf

    recorte = recorte_pagina(tamano_pagina_mm, limites_pagina_mm, margen_mm)
    return exceso_de_tamano(tamano_visible(recorte), zona) == (0.0, 0.0)


def margen_valido(valor) -> bool:
    """Un margen de 0 a MARGEN_MAXIMO_MM mm (número, no booleano)."""
    return (not isinstance(valor, bool) and isinstance(valor, (int, float))
            and 0 <= valor <= MARGEN_MAXIMO_MM)
