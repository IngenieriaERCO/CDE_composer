"""Hoja base del formato: plantilla del rótulo (o marco propio) y guías."""

import pymupdf

from componedor.dibujo import dibujar_guias, dibujar_marco
from componedor.formato import Formato
from componedor.hoja import crear_pagina
from componedor.plantilla import InformePlantilla, colocar_plantilla


def hoja_base(formato: Formato, guias: bool = False, exigir_marco: bool = True,
              ) -> tuple[pymupdf.Document, InformePlantilla | None]:
    """Hoja con la plantilla (si el formato la tiene) o con nuestro marco, y las guías encima.

    Con plantilla no se dibuja nuestro marco: el rótulo ya trae el marco oficial. La
    plantilla se coloca primero, así queda debajo de guías y detalles.
    """
    doc = crear_pagina(formato.ancho_mm, formato.alto_mm)
    informe = None
    if formato.plantilla is not None:
        informe = colocar_plantilla(doc[0], formato, exigir_marco)
    else:
        dibujar_marco(doc[0], formato)
    if guias:
        dibujar_guias(doc[0], formato)
    return doc, informe
