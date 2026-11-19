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



# --- versión 5: ortofoto por detalle ------------------------------------------------------------

PENDIENTE = {"id": "via", "origen": {"dxf": "d1", "bloque": "via", "handle": "1B5E5",
                                     "ocurrencia": 1, "escala": "1:500",
                                     "tamano_m": [218.4, 223.7]},
             "centro_mm": [300, 300]}
DXF = [{"id": "d1", "archivo": "prgd.dxf", "sha256": "4b1d" + "0" * 60, "margen_mm": 5}]


def test_version_5_por_detalle(tmp_path):
    datos = plano(version=5, ortofoto=ORTOFOTO, dxf=DXF)
    datos["detalles"] = [{**datos["detalles"][0], "ortofoto": True},
                         {"id": "perfil", "manifiesto": "b.manifest.json", "posicion_mm": [300, 40]},
                         {**PENDIENTE, "ortofoto": True}]
    p = leer_plano(escribir(tmp_path, datos))
    assert p.version == 5 and [d.ortofoto for d in p.detalles] == [True, False]
    assert p.pendientes[0].ortofoto is True


def test_la_version_4_se_lee_con_todos_los_detalles(tmp_path):
    datos = plano(ortofoto=ORTOFOTO, dxf=DXF)
    datos["detalles"].append(PENDIENTE)
    p = leer_plano(escribir(tmp_path, datos))
    assert [d.ortofoto for d in p.detalles] == [True] and p.pendientes[0].ortofoto is True
    assert [d.ortofoto for d in leer_plano(escribir(tmp_path, plano())).detalles] == [False]


@pytest.mark.parametrize("version, detalle, seccion, esperado", [
    (4, {"ortofoto": True}, True, "detalles[0].ortofoto: solo existe en la versión 5"),
    (5, {"ortofoto": "sí"}, True, "detalles[0].ortofoto: se esperaba true o false"),
    (5, {"ortofoto": True}, False, ("detalle 'd1': lleva \"ortofoto\": true, pero el plano no "
                                    "tiene la sección \"ortofoto\"")),
])
def test_ortofoto_por_detalle_mal_escrita(tmp_path, version, detalle, seccion, esperado):
    datos = plano(version=version, **({"ortofoto": ORTOFOTO} if seccion else {}))
    datos["detalles"] = [{**datos["detalles"][0], **detalle}]
    assert esperado in error(tmp_path, datos)


def test_pendiente_con_ortofoto_en_la_version_4_es_error(tmp_path):
    datos = plano(ortofoto=ORTOFOTO, dxf=DXF)
    datos["detalles"] = [{**PENDIENTE, "ortofoto": True}]
    assert "detalles[0].ortofoto: solo existe en la versión 5" in error(tmp_path, datos)
