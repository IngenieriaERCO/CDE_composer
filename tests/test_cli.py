import re
from pathlib import Path

import pymupdf

from conftest import escribir_formato

from componedor.cli import hoja_vacia, main


def test_crea_hoja_y_muestra_tamano(tmp_path, capsys):
    salida = tmp_path / "a1_horizontal.pdf"
    assert main(["hoja-vacia", "--orientacion", "horizontal", "--salida", str(salida)]) == 0
    assert salida.exists()
    with pymupdf.open(salida) as doc:
        assert doc.page_count == 1
        assert doc[0].rotation == 0
    assert "841.0 x 594.0 mm" in capsys.readouterr().out


def test_no_sobrescribe_sin_permiso(tmp_path, capsys):
    salida = tmp_path / "existente.pdf"
    salida.write_bytes(b"no tocar")
    assert main(["hoja-vacia", "--salida", str(salida)]) == 1
    assert salida.read_bytes() == b"no tocar"
    assert "--sobrescribir" in capsys.readouterr().err


def test_sobrescribe_con_permiso(tmp_path):
    salida = tmp_path / "existente.pdf"
    salida.write_bytes(b"viejo")
    ancho, alto = hoja_vacia("vertical", salida, sobrescribir=True)
    assert (round(ancho, 1), round(alto, 1)) == (594.0, 841.0)
    with pymupdf.open(salida) as doc:
        assert doc.page_count == 1


def test_hoja_formato_imprime_tabla(tmp_path, capsys):
    salida = tmp_path / "a1_erco.pdf"
    formato = escribir_formato(tmp_path / "formato.json")
    args = ["hoja-formato", "--formato", str(formato), "--salida", str(salida), "--guias"]
    assert main(args) == 0
    out = capsys.readouterr().out
    assert "815.6 x 568.6" in out  # marco
    assert "639.7 x 548.6" in out  # area_dibujo
    assert "155.9 x 146.8" in out  # localizacion
    # Segunda vez sin --sobrescribir: se niega.
    assert main(args) == 1
    assert "--sobrescribir" in capsys.readouterr().err


def test_hoja_formato_invalido(tmp_path, capsys):
    formato = tmp_path / "malo.json"
    formato.write_text("{ no es json", encoding="utf-8")
    salida = tmp_path / "x.pdf"
    assert main(["hoja-formato", "--formato", str(formato), "--salida", str(salida)]) == 1
    assert "no es un JSON válido" in capsys.readouterr().err
    assert not salida.exists()


def test_colocar_con_posicion(tmp_path, capsys, detalle):
    salida = tmp_path / "hoja_detalle.pdf"
    formato = escribir_formato(tmp_path / "formato.json")
    args = ["colocar", "--formato", str(formato), "--detalle", str(detalle),
            "--salida", str(salida), "--posicion", "100", "200"]
    assert main(args) == 0
    out = capsys.readouterr().out
    assert "Tamaño del detalle: 120.0 x 80.0 mm" in out
    assert "X 100.00 a 220.00, Y 200.00 a 280.00" in out
    assert salida.exists()


def test_colocar_centrado(tmp_path, capsys, detalle):
    salida = tmp_path / "hoja_centrada.pdf"
    formato = escribir_formato(tmp_path / "formato.json")
    args = ["colocar", "--formato", str(formato), "--detalle", str(detalle),
            "--salida", str(salida), "--centrar", "--guias"]
    assert main(args) == 0
    # Centro del área de dibujo: (342.55, 297.0) -> X 282.55 a 402.55, Y 257.0 a 337.0
    out = capsys.readouterr().out
    x0, x1, y0, y1 = map(float, re.search(r"X (\S+) a (\S+), Y (\S+) a (\S+)", out).groups())
    assert abs((x0 + x1) / 2 - 342.55) <= 0.1
    assert abs((y0 + y1) / 2 - 297.0) <= 0.1


def test_colocar_detalle_grande_no_crea_archivo(tmp_path, capsys):
    from conftest import crear_detalle_sintetico

    grande = crear_detalle_sintetico(tmp_path / "grande.pdf", ancho_mm=700, alto_mm=80)
    salida = tmp_path / "no_debe_existir.pdf"
    formato = escribir_formato(tmp_path / "formato.json")
    args = ["colocar", "--formato", str(formato), "--detalle", str(grande),
            "--salida", str(salida), "--centrar"]
    assert main(args) == 1
    assert "se pasa 60.3 mm a lo ancho" in capsys.readouterr().err
    assert not salida.exists()


def test_orientacion_invalida_en_cli(tmp_path, capsys):
    salida = tmp_path / "x.pdf"
    assert main(["hoja-vacia", "--orientacion", "diagonal", "--salida", str(salida)]) == 1
    assert not salida.exists()
    assert "Orientación no válida: 'diagonal'" in capsys.readouterr().err
