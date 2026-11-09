"""Firmas en imagen en la celda FIRMA (subfase 4.2d), con PNG SINTÉTICOS generados en tmp
(nunca firmas reales)."""

import json
import random

import pymupdf
import pytest

from componedor import componer as modulo_componer
from componedor.cli import main
from componedor.componer import PlanoNoComponible, componer_plano
from componedor.firmas import colocar_firma
from componedor.formato import cargar_formato
from componedor.plano import leer_plano
from componedor.rotulo_formato import RotuloFormatoInvalido, leer_definicion_rotulo
from componedor.transformaciones import rect_pdf_a_papel
from conftest import (
    ARIAL,
    RUTA_A1,
    crear_paquete_real,
    crear_plantilla_sintetica,
    escribir_formato,
    requiere_arial,
    rotulo_a1,
)

CELDA_DIBUJO = (757.6, 39.0, 775.8, 43.5)  # FIRMA, fila DIBUJÓ
CELDA_REVISO = (757.6, 25.4, 775.8, 34.5)  # FIRMA, fila REVISÓ (más alta)


def garabato(ruta, ancho_px=480, alto_px=160, alfa=True, semilla=1):
    """PNG de un «garabato» sintético: curvas azules sobre fondo transparente (o blanco)."""
    escala = 2
    doc = pymupdf.open()
    page = doc.new_page(width=ancho_px / escala, height=alto_px / escala)
    azar = random.Random(semilla)
    w, h = page.rect.width, page.rect.height
    for _ in range(3):
        puntos = [(azar.uniform(0.05, 0.95) * w, azar.uniform(0.1, 0.9) * h) for _ in range(4)]
        page.draw_bezier(*puntos, color=(0.05, 0.1, 0.5), width=2)
    pix = page.get_pixmap(matrix=pymupdf.Matrix(escala, escala), alpha=alfa)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    pix.save(ruta)
    return ruta


@pytest.fixture
def entorno(tmp_path):
    plantilla = crear_plantilla_sintetica(tmp_path / "rotulo.pdf")  # trae 1 imagen (el «logo»)
    rotulo = rotulo_a1(fuente={"archivo": str(ARIAL)},
                       carpeta_firmas=[str(tmp_path / "firmas"), str(tmp_path / "otras")])
    escribir_formato(tmp_path / "formato.json", plantilla=plantilla, rotulo=rotulo)
    crear_paquete_real(tmp_path / "input", "a")
    garabato(tmp_path / "firmas" / "persona_a.png", semilla=1)
    garabato(tmp_path / "firmas" / "persona_b.png", semilla=2)
    return tmp_path


def _plano(carpeta, firmas):
    datos = {"version": 2, "formato": "formato.json",
             "detalles": [{"id": "d1", "manifiesto": "input/a.manifest.json", "posicion_mm": [40, 300]}],
             "rotulo": {"firmas": firmas}}
    (carpeta / "plano.json").write_text(json.dumps(datos), encoding="utf-8")
    return leer_plano(carpeta / "plano.json")


def _imagenes(ruta):
    with pymupdf.open(ruta) as doc:
        page = doc[0]
        mascaras = {i[0]: i[1] for i in page.get_images(full=True)}
        return [(rect_pdf_a_papel(pymupdf.Rect(i["bbox"]), 594.0), mascaras.get(i["xref"], 0))
                for i in page.get_image_info(xrefs=True)]


# --- formato ---------------------------------------------------------------------------------

def test_a1_erco_acepta_imagen_solo_en_la_columna_firma():
    r = cargar_formato(RUTA_A1, usar_plantilla=False).rotulo
    raiz = RUTA_A1.parent.parent
    assert r.carpetas_firmas == (raiz / "firmas", raiz / "data" / "firmas")
    firmas = r.campos["firmas"]
    assert all(c.acepta_imagen == (col == "firma") for (_, col), c in firmas.celdas.items())
    assert not any(c.acepta_imagen for c in r.campos["revisiones"].celdas.values())


def test_esquema_de_imagen_en_el_formato():
    zona = (672.4, 12.7, 828.3, 581.3)
    sin_carpeta = rotulo_a1()
    sin_carpeta.pop("carpeta_firmas")
    with pytest.raises(RotuloFormatoInvalido, match="hay celdas que aceptan imagen .* y falta la "
                                                     "carpeta donde buscar las firmas"):
        leer_definicion_rotulo(sin_carpeta, zona)
    malo = rotulo_a1()
    malo["campos"]["firmas"]["columnas"]["firma"]["acepta_imagen"] = "sí"
    with pytest.raises(RotuloFormatoInvalido, match=r"firma.acepta_imagen: se esperaba true o false"):
        leer_definicion_rotulo(malo, zona)
    with pytest.raises(RotuloFormatoInvalido, match="carpeta_firmas: se esperaba una ruta o una lista"):
        leer_definicion_rotulo(rotulo_a1(carpeta_firmas=[]), zona)


# --- colocación --------------------------------------------------------------------------------

def test_colocacion_proporcional_centrada_y_nunca_mayor_que_300_ppp():
    # Chica (60 x 20 px = 5,08 x 1,69 mm a 300 ppp): queda de ese tamaño, centrada.
    caja, f = colocar_firma(60, 20, CELDA_DIBUJO, 0.6)
    assert f == 1.0
    assert caja == pytest.approx((766.7 - 2.54, 41.25 - 0.8467, 766.7 + 2.54, 41.25 + 0.8467),
                                 abs=1e-3)
    # Grande (600 x 200 px = 50,8 x 16,9 mm): se reduce al espacio útil (17,0 x 3,3), proporcional.
    caja, f = colocar_firma(600, 200, CELDA_DIBUJO, 0.6)
    assert caja[3] - caja[1] == pytest.approx(3.3)
    assert (caja[2] - caja[0]) / (caja[3] - caja[1]) == pytest.approx(3.0)
    assert f == pytest.approx(3.3 / (200 / 300 * 25.4))


# --- componer ----------------------------------------------------------------------------------

@requiere_arial
def test_firmas_en_imagen_con_mascara_en_su_celda(entorno, capsys):
    _plano(entorno, {"dibujo": {"nombre": "PERSONA A", "firma": {"imagen": "persona_a"}},
                     "reviso": {"nombre": "PERSONA B", "firma": {"imagen": "persona_b"}},
                     "diseno": {"firma": "P.C."}})  # texto, como antes
    assert main(["componer", str(entorno / "plano.json"), "--salida", str(entorno / "p.pdf")]) == 0
    out = capsys.readouterr().out
    assert "Firmas en imagen: 2 (firmas.dibujo.firma: persona_a" in out
    assert "cada firma en imagen está en su celda (±0,1 mm), con su máscara" in out
    imagenes = _imagenes(entorno / "p.pdf")
    assert len(imagenes) == 3  # el logo de la plantilla + 2 firmas
    firmas = [(r, m) for r, m in imagenes if r[3] < 50]  # filas de firmas (el logo está más arriba)
    assert len(firmas) == 2 and all(m for _, m in firmas)  # con máscara de transparencia
    for (rect, _), celda in zip(sorted(firmas, key=lambda t: -t[0][1]), (CELDA_DIBUJO, CELDA_REVISO)):
        assert celda[0] <= rect[0] and rect[2] <= celda[2] and celda[1] <= rect[1] and rect[3] <= celda[3]
    with pymupdf.open(entorno / "p.pdf") as doc:
        assert "P.C." in doc[0].get_text()


@requiere_arial
def test_firma_sin_alfa_es_advertencia_y_se_verifica_igual(entorno):
    garabato(entorno / "firmas" / "opaca.png", alfa=False)
    r = componer_plano(_plano(entorno, {"aprobo": {"firma": {"imagen": "opaca"}}}), entorno / "p.pdf")
    assert any("la firma 'opaca' (opaca.png) no tiene canal alfa" in a for a in r.advertencias)
    assert r.firmas[0].alfa is False
    firma = [m for rect, m in _imagenes(entorno / "p.pdf") if rect[3] < 50]
    assert firma == [0]  # sin máscara


@requiere_arial
def test_todos_los_problemas_juntos(entorno):
    garabato(entorno / "firmas" / "ancha.png", ancho_px=700, alto_px=100)
    ruido = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 600, 200), True)
    azar = random.Random(3)
    ruido.set_rect(ruido.irect, (0, 0, 0, 255))
    for x in range(0, 600, 1):
        for y in range(0, 200, 2):
            ruido.set_pixel(x, y, (azar.randrange(256), azar.randrange(256), azar.randrange(256), 255))
    ruido.save(entorno / "firmas" / "pesada.png")
    (entorno / "firmas" / "jpg.png").write_bytes(  # un JPEG con nombre .png
        pymupdf.Pixmap(pymupdf.Pixmap(str(entorno / "firmas" / "persona_a.png")), 0).tobytes("jpeg"))
    garabato(entorno / "otras" / "persona_a.png")  # repetida en dos carpetas
    firmas = {
        "dibujo": {"firma": {"imagen": "no_existe"}, "matricula": {"imagen": "persona_b"}},
        "diseno": {"firma": {"imagen": "ancha", "escala": 2}},
        "reviso": {"firma": {"imagen": "pesada"}},
        "aprobo": {"firma": {"imagen": "jpg"}, "fecha": {"imagen": "../../secreto"}},
    }
    with pytest.raises(PlanoNoComponible) as e:
        componer_plano(_plano(entorno, firmas), entorno / "p.pdf")
    m = str(e.value)
    for esperado in [
        "rotulo.firmas.dibujo.firma.imagen: no se encontró la firma 'no_existe' (se buscó "
        "no_existe.png en: ",
        "rotulo.firmas.dibujo.matricula: la celda 'firmas.dibujo.matricula' no acepta imagen",
        "rotulo.firmas.diseno.firma.escala: campo no reconocido (campos válidos: imagen)",
        "rotulo.firmas.reviso.firma.imagen: '",
        "pesada.png' pesa ",
        "KB y el máximo es 100 KB",
        "rotulo.firmas.aprobo.firma.imagen: '",
        "jpg.png' no es un PNG",
        "rotulo.firmas.aprobo.fecha: la celda 'firmas.aprobo.fecha' no acepta imagen",
    ]:
        assert esperado in m, esperado
    assert not (entorno / "p.pdf").exists()
    # La ancha (700 x 100 px) y la repetida, por separado:
    with pytest.raises(PlanoNoComponible, match=r"mide 700 x 100 px y el máximo es 600 x 200 px"):
        componer_plano(_plano(entorno, {"diseno": {"firma": {"imagen": "ancha"}}}), entorno / "p.pdf")
    with pytest.raises(PlanoNoComponible, match=r"la firma 'persona_a' está en más de una carpeta"):
        componer_plano(_plano(entorno, {"dibujo": {"firma": {"imagen": "persona_a"}}}),
                       entorno / "p.pdf")
    with pytest.raises(PlanoNoComponible, match=r"imagen: se esperaba el id de la firma"):
        componer_plano(_plano(entorno, {"dibujo": {"firma": {"imagen": "../x"}}}), entorno / "p.pdf")


# --- fallas forzadas de la verificación ----------------------------------------------------------

def _forzar(monkeypatch, cambio):
    original = modulo_componer.insertar_firmas

    def insertar(page, firmas, alto):
        cambio(page, firmas, alto, original)

    monkeypatch.setattr(modulo_componer, "insertar_firmas", insertar)


@requiere_arial
@pytest.mark.parametrize("caso, esperado", [
    ("corrida", "se esperaba una imagen en X "),
    ("otra_imagen", "la imagen del PDF no es la del archivo leído (persona_a.png, SHA-256 "),
    ("sin_mascara", "la imagen no tiene máscara de transparencia (SMask)"),
    ("dos_veces", "imágenes y debía tener 2 (hoja base 1 + 1 firma(s)): no se debe rasterizar"),
])
def test_fallas_forzadas_sin_pdf(entorno, monkeypatch, caso, esperado):
    from dataclasses import replace

    def cambio(page, firmas, alto, original):
        f = firmas[0]
        if caso == "corrida":
            original(page, [replace(f, destino=(f.destino[0] + 0.3, f.destino[1],
                                                f.destino[2] + 0.3, f.destino[3]))], alto)
        elif caso == "otra_imagen":
            otra = (entorno / "firmas" / "persona_b.png").read_bytes()
            original(page, [replace(f, datos=otra)], alto)
        elif caso == "sin_mascara":
            opaca = pymupdf.Pixmap(pymupdf.Pixmap(f.datos), 0).tobytes("png")
            original(page, [replace(f, datos=opaca)], alto)
        else:
            original(page, firmas + firmas, alto)

    _forzar(monkeypatch, cambio)
    with pytest.raises(PlanoNoComponible) as e:
        componer_plano(_plano(entorno, {"dibujo": {"firma": {"imagen": "persona_a"}}}),
                       entorno / "p.pdf")
    assert str(e.value).startswith("La verificación del PDF compuesto falló; no se generó el plano:")
    assert esperado in str(e.value)
    assert not (entorno / "p.pdf").exists() and not list(entorno.glob(".*.componiendo.pdf"))
