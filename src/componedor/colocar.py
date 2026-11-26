"""Colocación de un detalle PDF en la hoja, sin escalar y como vector.

Los PDF del exportador ya vienen a escala física (la escala 1:N ya está aplicada):
1 mm del PDF de origen = 1 mm en la hoja.

Cómo se resuelven el CropBox y el /Rotate de la página de origen
-----------------------------------------------------------------
- Manda el tamaño VISIBLE: `page.rect` de PyMuPDF, que es el CropBox ya girado según
  /Rotate (una página de 120 x 80 mm con /Rotate 90 se ve de 80 x 120 mm).
- `Page.show_pdf_page` (PyMuPDF 1.28) no tiene en cuenta el /Rotate del origen: recorta
  con las medidas giradas sobre el contenido sin girar. Y `Page.remove_rotation()`
  pierde el CropBox. Por eso:
    1. se copia la página de origen a un documento temporal en memoria (sigue siendo vector),
    2. a esa copia se le pone /Rotate 0 (el CropBox se conserva),
    3. se llama a `show_pdf_page` con `rotate = -rotación_origen` y un rectángulo destino
       del tamaño visible exacto, así el factor de escala resulta 1.
  Verificado píxel a píxel contra la página de origen en 0/90/180/270 grados, con y sin
  CropBox desplazado.
- `show_pdf_page` inserta la página como Form XObject: el detalle sigue siendo vector.
"""

from pathlib import Path

import pymupdf

from componedor.formato import EPS_MM, Formato, RectMM
from componedor.transformaciones import rect_papel_a_pdf
from componedor.unidades import mm_a_pt, pt_a_mm


class DetalleInvalido(ValueError):
    """El detalle no se puede abrir o no cabe en la zona destino."""


def tamano_visible_mm(pagina: pymupdf.Page) -> tuple[float, float]:
    """(ancho, alto) visible de una página en mm: CropBox girado según /Rotate."""
    return pt_a_mm(pagina.rect.width), pt_a_mm(pagina.rect.height)


def posicion_centrada(tamano_mm: tuple[float, float], zona: RectMM) -> tuple[float, float]:
    """Esquina inferior izquierda que centra un detalle de `tamano_mm` en la zona."""
    ancho, alto = tamano_mm
    return (
        (zona[0] + zona[2]) / 2 - ancho / 2,
        (zona[1] + zona[3]) / 2 - alto / 2,
    )


def colocar_detalle(
    hoja: pymupdf.Page,
    formato: Formato,
    origen: pymupdf.Document | Path | str,
    posicion_mm: tuple[float, float] | None = None,
    pagina: int = 0,
    zona: str = "area_dibujo",
) -> RectMM:
    """Coloca la página `pagina` de `origen` en la hoja, sin escalar.

    `posicion_mm` es la esquina inferior izquierda del detalle en mm de papel (Y hacia
    arriba). Si es None, el detalle se centra en la zona. Devuelve el rectángulo ocupado
    (xmin, ymin, xmax, ymax) en mm de papel. Lanza `DetalleInvalido` si no cabe en la zona.
    """
    if zona not in formato.zonas:
        raise DetalleInvalido(
            f"La zona '{zona}' no existe en el formato. Zonas disponibles: "
            f"{', '.join(formato.zonas)}."
        )
    rect_zona = formato.zonas[zona]

    doc_origen = abrir_pdf(origen, "el detalle", DetalleInvalido)
    try:
        return _colocar(hoja, formato, doc_origen, pagina, posicion_mm, zona, rect_zona)
    finally:
        if doc_origen is not origen:  # solo se cierra si se abrió aquí
            doc_origen.close()


def _colocar(hoja: pymupdf.Page, formato: Formato, doc_origen: pymupdf.Document, pagina: int,
             posicion_mm: tuple[float, float] | None, zona: str, rect_zona: RectMM) -> RectMM:
    if not 0 <= pagina < doc_origen.page_count:
        raise DetalleInvalido(
            f"El detalle tiene {doc_origen.page_count} página(s); no existe la página {pagina} "
            f"(se cuentan desde 0)."
        )
    pagina_origen = doc_origen[pagina]
    ancho, alto = tamano_visible_mm(pagina_origen)

    if posicion_mm is None:
        posicion_mm = posicion_centrada((ancho, alto), rect_zona)
    x, y = posicion_mm
    _exigir_que_quepa((x, y, x + ancho, y + alto), zona, rect_zona)
    return insertar_pagina(hoja, formato, doc_origen, pagina, (x, y))


def insertar_pagina(hoja: pymupdf.Page, formato: Formato, doc_origen: pymupdf.Document,
                    pagina: int, posicion_mm: tuple[float, float],
                    recorte_mm: RectMM | None = None) -> RectMM:
    """Inserta la página tal como se ve (corrige /Rotate, ver arriba), sin escalar.

    `posicion_mm` es la esquina inferior izquierda de la PÁGINA en mm de papel. No valida que
    quepa. `recorte_mm`: solo esa parte de la página (mm de la página, Y abajo; ver
    recorte_detalle.py), con `clip`: sigue siendo vector y el dibujo no se mueve. Solo en
    páginas sin /Rotate (las del Exportador); en una girada se ignora.
    Devuelve el rectángulo que se ve en mm de papel.
    """
    pagina_origen = doc_origen[pagina]
    ancho, alto = tamano_visible_mm(pagina_origen)
    x, y = posicion_mm
    ocupado = (x, y, x + ancho, y + alto)

    rotacion = pagina_origen.rotation
    temporal = pymupdf.open()
    temporal.insert_pdf(doc_origen, from_page=pagina, to_page=pagina)
    temporal[0].set_rotation(0)
    clip = None
    if recorte_mm is not None and rotacion == 0:
        rx0, ry0, rx1, ry1 = recorte_mm
        ocupado = (x + rx0, y + alto - ry1, x + rx1, y + alto - ry0)
        clip = pymupdf.Rect(*(mm_a_pt(v) for v in recorte_mm))
    destino = rect_papel_a_pdf(ocupado, formato.alto_mm)
    hoja.show_pdf_page(destino, temporal, 0, rotate=-rotacion, clip=clip)
    temporal.close()
    return ocupado


def abrir_pdf(origen: pymupdf.Document | Path | str, que: str,
              error: type[ValueError]) -> pymupdf.Document:
    """Abre un PDF (o devuelve el documento recibido). `que` es p. ej. "el detalle"."""
    if isinstance(origen, pymupdf.Document):
        return origen
    ruta = Path(origen)
    if not ruta.exists():
        raise error(f"No se encontró {que} '{ruta}'.")
    try:
        doc = pymupdf.open(ruta)
    except pymupdf.FileDataError as e:
        raise error(f"No se pudo abrir {que} '{ruta}' como PDF: {e}") from e
    if not doc.is_pdf:
        doc.close()
        raise error(f"{que[0].upper()}{que[1:]} '{ruta}' no es un PDF.")
    if doc.page_count == 0:
        doc.close()
        raise error(f"{que[0].upper()}{que[1:]} '{ruta}' no tiene páginas.")
    return doc


def exceso_de_tamano(tamano_mm: tuple[float, float], zona: RectMM) -> tuple[float, float]:
    """Cuánto se pasa (ancho, alto) en mm un detalle de `tamano_mm` respecto a la zona;
    (0, 0) si cabe por tamaño. Es la regla que usan `colocar` y el inventario."""
    dx = tamano_mm[0] - (zona[2] - zona[0])
    dy = tamano_mm[1] - (zona[3] - zona[1])
    return (dx if dx > EPS_MM else 0.0, dy if dy > EPS_MM else 0.0)


def _exigir_que_quepa(ocupado: RectMM, nombre_zona: str, zona: RectMM) -> None:
    motivo = motivo_fuera_de_zona(ocupado, nombre_zona, zona)
    if motivo:
        raise DetalleInvalido(motivo)


def motivo_fuera_de_zona(ocupado: RectMM, nombre_zona: str, zona: RectMM,
                         que: str = "El detalle") -> str | None:
    """Por qué el rectángulo `ocupado` (mm de papel) no cabe en la zona, o None si cabe.

    Regla estricta (solo tolera ruido numérico, EPS_MM). La usan `colocar` y `componer`
    (también para la rosa de los vientos: `que="La rosa de los vientos"`).
    """
    ancho, alto = ocupado[2] - ocupado[0], ocupado[3] - ocupado[1]
    ancho_zona, alto_zona = zona[2] - zona[0], zona[3] - zona[1]
    descripcion = (
        f"{que} ({ancho:.1f} x {alto:.1f} mm) no cabe en la zona '{nombre_zona}' "
        f"({ancho_zona:.1f} x {alto_zona:.1f} mm)"
    )

    # 1) Más grande que la zona: no cabe en ninguna posición.
    dx, dy = exceso_de_tamano((ancho, alto), zona)
    exceso = []
    if dx:
        exceso.append(f"{dx:.1f} mm a lo ancho")
    if dy:
        exceso.append(f"{dy:.1f} mm a lo alto")
    if exceso:
        return f"{descripcion}: se pasa {' y '.join(exceso)}."

    # 2) Cabe por tamaño, pero la posición pedida lo saca de la zona.
    lados = [
        (zona[0] - ocupado[0], "por la izquierda"),
        (zona[1] - ocupado[1], "por abajo"),
        (ocupado[2] - zona[2], "por la derecha"),
        (ocupado[3] - zona[3], "por arriba"),
    ]
    fuera = [f"{d:.1f} mm {lado}" for d, lado in lados if d > EPS_MM]
    if fuera:
        return (f"{descripcion} en la posición pedida {[round(v, 1) for v in ocupado]}: "
                f"se pasa {' y '.join(fuera)}.")
    return None
