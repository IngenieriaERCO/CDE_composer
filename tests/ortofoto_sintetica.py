"""GeoTIFF sintéticos para las pruebas de la ortofoto (con rasterio, en tmp_path).

Cada píxel dice dónde está: rojo = columna % 256, verde = fila % 256, azul = 200. Así una
prueba puede comprobar QUÉ parte de la ortofoto cayó en cada lugar de la vista previa.

La ortofoto real de prueba (data/input/ortofotos/Foto_tunez.tif, fuera de git) la usan las
pruebas que la necesitan, saltándose si no está.
"""

from pathlib import Path

import numpy as np
import rasterio
from affine import Affine
from rasterio.enums import ColorInterp, Resampling

RAIZ = Path(__file__).resolve().parent.parent
FOTO_TUNEZ = RAIZ / "data" / "input" / "ortofotos" / "Foto_tunez.tif"
# Origen-Nacional (EPSG:9377): una esquina superior izquierda plausible en Colombia.
ORIGEN = (4705000.0, 2201000.0)


def patron(ancho: int, alto: int) -> np.ndarray:
    """(3, alto, ancho) uint8: rojo = columna % 256, verde = fila % 256, azul = 200."""
    filas, cols = np.mgrid[0:alto, 0:ancho]
    return np.stack([cols % 256, filas % 256, np.full((alto, ancho), 200)]).astype(np.uint8)


def patron_sinusoidal(ancho: int, alto: int) -> np.ndarray:
    """(3, alto, ancho) uint8 suave (el JPEG casi no lo cambia) pero que varía rápido: correrlo
    un píxel cambia los valores hasta ~40. Sirve para medir DÓNDE quedó la foto."""
    filas, cols = np.mgrid[0:alto, 0:ancho].astype(np.float64)
    r = 128 + 100 * np.sin(2 * np.pi * cols / 16)
    g = 128 + 100 * np.sin(2 * np.pi * filas / 16)
    b = 128 + 100 * np.sin(2 * np.pi * (cols + filas) / 23)
    return np.stack([r, g, b]).round().astype(np.uint8)


def crear_geotiff(ruta: Path, ancho: int = 400, alto: int = 300, origen=ORIGEN,
                  pixel: float = 1.0, crs: str | None = "EPSG:9377", bandas: int = 3,
                  tipo: str = "uint8", mosaicos: bool = False, compresion: str | None = None,
                  piramides: tuple[int, ...] = (), bigtiff: bool = False, nodata=None,
                  alfa: bool = False, paleta: bool = False, giro_grados: float = 0.0,
                  sin_georreferencia: bool = False, sinusoidal: bool = False) -> Path:
    """Escribe el GeoTIFF y devuelve su ruta. `pixel`: tamaño del píxel en m (cuadrado)."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    rgb = patron_sinusoidal(ancho, alto) if sinusoidal else patron(ancho, alto)
    if paleta or bandas == 1:
        datos = rgb[:1]
    elif alfa:
        a = np.full((1, alto, ancho), 255, np.uint8)
        a[0, :, : ancho // 2] = 0  # mitad izquierda transparente
        datos = np.concatenate([rgb, a])
    else:
        datos = rgb[:bandas] if bandas <= 3 else np.concatenate(
            [rgb, np.zeros((bandas - 3, alto, ancho), np.uint8)])
    if tipo == "uint16":
        datos = datos.astype(np.uint16) * 200
    if nodata is not None:
        datos[:, :, : ancho // 4] = nodata  # el primer cuarto, sin foto
    transform = (Affine.translation(*origen) @ Affine.rotation(giro_grados)
                 @ Affine.scale(pixel, -pixel))
    perfil = {"driver": "GTiff", "width": ancho, "height": alto, "count": datos.shape[0],
              "dtype": datos.dtype.name}
    if not sin_georreferencia:
        perfil["transform"] = transform
        if crs is not None:
            perfil["crs"] = crs
    if nodata is not None:
        perfil["nodata"] = nodata
    if mosaicos:
        perfil.update(tiled=True, blockxsize=256, blockysize=256)
    if compresion:
        perfil["compress"] = compresion
        if compresion == "jpeg":
            perfil["photometric"] = "YCbCr"
    if bigtiff:
        perfil["BIGTIFF"] = "YES"
    if alfa:
        perfil["photometric"] = "RGB"
        perfil["alpha"] = "YES"
    with rasterio.Env(GTIFF_SRS_SOURCE="EPSG"), rasterio.open(ruta, "w", **perfil) as d:
        d.write(datos)
        if alfa:
            d.colorinterp = [ColorInterp.red, ColorInterp.green, ColorInterp.blue,
                             ColorInterp.alpha]
        if paleta:
            d.write_colormap(1, {i: (i, 255 - i, 50, 255) for i in range(256)})
        if piramides:
            d.build_overviews(list(piramides), Resampling.average)
    return ruta


def muestrear(ruta: Path, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    """Valores RGB (n, 3) de la ortofoto en los puntos (xs, ys) de SU sistema, con interpolación
    bilineal hecha aquí (centros de píxel en +0,5), sin pasar por el código del Componedor: así
    se compara contra algo independiente. Lee solo la ventana que cubre los puntos (sirve para
    ortofotos de cualquier tamaño)."""
    from rasterio.windows import Window

    xs, ys = np.asarray(xs, np.float64), np.asarray(ys, np.float64)
    with rasterio.open(ruta) as d:
        inversa = ~d.transform
        cols = inversa.a * xs + inversa.b * ys + inversa.c - 0.5
        filas = inversa.d * xs + inversa.e * ys + inversa.f - 0.5
        v0 = max(0, int(np.floor(cols.min())) - 1), max(0, int(np.floor(filas.min())) - 1)
        v1 = (min(d.width, int(np.ceil(cols.max())) + 2), min(d.height, int(np.ceil(filas.max())) + 2))
        datos = d.read([1, 2, 3], window=Window(v0[0], v0[1], v1[0] - v0[0], v1[1] - v0[1])
                       ).astype(np.float64)
    cols, filas = cols - v0[0], filas - v0[1]
    c0 = np.clip(np.floor(cols).astype(int), 0, datos.shape[2] - 2)
    f0 = np.clip(np.floor(filas).astype(int), 0, datos.shape[1] - 2)
    tc, tf = np.clip(cols - c0, 0, 1), np.clip(filas - f0, 0, 1)
    v = (datos[:, f0, c0] * (1 - tc) * (1 - tf) + datos[:, f0, c0 + 1] * tc * (1 - tf)
         + datos[:, f0 + 1, c0] * (1 - tc) * tf + datos[:, f0 + 1, c0 + 1] * tc * tf)
    return v.T


def imagenes_pdf(ruta_pdf: Path, alto_hoja_mm: float) -> list[dict]:
    """Cada imagen de la primera página: {rect_mm (papel, Y arriba), rgb (alto, ancho, 3),
    filtro, mascara (alto, ancho) o None, xref}."""
    import pymupdf

    salida = []
    with pymupdf.open(ruta_pdf) as doc:
        page = doc[0]
        for img in page.get_images(full=True):
            xref, smask = img[0], img[1]
            pix = pymupdf.Pixmap(doc.extract_image(xref)["image"])
            rgb = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)[:, :, :3]
            mascara = None
            if smask:
                m = pymupdf.Pixmap(doc, smask)
                mascara = np.frombuffer(m.samples, np.uint8).reshape(m.height, m.width)
            filtro = doc.xref_get_key(xref, "Filter")[1]
            for r in page.get_image_rects(xref):
                rect_mm = (r.x0 * 25.4 / 72, alto_hoja_mm - r.y1 * 25.4 / 72,
                           r.x1 * 25.4 / 72, alto_hoja_mm - r.y0 * 25.4 / 72)
                salida.append({"rect_mm": rect_mm, "rgb": rgb, "filtro": filtro,
                               "mascara": mascara, "xref": xref})
    return salida


def error_de_posicion(imagen: dict, a_cad, ruta_tif: Path, paso: int = 7,
                      corrimiento=(0.0, 0.0)) -> float:
    """Error medio (0–255) entre los píxeles de una imagen del PDF y la ortofoto muestreada en
    el punto CAD que predice el dibujo para cada píxel. `a_cad(x_mm, y_mm)` → (X, Y) en el
    sistema de la ortofoto; `corrimiento` (mm de papel) para ver que un error de posición se
    nota."""
    rgb = imagen["rgb"]
    alto, ancho = rgb.shape[:2]
    x0, y0, x1, y1 = imagen["rect_mm"]
    js, is_ = np.mgrid[0:alto:paso, 0:ancho:paso]
    xs = x0 + (is_ + 0.5) * (x1 - x0) / ancho + corrimiento[0]
    ys = y1 - (js + 0.5) * (y1 - y0) / alto + corrimiento[1]
    cad = [a_cad(x, y) for x, y in zip(xs.ravel(), ys.ravel())]
    esperado = muestrear(ruta_tif, np.array([c[0] for c in cad]), np.array([c[1] for c in cad]))
    leido = rgb[js.ravel(), is_.ravel()].astype(np.float64)
    if imagen["mascara"] is not None:
        visibles = imagen["mascara"][js.ravel(), is_.ravel()] > 0
        esperado, leido = esperado[visibles], leido[visibles]
    return float(np.abs(esperado - leido).mean())
