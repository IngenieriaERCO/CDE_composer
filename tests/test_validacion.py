"""Comando `referencia` completo. No depende de archivos de ERCO ni de data/."""

import pytest

from componedor import comando_referencia
from componedor import referencia as ref
from componedor.cli import main
from conftest import (
    crear_plantilla_sintetica,
    escribir_formato,
    crear_paquete_real,
)

SECCIONES = ("== HOJA ==", "== MARCO ==", "== PLANTILLA ==", "== DETALLE DE REFERENCIA ==",
             "== ESCALA ==", "== VECTOR ==")


@pytest.fixture
def formato_con_plantilla(tmp_path):
    plantilla = crear_plantilla_sintetica(tmp_path / "rotulo.pdf")
    return escribir_formato(tmp_path / "formato.json", plantilla=plantilla)


def _correr(formato, salida, *extra):
    return main(["referencia", "--formato", str(formato), "--salida", str(salida), *extra])


def test_con_plantilla_sintetica_todo_pasa(tmp_path, capsys, formato_con_plantilla):
    salida = tmp_path / "referencia_A1.pdf"
    assert _correr(formato_con_plantilla, salida) == 0
    out = capsys.readouterr().out
    assert "RESULTADO: PASA" in out and "FALLA" not in out
    txt = (tmp_path / "referencia_A1.txt").read_text(encoding="utf-8")
    assert txt.rstrip().endswith("RESULTADO: PASA")
    for seccion in SECCIONES:
        assert seccion in txt
    assert "Marco del rótulo vs formato" in txt and "±0.5 mm" in txt
    assert "esperado:   1 (solo las de la plantilla)" in txt  # el logo sintético


def test_sin_plantilla_todo_pasa(tmp_path, capsys, formato_con_plantilla):
    salida = tmp_path / "ref.pdf"
    assert _correr(formato_con_plantilla, salida, "--sin-plantilla") == 0
    txt = (tmp_path / "ref.txt").read_text(encoding="utf-8")
    assert "no se usa plantilla" in txt
    assert "Marco dibujado vs formato" in txt
    assert "esperado:   0 (solo las de la plantilla)" in txt
    assert "RESULTADO: PASA" in txt


def test_plantilla_inexistente_avisa_y_sigue(tmp_path, capsys):
    formato = escribir_formato(tmp_path / "f.json", plantilla=tmp_path / "no_existe.pdf")
    assert _correr(formato, tmp_path / "ref.pdf") == 0
    out = capsys.readouterr().out
    assert "AVISO: No se encontró la plantilla" in out and "Se sigue sin plantilla" in out
    assert "RESULTADO: PASA" in out


def test_desplazar_1_mm_falla(tmp_path, capsys, monkeypatch, formato_con_plantilla):
    original = comando_referencia.origen_para_ancla

    def desplazado(*args):
        x, y = original(*args)
        return x + 1.0, y  # el detalle queda 1 mm a la derecha de donde debía

    monkeypatch.setattr(comando_referencia, "origen_para_ancla", desplazado)
    assert _correr(formato_con_plantilla, tmp_path / "ref.pdf") == 1
    txt = (tmp_path / "ref.txt").read_text(encoding="utf-8")
    assert "[FALLA] Cuadrado 5 x 5 m: esquina inferior izquierda" in txt
    assert "medido:     (101.000, 100.000) mm" in txt
    assert "[FALLA] Orientación (marca asimétrica)" in txt
    assert "[PASA] Cuadrado 5 x 5 m: tamaño" in txt  # el tamaño sigue bien
    assert "RESULTADO: FALLA (3 comprobaciones)" in txt


def test_escalar_1_por_ciento_falla(tmp_path, monkeypatch, formato_con_plantilla):
    original = ref.generar_detalle_referencia
    monkeypatch.setattr(comando_referencia, "generar_detalle_referencia",
                        lambda: original(factor_error=1.01))
    assert _correr(formato_con_plantilla, tmp_path / "ref.pdf") == 1
    txt = (tmp_path / "ref.txt").read_text(encoding="utf-8")
    assert "[FALLA] Cuadrado 5 x 5 m: tamaño" in txt
    assert "medido:     101.000 x 101.000 mm" in txt
    assert "[FALLA] Escala medida" in txt and "1:49.50" in txt
    assert "RESULTADO: FALLA (" in txt


def test_reproducible(tmp_path, formato_con_plantilla):
    a = comando_referencia.ejecutar_referencia(formato_con_plantilla, tmp_path / "a.pdf")
    b = comando_referencia.ejecutar_referencia(formato_con_plantilla, tmp_path / "b.pdf")
    medidos = lambda r: [(c.seccion, c.nombre, c.pasa, c.esperado, c.medido)  # noqa: E731
                         for c in r.comprobaciones]
    assert medidos(a) == medidos(b)


def test_detalle_real_con_manifiesto(tmp_path, capsys, formato_con_plantilla):
    detalle = crear_paquete_real(tmp_path / "paquete")
    manifiesto = detalle.with_name("detalle.manifest.json")
    assert _correr(formato_con_plantilla, tmp_path / "ref.pdf", "--detalle", str(detalle),
                   "--manifiesto", str(manifiesto)) == 0
    txt = (tmp_path / "ref.txt").read_text(encoding="utf-8")
    assert "== DETALLE REAL ==" in txt
    assert "[PASA] Límites del dibujo vs page_bounds_mm (en papel)" in txt
    assert "[PASA] Tamaño de página vs page_size_mm" in txt


def test_detalle_real_que_no_coincide_falla(tmp_path, formato_con_plantilla):
    detalle = crear_paquete_real(tmp_path / "paquete",
                                 cambiar={"pdf.drawing.page_bounds_mm.x0": 37.3 - 0.5})
    manifiesto = detalle.with_name("detalle.manifest.json")
    assert _correr(formato_con_plantilla, tmp_path / "ref.pdf", "--detalle", str(detalle),
                   "--manifiesto", str(manifiesto)) == 1
    txt = (tmp_path / "ref.txt").read_text(encoding="utf-8")
    assert "[FALLA] Límites del dibujo vs page_bounds_mm (en papel)" in txt
    assert "RESULTADO: FALLA (1 comprobación)" in txt


def test_detalle_sin_manifiesto_y_sobrescribir(tmp_path, capsys, formato_con_plantilla):
    assert _correr(formato_con_plantilla, tmp_path / "ref.pdf", "--detalle", "x.pdf") == 2
    assert "--detalle y --manifiesto van juntos" in capsys.readouterr().err
    assert _correr(formato_con_plantilla, tmp_path / "ref.pdf") == 0
    assert _correr(formato_con_plantilla, tmp_path / "ref.pdf") == 1
    assert "Use --sobrescribir" in capsys.readouterr().err
    assert _correr(formato_con_plantilla, tmp_path / "ref.pdf", "--sobrescribir") == 0
