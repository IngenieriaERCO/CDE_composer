"""Rosa de los vientos: se puede ocultar o mover (subfase 4.1).

La rosa viene dibujada en la plantilla del rótulo, en el rectángulo del elemento fijo
"rosa_vientos" del formato. `componer` SIEMPRE:
  1. la quita de la hoja con redacciones de PyMuPDF sobre ese rectángulo (más un margen de
     `MARGEN_MM`): se borran solo los trazos COMPLETAMENTE contenidos y el texto de esa zona;
     el marco, el borde del área de dibujo y lo demás no se tocan. Se comprueba que el resto
     de la plantilla quedó idéntico (mismos trazos en el mismo orden, mismos textos, mismas
     imágenes); si no, error.
  2. si es visible, la vuelve a dibujar en su posición (la original o la del plano)
     copiándola como VECTORES desde la plantilla original: `show_pdf_page` con `clip` en su
     rectángulo, mismo tamaño y sin rotación, desde una copia de la plantilla en la que se
     borró todo lo de alrededor (así la copia solo trae la rosa).
Al verificar el PDF se mide la rosa copiada: sus trazos deben ser los originales trasladados
(±0,1 mm) y sus letras las mismas.

La posición es la esquina inferior izquierda del rectángulo de la rosa (mm de papel, Y hacia
arriba), como `posicion_mm` de los detalles. Debe quedar completa dentro de `area_dibujo`.
"""

from dataclasses import dataclass

import pymupdf

from componedor.colocar import motivo_fuera_de_zona
from componedor.formato import ElementoPlantilla, Formato, RectMM
from componedor.hoja import crear_pagina
from componedor.plantilla import colocar_plantilla
from componedor.transformaciones import rect_papel_a_pdf
from componedor.unidades import mm_a_pt

NOMBRE = "rosa_vientos"
ZONA = "area_dibujo"
# MuPDF solo borra un trazo si su caja ENSANCHADA por el grosor y las puntas (inglete) queda
# dentro de la redacción: con 1 mm una diagonal fina no se borraba. Con 2 mm sí, y nada más de
# la plantilla real cabe completo en esa caja (lo comprueba `_cambios_fuera_de_la_rosa`).
MARGEN_MM = 2.0
TOL_MM = 0.1


class RosaInvalida(ValueError):
    """La rosa no se puede quitar, mover o verificar (el mensaje dice por qué)."""


@dataclass(frozen=True)
class InformeRosa:
    original: RectMM  # rectángulo de la rosa en la plantilla (mm de papel)
    destino: RectMM | None  # dónde quedó; None: oculta
    trazos_original: tuple[tuple[float, float, float, float], ...]  # pt, en la plantilla
    textos_original: tuple[str, ...]  # palabras de la rosa (N, S, E, W), ordenadas
    quitados: int  # trazos quitados de la plantilla


def rect_destino(original: RectMM, posicion_mm: tuple[float, float] | None) -> RectMM:
    """Rectángulo de la rosa con su esquina inferior izquierda en `posicion_mm` (None: la
    original). Mismo tamaño."""
    if posicion_mm is None:
        return original
    x, y = posicion_mm
    return (x, y, x + original[2] - original[0], y + original[3] - original[1])


def motivo_fuera(destino: RectMM, formato: Formato) -> str | None:
    """Por qué la rosa en `destino` no queda completa dentro de `area_dibujo` (None: cabe)."""
    return motivo_fuera_de_zona(destino, ZONA, formato.zonas[ZONA], que="La rosa de los vientos")


def elementos_visibles(formato: Formato, destino_rosa: RectMM | None) -> list[ElementoPlantilla]:
    """Los elementos fijos tal como quedan en la hoja: la rosa en `destino_rosa` (o fuera de la
    lista si está oculta: None); los demás, sin cambios y en el mismo orden. Es la lista con
    la que se calculan las advertencias (igual en el editor)."""
    lista = []
    for elemento in formato.elementos_plantilla:
        if elemento.nombre != NOMBRE:
            lista.append(elemento)
        elif destino_rosa is not None:
            lista.append(ElementoPlantilla(NOMBRE, destino_rosa))
    return lista


def aplicar_rosa(page: pymupdf.Page, formato: Formato, destino: RectMM | None) -> InformeRosa:
    """Quita la rosa de la plantilla ya colocada en `page` y, si `destino` no es None, la
    vuelve a dibujar ahí. Lanza `RosaInvalida`."""
    elemento = formato.elemento(NOMBRE)
    if formato.plantilla is None or elemento is None:
        raise RosaInvalida(f"el formato no tiene plantilla con el elemento '{NOMBRE}'")
    original = elemento.rect
    caja = _caja(original, formato)

    trazos = page.get_drawings()
    palabras = page.get_text("words")
    imagenes = _imagenes(page)
    de_la_rosa = [d for d in trazos if caja.contains(d["rect"])]
    textos = tuple(sorted(p[4] for p in palabras if caja.contains(pymupdf.Rect(p[:4]))))

    page.add_redact_annot(caja, fill=False)
    page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE,
                          graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED,
                          text=pymupdf.PDF_REDACT_TEXT_REMOVE)
    problemas = _cambios_fuera_de_la_rosa(page, caja, trazos, palabras, imagenes)
    if problemas:
        raise RosaInvalida("al quitar la rosa de la plantilla cambió algo más:\n"
                           + "\n".join(f"- {p}" for p in problemas))

    if destino is not None:
        sola = documento_rosa_sola(formato)
        try:
            page.show_pdf_page(_caja(destino, formato), sola, 0, clip=caja)
        finally:
            sola.close()
    return InformeRosa(original, destino, tuple(tuple(d["rect"]) for d in de_la_rosa), textos,
                       len(de_la_rosa))


def redibujar_rosa(page: pymupdf.Page, formato: Formato, destino: RectMM) -> None:
    """Vuelve a dibujar la rosa en `destino`, encima de lo que ya hay (p. ej. la ortofoto: la
    rosa nunca queda tapada por la foto). Es la misma copia que hace `aplicar_rosa`."""
    sola = documento_rosa_sola(formato)
    try:
        page.show_pdf_page(_caja(destino, formato), sola, 0,
                           clip=_caja(formato.elemento(NOMBRE).rect, formato))
    finally:
        sola.close()


def documento_rosa_sola(formato: Formato) -> pymupdf.Document:
    """Hoja con la plantilla en la que se borró TODO lo que no es la rosa: las cuatro franjas
    alrededor de su rectángulo (más el margen) se redactan quitando cualquier trazo que las
    toque, sus textos y sus imágenes. Sirve de origen para copiarla (y para su imagen en el
    editor)."""
    doc = crear_pagina(formato.ancho_mm, formato.alto_mm)
    colocar_plantilla(doc[0], formato)
    page = doc[0]
    caja = _caja(formato.elemento(NOMBRE).rect, formato)
    ancho, alto = page.rect.width, page.rect.height
    for franja in (pymupdf.Rect(0, 0, ancho, caja.y0), pymupdf.Rect(0, caja.y1, ancho, alto),
                   pymupdf.Rect(0, caja.y0, caja.x0, caja.y1),
                   pymupdf.Rect(caja.x1, caja.y0, ancho, caja.y1)):
        page.add_redact_annot(franja, fill=False)
    page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_REMOVE,
                          graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED,
                          text=pymupdf.PDF_REDACT_TEXT_REMOVE)
    return doc


def verificar_rosa(page: pymupdf.Page, informe: InformeRosa, formato: Formato,
                   trazos_base: int) -> list[str]:
    """Mide la rosa en el PDF guardado. `trazos_base`: cuántos trazos tiene la hoja base (la
    rosa copiada está entre ellos; los detalles van después)."""
    base = page.get_drawings()[:trazos_base]
    if informe.destino is None:
        caja = _caja(informe.original, formato)
        quedan = [d for d in base if caja.contains(d["rect"])]
        return ([f"la rosa está oculta, pero quedan {len(quedan)} trazo(s) en su sitio original"]
                if quedan else [])

    caja = _caja(informe.destino, formato)
    origen = rect_papel_a_pdf(informe.original, formato.alto_mm)
    llegada = rect_papel_a_pdf(informe.destino, formato.alto_mm)
    dx, dy = llegada.x0 - origen.x0, llegada.y0 - origen.y0
    esperados = sorted((r[0] + dx, r[1] + dy, r[2] + dx, r[3] + dy)
                       for r in informe.trazos_original)
    medidos = sorted(tuple(d["rect"]) for d in base if caja.contains(d["rect"]))
    problemas = []
    if len(medidos) != len(esperados):
        problemas.append(f"la rosa debía tener {len(esperados)} trazos en "
                         f"{_mm(informe.destino)} y tiene {len(medidos)}")
    else:
        diferencia = max((abs(a - b) for m, e in zip(medidos, esperados) for a, b in zip(m, e)),
                         default=0.0)
        if diferencia > mm_a_pt(TOL_MM):
            problemas.append(f"la rosa quedó corrida {diferencia * 25.4 / 72:.3f} mm de "
                             f"{_mm(informe.destino)} (tolerancia ±{TOL_MM} mm)")
    textos = tuple(sorted(p[4] for p in page.get_text("words")
                          if caja.contains(pymupdf.Rect(p[:4]))))
    if textos != informe.textos_original:
        problemas.append(f"las letras de la rosa debían ser {list(informe.textos_original)} y "
                         f"son {list(textos)}")
    return problemas


# --- partes ------------------------------------------------------------------------------

def _caja(rect: RectMM, formato: Formato) -> pymupdf.Rect:
    """Rectángulo de la rosa más el margen, en pt de PyMuPDF."""
    m = MARGEN_MM
    return rect_papel_a_pdf((rect[0] - m, rect[1] - m, rect[2] + m, rect[3] + m), formato.alto_mm)


def _firma(trazo: dict) -> tuple:
    """Lo que identifica a un trazo para compararlo antes y después de quitar la rosa."""
    return (trazo.get("type"), tuple(round(v, 3) for v in trazo["rect"]), trazo.get("color"),
            trazo.get("fill"), round(trazo.get("width") or 0.0, 4), len(trazo["items"]))


def _imagenes(page: pymupdf.Page) -> list[tuple]:
    return [tuple(round(v, 3) for v in i["bbox"]) for i in page.get_image_info()]


def _cambios_fuera_de_la_rosa(page: pymupdf.Page, caja: pymupdf.Rect, trazos: list[dict],
                              palabras: list, imagenes: list) -> list[str]:
    problemas = []
    esperados = [_firma(d) for d in trazos if not caja.contains(d["rect"])]
    actuales = [_firma(d) for d in page.get_drawings()]
    if actuales != esperados:
        distintos = sum(1 for a, b in zip(actuales, esperados) if a != b)
        problemas.append(f"trazos: quedaron {len(actuales)} y debían quedar {len(esperados)} "
                         f"({distintos} distintos)")
    fuera = [tuple(p[:5]) for p in palabras if not caja.contains(pymupdf.Rect(p[:4]))]
    if [tuple(p[:5]) for p in page.get_text("words")] != fuera:
        problemas.append("textos: cambió algún texto fuera de la rosa")
    if _imagenes(page) != imagenes:
        problemas.append("imágenes: cambió alguna imagen de la plantilla")
    return problemas


def _mm(r: RectMM) -> str:
    return "X {:.2f} a {:.2f}, Y {:.2f} a {:.2f} mm".format(r[0], r[2], r[1], r[3])
