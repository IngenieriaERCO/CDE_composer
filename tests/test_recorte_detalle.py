"""El recorte de cada detalle en la hoja (Fase 11): se ve el dibujo más un margen, no la página
entera del paquete. Sigue siendo vector, el dibujo no se mueve y la verificación final de
componer (±0,1 mm contra los trazos del PDF del detalle) sigue igual."""

import json

import pymupdf
import pytest
from conftest import crear_paquete_real, crear_plantilla_sintetica, escribir_formato
from ortofoto_sintetica import crear_geotiff, error_de_posicion, imagenes_pdf
from test_componer_ortofoto import MATRIZ, POCO, X0_CAD, Y0_CAD

from componedor import componer
from componedor.componer import PlanoNoComponible, componer_plano
from componedor.ortofoto_pdf import papel_a_cad
from componedor.plano import PlanoInvalido, leer_plano
from componedor.recorte_detalle import (
    posicion_centrada_recorte,
    recorte_pagina,
    visible_en_papel,
)
from componedor.transformaciones import rect_pdf_a_papel

# Paquete sintético: página 260 × 120 mm; page_bounds (página, Y abajo) 37,3..237,3 ×
# 18,7..98,7: en papel, relativo a la esquina de la página, X +37,3..+237,3, Y +21,3..+101,3.
LIMITES = (37.3, 18.7, 237.3, 98.7)
AREA = (22.7, 22.7, 662.4, 571.3)


def _dibujo(x, y, m=0.0):
    return (x + 37.3 - m, y + 21.3 - m, x + 237.3 + m, y + 101.3 + m)


@pytest.fixture
def entorno(tmp_path):
    escribir_formato(tmp_path / "formato.json",
                     plantilla=crear_plantilla_sintetica(tmp_path / "rotulo.pdf"))
    crear_paquete_real(tmp_path / "input", "a")  # con fondo blanco (exportador viejo)
    crear_paquete_real(tmp_path / "input", "s", sin_fondo=True)
    return tmp_path


def _plano(carpeta, detalles, version=2):
    ruta = carpeta / "plano.json"
    ruta.write_text(json.dumps({"version": version, "formato": "formato.json",
                                "detalles": detalles}), encoding="utf-8")
    return ruta


def _d(id_, prefijo, pos=None, **extra):
    d = {"id": id_, "manifiesto": f"input/{prefijo}.manifest.json", **extra}
    if pos is not None:
        d["posicion_mm"] = list(pos)
    return d


def _recortes_pdf(ruta):
    """Los rectángulos de recorte (clip) de la hoja, en mm de papel."""
    with pymupdf.open(ruta) as doc:
        return [rect_pdf_a_papel(d["scissor"], 594.0) for d in doc[0].get_drawings(extended=True)
                if d.get("type") == "clip" and d.get("scissor") is not None]


# --- el cálculo ---------------------------------------------------------------------------

def test_recorte_de_la_pagina():
    assert recorte_pagina((260, 120), LIMITES, 1) == pytest.approx((36.3, 17.7, 238.3, 99.7))
    assert recorte_pagina((260, 120), LIMITES, 0) == LIMITES
    # Nunca más que la página.
    assert recorte_pagina((260, 120), LIMITES, 50) == (0.0, 0.0, 260.0, 120.0)
    assert visible_en_papel(LIMITES, 120, (30, 40)) == pytest.approx(_dibujo(30, 40))
    # Centrado: lo que se ve (no la página) queda en el centro del área.
    x, y = posicion_centrada_recorte(recorte_pagina((260, 120), LIMITES, 1), 120, AREA)
    v = _dibujo(x, y, 1)
    assert ((v[0] + v[2]) / 2, (v[1] + v[3]) / 2) == pytest.approx((342.55, 297.0))


# --- componer: margen 0 y 1 mm ------------------------------------------------------------

def test_un_detalle_con_margen_0_y_otro_con_1_mm(entorno):
    """«a» con su margen 0 (en el plano) y «s» con el general, 1 mm: cada uno se ve recortado,
    el dibujo queda donde dice posicion_mm y la verificación final (±0,1 mm) pasa."""
    plano = leer_plano(_plano(entorno, [_d("cero", "a", (30, 400), margen_mm=0),
                                        _d("uno", "s", (330, 400))]))
    assert [d.margen_mm for d in plano.detalles] == [0.0, None]
    r = componer_plano(plano, entorno / "p.pdf")
    cero, uno = r.detalles
    assert cero.margen_mm == 0.0 and uno.margen_mm == 1.0
    assert cero.ocupado == pytest.approx(_dibujo(30, 400), abs=1e-4)
    assert uno.ocupado == pytest.approx(_dibujo(330, 400, 1), abs=1e-4)
    # La página entera sigue en posicion_mm: el dibujo no se movió.
    assert cero.pagina == pytest.approx((30, 400, 290, 520), abs=1e-4)
    assert cero.dibujo == pytest.approx(_dibujo(30, 400), abs=1e-4)
    # En el PDF: un recorte por detalle, justo lo que se ve; sin imágenes nuevas (vector).
    recortes = _recortes_pdf(entorno / "p.pdf")
    for esperado in (cero.ocupado, uno.ocupado):
        assert any(c == pytest.approx(esperado, abs=0.01) for c in recortes), esperado
    # Los mismos trazos e imágenes que sin recorte: nada se rasterizó, solo se ve menos página.
    componer_plano(plano, entorno / "entera.pdf", margen_mm=None)
    with pymupdf.open(entorno / "p.pdf") as con, pymupdf.open(entorno / "entera.pdf") as sin:
        assert len(con[0].get_drawings()) == len(sin[0].get_drawings())
        assert len(con[0].get_image_info()) == len(sin[0].get_image_info())


def test_cabe_lo_que_se_ve_aunque_la_pagina_se_salga(entorno):
    """Con x = 0 la página (0..260) se sale del área (22,7); lo que se ve (36,3..) no."""
    r = componer_plano(leer_plano(_plano(entorno, [_d("a", "s", (0, 400))])), entorno / "p.pdf")
    assert r.detalles[0].ocupado[0] == pytest.approx(36.3, abs=1e-4)
    with pytest.raises(PlanoNoComponible) as e:  # sin recorte (la página entera), no
        componer_plano(leer_plano(_plano(entorno, [_d("a", "s", (0, 400))])), entorno / "q.pdf",
                       margen_mm=None)
    assert "fuera de 'area_dibujo'" in str(e.value)
    # Si lo que se ve se sale, error: X 0 - 37,3 + 1 = -36,3… pegado al borde por la izquierda.
    with pytest.raises(PlanoNoComponible):
        componer_plano(leer_plano(_plano(entorno, [_d("a", "s", (-20, 400))])), entorno / "r.pdf")


def test_centrar_centra_lo_que_se_ve(entorno):
    r = componer_plano(leer_plano(_plano(entorno, [_d("a", "s", centrar=True)])), entorno / "p.pdf")
    v = r.detalles[0].ocupado
    assert ((v[0] + v[2]) / 2, (v[1] + v[3]) / 2) == pytest.approx((342.55, 297.0), abs=1e-3)
    assert r.detalles[0].pagina[:2] == pytest.approx((205.25, 235.7), abs=1e-3)


def test_el_margen_general_sale_del_parametro(entorno):
    plano = leer_plano(_plano(entorno, [_d("a", "s", (30, 400)), _d("b", "s", (330, 400),
                                                                   margen_mm=2.5)]))
    a, b = componer_plano(plano, entorno / "p.pdf", margen_mm=4).detalles
    assert a.ocupado == pytest.approx(_dibujo(30, 400, 4), abs=1e-4)
    assert b.ocupado == pytest.approx(_dibujo(330, 400, 2.5), abs=1e-4)  # el suyo manda


def test_la_verificacion_sigue_detectando_un_detalle_corrido(entorno, monkeypatch):
    """Con recorte, 0,5 mm de corrimiento real sigue fallando (tolerancia ±0,1 mm)."""
    original = componer.insertar_pagina

    def corrido(hoja, formato, doc, pagina, posicion, recorte=None):
        return original(hoja, formato, doc, pagina, (posicion[0], posicion[1] + 0.5), recorte)

    monkeypatch.setattr(componer, "insertar_pagina", corrido)
    with pytest.raises(PlanoNoComponible) as e:
        componer_plano(leer_plano(_plano(entorno, [_d("a", "a", (30, 400), margen_mm=0)])),
                       entorno / "p.pdf")
    assert "diferencia máx. 0.500 mm, tolerancia ±0.1 mm" in str(e.value)
    assert not (entorno / "p.pdf").exists()


def test_margen_en_el_plano(entorno):
    for margen, texto in ((-1, "margen_mm: se esperaba un número de 0 a 50"),
                          (51, "margen_mm: se esperaba un número de 0 a 50"),
                          ("1", "margen_mm: se esperaba un número de 0 a 50")):
        with pytest.raises(PlanoInvalido, match=texto):
            leer_plano(_plano(entorno, [_d("a", "s", (30, 400), margen_mm=margen)]))
    with pytest.raises(PlanoInvalido, match="margen_mm: solo existe en la versión 2"):
        leer_plano(_plano(entorno, [_d("a", "s", (30, 400), margen_mm=1)], version=1))
    # Los planos viejos (sin la clave) se leen igual.
    assert leer_plano(_plano(entorno, [_d("a", "s", (30, 400))], version=1)).detalles[0].margen_mm is None


# --- con ortofoto: la foto se corta al mismo margen que el dibujo -------------------------

def test_con_ortofoto_la_foto_va_detras_de_lo_que_se_ve(tmp_path):
    escribir_formato(tmp_path / "formato.json",
                     plantilla=crear_plantilla_sintetica(tmp_path / "rotulo.pdf"))
    crear_paquete_real(tmp_path / "input", "a", sin_fondo=True)
    tif = tmp_path / "fotos" / "orto.tif"
    crear_geotiff(tif, ancho=400, alto=200, origen=(X0_CAD - 2, Y0_CAD + 8), pixel=0.05,
                  sinusoidal=True)
    ruta = tmp_path / "planos" / "plano.json"
    ruta.parent.mkdir()
    ruta.write_text(json.dumps({
        "version": 5, "formato": "../formato.json",
        "detalles": [{"id": "a", "manifiesto": "../input/a.manifest.json",
                      "posicion_mm": [30.0, 40.0], "ortofoto": True, "margen_mm": 1}],
        "ortofoto": {"archivo": "../fotos/orto.tif", "bytes": tif.stat().st_size,
                     "crs": "EPSG:9377", "crs_dibujo": "EPSG:9377", "opacidad": 1.0}}),
        encoding="utf-8")
    r = componer_plano(leer_plano(ruta), tmp_path / "p.pdf", config_ortofoto=POCO)
    (a,) = r.detalles
    assert a.ocupado == pytest.approx(_dibujo(30, 40, 1), abs=1e-4)
    assert r.ortofoto.cobertura == {"a": 1.0} and r.extendida is False
    (foto,) = [i for i in imagenes_pdf(tmp_path / "p.pdf", 594.0) if i["filtro"] == "/DCTDecode"]
    # La foto cubre lo que se ve (no la página entera) y sigue en su sitio: el mapeo CAD → papel
    # es el de la página del paquete en posicion_mm.
    assert foto["rect_mm"] == pytest.approx(a.ocupado, abs=0.01)
    pagina = (30.0, 40.0, 290.0, 160.0)
    assert error_de_posicion(foto, lambda x, y: papel_a_cad((x, y), pagina, MATRIZ), tif) < 4
