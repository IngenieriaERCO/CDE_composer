"""Plantilla v3 del rótulo A1 ERCO, sacada de la v2 sin tocar el original.

Qué cambia respecto de `plantillas/rotulo_A1_ERCO_v2.pdf`:
  1. La fila «DISEÑADOR | REVISOR» (encima del logo) queda vacía: se BORRAN los trazos que
     caen completos dentro de ella (las letras SHX de los dos títulos y la línea vertical del
     medio) y las dos anotaciones invisibles con esos textos. No se tapa nada con blanco: los
     trazos dejan de existir, así que no se nota ni al ampliar. Las líneas de la fila (que
     siguen más allá de ella) y el marco no se tocan.
  2. El logo de ERCO se corre en X para que lo que se VE de él (sus píxeles no blancos) quede
     centrado en la columna del rótulo. Se reinserta la MISMA imagen del PDF (mismo objeto, sin
     volver a comprimirla); solo cambia su posición.

Se verifica solo, antes de dejar el archivo: el original no cambió (MD5), se borró al menos un
trazo y todos los borrados estaban dentro de la fila, fuera de la fila y del logo la página se
ve igual píxel a píxel, la imagen del logo es byte a byte la misma y su parte visible quedó
centrada (±0,1 mm). Si algo falla, no se escribe nada.

Uso: `python -m componedor.cli crear-plantilla-v3` (ver docs/editor.md). Coordenadas en mm de
papel (origen abajo a la izquierda, Y hacia arriba).
"""

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from componedor.unidades import mm_a_pt, pt_a_mm

ORIGEN = Path("plantillas/rotulo_A1_ERCO_v2.pdf")
DESTINO = Path("plantillas/rotulo_A1_ERCO_v3.pdf")
ALTO_HOJA_MM = 594.0
# Fila de los títulos DISEÑADOR | REVISOR, un poco adentro del marco (X) y apenas más alta que
# la fila (Y 99,4 a 106,2): así entran la línea vertical entera y las letras, y quedan fuera las
# líneas horizontales y verticales que siguen más allá de la fila.
FILA_TITULOS_MM = (673.0, 99.1, 827.7, 106.5)
ANOTACIONES = ("DISEÑADOR", "REVISOR")
# Columna del rótulo (CLAUDE.md, «Formato A1 ERCO»): el logo se centra entre estas X.
FRANJA_X_MM = (672.4, 828.3)
TOLERANCIA_MM = 0.1
UMBRAL_BLANCO = 200  # un píxel con algún canal por debajo de esto «se ve»
PPP_COMPARACION = 100


class PlantillaV3Invalida(ValueError):
    """No se pudo crear la plantilla v3 (mensaje en español para el usuario)."""


@dataclass
class InformePlantillaV3:
    destino: Path
    md5_origen: str
    trazos_quitados: list[tuple[float, float, float, float]]  # mm de papel
    anotaciones_quitadas: list[str]
    desplazamiento_logo_mm: float
    centro_logo_antes_mm: float
    centro_logo_despues_mm: float
    centro_franja_mm: float


def crear_plantilla_v3(origen: Path | str = ORIGEN, destino: Path | str = DESTINO,
                       sobrescribir: bool = False, fila_mm=FILA_TITULOS_MM,
                       franja_x_mm=FRANJA_X_MM, anotaciones=ANOTACIONES) -> InformePlantillaV3:
    """Crea `destino` a partir de `origen` (que no se modifica). Lanza PlantillaV3Invalida."""
    origen, destino = Path(origen), Path(destino)
    if not origen.is_file():
        raise PlantillaV3Invalida(f"No existe la plantilla de origen '{origen}'.")
    if origen.resolve() == destino.resolve():
        raise PlantillaV3Invalida("La salida no puede ser la misma plantilla de origen.")
    if destino.exists() and not sobrescribir:
        raise PlantillaV3Invalida(f"'{destino}' ya existe. Use --sobrescribir para reemplazarlo.")
    md5_antes = _md5(origen)

    doc = pymupdf.open(origen)
    if len(doc) != 1:
        raise PlantillaV3Invalida(f"'{origen}': se esperaba una sola página; tiene {len(doc)}.")
    pagina = doc[0]
    fila = _rect_pdf(fila_mm)
    referencia = pagina.get_pixmap(dpi=PPP_COMPARACION, annots=False)

    # 1. Fila de títulos: las anotaciones con esos textos (primero, para que no cuenten como
    #    trazos) y los trazos que caen completos dentro de la fila.
    quitadas_anot = []
    for anot in list(pagina.annots()):
        contenido = anot.info.get("content", "").strip()
        if contenido in anotaciones and fila.intersects(anot.rect):
            quitadas_anot.append(contenido)
            pagina.delete_annot(anot)
    ops_antes = pagina.get_bboxlog()
    pagina.add_redact_annot(fila)
    pagina.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE,
                            graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED,
                            text=pymupdf.PDF_REDACT_TEXT_NONE)
    ops_despues = pagina.get_bboxlog()
    quitados = _quitados(ops_antes, ops_despues)
    if not quitados:
        raise PlantillaV3Invalida(f"'{origen}': no hay trazos dentro de la fila de títulos "
                                  f"{_mm(fila_mm)}; ¿es la plantilla v2 correcta?")
    fuera = [r for r in quitados if not fila.contains(r)]
    if fuera:
        raise PlantillaV3Invalida(f"Se habría borrado algo fuera de la fila de títulos: "
                                  f"{_mm(_rect_papel(fuera[0]))}.")

    # 2. Logo: la misma imagen, corrida en X hasta centrar lo que se ve de ella.
    xref, rect_logo = _logo(doc, pagina)
    crudo = doc.xref_stream_raw(xref)
    x0_vis, x1_vis = _x_visible(doc, xref, rect_logo)
    centro_franja = (franja_x_mm[0] + franja_x_mm[1]) / 2
    centro_antes = (x0_vis + x1_vis) / 2
    dx_mm = round(centro_franja - centro_antes, 3)
    nuevo = rect_logo + (mm_a_pt(dx_mm), 0, mm_a_pt(dx_mm), 0)
    pagina.add_redact_annot(rect_logo)
    pagina.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_REMOVE,
                            graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
                            text=pymupdf.PDF_REDACT_TEXT_NONE)
    # keep_proportion=False: mismo tamaño exacto que en la v2 (si no, PyMuPDF la ajusta a la
    # proporción de sus píxeles y la achica unas centésimas de mm).
    pagina.insert_image(nuevo, xref=xref, keep_proportion=False)

    temporal = destino.with_name(destino.name + ".tmp")
    destino.parent.mkdir(parents=True, exist_ok=True)
    # deflate=False: no se recomprime ningún flujo (con deflate=True PyMuPDF comprime una
    # imagen guardada sin compresión aunque se pida deflate_images=False).
    doc.save(temporal, garbage=3, deflate=False)
    doc.close()
    try:
        centro_despues = _verificar(temporal, referencia, fila, rect_logo, nuevo, crudo)
        if _md5(origen) != md5_antes:
            raise PlantillaV3Invalida(f"El original '{origen}' cambió (MD5); no se usa la salida.")
        if abs(centro_despues - centro_franja) > TOLERANCIA_MM:
            raise PlantillaV3Invalida(f"El logo quedó con centro en X {centro_despues:.2f} mm; "
                                      f"se esperaba {centro_franja:.2f} ±{TOLERANCIA_MM} mm.")
        os.replace(temporal, destino)
    finally:
        if temporal.exists():
            temporal.unlink()
    return InformePlantillaV3(destino, md5_antes, [_rect_papel(r) for r in quitados],
                              quitadas_anot, dx_mm, centro_antes, centro_despues, centro_franja)


def texto_informe(i: InformePlantillaV3, origen: Path | str) -> str:
    lineas = [f"Plantilla v3 creada: {i.destino}",
              f"Origen sin cambios: {origen} (MD5 {i.md5_origen}, igual antes y después).",
              (f"Fila DISEÑADOR | REVISOR: {len(i.trazos_quitados)} trazo(s) borrado(s) (letras y "
               f"línea vertical) y {len(i.anotaciones_quitadas)} anotación(es) "
               f"({', '.join(i.anotaciones_quitadas) or 'ninguna'})."),
              (f"Logo: corrido {i.desplazamiento_logo_mm:+.2f} mm en X (centro visible "
               f"{i.centro_logo_antes_mm:.2f} -> {i.centro_logo_despues_mm:.2f} mm; centro de la "
               f"columna del rótulo {i.centro_franja_mm:.2f} mm). Misma imagen, sin recomprimir."),
              ("Verificación: fuera de la fila y del logo la hoja se ve igual píxel a píxel "
               f"({PPP_COMPARACION} ppp).")]
    return "\n".join(lineas)


# --- auxiliares ---------------------------------------------------------------------------------

def _md5(ruta: Path) -> str:
    return hashlib.md5(ruta.read_bytes()).hexdigest()


def _rect_pdf(r_mm) -> pymupdf.Rect:
    x0, y0, x1, y1 = r_mm
    return pymupdf.Rect(mm_a_pt(x0), mm_a_pt(ALTO_HOJA_MM - y1), mm_a_pt(x1),
                        mm_a_pt(ALTO_HOJA_MM - y0))


def _rect_papel(r) -> tuple[float, float, float, float]:
    r = pymupdf.Rect(r)
    return (round(pt_a_mm(r.x0), 2), round(ALTO_HOJA_MM - pt_a_mm(r.y1), 2),
            round(pt_a_mm(r.x1), 2), round(ALTO_HOJA_MM - pt_a_mm(r.y0), 2))


def _mm(r) -> str:
    x0, y0, x1, y1 = r
    return f"X {x0:.1f}-{x1:.1f} Y {y0:.1f}-{y1:.1f} mm"


def _quitados(antes, despues) -> list[pymupdf.Rect]:
    """Operaciones de dibujo que estaban antes y ya no (comparando por tipo y caja)."""
    restantes = list(despues)
    quitados = []
    for op in antes:
        if op in restantes:
            restantes.remove(op)
        else:
            quitados.append(pymupdf.Rect(op[1]))
    return quitados


def _logo(doc, pagina) -> tuple[int, pymupdf.Rect]:
    imagenes = pagina.get_images(full=True)
    if len(imagenes) != 1:
        raise PlantillaV3Invalida(f"Se esperaba una sola imagen (el logo); la plantilla tiene "
                                  f"{len(imagenes)}.")
    xref = imagenes[0][0]
    rects = pagina.get_image_rects(xref, transform=True)
    if len(rects) != 1:
        raise PlantillaV3Invalida(f"El logo aparece {len(rects)} veces; se esperaba una.")
    rect, m = rects[0]
    if abs(m.b) > 1e-6 or abs(m.c) > 1e-6 or m.a <= 0:
        raise PlantillaV3Invalida("El logo está girado o reflejado; no se sabe centrarlo.")
    return xref, pymupdf.Rect(rect)


def _x_visible(doc, xref: int, rect: pymupdf.Rect) -> tuple[float, float]:
    """X (mm de papel) de la primera y la última columna del logo que se ven."""
    pix = pymupdf.Pixmap(doc, xref)
    if pix.alpha:  # sin alfa para comparar colores
        pix = pymupdf.Pixmap(pix, 0)
    if pix.colorspace is None or pix.colorspace.n != 3:
        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
    ancho, alto, n = pix.width, pix.height, pix.n
    datos = pix.samples_mv
    columnas = []
    for x in range(ancho):
        for y in range(alto):
            i = (y * ancho + x) * n
            if min(datos[i], datos[i + 1], datos[i + 2]) < UMBRAL_BLANCO:
                columnas.append(x)
                break
    if not columnas:
        raise PlantillaV3Invalida("El logo es completamente blanco; no se sabe centrarlo.")
    escala = rect.width / ancho
    return (pt_a_mm(rect.x0 + columnas[0] * escala),
            pt_a_mm(rect.x0 + (columnas[-1] + 1) * escala))


def _verificar(ruta: Path, referencia, fila, logo_antes, logo_despues, crudo) -> float:
    """Revisa lo guardado. Devuelve el centro visible del logo (mm)."""
    doc = pymupdf.open(ruta)
    try:
        pagina = doc[0]
        imagenes = pagina.get_images(full=True)
        if len(imagenes) != 1:
            raise PlantillaV3Invalida(f"Tras reinsertar el logo hay {len(imagenes)} imágenes.")
        xref = imagenes[0][0]
        if doc.xref_stream_raw(xref) != crudo:
            raise PlantillaV3Invalida("La imagen del logo cambió al reinsertarla.")
        # Dónde se PINTA (get_image_rects puede quedar con la posición anterior).
        dibujadas = [pymupdf.Rect(r) for t, r in pagina.get_bboxlog() if "image" in t]
        if len(dibujadas) != 1:
            raise PlantillaV3Invalida(f"El logo se dibuja {len(dibujadas)} veces; se esperaba una.")
        rect = dibujadas[0]
        if max(abs(a - b) for a, b in zip(rect, logo_despues)) > 0.01:
            raise PlantillaV3Invalida(f"El logo no quedó donde se pidió ({_mm(_rect_papel(rect))}; "
                                      f"se pidió {_mm(_rect_papel(logo_despues))}).")
        nueva = pagina.get_pixmap(dpi=PPP_COMPARACION, annots=False)
        excluidas = [fila, logo_antes | logo_despues]
        distintas = _filas_distintas_fuera(referencia, nueva, excluidas)
        if distintas:
            raise PlantillaV3Invalida(f"La hoja cambió fuera de la fila y del logo ({distintas} "
                                      f"fila(s) de píxeles a {PPP_COMPARACION} ppp).")
        x0, x1 = _x_visible(doc, xref, rect)
        return (x0 + x1) / 2
    finally:
        doc.close()


def _filas_distintas_fuera(a, b, excluidas: list[pymupdf.Rect]) -> int:
    """Filas de píxeles con alguna diferencia fuera de los rectángulos `excluidas` (pt)."""
    if (a.width, a.height, a.n) != (b.width, b.height, b.n):
        return a.height
    escala = PPP_COMPARACION / 72
    cajas = [(int(r.x0 * escala) - 1, int(r.y0 * escala) - 1,
              int(r.x1 * escala) + 2, int(r.y1 * escala) + 2) for r in excluidas]
    ancho, n = a.width, a.n
    ma, mb = a.samples_mv, b.samples_mv
    distintas = 0
    for y in range(a.height):
        ra, rb = ma[y * ancho * n:(y + 1) * ancho * n], mb[y * ancho * n:(y + 1) * ancho * n]
        if ra == rb:
            continue
        huecos = sorted((max(x0, 0), min(x1, ancho)) for x0, y0, x1, y1 in cajas if y0 <= y < y1)
        inicio = 0
        for x0, x1 in huecos + [(ancho, ancho)]:
            if ra[inicio * n:x0 * n] != rb[inicio * n:x0 * n]:
                distintas += 1
                break
            inicio = max(inicio, x1)
    return distintas
