"""Errores del trabajador → mensaje claro para el usuario, con el texto técnico en «detalle»."""

from pathlib import Path

from componedor.mensajes_trabajador import AVISAR, para_el_usuario, ruta_para_mostrar

REGISTRO = Path.cwd() / "data" / "cache_exportador" / "trabajador.log"
TECNICO = "Error inesperado del exportador (TypeError): 'NoneType' object is not subscriptable"


def test_error_interno_determinista():
    u = para_el_usuario("cargar_dxf", "INTERNAL", TECNICO,
                        "Repita el pedido; si vuelve a fallar, guarde el registro de stderr.",
                        {"type": "TypeError"}, REGISTRO)
    assert u["mensaje"] == "No se pudo leer el DXF: el exportador encontró un objeto que no entiende."
    assert u["consejo"] == AVISAR and "Repita" not in u["consejo"]
    assert u["detalle"] == TECNICO
    assert u["registro"] == str(Path("data") / "cache_exportador" / "trabajador.log")


def test_error_interno_que_puede_no_repetirse():
    u = para_el_usuario("exportar", "INTERNAL", "Error inesperado del exportador (MemoryError): ",
                        "Repita el pedido…", {"type": "MemoryError"}, REGISTRO)
    assert u["mensaje"] == ("No se pudo exportar el bloque: el exportador encontró un objeto que "
                            "no entiende.")
    assert u["consejo"].startswith("Vuelva a intentarlo")


def test_con_traceback_va_en_el_detalle():
    u = para_el_usuario("previa", "INTERNAL", TECNICO, None,
                        {"type": "KeyError", "traceback": "Traceback (most recent call last): …"},
                        REGISTRO)
    assert u["mensaje"].startswith("No se pudo dibujar la vista previa:")
    assert u["detalle"] == TECNICO + "\n\nTraceback (most recent call last): …"


def test_dxf_invalido_y_errores_por_trabajo():
    u = para_el_usuario("cargar_dxf", "DXF_INVALID",
                        "No se pudo leer el DXF: File 'a.dxf' is not a DXF file",
                        "Si AutoCAD lo estaba guardando, repita «load».", {}, REGISTRO)
    assert u["mensaje"].startswith("No se pudo leer el DXF: el archivo está dañado")
    assert "is not a DXF file" in u["detalle"] and "AUDIT" in u["consejo"]
    for codigo, empieza in (("EXPORT_FAILED", "No se pudo exportar el bloque"),
                            ("VALIDATION_FAILED", "El exportador dibujó el bloque"),
                            ("CRITICAL_NOTICE", "El exportador se detuvo por un aviso crítico")):
        u = para_el_usuario("exportar", codigo, "texto de la terminal", None, None, REGISTRO)
        assert u["mensaje"].startswith(empieza) and u["detalle"] == "texto de la terminal"


def test_los_mensajes_que_ya_son_claros_no_cambian():
    u = para_el_usuario("cargar_dxf", "DXF_NOT_FOUND", "No existe el DXF: C:\a.dxf",
                        "Revise la ruta.", {}, REGISTRO)
    assert u == {"codigo": "DXF_NOT_FOUND", "mensaje": "No existe el DXF: C:\a.dxf",
                 "consejo": "Revise la ruta.", "detalle": None, "registro": None}


def test_ruta_fuera_de_la_carpeta(tmp_path):
    assert ruta_para_mostrar(tmp_path / "x.log") == str(tmp_path / "x.log")
    assert ruta_para_mostrar(None) is None
