"""Cabecera de la ortofoto (GeoTIFF): ficha, avisos y sistemas de coordenadas."""

import warnings

import pytest
from ortofoto_sintetica import FOTO_TUNEZ, ORIGEN, crear_geotiff
from rasterio.errors import NotGeoreferencedWarning

from componedor.ortofoto import (
    SISTEMAS_COMUNES,
    OrtofotoInvalida,
    SistemaInvalido,
    leer_cabecera,
    leer_sistema,
    texto_sistema,
    validar_ruta,
)


def niveles(ficha):
    return [a["nivel"] for a in ficha["avisos"]]


def test_ficha_de_un_geotiff_simple(tmp_path):
    ruta = crear_geotiff(tmp_path / "a.tif", ancho=400, alto=300, pixel=0.5)
    f = leer_cabecera(ruta)
    assert f["nombre"] == "a.tif" and f["bytes"] == ruta.stat().st_size
    assert f["px"] == [400, 300] and f["bandas"] == 3 and f["tipo"] == "uint8"
    assert f["color"] == "RGB"
    assert f["sistema"] == {"codigo": "EPSG:9377", "nombre": "MAGNA-SIRGAS 2018 / Origen-Nacional"}
    assert f["resolucion"] == [0.5, 0.5]
    assert f["limites"] == [ORIGEN[0], ORIGEN[1] - 150, ORIGEN[0] + 200, ORIGEN[1]]
    assert (f["girada"], f["piramides"], f["mosaicos"], f["bigtiff"]) == (False, [], False, False)
    assert f["compresion"] is None and f["fondo"] is None and f["nodata"] is None
    assert f["avisos"] == []
    assert f["modificado"].endswith("Z")


def test_mosaicos_compresion_piramides_y_bigtiff(tmp_path):
    ruta = crear_geotiff(tmp_path / "grande.tif", ancho=1024, alto=768, mosaicos=True,
                         compresion="lzw", piramides=(2, 4, 8), bigtiff=True)
    f = leer_cabecera(ruta)
    assert f["mosaicos"] and f["bloque_px"] == [256, 256]
    assert f["compresion"] == "lzw" and f["piramides"] == [2, 4, 8] and f["bigtiff"]
    assert f["avisos"] == []


def test_jpeg_en_mosaicos(tmp_path):
    f = leer_cabecera(crear_geotiff(tmp_path / "j.tif", ancho=512, alto=512, mosaicos=True,
                                    compresion="jpeg"))
    assert f["compresion"] == "jpeg" and f["color"] == "RGB"


def test_sin_sistema_pide_elegirlo_sin_suponer(tmp_path):
    f = leer_cabecera(crear_geotiff(tmp_path / "s.tif", crs=None))
    assert f["sistema"] is None
    assert niveles(f) == ["elegir"]
    assert "no se supone" in f["avisos"][0]["texto"]


def test_sin_georreferencia_se_rechaza(tmp_path):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", NotGeoreferencedWarning)
        ruta = crear_geotiff(tmp_path / "plano.tif", sin_georreferencia=True)
        with pytest.raises(OrtofotoInvalida, match="no tiene georreferencia"):
            leer_cabecera(ruta)


def test_girada_banda_unica_16_bits_alfa_nodata_y_paleta(tmp_path):
    f = leer_cabecera(crear_geotiff(tmp_path / "g.tif", giro_grados=10))
    assert f["girada"] and niveles(f) == ["aviso"] and "endereza" in f["avisos"][0]["texto"]
    f = leer_cabecera(crear_geotiff(tmp_path / "gris.tif", bandas=1))
    assert f["color"] == "gris" and f["avisos"] == []
    f = leer_cabecera(crear_geotiff(tmp_path / "u16.tif", tipo="uint16"))
    assert f["tipo"] == "uint16" and "brillo" in f["avisos"][0]["texto"]
    f = leer_cabecera(crear_geotiff(tmp_path / "rgba.tif", alfa=True))
    assert (f["color"], f["fondo"]) == ("RGBA", "alfa")
    f = leer_cabecera(crear_geotiff(tmp_path / "nd.tif", nodata=0))
    assert (f["fondo"], f["nodata"]) == ("nodata", 0)
    f = leer_cabecera(crear_geotiff(tmp_path / "pal.tif", paleta=True))
    assert f["color"] == "paleta"
    f = leer_cabecera(crear_geotiff(tmp_path / "cinco.tif", bandas=5))
    assert "tres primeras" in f["avisos"][0]["texto"]


def test_grande_sin_piramides_ni_mosaicos_avisa(tmp_path):
    f = leer_cabecera(crear_geotiff(tmp_path / "g.tif", ancho=8000, alto=10, bandas=1))
    textos = " ".join(a["texto"] for a in f["avisos"])
    assert "No tiene pirámides" in textos and "gdaladdo" in textos and "franjas" in textos


def test_validar_ruta(tmp_path):
    with pytest.raises(OrtofotoInvalida, match="no es un GeoTIFF"):
        validar_ruta(tmp_path / "foto.png")
    with pytest.raises(OrtofotoInvalida, match="No existe"):
        validar_ruta(tmp_path / "falta.TIF")
    roto = tmp_path / "roto.tiff"
    roto.write_bytes(b"esto no es un tiff")
    with pytest.raises(OrtofotoInvalida, match="No se pudo leer"):
        leer_cabecera(roto)


def test_leer_sistema():
    assert leer_sistema("EPSG:9377").to_epsg() == 9377
    assert leer_sistema(" epsg:3116 ").to_epsg() == 3116
    for malo in ("9377", "EPSG:", None, 3116, "WGS84"):
        with pytest.raises(SistemaInvalido, match="no válido"):
            leer_sistema(malo)
    with pytest.raises(SistemaInvalido, match="no es un sistema proyectado"):
        leer_sistema("EPSG:4326")
    with pytest.raises(SistemaInvalido, match="no conoce"):
        leer_sistema("EPSG:99999")
    assert texto_sistema(None) is None


def test_los_sistemas_comunes_son_proyectados_y_conocidos():
    codigos = [c for c, _ in SISTEMAS_COMUNES]
    assert codigos[0] == "EPSG:9377" and len(set(codigos)) == len(codigos)
    for codigo, _ in SISTEMAS_COMUNES:
        assert leer_sistema(codigo).is_projected


@pytest.mark.skipif(not FOTO_TUNEZ.is_file(), reason="falta data/input/ortofotos/Foto_tunez.tif")
def test_la_ortofoto_real_de_prueba():
    f = leer_cabecera(FOTO_TUNEZ)
    assert f["px"] == [1421, 807] and f["color"] == "RGB" and f["tipo"] == "uint8"
    assert f["sistema"]["codigo"] == "EPSG:9377"
    assert f["resolucion"][0] == pytest.approx(1.0815, abs=1e-4)
    assert f["limites"][0] == pytest.approx(4705253.2127) and f["limites"][3] == pytest.approx(2201604.6983)
    assert f["avisos"] == []
