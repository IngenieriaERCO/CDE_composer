"""Datos del rótulo para el editor (subfase 4.3a): catálogo de notas por grupos, símbolos en
PNG, tabla de anchos, definición del rótulo, formato de fecha y que las firmas nunca se
incrusten. Todo sintético."""

import base64
import json

import pymupdf
import pytest

from componedor.cli import main
from componedor.datos_editor import construir_datos_editor, preparar_editor
from componedor.datos_rotulo_editor import (
    catalogo_notas,
    definicion_editor,
    simbolos_editor,
    tabla_anchos,
)
from componedor.editor_html import datos_incrustados, generar_editor
from componedor.formato import cargar_formato
from componedor.fuente import cargar_fuente
from componedor.rotulo_formato import RotuloFormatoInvalido, leer_definicion_rotulo
from componedor.simbolos import extraer_simbolos
from conftest import (
    ARIAL,
    RUTA_A1,
    crear_paquete_real,
    crear_plano_con_leyenda,
    crear_plantilla_sintetica,
    escribir_formato,
    requiere_arial,
    rotulo_a1,
)

ZONA = (672.4, 12.7, 828.3, 581.3)


def _txt(ruta, texto, codificacion="utf-8"):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(texto.encode(codificacion))


@pytest.fixture
def notas(tmp_path):
    raiz = tmp_path / "notas"
    _txt(raiz / "general.txt", "LAS COTAS ESTÁN EN METROS.\n")
    _txt(raiz / "vias" / "pavimentos.txt", "# vías\nPAVIMENTO FLEXIBLE:\n- BASE GRANULAR.\n"
                                           "- CARPETA ASFÁLTICA.\n3. SUBRASANTE COMPACTADA.\n")
    _txt(raiz / "vias" / "andenes.txt", "ANDENES EN CONCRETO.\n")
    _txt(raiz / "hidraulica" / "drenaje.txt", "CUNETAS EN CONCRETO.\n")
    _txt(raiz / "mov_tierras" / "cortes" / "taludes.txt", "TALUDES 1H:1V.\n")
    _txt(raiz / "estructuras" / "ansi.txt", "DISEÑO.\n", codificacion="cp1252")
    _txt(raiz / "cerramientos" / "mal.txt", "- VIÑETA SUELTA.\nNOTA.\n")
    (raiz / "vacia").mkdir()
    return raiz


# --- catálogo de notas -----------------------------------------------------------------------

def test_catalogo_por_grupos_recursivo(notas):
    c = catalogo_notas(notas)
    assert [g["titulo"] for g in c["grupos"]] == [
        "General", "cerramientos", "estructuras", "hidraulica", "mov_tierras/cortes", "vias"]
    assert c["avisos"] == []
    general, cerramientos, estructuras, _, _, vias = c["grupos"]
    assert [a["archivo"] for a in general["archivos"]] == ["general.txt"]
    assert [a["archivo"] for a in vias["archivos"]] == ["vias/andenes.txt", "vias/pavimentos.txt"]
    pav = vias["archivos"][1]
    assert pav["notas"] == [
        {"texto": "PAVIMENTO FLEXIBLE:", "vinetas": ["BASE GRANULAR.", "CARPETA ASFÁLTICA."],
         "origen": "pavimentos.txt, línea 2"},
        {"texto": "SUBRASANTE COMPACTADA.", "vinetas": [], "origen": "pavimentos.txt, línea 5"}]
    assert "traía su propio número «3.»" in pav["avisos"][0] and pav["problemas"] == []
    # Los mismos problemas de lectura que en componer, por archivo:
    assert "no está en UTF-8" in estructuras["archivos"][0]["problemas"][0]
    assert "es una viñeta" in cerramientos["archivos"][0]["problemas"][0]
    assert cerramientos["archivos"][0]["notas"][0]["texto"] == "NOTA."


def test_catalogo_de_carpeta_vacia_o_inexistente(tmp_path):
    (tmp_path / "vacia").mkdir()
    assert catalogo_notas(tmp_path / "vacia")["avisos"] == [
        f"la carpeta de notas '{tmp_path / 'vacia'}' no tiene archivos .txt"]
    assert catalogo_notas(tmp_path / "no")["avisos"] == [
        f"no se encontró la carpeta de notas '{tmp_path / 'no'}'"]


# --- tabla de anchos y definición ------------------------------------------------------------

@requiere_arial
def test_tabla_de_anchos_mide_igual_que_python():
    fuente = cargar_fuente(ARIAL)
    tabla = tabla_anchos(fuente)
    assert tabla["nombre"].startswith("Arial")
    assert tabla["altura_mayusculas"] == pytest.approx(1467 / 2048)
    for c in "ñÑáéíóúÁÉÍÓÚü°±²–—•…":
        assert c in tabla["anchos_em"], c
    for texto in ["VÍA SUÁREZ – LA GLORIA", "ERCO-PSF-CIV-PL-0001", "Diseñó: Ángela ±0,5 °C"]:
        tam = fuente.tamano_pt(2.0)
        suma = sum(tabla["anchos_em"][c] for c in texto) * tam * 25.4 / 72
        assert suma == pytest.approx(fuente.ancho_mm(texto, 2.0), abs=1e-6)


def test_definicion_del_rotulo_para_el_editor():
    d = definicion_editor(cargar_formato(RUTA_A1, usar_plantilla=False).rotulo)
    assert d["formato_fecha"] == "dd/mm/aa" and d["relleno_mm"] == 0.6
    c = d["campos"]
    assert c["titulo"]["tipo"] == "texto" and c["titulo"]["lineas_max"] == 3
    assert c["escala"]["calculado"] == "escala_comun"
    assert c["notas"]["tipo"] == "notas" and c["notas"]["separacion_notas"] == 0.5
    assert c["convenciones"]["capacidad"] == 24 and len(c["convenciones"]["simbolos"]) == 24
    firma = next(col for col in c["firmas"]["columnas"] if col["clave"] == "firma")
    assert firma["acepta_imagen"] is True and firma["alto_max_mm"] == 5.0
    assert [f["clave"] for f in c["revisiones"]["filas"]] == ["0", "C", "B", "A"]
    assert c["revisiones"]["orden"] == ["A", "B", "C", "0"]
    json.dumps(d)  # todo es JSON


@pytest.mark.parametrize("formato, valido", [
    ("dd/mm/aa", True), ("aaaa-mm-dd", True), ("mm.dd.aaaa", True),
    ("dd/mm/dd", False), ("dd/mm-aa", False), ("dd/mm", False), ("d/m/a", False), (3, False),
])
def test_formato_de_fecha(formato, valido):
    datos = rotulo_a1(formato_fecha=formato)
    if valido:
        assert leer_definicion_rotulo(datos, ZONA).formato_fecha == formato
    else:
        with pytest.raises(RotuloFormatoInvalido, match="rotulo.formato_fecha: se esperaba día, "
                                                         "mes y año"):
            leer_definicion_rotulo(datos, ZONA)


# --- símbolos ---------------------------------------------------------------------------------

def _formato_con_biblioteca(tmp_path, opacidad_corte=None):
    rotulo = rotulo_a1(fuente={"archivo": str(ARIAL)},
                       carpeta_firmas=[str(tmp_path / "firmas")])
    rotulo["campos"]["convenciones"]["biblioteca"] = str(tmp_path / "simbolos" / "indice.json")
    plantilla = crear_plantilla_sintetica(tmp_path / "rotulo.pdf")
    ruta = escribir_formato(tmp_path / "formato.json", plantilla=plantilla, rotulo=rotulo)
    plano = crear_plano_con_leyenda(tmp_path / "leyenda.pdf", {1: "relleno", 2: "malla"})
    (tmp_path / "simbolos").mkdir()
    (tmp_path / "simbolos" / "indice.json").write_text(json.dumps({"version": 1, "simbolos": [
        {"id": "corte", "descripcion": "CORTE", "casilla_origen": 1,
         **({"opacidad": opacidad_corte} if opacidad_corte else {})},
        {"id": "panel", "descripcion": "PANEL", "casilla_origen": 2}]}), encoding="utf-8")
    extraer_simbolos(plano, cargar_formato(ruta, usar_plantilla=False),
                     tmp_path / "simbolos" / "indice.json")
    return ruta


def test_simbolos_en_png_transparente_con_su_opacidad(tmp_path):
    ruta = _formato_con_biblioteca(tmp_path, opacidad_corte=0.5)
    salida = tmp_path / "editor"
    simbolos, avisos = simbolos_editor(cargar_formato(ruta, usar_plantilla=False).rotulo, salida)
    assert avisos == [] and [s["id"] for s in simbolos] == ["corte", "panel"]
    corte, panel = simbolos
    assert corte["opacidad"] == 0.5 and corte["descripcion"] == "CORTE"
    pix = pymupdf.Pixmap(str(salida / corte["imagen"]["archivo"]))
    ancho, alto = corte["tamano_dibujo_mm"]
    assert pix.alpha == 1  # transparente
    assert (pix.width, pix.height) == (corte["imagen"]["ancho_px"], corte["imagen"]["alto_px"])
    assert pix.width == pytest.approx((ancho + 1.0) * 20, abs=2)  # 20 px/mm (con su margen)
    # Con opacidad 0,5 ningún píxel pasa de ~50 %; el panel (opacidad 1) sí.
    alfa_corte = max(pix.samples[3::4])
    opaco = pymupdf.Pixmap(str(salida / panel["imagen"]["archivo"]))
    assert alfa_corte <= 130 and max(opaco.samples[3::4]) > 200


def test_sin_biblioteca_lista_vacia_y_aviso(tmp_path):
    rotulo = rotulo_a1(fuente={"archivo": str(ARIAL)})
    rotulo["campos"]["convenciones"]["biblioteca"] = str(tmp_path / "no" / "indice.json")
    ruta = escribir_formato(tmp_path / "formato.json", rotulo=rotulo)
    simbolos, avisos = simbolos_editor(cargar_formato(ruta).rotulo, tmp_path / "editor")
    assert simbolos == [] and "extraer-simbolos" in avisos[0]


# --- datos del editor y editor.html -----------------------------------------------------------

@requiere_arial
def test_editor_con_notas_simbolos_y_sin_firmas(tmp_path, notas, capsys):
    ruta = _formato_con_biblioteca(tmp_path)
    crear_paquete_real(tmp_path / "input", "a")
    # Una firma (sintética) en la carpeta de firmas del formato: NO debe llegar al editor.
    firma = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 60, 20), True)
    firma.set_rect(firma.irect, (10, 20, 120, 255))
    (tmp_path / "firmas" / "Persona Prueba").mkdir(parents=True)
    firma.save(tmp_path / "firmas" / "Persona Prueba" / "firma.png")
    bytes_firma = (tmp_path / "firmas" / "Persona Prueba" / "firma.png").read_bytes()

    assert main(["editor", str(tmp_path / "input"), "--formato", str(ruta), "--salida",
                 str(tmp_path / "editor"), "--notas", str(notas)]) == 0
    out = capsys.readouterr().out
    # 7 notas en 7 archivos (ansi.txt no aporta notas) y 6 grupos (la carpeta «vacia» no cuenta).
    assert "KB)" in out and "Rótulo: 7 nota(s) típica(s) (2 viñeta(s)) en 7 archivo(s) y 6 " in out
    assert "  - Problema: estructuras/ansi.txt: el archivo" in out
    assert "Firmas en imagen: no se incrustan." in out

    html = (tmp_path / "editor" / "editor.html").read_text(encoding="utf-8")
    datos = datos_incrustados(html)
    rotulo = datos["rotulo"]
    assert rotulo["definicion"]["formato_fecha"] == "dd/mm/aa"
    assert rotulo["fuente"]["anchos_em"]["Ñ"] > 0
    assert len(rotulo["notas"]["grupos"]) == 6
    assert [s["id"] for s in rotulo["simbolos"]] == ["corte", "panel"]
    assert all(s["imagen"]["data_url"].startswith("data:image/png;base64,")
               for s in rotulo["simbolos"])
    # Las firmas NUNCA se incrustan: ni la imagen ni la carpeta.
    assert base64.b64encode(bytes_firma).decode("ascii") not in html
    assert "Persona Prueba" not in html and "carpeta_firmas" not in html
    assert "raiz.EditorRotulo = api" in html  # el modelo del rótulo está incrustado


def test_formato_sin_rotulo_no_trae_datos_de_rotulo(tmp_path):
    escribir_formato(tmp_path / "formato.json")
    crear_paquete_real(tmp_path / "input", "a")
    datos, _ = construir_datos_editor(tmp_path / "input", tmp_path / "formato.json",
                                      tmp_path / "editor", carpeta_notas=tmp_path / "x")
    assert datos["rotulo"] is None
    datos = preparar_editor(tmp_path / "input", tmp_path / "formato.json", tmp_path / "editor")
    assert datos["rotulo"] is None and not (tmp_path / "editor" / "simbolos").exists()
    ruta = generar_editor(tmp_path / "input", tmp_path / "formato.json", tmp_path / "editor",
                          sobrescribir=True)
    assert datos_incrustados(ruta.read_text(encoding="utf-8"))["rotulo"] is None
