"""Inventario de detalles (paquetes sintéticos, no de ERCO)."""

import pytest

from componedor.cli import main
from componedor.formato import cargar_formato
from componedor.importador import PaqueteRechazado, importar_paquete
from componedor.inventario import ACEPTADO, RECHAZADO, construir_inventario
from conftest import RUTA_A1, crear_paquete_real


@pytest.fixture
def formato():
    return cargar_formato(RUTA_A1, usar_plantilla=False)  # área de dibujo 639,7 x 548,6 mm


def _grande(carpeta, prefijo="grande", **kw):
    """Paquete coherente con página de 700 x 120 mm: no cabe en el área de dibujo A1."""
    cambiar = {"pdf.page_size_mm": [700.0, 120.0], "pdf.expected_page_size_mm": [700.0, 120.0],
               **kw.pop("cambiar", {})}
    return crear_paquete_real(carpeta, prefijo, pagina_mm=(700.0, 120.0), cambiar=cambiar, **kw)


def _por_prefijo(entradas):
    return {e.prefijo: e for e in entradas}


def test_aceptado_y_rechazado_con_los_motivos_del_importador(tmp_path):
    crear_paquete_real(tmp_path, "bueno")
    crear_paquete_real(tmp_path, "sin_escala", cambiar={"scale.physical_scale_guaranteed": False})
    e = _por_prefijo(construir_inventario(tmp_path))
    assert e["bueno"].estado == ACEPTADO and e["bueno"].motivos == []
    assert e["bueno"].escala == 50.0 and e["bueno"].bloque == "DETALLE_PRUEBA"
    assert e["bueno"].tamano_pagina_mm == (260.0, 120.0)
    assert e["bueno"].tamano_dibujo_mm == pytest.approx((200.0, 80.0))
    assert e["bueno"].cabe is None  # sin formato
    assert e["sin_escala"].estado == RECHAZADO
    with pytest.raises(PaqueteRechazado) as error:
        importar_paquete(tmp_path / "sin_escala.manifest.json")
    assert e["sin_escala"].motivos == [f"[{c}] {t}" for c, t in error.value.motivos]
    assert e["sin_escala"].motivos[0].startswith("[escala] escala física no garantizada")


def test_rechazado_por_manifiesto_invalido(tmp_path):
    crear_paquete_real(tmp_path, cambiar={"schema_version": "9.0"})
    (e,) = construir_inventario(tmp_path)
    assert e.estado == RECHAZADO and e.bloque is None and e.escala is None
    assert e.motivos[0].startswith("[manifiesto] schema_version: versión 9.0 no soportada")


def test_cabe(tmp_path, formato):
    crear_paquete_real(tmp_path)
    (e,) = construir_inventario(tmp_path, formato)
    assert e.cabe is True and e.notas == []


def test_no_cabe_con_margen_sugiere_escala(tmp_path, formato):
    _grande(tmp_path)
    (e,) = construir_inventario(tmp_path, formato)
    assert e.estado == ACEPTADO  # no caber NO es motivo de rechazo
    assert e.cabe is False
    # Contenido 690 x 110 (página - 2 x 5 mm); a 1:100 la página sería 355 x 65 mm.
    assert e.notas == ["no cabe en area_dibujo: se pasa 60.3 mm de ancho y 0.0 mm de alto",
                       "escala sugerida (aproximada): 1:75, página ≈ 470.0 x 83.3 mm"]


def test_no_cabe_sin_margen_no_sugiere(tmp_path, formato):
    _grande(tmp_path, quitar=["pdf.margin_mm"])
    (e,) = construir_inventario(tmp_path, formato)
    assert e.estado == ACEPTADO and e.cabe is False
    assert e.notas[1] == "sin escala sugerida: el manifiesto no indica pdf.margin_mm"


def test_no_cabe_ni_con_la_mayor_escala(tmp_path, formato):
    _grande(tmp_path, cambiar={"scale.denominator": 10000.0})  # ya está en la mayor de la lista
    (e,) = construir_inventario(tmp_path, formato)
    assert e.cabe is False
    assert e.notas[1] == "sin escala sugerida: ni a 1:10000 cabe (la mayor de la lista estándar)"


def test_zona_inexistente(tmp_path, formato):
    with pytest.raises(ValueError, match="La zona 'patio' no existe"):
        construir_inventario(tmp_path, formato, zona="patio")


def test_duplicado_por_sha256(tmp_path):
    original = crear_paquete_real(tmp_path, "a_original")
    crear_paquete_real(tmp_path / "copias", "b_copia", contenido=original.read_bytes())
    e = construir_inventario(tmp_path, recursivo=True)
    assert [x.prefijo for x in e] == ["a_original", "b_copia"]
    assert e[0].notas == []
    assert e[1].notas == ["duplicado de a_original.pdf"]
    assert e[1].estado == ACEPTADO  # duplicar no es motivo de rechazo


def test_recursivo(tmp_path):
    crear_paquete_real(tmp_path, "raiz")
    crear_paquete_real(tmp_path / "sub", "hijo")
    assert [e.prefijo for e in construir_inventario(tmp_path)] == ["raiz"]
    assert [e.prefijo for e in construir_inventario(tmp_path, recursivo=True)] == ["raiz", "hijo"]


# --- CLI inventario ----------------------------------------------------------------------

def test_cli_sin_formato_no_hay_columna_cabe(tmp_path, capsys):
    crear_paquete_real(tmp_path, "bueno")
    assert main(["inventario", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    lineas = out.splitlines()
    titulos = next(l for l in lineas if l.startswith("Prefijo"))
    assert "Cabe" not in out
    assert [t.strip() for t in titulos.split("  ") if t.strip()] == \
        ["Prefijo", "Bloque", "Escala", "Dibujo (mm)", "Página (mm)", "Estado"]
    fila = next(l for l in lineas if l.startswith("bueno"))
    assert [c.strip() for c in fila.split("  ") if c.strip()] == \
        ["bueno", "DETALLE_PRUEBA", "1:50", "200.00 x 80.00", "260.00 x 120.00", "aceptado"]
    assert out.rstrip().endswith("1 detalle(s): 1 aceptado(s), 0 rechazado(s).")


def test_cli_no_caber_no_cambia_el_codigo(tmp_path, capsys):
    crear_paquete_real(tmp_path, "bueno")
    _grande(tmp_path)
    assert main(["inventario", str(tmp_path), "--formato", str(RUTA_A1)]) == 0
    out = capsys.readouterr().out
    assert "Cabe" in out
    filas = {l.split()[0]: l.split()[-2:] for l in out.splitlines()
             if l.startswith(("bueno", "grande"))}
    assert filas == {"bueno": ["aceptado", "sí"], "grande": ["aceptado", "no"]}
    assert "Notas:\n  grande:\n    - no cabe en area_dibujo: se pasa 60.3 mm" in out
    assert "escala sugerida (aproximada): 1:75" in out
    assert out.rstrip().endswith("2 detalle(s): 2 aceptado(s), 0 rechazado(s), "
                                 "1 no caben en area_dibujo.")


def test_cli_rechazados_codigo_1(tmp_path, capsys):
    crear_paquete_real(tmp_path, "bueno")
    crear_paquete_real(tmp_path, "corrido", desplazar_dibujo_mm=(0.0, 3.0))
    crear_paquete_real(tmp_path, "sin_pdf").unlink()
    assert main(["inventario", str(tmp_path), "--formato", str(RUTA_A1)]) == 1
    out = capsys.readouterr().out
    assert "Motivos de rechazo:" in out
    assert "  corrido:\n    - [coherencia] los trazos del PDF no están" in out
    assert "  sin_pdf:\n    - [archivos] falta el PDF 'sin_pdf.pdf'" in out
    assert "sin_pdf  -  " not in out  # el incompleto sí tiene manifiesto: muestra su bloque
    assert out.rstrip().endswith("3 detalle(s): 1 aceptado(s), 2 rechazado(s), "
                                 "0 no caben en area_dibujo.")


def test_cli_carpeta_vacia_y_zona_otra(tmp_path, capsys):
    assert main(["inventario", str(tmp_path)]) == 0
    assert "No se encontraron paquetes" in capsys.readouterr().out
    crear_paquete_real(tmp_path)
    assert main(["inventario", str(tmp_path), "--formato", str(RUTA_A1), "--zona", "cajetin"]) == 0
    out = capsys.readouterr().out
    assert "no cabe en cajetin" in out and "1 no caben en cajetin." in out
