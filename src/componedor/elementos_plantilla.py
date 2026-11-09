"""Detectar los elementos fijos de la plantilla que caen dentro del área de dibujo.

La plantilla del rótulo trae cosas dentro de `area_dibujo` (en la v2, la rosa de los vientos;
la v1 traía además el recuadro «LAYERS AUTORIZADOS») que un detalle puede tapar. Aquí se
MIDEN (no se inventan): se coloca la plantilla en la hoja igual que en `componer`
(`composicion.hoja_base`), se toman trazos, textos e imágenes cuyo rectángulo cae dentro
del área de dibujo, sin el propio borde del área, y se agrupan por cercanía.

Los candidatos se revisan a ojo con el PDF de verificación antes de copiarlos a
`elementos_plantilla` del formato. Rectángulo exacto, sin holgura.
"""

from dataclasses import dataclass, field, replace
from pathlib import Path

import pymupdf

from componedor.composicion import hoja_base
from componedor.formato import Formato, RectMM
from componedor.transformaciones import rect_papel_a_pdf, rect_pdf_a_papel

ZONA = "area_dibujo"
DISTANCIA_GRUPO_MM = 3.0  # piezas a menos de esto se juntan en un mismo elemento
TOL_BORDE_MM = 0.5  # un trazo así de parecido al área es su propio borde, no un elemento


@dataclass
class Candidato:
    rect: RectMM  # mm de papel, Y hacia arriba
    trazos: int = 0
    imagenes: int = 0
    textos: list[str] = field(default_factory=list)


def detectar_elementos(formato: Formato) -> list[Candidato]:
    """Candidatos a elemento fijo dentro de `area_dibujo`, ordenados de arriba abajo y de
    izquierda a derecha. Requiere que el formato tenga plantilla."""
    if formato.plantilla is None:
        raise ValueError("El formato no tiene plantilla: no hay elementos que detectar.")
    area = formato.zonas[ZONA]
    # Solo la plantilla: sin elementos ya declarados que pudieran dibujarse.
    doc, _ = hoja_base(replace(formato, elementos_plantilla=()))
    try:
        page = doc[0]
        piezas: list[Candidato] = []
        for trazo in page.get_drawings():
            rect = rect_pdf_a_papel(trazo["rect"], formato.alto_mm)
            if _dentro(rect, area) and not _es_borde_del_area(rect, area):
                piezas.append(Candidato(rect, trazos=1))
        for bloque in page.get_text("blocks"):
            rect = rect_pdf_a_papel(pymupdf.Rect(bloque[:4]), formato.alto_mm)
            if _dentro(rect, area) and bloque[4].strip():
                piezas.append(Candidato(rect, textos=[bloque[4].strip().replace("\n", " ")]))
        for imagen in page.get_image_info():
            rect = rect_pdf_a_papel(pymupdf.Rect(imagen["bbox"]), formato.alto_mm)
            if _dentro(rect, area):
                piezas.append(Candidato(rect, imagenes=1))
    finally:
        doc.close()
    grupos = _agrupar(piezas)
    return sorted(grupos, key=lambda c: (-c.rect[3], c.rect[0]))


def pdf_verificacion(formato: Formato, candidatos: list[Candidato], salida: Path) -> None:
    """La hoja con la plantilla y cada candidato dibujado en rojo y rotulado con su número
    y sus coordenadas (mm de papel)."""
    doc, _ = hoja_base(replace(formato, elementos_plantilla=()))
    try:
        page = doc[0]
        rojo = (0.85, 0.0, 0.0)
        area = rect_papel_a_pdf(formato.zonas[ZONA], formato.alto_mm)
        page.draw_rect(area, color=(0.0, 0.4, 0.9), width=0.6, dashes="[4 2] 0")
        page.insert_text(area.tl + (4, 12), f"{ZONA} (en azul)", fontsize=9, color=(0.0, 0.4, 0.9))
        for i, c in enumerate(candidatos, start=1):
            rect = rect_papel_a_pdf(c.rect, formato.alto_mm)
            page.draw_rect(rect, color=rojo, width=0.8)
            etiqueta = (f"{i}: X {c.rect[0]:.2f}-{c.rect[2]:.2f}, "
                        f"Y {c.rect[1]:.2f}-{c.rect[3]:.2f} mm")
            # Etiqueta encima del rectángulo, alineada a su derecha para no salir de la hoja.
            ancho = pymupdf.get_text_length(etiqueta, fontsize=7)
            page.insert_text((rect.x1 - ancho, rect.y0 - 3), etiqueta, fontsize=7, color=rojo)
        salida.parent.mkdir(parents=True, exist_ok=True)
        doc.save(salida)
    finally:
        doc.close()


def _dentro(rect: RectMM, area: RectMM) -> bool:
    return (rect[0] >= area[0] - TOL_BORDE_MM and rect[1] >= area[1] - TOL_BORDE_MM
            and rect[2] <= area[2] + TOL_BORDE_MM and rect[3] <= area[3] + TOL_BORDE_MM)


def _es_borde_del_area(rect: RectMM, area: RectMM) -> bool:
    return all(abs(a - b) <= TOL_BORDE_MM for a, b in zip(rect, area))


def _cerca(a: RectMM, b: RectMM) -> bool:
    d = DISTANCIA_GRUPO_MM
    return a[0] - d <= b[2] and b[0] - d <= a[2] and a[1] - d <= b[3] and b[1] - d <= a[3]


def _agrupar(piezas: list[Candidato]) -> list[Candidato]:
    """Junta piezas cercanas hasta que ningún par de grupos quede a menos de la distancia."""
    grupos = list(piezas)
    cambio = True
    while cambio:
        cambio = False
        for i in range(len(grupos)):
            for j in range(i + 1, len(grupos)):
                if _cerca(grupos[i].rect, grupos[j].rect):
                    a, b = grupos[i], grupos.pop(j)
                    grupos[i] = Candidato(
                        (min(a.rect[0], b.rect[0]), min(a.rect[1], b.rect[1]),
                         max(a.rect[2], b.rect[2]), max(a.rect[3], b.rect[3])),
                        a.trazos + b.trazos, a.imagenes + b.imagenes, a.textos + b.textos)
                    cambio = True
                    break
            if cambio:
                break
    return grupos
