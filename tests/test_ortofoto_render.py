"""Pintar la ortofoto en una caja (ortofoto_render): factor entero y mosaicos sin costuras."""

import numpy as np
import pytest
from ortofoto_sintetica import ORIGEN, crear_geotiff
from rasterio.warp import transform_bounds

from componedor.ortofoto import OrtofotoInvalida, leer_sistema
from componedor.ortofoto_render import abrir_fuente, pintar, ventana_fuente

X0, Y1 = ORIGEN
M9377 = leer_sistema("EPSG:9377")
M3116 = leer_sistema("EPSG:3116")


def test_factor_y_resolucion_en_el_dibujo(tmp_path):
    with abrir_fuente(crear_geotiff(tmp_path / "a.tif", pixel=0.5)) as f:
        caja = (X0, Y1 - 100, X0 + 100, Y1)
        assert f.factor(caja, 200, 200, M9377) == 1  # 0,5 m por píxel: justo
        assert f.factor(caja, 50, 50, M9377) == 4  # 2 m por píxel de destino
        assert f.factor(caja, 30, 30, M9377) == 6  # 3,33 → 6 (entero hacia abajo)
        assert f.resolucion_en_dibujo(caja, M9377) == pytest.approx(0.5)


def test_ventana_alineada_al_factor(tmp_path):
    with abrir_fuente(crear_geotiff(tmp_path / "a.tif", ancho=400, alto=300)) as f:
        v = ventana_fuente(f.d, (X0 + 101.3, Y1 - 157.2, X0 + 203.9, Y1 - 50.5), 4)
        assert v.col_off % 4 == 0 and v.row_off % 4 == 0
        assert v.width % 4 == 0 and v.height % 4 == 0
        assert v.col_off <= 101.3 - 8 and v.col_off + v.width >= 203.9 + 8
        assert ventana_fuente(f.d, (0, 0, 1, 1), 4) is None


@pytest.mark.parametrize("factor, reproyectar", [(1, False), (3, False), (2, True)])
def test_dos_mosaicos_son_la_misma_imagen_que_uno(tmp_path, factor, reproyectar):
    """Con el mismo factor entero, pintar la caja en dos mitades da EXACTAMENTE lo mismo que
    pintarla entera: en el PDF no se notan las uniones entre mosaicos."""
    ruta = crear_geotiff(tmp_path / "a.tif", ancho=600, alto=400, piramides=(2, 4))
    caja = (X0 + 37.3, Y1 - 351.9, X0 + 537.3, Y1 - 51.9)  # no alineada a la grilla
    crs = M9377
    if reproyectar:  # la misma zona, con el dibujo en otro sistema
        crs = M3116
        caja = transform_bounds(M9377, M3116, *caja)
    ancho, alto = 400, 240
    with abrir_fuente(ruta) as f:
        rgb, alfa = pintar(f, caja, ancho, alto, crs, factor)
        medio = caja[0] + (caja[2] - caja[0]) * 160 / ancho
        izq = pintar(f, (caja[0], caja[1], medio, caja[3]), 160, alto, crs, factor)
        der = pintar(f, (medio, caja[1], caja[2], caja[3]), ancho - 160, alto, crs, factor)
    unidas = np.concatenate([izq[0], der[0]], axis=2)
    assert np.abs(unidas.astype(int) - rgb.astype(int)).max() <= 1
    assert (np.concatenate([izq[1], der[1]], axis=1) == alfa).all()


def test_sin_sistema_no_se_abre(tmp_path):
    with pytest.raises(OrtofotoInvalida, match="elíjalo"), abrir_fuente(
            crear_geotiff(tmp_path / "s.tif", crs=None)):
        pass
    with abrir_fuente(crear_geotiff(tmp_path / "t.tif", crs=None), M9377) as f:
        assert f.crs == M9377


def test_fuera_de_la_ortofoto(tmp_path):
    with abrir_fuente(crear_geotiff(tmp_path / "a.tif")) as f:
        rgb, alfa = pintar(f, (0, 0, 10, 10), 20, 20, M9377, 1)
    assert rgb.shape == (3, 20, 20) and alfa.max() == 0
