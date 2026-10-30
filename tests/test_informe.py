from componedor.informe import escribir_informe, resultado_final, texto_informe
from componedor.validacion import Comprobacion

PASA = Comprobacion("Hoja", "Tamaño de la hoja", True, "841 x 594", "841 x 594", "±0.1 mm")
FALLA = Comprobacion("Escala", "Escala medida", False, "1:50", "1:49.5", "< 0.0005")


def test_resultado_final():
    assert resultado_final([PASA]) == "RESULTADO: PASA"
    assert resultado_final([PASA, FALLA]) == "RESULTADO: FALLA (1 comprobación)"
    assert resultado_final([FALLA, FALLA]) == "RESULTADO: FALLA (2 comprobaciones)"


def test_texto_por_secciones_y_utf8(tmp_path):
    texto = texto_informe([FALLA, PASA], ["Formato: prueba"],
                          {"Plantilla": ["no se usa plantilla"]})
    # Las secciones salen en orden fijo, no en el orden de la lista.
    assert texto.index("== HOJA ==") < texto.index("== PLANTILLA ==") < texto.index("== ESCALA ==")
    assert "  [FALLA] Escala medida\n      esperado:   1:50\n      medido:     1:49.5" in texto
    assert "  (no se usa plantilla)" in texto
    assert "== VECTOR ==" not in texto  # sección sin filas ni notas: no aparece
    ruta = tmp_path / "informe.txt"
    escribir_informe(ruta, texto)
    assert ruta.read_bytes().decode("utf-8") == texto
    assert "Tamaño" in ruta.read_text(encoding="utf-8")
