"""Escribir en la hoja los textos ya maquetados y verificarlos en el PDF guardado (4.1).

Los textos se escriben como TEXTO real (buscable y seleccionable), con la fuente embebida
completa (`Page.insert_font` + `Page.insert_text`): no se convierten en curvas ni imágenes.

Texto buscable correcto: Arial usa el MISMO glifo para "-" y el guion blando (U+00AD), y
para el espacio y el no separable (U+00A0); PyMuPDF escribe en la tabla ToUnicode de la
fuente el que no es, y al copiar o buscar "ERCO-PSF" no se encontraría. Por eso, después de
escribir, la tabla ToUnicode de NUESTRA fuente (solo la usan estos textos) se reemplaza por
una que asigna a cada glifo usado el carácter que realmente se escribió.

Verificación (sobre el PDF ya guardado, con los caracteres de `get_text("rawdict")`):
  1. Posición: para cada línea se busca su primer carácter en la base esperada (±0,1 mm) y el
     resto de la línea en la misma base, con el mismo texto. Los espacios no se comparan (el
     lector de PDF puede omitirlos).
  2. Celda: la unión de los bboxes de los caracteres de la línea (ancho de avance y caja de
     línea de la fuente: ascenso y descenso) debe quedar dentro del rectángulo de su celda
     (`TextoMaquetado.celda_mm`; en una etiqueta ESC, su caja reservada), ±0,1 mm. Si se
     sale, se dice por qué lado y cuántos mm.
"""

import pymupdf

from componedor.fuente import NOMBRE_EN_PDF, Fuente
from componedor.maquetacion import TextoMaquetado
from componedor.transformaciones import punto_papel_a_pdf, rect_pdf_a_papel
from componedor.unidades import mm_a_pt

TOL_MM = 0.1


def escribir_textos(page: pymupdf.Page, textos: list[TextoMaquetado], fuente: Fuente,
                    alto_hoja_mm: float) -> int:
    """Escribe cada línea en negro. Devuelve cuántas líneas escribió."""
    if not textos:
        return 0
    page.insert_font(fontname=NOMBRE_EN_PDF, fontfile=str(fuente.ruta))
    n = 0
    for texto in textos:
        tamano = fuente.tamano_pt(texto.altura_mm)
        for linea in texto.lineas:
            page.insert_text(punto_papel_a_pdf(*linea.base_mm, alto_hoja_mm), linea.texto,
                             fontname=NOMBRE_EN_PDF, fontsize=tamano, color=(0, 0, 0))
            n += 1
    _corregir_tounicode(page, "".join(l.texto for t in textos for l in t.lineas), fuente)
    return n


def cmap_tounicode(glifos: dict[int, str]) -> bytes:
    """CMap ToUnicode (Identity-H: código = glifo) con una entrada por glifo."""
    entradas = [f"<{g:04x}> <{c.encode('utf-16-be').hex()}>" for g, c in sorted(glifos.items())]
    bloques = []
    for i in range(0, len(entradas), 100):  # máximo 100 por bloque (norma de los CMap)
        parte = entradas[i:i + 100]
        bloques.append(f"{len(parte)} beginbfchar\n" + "\n".join(parte) + "\nendbfchar")
    return ("/CIDInit /ProcSet findresource begin\n12 dict begin\nbegincmap\n"
            "/CIDSystemInfo <</Registry(Adobe)/Ordering(UCS)/Supplement 0>> def\n"
            "/CMapName /Adobe-Identity-UCS def\n/CMapType 2 def\n"
            "1 begincodespacerange\n<0000> <FFFF>\nendcodespacerange\n"
            + "\n".join(bloques)
            + "\nendcmap\nCMapName currentdict /CMap defineresource pop\nend\nend\n"
            ).encode("ascii")


def _corregir_tounicode(page: pymupdf.Page, texto: str, fuente: Fuente) -> None:
    """Reemplaza la tabla ToUnicode de nuestra fuente (ver arriba)."""
    glifos: dict[int, str] = {}
    for c in texto:
        glifos.setdefault(fuente.glifo(c), c)  # si dos caracteres comparten glifo, el primero
    xref = next(f[0] for f in page.get_fonts() if f[4] == NOMBRE_EN_PDF)
    doc = page.parent
    tipo, valor = doc.xref_get_key(xref, "ToUnicode")
    if tipo == "xref":
        doc.update_stream(int(valor.split()[0]), cmap_tounicode(glifos))
    else:
        nuevo = doc.get_new_xref()
        doc.update_object(nuevo, "<<>>")
        doc.update_stream(nuevo, cmap_tounicode(glifos))
        doc.xref_set_key(xref, "ToUnicode", f"{nuevo} 0 R")


def verificar_textos(page: pymupdf.Page, textos: list[TextoMaquetado],
                     alto_hoja_mm: float) -> list[str]:
    """Problemas encontrados (lista vacía si cada línea está en su sitio y dentro de su celda,
    ±0,1 mm)."""
    caracteres = caracteres_de_pagina(page)
    tol = mm_a_pt(TOL_MM)
    problemas = []
    for texto in textos:
        for i, linea in enumerate(texto.lineas, start=1):
            esperado = "".join(c for c in linea.texto if not c.isspace())
            base = punto_papel_a_pdf(*linea.base_mm, alto_hoja_mm)
            leido, en_base = leer_linea(caracteres, linea, alto_hoja_mm)
            donde = f"'{texto.ruta}'" + (f", línea {i}" if len(texto.lineas) > 1 else "")
            if leido != esperado or not en_base or abs(en_base[0][0] - base.x) > tol:
                problemas.append(
                    f"texto {donde}: se esperaba «{linea.texto}» con su base en X "
                    f"{linea.base_mm[0]:.2f}, Y {linea.base_mm[1]:.2f} mm (±{TOL_MM} mm) y allí "
                    f"se lee «{leido}»")
                continue
            if texto.celda_mm is not None:
                medido = _union([caja for _, _, caja in en_base], alto_hoja_mm)
                fuera = fuera_de_celda(medido, texto.celda_mm)
                if fuera:
                    problemas.append(
                        f"texto {donde}: «{linea.texto}» se sale de su celda "
                        f"{_rect(texto.celda_mm)} {' y '.join(fuera)} (medido en el PDF: "
                        f"{_rect(medido)}; tolerancia ±{TOL_MM} mm)")
    return problemas


def leer_linea(caracteres: list, linea, alto_hoja_mm: float) -> tuple[str, list]:
    """Lo que el PDF tiene escrito donde va `linea`: caracteres con su origen en la base de la
    línea (±0,1 mm) y entre su inicio y su fin. Devuelve (texto sin espacios, [(x, carácter,
    bbox)] ordenados de izquierda a derecha)."""
    tol = mm_a_pt(TOL_MM)
    base = punto_papel_a_pdf(*linea.base_mm, alto_hoja_mm)
    fin = base.x + mm_a_pt(linea.ancho_mm) + tol
    en_base = sorted(((x, c, caja) for c, x, y, caja in caracteres
                      if abs(y - base.y) <= tol and base.x - tol <= x <= fin),
                     key=lambda t: t[0])
    return "".join(c for _, c, _ in en_base if not c.isspace()), en_base


def fuera_de_celda(medido: tuple, celda: tuple) -> list[str]:
    """Lados por los que `medido` se sale de `celda` más de la tolerancia (mm de papel, Y
    hacia arriba), p. ej. ["0.30 mm por la derecha"]. Vacía si queda dentro."""
    lados = [(celda[0] - medido[0], "por la izquierda"), (celda[1] - medido[1], "por abajo"),
             (medido[2] - celda[2], "por la derecha"), (medido[3] - celda[3], "por arriba")]
    return [f"{d:.2f} mm {lado}" for d, lado in lados if d > TOL_MM + 1e-9]


def _union(cajas: list[pymupdf.Rect], alto_hoja_mm: float) -> tuple:
    """Caja que encierra a todas (pt) pasada a mm de papel."""
    union = pymupdf.Rect(min(c.x0 for c in cajas), min(c.y0 for c in cajas),
                         max(c.x1 for c in cajas), max(c.y1 for c in cajas))
    return rect_pdf_a_papel(union, alto_hoja_mm)


def _rect(r: tuple) -> str:
    return "X {:.2f} a {:.2f}, Y {:.2f} a {:.2f}".format(r[0], r[2], r[1], r[3])


def caracteres_de_pagina(page: pymupdf.Page) -> list[tuple[str, float, float, pymupdf.Rect]]:
    """(carácter, x, y de su origen en pt, su bbox en pt) de todo el texto de la página."""
    resultado = []
    for bloque in page.get_text("rawdict")["blocks"]:
        for linea in bloque.get("lines", []):
            for span in linea["spans"]:
                for ch in span["chars"]:
                    resultado.append((ch["c"], ch["origin"][0], ch["origin"][1],
                                      pymupdf.Rect(ch["bbox"])))
    return resultado
