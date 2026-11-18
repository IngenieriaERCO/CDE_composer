"""Exportar (etapa 3), las piezas sin servidor: carpeta y nombre, caché, verificación, paquetes
viejos a _para_borrar y posición por el centro CAD. Los paquetes los publica el trabajador
falso (coherentes, como los del exportador)."""

import json
import re
from pathlib import Path

import pytest
from conftest import comando_falso, crear_paquete_real, dxf_falso

from componedor.exportar_dxf import (
    PaqueteNoValido,
    Pedido,
    archivos_del_paquete,
    carpeta_del_dxf,
    de_la_cache,
    motivos_de_otro_pedido,
    mover_a_para_borrar,
    nombre_del_paquete,
    posicion_por_centro,
    verificar,
)
from componedor.paquete import localizar_paquetes
from componedor.trabajador import Trabajador

BLOQUE = {"name": "BLOQUE1", "size_cad": [957.18, 1350.019], "min": [899699.777, 937885.353],
          "handle": "50CA"}


@pytest.fixture
def exportado(tmp_path):
    """Exporta BLOQUE1 a 1:5000 con el trabajador falso. (manifiesto, Pedido, carpeta)."""
    ruta = dxf_falso(tmp_path / "GUAMO.dxf", blocks=[BLOQUE])
    salida = tmp_path / "paquetes" / "GUAMO"
    salida.mkdir(parents=True)
    t = Trabajador(comando_falso(), tmp_path / "trabajo")
    t.iniciar()
    try:
        carga = t.pedir("load", {"dxf": str(ruta), "units": None, "margin_mm": 5.0})
        r = t.pedir("export", {"session": carga["session"], "output_dir": str(salida),
                               "jobs": [{"job": "j1", "ref": "BLOQUE1#1", "scale": "1:5000",
                                         "package": "BLOQUE1_1-5000"}], "options": {}})
    finally:
        t.cerrar()
    pagina = (957.18 / 5 + 10, 1350.019 / 5 + 10)
    pedido = Pedido(carga["dxf"]["sha256"], "50CA", 5000.0, 5.0, pagina, True)
    return r["jobs"][0]["package"]["manifest"], pedido, salida


def test_carpeta_y_nombre():
    assert carpeta_del_dxf("data/input/dxf", "GUAMO prueba Ñ.dxf").as_posix() == \
        "data/input/dxf/GUAMO_prueba_N"
    assert nombre_del_paquete("BLOQUE1", 5000.0) == "BLOQUE1_1-5000"
    assert nombre_del_paquete("Viga", 12.5) == "Viga_1-12.5"


def test_paquete_exportado_verificado(exportado):
    manifiesto, pedido, _ = exportado
    aceptado = verificar(manifiesto, pedido)  # importar_paquete + que sea el pedido
    assert aceptado.paquete.prefijo == "BLOQUE1_1-5000"


@pytest.mark.parametrize("cambio, motivo", [
    ({"sha256": "0" * 64}, "es de otra versión del DXF"),
    ({"handle": "51"}, "es de otra referencia (handle 50CA, se esperaba 51)"),
    ({"denominador": 2500.0}, "está a otra escala (1:5000.0, se esperaba 1:2500)"),
    ({"margen_mm": 10.0}, "tiene otro margen"),
    ({"pagina_max_mm": (150.0, 280.0)}, "más que la caja del editor"),
    ({"pagina_max_mm": (250.0, 290.0)}, "y la caja exacta"),
])
def test_no_es_el_paquete_pedido(exportado, cambio, motivo):
    manifiesto, pedido, carpeta = exportado
    otro = Pedido(**{**pedido.__dict__, **cambio})
    with pytest.raises(PaqueteNoValido, match=re.escape(motivo)):
        verificar(manifiesto, otro)
    assert de_la_cache(carpeta, "BLOQUE1_1-5000", otro) is None


def test_caja_aproximada_admite_pagina_menor(exportado):
    manifiesto, pedido, _ = exportado
    aprox = Pedido(**{**pedido.__dict__, "pagina_max_mm": (250.0, 290.0), "caja_exacta": False})
    datos = json.loads(Path(manifiesto).read_text(encoding="utf-8"))
    assert motivos_de_otro_pedido(datos, aprox) == []


def test_cache(exportado):
    _, pedido, carpeta = exportado
    assert de_la_cache(carpeta, "BLOQUE1_1-5000", pedido) == carpeta / "BLOQUE1_1-5000.manifest.json"
    assert de_la_cache(carpeta, "OTRO_1-50", pedido) is None
    # Un paquete roto (PDF cambiado) no sirve de caché.
    (carpeta / "BLOQUE1_1-5000.pdf").write_bytes(b"%PDF-roto")
    assert de_la_cache(carpeta, "BLOQUE1_1-5000", pedido) is None


def test_paquete_rechazado_por_importar(tmp_path):
    crear_paquete_real(tmp_path, "malo", cambiar={"scale.physical_scale_guaranteed": False})
    with pytest.raises(PaqueteNoValido, match="escala física"):
        verificar(tmp_path / "malo.manifest.json",
                  Pedido("ab" * 32, "1A", 50.0, 5.0, (260.0, 120.0)))


def test_mover_a_para_borrar_sin_pisar_ni_borrar(exportado, tmp_path):
    _, _, carpeta = exportado
    archivos = archivos_del_paquete(carpeta, "BLOQUE1_1-5000")
    assert [a.name for a in archivos] == ["BLOQUE1_1-5000.manifest.json", "BLOQUE1_1-5000.pdf",
                                          "BLOQUE1_1-5000.txt"]
    contenido = archivos[1].read_bytes()
    nuevas = mover_a_para_borrar(archivos, tmp_path / "paquetes", tmp_path / "_para_borrar",
                                 momento="20261117-1200")
    assert [n.relative_to(tmp_path).as_posix() for n in nuevas] == [
        "_para_borrar/paquetes_20261117-1200/GUAMO/BLOQUE1_1-5000.manifest.json",
        "_para_borrar/paquetes_20261117-1200/GUAMO/BLOQUE1_1-5000.pdf",
        "_para_borrar/paquetes_20261117-1200/GUAMO/BLOQUE1_1-5000.txt"]
    assert nuevas[1].read_bytes() == contenido and archivos_del_paquete(carpeta, "BLOQUE1_1-5000") == []
    # Otra vez en el mismo momento: no pisa, agrega _2.
    (carpeta / "BLOQUE1_1-5000.pdf").write_bytes(b"otro")
    (otra,) = mover_a_para_borrar([carpeta / "BLOQUE1_1-5000.pdf"], tmp_path / "paquetes",
                                  tmp_path / "_para_borrar", momento="20261117-1200")
    assert otra.name == "BLOQUE1_1-5000_2.pdf" and otra.read_bytes() == b"otro"


def test_posicion_por_el_centro_cad(exportado):
    manifiesto, _, _ = exportado
    centro_cad = (899699.777 + 957.18 / 2, 937885.353 + 1350.019 / 2)
    x, y = posicion_por_centro(manifiesto, centro_cad, (342.55, 297.0))
    assert (x, y) == pytest.approx((342.55 - (957.18 / 5 + 10) / 2, 297.0 - (1350.019 / 5 + 10) / 2))
    # Otro punto CAD (100 m a la derecha del centro, a 1:5000 = 20 mm): la página se corre 20 mm.
    x2, _ = posicion_por_centro(manifiesto, (centro_cad[0] + 100, centro_cad[1]), (342.55, 297.0))
    assert x2 == pytest.approx(x - 20)


def test_localizar_ignora_los_temporales_del_exportador(tmp_path):
    crear_paquete_real(tmp_path / "GUAMO", "bueno")
    crear_paquete_real(tmp_path / "GUAMO" / ".cde-tmp-4242", "a_medias")
    crear_paquete_real(tmp_path / "GUAMO", ".cde-tmp-suelto")
    assert [p.prefijo for p in localizar_paquetes(tmp_path / "GUAMO")] == ["bueno"]
    assert [p.prefijo for p in localizar_paquetes(tmp_path, recursivo=True)] == ["bueno"]


# --- el export del trabajador falso: lo que comprueba antes de exportar ----------------------

def test_export_comprueba_antes_de_empezar(tmp_path):
    from componedor.trabajador import ErrorTrabajador

    ruta = dxf_falso(tmp_path / "GUAMO.dxf", blocks=[BLOQUE], dejar_temporal=True)
    salida = tmp_path / "paquetes"
    salida.mkdir()
    t = Trabajador(comando_falso(), tmp_path / "trabajo")
    t.iniciar()
    try:
        s = t.pedir("load", {"dxf": str(ruta), "units": None, "margin_mm": 5.0})["session"]

        def exportar(paquete="BLOQUE1_1-5000", **opciones):
            return t.pedir("export", {"session": s, "output_dir": str(salida), "options": opciones,
                                      "jobs": [{"job": "j1", "ref": "BLOQUE1#1",
                                                "scale": "1:5000", "package": paquete}]})

        for paquete, opciones, codigo in (("Ñandú", {}, "OUTPUT_INVALID"),
                                          ("x" * 61, {}, "OUTPUT_INVALID"),
                                          ("BLOQUE1_1-5000", {"margin_mm": 10}, "BAD_REQUEST")):
            with pytest.raises(ErrorTrabajador) as e:
                exportar(paquete, **opciones)
            assert e.value.codigo == codigo
        exportar()
        with pytest.raises(ErrorTrabajador) as e:
            exportar()  # ya existe y overwrite es false
        assert e.value.codigo == "OUTPUT_EXISTS"
    finally:
        t.cerrar()
    # Quedó una carpeta .cde-tmp-* (publicación como la del exportador): se ignora.
    assert any(p.name.startswith(".cde-tmp-") for p in salida.iterdir())
    assert [p.prefijo for p in localizar_paquetes(tmp_path, recursivo=True)] == ["BLOQUE1_1-5000"]


def test_limpiar_la_preparacion(tmp_path):
    from componedor.exportar_dxf import carpeta_de_preparacion, limpiar_preparacion

    carpeta = tmp_path / "paquetes" / "GUAMO"
    prep = carpeta_de_preparacion(carpeta, "7")
    assert prep.name == ".componedor-nuevo-7"
    crear_paquete_real(prep, "a_medias")  # publicado pero no usado
    (prep / ".cde-tmp-99").mkdir()  # del trabajador: vacía, se quita
    assert [p.prefijo for p in localizar_paquetes(tmp_path, recursivo=True)] == []  # se ignora
    movidos = limpiar_preparacion(prep, tmp_path / "paquetes", tmp_path / "_para_borrar")
    assert sorted(m.name for m in movidos) == ["a_medias.manifest.json", "a_medias.pdf"]
    assert not prep.exists()
    assert limpiar_preparacion(prep, tmp_path, tmp_path / "_para_borrar") == []  # ya no está
