"""Plantilla del rótulo (PDF impreso desde AutoCAD) como fondo de la hoja.

La plantilla se coloca en (0, 0), sin escalar, con la misma lógica que los detalles
(`colocar.insertar_pagina`, que corrige /Rotate). Va DEBAJO: se coloca antes que guías
y detalles.

AutoCAD redondea el tamaño de página a puntos enteros (A1 sale de 2384 x 1684 pt =
841,02 x 594,08 mm), por eso se acepta una diferencia de tamaño de hasta ±0,5 mm.
Después se hace una validación cruzada: el marco dibujado en la plantilla debe coincidir
con el marco del formato (±0,5 mm); si no, alguna medida del JSON está mal.
"""

from dataclasses import dataclass
from pathlib import Path

import pymupdf

from componedor.colocar import abrir_pdf, insertar_pagina, tamano_visible_mm
from componedor.formato import Formato, RectMM
from componedor.transformaciones import rect_pdf_a_papel

TOLERANCIA_TAMANO_MM = 0.5
TOLERANCIA_MARCO_MM = 0.5


class PlantillaInvalida(ValueError):
    """La plantilla no se puede usar con este formato."""


@dataclass(frozen=True)
class InformePlantilla:
    ruta: Path
    tamano_mm: tuple[float, float]
    diferencia_tamano_mm: tuple[float, float]  # plantilla - hoja (ancho, alto)
    marco_leido: RectMM
    diferencia_marco_mm: RectMM  # marco leído - marco del formato, por lado

    @property
    def diferencia_marco_max_mm(self) -> float:
        return max(abs(d) for d in self.diferencia_marco_mm)


def colocar_plantilla(hoja: pymupdf.Page, formato: Formato,
                      exigir_marco: bool = True) -> InformePlantilla:
    """Coloca la plantilla del formato en (0, 0) y valida tamaño y marco.

    Debe llamarse sobre la hoja vacía, antes de dibujar guías o detalles: la validación
    del marco lee los trazos de la página. Con `exigir_marco=False` el marco solo se mide
    (no lanza error si no coincide); lo usa el comando `referencia` para informarlo.
    """
    if formato.plantilla is None:
        raise PlantillaInvalida("El formato no tiene plantilla.")

    doc = abrir_pdf(formato.plantilla, "la plantilla", PlantillaInvalida)
    try:
        ancho, alto = tamano_visible_mm(doc[0])
        diferencia = (ancho - formato.ancho_mm, alto - formato.alto_mm)
        if any(abs(d) > TOLERANCIA_TAMANO_MM for d in diferencia):
            raise PlantillaInvalida(
                f"La plantilla '{formato.plantilla}' mide {ancho:.2f} x {alto:.2f} mm y la hoja "
                f"{formato.ancho_mm:.1f} x {formato.alto_mm:.1f} mm: diferencia "
                f"{diferencia[0]:+.2f} x {diferencia[1]:+.2f} mm, mayor que la tolerancia de "
                f"±{TOLERANCIA_TAMANO_MM} mm. Revise el tamaño de papel con que se imprimió."
            )
        insertar_pagina(hoja, formato, doc, 0, (0.0, 0.0))
    finally:
        doc.close()

    if exigir_marco:
        marco_leido, diferencia_marco = leer_marco(hoja, formato)
    else:
        encontrado = buscar_marco(hoja, formato)
        if encontrado is None:
            raise PlantillaInvalida("La plantilla no tiene trazos: no se puede medir el marco.")
        marco_leido, diferencia_marco = encontrado
    return InformePlantilla(
        ruta=formato.plantilla,
        tamano_mm=(ancho, alto),
        diferencia_tamano_mm=diferencia,
        marco_leido=marco_leido,
        diferencia_marco_mm=diferencia_marco,
    )


def buscar_marco(hoja: pymupdf.Page, formato: Formato) -> tuple[RectMM, RectMM] | None:
    """Trazo de la hoja más parecido al marco del formato, sin juzgarlo.

    Devuelve (rectángulo leído, diferencias por lado) en mm de papel, o None si la hoja no
    tiene trazos.
    """
    mejor, diferencia, error = None, None, float("inf")
    for trazo in hoja.get_drawings():
        rect = rect_pdf_a_papel(trazo["rect"], formato.alto_mm)
        dif = tuple(a - b for a, b in zip(rect, formato.marco))
        if max(abs(d) for d in dif) < error:
            mejor, diferencia, error = rect, dif, max(abs(d) for d in dif)
    return None if mejor is None else (mejor, diferencia)


def leer_marco(hoja: pymupdf.Page, formato: Formato) -> tuple[RectMM, RectMM]:
    """Busca en la hoja el trazo que mejor coincide con el marco del formato.

    Devuelve (marco leído, diferencias por lado) en mm de papel. Lanza `PlantillaInvalida`
    si el más parecido se aparta más de la tolerancia.
    """
    encontrado = buscar_marco(hoja, formato)
    if encontrado is None:
        raise PlantillaInvalida("La plantilla no tiene trazos: no se puede comprobar el marco.")
    mejor, diferencia = encontrado
    if max(abs(d) for d in diferencia) > TOLERANCIA_MARCO_MM:
        raise PlantillaInvalida(
            f"El marco del rótulo no coincide con el marco del formato (tolerancia "
            f"±{TOLERANCIA_MARCO_MM} mm). Trazo más parecido en la plantilla: {_mm(mejor)}; "
            f"marco del formato: {_mm(formato.marco)}; diferencias "
            f"xmin {_dif(diferencia[0])}, ymin {_dif(diferencia[1])}, "
            f"xmax {_dif(diferencia[2])}, ymax {_dif(diferencia[3])} mm. "
            f"Revise las medidas de 'marco' en el JSON del formato."
        )
    return mejor, diferencia


def _mm(rect: RectMM) -> str:
    return "[" + ", ".join(f"{v:.2f}" for v in rect) + "]"


def _dif(valor: float) -> str:
    """Diferencia con signo y 2 decimales, sin "-0.00" por errores de redondeo."""
    return f"{round(valor, 2) + 0.0:+.2f}"
