"""Utilidades compartidas por las pruebas.

Las pruebas NO dependen del rótulo real (plantillas/*.pdf no se versiona): usan copias del
JSON del formato sin plantilla o con una plantilla sintética.
"""

import hashlib
import json
from pathlib import Path

import pymupdf
import pytest

from componedor.unidades import mm_a_pt, pt_a_mm

RUTA_A1 = Path(__file__).parent.parent / "formatos" / "A1_ERCO.json"
TEXTO_DETALLE = "DETALLE A"
MARCO_A1 = (12.7, 12.7, 828.3, 581.3)
ARIAL = Path("C:/Windows/Fonts/arial.ttf")  # la del formato A1 ERCO (subfase 4.1)
requiere_arial = pytest.mark.skipif(not ARIAL.is_file(), reason="Arial no está instalada")


def rotulo_a1(**cambios) -> dict:
    """Sección "rotulo" de A1_ERCO.json (campos medidos del rótulo v2), con cambios."""
    datos = json.loads(RUTA_A1.read_text(encoding="utf-8"))["rotulo"]
    datos.update(cambios)
    return datos


def escribir_formato(destino: Path, plantilla: Path | None = None, **cambios) -> Path:
    """Copia de A1_ERCO.json sin la plantilla real, sin sus elementos medidos (la rosa: es del
    rótulo real) y sin los campos de texto del rótulo; opcionalmente con otra plantilla. Para
    probar elementos o campos, páselos en `cambios` (elementos_plantilla=[...], rotulo={...})."""
    datos = json.loads(RUTA_A1.read_text(encoding="utf-8"))
    datos.pop("plantilla", None)
    datos.pop("elementos_plantilla", None)
    datos.pop("rotulo", None)
    if plantilla is not None:
        datos["plantilla"] = str(plantilla)
    datos.update(cambios)
    destino.write_text(json.dumps(datos), encoding="utf-8")
    return destino


def crear_plantilla_sintetica(ruta: Path, ancho_pt: float = 2384, alto_pt: float = 1684,
                              rotacion: int = 0, marco_mm=MARCO_A1, elementos_mm=(),
                              letra_en_elementos: str | None = None) -> Path:
    """Rótulo de prueba: marco, columna del rótulo y un "logo" (imagen RGB pequeña).

    Por defecto 2384 x 1684 pt (841,02 x 594,08 mm), como redondea AutoCAD el A1.
    Las medidas van en mm de papel (origen inferior izquierdo de la plantilla tal como se
    ve). Con /Rotate 90 o 270 la página se crea vertical y se dibuja de modo que se vea
    horizontal, como un plot de AutoCAD en hoja vertical girada.
    """
    doc = pymupdf.open()
    if rotacion in (90, 270):
        page = doc.new_page(width=alto_pt, height=ancho_pt)
    else:
        page = doc.new_page(width=ancho_pt, height=alto_pt)
    page.set_rotation(rotacion)
    alto_mm = pt_a_mm(alto_pt)

    def r(xmin, ymin, xmax, ymax):  # mm de papel -> coordenadas sin girar de la página
        visible = pymupdf.Rect(mm_a_pt(xmin), mm_a_pt(alto_mm - ymax),
                               mm_a_pt(xmax), mm_a_pt(alto_mm - ymin))
        return visible * page.derotation_matrix

    page.draw_rect(r(*marco_mm), color=(0, 0, 0), width=0.72)
    page.draw_line(r(672.4, 12.7, 672.4, 581.3).tl, r(672.4, 12.7, 672.4, 581.3).br,
                   color=(0, 0, 0), width=0.72)
    logo = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 40, 12), False)
    logo.set_rect(logo.irect, (0, 150, 60))
    page.insert_image(r(761.0, 79.4, 817.2, 96.7), pixmap=logo)
    # Elementos fijos dentro del área de dibujo (como la rosa de los vientos): un cuadro y
    # una cruz por dentro, para que sean varios trazos agrupados en uno.
    # Con `letra_en_elementos` (p. ej. "N"), además una letra de texto dentro de cada uno,
    # como las letras N S E W de la rosa real (solo para plantillas sin /Rotate).
    for xmin, ymin, xmax, ymax in elementos_mm:
        page.draw_rect(r(xmin, ymin, xmax, ymax), color=(0, 0, 0), width=0.5)
        page.draw_line(r(xmin, ymin, xmax, ymax).tl, r(xmin, ymin, xmax, ymax).br,
                       color=(0, 0, 0), width=0.3)
        if letra_en_elementos:
            page.insert_text(r(xmin + 5, ymin + 5, xmin + 10, ymin + 10).bl, letra_en_elementos,
                             fontsize=10)
    doc.save(ruta)
    doc.close()
    return ruta


# --- Plano sintético con leyenda CONVENCIONES (subfase 4.2b; no es un plano de ERCO) -------
FILAS_CONV = [259.88, 249.39, 238.89, 228.43, 217.93, 207.48, 196.98, 186.52, 176.02, 166.45,
              156.84, 147.28, 137.71]
COLUMNAS_CONV = [(672.4, 693.84), (693.84, 750.32), (750.32, 771.82), (771.82, 828.2)]
# Trazos que deja cada tipo de símbolo (para comprobar la extracción).
TRAZOS_POR_TIPO = {"linea": 1, "relleno": 1, "puntos": 12, "malla": 9, "ancho": 1, "alto": 1}


def casilla_conv(k: int) -> tuple[float, float, float, float]:
    """Casilla de símbolo k (1..24, por columna) de la rejilla de convenciones, mm de papel."""
    par, fila = divmod(k - 1, 12)
    x0, x1 = COLUMNAS_CONV[2 * par]
    return x0, FILAS_CONV[fila + 1], x1, FILAS_CONV[fila]


def dibujo_de_tipo(tipo: str, casilla) -> tuple[float, float, float, float]:
    """Caja (mm de papel) del dibujo de prueba de ese tipo, centrado en la casilla."""
    cx, cy = (casilla[0] + casilla[2]) / 2, (casilla[1] + casilla[3]) / 2
    medio = {"linea": (6.0, 0.0), "relleno": (7.0, 3.0), "puntos": (6.0, 3.0),
             "malla": (5.0, 3.0), "ancho": (10.5, 0.0), "alto": (3.0, 4.6)}[tipo]
    return cx - medio[0], cy - medio[1], cx + medio[0], cy + medio[1]


def crear_plano_con_leyenda(ruta: Path, simbolos: dict[int, str], rotacion: int = 270) -> Path:
    """PDF A1 (2384 x 1684 pt) girado como un plot de AutoCAD (/Rotate 270 por defecto) con la
    rejilla de convenciones del rótulo v2, «descripciones» dibujadas como trazos (como el texto
    SHX), un dibujo grande en el área de dibujo y un símbolo de prueba por casilla:
    {casilla (1..24): "linea" | "relleno" | "puntos" | "malla" | "ancho" | "alto"}.
    "ancho" (21 mm) no cabe en el ancho útil (20,24 mm); "alto" (9,2 mm) cabe en las filas
    1 a 8 (9,25 mm útiles o más) pero no en las 9 a 12 (unos 8,4 mm)."""
    ancho_pt, alto_pt = 2384, 1684
    doc = pymupdf.open()
    page = doc.new_page(width=alto_pt, height=ancho_pt) if rotacion in (90, 270) else \
        doc.new_page(width=ancho_pt, height=alto_pt)
    page.set_rotation(rotacion)
    alto_mm = pt_a_mm(alto_pt)

    def p(x, y):  # punto de papel -> página sin girar
        return pymupdf.Point(mm_a_pt(x), mm_a_pt(alto_mm - y)) * page.derotation_matrix

    def linea(x0, y0, x1, y1, color=(0, 0, 0), ancho=0.5):
        page.draw_line(p(x0, y0), p(x1, y1), color=color, width=ancho)

    def rect(x0, y0, x1, y1):
        return pymupdf.Rect(p(x0, y1), p(x1, y0)).normalize()

    for y in FILAS_CONV:
        linea(672.4, y, 828.2, y)
    for x in (693.84, 750.32, 771.82):
        linea(x, FILAS_CONV[-1], x, FILAS_CONV[0])
    page.draw_rect(rect(100, 100, 500, 400), color=(0, 0, 1), width=1)  # algo en el área
    for k in range(1, 25):  # una «descripción» en trazos en cada fila de la columna izquierda
        if k <= 12:
            d = casilla_conv(k)
            linea(696.0, (d[1] + d[3]) / 2, 720.0, (d[1] + d[3]) / 2, ancho=0.3)
    for k, tipo in simbolos.items():
        x0, y0, x1, y1 = dibujo_de_tipo(tipo, casilla_conv(k))
        if tipo in ("linea", "ancho"):
            linea(x0, y0, x1, y1, color=(1, 0.5, 0), ancho=1.0)
        elif tipo in ("relleno", "alto"):
            page.draw_rect(rect(x0, y0, x1, y1), color=(0.2, 0.2, 0.2), fill=(1, 0.55, 0.1),
                           width=0.5)
        elif tipo == "puntos":
            for i in range(12):
                cx, cy = x0 + 0.5 + (i % 6) * 2.2, y0 + 0.5 + (i // 6) * 5.0
                page.draw_circle(p(cx, cy), mm_a_pt(0.3), color=(0.9, 0.7, 0), width=0.3)
        elif tipo == "malla":
            for i in range(5):
                linea(x0 + i * 2.5, y0, x0 + i * 2.5, y1, color=(0, 0, 1), ancho=0.2)
            for j in range(4):
                linea(x0, y0 + j * 2.0, x1, y0 + j * 2.0, color=(0, 0, 1), ancho=0.2)
    doc.save(ruta)
    doc.close()
    return ruta


def crear_detalle_sintetico(ruta: Path, ancho_mm: float = 120, alto_mm: float = 80,
                            rotacion: int = 0, cropbox_mm=None) -> Path:
    """PDF de prueba de una página: rectángulo de 100 x 50 mm, diagonal, texto y marca.

    Coordenadas propias de PyMuPDF (pt, Y hacia abajo) en la página de 120 x 80 mm:
    - rectángulo de (10, 15) a (110, 65) mm  -> centrado en la página;
    - diagonal de (10, 15) a (110, 65) mm;
    - texto "DETALLE A";
    - marca de orientación rellena de (12, 17) a (30, 25) mm, en la esquina superior
      izquierda del rectángulo, para distinguir hacia dónde se giró.
    """
    def r(x0, y0, x1, y1):
        return pymupdf.Rect(mm_a_pt(x0), mm_a_pt(y0), mm_a_pt(x1), mm_a_pt(y1))

    doc = pymupdf.open()
    page = doc.new_page(width=mm_a_pt(ancho_mm), height=mm_a_pt(alto_mm))
    page.draw_rect(r(10, 15, 110, 65), color=(0, 0, 0), width=0.7)
    page.draw_line(pymupdf.Point(mm_a_pt(10), mm_a_pt(15)),
                   pymupdf.Point(mm_a_pt(110), mm_a_pt(65)), color=(0, 0, 0), width=0.7)
    page.draw_rect(r(12, 17, 30, 25), color=(1, 0, 0), fill=(1, 0, 0), width=0.3)
    page.insert_text(pymupdf.Point(mm_a_pt(40), mm_a_pt(45)), TEXTO_DETALLE, fontsize=12)
    if cropbox_mm:
        page.set_cropbox(r(*cropbox_mm))
    page.set_rotation(rotacion)
    doc.save(ruta)
    doc.close()
    return ruta


# --- Detalle con matriz cad_to_page sintética (no son datos de ERCO) -----------------------
# Escala 20 mm por unidad CAD (1:50 en metros), Y CAD hacia arriba -> d = -20.
# Coordenadas CAD de millones -> e y f de magnitud ~1e8. Márgenes a propósito distintos de
# 5 mm: la matriz ya los incluye.
X0_CAD, Y0_CAD = 4_900_000.0, 5_100_000.0
MATRIZ_SINTETICA = (20.0, 0.0, 0.0, -20.0, 17.3 - 20 * X0_CAD, 20 * (Y0_CAD + 6) + 18.7)
RECT_CAD = (X0_CAD + 1, Y0_CAD + 2, X0_CAD + 11, Y0_CAD + 6)  # 10 x 4 unidades CAD
PAGINA_CAD_MM = (260.0, 120.0)
LIMITES_RECT_PAGINA_MM = (37.3, 18.7, 237.3, 98.7)  # el rectángulo en la página, Y abajo


def _cad_a_pagina_mm(x, y):
    a, b, c, d, e, f = MATRIZ_SINTETICA
    return a * x + c * y + e, b * x + d * y + f


def _dibujar_detalle_cad(page: pymupdf.Page, desplazar_mm=(0.0, 0.0), fondo: bool = True) -> None:
    """Fondo blanco (como el exportador antiguo; `fondo=False`: como el nuevo, sin fondo) y
    el rectángulo RECT_CAD con MATRIZ_SINTETICA.

    `desplazar_mm` mueve el dibujo en la página (solo para provocar incoherencias)."""
    if fondo:
        page.draw_rect(page.rect, color=None, fill=(1, 1, 1))  # fondo de página
    x0, y0, x1, y1 = RECT_CAD
    dx, dy = desplazar_mm
    esquinas = [_cad_a_pagina_mm(x, y) for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
    puntos = [pymupdf.Point(mm_a_pt(x + dx), mm_a_pt(y + dy)) for x, y in esquinas]
    page.draw_polyline(puntos + [puntos[0]], color=(0, 0, 0), width=0.5)


def crear_detalle_cad(ruta: Path) -> Path:
    """PDF de 260 x 120 mm con el detalle de `_dibujar_detalle_cad` (sin manifiesto)."""
    doc = pymupdf.open()
    _dibujar_detalle_cad(doc.new_page(width=mm_a_pt(PAGINA_CAD_MM[0]),
                                      height=mm_a_pt(PAGINA_CAD_MM[1])))
    doc.save(ruta)
    doc.close()
    return ruta


SHA256_FICTICIO = "ab" * 32  # 64 hexadecimales; no es el hash de ningún archivo


def manifiesto_paquete(quitar=(), cambiar=None, minimo: bool = False) -> dict:
    """Manifiesto sintético con la forma del exportador (esquema 1.0, modelo "2").

    - `quitar`: rutas con puntos que se eliminan (p. ej. "pdf.page_size_mm").
    - `cambiar`: {ruta con puntos: valor nuevo}; crea el campo si no existe.
    - `minimo=True`: solo los campos obligatorios para el componedor.
    Los nombres y valores son inventados (no son datos de ERCO).
    """
    x0, y0, x1, y1 = LIMITES_RECT_PAGINA_MM
    datos = {
        "document_type": "cde-detail-manifest",
        "schema_version": "1.0",
        "model_version": "2",
        "units": {"millimeters_per_unit": 1000.0},
        "scale": {"denominator": 50.0, "factor_mm_per_cad_unit": 20.0,
                  "physical_scale_guaranteed": True},
        "pdf": {
            "file_name": "detalle_prueba.pdf",
            "bytes": 12345,
            "sha256": SHA256_FICTICIO,
            "page_count": 1,
            "page_size_mm": list(PAGINA_CAD_MM),
            "expected_page_size_mm": list(PAGINA_CAD_MM),
            "margin_mm": 5.0,
            "drawing": {
                "cad_bounds": {"min": [RECT_CAD[0], RECT_CAD[1]], "max": [RECT_CAD[2], RECT_CAD[3]]},
                "page_bounds_mm": {"x0": x0, "y0": y0, "x1": x1, "y1": y1},
                "cad_to_page": {"units": "mm", "origin": "top-left", "y_axis": "down",
                                "matrix": list(MATRIZ_SINTETICA)},
            },
        },
        "validation": {"status": "complete_with_warnings"},
    }
    if not minimo:
        datos["generated_at"] = "2026-01-01T00:00:00-05:00"
        datos["exporter"] = {"version": "0.0.0", "ezdxf": None, "pymupdf": None}
        datos["source"] = {"dxf_name": "dibujo_prueba.dxf", "dxf_sha256": SHA256_FICTICIO,
                           "dxf_bytes": 1000, "block_name": "DETALLE_PRUEBA",
                           "block_definition_handle": None}
        datos["units"].update(declared_code=6, name="m", status="ficticio", user_override=None)
        datos["scale"].update(requested="1:50", physical_scale_reason=None)
        datos["pdf"]["content_size_mm"] = [250.0, 110.0]
        datos["entities"] = {"total": 1, "by_type": [], "by_layer": [], "not_conserved": []}
        datos["fonts"] = []
        datos["dependencies"] = []
        datos["notices"] = {"counts": {"info": 0, "warning": 1, "critical": 0},
                            "by_category": {}}
        datos["validation"]["checks"] = []
        datos["options"] = {"hatch_mode": "auto", "margin_mm": 5.0}

    for ruta in quitar:
        *padres, ultimo = ruta.split(".")
        nodo = datos
        for parte in padres:
            nodo = nodo[parte]
        del nodo[ultimo]
    for ruta, valor in (cambiar or {}).items():
        *padres, ultimo = ruta.split(".")
        nodo = datos
        for parte in padres:
            nodo = nodo.setdefault(parte, {})
        nodo[ultimo] = valor
    return datos


def crear_paquete_real(carpeta: Path, prefijo: str = "detalle", paginas: int = 1,
                       contenido: bytes | None = None, rotacion: int = 0,
                       pagina_mm: tuple[float, float] = PAGINA_CAD_MM,
                       desplazar_dibujo_mm: tuple[float, float] = (0.0, 0.0),
                       sin_fondo: bool = False, **kw_manifiesto) -> Path:
    """Paquete sintético COHERENTE: PDF de verdad con el detalle de `_dibujar_detalle_cad` y
    un manifiesto (`manifiesto_paquete`) cuyos `pdf.bytes` y `pdf.sha256` se calculan del
    archivo escrito. Devuelve la ruta del PDF.

    Opciones para provocar fallas: `contenido` (bytes en lugar del PDF), `paginas`,
    `rotacion` (/Rotate), `pagina_mm` (otro tamaño de página, sin tocar el manifiesto),
    `desplazar_dibujo_mm` y `cambiar`/`quitar` del manifiesto. `sin_fondo=True`: PDF como los
    del exportador nuevo, sin el rectángulo blanco de página.
    """
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta_pdf = carpeta / f"{prefijo}.pdf"
    if contenido is None:
        doc = pymupdf.open()
        for _ in range(paginas):
            pagina = doc.new_page(width=mm_a_pt(pagina_mm[0]), height=mm_a_pt(pagina_mm[1]))
            _dibujar_detalle_cad(pagina, desplazar_dibujo_mm, fondo=not sin_fondo)
            pagina.set_rotation(rotacion)
        contenido = doc.tobytes()
        doc.close()
    ruta_pdf.write_bytes(contenido)
    cambiar = {"pdf.file_name": ruta_pdf.name, "pdf.bytes": len(contenido),
               "pdf.sha256": hashlib.sha256(contenido).hexdigest(),
               **kw_manifiesto.pop("cambiar", {})}
    escribir_json(carpeta / f"{prefijo}.manifest.json",
                  manifiesto_paquete(cambiar=cambiar, **kw_manifiesto))
    return ruta_pdf


def escribir_json(ruta: Path, datos: dict) -> Path:
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    return ruta


@pytest.fixture
def detalle(tmp_path):
    """Detalle sintético estándar de 120 x 80 mm sin rotación."""
    return crear_detalle_sintetico(tmp_path / "detalle.pdf")
