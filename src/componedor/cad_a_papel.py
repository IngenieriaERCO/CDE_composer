"""Transformaciones CAD -> página del detalle -> papel.

El manifiesto del exportador trae en `pdf.drawing.cad_to_page` la matriz [a, b, c, d, e, f]
que lleva un punto CAD (unidades del dibujo, p. ej. metros) a mm de la PÁGINA del PDF del
detalle (origen arriba-izquierda, Y hacia abajo):

    x_pagina = a*X + c*Y + e
    y_pagina = b*X + d*Y + f

La matriz ya incluye la escala (1:50 en metros -> a = 20, d = -20), el margen y el
centrado del dibujo en la página: aquí NO se supone ningún margen fijo.

La matriz se lee del manifiesto con `manifiesto.leer_manifiesto` (Manifiesto.pdf.dibujo).
Paso página -> papel: `transformaciones.punto_pagina_a_papel` (único lugar donde se
invierte Y).
"""

from dataclasses import dataclass

from componedor.formato import RectMM
from componedor.transformaciones import PuntoMM, punto_pagina_a_papel


class MatrizNoInvertible(ValueError):
    """La matriz cad_to_page no se puede invertir."""


@dataclass(frozen=True)
class MatrizCad:
    """Matriz afín CAD -> página del detalle (mm, Y abajo), formato [a, b, c, d, e, f]."""

    a: float
    b: float
    c: float
    d: float
    e: float
    f: float

    @property
    def determinante(self) -> float:
        return self.a * self.d - self.b * self.c

    def cad_a_pagina(self, x: float, y: float) -> PuntoMM:
        """Punto CAD -> mm de la página del detalle (origen arriba-izquierda, Y abajo)."""
        return self.a * x + self.c * y + self.e, self.b * x + self.d * y + self.f

    def pagina_a_cad(self, x_mm: float, y_mm: float) -> PuntoMM:
        """mm de la página del detalle -> punto CAD (inversa de `cad_a_pagina`)."""
        det = self.determinante
        escala = max(abs(self.a), abs(self.b), abs(self.c), abs(self.d))
        if escala == 0 or abs(det) <= 1e-12 * escala * escala:
            raise MatrizNoInvertible(
                f"La matriz cad_to_page [{self.a}, {self.b}, {self.c}, {self.d}, {self.e}, "
                f"{self.f}] no es invertible (determinante a*d - b*c = {det}): no se puede "
                f"pasar de la página a coordenadas CAD. Revise el manifiesto del exportador."
            )
        dx, dy = x_mm - self.e, y_mm - self.f
        return (self.d * dx - self.c * dy) / det, (-self.b * dx + self.a * dy) / det


def cad_a_papel(x: float, y: float, origen_detalle_mm: PuntoMM, alto_pagina_mm: float,
                matriz: MatrizCad) -> PuntoMM:
    """Punto CAD -> mm de papel.

    `origen_detalle_mm` es dónde quedó en la hoja la esquina inferior izquierda de la
    página del detalle; `alto_pagina_mm` es el alto de esa página.
    """
    x_pag, y_pag = matriz.cad_a_pagina(x, y)
    return punto_pagina_a_papel(x_pag, y_pag, alto_pagina_mm, origen_detalle_mm)


def origen_para_ancla(punto_cad: PuntoMM, punto_papel: PuntoMM, matriz: MatrizCad,
                      alto_pagina_mm: float) -> PuntoMM:
    """Esquina inferior izquierda del detalle que hace caer `punto_cad` en `punto_papel`."""
    relativo = punto_pagina_a_papel(*matriz.cad_a_pagina(*punto_cad), alto_pagina_mm)
    return punto_papel[0] - relativo[0], punto_papel[1] - relativo[1]


def limites_dibujo_en_papel(limites_pagina_mm: RectMM, alto_pagina_mm: float,
                            origen_detalle_mm: PuntoMM) -> RectMM:
    """page_bounds_mm (página, Y abajo) trasladado a mm de papel (xmin, ymin, xmax, ymax)."""
    x0, y0, x1, y1 = limites_pagina_mm
    xmin, ymin = punto_pagina_a_papel(x0, y1, alto_pagina_mm, origen_detalle_mm)  # abajo-izq.
    xmax, ymax = punto_pagina_a_papel(x1, y0, alto_pagina_mm, origen_detalle_mm)  # arriba-der.
    return xmin, ymin, xmax, ymax
