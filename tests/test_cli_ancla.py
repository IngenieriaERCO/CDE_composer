"""CLI `colocar` con manifiesto y ancla CAD (datos sintéticos, no de ERCO).

Con --manifiesto el paquete debe estar completo, íntegro y coherente; si no, no se coloca.
"""

import pymupdf
import pytest

from componedor.cad_a_papel import MatrizCad, cad_a_papel
from componedor.cli import main
from componedor.transformaciones import rect_pdf_a_papel
from componedor.unidades import mm_a_pt
from conftest import (
    MATRIZ_SINTETICA,
    PAGINA_CAD_MM,
    RECT_CAD,
    crear_detalle_cad,
    crear_paquete_real,
    escribir_formato,
)

TOL_MM = 0.1
ANCLA_CAD = (RECT_CAD[0], RECT_CAD[1])  # esquina inferior izquierda del rectángulo CAD
ANCLA_PAPEL = (150.0, 200.0)


@pytest.fixture
def entradas(tmp_path):
    detalle = crear_paquete_real(tmp_path / "paquete")  # PDF + manifiesto coherentes
    return {
        "formato": escribir_formato(tmp_path / "formato.json"),
        "detalle": detalle,
        "manifiesto": detalle.with_name("detalle.manifest.json"),
        "salida": tmp_path / "salida.pdf",
    }


def _paquete(tmp_path, entradas, **kw):
    """Reemplaza el paquete de `entradas` por uno con las opciones dadas."""
    detalle = crear_paquete_real(tmp_path / "otro_paquete", **kw)
    entradas.update(detalle=detalle, manifiesto=detalle.with_name("detalle.manifest.json"))


def _args(e, *extra):
    return ["colocar", "--formato", str(e["formato"]), "--detalle", str(e["detalle"]),
            "--salida", str(e["salida"]), *extra]


def _ancla(ancla_cad=ANCLA_CAD, ancla_papel=ANCLA_PAPEL):
    return ["--ancla-cad", repr(ancla_cad[0]), repr(ancla_cad[1]),
            "--ancla-papel", repr(ancla_papel[0]), repr(ancla_papel[1])]


def test_esquinas_caen_donde_predice_cad_a_papel(entradas, capsys):
    assert main(_args(entradas, "--manifiesto", str(entradas["manifiesto"]), *_ancla())) == 0
    out = capsys.readouterr().out

    # Origen que imprimió el CLI (esquina inferior izquierda de la página del detalle).
    with pymupdf.open(entradas["salida"]) as doc:
        dibujos = doc[0].get_drawings()
    rects = [rect_pdf_a_papel(d["rect"], 594.0) for d in dibujos
             if abs(d["rect"].width - mm_a_pt(200)) < 1 and abs(d["rect"].height - mm_a_pt(80)) < 1]
    assert len(rects) == 1
    xmin, ymin, xmax, ymax = rects[0]

    # Predicción independiente: la esquina CAD del ancla cae en ANCLA_PAPEL, así que el
    # origen es ANCLA_PAPEL menos la posición relativa de esa esquina en la página.
    m = MatrizCad(*MATRIZ_SINTETICA)
    origen = (ANCLA_PAPEL[0] - 37.3, ANCLA_PAPEL[1] - (PAGINA_CAD_MM[1] - 98.7))
    abajo_izq = cad_a_papel(RECT_CAD[0], RECT_CAD[1], origen, PAGINA_CAD_MM[1], m)
    arriba_der = cad_a_papel(RECT_CAD[2], RECT_CAD[3], origen, PAGINA_CAD_MM[1], m)
    assert abs(xmin - abajo_izq[0]) <= TOL_MM and abs(ymin - abajo_izq[1]) <= TOL_MM
    assert abs(xmax - arriba_der[0]) <= TOL_MM and abs(ymax - arriba_der[1]) <= TOL_MM
    # Y la esquina del ancla está exactamente en el punto de papel pedido.
    assert abs(xmin - ANCLA_PAPEL[0]) <= TOL_MM and abs(ymin - ANCLA_PAPEL[1]) <= TOL_MM

    assert "Rectángulo del dibujo (page_bounds_mm en papel): X 150.00 a 350.00, " \
           "Y 200.00 a 280.00" in out
    assert ("Paquete verificado: completo, integridad OK y coherencia OK (trazos del PDF vs "
            "page_bounds_mm: diferencia máx. 0.000 mm)") in out


def test_con_manifiesto_y_centrar_tambien_imprime_el_dibujo(entradas, capsys):
    assert main(_args(entradas, "--centrar", "--manifiesto", str(entradas["manifiesto"]))) == 0
    out = capsys.readouterr().out
    assert "Rectángulo ocupado (mm)" in out
    assert "Rectángulo del dibujo (page_bounds_mm en papel)" in out


def test_paquete_incoherente_no_se_coloca(entradas, capsys, tmp_path):
    # Antes era una advertencia; ahora la coherencia es requisito para colocar.
    _paquete(tmp_path, entradas, desplazar_dibujo_mm=(0.0, 1.5))
    assert main(_args(entradas, "--centrar", "--manifiesto", str(entradas["manifiesto"]))) == 1
    err = capsys.readouterr().err
    assert "Paquete 'detalle' rechazado (1 motivo):" in err
    assert ("  - [coherencia] los trazos del PDF no están donde dice page_bounds_mm "
            "(diferencia máx. 1.500 mm)") in err
    assert not entradas["salida"].exists()


def test_integridad_fallida_no_se_coloca(entradas, capsys):
    datos = bytearray(entradas["detalle"].read_bytes())
    datos[200] ^= 0x01
    entradas["detalle"].write_bytes(bytes(datos))
    assert main(_args(entradas, "--centrar", "--manifiesto", str(entradas["manifiesto"]))) == 1
    assert "  - [integridad] el contenido del PDF cambió después de exportarse" in         capsys.readouterr().err
    assert not entradas["salida"].exists()


def test_escala_no_garantizada_no_se_coloca(entradas, capsys, tmp_path):
    _paquete(tmp_path, entradas, cambiar={"scale.physical_scale_guaranteed": False})
    assert main(_args(entradas, "--manifiesto", str(entradas["manifiesto"]), *_ancla())) == 1
    assert "  - [escala] escala física no garantizada: el paquete no se usa" in         capsys.readouterr().err


def test_detalle_que_no_es_el_del_manifiesto(entradas, capsys, tmp_path):
    otro = crear_detalle_cad(tmp_path / "otro.pdf")  # mismo dibujo, pero otro archivo
    args = _args(dict(entradas, detalle=otro), "--centrar", "--manifiesto",
                 str(entradas["manifiesto"]))
    assert main(args) == 1
    err = capsys.readouterr().err
    assert (f"  - [archivos] el PDF indicado '{otro}' no es el del paquete: el manifiesto "
            f"indica 'detalle.pdf'") in err
    assert not entradas["salida"].exists()


def test_paquete_incompleto_no_se_coloca(entradas, capsys, tmp_path):
    otro = crear_detalle_cad(tmp_path / "suelto.pdf")
    entradas["detalle"].unlink()
    assert main(_args(dict(entradas, detalle=otro), "--centrar", "--manifiesto",
                      str(entradas["manifiesto"]))) == 1
    err = capsys.readouterr().err
    assert "Paquete 'detalle' rechazado (1 motivo):" in err
    assert "  - [archivos] falta el PDF 'detalle.pdf'" in err


def test_ancla_fuera_de_la_zona_no_crea_archivo(entradas, capsys):
    args = _args(entradas, "--manifiesto", str(entradas["manifiesto"]),
                 *_ancla(ancla_papel=(600.0, 200.0)))
    assert main(args) == 1
    assert "se pasa" in capsys.readouterr().err
    assert not entradas["salida"].exists()


def test_manifiesto_invalido_no_crea_archivo(entradas, capsys, tmp_path):
    _paquete(tmp_path, entradas, cambiar={"pdf.drawing.cad_to_page.units": "m"})
    assert main(_args(entradas, "--manifiesto", str(entradas["manifiesto"]), *_ancla())) == 1
    err = capsys.readouterr().err
    assert "Paquete 'detalle' rechazado (1 motivo):" in err
    assert "  - [manifiesto] pdf.drawing.cad_to_page.units: debe ser 'mm'; tiene 'm'" in err
    assert not entradas["salida"].exists()


def test_archivo_que_no_es_manifiesto(entradas, capsys, tmp_path):
    otro = tmp_path / "geometria.json"
    otro.write_text("{}", encoding="utf-8")
    assert main(_args(entradas, "--centrar", "--manifiesto", str(otro))) == 1
    err = capsys.readouterr().err
    assert "Paquete 'geometria.json' rechazado (1 motivo):" in err
    assert "[archivos] 'geometria.json' no es un manifiesto de paquete" in err


@pytest.mark.parametrize("extra, mensaje", [
    (["--centrar", "--manifiesto", "m.json", *_ancla()],
     "--centrar y --ancla-cad son excluyentes"),
    (["--posicion", "10", "10", "--manifiesto", "m.json", *_ancla()],
     "--posicion y --ancla-cad son excluyentes"),
    (_ancla(), "--ancla-cad requiere --manifiesto"),
    (["--manifiesto", "m.json", "--ancla-cad", "1", "2"], "--ancla-cad requiere --ancla-papel"),
    (["--centrar", "--ancla-papel", "1", "2"], "--ancla-papel va junto con --ancla-cad"),
    ([], "Indique dónde colocar el detalle"),
])
def test_opciones_incompatibles(entradas, capsys, extra, mensaje):
    assert main(_args(entradas, *extra)) == 2
    assert mensaje in capsys.readouterr().err
    assert not entradas["salida"].exists()
