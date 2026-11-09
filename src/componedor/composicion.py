"""Hoja base del formato: plantilla del rótulo (o marco propio), rosa de los vientos y guías."""

import pymupdf

from componedor.dibujo import dibujar_guias, dibujar_marco
from componedor.formato import Formato, RectMM
from componedor.hoja import crear_pagina
from componedor.plantilla import InformePlantilla, colocar_plantilla
from componedor.rosa import NOMBRE as ROSA
from componedor.rosa import InformeRosa, aplicar_rosa

MANTENER = "mantener"  # la rosa queda como viene en la plantilla (no se toca)


def hoja_base(formato: Formato, guias: bool = False, exigir_marco: bool = True,
              ) -> tuple[pymupdf.Document, InformePlantilla | None]:
    """Hoja con la plantilla tal cual (si el formato la tiene) o con nuestro marco, y las
    guías encima.

    Con plantilla no se dibuja nuestro marco: el rótulo ya trae el marco oficial. La
    plantilla se coloca primero, así queda debajo de guías y detalles.
    """
    doc, informe, _ = hoja_base_con_rosa(formato, guias, exigir_marco, MANTENER)
    return doc, informe


def hoja_base_con_rosa(formato: Formato, guias: bool = False, exigir_marco: bool = True,
                       rosa: RectMM | None | str = MANTENER,
                       ) -> tuple[pymupdf.Document, InformePlantilla | None, InformeRosa | None]:
    """Como `hoja_base`, decidiendo además dónde va la rosa de los vientos (rosa.py):
    `MANTENER` (como viene), None (oculta) o el rectángulo (mm de papel) donde dibujarla.

    Si el formato no tiene plantilla o no declara la rosa, `rosa` no tiene efecto. Las guías
    se dibujan al final, sobre la rosa.
    """
    doc = crear_pagina(formato.ancho_mm, formato.alto_mm)
    informe, informe_rosa = None, None
    if formato.plantilla is not None:
        informe = colocar_plantilla(doc[0], formato, exigir_marco)
        if rosa != MANTENER and formato.elemento(ROSA) is not None:
            informe_rosa = aplicar_rosa(doc[0], formato, rosa)
    else:
        dibujar_marco(doc[0], formato)
    if guias:
        dibujar_guias(doc[0], formato)
    return doc, informe, informe_rosa
