"""Comprobaciones de la hoja compuesta contra geometría conocida.

Cada comprobación devuelve `Comprobacion(seccion, nombre, pasa, esperado, medido,
tolerancia)`. Todo se mide sobre el PDF ya guardado, con `get_drawings()`,
`get_image_info()` y `search_for()`. Lo esperado se calcula aquí de forma independiente
(matriz + ancla), no se copia de lo que hizo la composición.
"""

import math
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

from componedor import referencia as ref
from componedor.cad_a_papel import cad_a_papel, limites_dibujo_en_papel, origen_para_ancla
from componedor.colocar import DetalleInvalido, abrir_pdf, colocar_detalle, tamano_visible_mm
from componedor.comprobacion_dibujo import trazos_sin_fondo
from componedor.formato import Formato, RectMM
from componedor.hoja import crear_pagina
from componedor.manifiesto import leer_manifiesto
from componedor.plantilla import (
    TOLERANCIA_MARCO_MM,
    TOLERANCIA_TAMANO_MM,
    InformePlantilla,
    buscar_marco,
)
from componedor.transformaciones import PuntoMM, rect_papel_a_pdf, rect_pdf_a_papel

TOL_MM = 0.1
TOL_ESCALA_RELATIVA = 0.0005
TOL_DETALLE_REAL_MM = 0.2
VENTANA_BUSQUEDA_MM = 5.0  # para reconocer una figura aunque esté mal medida


@dataclass(frozen=True)
class Comprobacion:
    seccion: str
    nombre: str
    pasa: bool
    esperado: str
    medido: str
    tolerancia: str
    detalle: str = ""  # explicación para la persona (integridad y coherencia)


@dataclass
class ResultadoVerificacion:
    """Resultado de una verificación de paquete (integridad o coherencia)."""

    prefijo: str
    verificable: bool
    comprobaciones: list[Comprobacion] = field(default_factory=list)
    motivo: str = ""  # por qué no es verificable
    datos: dict = field(default_factory=dict)  # medidas numéricas para informar

    @property
    def pasa(self) -> bool:
        return self.verificable and all(c.pasa for c in self.comprobaciones)

    @property
    def etiqueta(self) -> str:
        """Para las columnas del CLI: OK, FALLA o — (no verificable)."""
        if not self.verificable:
            return "—"
        return "OK" if self.pasa else "FALLA"

    @property
    def fallas(self) -> list[Comprobacion]:
        return [c for c in self.comprobaciones if not c.pasa]


def _r(rect: RectMM) -> str:
    return "X {:.3f} a {:.3f}, Y {:.3f} a {:.3f}".format(rect[0], rect[2], rect[1], rect[3])


def _cerca(a, b, tol) -> bool:
    return all(abs(x - y) <= tol for x, y in zip(a, b))


# --- Hoja y marco ---------------------------------------------------------------------

def comprobar_hoja(doc: pymupdf.Document, formato: Formato) -> list[Comprobacion]:
    page = doc[0]
    ancho, alto = (rect_pdf_a_papel(page.rect, formato.alto_mm)[i] for i in (2, 3))
    return [
        Comprobacion("Hoja", "Número de páginas", doc.page_count == 1, "1",
                     str(doc.page_count), "exacto"),
        Comprobacion("Hoja", "Tamaño de la hoja",
                     _cerca((ancho, alto), (formato.ancho_mm, formato.alto_mm), TOL_MM),
                     f"{formato.ancho_mm:.3f} x {formato.alto_mm:.3f} mm",
                     f"{ancho:.3f} x {alto:.3f} mm", f"±{TOL_MM} mm"),
        Comprobacion("Hoja", "Rotación de la página", page.rotation == 0, "0",
                     str(page.rotation), "exacto"),
    ]


def comprobar_marco(page: pymupdf.Page, formato: Formato, con_plantilla: bool) -> list[Comprobacion]:
    """Sin plantilla: nuestro marco a ±0,1 mm. Con plantilla: el del rótulo a ±0,5 mm
    (misma búsqueda que la validación cruzada de plantilla.py)."""
    tol = TOLERANCIA_MARCO_MM if con_plantilla else TOL_MM
    nombre = "Marco del rótulo vs formato" if con_plantilla else "Marco dibujado vs formato"
    encontrado = buscar_marco(page, formato)
    if encontrado is None:
        return [Comprobacion("Marco", nombre, False, _r(formato.marco), "sin trazos",
                             f"±{tol} mm")]
    leido, diferencia = encontrado
    return [Comprobacion("Marco", nombre, max(abs(d) for d in diferencia) <= tol,
                         _r(formato.marco), _r(leido), f"±{tol} mm")]


def comprobar_plantilla(informe: InformePlantilla) -> list[Comprobacion]:
    dx, dy = informe.diferencia_tamano_mm
    ancho, alto = informe.tamano_mm
    return [Comprobacion(
        "Plantilla", "Tamaño de la plantilla vs hoja",
        abs(dx) <= TOLERANCIA_TAMANO_MM and abs(dy) <= TOLERANCIA_TAMANO_MM,
        f"{ancho - dx:.3f} x {alto - dy:.3f} mm", f"{ancho:.3f} x {alto:.3f} mm",
        f"±{TOLERANCIA_TAMANO_MM} mm (redondeo de AutoCAD)")]


# --- Detalle de referencia -------------------------------------------------------------

def _figuras_del_detalle(page: pymupdf.Page, alto_hoja: float,
                         region: RectMM) -> list[tuple[dict, RectMM]]:
    """Trazos dentro de la región del detalle (con holgura), sin su fondo blanco."""
    fondo = rect_papel_a_pdf(region, alto_hoja)
    holgura = VENTANA_BUSQUEDA_MM
    figuras = []
    for trazo in trazos_sin_fondo(page, fondo):
        r = rect_pdf_a_papel(trazo["rect"], alto_hoja)
        if (r[0] >= region[0] - holgura and r[1] >= region[1] - holgura
                and r[2] <= region[2] + holgura and r[3] <= region[3] + holgura):
            figuras.append((trazo, r))
    return figuras


def _buscar_contorno(figuras, ancho: float, alto: float) -> RectMM | None:
    """Contorno (no relleno, más de un segmento) de tamaño más parecido a ancho x alto."""
    mejor, error = None, VENTANA_BUSQUEDA_MM
    for trazo, r in figuras:
        if trazo.get("fill") is not None or len(trazo["items"]) == 1 and trazo["items"][0][0] == "l":
            continue
        e = max(abs((r[2] - r[0]) - ancho), abs((r[3] - r[1]) - alto))
        if e <= error:
            mejor, error = r, e
    return mejor


def _comprobar_figura(nombre: str, figuras, cad: RectMM, origen: PuntoMM,
                      detalle: ref.DetalleReferencia) -> tuple[list[Comprobacion], RectMM | None]:
    esperado = (*cad_a_papel(cad[0], cad[1], origen, detalle.alto_pagina_mm, detalle.matriz),
                *cad_a_papel(cad[2], cad[3], origen, detalle.alto_pagina_mm, detalle.matriz))
    ancho, alto = esperado[2] - esperado[0], esperado[3] - esperado[1]
    medido = _buscar_contorno(figuras, ancho, alto)
    seccion = "Detalle de referencia"
    if medido is None:
        return [Comprobacion(seccion, f"{nombre}: tamaño", False, f"{ancho:.3f} x {alto:.3f} mm",
                             "no encontrado", f"±{TOL_MM} mm")], None
    m_ancho, m_alto = medido[2] - medido[0], medido[3] - medido[1]
    return [
        Comprobacion(seccion, f"{nombre}: tamaño", _cerca((m_ancho, m_alto), (ancho, alto), TOL_MM),
                     f"{ancho:.3f} x {alto:.3f} mm", f"{m_ancho:.3f} x {m_alto:.3f} mm",
                     f"±{TOL_MM} mm"),
        Comprobacion(seccion, f"{nombre}: esquina inferior izquierda",
                     _cerca(medido[:2], esperado[:2], TOL_MM),
                     f"({esperado[0]:.3f}, {esperado[1]:.3f}) mm",
                     f"({medido[0]:.3f}, {medido[1]:.3f}) mm", f"±{TOL_MM} mm"),
    ], medido


def comprobar_detalle_referencia(page: pymupdf.Page, formato: Formato,
                                 detalle: ref.DetalleReferencia,
                                 ancla_papel: PuntoMM) -> list[Comprobacion]:
    """Cuadrado, rectángulo, escala y orientación del detalle de referencia en la hoja."""
    esquina_cad = ref.CUADRADO_CAD[:2]
    origen = origen_para_ancla(esquina_cad, ancla_papel, detalle.matriz, detalle.alto_pagina_mm)
    region = (origen[0], origen[1], origen[0] + detalle.ancho_pagina_mm,
              origen[1] + detalle.alto_pagina_mm)
    figuras = _figuras_del_detalle(page, formato.alto_mm, region)

    resultado, cuadrado = _comprobar_figura("Cuadrado 5 x 5 m", figuras, ref.CUADRADO_CAD,
                                            origen, detalle)
    filas_rect, rectangulo = _comprobar_figura("Rectángulo 5 x 2 m", figuras,
                                               ref.RECTANGULO_CAD, origen, detalle)
    resultado += filas_rect
    resultado.append(_comprobar_escala(cuadrado, rectangulo))
    resultado.append(_comprobar_orientacion(figuras, origen, detalle))
    return resultado


def _comprobar_escala(cuadrado: RectMM | None, rectangulo: RectMM | None) -> Comprobacion:
    """1:N medida = distancia CAD (m) x 1000 / distancia en la hoja (mm)."""
    tol = f"diferencia relativa < {TOL_ESCALA_RELATIVA}"
    if cuadrado is None or rectangulo is None:
        return Comprobacion("Escala", "Escala medida", False, f"1:{ref.ESCALA}",
                            "no se pudo medir", tol)
    # Esquina inferior izquierda del cuadrado -> esquina superior derecha del rectángulo.
    d_cad = math.dist(ref.CUADRADO_CAD[:2], ref.RECTANGULO_CAD[2:])
    d_papel = math.dist(cuadrado[:2], rectangulo[2:])
    denominador = d_cad * 1000 / d_papel
    relativa = abs(denominador - ref.ESCALA) / ref.ESCALA
    return Comprobacion("Escala", f"Escala medida ({d_cad:.3f} m CAD / {d_papel:.3f} mm)",
                        relativa < TOL_ESCALA_RELATIVA, f"1:{ref.ESCALA}",
                        f"1:{denominador:.4f} (dif. relativa {relativa:.6f})", tol)


def _comprobar_orientacion(figuras, origen: PuntoMM,
                           detalle: ref.DetalleReferencia) -> Comprobacion:
    m = ref.MARCA_CAD
    e0 = cad_a_papel(m[0], m[1], origen, detalle.alto_pagina_mm, detalle.matriz)
    e1 = cad_a_papel(m[2], m[3], origen, detalle.alto_pagina_mm, detalle.matriz)
    esperado = ((e0[0] + e1[0]) / 2, (e0[1] + e1[1]) / 2, e1[0] - e0[0], e1[1] - e0[1])
    texto_esperado = (f"centro ({esperado[0]:.3f}, {esperado[1]:.3f}), "
                      f"{esperado[2]:.3f} x {esperado[3]:.3f} mm (arriba-izquierda del cuadrado)")
    marcas = [r for t, r in figuras if t.get("fill") == ref.COLOR_MARCA]
    if len(marcas) != 1:
        return Comprobacion("Detalle de referencia", "Orientación (marca asimétrica)", False,
                            texto_esperado, f"{len(marcas)} marcas encontradas", f"±{TOL_MM} mm")
    r = marcas[0]
    medido = ((r[0] + r[2]) / 2, (r[1] + r[3]) / 2, r[2] - r[0], r[3] - r[1])
    return Comprobacion("Detalle de referencia", "Orientación (marca asimétrica)",
                        _cerca(medido, esperado, TOL_MM), texto_esperado,
                        f"centro ({medido[0]:.3f}, {medido[1]:.3f}), "
                        f"{medido[2]:.3f} x {medido[3]:.3f} mm", f"±{TOL_MM} mm")


# --- Vector y texto --------------------------------------------------------------------

def comprobar_vector(page: pymupdf.Page, imagenes_plantilla: int) -> list[Comprobacion]:
    imagenes = len(page.get_image_info())
    encontrados = page.search_for(ref.TEXTO)
    return [
        Comprobacion("Vector", "Sin rasterizar: imágenes en la hoja",
                     imagenes == imagenes_plantilla,
                     f"{imagenes_plantilla} (solo las de la plantilla)", str(imagenes), "exacto"),
        Comprobacion("Vector", f"Texto «{ref.TEXTO}» como texto real",
                     len(encontrados) == 1 and ref.TEXTO in page.get_text(),
                     "1 aparición", f"{len(encontrados)} aparición(es)", "exacto"),
    ]


# --- Todo junto ------------------------------------------------------------------------

def validar_hoja_referencia(doc: pymupdf.Document, formato: Formato,
                            detalle: ref.DetalleReferencia, ancla_papel: PuntoMM,
                            informe_plantilla: InformePlantilla | None,
                            imagenes_plantilla: int) -> list[Comprobacion]:
    page = doc[0]
    comprobaciones = comprobar_hoja(doc, formato)
    comprobaciones += comprobar_marco(page, formato, informe_plantilla is not None)
    if informe_plantilla is not None:
        comprobaciones += comprobar_plantilla(informe_plantilla)
    comprobaciones += comprobar_detalle_referencia(page, formato, detalle, ancla_papel)
    comprobaciones += comprobar_vector(page, imagenes_plantilla)
    return comprobaciones


def validar_detalle_real(formato: Formato, ruta_detalle: Path,
                         ruta_manifiesto: Path) -> list[Comprobacion]:
    """Coloca el detalle real centrado en una hoja limpia (sin plantilla ni marco) y compara
    con su manifiesto: tamaño de página y límites del dibujo en papel."""
    manifiesto = leer_manifiesto(ruta_manifiesto)
    tamano_manifiesto = manifiesto.pdf.tamano_pagina_mm
    detalle = abrir_pdf(ruta_detalle, "el detalle", DetalleInvalido)
    hoja = crear_pagina(formato.ancho_mm, formato.alto_mm)
    try:
        ancho, alto = tamano_visible_mm(detalle[0])
        ocupado = colocar_detalle(hoja[0], formato, detalle)  # centrado en area_dibujo
        # Alto real de la página colocada (coincide con page_size_mm ±0,1 mm si el
        # paquete es coherente).
        esperado = limites_dibujo_en_papel(manifiesto.pdf.dibujo.limites_pagina_mm, alto,
                                           ocupado[:2])
        fondo = rect_papel_a_pdf(ocupado, formato.alto_mm)
        rects = [rect_pdf_a_papel(t["rect"], formato.alto_mm)
                 for t in trazos_sin_fondo(hoja[0], fondo)]
    finally:
        detalle.close()
        hoja.close()

    filas = [Comprobacion(
        "Detalle real", "Tamaño de página vs page_size_mm",
        _cerca((ancho, alto), tamano_manifiesto, TOL_MM),
        f"{tamano_manifiesto[0]:.3f} x {tamano_manifiesto[1]:.3f} mm",
        f"{ancho:.3f} x {alto:.3f} mm", f"±{TOL_MM} mm")]
    if not rects:
        filas.append(Comprobacion("Detalle real", "Límites del dibujo vs page_bounds_mm", False,
                                  _r(esperado), "sin trazos", f"±{TOL_DETALLE_REAL_MM} mm"))
        return filas
    medido = (min(r[0] for r in rects), min(r[1] for r in rects),
              max(r[2] for r in rects), max(r[3] for r in rects))
    filas.append(Comprobacion(
        "Detalle real", "Límites del dibujo vs page_bounds_mm (en papel)",
        _cerca(medido, esperado, TOL_DETALLE_REAL_MM), _r(esperado), _r(medido),
        f"±{TOL_DETALLE_REAL_MM} mm"))
    return filas
