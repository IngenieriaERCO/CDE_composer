"""Transformaciones CAD -> página del detalle -> papel.

El manifiesto del exportador trae en `pdf.drawing.cad_to_page` la matriz [a, b, c, d, e, f]
que lleva un punto CAD (unidades del dibujo, p. ej. metros) a mm de la PÁGINA del PDF del
detalle (origen arriba-izquierda, Y hacia abajo):

    x_pagina = a*X + c*Y + e
    y_pagina = b*X + d*Y + f

La matriz ya incluye la escala (1:50 en metros -> a = 20, d = -20), el margen y el
centrado del dibujo en la página: aquí NO se supone ningún margen fijo.

Paso página -> papel: `transformaciones.punto_pagina_a_papel` (único lugar donde se
invierte Y).
"""

import json
import math
from dataclasses import dataclass
from pathlib import Path

from componedor.formato import RectMM
from componedor.transformaciones import PuntoMM, punto_pagina_a_papel


class ManifiestoInvalido(ValueError):
    """El manifiesto no trae la geometría esperada."""


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


@dataclass(frozen=True)
class GeometriaManifiesto:
    """Lo único que esta fase lee del manifiesto."""

    ancho_pagina_mm: float
    alto_pagina_mm: float
    matriz: MatrizCad
    limites_pagina_mm: RectMM  # page_bounds_mm (x0, y0, x1, y1): mm de página, Y abajo


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


def limites_dibujo_en_papel(geometria: GeometriaManifiesto, origen_detalle_mm: PuntoMM) -> RectMM:
    """page_bounds_mm (página, Y abajo) trasladado a mm de papel (xmin, ymin, xmax, ymax)."""
    x0, y0, x1, y1 = geometria.limites_pagina_mm
    alto = geometria.alto_pagina_mm
    xmin, ymin = punto_pagina_a_papel(x0, y1, alto, origen_detalle_mm)  # abajo-izquierda
    xmax, ymax = punto_pagina_a_papel(x1, y0, alto, origen_detalle_mm)  # arriba-derecha
    return xmin, ymin, xmax, ymax


def leer_geometria_manifiesto(ruta: Path | str) -> GeometriaManifiesto:
    """Lee SOLO pdf.page_size_mm, pdf.drawing.cad_to_page y pdf.drawing.page_bounds_mm.

    Lectura mínima y provisional: la Fase 2 la reemplazará por el importador completo del
    manifiesto (hash del PDF, versión de esquema, unidades y escala, coherencia, etc.).
    """
    ruta = Path(ruta)
    if not ruta.exists():
        raise ManifiestoInvalido(f"No se encontró el manifiesto '{ruta}'.")
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ManifiestoInvalido(f"El manifiesto '{ruta}' no es un JSON válido: {e}") from e

    def campo(camino: str):
        valor = datos
        for parte in camino.split("."):
            if not isinstance(valor, dict) or parte not in valor:
                raise ManifiestoInvalido(f"Falta el campo '{camino}' en el manifiesto '{ruta}'.")
            valor = valor[parte]
        return valor

    tamano = campo("pdf.page_size_mm")
    if not (_lista_de_numeros(tamano, 2) and tamano[0] > 0 and tamano[1] > 0):
        raise ManifiestoInvalido(
            f"'pdf.page_size_mm' debe ser [ancho, alto] en mm, positivos; tiene {tamano!r}."
        )

    esperado = {"units": "mm", "origin": "top-left", "y_axis": "down"}
    for clave, valor_esperado in esperado.items():
        valor = campo(f"pdf.drawing.cad_to_page.{clave}")
        if valor != valor_esperado:
            raise ManifiestoInvalido(
                f"'pdf.drawing.cad_to_page.{clave}' debe ser '{valor_esperado}'; tiene "
                f"{valor!r}. Este componedor solo entiende matrices a mm de página con origen "
                f"arriba-izquierda y Y hacia abajo."
            )
    matriz = campo("pdf.drawing.cad_to_page.matrix")
    if not _lista_de_numeros(matriz, 6):
        n = len(matriz) if isinstance(matriz, list) else "no es lista"
        raise ManifiestoInvalido(
            f"'pdf.drawing.cad_to_page.matrix' debe tener 6 números [a, b, c, d, e, f]; "
            f"tiene {n} ({matriz!r})."
        )

    limites = campo("pdf.drawing.page_bounds_mm")
    claves = ("x0", "y0", "x1", "y1")
    if not isinstance(limites, dict) or not all(k in limites for k in claves):
        raise ManifiestoInvalido(
            f"'pdf.drawing.page_bounds_mm' debe tener x0, y0, x1, y1; tiene {limites!r}."
        )
    rect = tuple(limites[k] for k in claves)
    if not _lista_de_numeros(list(rect), 4) or rect[2] <= rect[0] or rect[3] <= rect[1]:
        raise ManifiestoInvalido(
            f"'pdf.drawing.page_bounds_mm' debe ser un rectángulo con x1 > x0 e y1 > y0; "
            f"tiene {limites!r}."
        )

    return GeometriaManifiesto(
        ancho_pagina_mm=float(tamano[0]),
        alto_pagina_mm=float(tamano[1]),
        matriz=MatrizCad(*(float(v) for v in matriz)),
        limites_pagina_mm=tuple(float(v) for v in rect),
    )


def _lista_de_numeros(valor, n: int) -> bool:
    return (
        isinstance(valor, list)
        and len(valor) == n
        and all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
                for v in valor)
    )
