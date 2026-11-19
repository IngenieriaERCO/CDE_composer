"""Imagen de localización en el rótulo (localizacion.py y componer): contener, PNG reducido a
~300 ppp sin agrandar, JPG tal cual, copia junto al plano, aviso de la escala vacía, el PDF."""

import json
import os
import re
import shutil

import numpy as np
import pymupdf
import pytest
from conftest import (
    ARIAL,
    crear_paquete_real,
    crear_plantilla_sintetica,
    escribir_formato,
    requiere_arial,
    rotulo_a1,
)

from componedor.cli import main
from componedor.componer import PlanoNoComponible, componer_plano
from componedor.formato import cargar_formato
from componedor.localizacion import (
    LocalizacionInvalida,
    contener,
    copia_junto_al_plano,
    leer_valor,
    preparar,
)
from componedor.ortofoto_fuente import fecha
from componedor.plano import leer_plano
from componedor.rotulo_formato import CampoImagen
from componedor.transformaciones import rect_pdf_a_papel

RECT = (673.4, 455.8, 827.3, 570.2)  # el recuadro de A1_ERCO (153,9 × 114,4 mm)
CAMPO = CampoImagen("localizacion_imagen", RECT, 300, "localizacion_escala")


def png(ruta, ancho, alto, alfa=False):
    """Un mapa sintético: degradado con una cruz (sin compresión con pérdida)."""
    filas, cols = np.mgrid[0:alto, 0:ancho]
    rgb = np.stack([cols * 255 // max(1, ancho - 1), filas * 255 // max(1, alto - 1),
                    np.full((alto, ancho), 120)], axis=-1).astype(np.uint8)
    rgb[alto // 2, :] = 0
    rgb[:, ancho // 2] = 0
    n = 4 if alfa else 3
    datos = np.concatenate([rgb, np.full((alto, ancho, 1), 255, np.uint8)], axis=-1) if alfa else rgb
    pix = pymupdf.Pixmap(pymupdf.csRGB, ancho, alto, datos.tobytes(), alfa)
    assert pix.n == n
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(pix.tobytes("png"))
    return ruta


def jpg(ruta, ancho, alto):
    p = png(ruta.with_suffix(".tmp.png"), ancho, alto)
    pix = pymupdf.Pixmap(str(p))
    ruta.write_bytes(pix.tobytes("jpg", jpg_quality=80))
    p.unlink()
    return ruta


def valor(ruta, carpeta):
    return {"archivo": os.path.relpath(ruta, carpeta).replace(os.sep, "/"),
            "bytes": ruta.stat().st_size, "modificado": fecha(ruta)}


def test_contener_entera_centrada_sin_deformar():
    ancha = contener(RECT, 2000, 1000)  # más ancha que el recuadro: llena el ancho
    assert ancha[0] == pytest.approx(RECT[0]) and ancha[2] == pytest.approx(RECT[2])
    assert (ancha[3] - ancha[1]) == pytest.approx(153.9 / 2)
    assert (ancha[1] + ancha[3]) / 2 == pytest.approx((RECT[1] + RECT[3]) / 2)
    alta = contener(RECT, 500, 1000)  # más alta: llena el alto, bandas a los lados
    assert alta[1] == pytest.approx(RECT[1]) and alta[3] == pytest.approx(RECT[3])
    assert (alta[2] - alta[0]) == pytest.approx(114.4 / 2)


def test_el_recuadro_de_a1_no_tapa_esc_ni_coordenadas():
    f = cargar_formato("formatos/A1_ERCO.json", usar_plantilla=False)
    c = f.rotulo.campos["localizacion_imagen"]
    assert isinstance(c, CampoImagen) and c.rect == RECT and c.ppp == 300
    assert c.campo_escala == "localizacion_escala"
    escala = f.rotulo.campos["localizacion_escala"].celda.rect
    assert c.rect[1] > escala[3]  # por encima de la fila de «ESC:»
    zona = f.zonas["localizacion"]
    assert zona[0] <= c.rect[0] and c.rect[2] <= zona[2] and c.rect[3] <= zona[3]


@pytest.mark.parametrize("v, texto", [
    ("a.png", "se esperaba un objeto"),
    ({"archivo": ""}, "archivo: se esperaba la ruta"),
    ({"archivo": "mapa.tif"}, "no es un .png ni un .jpg"),
    ({"archivo": "a.png", "bytes": -1}, "bytes: se esperaba un entero"),
    ({"archivo": "a.png", "ruta": "x"}, "ruta: campo no reconocido"),
])
def test_valor_mal_escrito(v, texto):
    problemas = []
    assert leer_valor(v, "rotulo.localizacion_imagen", problemas) is None
    assert texto in problemas[0]


def test_png_grande_se_reduce_a_300_ppp_y_deja_la_copia(tmp_path):
    plano = tmp_path / "planos" / "Plano 1.json"
    plano.parent.mkdir()
    img = png(tmp_path / "qgis" / "loc.png", 3000, 2000)  # ~495 ppp en 153,9 mm
    r = preparar(CAMPO, valor(img, plano.parent), plano, escala_vacia=False)
    assert r.origen == "original" and r.formato == "png" and r.avisos == []
    assert r.px_original == (3000, 2000)
    assert r.px == (1818, 1212) and r.ppp == pytest.approx(300, abs=0.5)
    assert pymupdf.Pixmap(r.datos).width == 1818
    copia = copia_junto_al_plano(plano, ".png")
    assert copia == tmp_path / "planos" / "Plano 1_localizacion.png"
    assert copia.read_bytes() == img.read_bytes()


def test_png_chico_no_se_agranda_y_jpg_va_tal_cual(tmp_path):
    plano = tmp_path / "plano.json"
    chico = png(tmp_path / "chico.png", 600, 400)  # ~99 ppp
    r = preparar(CAMPO, valor(chico, tmp_path), plano, escala_vacia=False)
    assert r.px == (600, 400) and r.datos == chico.read_bytes()
    grande = jpg(tmp_path / "loc.jpg", 4000, 2600)  # ~660 ppp: igual va tal cual
    r = preparar(CAMPO, valor(grande, tmp_path), plano, escala_vacia=False)
    assert r.formato == "jpeg" and r.datos == grande.read_bytes() and r.px == (4000, 2600)


def test_original_movido_o_cambiado_usa_la_copia_con_aviso(tmp_path):
    plano = tmp_path / "plano.json"
    img = png(tmp_path / "qgis" / "loc.png", 900, 600)
    v = valor(img, tmp_path)
    preparar(CAMPO, v, plano, escala_vacia=False)  # deja la copia
    shutil.move(img, tmp_path / "otro.png")
    r = preparar(CAMPO, v, plano, escala_vacia=False)
    assert r.origen == "copia" and r.archivo.name == "plano_localizacion.png"
    assert "no se encontró" in r.avisos[0] and "se usó la copia" in r.avisos[0]
    (tmp_path / "plano_localizacion.png").unlink()
    with pytest.raises(LocalizacionInvalida, match="no hay una copia «plano_localizacion.png»"):
        preparar(CAMPO, v, plano, escala_vacia=False)


def test_aviso_de_escala_vacia(tmp_path):
    img = png(tmp_path / "loc.png", 900, 600)
    r = preparar(CAMPO, valor(img, tmp_path), tmp_path / "p.json", escala_vacia=True)
    assert r.avisos == [("rotulo.localizacion_escala: la imagen de localización no tiene "
                         "escala: sale «DEFINIR». Escríbala a mano en el editor (Rótulo).")]


@pytest.fixture
def entorno(tmp_path):
    escribir_formato(tmp_path / "formato.json",
                     plantilla=crear_plantilla_sintetica(tmp_path / "rotulo.pdf"),
                     rotulo=rotulo_a1(fuente={"archivo": str(ARIAL)}))
    crear_paquete_real(tmp_path / "input", "a", sin_fondo=True)
    return tmp_path


def plano(carpeta, rotulo):
    datos = {"version": 2, "formato": "formato.json", "rotulo": rotulo,
             "detalles": [{"id": "a", "manifiesto": "input/a.manifest.json",
                           "posicion_mm": [30, 40]}]}
    ruta = carpeta / "plano.json"
    ruta.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    return leer_plano(ruta)


@requiere_arial
@pytest.mark.parametrize("tipo", ["png", "jpg"])
def test_componer_pone_la_imagen_en_su_recuadro(entorno, tipo, capsys):
    img = (png(entorno / "qgis" / "loc.png", 3000, 2000) if tipo == "png"
           else jpg(entorno / "qgis" / "loc.jpg", 1200, 800))
    p = plano(entorno, {"localizacion_imagen": valor(img, entorno),
                        "localizacion_escala": "1:25000"})
    r = componer_plano(p, entorno / "p.pdf")
    loc = r.localizacion
    assert loc is not None and r.advertencias == []
    with pymupdf.open(entorno / "p.pdf") as d:
        page = d[0]
        (info,) = [i for i in page.get_images(full=True) if i[2] == loc.px[0]]
        (rect,) = page.get_image_rects(info[0])
        assert max(abs(a - b) for a, b in zip(rect_pdf_a_papel(rect, 594.0), loc.destino)) < 0.1
        filtro = d.xref_get_key(info[0], "Filter")[1]
        assert ("DCTDecode" in filtro) == (tipo == "jpg")
        # Debajo de los textos del rótulo: la imagen se dibuja antes que «1:25000».
        orden = page.read_contents().decode("latin-1")
        imagenes = list(re.finditer(r"/fzImg\d+ Do", orden))
        assert imagenes and imagenes[-1].start() < orden.rindex("BT")
        assert "1:25000" in page.get_text()
    assert main(["componer", str(p.ruta), "--salida", str(entorno / "q.pdf")]) == 0
    salida = capsys.readouterr().out
    assert re.search(r"Imagen de localización \(el original: loc\.(png|jpg)\)", salida)
    assert "que las de la plantilla y la imagen de localización" in salida
    assert ("sigue siendo el JPEG original" in salida) == (tipo == "jpg")


@requiere_arial
def test_componer_sin_escala_avisa_y_sale_definir(entorno):
    img = png(entorno / "loc.png", 900, 600)
    r = componer_plano(plano(entorno, {"localizacion_imagen": valor(img, entorno)}),
                       entorno / "p.pdf")
    assert any("sale «DEFINIR»" in a for a in r.advertencias)
    with pymupdf.open(entorno / "p.pdf") as d:
        assert "DEFINIR" in d[0].get_text()


@requiere_arial
def test_componer_sin_imagen_ni_copia_no_compone(entorno):
    p = plano(entorno, {"localizacion_imagen": {"archivo": "no_esta.png", "bytes": 10}})
    with pytest.raises(PlanoNoComponible, match="no se encontró .*no_esta.png"):
        componer_plano(p, entorno / "p.pdf")
    assert not (entorno / "p.pdf").exists()
