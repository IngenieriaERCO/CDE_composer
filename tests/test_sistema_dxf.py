"""El sistema de coordenadas del DXF (dxf.crs del Exportador): código para prellenar el selector
y aviso si el código no coincide con el nombre (caso real de PRGD)."""

import pytest

from componedor.sistema_dxf import sistema_del_dxf, zona

# Como lo manda el Exportador (protocolo, dxf.crs), con los datos reales de PRGD y GUAMO.
PRGD = {"source": "GEODATA", "format": "xml", "id": None, "name": "MAGNA_Colombia CTM12",
        "description": None, "authority": "EPSG:3115", "epsg": 3115, "epsg_from": "authority"}
GUAMO = {"source": "GEODATA", "format": "xml", "id": "MAGNA.Columbia-Bogota",
         "name": "MAGNA.Columbia-Bogota", "description": "MAGNA-SIRGAS / Colombia Bogota zone",
         "authority": "EPSG, V6.11.2, 3116 [Instituto Geografico Agustin Caduzzi (I]",
         "epsg": 3116, "epsg_from": "alias"}


def test_prgd_codigo_y_nombre_no_coinciden():
    s = sistema_del_dxf(PRGD)
    assert s["codigo"] == "EPSG:3115"
    # Salió del texto de la autoridad (epsg_from "authority"): el selector NO se preselecciona.
    assert s["prellenar"] is False
    assert s["oficial"] == "MAGNA-SIRGAS / Colombia West zone"
    assert s["sugerido"] == "EPSG:9377"
    assert s["aviso"] == ("El DXF dice «MAGNA_Colombia CTM12», pero su código es EPSG:3115 "
                          "(MAGNA-SIRGAS / Colombia West zone): no coinciden. «MAGNA_Colombia "
                          "CTM12» corresponde a EPSG:9377 (Origen-Nacional). Revise el sistema "
                          "del dibujo.")


def test_guamo_coincide():
    s = sistema_del_dxf(GUAMO)
    assert (s["codigo"], s["aviso"], s["sugerido"]) == ("EPSG:3116", None, None)
    assert s["prellenar"] is True  # de un Alias del GEODATA: se preselecciona (editable)
    assert s["nombre"] == "MAGNA.Columbia-Bogota"


@pytest.mark.parametrize("valor, codigo", [
    (None, None), ({"source": "GEODATA", "format": "unknown", "epsg": None}, None),
    ("EPSG:9377", "EPSG:9377"), (" epsg:3116 ", "EPSG:3116"), (9377, "EPSG:9377"),
    ({"code": "EPSG:9377"}, "EPSG:9377"), ("MAGNA", None), (True, None),
])
def test_formas_aceptadas(valor, codigo):
    s = sistema_del_dxf(valor)
    assert (s["codigo"] if s else None) == codigo


def test_de_la_autoridad_nunca_se_preselecciona_aunque_coincida():
    s = sistema_del_dxf({**GUAMO, "epsg_from": "authority"})
    assert (s["codigo"], s["aviso"], s["prellenar"]) == ("EPSG:3116", None, False)
    assert sistema_del_dxf({"name": "x", "epsg": 9377})["prellenar"] is True  # sin epsg_from
    assert sistema_del_dxf("EPSG:9377")["prellenar"] is True


def test_codigo_que_no_sirve_avisa():
    s = sistema_del_dxf({"name": "WGS 84", "epsg": 4326})
    assert s["oficial"] is None and "no es un sistema proyectado" in s["aviso"]


@pytest.mark.parametrize("texto, esperada", [
    ("MAGNA_Colombia CTM12", "Origen-Nacional"),
    ("MAGNA-SIRGAS 2018 / Origen-Nacional", "Origen-Nacional"),
    ("MAGNA-SIRGAS / Colombia Far West zone", "Far West"),
    ("MAGNA-SIRGAS / Colombia East Central zone", "East Central"),
    ("Colombia Este Central", "East Central"),
    ("MAGNA-SIRGAS / Colombia West zone", "West"),
    ("Colombia Oeste", "West"),
    ("MAGNA-SIRGAS / Colombia East zone", "East"),
    ("MAGNA.Columbia-Bogota", "Bogotá"),
    ("Bogotá", "Bogotá"),
    ("Mi sistema local", None), (None, None),
])
def test_zona_por_el_nombre(texto, esperada):
    z = zona(texto)
    assert (z[0] if z else None) == esperada
