"""Importador: única puerta de entrada (paquetes sintéticos, no de ERCO)."""

import pytest

from componedor.importador import PaqueteAceptado, PaqueteRechazado, importar_paquete
from conftest import crear_paquete_real


def _manifiesto(carpeta, prefijo="detalle"):
    return carpeta / f"{prefijo}.manifest.json"


def _rechazo(ruta, **kw) -> PaqueteRechazado:
    with pytest.raises(PaqueteRechazado) as e:
        importar_paquete(ruta, **kw)
    return e.value


def test_paquete_aceptado(tmp_path):
    pdf = crear_paquete_real(tmp_path)
    aceptado = importar_paquete(_manifiesto(tmp_path), pdf_esperado=pdf)
    assert isinstance(aceptado, PaqueteAceptado)
    assert aceptado.integridad.pasa and aceptado.coherencia.pasa
    assert aceptado.manifiesto.escala.denominador == 50.0
    assert aceptado.paquete.ruta_pdf == pdf


def test_manifiesto_invalido(tmp_path):
    crear_paquete_real(tmp_path, cambiar={"schema_version": "2.0"})
    e = _rechazo(_manifiesto(tmp_path))
    assert e.prefijo == "detalle"
    assert e.motivos == [("manifiesto", "schema_version: versión 2.0 no soportada; el "
                                        "componedor entiende la versión mayor 1 (1.x)")]
    assert str(e).startswith("Paquete 'detalle' rechazado (1 motivo):\n  - [manifiesto] ")


def test_archivos_falta_el_pdf(tmp_path):
    crear_paquete_real(tmp_path).unlink()
    e = _rechazo(_manifiesto(tmp_path))
    assert e.motivos == [("archivos", "falta el PDF 'detalle.pdf' (indicado en pdf.file_name): "
                                      "paquete incompleto")]


def test_archivos_manifiesto_inexistente(tmp_path):
    e = _rechazo(tmp_path / "fantasma.manifest.json")
    assert e.prefijo == "fantasma"
    assert e.motivos[0][0] == "archivos" and "No se encontró el manifiesto" in e.motivos[0][1]


def test_archivos_pdf_indicado_no_es_el_del_paquete(tmp_path):
    crear_paquete_real(tmp_path)
    otro = crear_paquete_real(tmp_path / "otra", "otro")
    e = _rechazo(_manifiesto(tmp_path), pdf_esperado=otro)
    assert e.motivos[0][0] == "archivos"
    assert "no es el del paquete: el manifiesto indica 'detalle.pdf'" in e.motivos[0][1]


def test_integridad(tmp_path):
    pdf = crear_paquete_real(tmp_path)
    datos = bytearray(pdf.read_bytes())
    datos[300] ^= 0x01
    pdf.write_bytes(bytes(datos))
    e = _rechazo(_manifiesto(tmp_path))
    assert e.motivos == [("integridad", "el contenido del PDF cambió después de exportarse "
                                        "(mismo tamaño, otro SHA-256)")]


def test_coherencia(tmp_path):
    crear_paquete_real(tmp_path, desplazar_dibujo_mm=(1.0, 0.0))
    e = _rechazo(_manifiesto(tmp_path))
    assert e.motivos == [("coherencia", "los trazos del PDF no están donde dice page_bounds_mm "
                                        "(diferencia máx. 1.000 mm)")]


def test_escala(tmp_path):
    crear_paquete_real(tmp_path, cambiar={"scale.physical_scale_guaranteed": False,
                                          "scale.physical_scale_reason": "motivo de prueba"})
    e = _rechazo(_manifiesto(tmp_path))
    assert e.motivos == [("escala", "escala física no garantizada: el paquete no se usa para "
                                    "componer a escala (motivo del exportador: motivo de prueba)")]


def test_varios_motivos_en_un_solo_mensaje(tmp_path):
    crear_paquete_real(tmp_path, desplazar_dibujo_mm=(0.0, 2.0),
                       cambiar={"scale.physical_scale_guaranteed": False,
                                "pdf.expected_page_size_mm": [270.0, 120.0]})
    e = _rechazo(_manifiesto(tmp_path))
    assert [categoria for categoria, _ in e.motivos] == ["coherencia", "coherencia", "escala"]
    mensaje = str(e)
    assert mensaje.startswith("Paquete 'detalle' rechazado (3 motivos):")
    assert mensaje.count("\n  - [") == 3


def test_manifiesto_invalido_y_pdf_ausente(tmp_path):
    crear_paquete_real(tmp_path, quitar=["scale"]).unlink()
    e = _rechazo(_manifiesto(tmp_path))
    assert e.motivos == [("manifiesto", "scale: falta el campo"),
                         ("archivos", "falta el PDF 'detalle.pdf' (indicado en pdf.file_name): "
                                      "paquete incompleto")]
