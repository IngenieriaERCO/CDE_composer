"""CLI `colocar` con manifiesto y ancla CAD (datos sintéticos, no de ERCO)."""

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
    escribir_formato,
    escribir_json,
    manifiesto_sintetico,
)

TOL_MM = 0.1
ANCLA_CAD = (RECT_CAD[0], RECT_CAD[1])  # esquina inferior izquierda del rectángulo CAD
ANCLA_PAPEL = (150.0, 200.0)


@pytest.fixture
def entradas(tmp_path):
    return {
        "formato": escribir_formato(tmp_path / "formato.json"),
        "detalle": crear_detalle_cad(tmp_path / "detalle.pdf"),
        "manifiesto": escribir_json(tmp_path / "detalle.manifest.json", manifiesto_sintetico()),
        "salida": tmp_path / "salida.pdf",
    }


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
    assert "diferencia máx. 0.00" in out
    assert "ADVERTENCIA" not in out


def test_con_manifiesto_y_centrar_tambien_imprime_el_dibujo(entradas, capsys):
    assert main(_args(entradas, "--centrar", "--manifiesto", str(entradas["manifiesto"]))) == 0
    out = capsys.readouterr().out
    assert "Rectángulo ocupado (mm)" in out
    assert "Rectángulo del dibujo (page_bounds_mm en papel)" in out


def test_advertencia_si_page_bounds_no_coincide(entradas, capsys, tmp_path):
    datos = manifiesto_sintetico()
    datos["pdf"]["drawing"]["page_bounds_mm"]["y1"] += 1.5
    manifiesto = escribir_json(tmp_path / "otro.json", datos)
    assert main(_args(entradas, "--centrar", "--manifiesto", str(manifiesto))) == 0
    out = capsys.readouterr().out
    assert "diferencia máx. 1.500 mm" in out
    assert "ADVERTENCIA" in out
    assert entradas["salida"].exists()


def test_ancla_fuera_de_la_zona_no_crea_archivo(entradas, capsys):
    args = _args(entradas, "--manifiesto", str(entradas["manifiesto"]),
                 *_ancla(ancla_papel=(600.0, 200.0)))
    assert main(args) == 1
    assert "se pasa" in capsys.readouterr().err
    assert not entradas["salida"].exists()


def test_manifiesto_invalido_no_crea_archivo(entradas, capsys, tmp_path):
    manifiesto = escribir_json(tmp_path / "m.json", manifiesto_sintetico(units="m"))
    assert main(_args(entradas, "--manifiesto", str(manifiesto), *_ancla())) == 1
    assert "debe ser 'mm'" in capsys.readouterr().err
    assert not entradas["salida"].exists()


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
