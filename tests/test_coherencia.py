"""Coherencia del paquete (PDF y manifiesto sintéticos, no de ERCO).

Cada caso hace fallar SOLO una comprobación (a-i); el paquete base pasa todas.
"""

import pytest

from componedor.cad_a_papel import MatrizCad
from componedor.cli import main
from componedor.coherencia import verificar_coherencia, verificar_paquete
from componedor.paquete import localizar_paquetes
from conftest import LIMITES_RECT_PAGINA_MM, MATRIZ_SINTETICA, RECT_CAD, crear_paquete_real


def _coherencia(carpeta):
    (paquete,) = localizar_paquetes(carpeta)
    integridad, coherencia = verificar_paquete(paquete)
    assert integridad.pasa, [c.detalle for c in integridad.fallas]
    return coherencia


def _letras_que_fallan(resultado) -> set[str]:
    return {c.nombre[0] for c in resultado.fallas}


def _falla(resultado, letra):
    (c,) = [c for c in resultado.comprobaciones if c.nombre.startswith(f"{letra})")]
    assert not c.pasa
    return c


def test_paquete_coherente_pasa_todo(tmp_path):
    crear_paquete_real(tmp_path)
    r = _coherencia(tmp_path)
    assert r.verificable and r.pasa and r.etiqueta == "OK"
    assert [c.nombre[0] for c in r.comprobaciones] == list("abcdefghi")
    assert all(c.seccion == "Coherencia" for c in r.comprobaciones)
    assert r.datos["diferencia_trazos_mm"] < 0.01


def test_a_rotacion(tmp_path):
    crear_paquete_real(tmp_path, rotacion=90)
    r = _coherencia(tmp_path)
    assert [c.nombre[0] for c in r.comprobaciones] == ["a"]  # se detiene: la matriz no aplica
    assert _falla(r, "a").detalle.startswith("incompatible: el PDF tiene /Rotate 90")


def test_b_pagina_de_otro_tamano(tmp_path):
    crear_paquete_real(tmp_path, pagina_mm=(262.0, 120.0))  # el manifiesto dice 260 x 120
    r = _coherencia(tmp_path)
    assert _letras_que_fallan(r) == {"b"}
    assert _falla(r, "b").medido == "262.000 x 120.000 mm"


def test_c_page_size_distinto_del_esperado(tmp_path):
    crear_paquete_real(tmp_path, cambiar={"pdf.expected_page_size_mm": [261.0, 120.0]})
    assert _letras_que_fallan(_coherencia(tmp_path)) == {"c"}


def test_d_factor_de_escala(tmp_path):
    # 1000 mm por unidad / 40 = 25, pero el factor (y la matriz) dicen 20.
    crear_paquete_real(tmp_path, cambiar={"scale.denominator": 40.0})
    r = _coherencia(tmp_path)
    assert _letras_que_fallan(r) == {"d"}
    assert _falla(r, "d").esperado.startswith("25 (1000 / 40)")


def test_e_matriz_con_d_distinto(tmp_path):
    # d = -21; cad_bounds se recalcula con esa matriz para que f siga cuadrando.
    a, b, c, d, e, f = MATRIZ_SINTETICA
    matriz = MatrizCad(a, b, c, -21.0, e, f)
    x0, y0, x1, y1 = LIMITES_RECT_PAGINA_MM
    cmin, cmax = matriz.pagina_a_cad(x0, y1), matriz.pagina_a_cad(x1, y0)
    crear_paquete_real(tmp_path, cambiar={
        "pdf.drawing.cad_to_page.matrix": [a, b, c, -21.0, e, f],
        "pdf.drawing.cad_bounds": {"min": list(cmin), "max": list(cmax)},
    })
    r = _coherencia(tmp_path)
    assert _letras_que_fallan(r) == {"e"}
    assert _falla(r, "e").detalle.startswith("la escala de la matriz no es la del manifiesto")


def test_e_matriz_con_giro_no_soportada(tmp_path):
    a, b, c, d, e, f = MATRIZ_SINTETICA
    crear_paquete_real(tmp_path, cambiar={"pdf.drawing.cad_to_page.matrix": [a, b, 0.5, d, e, f]})
    detalle = _falla(_coherencia(tmp_path), "e").detalle
    assert detalle.startswith("matriz con giro o inclinación: todavía no soportada")
    assert "no un manifiesto inválido" in detalle


def test_f_cad_bounds_no_cuadra(tmp_path):
    x0, y0, x1, y1 = RECT_CAD
    crear_paquete_real(tmp_path, cambiar={  # 0,05 m CAD = 1 mm de papel
        "pdf.drawing.cad_bounds": {"min": [x0 + 0.05, y0], "max": [x1, y1]}})
    r = _coherencia(tmp_path)
    assert _letras_que_fallan(r) == {"f"}
    assert "diferencia máx. 1.000 mm" in _falla(r, "f").detalle


def test_g_dibujo_fuera_de_la_pagina(tmp_path):
    # Página de 230 mm (y el manifiesto lo dice), pero el dibujo llega hasta x = 237,3 mm.
    crear_paquete_real(tmp_path, pagina_mm=(230.0, 120.0), cambiar={
        "pdf.page_size_mm": [230.0, 120.0], "pdf.expected_page_size_mm": [230.0, 120.0]})
    r = _coherencia(tmp_path)
    assert _letras_que_fallan(r) == {"g"}
    assert _falla(r, "g").detalle == "el dibujo declarado se sale de la página del PDF"


def test_h_trazos_corridos_1_mm(tmp_path):
    crear_paquete_real(tmp_path, desplazar_dibujo_mm=(1.0, 0.0))
    r = _coherencia(tmp_path)
    assert _letras_que_fallan(r) == {"h"}
    assert "diferencia máx. 1.000 mm" in _falla(r, "h").detalle
    assert r.datos["diferencia_trazos_mm"] == pytest.approx(1.0, abs=0.001)


def test_i_escala_fisica_no_garantizada(tmp_path):
    crear_paquete_real(tmp_path, cambiar={
        "scale.physical_scale_guaranteed": False,
        "scale.physical_scale_reason": "Sin escala nominal de prueba"})
    r = _coherencia(tmp_path)
    assert _letras_que_fallan(r) == {"i"}
    assert _falla(r, "i").detalle == (
        "escala física no garantizada: el paquete no se usa para componer a escala "
        "(motivo del exportador: Sin escala nominal de prueba)")


def test_i_sin_motivo(tmp_path):
    crear_paquete_real(tmp_path, cambiar={"scale.physical_scale_guaranteed": False})
    assert "motivo" not in _falla(_coherencia(tmp_path), "i").detalle


def test_no_verificable_si_incompleto_o_sin_integridad(tmp_path):
    crear_paquete_real(tmp_path / "a").unlink()
    (paquete,) = localizar_paquetes(tmp_path / "a")
    r = verificar_coherencia(paquete)
    assert (r.verificable, r.motivo, r.etiqueta) == (False, "no verificable (paquete incompleto)", "—")

    ruta = crear_paquete_real(tmp_path / "b")
    ruta.write_bytes(ruta.read_bytes()[:-1] + b"X")  # mismo tamaño, otro hash
    (paquete,) = localizar_paquetes(tmp_path / "b")
    integridad, coherencia = verificar_paquete(paquete)
    assert not integridad.pasa
    assert coherencia.motivo == "no verificable (la integridad no pasa)"


# --- CLI ---------------------------------------------------------------------------------

def test_cli_paquetes_verificar_columna_coherencia(tmp_path, capsys):
    crear_paquete_real(tmp_path, "bueno")
    crear_paquete_real(tmp_path, "corrido", desplazar_dibujo_mm=(0.0, 2.0))
    assert main(["paquetes", str(tmp_path), "--verificar"]) == 1
    out = capsys.readouterr().out
    assert "Integridad  Coherencia" in out
    filas = {l.split()[0]: l.split()[-2:] for l in out.splitlines()
             if l.startswith(("bueno", "corrido"))}
    assert filas == {"bueno": ["OK", "OK"], "corrido": ["OK", "FALLA"]}
    assert "Problemas de coherencia:\n  corrido:\n    - h) Trazos del PDF vs page_bounds_mm" in out
    assert "Integridad: 2 OK, 0 con falla. Coherencia: 1 OK, 1 con falla." in out


def test_cli_verificar_paquete_pasa(tmp_path, capsys):
    crear_paquete_real(tmp_path)
    assert main(["verificar-paquete", str(tmp_path / "detalle.manifest.json")]) == 0
    out = capsys.readouterr().out
    assert "== INTEGRIDAD ==" in out and "== COHERENCIA ==" in out
    assert out.count("[PASA]") == 5 + 9
    assert "  [PASA] h) Trazos del PDF vs page_bounds_mm\n      esperado:   x0 37.300" in out
    assert "      tolerancia: ±0.5 mm" in out
    assert out.rstrip().endswith("RESULTADO: PASA")


def test_cli_verificar_paquete_falla(tmp_path, capsys):
    crear_paquete_real(tmp_path, cambiar={"scale.physical_scale_guaranteed": False})
    assert main(["verificar-paquete", str(tmp_path / "detalle.manifest.json")]) == 1
    out = capsys.readouterr().out
    assert "  [FALLA] i) Escala física garantizada" in out
    assert "      detalle:    escala física no garantizada" in out
    assert out.rstrip().endswith("RESULTADO: FALLA (1 comprobación)")


def test_cli_verificar_paquete_incompleto_e_inexistente(tmp_path, capsys):
    crear_paquete_real(tmp_path).unlink()
    assert main(["verificar-paquete", str(tmp_path / "detalle.manifest.json")]) == 1
    out = capsys.readouterr().out
    assert "(no verificable (paquete incompleto))" in out
    assert out.rstrip().endswith("RESULTADO: FALLA (paquete incompleto: no verificable)")
    assert main(["verificar-paquete", str(tmp_path / "otro.manifest.json")]) == 1
    assert "No se encontró el manifiesto" in capsys.readouterr().err


def test_e_b_casi_cero_es_ruido_numerico(tmp_path):
    a, b, c, d, e, f = MATRIZ_SINTETICA
    crear_paquete_real(tmp_path, cambiar={"pdf.drawing.cad_to_page.matrix": [a, 1e-16, c, d, e, f]})
    assert _coherencia(tmp_path).pasa


def test_e_b_pequeno_pero_real_es_giro(tmp_path):
    a, b, c, d, e, f = MATRIZ_SINTETICA
    crear_paquete_real(tmp_path, cambiar={"pdf.drawing.cad_to_page.matrix": [a, 0.01, c, d, e, f]})
    r = _coherencia(tmp_path)
    assert "e" in _letras_que_fallan(r)
    assert _falla(r, "e").detalle.startswith("matriz con giro o inclinación")
