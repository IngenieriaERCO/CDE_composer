"""Comprobación h con máscara de recorte (manifiesto 1.5, `pdf.drawing.mask`).

Paquete sintético (no de ERCO) como el de una zona del Model Space: lo que cruza el borde
se escribe entero en el PDF y una máscara lo oculta; `get_drawings()` lo devuelve entero,
así que la h recorta cada trazo a `mask.zone_page_mm` antes de medir
(docs/manifiesto.md del exportador, «Cómo medir los trazos con máscara»).
"""

import pymupdf
import pytest
from conftest import crear_paquete_real, escribir_json, manifiesto_paquete

from componedor.coherencia import verificar_paquete
from componedor.comprobacion_dibujo import medir_limites_trazos, recortar_a_zona
from componedor.manifiesto import ManifiestoInvalido, leer_manifiesto
from componedor.paquete import localizar_paquetes
from componedor.unidades import mm_a_pt

PAGINA_MM = (100.0, 80.0)
ZONA_MM = (5.0, 5.0, 95.0, 75.0)  # x0, y0, x1, y1 (mm de página, Y abajo)
VISIBLE_MM = (10.0, 5.0, 95.0, 50.0)  # lo dibujado recortado a la zona
# 1:50 en m: x_pag = 20·X, y_pag = −20·Y + 100
MATRIZ = [20.0, 0.0, 0.0, -20.0, 0.0, 100.0]


def _linea(pagina, x0, y0, x1, y1):
    pagina.draw_line(pymupdf.Point(mm_a_pt(x0), mm_a_pt(y0)),
                     pymupdf.Point(mm_a_pt(x1), mm_a_pt(y1)), color=(0, 0, 0), width=0.25)


def _pdf_de_zona(solo_fuera: bool = False) -> bytes:
    doc = pymupdf.open()
    p = doc.new_page(width=mm_a_pt(PAGINA_MM[0]), height=mm_a_pt(PAGINA_MM[1]))
    if not solo_fuera:
        p.draw_rect(pymupdf.Rect(*(mm_a_pt(v) for v in (10, 10, 60, 50))), color=(0, 0, 0))
        _linea(p, 40, 30, 130, 30)   # horizontal (alto 0): cruza la zona y la página
        _linea(p, 20, -20, 20, 40)   # vertical (ancho 0): sale por arriba de la página
    _linea(p, 96, 2, 99, 3)          # entero en la franja del bleed: no cuenta
    contenido = doc.tobytes()
    doc.close()
    return contenido


def _cambios(mascara="zona"):
    x0, y0, x1, y1 = VISIBLE_MM
    cambios = {
        "schema_version": "1.5",
        "pdf.page_size_mm": list(PAGINA_MM),
        "pdf.expected_page_size_mm": list(PAGINA_MM),
        "pdf.drawing.cad_bounds": {"min": [x0 / 20, (100 - y1) / 20],
                                   "max": [x1 / 20, (100 - y0) / 20]},
        "pdf.drawing.page_bounds_mm": {"x0": x0, "y0": y0, "x1": x1, "y1": y1},
        "pdf.drawing.cad_to_page.matrix": MATRIZ,
    }
    if mascara == "zona":
        zx0, zy0, zx1, zy1 = ZONA_MM
        cambios["pdf.drawing.mask"] = {
            "zone_cad": [zx0 / 20, (100 - zy1) / 20, zx1 / 20, (100 - zy0) / 20],
            "zone_page_mm": {"x0": zx0, "y0": zy0, "x1": zx1, "y1": zy1}, "bleed_mm": 0.5}
    elif mascara is not ...:
        cambios["pdf.drawing.mask"] = mascara
    return cambios


def _coherencia(carpeta, **kw):
    crear_paquete_real(carpeta, "Zona_01", contenido=_pdf_de_zona(**kw.pop("pdf", {})),
                       cambiar=_cambios(**kw))
    (paquete,) = localizar_paquetes(carpeta)
    integridad, coherencia = verificar_paquete(paquete)
    assert integridad.pasa
    return coherencia


def _h(resultado):
    (c,) = [c for c in resultado.comprobaciones if c.nombre.startswith("h)")]
    return c


# --- recortar_a_zona ----------------------------------------------------------------------

def _trazo(x0, y0, x1, y1):
    return {"type": "s", "rect": pymupdf.Rect(*(mm_a_pt(v) for v in (x0, y0, x1, y1)))}


def test_recorte_conserva_segmentos_horizontales_y_verticales():
    horizontal, vertical = _trazo(40, 30, 130, 30), _trazo(20, -20, 20, 40)
    rec = recortar_a_zona([horizontal, vertical], ZONA_MM)
    assert [tuple(t["rect"]) for t in rec] == [
        pytest.approx((mm_a_pt(40), mm_a_pt(30), mm_a_pt(95), mm_a_pt(30))),
        pytest.approx((mm_a_pt(20), mm_a_pt(5), mm_a_pt(20), mm_a_pt(40)))]


def test_recorte_descarta_lo_de_fuera_y_conserva_lo_que_toca_el_borde():
    fuera, toca = _trazo(96, 2, 99, 3), _trazo(95, 10, 120, 20)
    rec = recortar_a_zona([fuera, toca], ZONA_MM)
    assert len(rec) == 1
    assert rec[0]["rect"].x0 == pytest.approx(mm_a_pt(95))
    assert rec[0]["rect"].x1 == pytest.approx(mm_a_pt(95))  # ancho cero: cuenta


def test_recorte_no_cambia_los_trazos_recibidos():
    t = _trazo(0, 0, 200, 200)
    recortar_a_zona([t], ZONA_MM)
    assert t["rect"].x1 == pytest.approx(mm_a_pt(200))


def test_medir_con_y_sin_mascara(tmp_path):
    ruta = tmp_path / "z.pdf"
    ruta.write_bytes(_pdf_de_zona())
    doc = pymupdf.open(ruta)
    assert medir_limites_trazos(doc[0], ZONA_MM) == pytest.approx(VISIBLE_MM, abs=0.01)
    assert medir_limites_trazos(doc[0])[2] == pytest.approx(130, abs=0.01)  # sin recorte
    doc.close()


# --- manifiesto ---------------------------------------------------------------------------

def _leer(tmp_path, **cambios):
    return leer_manifiesto(escribir_json(tmp_path / "m.manifest.json",
                                         manifiesto_paquete(cambiar=cambios)))


def test_manifiesto_sin_mask_o_con_null_no_tiene_mascara(tmp_path):
    assert _leer(tmp_path).pdf.dibujo.mascara_mm is None  # 1.0–1.4: no existe la clave
    assert _leer(tmp_path, **{"pdf.drawing.mask": None}).pdf.dibujo.mascara_mm is None


def test_manifiesto_lee_la_zona_de_la_mascara(tmp_path):
    m = _leer(tmp_path, **_cambios())
    assert m.pdf.dibujo.mascara_mm == ZONA_MM


@pytest.mark.parametrize("mascara, texto", [
    ({"zone_page_mm": {"x0": 50, "y0": 5, "x1": 10, "y1": 75}},
     "pdf.drawing.mask.zone_page_mm: debe cumplir x1 > x0 e y1 > y0"),
    ({"bleed_mm": 0.5}, "pdf.drawing.mask.zone_page_mm: falta el campo"),
    ([1, 2, 3, 4], "pdf.drawing.mask: se esperaba un objeto"),
])
def test_manifiesto_rechaza_una_mascara_mal_formada(tmp_path, mascara, texto):
    with pytest.raises(ManifiestoInvalido, match=texto.replace("(", r"\(").replace(")", r"\)")):
        _leer(tmp_path, **{"pdf.drawing.mask": mascara})


# --- comprobación h -----------------------------------------------------------------------

def test_h_pasa_con_la_mascara(tmp_path):
    r = _coherencia(tmp_path)
    assert r.pasa, [(c.nombre, c.detalle) for c in r.fallas]
    assert r.datos["diferencia_trazos_mm"] < 0.01
    assert _h(r).nombre == ("h) Trazos del PDF vs page_bounds_mm (recortados a la máscara "
                            "x0 5.000, y0 5.000, x1 95.000, y1 75.000)")


def test_h_falla_si_el_mismo_pdf_no_trae_mascara(tmp_path):
    r = _coherencia(tmp_path, mascara=None)  # mask: null → sin recorte
    assert {c.nombre[0] for c in r.fallas} == {"h"}
    assert "recortados" not in _h(r).nombre


def test_h_falla_sin_trazos_dentro_de_la_zona(tmp_path):
    r = _coherencia(tmp_path, pdf={"solo_fuera": True})
    c = _h(r)
    assert not c.pasa
    assert c.medido == "sin trazos"
    assert c.detalle == "el PDF no tiene trazos dentro de la zona de la máscara de recorte"
