"""plano.json versión 4: la sección "ortofoto" (lectura y validación). La composición en el
PDF se prueba en test_componer_ortofoto.py."""

import json

import pytest

from componedor.plano import PlanoInvalido, leer_plano
from componedor.plano_ortofoto import OrtofotoPlano

ORTOFOTO = {"archivo": "../data/ortofotos/Foto_tunez.tif", "bytes": 3445480,
            "modificado": "2026-11-18T21:26:25Z", "crs": None, "crs_dibujo": "EPSG:9377",
            "opacidad": 0.6}


def escribir(carpeta, datos):
    ruta = carpeta / "planos" / "plano.json"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    return ruta


def plano(version=4, **extra):
    return {"version": version, "formato": "formato.json",
            "detalles": [{"id": "d1", "manifiesto": "a.manifest.json", "posicion_mm": [30, 40]}],
            **extra}


def error(tmp_path, datos) -> str:
    with pytest.raises(PlanoInvalido) as e:
        leer_plano(escribir(tmp_path, datos))
    return str(e.value)


def test_leer_la_ortofoto(tmp_path):
    p = leer_plano(escribir(tmp_path, plano(ortofoto=ORTOFOTO)))
    assert p.version == 4
    assert p.ortofoto == OrtofotoPlano(
        (tmp_path / "data" / "ortofotos" / "Foto_tunez.tif").resolve(), 3445480, None,
        "EPSG:9377", 0.6, "2026-11-18T21:26:25Z")
    # Lo mínimo: el archivo (opacidad 1, sin sistemas todavía).
    p = leer_plano(escribir(tmp_path, plano(ortofoto={"archivo": "x.TIFF"})))
    assert p.ortofoto == OrtofotoPlano((tmp_path / "planos" / "x.TIFF").resolve())
    # La versión 4 sin ortofoto también vale (y la 3 sigue igual).
    assert leer_plano(escribir(tmp_path, plano())).ortofoto is None
    assert leer_plano(escribir(tmp_path, plano(version=3))).ortofoto is None


def test_solo_en_la_version_4(tmp_path):
    assert "ortofoto: solo existe en la versión 4 del plano" in error(
        tmp_path, plano(version=3, ortofoto=ORTOFOTO))


@pytest.mark.parametrize("cambio, esperado", [
    ({"archivo": ""}, "ortofoto.archivo: se esperaba la ruta del GeoTIFF"),
    ({"archivo": "foto.jpg"}, "ortofoto.archivo: 'foto.jpg' no es un .tif"),
    ({"bytes": -1}, "ortofoto.bytes: se esperaba un entero ≥ 0"),
    ({"bytes": True}, "ortofoto.bytes"),
    ({"crs": "9377"}, "ortofoto.crs: se esperaba «EPSG:<código>»"),
    ({"crs_dibujo": "MAGNA"}, "ortofoto.crs_dibujo: se esperaba «EPSG:<código>»"),
    ({"opacidad": 1.5}, "ortofoto.opacidad: se esperaba un número de 0 a 1"),
    ({"modificado": "18/11/2026"}, "ortofoto.modificado: se esperaba la fecha"),
    ({"modificado": "2026-11-18T21:26:25"}, "ortofoto.modificado"),
    ({"opacidad": "70 %"}, "ortofoto.opacidad"),
    ({"ruta": "x"}, "ortofoto.ruta: campo no reconocido"),
])
def test_ortofoto_invalida(tmp_path, cambio, esperado):
    assert esperado in error(tmp_path, plano(ortofoto={**ORTOFOTO, **cambio}))


def test_ortofoto_que_no_es_objeto(tmp_path):
    assert "ortofoto: se esperaba un objeto" in error(tmp_path, plano(ortofoto="a.tif"))

