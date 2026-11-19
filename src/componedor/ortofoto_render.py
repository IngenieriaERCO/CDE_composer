"""Pintar la ortofoto en una caja del dibujo: píxeles RGB y alfa, leyendo SOLO la ventana necesaria.

Lo usan la vista previa del editor (`previa_ortofoto`), el PDF (`ortofoto_pdf`) y la copia
reducida (`ortofoto_copia`).

La caja va en metros, en el sistema del DIBUJO (`crs_dibujo`); la ortofoto puede estar en otro
(se reproyecta). Pasos de `pintar`:

1. La caja llevada al sistema de la ortofoto y a sus píxeles: la VENTANA a leer (nunca el
   archivo entero; sirve igual para un BigTIFF de varios GB).
2. Esa ventana se lee REDUCIDA a lo que hace falta (`out_shape`: GDAL usa las pirámides si
   las hay). Con `factor` entero (el PDF y la copia), la ventana se alinea a múltiplos del
   factor: así dos mosaicos vecinos leen la misma grilla reducida y no se nota la unión.
3. Reproyección a la caja: bilineal la imagen; la máscara, por vecino más cercano, como 1 (sin
   foto) y 2 (con foto), porque GDAL cambiaría un 0 de la fuente por 1.
4. Alfa 255 donde hay foto y 0 donde no (fuera de la ortofoto, alfa, máscara o «nodata»).

16 bits u otros tipos: se estiran a 8 bits entre los percentiles 2 y 98 de TODA la ortofoto
(calculados una vez, a baja resolución): el mismo brillo en todos los detalles y mosaicos.
"""

import math
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
from affine import Affine
from rasterio.crs import CRS
from rasterio.enums import Resampling
from rasterio.warp import reproject, transform_bounds
from rasterio.windows import Window

from componedor.ortofoto import OrtofotoInvalida

LADO_MUESTRA_PX = 512
_RANGOS: dict[tuple, tuple[float, float]] = {}  # (ruta, bytes, fecha) → (bajo, alto)


@dataclass
class Fuente:
    """La ortofoto abierta y lo que hace falta para pintarla."""
    d: object  # rasterio DatasetReader
    ruta: Path
    crs: CRS
    bandas: list[int]
    paleta: dict | None
    rango: tuple[float, float] | None  # para estirar a 8 bits (None: ya es de 8 bits)
    resolucion: float  # tamaño del píxel en su sistema

    def caja_en_fuente(self, caja_m, crs_dibujo: CRS) -> tuple[float, float, float, float]:
        return transform_bounds(crs_dibujo, self.crs, *caja_m, densify_pts=21)

    def factor(self, caja_m, ancho: int, alto: int, crs_dibujo: CRS) -> int:
        """Cuántos píxeles de la ortofoto caben (entero, ≥ 1) en un píxel de destino."""
        cf = self.caja_en_fuente(caja_m, crs_dibujo)
        por_px = min((cf[2] - cf[0]) / ancho, (cf[3] - cf[1]) / alto) / self.resolucion
        return max(1, math.floor(por_px + 1e-9))

    def resolucion_en_dibujo(self, caja_m, crs_dibujo: CRS) -> float:
        """El píxel de la ortofoto medido en el sistema del dibujo (m), en esa caja."""
        cf = self.caja_en_fuente(caja_m, crs_dibujo)
        escala = (caja_m[2] - caja_m[0]) / (cf[2] - cf[0])
        return self.resolucion * escala


@contextmanager
def abrir_fuente(ruta: Path | str, crs_ortofoto: CRS | None = None) -> Iterator[Fuente]:
    """Abre la ortofoto. `crs_ortofoto`: el elegido a mano, solo si el archivo no trae el suyo.
    OrtofotoInvalida si no se sabe su sistema."""
    ruta = Path(ruta)
    with rasterio.open(ruta) as d:
        crs = d.crs if d.crs else crs_ortofoto
        if crs is None:
            raise OrtofotoInvalida("La ortofoto no dice su sistema de coordenadas: elíjalo en el "
                                   "editor para poder ubicarla.")
        bandas, paleta = _bandas(d)
        rango = (rango_8_bits(d, ruta, bandas)
                 if d.dtypes[0] != "uint8" and paleta is None else None)
        yield Fuente(d, ruta, crs, bandas, paleta, rango,
                     math.hypot(d.transform.a, d.transform.d))


def destino(caja_m, ancho: int, alto: int) -> Affine:
    """Geotransformación de una imagen de ancho × alto píxeles que cubre la caja (Y abajo)."""
    return Affine.translation(caja_m[0], caja_m[3]) @ Affine.scale(
        (caja_m[2] - caja_m[0]) / ancho, -(caja_m[3] - caja_m[1]) / alto)


def ventana_fuente(d, caja_fuente, factor: int = 1) -> Window | None:
    """La ventana de píxeles de la ortofoto que cubre `caja_fuente` (en SU sistema), con 2 px
    reducidos de holgura, alineada a múltiplos de `factor` y recortada a la imagen; None si no
    se tocan. Sirve también si está girada."""
    x0, y0, x1, y1 = caja_fuente
    inversa = ~d.transform
    esquinas = [inversa @ (x, y) for x, y in ((x0, y0), (x0, y1), (x1, y0), (x1, y1))]
    cols = [c for c, _ in esquinas]
    filas = [f for _, f in esquinas]
    holgura = 2 * factor
    c0 = max(0, math.floor((min(cols) - holgura) / factor) * factor)
    f0 = max(0, math.floor((min(filas) - holgura) / factor) * factor)
    c1 = min(d.width, math.ceil((max(cols) + holgura) / factor) * factor)
    f1 = min(d.height, math.ceil((max(filas) + holgura) / factor) * factor)
    if c1 <= c0 or f1 <= f0:
        return None
    return Window(c0, f0, c1 - c0, f1 - f0)


def _bandas(d) -> tuple[list[int], dict | None]:
    """Qué bandas leer (1 o 3) y la paleta, si es una imagen con paleta."""
    interpretacion = [c.name for c in d.colorinterp]
    if d.count == 1:
        if interpretacion[0] == "palette":
            try:
                return [1], d.colormap(1)
            except ValueError:
                return [1], None
        return [1], None
    if d.count == 2:  # gris + alfa (la alfa va en la máscara)
        return [1], None
    return [1, 2, 3], None


def rango_8_bits(d, ruta: Path, bandas: list[int]) -> tuple[float, float]:
    """Percentiles 2 y 98 de TODA la ortofoto (leída reducida, ≤ 512 px; con pirámides es
    inmediato). Se calcula una vez por archivo."""
    estado = Path(ruta).stat()
    clave = (str(ruta), estado.st_size, estado.st_mtime_ns)
    if clave not in _RANGOS:
        paso = max(1.0, max(d.width, d.height) / LADO_MUESTRA_PX)
        forma = (len(bandas), max(1, round(d.height / paso)), max(1, round(d.width / paso)))
        muestra = d.read(bandas, out_shape=forma, resampling=Resampling.nearest)
        validos = d.dataset_mask(out_shape=forma[1:], resampling=Resampling.nearest) > 0
        valores = muestra[:, validos] if validos.any() else muestra.reshape(len(bandas), -1)
        bajo, alto = (np.percentile(valores.astype(np.float64), (2, 98)) if valores.size
                      else (0.0, 1.0))
        _RANGOS[clave] = (float(bajo), float(alto) if alto > bajo else float(bajo) + 1)
    return _RANGOS[clave]


def _a_8_bits(datos: np.ndarray, rango: tuple[float, float] | None) -> np.ndarray:
    if datos.dtype == np.uint8 or rango is None:
        return datos.astype(np.uint8)
    bajo, alto = rango
    escalado = (datos.astype(np.float64) - bajo) * (255.0 / (alto - bajo))
    return np.clip(escalado, 0, 255).astype(np.uint8)


def pintar(f: Fuente, caja_m, ancho: int, alto: int, crs_dibujo: CRS,
           factor: int | None = None) -> tuple[np.ndarray, np.ndarray]:
    """(rgb (3, alto, ancho) uint8, alfa (alto, ancho) uint8 0/255) de la ortofoto en la caja.

    factor: reducción entera fija (PDF y copia: mosaicos sin costuras). None: la que haga
    falta para esta caja (vista previa)."""
    rgb = np.zeros((3, alto, ancho), np.uint8)
    alfa = np.zeros((alto, ancho), np.uint8)
    d = f.d
    caja_fuente = f.caja_en_fuente(caja_m, crs_dibujo)
    k = factor or 1
    ventana = ventana_fuente(d, caja_fuente, k)
    if ventana is None:
        return rgb, alfa
    if factor is None:
        por_px = min((caja_fuente[2] - caja_fuente[0]) / ancho,
                     (caja_fuente[3] - caja_fuente[1]) / alto) / f.resolucion
        paso = max(1.0, por_px)
    else:
        paso = float(factor)
    sale_ancho = max(1, math.ceil(ventana.width / paso))
    sale_alto = max(1, math.ceil(ventana.height / paso))
    remuestreo = Resampling.average if paso > 1 else Resampling.nearest
    datos = d.read(f.bandas, window=ventana, out_shape=(len(f.bandas), sale_alto, sale_ancho),
                   resampling=remuestreo)
    mascara = d.dataset_mask(window=ventana, out_shape=(sale_alto, sale_ancho),
                             resampling=Resampling.nearest)
    fuente = d.window_transform(ventana) @ Affine.scale(ventana.width / sale_ancho,
                                                        ventana.height / sale_alto)
    if f.paleta is not None:
        tabla = np.zeros((256, 3), np.uint8)
        for i, color in f.paleta.items():
            if 0 <= i < 256:
                tabla[i] = color[:3]
        datos = np.moveaxis(tabla[datos[0].clip(0, 255).astype(np.uint8)], -1, 0)
    elif len(f.bandas) == 1:
        datos = np.repeat(datos, 3, axis=0)
    datos = _a_8_bits(datos, f.rango)
    comun = {"src_transform": fuente, "src_crs": f.crs, "dst_transform": destino(caja_m, ancho, alto),
             "dst_crs": crs_dibujo}
    reproject(datos, rgb, resampling=Resampling.bilinear, src_nodata=None, dst_nodata=None,
              **comun)
    marcas = np.where(mascara > 0, 2, 1).astype(np.uint8)
    reproject(marcas, alfa, resampling=Resampling.nearest, src_nodata=None, dst_nodata=0, **comun)
    alfa = np.where(alfa == 2, 255, 0).astype(np.uint8)
    return rgb, alfa
