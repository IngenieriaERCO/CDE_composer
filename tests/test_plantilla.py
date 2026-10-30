import pymupdf
import pytest

from componedor.cli import main
from componedor.formato import cargar_formato
from componedor.hoja import crear_pagina
from componedor.plantilla import PlantillaInvalida, colocar_plantilla
from componedor.transformaciones import rect_pdf_a_papel
from componedor.unidades import mm_a_pt
from conftest import MARCO_A1, crear_plantilla_sintetica, escribir_formato

TOL_MM = 0.1


def _formato_con(tmp_path, **kwargs_plantilla):
    plantilla = crear_plantilla_sintetica(tmp_path / "rotulo.pdf", **kwargs_plantilla)
    return escribir_formato(tmp_path / "formato.json", plantilla=plantilla)


def _colocar(ruta_formato):
    formato = cargar_formato(ruta_formato)
    doc = crear_pagina(formato.ancho_mm, formato.alto_mm)
    return doc, formato, colocar_plantilla(doc[0], formato)


@pytest.mark.parametrize("rotacion", [0, 90, 270])
def test_plantilla_redondeada_por_autocad(tmp_path, rotacion):
    doc, formato, informe = _colocar(_formato_con(tmp_path, rotacion=rotacion))
    # 2384 x 1684 pt = 841,02 x 594,08 mm: dentro de la tolerancia de ±0,5 mm.
    assert informe.diferencia_tamano_mm == pytest.approx((0.022, 0.078), abs=0.001)
    # Validación cruzada: el marco del rótulo coincide con el del formato.
    assert all(abs(a - b) <= TOL_MM for a, b in zip(informe.marco_leido, MARCO_A1))
    assert informe.diferencia_marco_max_mm <= TOL_MM
    # La plantilla trae su logo: una sola imagen.
    assert len(doc[0].get_image_info()) == 1


def test_plantilla_de_otro_tamano(tmp_path):
    doc_formato = _formato_con(tmp_path, ancho_pt=mm_a_pt(843.0))
    with pytest.raises(PlantillaInvalida,
                       match=r"mide 843\.00 x 594\.08 mm .* diferencia \+2\.00 x \+0\.08 mm"):
        _colocar(doc_formato)


def test_marco_que_no_coincide(tmp_path):
    marco_corrido = (13.7, 12.7, 828.3, 581.3)  # 1 mm a la derecha en xmin
    ruta = _formato_con(tmp_path, marco_mm=marco_corrido)
    with pytest.raises(PlantillaInvalida) as e:
        _colocar(ruta)
    mensaje = str(e.value)
    assert "El marco del rótulo no coincide con el marco del formato" in mensaje
    assert "xmin +1.00, ymin +0.00, xmax +0.00, ymax +0.00 mm" in mensaje


def _args_colocar(tmp_path, ruta_formato, detalle, *extra):
    return ["colocar", "--formato", str(ruta_formato), "--detalle", str(detalle),
            "--salida", str(tmp_path / "salida.pdf"), "--centrar", *extra]


def test_cli_plantilla_debajo_y_detalle_encima(tmp_path, capsys, detalle):
    ruta = _formato_con(tmp_path)
    assert main(_args_colocar(tmp_path, ruta, detalle)) == 0
    out = capsys.readouterr().out
    assert "diferencia con la hoja +0.02 x +0.08 mm" in out
    assert "coincide" in out

    with pymupdf.open(tmp_path / "salida.pdf") as doc:
        page = doc[0]
        # Solo la imagen propia de la plantilla (el logo), ninguna adicional.
        assert len(page.get_image_info()) == 1
        dibujos = page.get_drawings()
        marco = [d for d in dibujos
                 if all(abs(a - b) <= TOL_MM
                        for a, b in zip(rect_pdf_a_papel(d["rect"], 594.0), MARCO_A1))]
        diagonal = [d for d in dibujos if len(d["items"]) == 1 and d["items"][0][0] == "l"
                    and abs(d["rect"].width - mm_a_pt(100)) < 1]
        assert len(marco) == 1 and len(diagonal) == 1
        # La plantilla se dibuja antes (debajo) que el detalle.
        assert marco[0]["seqno"] < diagonal[0]["seqno"]
        # Con plantilla no se dibuja nuestro marco de 0,5 mm encima del oficial.
        assert not [d for d in dibujos if d.get("width") == pytest.approx(mm_a_pt(0.5))]


def test_cli_sin_plantilla(tmp_path, capsys, detalle):
    ruta = _formato_con(tmp_path)
    assert main(_args_colocar(tmp_path, ruta, detalle, "--sin-plantilla")) == 0
    assert "Plantilla: no se usa" in capsys.readouterr().out
    with pymupdf.open(tmp_path / "salida.pdf") as doc:
        assert doc[0].get_image_info() == []
        assert [d for d in doc[0].get_drawings()
                if d.get("width") == pytest.approx(mm_a_pt(0.5))]  # nuestro marco


def test_cli_hoja_formato_con_plantilla(tmp_path, capsys):
    ruta = _formato_con(tmp_path)
    salida = tmp_path / "hoja.pdf"
    assert main(["hoja-formato", "--formato", str(ruta), "--salida", str(salida),
                 "--guias"]) == 0
    assert "Marco del rótulo leído: X 12.70 a 828.30, Y 12.70 a 581.30 mm" \
        in capsys.readouterr().out
    with pymupdf.open(salida) as doc:
        assert len(doc[0].get_image_info()) == 1


def test_cli_marco_que_no_coincide_no_crea_archivo(tmp_path, capsys, detalle):
    ruta = _formato_con(tmp_path, marco_mm=(12.7, 12.7, 828.3, 583.3))
    assert main(_args_colocar(tmp_path, ruta, detalle)) == 1
    assert "ymax +2.00 mm" in capsys.readouterr().err
    assert not (tmp_path / "salida.pdf").exists()


def test_exigir_marco_false_mide_sin_error(tmp_path):
    from componedor.plantilla import buscar_marco

    ruta = _formato_con(tmp_path, marco_mm=(13.7, 12.7, 828.3, 581.3))
    formato = cargar_formato(ruta)
    doc = crear_pagina(formato.ancho_mm, formato.alto_mm)
    informe = colocar_plantilla(doc[0], formato, exigir_marco=False)
    assert informe.diferencia_marco_mm[0] == pytest.approx(1.0, abs=0.01)
    leido, _ = buscar_marco(doc[0], formato)
    assert leido[0] == pytest.approx(13.7, abs=0.01)
