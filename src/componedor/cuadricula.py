"""Cuadrícula de coordenadas (vectorial) sobre la ortofoto.

Líneas de Este (verticales) y de Norte (horizontales) cada `intervalo_m`, en el sistema del
DIBUJO, dentro de una región de la hoja: la página de cada detalle con ortofoto o, en modo
extendido, toda el área de dibujo. Como la matriz `cad_to_page` no tiene giro (si lo tiene, no
hay cuadrícula), las líneas quedan paralelas a la hoja.

Estilo copiado del plano de AutoCAD de PRGD (data/input/PRGD-26-1377-GEN-PL-101_1_V0.pdf, leído
con PyMuPDF):

- líneas negras de 0,085 mm, continuas, que cruzan toda la foto (la región entera);
- una etiqueta en CADA línea, en los dos extremos, FUERA de la región: en una franja de 10 mm
  (la distancia entre el marco y el área de dibujo), centrada en ella y en su línea. El Este
  abajo y arriba (horizontal); el Norte a la izquierda y a la derecha, girado 90° (se lee de
  abajo hacia arriba). Sin fondo ni halo (van sobre el papel, no sobre la foto);
- Arial (ArialMT, la fuente del rótulo) de 10 pt exactos (cifras de 2,53 mm); negro;
- formato «4705900.000»: 3 decimales, punto, sin letras.

Una etiqueta que se salga del marco, toque el rótulo (o otra zona no editable), la rosa, una
etiqueta «ESC: 1:N» o la página de otro detalle se omite (y se cuenta). Las líneas van siempre.
"""

import math
from dataclasses import dataclass, field

import pymupdf

from componedor.cad_a_papel import MatrizCad, cad_a_papel
from componedor.formato import RectMM
from componedor.fuente import NOMBRE_EN_PDF, Fuente
from componedor.ortofoto_pdf import caja_cad
from componedor.transformaciones import punto_papel_a_pdf, rect_papel_a_pdf
from componedor.unidades import mm_a_pt

COLOR = (0.0, 0.0, 0.0)  # como en PRGD
GROSOR_MM = 0.085  # como en PRGD
TAMANO_PT = 10.0  # ArialMT de 10 pt en PRGD
EM_MM = TAMANO_PT * 25.4 / 72  # el em de 10 pt, en mm
BANDA_MM = 10.0  # franja de las etiquetas, fuera de la región (marco ↔ área de dibujo)
# Sin la fuente del rótulo (formato sin rótulo): Helvetica, que mide como Arial.
CIFRA_EM = 0.718  # altura de las cifras de Helvetica, en em
ALTURA_TEXTO_MM = EM_MM * CIFRA_EM  # sin la fuente del rótulo (con Arial: 0,7163 em → 2,53 mm)
ANCHOS_EM = {**dict.fromkeys("0123456789", 0.556), ".": 0.278, "-": 0.333}
ESPACIO_MIN_MM = 15.0  # menos que esto entre líneas: se avisa (muy apretada)
MAX_LINEAS = 400
FUENTE_RESERVA = "helv"


@dataclass(frozen=True)
class Etiqueta:
    eje: str  # "E" o "N"
    texto: str
    rect_mm: RectMM  # su caja (cifras: ancho de avance × altura de las cifras)
    base_mm: tuple[float, float]  # inicio de la línea de base del texto
    giro: int  # 0 (Este) o 90 (Norte)


@dataclass
class InformeCuadricula:
    detalle: str
    region_mm: RectMM
    intervalo_m: float
    este: list[float] = field(default_factory=list)  # valores (m) de las líneas verticales
    norte: list[float] = field(default_factory=list)
    lineas_mm: list[tuple[float, float, float, float]] = field(default_factory=list)
    etiquetas: list[Etiqueta] = field(default_factory=list)
    omitidas: int = 0
    avisos: list[str] = field(default_factory=list)


def texto_coordenada(valor_m: float) -> str:
    return f"{valor_m:.3f}"


def altura_mm(fuente: Fuente | None = None) -> float:
    """Altura de las cifras a 10 pt: la caja de cada etiqueta."""
    return EM_MM * (fuente.altura_mayusculas if fuente is not None else CIFRA_EM)


def ancho_texto_mm(texto: str, fuente: Fuente | None = None) -> float:
    """Ancho de avance del texto a 10 pt (con la fuente del rótulo o Helvetica)."""
    if fuente is not None:
        return fuente.ancho_mm(texto, altura_mm(fuente))
    return sum(ANCHOS_EM.get(c, 0.556) for c in texto) * EM_MM


def valores(minimo: float, maximo: float, intervalo: float) -> list[float]:
    """Múltiplos de `intervalo` estrictamente dentro de (minimo, maximo)."""
    eps = intervalo * 1e-9
    k0 = math.floor(minimo / intervalo) + 1
    k1 = math.ceil(maximo / intervalo) - 1
    return [k * intervalo for k in range(k0, k1 + 1) if minimo + eps < k * intervalo < maximo - eps]


def _cruza(a: RectMM, b: RectMM) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _dentro(a: RectMM, b: RectMM) -> bool:
    return a[0] >= b[0] - 1e-9 and a[1] >= b[1] - 1e-9 and a[2] <= b[2] + 1e-9 and a[3] <= b[3] + 1e-9


def armar(ident: str, region: RectMM, ocupado: RectMM, matriz: MatrizCad, mm_por_unidad: float,
          intervalo_m: float, obstaculos: list[RectMM] = (), limite: RectMM | None = None,
          fuente: Fuente | None = None) -> InformeCuadricula:
    """Líneas de la cuadrícula en `region` (mm de papel), con el mapeo CAD → papel del detalle
    (`ocupado` + `matriz`), y sus etiquetas en la franja de afuera. `limite`: de donde no puede
    salir una etiqueta (el marco); `fuente`: la del rótulo (sin ella, Helvetica)."""

    def medir(texto):
        return ancho_texto_mm(texto, fuente)

    informe = InformeCuadricula(ident, region, intervalo_m)
    caja = caja_cad(region, ocupado, matriz)
    if caja is None:
        informe.avisos.append(f"Detalle '{ident}': su dibujo está girado en la página: sin "
                              f"cuadrícula.")
        return informe
    k = mm_por_unidad / 1000.0  # unidades CAD → m
    caja_m = tuple(v * k for v in caja)
    informe.este = valores(caja_m[0], caja_m[2], intervalo_m)
    informe.norte = valores(caja_m[1], caja_m[3], intervalo_m)
    if len(informe.este) + len(informe.norte) > MAX_LINEAS:
        informe.avisos.append(f"Cuadrícula de '{ident}': cada {intervalo_m:g} m saldrían "
                              f"{len(informe.este) + len(informe.norte)} líneas: no se dibuja "
                              f"(aumente el intervalo).")
        informe.este, informe.norte = [], []
        return informe
    alto = ocupado[3] - ocupado[1]

    def a_papel(x_m, y_m):
        return cad_a_papel(x_m / k, y_m / k, ocupado[:2], alto, matriz)

    x0, y0, x1, y1 = region
    xs = [a_papel(e, caja_m[1])[0] for e in informe.este]
    ys = [a_papel(caja_m[0], n)[1] for n in informe.norte]
    informe.lineas_mm = [(x, y0, x, y1) for x in xs] + [(x0, y, x1, y) for y in ys]
    h, mitad = altura_mm(fuente), BANDA_MM / 2
    candidatas = []
    for e, x in zip(informe.este, xs, strict=True):
        t = texto_coordenada(e)
        w = medir(t)
        for yb in (y0 - mitad - h / 2, y1 + mitad - h / 2):  # abajo y arriba de la región
            candidatas.append(Etiqueta("E", t, (x - w / 2, yb, x + w / 2, yb + h), (x - w / 2, yb), 0))
    for n, y in zip(informe.norte, ys, strict=True):
        t = texto_coordenada(n)
        w = medir(t)
        for xb in (x0 - mitad + h / 2, x1 + mitad + h / 2):  # base: las cifras, a su izquierda
            candidatas.append(Etiqueta("N", t, (xb - h, y - w / 2, xb, y + w / 2), (xb, y - w / 2),
                                       90))
    puestas: list[RectMM] = []
    for et in candidatas:
        if ((limite is not None and not _dentro(et.rect_mm, limite))
                or any(_cruza(et.rect_mm, o) for o in obstaculos)
                or any(_cruza(et.rect_mm, p) for p in puestas)):
            informe.omitidas += 1
            continue
        informe.etiquetas.append(et)
        puestas.append(et.rect_mm)
    paso_mm = intervalo_m / k * abs(matriz.a)  # intervalo en unidades CAD × mm de papel por unidad
    if not informe.lineas_mm:
        informe.avisos.append(f"Cuadrícula de '{ident}': cada {intervalo_m:g} m no cae ninguna "
                              f"línea en la caja (reduzca el intervalo).")
    elif paso_mm < ESPACIO_MIN_MM:
        informe.avisos.append(f"Cuadrícula de '{ident}': cada {intervalo_m:g} m las líneas "
                              f"quedan a {paso_mm:.1f} mm: muy apretadas (aumente el intervalo).")
    if informe.omitidas:
        informe.avisos.append(f"Cuadrícula de '{ident}': se omitieron {informe.omitidas} "
                              f"etiqueta(s) que se salían del marco o chocaban con el rótulo, "
                              f"otro detalle, la rosa, una etiqueta de escala u otra etiqueta.")
    return informe


def dibujar(page: pymupdf.Page, alto_hoja_mm: float, informe: InformeCuadricula,
            fuente: Fuente | None = None) -> None:
    """Las líneas (una forma) y las etiquetas, con la fuente del rótulo (embebida una sola vez:
    la misma de los textos; ver textos_pdf.corregir_tounicode) o, sin ella, Helvetica."""
    if informe.lineas_mm:
        forma = page.new_shape()
        for x0, y0, x1, y1 in informe.lineas_mm:
            forma.draw_line(punto_papel_a_pdf(x0, y0, alto_hoja_mm),
                            punto_papel_a_pdf(x1, y1, alto_hoja_mm))
        forma.finish(color=COLOR, width=mm_a_pt(GROSOR_MM), closePath=False)
        forma.commit()
    if not informe.etiquetas:
        return
    nombre = FUENTE_RESERVA
    if fuente is not None:
        page.insert_font(fontname=NOMBRE_EN_PDF, fontfile=str(fuente.ruta))
        nombre = NOMBRE_EN_PDF
    for et in informe.etiquetas:
        page.insert_text(punto_papel_a_pdf(*et.base_mm, alto_hoja_mm), et.texto,
                         fontname=nombre, fontsize=TAMANO_PT, rotate=et.giro,
                         color=COLOR)


def verificar(page: pymupdf.Page, informes: list[InformeCuadricula],
              alto_hoja_mm: float) -> list[str]:
    """En el PDF guardado: cada etiqueta se lee, con su texto, dentro de su fondo."""
    problemas = []
    for inf in informes:
        for et in inf.etiquetas:
            r = et.rect_mm  # con medio milímetro de holgura (ascenso y descenso de la fuente)
            clip = rect_papel_a_pdf((r[0] - 0.5, r[1] - 0.5, r[2] + 0.5, r[3] + 0.5), alto_hoja_mm)
            palabras = [w[4] for w in page.get_text("words", clip=clip)]
            if et.texto not in palabras:
                problemas.append(f"cuadrícula de '{inf.detalle}': falta la etiqueta {et.texto} "
                                 f"({'Este' if et.eje == 'E' else 'Norte'}) en X "
                                 f"{et.rect_mm[0]:.2f}, Y {et.rect_mm[1]:.2f} mm")
    return problemas
