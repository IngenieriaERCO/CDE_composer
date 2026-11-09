"""Firmas en imagen en la celda FIRMA (subfase 4.2d), con PNG SINTÉTICOS generados en tmp
(nunca firmas reales)."""

import json
import random

import pymupdf
import pytest

from componedor import componer as modulo_componer
from componedor.cli import main
from componedor.componer import PlanoNoComponible, componer_plano
from componedor.firmas import caja_firma, colocar_firma
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
    caja = (758.2, 37.25, 775.2, 45.25)  # 17,0 x 8,0 mm
    # Chica (60 x 20 px = 5,08 x 1,69 mm a 300 ppp): queda de ese tamaño, centrada en la caja.
    rect, f = colocar_firma(60, 20, caja)
    assert f == 1.0
    assert rect == pytest.approx((766.7 - 2.54, 41.25 - 0.8467, 766.7 + 2.54, 41.25 + 0.8467),
                                 abs=1e-3)
    # Grande (600 x 200 px = 50,8 x 16,9 mm): se reduce a lo ancho (17,0 mm), proporcional.
    rect, f = colocar_firma(600, 200, caja)
    assert rect[2] - rect[0] == pytest.approx(17.0)
    assert (rect[2] - rect[0]) / (rect[3] - rect[1]) == pytest.approx(3.0)
    assert f == pytest.approx(17.0 / 50.8)


# --- caja ampliada (subfase 4.2e) -------------------------------------------------------------
# Tabla de firmas de A1 ERCO: cuerpo Y 20,9 a 43,5 (encabezado «FIRMA» encima de 43,5);
# filas DIBUJÓ 39,0–43,5, DISEÑÓ 34,5–39,0, REVISÓ 25,4–34,5, APROBÓ 20,9–25,4.

def _celdas_firma():
    return cargar_formato(RUTA_A1, usar_plantilla=False).rotulo.campos["firmas"]


def test_caja_centrada_en_su_fila_y_mas_alta_que_ella():
    celdas = _celdas_firma()
    # DISEÑÓ: fila de 4,5 mm (3,3 útiles) -> caja de alto_max_mm = 5,0, centrada en 36,75.
    caja = caja_firma(celdas.celdas[("diseno", "firma")], 0.6)
    assert celdas.celdas[("diseno", "firma")].alto_max_mm == 5.0
    assert caja == pytest.approx((758.2, 36.75 - 2.5, 775.2, 36.75 + 2.5))


def test_fila_mas_alta_que_alto_max_usa_su_propia_altura():
    # REVISÓ: fila de 9,1 mm -> 7,9 útiles > 5,0: la caja es max(5,0; 7,9) = 7,9, centrada.
    celdas = _celdas_firma()
    reviso = caja_firma(celdas.celdas[("reviso", "firma")], 0.6)
    assert reviso == pytest.approx((758.2, 29.95 - 3.95, 775.2, 29.95 + 3.95))
    assert reviso[3] - reviso[1] == pytest.approx(7.9)


def test_caja_se_corre_hacia_adentro_en_la_primera_y_la_ultima_fila():
    celdas = _celdas_firma()
    # DIBUJÓ (centro 41,25): la caja ideal llegaría a 43,75, sobre el encabezado; se corre
    # hacia abajo hasta 43,5 - 0,6 = 42,9.
    arriba = caja_firma(celdas.celdas[("dibujo", "firma")], 0.6)
    assert arriba == pytest.approx((758.2, 42.9 - 5.0, 775.2, 42.9))
    # APROBÓ (centro 23,15): bajaría a 20,65, fuera de la tabla; se corre hacia arriba desde
    # 20,9 + 0,6 = 21,5.
    abajo = caja_firma(celdas.celdas[("aprobo", "firma")], 0.6)
    assert abajo == pytest.approx((758.2, 21.5, 775.2, 21.5 + 5.0))
    # Las demás columnas no aceptan imagen ni tienen caja ampliada.
    assert celdas.celdas[("dibujo", "nombre")].alto_max_mm == 0.0


def test_alto_max_en_el_formato():
    zona = (672.4, 12.7, 828.3, 581.3)
    malo = rotulo_a1()
    malo["campos"]["firmas"]["columnas"]["nombre"]["alto_max_mm"] = 5
    with pytest.raises(RotuloFormatoInvalido, match=r"nombre.alto_max_mm: solo se usa con "
                                                     r"\"acepta_imagen\": true"):
        leer_definicion_rotulo(malo, zona)
    malo = rotulo_a1()
    malo["campos"]["firmas"]["columnas"]["firma"]["alto_max_mm"] = 0
    with pytest.raises(RotuloFormatoInvalido, match=r"firma.alto_max_mm: se esperaba un número "
                                                     r"positivo"):
        leer_definicion_rotulo(malo, zona)
    sin_valor = rotulo_a1()
    sin_valor["campos"]["firmas"]["columnas"]["firma"].pop("alto_max_mm")
    d = leer_definicion_rotulo(sin_valor, zona)
    assert d.campos["firmas"].celdas[("dibujo", "firma")].alto_max_mm == 5.0  # por defecto


# --- componer ----------------------------------------------------------------------------------

@requiere_arial
def test_firmas_en_imagen_con_mascara_en_su_celda(entorno, capsys):
    _plano(entorno, {"dibujo": {"nombre": "PERSONA A", "firma": {"imagen": "persona_a"}},
                     "reviso": {"nombre": "PERSONA B", "firma": {"imagen": "persona_b"}},
                     "diseno": {"firma": "P.C."}})  # texto, como antes
    assert main(["componer", str(entorno / "plano.json"), "--salida", str(entorno / "p.pdf")]) == 0
    out = capsys.readouterr().out
    assert "Firmas en imagen: 2 (firmas.dibujo.firma: persona_a" in out
    assert "cada firma en imagen está dentro de su caja en la columna FIRMA sin pisar el " \
           "encabezado (±0,1 mm), con su máscara" in out
    imagenes = _imagenes(entorno / "p.pdf")
    assert len(imagenes) == 3  # el logo de la plantilla + 2 firmas
    firmas = [(r, m) for r, m in imagenes if r[3] < 50]  # filas de firmas (el logo está más arriba)
    assert len(firmas) == 2 and all(m for _, m in firmas)  # con máscara de transparencia
    for rect, _ in firmas:  # dentro del ANCHO de la columna FIRMA y del cuerpo de la tabla
        assert 758.2 - 0.1 <= rect[0] and rect[2] <= 775.2 + 0.1
        assert 21.5 - 0.1 <= rect[1] and rect[3] <= 42.9 + 0.1
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
def test_firma_realista_centrada_en_su_fila_y_montaje_con_advertencia(entorno):
    garabato(entorno / "firmas" / "ancha_a.png", ancho_px=600, alto_px=200, semilla=4)
    garabato(entorno / "firmas" / "ancha_b.png", ancho_px=600, alto_px=200, semilla=5)
    # Sola en REVISÓ (caja de 17,0 x 7,9 mm): 600 x 200 px a 300 ppp = 50,8 x 16,9 mm; cabe a
    # 17,0 x 5,67 mm, centrada en su fila (29,95).
    r = componer_plano(_plano(entorno, {"reviso": {"firma": {"imagen": "ancha_a"}}}),
                       entorno / "p.pdf")
    (firma,) = r.firmas
    assert firma.destino == pytest.approx((758.2, 29.95 - 17.0 / 6, 775.2, 29.95 + 17.0 / 6),
                                          abs=1e-3)
    assert r.advertencias == []
    # DIBUJÓ y DISEÑÓ, filas vecinas de 4,5 mm (cajas de 5,0 mm): cada firma queda de 15,0 x
    # 5,0 mm (limita el alto) y se montan -> advertencia, no error.
    r = componer_plano(_plano(entorno, {"dibujo": {"firma": {"imagen": "ancha_a"}},
                                        "diseno": {"firma": {"imagen": "ancha_b"}}}),
                       entorno / "p.pdf", sobrescribir=True)
    dibujo, diseno = r.firmas
    assert dibujo.destino == pytest.approx((759.2, 37.9, 774.2, 42.9), abs=1e-3)  # corrida abajo
    assert diseno.destino == pytest.approx((759.2, 34.25, 774.2, 39.25), abs=1e-3)
    assert r.advertencias == [
        f"Advertencia: las firmas de las filas 'dibujo' y 'diseno' se montan una sobre otra "
        f"(15.0 x {diseno.destino[3] - dibujo.destino[1]:.1f} mm). Si estorba, use firmas más "
        f"bajas o baje \"alto_max_mm\" en el formato."]
    assert (entorno / "p.pdf").is_file()


@requiere_arial
def test_sin_montaje_no_hay_advertencia(entorno):
    garabato(entorno / "firmas" / "ancha_a.png", ancho_px=600, alto_px=200, semilla=4)
    garabato(entorno / "firmas" / "ancha_b.png", ancho_px=600, alto_px=200, semilla=5)
    # DIBUJÓ (Y 37,9–42,9) y REVISÓ (Y 27,1–32,8): no se cruzan.
    r = componer_plano(_plano(entorno, {"dibujo": {"firma": {"imagen": "ancha_a"}},
                                        "reviso": {"firma": {"imagen": "ancha_b"}}}),
                       entorno / "p.pdf")
    assert len(r.firmas) == 2 and r.advertencias == []


@requiere_arial
def test_falla_forzada_si_la_firma_pisa_el_encabezado(entorno, monkeypatch):
    from dataclasses import replace

    from componedor import rotulo as modulo_rotulo
    original = modulo_rotulo.pedir_firma

    def subida(*args, **kwargs):  # el cálculo «se equivoca» y la pone 3 mm más arriba
        f = original(*args, **kwargs)
        sube = lambda r: (r[0], r[1] + 3.0, r[2], r[3] + 3.0)  # noqa: E731
        return replace(f, destino=sube(f.destino), caja=sube(f.caja))

    monkeypatch.setattr(modulo_rotulo, "pedir_firma", subida)
    with pytest.raises(PlanoNoComponible, match=r"firma 'persona_a' en 'firmas.dibujo.firma': la "
                                                r"imagen .* pisa el encabezado de la tabla o se "
                                                r"sale de ella \(cuerpo: Y 20.90 a 43.50 mm\)"):
        componer_plano(_plano(entorno, {"dibujo": {"firma": {"imagen": "persona_a"}}}),
                       entorno / "p.pdf")
    assert not (entorno / "p.pdf").exists()


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
