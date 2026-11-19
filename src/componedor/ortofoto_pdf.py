"""La ortofoto en el PDF: detrás de los detalles, recortada a la página de cada uno.

Orden en la hoja: plantilla → ortofoto → detalles (vectores) → rótulo. `componer` llama a
`poner_ortofoto` después de la hoja base y antes de insertar los detalles.

Por cada detalle:

1. Su página en la hoja (`ocupado`, mm de papel) se lleva a coordenadas CAD con la inversa de
   su matriz `cad_to_page` (no se supone ningún margen: es la página entera del paquete).
   Si la matriz está girada, no se pone ortofoto (advertencia).
2. Se arma una CUADRÍCULA de la página a `ppp` píxeles por pulgada de papel (300 por defecto,
   `componedor.json` → `ortofoto.ppp`), en MOSAICOS de 1024 px. Cada mosaico se pinta aparte
   (`ortofoto_render.pintar`, por ventanas, con la misma reducción entera para todo el detalle:
   no se notan las uniones), así la memoria no depende del tamaño del detalle ni de la
   ortofoto.
3. Cada mosaico va como JPEG (calidad `ortofoto.calidad_jpeg`, 85) con `insert_image`: el JPEG
   entra tal cual (DCTDecode). Si tiene partes sin foto o la opacidad es menor que 1, lleva una
   máscara (SMask) con alfa = cubierto × opacidad. Un mosaico sin nada de foto no se pone.

Los detalles siguen siendo vectores: la ortofoto son imágenes aparte, debajo de ellos.
"""

from dataclasses import dataclass, field

import numpy as np
import pymupdf
from rasterio.crs import CRS

from componedor.cad_a_papel import MatrizCad, MatrizNoInvertible
from componedor.formato import RectMM
from componedor.ortofoto_render import Fuente, pintar
from componedor.transformaciones import (
    punto_papel_a_pagina,
    rect_papel_a_pdf,
    rect_pdf_a_papel,
)

LADO_MOSAICO_PX = 1024
MM_POR_PULGADA = 25.4


@dataclass(frozen=True)
class DetalleOrtofoto:
    """Lo que hace falta de un detalle colocado para poner la ortofoto detrás."""
    id: str
    ocupado: RectMM  # página del detalle en la hoja (mm de papel, Y arriba)
    matriz: MatrizCad  # cad_to_page del manifiesto
    mm_por_unidad: float  # mm reales por unidad CAD (1000 si el dibujo está en m)
    tiene_fondo: bool = False  # paquete antiguo con fondo blanco: tapa la ortofoto


@dataclass(frozen=True)
class Mosaico:
    columnas: tuple[int, int]  # [c0, c1) en la cuadrícula del detalle
    filas: tuple[int, int]  # [f0, f1), fila 0 arriba
    rect_mm: RectMM  # en la hoja (mm de papel, Y arriba)


@dataclass(frozen=True)
class MosaicoPuesto:
    detalle: str
    rect_mm: RectMM
    px: tuple[int, int]
    bytes_jpeg: int
    con_mascara: bool


@dataclass
class InformeOrtofoto:
    ppp: int
    calidad_jpeg: int
    opacidad: float
    mosaicos: list[MosaicoPuesto] = field(default_factory=list)
    cobertura: dict[str, float] = field(default_factory=dict)  # por detalle, 0 a 1
    px: dict[str, tuple[int, int]] = field(default_factory=dict)  # cuadrícula de cada detalle
    avisos: list[str] = field(default_factory=list)
    fuente: str = "original"  # "original" o "copia"
    archivo: str = ""

    @property
    def bytes_jpeg(self) -> int:
        return sum(m.bytes_jpeg for m in self.mosaicos)


def papel_a_cad(punto_mm, ocupado: RectMM, matriz: MatrizCad) -> tuple[float, float]:
    """Un punto de la hoja (mm de papel) → CAD, con la página del detalle en `ocupado`."""
    alto = ocupado[3] - ocupado[1]
    x_pag, y_pag = punto_papel_a_pagina(punto_mm[0], punto_mm[1], alto, ocupado[:2])
    return matriz.pagina_a_cad(x_pag, y_pag)


def caja_cad(rect_mm: RectMM, ocupado: RectMM, matriz: MatrizCad) -> tuple[float, ...] | None:
    """La caja CAD que cubre `rect_mm` (un trozo de la página del detalle), o None si la matriz
    está girada (b o c ≠ 0) o no se puede invertir."""
    if matriz.b != 0 or matriz.c != 0:
        return None
    try:
        esquinas = [papel_a_cad(p, ocupado, matriz) for p in
                    ((rect_mm[0], rect_mm[1]), (rect_mm[2], rect_mm[3]))]
    except MatrizNoInvertible:
        return None
    xs, ys = [p[0] for p in esquinas], [p[1] for p in esquinas]
    return min(xs), min(ys), max(xs), max(ys)


def cuadricula(ocupado: RectMM, ppp: int, lado: int = LADO_MOSAICO_PX
               ) -> tuple[tuple[int, int], list[Mosaico]]:
    """((ancho_px, alto_px), mosaicos) de la página a `ppp`. El último de cada fila y columna
    puede ser más chico; juntos cubren la página exacta."""
    ancho_mm, alto_mm = ocupado[2] - ocupado[0], ocupado[3] - ocupado[1]
    ancho = max(1, round(ancho_mm * ppp / MM_POR_PULGADA))
    alto = max(1, round(alto_mm * ppp / MM_POR_PULGADA))
    mosaicos = []
    for f0 in range(0, alto, lado):
        f1 = min(alto, f0 + lado)
        for c0 in range(0, ancho, lado):
            c1 = min(ancho, c0 + lado)
            rect = (ocupado[0] + c0 * ancho_mm / ancho, ocupado[3] - f1 * alto_mm / alto,
                    ocupado[0] + c1 * ancho_mm / ancho, ocupado[3] - f0 * alto_mm / alto)
            mosaicos.append(Mosaico((c0, c1), (f0, f1), rect))
    return (ancho, alto), mosaicos


def jpeg(rgb: np.ndarray, calidad: int) -> bytes:
    alto, ancho = rgb.shape[1:]
    muestras = np.ascontiguousarray(np.moveaxis(rgb, 0, -1))
    return pymupdf.Pixmap(pymupdf.csRGB, ancho, alto, muestras.tobytes(), False).tobytes(
        "jpg", jpg_quality=calidad)


def mascara_png(alfa: np.ndarray, opacidad: float) -> bytes:
    alto, ancho = alfa.shape
    valores = np.round(alfa.astype(np.float64) * opacidad).astype(np.uint8)
    return pymupdf.Pixmap(pymupdf.csGRAY, ancho, alto, valores.tobytes(), False).tobytes("png")


def en_metros(caja, mm_por_unidad: float) -> tuple[float, ...]:
    k = mm_por_unidad / 1000.0
    return tuple(v * k for v in caja)


def poner_ortofoto(page: pymupdf.Page, alto_hoja_mm: float, detalles: list[DetalleOrtofoto],
                   fuentes: dict[str, Fuente], crs_dibujo: CRS, ppp: int = 300,
                   calidad: int = 85, opacidad: float = 1.0,
                   lado: int = LADO_MOSAICO_PX) -> InformeOrtofoto:
    """Pone la ortofoto detrás de cada detalle (en el orden de `detalles`). `fuentes`: la
    ortofoto abierta de cada detalle (la misma para todos con el original; una por detalle con
    la copia). Un detalle sin fuente no lleva ortofoto."""
    informe = InformeOrtofoto(ppp, calidad, opacidad)
    for det in detalles:
        fuente = fuentes.get(det.id)
        if fuente is None:
            continue
        caja = caja_cad(det.ocupado, det.ocupado, det.matriz)
        if caja is None:
            informe.avisos.append(f"Detalle '{det.id}': su dibujo está girado en la página "
                                  f"(matriz con giro): no lleva ortofoto.")
            continue
        (ancho, alto), mosaicos = cuadricula(det.ocupado, ppp, lado)
        informe.px[det.id] = (ancho, alto)
        factor = fuente.factor(en_metros(caja, det.mm_por_unidad), ancho, alto, crs_dibujo)
        cubiertos = 0
        for m in mosaicos:
            sub = en_metros(caja_cad(m.rect_mm, det.ocupado, det.matriz), det.mm_por_unidad)
            w, h = m.columnas[1] - m.columnas[0], m.filas[1] - m.filas[0]
            rgb, alfa = pintar(fuente, sub, w, h, crs_dibujo, factor)
            n = int(np.count_nonzero(alfa))
            cubiertos += n
            if n == 0:
                continue
            datos = jpeg(rgb, calidad)
            completa = n == alfa.size and opacidad >= 1.0
            mascara = None if completa else mascara_png(alfa, opacidad)
            page.insert_image(rect_papel_a_pdf(m.rect_mm, alto_hoja_mm), stream=datos,
                              mask=mascara, keep_proportion=False)
            informe.mosaicos.append(MosaicoPuesto(det.id, m.rect_mm, (w, h), len(datos),
                                                  mascara is not None))
        informe.cobertura[det.id] = cubiertos / (ancho * alto)
        if informe.cobertura[det.id] == 0:
            informe.avisos.append(f"La ortofoto no cubre el detalle '{det.id}'.")
        elif det.tiene_fondo:
            informe.avisos.append(f"El detalle '{det.id}' tiene fondo blanco de página (paquete "
                                  f"antiguo): tapa la ortofoto. Vuelva a exportarlo.")
    return informe


TOL_MM = 0.1


def verificar_ortofoto(page: pymupdf.Page, informe: InformeOrtofoto | None,
                       alto_hoja_mm: float) -> list[str]:
    """En el PDF guardado: cada mosaico es una imagen JPEG (DCTDecode) justo en su rectángulo
    (±0,1 mm). Devuelve los problemas."""
    if informe is None or not informe.mosaicos:
        return []
    doc = page.parent
    imagenes = []
    for img in page.get_images(full=True):
        filtro = doc.xref_get_key(img[0], "Filter")[1]
        for r in page.get_image_rects(img[0]):
            imagenes.append((rect_pdf_a_papel(r, alto_hoja_mm), filtro))
    problemas = []
    for m in informe.mosaicos:
        cerca = [f for r, f in imagenes if max(abs(a - b) for a, b in zip(r, m.rect_mm)) <= TOL_MM]
        if not cerca:
            problemas.append(f"ortofoto del detalle '{m.detalle}': falta el mosaico en "
                             f"X {m.rect_mm[0]:.2f} a {m.rect_mm[2]:.2f}, Y {m.rect_mm[1]:.2f} a "
                             f"{m.rect_mm[3]:.2f} mm")
        elif "/DCTDecode" not in cerca:
            problemas.append(f"ortofoto del detalle '{m.detalle}': el mosaico en "
                             f"X {m.rect_mm[0]:.2f}, Y {m.rect_mm[1]:.2f} mm no quedó en JPEG")
    return problemas
