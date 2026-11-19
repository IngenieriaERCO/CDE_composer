"""La entrada del catálogo del editor para un paquete recién exportado (etapa 3).

Es la misma forma que arma `datos_editor.construir_datos_editor` para cada detalle aceptado
(ver docs/formato_editor_datos.md), con la miniatura ya como `data_url`: el servidor se la da
al editor para que el bloque exportado pase a ser un detalle normal sin regenerar editor.html.
"""

import base64
import os
from pathlib import Path

import pymupdf

from componedor.cad_a_papel import limites_dibujo_en_papel
from componedor.colocar import exceso_de_tamano
from componedor.comprobacion_dibujo import tiene_fondo_de_pagina
from componedor.formato import RectMM
from componedor.importador import PaqueteAceptado

MAX_PX_MINIATURA = 1400  # igual que datos_editor.MAX_PX_MINIATURA


def ruta_para_el_editor(ruta: Path, carpeta_editor: Path) -> str:
    """Relativa a la carpeta del editor, con «/» (absoluta si está en otro disco)."""
    try:
        return Path(os.path.relpath(Path(ruta).resolve(), Path(carpeta_editor).resolve())).as_posix()
    except ValueError:
        return Path(ruta).resolve().as_posix()


def detalle_para_editor(aceptado: PaqueteAceptado, ident: str, carpeta_editor: Path,
                        zona: RectMM, max_px: int = MAX_PX_MINIATURA) -> dict:
    """{id, manifiesto, bloque, escala, tamano_pagina_mm, limites_dibujo_mm, cad_a_pagina,
    mm_por_unidad, cabe, tiene_fondo, notas, miniatura: {data_url, ancho_px, alto_px}}."""
    paquete = aceptado.paquete
    m = paquete.manifiesto
    ancho, alto = m.pdf.tamano_pagina_mm
    with pymupdf.open(paquete.ruta_pdf) as doc:
        pagina = doc[0]
        fondo = tiene_fondo_de_pagina(pagina)
        zoom = max_px / max(pagina.rect.width, pagina.rect.height)
        pix = pagina.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=not fondo)
        png = pix.tobytes("png")
    return {
        "id": ident,
        "manifiesto": ruta_para_el_editor(paquete.ruta_manifiesto, carpeta_editor),
        "bloque": m.bloque,
        "escala": m.escala.denominador,
        "tamano_pagina_mm": [ancho, alto],
        "limites_dibujo_mm": list(limites_dibujo_en_papel(m.pdf.dibujo.limites_pagina_mm, alto,
                                                          (0.0, 0.0))),
        "cad_a_pagina": [m.pdf.dibujo.matriz.a, m.pdf.dibujo.matriz.b, m.pdf.dibujo.matriz.c,
                         m.pdf.dibujo.matriz.d, m.pdf.dibujo.matriz.e, m.pdf.dibujo.matriz.f],
        "mm_por_unidad": m.unidades.milimetros_por_unidad,
        "cabe": exceso_de_tamano((ancho, alto), zona) == (0.0, 0.0),
        "tiene_fondo": fondo,
        "notas": [],
        "miniatura": {"data_url": "data:image/png;base64," + base64.b64encode(png).decode("ascii"),
                      "ancho_px": pix.width, "alto_px": pix.height},
    }
