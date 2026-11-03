"""Lectura y validación de la estructura del manifiesto (datos sintéticos, no de ERCO)."""

import pytest

from componedor.cli import main
from componedor.manifiesto import (
    CAMPOS_OBLIGATORIOS,
    MOTIVOS_NULL,
    ManifiestoInvalido,
    leer_manifiesto,
)
from conftest import (
    LIMITES_RECT_PAGINA_MM,
    MATRIZ_SINTETICA,
    PAGINA_CAD_MM,
    RECT_CAD,
    SHA256_FICTICIO,
    escribir_json,
    manifiesto_paquete,
)


def _leer(tmp_path, datos):
    return leer_manifiesto(escribir_json(tmp_path / "d.manifest.json", datos))


def _error(tmp_path, datos) -> str:
    with pytest.raises(ManifiestoInvalido) as e:
        _leer(tmp_path, datos)
    return str(e.value)


def test_manifiesto_completo_se_lee(tmp_path):
    m = _leer(tmp_path, manifiesto_paquete())
    assert (m.tipo_documento, m.version_esquema, m.version_modelo) == \
        ("cde-detail-manifest", "1.0", "2")
    assert m.unidades.milimetros_por_unidad == 1000.0
    assert (m.escala.denominador, m.escala.factor_mm_por_unidad_cad) == (50.0, 20.0)
    assert m.escala.fisica_garantizada is True
    assert m.pdf.nombre_archivo == "detalle_prueba.pdf"
    assert (m.pdf.bytes, m.pdf.sha256, m.pdf.paginas) == (12345, SHA256_FICTICIO, 1)
    assert m.pdf.tamano_pagina_mm == PAGINA_CAD_MM == m.pdf.tamano_esperado_mm
    assert m.pdf.margen_mm == 5.0
    assert m.pdf.dibujo.limites_cad == RECT_CAD
    assert m.pdf.dibujo.limites_pagina_mm == LIMITES_RECT_PAGINA_MM
    assert (m.pdf.dibujo.matriz.a, m.pdf.dibujo.matriz.e) == (20.0, MATRIZ_SINTETICA[4])
    assert m.estado_validacion == "complete_with_warnings"
    assert m.bloque == "DETALLE_PRUEBA"


def test_es_de_solo_lectura(tmp_path):
    m = _leer(tmp_path, manifiesto_paquete())
    with pytest.raises(AttributeError):
        m.escala.denominador = 100.0


def test_manifiesto_minimo_se_lee(tmp_path):
    m = _leer(tmp_path, manifiesto_paquete(minimo=True))
    assert m.escala.denominador == 50.0
    assert m.bloque is None  # source es opcional


def test_campos_desconocidos_se_ignoran(tmp_path):
    datos = manifiesto_paquete(cambiar={
        "campo_del_futuro": {"x": 1},
        "pdf.drawing.otra_cosa": [1, 2, 3],
        "scale.nueva_clave": "hola",
    })
    assert _leer(tmp_path, datos).escala.denominador == 50.0


def test_informativos_rotos_no_importan(tmp_path):
    datos = manifiesto_paquete(cambiar={"entities": "no es un objeto", "fonts": None})
    assert _leer(tmp_path, datos).pdf.paginas == 1


@pytest.mark.parametrize("ruta", CAMPOS_OBLIGATORIOS)
def test_falta_cada_campo_obligatorio(tmp_path, ruta):
    assert f"- {ruta}: falta el campo" in _error(tmp_path, manifiesto_paquete(quitar=[ruta]))


def test_falta_un_objeto_entero_se_reporta_una_vez(tmp_path):
    mensaje = _error(tmp_path, manifiesto_paquete(quitar=["scale"]))
    assert "- scale: falta el campo" in mensaje
    assert "scale.denominator" not in mensaje
    assert "(1 problema)" in mensaje


@pytest.mark.parametrize("ruta", sorted(MOTIVOS_NULL))
def test_null_se_distingue_de_falta(tmp_path, ruta):
    mensaje = _error(tmp_path, manifiesto_paquete(cambiar={ruta: None}))
    assert f"- {ruta}: es null ({MOTIVOS_NULL[ruta]})" in mensaje
    assert "falta el campo" not in mensaje


def test_varios_problemas_en_un_solo_mensaje(tmp_path):
    datos = manifiesto_paquete(
        quitar=["pdf.page_size_mm"],
        cambiar={"scale.denominator": None, "pdf.page_count": "uno",
                 "pdf.drawing.cad_to_page.units": "m", "validation.status": "failed"},
    )
    mensaje = _error(tmp_path, datos)
    lineas = [linea for linea in mensaje.splitlines() if linea.startswith("- ")]
    assert "(5 problemas)" in mensaje and len(lineas) == 5
    assert "- pdf.page_size_mm: falta el campo" in lineas
    assert "- scale.denominator: es null (el detalle se exportó sin escala nominal 1:N)" in lineas
    assert "- pdf.page_count: se esperaba un número entero; tiene texto 'uno'" in lineas
    assert "- pdf.drawing.cad_to_page.units: debe ser 'mm'; tiene 'm'" in lineas
    assert any(linea.startswith("- validation.status: debe ser uno de complete, "
                                "complete_with_warnings") for linea in lineas)


@pytest.mark.parametrize("cambio, esperado", [
    ({"scale.denominator": "50"}, "scale.denominator: se esperaba un número; tiene texto '50'"),
    ({"scale.denominator": True}, "scale.denominator: se esperaba un número; tiene un booleano"),
    ({"pdf.drawing.cad_to_page.matrix": [20, 0, 0, -20, 1e8]},
     "pdf.drawing.cad_to_page.matrix: se esperaba una lista de 6 números; tiene 5 elementos"),
    ({"pdf.drawing.cad_to_page.matrix": [20, 0, 0, -20, 1e8, float("nan")]},
     "pdf.drawing.cad_to_page.matrix: elemento 5: se esperaba un número finito; tiene nan"),
    ({"units.millimeters_per_unit": float("inf")},
     "units.millimeters_per_unit: se esperaba un número finito; tiene inf"),
    ({"scale.factor_mm_per_cad_unit": -20.0},
     "scale.factor_mm_per_cad_unit: debe ser mayor que 0; tiene -20.0"),
    ({"pdf.page_size_mm": [260.0, -1.0]},
     "pdf.page_size_mm: elemento 1: debe ser mayor que 0; tiene -1.0"),
    ({"pdf.page_size_mm": [260.0]},
     "pdf.page_size_mm: se esperaba una lista de 2 números; tiene 1 elementos"),
    ({"pdf.page_count": 0}, "pdf.page_count: debe ser al menos 1; tiene 0"),
    ({"pdf.bytes": 12.5}, "pdf.bytes: se esperaba un número entero"),
    ({"scale.physical_scale_guaranteed": "sí"},
     "scale.physical_scale_guaranteed: se esperaba true o false; tiene texto 'sí'"),
    ({"pdf.sha256": "ABC"}, "pdf.sha256: debe ser un SHA-256 en hexadecimal"),
    ({"pdf.sha256": "AB" * 32}, "pdf.sha256: debe ser un SHA-256 en hexadecimal"),
    ({"pdf.file_name": "carpeta/detalle.pdf"}, "pdf.file_name: debe ser un nombre de archivo"),
    ({"pdf.file_name": "C:\\detalle.pdf"}, "pdf.file_name: debe ser un nombre de archivo"),
    ({"pdf.drawing.page_bounds_mm.x1": 1.0}, "pdf.drawing.page_bounds_mm: debe cumplir x1 > x0"),
    ({"pdf.drawing.cad_to_page.origin": "bottom-left"},
     "pdf.drawing.cad_to_page.origin: debe ser 'top-left'"),
    ({"pdf.drawing.cad_to_page.y_axis": "up"}, "pdf.drawing.cad_to_page.y_axis: debe ser 'down'"),
    ({"document_type": "otro"}, "document_type: debe ser 'cde-detail-manifest'"),
    ({"pdf.drawing": [1, 2]}, "pdf.drawing: se esperaba un objeto"),
    ({"pdf": "texto"}, "pdf: se esperaba un objeto"),
])
def test_tipos_y_valores_incorrectos(tmp_path, cambio, esperado):
    assert esperado in _error(tmp_path, manifiesto_paquete(cambiar=cambio))


@pytest.mark.parametrize("quitar, cambiar", [
    (["pdf.margin_mm"], None),
    ([], {"pdf.margin_mm": None}),
    ([], {"pdf.margin_mm": -5.0}),
    ([], {"pdf.margin_mm": "cinco"}),
])
def test_margen_es_opcional_informativo(tmp_path, quitar, cambiar):
    m = _leer(tmp_path, manifiesto_paquete(quitar=quitar, cambiar=cambiar))
    assert m.pdf.margen_mm is None


def test_margen_valido_se_conserva(tmp_path):
    assert _leer(tmp_path, manifiesto_paquete()).pdf.margen_mm == 5.0
    assert "pdf.margin_mm" not in CAMPOS_OBLIGATORIOS and "pdf.margin_mm" not in MOTIVOS_NULL


def test_cli_resumen_sin_margen(tmp_path, capsys):
    ruta = escribir_json(tmp_path / "d.manifest.json", manifiesto_paquete(quitar=["pdf.margin_mm"]))
    assert main(["leer-manifiesto", str(ruta)]) == 0
    assert "margen no indicado" in capsys.readouterr().out


def test_escala_fisica_no_garantizada_se_lee(tmp_path):
    datos = manifiesto_paquete(cambiar={"scale.physical_scale_guaranteed": False})
    assert _leer(tmp_path, datos).escala.fisica_garantizada is False  # regla de uso: 2.4/2.5


@pytest.mark.parametrize("version", ["1.0", "1.3", "1", "1.10.2"])
def test_version_mayor_1_aceptada(tmp_path, version):
    assert _leer(tmp_path, manifiesto_paquete(cambiar={"schema_version": version})) \
        .version_esquema == version


@pytest.mark.parametrize("version, esperado", [
    ("2.0", "schema_version: versión 2.0 no soportada; el componedor entiende la versión mayor 1"),
    ("0.9", "versión 0.9 no soportada"),
    ("v1", "schema_version: formato de versión no reconocido: 'v1'"),
    (1.0, "schema_version: se esperaba texto"),
])
def test_version_rechazada(tmp_path, version, esperado):
    assert esperado in _error(tmp_path, manifiesto_paquete(cambiar={"schema_version": version}))


def test_json_mal_formado(tmp_path):
    ruta = tmp_path / "roto.manifest.json"
    ruta.write_text('{"document_type": "cde-detail-manifest",\n  "pdf": }', encoding="utf-8")
    with pytest.raises(ManifiestoInvalido, match=r"no es un JSON válido \(línea 2, columna"):
        leer_manifiesto(ruta)


def test_json_que_no_es_objeto(tmp_path):
    ruta = escribir_json(tmp_path / "lista.json", [1, 2])
    with pytest.raises(ManifiestoInvalido, match="debe ser un objeto JSON"):
        leer_manifiesto(ruta)


def test_archivo_inexistente(tmp_path):
    with pytest.raises(ManifiestoInvalido, match="No se encontró el manifiesto"):
        leer_manifiesto(tmp_path / "no_existe.manifest.json")


# --- CLI leer-manifiesto -----------------------------------------------------------------

def test_cli_resumen(tmp_path, capsys):
    ruta = escribir_json(tmp_path / "d.manifest.json", manifiesto_paquete())
    assert main(["leer-manifiesto", str(ruta)]) == 0
    out = capsys.readouterr().out
    assert "Bloque: DETALLE_PRUEBA" in out
    assert "Escala: 1:50 (20 mm de papel por unidad CAD; 1000 mm reales por unidad CAD)" in out
    assert "escala física garantizada: sí" in out
    assert "Tamaño de página: 260.00 x 120.00 mm" in out
    assert "Estado de validación del exportador: complete_with_warnings" in out
    assert "Estructura del manifiesto: válida" in out


def test_cli_manifiesto_invalido(tmp_path, capsys):
    ruta = escribir_json(tmp_path / "d.manifest.json",
                         manifiesto_paquete(quitar=["pdf.sha256"], cambiar={"pdf.drawing": None}))
    assert main(["leer-manifiesto", str(ruta)]) == 1
    err = capsys.readouterr().err
    assert "(2 problemas)" in err
    assert "- pdf.sha256: falta el campo" in err
    assert "- pdf.drawing: es null (el exportador no dibujó nada en el PDF)" in err
    assert "Traceback" not in err


def test_cli_archivo_inexistente(tmp_path, capsys):
    assert main(["leer-manifiesto", str(tmp_path / "no.json")]) == 1
    assert "No se encontró el manifiesto" in capsys.readouterr().err
