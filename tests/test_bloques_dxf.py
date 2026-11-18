"""Respuesta de `load` → carpeta del DXF del editor: tamaño, unidades, escala sugerida, notas."""

import copy

import pytest
from conftest import ZONA_A1

from componedor.bloques_dxf import (
    RespuestaInvalida,
    catalogo_dxf,
    escala_sugerida,
    pagina_mm,
)
from componedor.inventario import ESCALAS_ESTANDAR

UNIDADES = {"declared_code": 6, "name": "m", "millimeters_per_unit": 1000.0,
            "status": "declaradas en el DXF y coherentes", "verified": True, "warnings": []}


def bloque(nombre="B1", tamano=(10.0, 4.0), **cambios):
    b = {"ref": f"{nombre}#1", "name": nombre, "handle": "1A", "occurrence": 1,
         "total_occurrences": 1, "layer": "0",
         "bounds": {"min": [0, 0], "max": list(tamano), "exact": True},
         "size_cad": list(tamano), "size_m": list(tamano), "units": dict(UNIDADES),
         "entities": 12, "contains": {"solids_3d": 0, "regions": 0, "proxies": 0, "texts": 0,
                                      "hatches": 0, "images": 0},
         "hidden_layer_entities": 0, "file_stem": nombre}
    b.update(cambios)
    return b


def respuesta(*bloques, **cambios):
    r = {"session": "s-1",
         "dxf": {"name": "obra.dxf", "path": "C:\\obras\\obra.dxf", "bytes": 6781020,
                 "modified": "2026-11-12T16:17:03-05:00", "fingerprint": "8f0c", "sha256": "4b1d",
                 "dxf_version": "AC1032", "read_seconds": 1.5, "source_copy": None},
         "units": dict(UNIDADES), "margin_mm": 5.0, "blocks": list(bloques) or [bloque()],
         "omitted": [], "layers": [], "modelspace_loose": [], "notices": []}
    r.update(cambios)
    return r


def test_pagina_con_la_formula_del_contrato():
    assert pagina_mm((10.0, 4.0), 50, 5.0) == pytest.approx((210.0, 90.0))
    assert pagina_mm((957.18, 1350.019), 5000, 5.0) == pytest.approx((201.436, 280.0038))


@pytest.mark.parametrize("tamano, esperada", [
    ((10.0, 4.0), 50),            # 210 x 90 mm a 1:50
    ((31.0, 4.0), 50),            # 630 mm de ancho: cabe justo en 639,7
    ((32.0, 4.0), 100),           # a 1:50 serían 650 mm: no cabe
    ((957.18, 1350.019), 5000),   # BLOQUE1 de GUAMO: a 1:2500 el alto sería 550 > 548,6
    ((200000.0, 1.0), None),      # ni a 1:10000
])
def test_escala_sugerida(tamano, esperada):
    assert escala_sugerida(tamano, 5.0, ZONA_A1) == esperada


def test_catalogo_de_un_bloque():
    c = catalogo_dxf(respuesta(), ZONA_A1)
    assert c["sesion"] == "s-1" and c["margen_mm"] == 5.0
    assert c["dxf"] == {"nombre": "obra.dxf", "ruta": "C:\\obras\\obra.dxf", "bytes": 6781020,
                        "sha256": "4b1d", "huella": "8f0c",
                        "modificado": "2026-11-12T16:17:03-05:00", "version_dxf": "AC1032",
                        "segundos_lectura": 1.5, "copia_reducida": False}
    assert c["unidades"] == {"nombre": "m", "mm_por_unidad": 1000.0, "verificadas": True,
                             "estado": "declaradas en el DXF y coherentes", "avisos": []}
    assert c["escalas"] == list(ESCALAS_ESTANDAR)
    (b,) = c["bloques"]
    assert b == {"ref": "B1#1", "nombre": "B1", "handle": "1A", "ocurrencia": 1,
                 "total_ocurrencias": 1, "capa": "0", "tamano_m": [10.0, 4.0],
                 "unidades": c["unidades"], "caja_exacta": True,
                 "caja_cad": {"min": [0.0, 0.0], "max": [10.0, 4.0]}, "escala_sugerida": 50,
                 "pagina_sugerida_mm": [210.0, 90.0], "entidades": 12, "archivo": "B1",
                 "notas": []}
    assert c["omitidos"] == [] and c["avisos"] == [] and c["problemas"] == []


def test_notas_de_cada_caso():
    c = catalogo_dxf(respuesta(
        bloque("aprox", bounds={"min": [0, 0], "max": [1, 1], "exact": False}),
        bloque("solidos", contains={"solids_3d": 3, "proxies": 2, "regions": 1, "images": 4}),
        bloque("ocultas", hidden_layer_entities=8),
        bloque("enorme", tamano=(200000.0, 1.0)),
        bloque("sin_unidades", size_m=None,
               units={**UNIDADES, "verified": False, "warnings": ["$INSUNITS no declarado"]}),
    ), ZONA_A1)
    notas = {b["nombre"]: b["notas"] for b in c["bloques"]}
    assert notas["aprox"] == [("Caja aproximada (hay bloques anidados girados): la página real "
                               "puede salir algo menor.")]
    assert notas["solidos"] == [
        ("Tiene 3 sólido(s) 3D: la vista previa no los muestra; la exportación los dibuja como "
         "huella en planta."),
        "Tiene 2 objeto(s) proxy (pueden no dibujarse).", "Tiene 1 región(es).",
        "Tiene 4 imagen(es) raster insertada(s)."]
    assert notas["ocultas"] == ["8 objeto(s) en capas apagadas o congeladas: no se dibujan."]
    assert notas["enorme"] == [("No cabe en el área de dibujo ni a 1:10000 (la mayor de la "
                                "lista estándar).")]
    assert notas["sin_unidades"] == [
        ("Unidades sin verificar: no se puede calcular el tamaño en papel. Indique las unidades "
         "del dibujo al cargar el DXF."), "Unidades: $INSUNITS no declarado"]
    sin = next(b for b in c["bloques"] if b["nombre"] == "sin_unidades")
    assert sin["tamano_m"] is None and sin["escala_sugerida"] is None
    assert sin["pagina_sugerida_mm"] is None and sin["unidades"]["verificadas"] is False


def test_ocurrencias_omitidos_y_avisos():
    r = respuesta(bloque("P", ref="P#1"), bloque("P", ref="P#2", occurrence=2,
                                                 total_occurrences=2, handle="2B"),
                  omitted=[{"name": "*U1", "occurrence": 1, "total_occurrences": 1,
                            "handle": "9", "reason": "bloque anónimo"}],
                  notices=[{"code": "X", "severity": "info", "message": "Copia reducida."}],
                  dxf={**respuesta()["dxf"], "source_copy": {"seconds": 3}})
    r["blocks"][0]["total_occurrences"] = 2
    c = catalogo_dxf(r, ZONA_A1)
    assert [(b["ref"], b["ocurrencia"], b["total_ocurrencias"]) for b in c["bloques"]] == [
        ("P#1", 1, 2), ("P#2", 2, 2)]
    assert c["omitidos"] == [{"nombre": "*U1", "ocurrencia": 1, "total_ocurrencias": 1,
                              "motivo": "bloque anónimo"}]
    assert c["avisos"] == ["Copia reducida."] and c["dxf"]["copia_reducida"] is True


@pytest.mark.parametrize("cambio, motivo", [
    ({"handle": None}, "falta «handle» (texto no vacío)"),  # punto 9: nunca null
    ({"handle": ""}, "falta «handle» (texto no vacío)"),
    ({"ref": 3}, "falta «ref» (texto no vacío)"),
    ({"occurrence": 0}, "«occurrence» debe ser un entero ≥ 1"),
    ({"total_occurrences": True}, "«total_occurrences» debe ser un entero ≥ 1"),
    ({"bounds": {"min": [0, 0]}}, "falta «bounds» con «exact»"),
    ({"size_m": [1, "x"]}, "«size_m» debe ser [ancho, alto] en m, o null"),
    ({"size_m": [1, -2]}, "«size_m» debe ser [ancho, alto] en m, o null"),
])
def test_un_bloque_mal_descrito_se_omite_con_su_motivo(cambio, motivo):
    c = catalogo_dxf(respuesta(bloque("bueno"), bloque("malo", **cambio)), ZONA_A1)
    assert [b["nombre"] for b in c["bloques"]] == ["bueno"]
    assert c["problemas"] == [f"bloque 2 («malo»): {motivo}; se omite."]


def test_un_bloque_que_no_es_objeto():
    c = catalogo_dxf(respuesta(bloque(), "x"), ZONA_A1)
    assert c["problemas"] == ["bloque 2: no es un objeto; se omite."]


@pytest.mark.parametrize("quitar, mensaje", [
    ("session", "no trae «session»"),
    ("dxf", "no trae «dxf.name»"),
    ("blocks", "no trae la lista «blocks»"),
    ("margin_mm", "no trae «margin_mm»"),
])
def test_sin_lo_esencial_no_hay_carpeta(quitar, mensaje):
    r = respuesta()
    del r[quitar]
    with pytest.raises(RespuestaInvalida, match=mensaje):
        catalogo_dxf(r, ZONA_A1)
    with pytest.raises(RespuestaInvalida, match="no es un objeto"):
        catalogo_dxf([], ZONA_A1)


def test_no_modifica_la_respuesta():
    r = respuesta(bloque(), bloque("otro"))
    copia = copy.deepcopy(r)
    catalogo_dxf(r, ZONA_A1)
    assert r == copia


@pytest.mark.parametrize("caja, esperada", [
    ({"min": [899699.777, 937885.353], "max": [900656.957, 939235.372], "exact": True},
     {"min": [899699.777, 937885.353], "max": [900656.957, 939235.372]}),
    ({"min": [5, 0], "max": [1, 1], "exact": True}, None),       # min > max
    ({"min": [0, 0], "max": ["x", 1], "exact": True}, None),     # no es número
    ({"exact": False}, None),                                    # sin min/max
])
def test_caja_cad_para_poner_la_vista_previa(caja, esperada):
    """La caja de load (marco único del contrato): su centro va al centro de la página."""
    (b,) = catalogo_dxf(respuesta(bloque(bounds=caja)), ZONA_A1)["bloques"]
    assert b["caja_cad"] == esperada
