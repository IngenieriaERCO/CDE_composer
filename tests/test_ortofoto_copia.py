"""Copia reducida de la ortofoto (ortofoto_copia): un GeoTIFF por detalle, al día o reemplazada."""

import rasterio
from conftest import MATRIZ_SINTETICA, X0_CAD, Y0_CAD
from ortofoto_sintetica import crear_geotiff

from componedor.cad_a_papel import MatrizCad
from componedor.ortofoto import leer_sistema
from componedor.ortofoto_copia import (
    archivo_de,
    carpeta_copia,
    escribir_copia,
    leer_indice,
    plan_de_copia,
)
from componedor.ortofoto_pdf import DetalleOrtofoto
from componedor.ortofoto_render import abrir_fuente

M9377 = leer_sistema("EPSG:9377")
DET = DetalleOrtofoto("Vía 1/2", (30.0, 40.0, 290.0, 160.0), MatrizCad(*MATRIZ_SINTETICA), 1000.0)
ORIGINAL = {"nombre": "orto.tif", "bytes": 1, "modificado": "2026-11-18T21:26:25Z"}


def fuente(tmp_path, pixel):
    return abrir_fuente(crear_geotiff(tmp_path / "orto.tif", ancho=800, alto=400, pixel=pixel,
                                      origen=(X0_CAD - 4, Y0_CAD + 8)))  # cubre también el margen


def test_carpeta_y_resolucion(tmp_path):
    assert carpeta_copia(tmp_path / "planos" / "Plano 7.json") == tmp_path / "planos" / "Plano 7_ortofoto"
    with fuente(tmp_path, 0.05) as f:  # 5 cm: más grueso que 300 ppp a 1:50 (4,2 mm de terreno)
        (p,) = plan_de_copia([DET], f, M9377, 300)
    assert p["archivo"] == "01_V_a_1_2.tif"
    assert p["px"] == [312, 144]  # 15,6 × 7,2 m (página + 10 %) a 5 cm: nunca más fina
    with fuente(tmp_path, 0.001) as f:  # 1 mm: más fina que 300 ppp → la del PDF
        (p,) = plan_de_copia([DET], f, M9377, 300)
    assert p["px"] == [3686, 1701]  # 3071 × 1417 px del PDF + 10 % por lado (hacia arriba)


def test_escribir_al_dia_y_reemplazar(tmp_path):
    carpeta = tmp_path / "plano_ortofoto"
    with fuente(tmp_path, 0.05) as f:
        a = escribir_copia(carpeta, ORIGINAL, [DET], f, M9377, 300, 85)
        assert a.escrita and a.archivos == 1 and a.bytes > 0
        ruta = archivo_de(carpeta, leer_indice(carpeta), "Vía 1/2")
        with rasterio.open(ruta) as d:
            assert (d.crs.to_epsg(), d.width, d.height, d.compression.name) == (
                9377, 312, 144, "jpeg")
            assert d.block_shapes[0] == (512, 512) or d.block_shapes[0][0] <= 512
            assert d.dataset_mask().min() == 255  # todo con foto
        assert escribir_copia(carpeta, ORIGINAL, [DET], f, M9377, 300, 85).escrita is False
        # Otro original: se reescribe aparte y reemplaza a la vieja (sin dejar restos).
        b = escribir_copia(carpeta, {**ORIGINAL, "bytes": 2}, [DET], f, M9377, 300, 85)
        assert b.escrita and leer_indice(carpeta)["original"]["bytes"] == 2
    assert sorted(x.name for x in tmp_path.iterdir()) == ["orto.tif", "plano_ortofoto"]
    assert archivo_de(carpeta, leer_indice(carpeta), "otro") is None
    assert leer_indice(tmp_path / "no_hay") is None
