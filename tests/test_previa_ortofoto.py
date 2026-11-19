"""Vista previa de la ortofoto en la caja de un detalle: ventana, posición exacta, reproyección,
transparencia y los distintos tipos de GeoTIFF (con GeoTIFF sintéticos y, si está, el real)."""

import numpy as np
import pymupdf
import pytest
from ortofoto_sintetica import FOTO_TUNEZ, ORIGEN, crear_geotiff
from rasterio.warp import transform, transform_bounds

from componedor.ortofoto import OrtofotoInvalida, leer_sistema
from componedor.previa_ortofoto import (
    hacer_previa,
    tamano_px,
    validar_caja,
)

X0, Y1 = ORIGEN  # esquina superior izquierda del sintético
M9377 = leer_sistema("EPSG:9377")
M3116 = leer_sistema("EPSG:3116")


def pixeles(png: bytes) -> np.ndarray:
    """(alto, ancho, 4) uint8 del PNG RGBA."""
    pix = pymupdf.Pixmap(png)
    assert pix.n == 4 and pix.alpha
    return np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, 4)


def test_tamano_px_y_caja():
    assert tamano_px((0, 0, 200, 100), 1500) == (1500, 750)
    assert tamano_px((0, 0, 100, 400), 1000) == (250, 1000)
    assert tamano_px((0, 0, 1000, 0.01), 100) == (100, 1)
    assert validar_caja([1, 2, 3, 4]) == (1.0, 2.0, 3.0, 4.0)
    for mala in ([1, 2, 3], [0, 0, 0, 5], [0, 0, 5, 0], [0, 0, float("nan"), 1], "abcd",
                 [True, 0, 1, 1]):
        with pytest.raises(ValueError):
            validar_caja(mala)


def test_cada_pixel_cae_donde_va(tmp_path):
    """Caja de 100 × 100 m dentro de la foto (columnas y filas 100 a 200), 1 px = 1 m."""
    ruta = crear_geotiff(tmp_path / "a.tif")
    p = hacer_previa(ruta, (X0 + 100, Y1 - 200, X0 + 200, Y1 - 100), M9377, lado_px=100)
    assert p.px == (100, 100) and p.cobertura == 1.0
    a = pixeles(p.png)
    assert a[0, 0].tolist() == [100, 100, 200, 255]  # arriba-izquierda: columna 100, fila 100
    assert a[99, 99].tolist() == [199, 199, 200, 255]
    assert a[0, 99, 0] == 199 and a[99, 0, 1] == 199


def test_reducida_y_ampliada(tmp_path):
    ruta = crear_geotiff(tmp_path / "a.tif", piramides=(2, 4))
    p = hacer_previa(ruta, (X0, Y1 - 300, X0 + 400, Y1), M9377, lado_px=100)  # foto entera
    assert p.px == (100, 75) and p.cobertura == 1.0
    a = pixeles(p.png)
    assert abs(int(a[0, 50, 0]) - 202) <= 3  # 4 px de la foto por píxel: el centro de 200 a 204
    p = hacer_previa(ruta, (X0 + 10, Y1 - 20, X0 + 20, Y1 - 10), M9377, lado_px=200)
    assert p.px == (200, 200) and pixeles(p.png)[0, 0, 0] == 10  # ampliada: no inventa


def test_caja_a_medias_y_fuera(tmp_path):
    ruta = crear_geotiff(tmp_path / "a.tif")
    # La mitad izquierda de la caja cae fuera de la foto: transparente.
    p = hacer_previa(ruta, (X0 - 100, Y1 - 100, X0 + 100, Y1), M9377, lado_px=200)
    assert p.cobertura == pytest.approx(0.5)
    a = pixeles(p.png)
    assert a[50, 10, 3] == 0 and a[50, 150, 3] == 255 and a[50, 150, 0] == 50
    vacia = hacer_previa(ruta, (0, 0, 10, 10), M9377, lado_px=50)
    assert vacia.cobertura == 0.0 and vacia.px == (50, 50) and pixeles(vacia.png)[:, :, 3].max() == 0


def test_reproyecta_al_sistema_del_dibujo(tmp_path):
    ruta = crear_geotiff(tmp_path / "a.tif")
    caja = (X0 + 100, Y1 - 200, X0 + 200, Y1 - 100)
    caja_3116 = transform_bounds(M9377, M3116, *caja)
    p = hacer_previa(ruta, caja_3116, M3116, lado_px=200)
    assert p.cobertura == pytest.approx(1.0, abs=0.02)
    a = pixeles(p.png)
    # El centro de la caja en 3116 cae (casi) en el centro de la caja en 9377: columna/fila 150.
    cx, cy = (caja_3116[0] + caja_3116[2]) / 2, (caja_3116[1] + caja_3116[3]) / 2
    (x,), (y,) = transform(M3116, M9377, [cx], [cy])
    col, fila = x - X0, Y1 - y
    h, w = a.shape[:2]
    assert abs(int(a[h // 2, w // 2, 0]) - col) <= 2 and abs(int(a[h // 2, w // 2, 1]) - fila) <= 2


def test_sistema_de_la_ortofoto(tmp_path):
    ruta = crear_geotiff(tmp_path / "s.tif", crs=None)
    caja = (X0 + 100, Y1 - 200, X0 + 200, Y1 - 100)
    with pytest.raises(OrtofotoInvalida, match="elíjalo"):
        hacer_previa(ruta, caja, M9377)
    assert hacer_previa(ruta, caja, M9377, crs_ortofoto=M9377, lado_px=50).cobertura == 1.0
    # Con sistema propio, el elegido no cuenta (no se le gana al archivo).
    propio = crear_geotiff(tmp_path / "p.tif")
    assert hacer_previa(propio, caja, M9377, crs_ortofoto=M3116, lado_px=50).cobertura == 1.0


def test_unidades_del_dibujo_en_mm(tmp_path):
    ruta = crear_geotiff(tmp_path / "a.tif")
    caja_mm = ((X0 + 100) * 1000, (Y1 - 200) * 1000, (X0 + 200) * 1000, (Y1 - 100) * 1000)
    p = hacer_previa(ruta, caja_mm, M9377, mm_por_unidad=1.0, lado_px=100)
    assert pixeles(p.png)[0, 0].tolist() == [100, 100, 200, 255]
    with pytest.raises(ValueError, match="mm_por_unidad"):
        hacer_previa(ruta, caja_mm, M9377, mm_por_unidad=0)
    with pytest.raises(ValueError, match="lado_px"):
        hacer_previa(ruta, caja_mm, M9377, mm_por_unidad=1.0, lado_px=8)


def test_transparencias_nodata_y_alfa(tmp_path):
    caja = (X0, Y1 - 100, X0 + 400, Y1)
    p = hacer_previa(crear_geotiff(tmp_path / "nd.tif", nodata=0), caja, M9377, lado_px=400)
    assert p.cobertura == pytest.approx(0.75, abs=0.01)  # el primer cuarto es nodata
    a = pixeles(p.png)
    assert a[50, 50, 3] == 0 and a[50, 300, 3] == 255
    p = hacer_previa(crear_geotiff(tmp_path / "rgba.tif", alfa=True), caja, M9377, lado_px=400)
    assert p.cobertura == pytest.approx(0.5, abs=0.01)  # mitad izquierda con alfa 0
    assert pixeles(p.png)[50, 100, 3] == 0


def test_gris_paleta_16_bits_y_cinco_bandas(tmp_path):
    caja = (X0 + 100, Y1 - 200, X0 + 200, Y1 - 100)
    a = pixeles(hacer_previa(crear_geotiff(tmp_path / "g.tif", bandas=1), caja, M9377,
                             lado_px=100).png)
    assert a[0, 0].tolist() == [100, 100, 100, 255]  # gris: el mismo valor en las tres
    a = pixeles(hacer_previa(crear_geotiff(tmp_path / "p.tif", paleta=True), caja, M9377,
                             lado_px=100).png)
    assert a[0, 0].tolist() == [100, 155, 50, 255]  # la paleta de la prueba: (i, 255 − i, 50)
    u16 = crear_geotiff(tmp_path / "u.tif", tipo="uint16")
    a = pixeles(hacer_previa(u16, caja, M9377, lado_px=100).png)
    assert a[0, 0, 0] < a[0, 99, 0]  # estirado a 8 bits (sin saturar todo)
    # El mismo estiramiento en toda la ortofoto: la columna 150 vale igual en otra caja.
    b = pixeles(hacer_previa(u16, (X0 + 150, Y1 - 200, X0 + 250, Y1 - 100), M9377,
                             lado_px=100).png)
    assert b[0, 0, 0] == a[0, 50, 0]
    a = pixeles(hacer_previa(crear_geotiff(tmp_path / "c.tif", bandas=5), caja, M9377,
                             lado_px=100).png)
    assert a[0, 0].tolist() == [100, 100, 200, 255]


def test_girada_se_endereza(tmp_path):
    """Girada 90°: la columna de la foto corre hacia el SUR y la fila hacia el OESTE (affine)."""
    ruta = crear_geotiff(tmp_path / "g.tif", giro_grados=90)
    # Con giro de 90°: x = X0 + fila, y = Y1 + columna (la foto queda al norte-este del origen).
    caja = (X0 + 100, Y1 + 100, X0 + 200, Y1 + 200)
    p = hacer_previa(ruta, caja, M9377, lado_px=100)
    assert p.cobertura == 1.0
    a = pixeles(p.png)
    # Arriba-izquierda de la caja: x = X0 + 100 → fila 100; y = Y1 + 200 → columna 200.
    assert abs(int(a[0, 0, 1]) - 100) <= 1 and abs(int(a[0, 0, 0]) - 199) <= 1


def test_bigtiff_en_mosaicos_jpeg_con_piramides(tmp_path):
    ruta = crear_geotiff(tmp_path / "big.tif", ancho=2048, alto=2048, mosaicos=True,
                         compresion="jpeg", piramides=(2, 4, 8), bigtiff=True)
    p = hacer_previa(ruta, (X0, Y1 - 2048, X0 + 2048, Y1), M9377, lado_px=256)
    assert p.px == (256, 256) and p.cobertura == 1.0


@pytest.mark.skipif(not FOTO_TUNEZ.is_file(), reason="falta data/input/ortofotos/Foto_tunez.tif")
def test_la_ortofoto_real_cae_en_su_lugar():
    # Dentro de la foto: todo cubierto; la esquina sureste de la foto, a medias.
    p = hacer_previa(FOTO_TUNEZ, (4705600, 2200900, 4706400, 2201400), M9377, lado_px=400)
    assert p.cobertura == 1.0 and p.px == (400, 250)
    p = hacer_previa(FOTO_TUNEZ, (4706290.0755, 2200481.8987, 4707290.0755, 2200981.8987), M9377,
                     lado_px=400)
    assert p.cobertura == pytest.approx(0.25, abs=0.01)  # 500 × 250 m de 1000 × 500 m
