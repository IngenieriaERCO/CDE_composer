"""`componer` con rótulo, etiquetas de escala y rosa movible (subfase 4.1).

Plantilla sintética con una «rosa» (cuadro, diagonal y la letra N) en X 612..652, Y 51..91,
la sección "rotulo" de A1_ERCO.json (campos medidos del rótulo v2) y Arial. Paquete sintético:
página 260 x 120 mm, dibujo X +37,3..+237,3, Y +21,3..+101,3, escala 1:50.
"""

import json

import pymupdf
import pytest

from componedor.cli import main
from componedor.componer import PlanoNoComponible, componer_plano
from componedor.plano import leer_plano
from componedor.transformaciones import rect_papel_a_pdf
from conftest import (
    ARIAL,
    crear_paquete_real,
    crear_plantilla_sintetica,
    escribir_formato,
    requiere_arial,
    rotulo_a1,
)

pytestmark = requiere_arial
ROSA = (612.0, 51.0, 652.0, 91.0)


@pytest.fixture
def entorno(tmp_path):
    plantilla = crear_plantilla_sintetica(tmp_path / "rotulo.pdf", elementos_mm=[ROSA],
                                          letra_en_elementos="N")
    escribir_formato(tmp_path / "formato.json", plantilla=plantilla,
                     elementos_plantilla=[{"nombre": "rosa_vientos", "rect_mm": list(ROSA)}],
                     rotulo=rotulo_a1(fuente={"archivo": str(ARIAL)}))
    crear_paquete_real(tmp_path / "input", "a")  # con fondo blanco (paquete antiguo)
    crear_paquete_real(tmp_path / "input", "s", sin_fondo=True)
    return tmp_path


def _plano(carpeta, detalles, version=2, **extra):
    datos = {"version": version, "formato": "formato.json", "detalles": [
        {"id": i, "manifiesto": f"input/{p}.manifest.json", "posicion_mm": list(pos), **op}
        for i, p, pos, *resto in detalles for op in [resto[0] if resto else {}]], **extra}
    ruta = carpeta / "plano.json"
    ruta.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    return leer_plano(ruta)


def _texto_pdf(ruta):
    with pymupdf.open(ruta) as doc:
        return doc[0].get_text()


def _trazos_en(ruta, rect_mm):
    caja = rect_papel_a_pdf((rect_mm[0] - 1, rect_mm[1] - 1, rect_mm[2] + 1, rect_mm[3] + 1), 594.0)
    with pymupdf.open(ruta) as doc:
        return sum(caja.contains(d["rect"]) for d in doc[0].get_drawings())


ROTULO = {
    "titulo": "PLANTA GENERAL Y PERFIL",
    "este": "4.876.543,21", "norte": "2.012.345,67",
    "revisiones": [{"ver": "A", "fecha": "2026-10-20", "descripcion": "REVISIÓN INTERNA"},
                   {"ver": "0", "fecha": "2026-11-06", "descripcion": "EMISIÓN"}],
    "firmas": {"dibujo": {"nombre": "LUIS Á. NÚÑEZ", "fecha": "2026-11-06"}},
    "hoja": 1, "de": 2, "no_plano": "ERCO-PSF-CIV-PL-0001",
}


def test_rotulo_completo_y_etiquetas(entorno):
    plano = _plano(entorno, [("d1", "a", (40, 300)), ("d2", "s", (40, 100))], rotulo=ROTULO)
    r = componer_plano(plano, entorno / "p.pdf")
    assert r.advertencias == []
    assert r.rotulo["escala"] == "1:50" and r.rotulo["rev"] == "A"  # orden 0 < A
    texto = _texto_pdf(entorno / "p.pdf")
    for esperado in ["PLANTA GENERAL Y PERFIL", "4.876.543,21", "REVISIÓN INTERNA", "EMISIÓN",
                     "LUIS Á. NÚÑEZ", "ERCO-PSF-CIV-PL-0001", "DEFINIR", "1:50", "ESC: 1:50"]:
        assert esperado in texto, esperado
    assert texto.count("ESC: 1:50") == 2 and r.etiquetas == ["d1", "d2"]
    assert not list(entorno.glob(".*.componiendo.pdf"))


def test_rev_es_la_de_mayor_orden(entorno):
    rotulo = dict(ROTULO, revisiones=[{"ver": "B", "fecha": "1"}, {"ver": "0", "fecha": "2"},
                                      {"ver": "A", "fecha": "3"}])
    r = componer_plano(_plano(entorno, [("d1", "a", (40, 300))], rotulo=rotulo), entorno / "p.pdf")
    assert r.rotulo["rev"] == "B"


def test_plano_version_1_lleva_defectos_calculados_y_etiquetas(entorno):
    r = componer_plano(_plano(entorno, [("d1", "a", (40, 300))], version=1), entorno / "p.pdf")
    assert r.rotulo["localizacion_escala"] == "DEFINIR" and r.rotulo["escala"] == "1:50"
    assert r.rotulo["rev"] == "" and r.etiquetas == ["d1"]
    assert r.rosa is not None and r.rosa.destino == ROSA  # en su sitio


def test_texto_que_no_cabe_error_claro_y_sin_pdf(entorno):
    rotulo = dict(ROTULO, no_plano="ERCO-PSF-CIV-PL-0001-" * 8)
    with pytest.raises(PlanoNoComponible) as e:
        componer_plano(_plano(entorno, [("d1", "a", (40, 300))], rotulo=rotulo), entorno / "p.pdf")
    mensaje = str(e.value)
    assert mensaje.startswith("No se compone el plano. El rótulo tiene 1 problema:\n- campo "
                              "'no_plano': «ERCO-PSF-CIV-PL-0001-ERCO")
    assert "y la celda permite 114.9 mm (altura 2.5 mm)" in mensaje
    assert not (entorno / "p.pdf").exists() and not list(entorno.glob(".*.componiendo.pdf"))


def test_cada_texto_dentro_de_su_celda_en_el_pdf(entorno, monkeypatch):
    # Con las celdas reales, todo pasa; si la celda esperada de 'no_plano' termina 0,3 mm
    # antes del final de su texto, la verificación del PDF guardado lo detecta: error claro
    # y no queda PDF (ni temporal).
    from dataclasses import replace

    from componedor import componer as modulo
    plano = _plano(entorno, [("d1", "a", (40, 300))], rotulo=ROTULO)
    r = componer_plano(plano, entorno / "ok.pdf")
    assert r.rotulo["no_plano"] == "ERCO-PSF-CIV-PL-0001"

    original = modulo.preparar_rotulo

    def con_celda_corta(*args, **kwargs):
        preparado = original(*args, **kwargs)
        preparado.textos = [
            replace(t, celda_mm=(t.celda_mm[0], t.celda_mm[1],
                                 t.lineas[0].base_mm[0] + t.lineas[0].ancho_mm - 0.3,
                                 t.celda_mm[3])) if t.ruta == "no_plano" else t
            for t in preparado.textos]
        return preparado

    monkeypatch.setattr(modulo, "preparar_rotulo", con_celda_corta)
    with pytest.raises(PlanoNoComponible) as e:
        componer_plano(plano, entorno / "p.pdf")
    mensaje = str(e.value)
    assert mensaje.startswith("La verificación del PDF compuesto falló; no se generó el plano:")
    assert "- texto 'no_plano': «ERCO-PSF-CIV-PL-0001» se sale de su celda X 690.90 a" in mensaje
    assert "mm por la derecha (medido en el PDF:" in mensaje
    assert not (entorno / "p.pdf").exists() and not list(entorno.glob(".*.componiendo.pdf"))


def test_la_etiqueta_esc_lleva_su_caja_como_celda(entorno, monkeypatch):
    from componedor import componer as modulo
    escritos = []
    original = modulo.escribir_textos

    def espia(page, textos, fuente, alto):
        escritos.extend(textos)
        return original(page, textos, fuente, alto)

    monkeypatch.setattr(modulo, "escribir_textos", espia)
    componer_plano(_plano(entorno, [("d1", "s", (40, 300))]), entorno / "p.pdf")
    (etiqueta,) = [t for t in escritos if t.ruta == "etiqueta_escala.d1"]
    x0, y0, x1, y1 = etiqueta.celda_mm
    base = etiqueta.lineas[0].base_mm
    assert x0 == pytest.approx(base[0]) and x1 == pytest.approx(base[0] + etiqueta.lineas[0].ancho_mm)
    assert y0 < base[1] < base[1] + 2.5 < y1  # con descenso y ascenso de la fuente


def test_etiqueta_que_no_cabe_es_advertencia_y_se_puede_quitar(entorno):
    # Tres detalles apilados sin fondo: dibujos Y 47,3..127,3 / 131,3..211,3 / 214,3..294,3.
    # La etiqueta de d1 no cabe debajo (pisa el dibujo de d0) ni encima (pisa el de d2).
    detalles = [("d0", "s", (40, 26)), ("d1", "s", (40, 110)), ("d2", "s", (40, 193))]
    r = componer_plano(_plano(entorno, detalles), entorno / "p.pdf")
    assert r.etiquetas == ["d0", "d2"]
    assert r.advertencias == [
        "Advertencia: no se dibujó la etiqueta «ESC: 1:50» del detalle 'd1': no cabe a 3 mm de "
        "su dibujo (debajo: se monta sobre el dibujo de 'd0'; encima: se monta sobre el dibujo "
        "de 'd2'). Mueva el detalle o ponga \"etiqueta_escala\": false."]
    detalles[1] = ("d1", "s", (40, 110), {"etiqueta_escala": False})
    r = componer_plano(_plano(entorno, detalles), entorno / "p.pdf", sobrescribir=True)
    assert r.advertencias == [] and r.etiquetas == ["d0", "d2"]


# --- rosa de los vientos -----------------------------------------------------------------------

def test_rosa_movida_advertencias_con_su_posicion_nueva(entorno):
    # d1 en X 400..660, Y 40..160: su dibujo (X 437,3..637,3, Y 61,3..141,3) cubre el sitio
    # ORIGINAL de la rosa; la rosa se movió a X 100..140, Y 450..490, debajo del dibujo de d2.
    detalles = [("d1", "s", (400, 40)), ("d2", "s", (40, 420))]
    plano = _plano(entorno, detalles, rosa_vientos={"posicion_mm": [100, 450]})
    r = componer_plano(plano, entorno / "p.pdf")
    assert r.advertencias == [
        "ADVERTENCIA MUY FUERTE: el dibujo 'd2' se monta sobre 'rosa_vientos' de la plantilla "
        "(40.0 x 40.0 mm): sus líneas quedarán encima."]
    assert r.rosa.destino == (100.0, 450.0, 140.0, 490.0)
    assert _trazos_en(entorno / "p.pdf", ROSA) == 0  # el sitio viejo, vacío (d1 no tiene trazos ahí)
    with pymupdf.open(entorno / "p.pdf") as doc:
        assert "N" in [w[4] for w in doc[0].get_text("words")]


def test_rosa_oculta_no_avisa_y_no_se_dibuja(entorno):
    plano = _plano(entorno, [("d1", "a", (400, 40))], rosa_vientos={"visible": False})
    r = componer_plano(plano, entorno / "p.pdf")
    assert r.advertencias == [] and r.rosa.destino is None
    assert "N" not in [w for w in _texto_pdf(entorno / "p.pdf").split()]


def test_rosa_en_su_sitio_avisa_como_siempre(entorno):
    r = componer_plano(_plano(entorno, [("d1", "a", (400, 40))]), entorno / "p.pdf")
    assert r.advertencias == [
        "ADVERTENCIA MUY FUERTE: el dibujo 'd1' se monta sobre 'rosa_vientos' de la plantilla "
        "(25.3 x 29.7 mm); además su fondo blanco lo tapa."]


def test_rosa_fuera_del_area_es_error(entorno):
    plano = _plano(entorno, [("d1", "a", (40, 300))], rosa_vientos={"posicion_mm": [640, 60]})
    with pytest.raises(PlanoNoComponible, match=r"rosa_vientos.posicion_mm: La rosa de los vientos "
                                                r"\(40\.0 x 40\.0 mm\) no cabe en la zona "
                                                r"'area_dibujo' .*se pasa 17\.6 mm por la derecha\. "
                                                r"La rosa debe quedar completa"):
        componer_plano(plano, entorno / "p.pdf")
    assert not (entorno / "p.pdf").exists()


def test_rosa_en_un_formato_sin_rosa_es_error(entorno):
    escribir_formato(entorno / "formato.json", plantilla=entorno / "rotulo.pdf")
    plano = _plano(entorno, [("d1", "a", (40, 300))], rosa_vientos={"visible": False})
    with pytest.raises(PlanoNoComponible, match="rosa_vientos: el formato no declara el elemento"):
        componer_plano(plano, entorno / "p.pdf")


def test_cli_resume_rosa_y_rotulo(entorno, capsys):
    _plano(entorno, [("d1", "a", (40, 300))], rotulo=ROTULO,
           rosa_vientos={"posicion_mm": [100, 450]})
    assert main(["componer", str(entorno / "plano.json"), "--salida", str(entorno / "p.pdf")]) == 0
    out = capsys.readouterr().out
    assert "Rosa de los vientos: movida: esquina inferior izquierda (100.00, 450.00) mm." in out
    assert "ESCALA 1:50, REV. A." in out
    assert "Etiquetas \"ESC: 1:N\": 1 (d1)." in out
    assert "cada texto está en su sitio (±0,1 mm) y dentro de su celda." in out
