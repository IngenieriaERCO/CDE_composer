"""Estilo de impresión al exportar (estilos_impresion.py): lista de tablas .ctb, elección solo
por nombre, marca del nombre del paquete, estilo leído del manifiesto y configuración."""

import hashlib
import json
import zlib

import pytest

from componedor.configuracion import ConfigInvalida, leer_config_exportador
from componedor.estilos_impresion import (
    EstiloInvalido,
    descripcion_ctb,
    elegir,
    estilo_del_manifiesto,
    listar,
    marca,
    nombre_valido,
    opciones,
    texto_estilo,
)
from componedor.exportar_dxf import Pedido, motivos_de_otro_pedido
from componedor.nombres_paquete import MAX_PAQUETE, nombre_paquete

CABECERA = b"PIAFILEVERSION_2.0,CTBVER1,compress\r\npmzlibcodec"


def ctb(ruta, descripcion="Tabla de prueba", relleno=""):
    """Una .ctb con la forma de AutoCAD: 60 bytes de cabecera y el texto comprimido."""
    texto = f'description="{descripcion}\naci_table_available=TRUE\n{relleno}'.encode("cp1252")
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(CABECERA.ljust(60, b"\0") + zlib.compress(texto))
    return ruta


def test_listar_las_tablas_de_la_carpeta(tmp_path):
    a = ctb(tmp_path / "ctb" / "CTB_ERCO_derivada_PRGD.ctb", "Derivada del PDF de AutoCAD")
    ctb(tmp_path / "ctb" / "acad.CTB", "Diseños ERCO")
    (tmp_path / "ctb" / "notas.json").write_text("{}", encoding="utf-8")
    ctb(tmp_path / "ctb" / "sub" / "otra.ctb")  # solo ese nivel
    lista = listar(tmp_path / "ctb")
    assert [e.nombre for e in lista] == ["acad.CTB", "CTB_ERCO_derivada_PRGD.ctb"]
    e = lista[1]
    assert e.sha256 == hashlib.sha256(a.read_bytes()).hexdigest()
    assert e.descripcion == "Derivada del PDF de AutoCAD" and lista[0].descripcion == "Diseños ERCO"
    assert e.para_el_editor() == {"nombre": e.nombre, "sha256": e.sha256,
                                  "descripcion": e.descripcion}  # nunca la ruta
    assert listar(None) == [] and listar(tmp_path / "no_esta") == []
    assert descripcion_ctb(b"no es una ctb") == ""


def test_solo_se_elige_por_nombre_de_la_lista(tmp_path):
    carpeta = tmp_path / "ctb"
    ctb(carpeta / "CTB_ERCO.ctb")
    ctb(tmp_path / "fuera.ctb")
    assert elegir(carpeta, None) is None
    assert elegir(carpeta, "ctb_erco.CTB").nombre == "CTB_ERCO.ctb"
    for nombre in ("../fuera.ctb", str(tmp_path / "fuera.ctb"), "sub/CTB_ERCO.ctb",
                   "..\\fuera.ctb", "CTB_ERCO.stb", "", 5):
        assert not nombre_valido(nombre)
        with pytest.raises(EstiloInvalido, match="sin carpetas"):
            elegir(carpeta, nombre)
    with pytest.raises(EstiloInvalido, match="no está en la carpeta"):
        elegir(carpeta, "otra.ctb")


def test_marca_y_opciones_del_pedido(tmp_path):
    e = listar(ctb(tmp_path / "x.ctb").parent)[0]
    assert marca(None, True) == ""
    assert marca(e.sha256, True) == "_p" + e.sha256[:6]
    assert marca(e.sha256, False) == "_p" + e.sha256[:6] + "_t" and marca(None, False) == "_t"
    assert opciones(None, True) == {}  # el pedido de siempre
    assert opciones(e, False) == {"plot_style": str(e.ruta), "print_transparency": False}


def test_nombre_del_paquete_con_marca():
    assert nombre_paquete("I1.M1.PV1_12900", 75, "_pb4a909_t") == "I1.M1.PV1_12900_1-75_pb4a909_t"
    largo = "Bloque_de_nombre_muy_largo_que_casi_llena_los_sesenta_caracteres"
    n = nombre_paquete(largo, 500, "_pb4a909_t")
    assert len(n) <= MAX_PAQUETE and n.endswith("_1-500_pb4a909_t")
    assert n != nombre_paquete(largo, 500)  # no choca con el viejo


def test_estilo_del_manifiesto():
    viejo = {"options": {"margin_mm": 5}}  # 1.3: sin las opciones
    assert estilo_del_manifiesto(viejo) == {"ctb": None, "sha256": None, "transparencia": True}
    nuevo = {"options": {"plot_style": {"name": "CTB_ERCO_derivada_PRGD.ctb", "sha256": "b4a909ea" * 8},
                         "print_transparency": False}}
    e = estilo_del_manifiesto(nuevo)
    assert e == {"ctb": "CTB_ERCO_derivada_PRGD.ctb", "sha256": "b4a909ea" * 8, "transparencia": False}
    assert texto_estilo(e) == "CTB_ERCO_derivada_PRGD.ctb (b4a909…), sin transparencia"
    assert texto_estilo(estilo_del_manifiesto(viejo)) == "sin CTB"
    assert estilo_del_manifiesto({"options": "x"})["ctb"] is None


def test_un_paquete_con_otro_estilo_no_es_el_pedido():
    sha = "b4a909ea" * 8
    base = {"source": {"dxf_sha256": "d" * 64, "reference": {"handle": "12900"}},
            "scale": {"denominator": 75}, "pdf": {"margin_mm": 5.0, "page_size_mm": [100, 100]}}
    pedido = Pedido("d" * 64, "12900", 75.0, 5.0, (100.0, 100.0), True, sha, False)
    con = {**base, "options": {"plot_style": {"name": "a.ctb", "sha256": sha},
                               "print_transparency": False}}
    assert motivos_de_otro_pedido(con, pedido) == []
    motivos = motivos_de_otro_pedido(base, pedido)  # el paquete viejo, sin opciones
    assert any("otro estilo de impresión (sin CTB" in m for m in motivos)
    assert any("imprime la transparencia" in m for m in motivos)
    sin = Pedido("d" * 64, "12900", 75.0, 5.0, (100.0, 100.0))
    assert motivos_de_otro_pedido(base, sin) == []
    assert "se pidió sin CTB" in motivos_de_otro_pedido(con, sin)[0]


def config(tmp_path, **exportador):
    ruta = tmp_path / "componedor.json"
    ruta.write_text(json.dumps({"version": 1, "formato": "f.json", "exportador": {
        "comando": "cde-exporter", "trabajo": "trabajo", **exportador}}), encoding="utf-8")
    return ruta


def test_configuracion_del_estilo(tmp_path):
    c = leer_config_exportador(config(tmp_path))
    assert (c.carpeta_ctb, c.estilo_impresion, c.imprimir_transparencia) == (None, None, True)
    c = leer_config_exportador(config(tmp_path, carpeta_ctb="../Exportador Vectorial/data/input/ctb",
                                      estilo_impresion="CTB_ERCO_derivada_PRGD.ctb",
                                      imprimir_transparencia=False))
    assert c.carpeta_ctb == tmp_path / "../Exportador Vectorial/data/input/ctb"
    assert c.estilo_impresion == "CTB_ERCO_derivada_PRGD.ctb" and c.imprimir_transparencia is False
    with pytest.raises(ConfigInvalida) as e:
        leer_config_exportador(config(tmp_path, carpeta_ctb="ctb", estilo_impresion="../x.ctb",
                                      imprimir_transparencia="no"))
    assert "estilo_impresion: se esperaba el NOMBRE" in str(e.value)
    assert "imprimir_transparencia: se esperaba true o false" in str(e.value)
    with pytest.raises(ConfigInvalida, match="falta exportador.carpeta_ctb"):
        leer_config_exportador(config(tmp_path, estilo_impresion="x.ctb"))
