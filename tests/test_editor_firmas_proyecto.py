"""`editor --firmas` y `editor --proyecto` (subfase 4.3b): de la carpeta de firmas solo llegan
los NOMBRES de las personas (nunca una imagen) y proyecto.json se valida y se incrusta. Firmas
sintéticas generadas en tmp."""

import base64
import json

import pymupdf
import pytest

from componedor.cli import main
from componedor.datos_editor import construir_datos_editor
from componedor.editor_html import datos_incrustados
from componedor.firmas import personas_firmas
from conftest import ARIAL, crear_paquete_real, escribir_formato, requiere_arial, rotulo_a1


def _png(ruta, color=(10, 20, 120, 255)):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 60, 20), True)
    pix.set_rect(pix.irect, color)
    pix.save(ruta)
    return ruta.read_bytes()


def test_personas_solo_nombres_validos_y_con_png(tmp_path):
    firmas = tmp_path / "firmas"
    _png(firmas / "Luis Ángel Núñez" / "firma.png")
    _png(firmas / "María Ocaña" / "azul.png")  # sin firma.png, pero con un PNG: vale
    (firmas / "Sin Imagen").mkdir()
    (firmas / "Sin Imagen" / "leame.txt").write_text("x", encoding="utf-8")
    _png(firmas / "mal.nombre" / "firma.png")
    (firmas / "suelto.png").write_bytes(b"no es carpeta")
    personas, avisos = personas_firmas(firmas)
    assert personas == ["Luis Ángel Núñez", "María Ocaña"]
    assert avisos == [
        "firmas: se omitió la carpeta 'mal.nombre' (el nombre solo admite letras, números, "
        "espacio, «_» y «-»)",
        "firmas: se omitió la carpeta 'Sin Imagen' (no tiene ningún PNG)"]


def test_personas_carpeta_inexistente_o_vacia(tmp_path):
    assert personas_firmas(tmp_path / "no") == ([], [f"firmas: no se encontró la carpeta '{tmp_path / 'no'}'"])
    (tmp_path / "vacia").mkdir()
    assert personas_firmas(tmp_path / "vacia")[1] == [
        f"firmas: la carpeta '{tmp_path / 'vacia'}' no tiene carpetas de personas"]


@pytest.fixture
def entorno(tmp_path):
    ruta = escribir_formato(tmp_path / "formato.json", rotulo=rotulo_a1(fuente={"archivo": str(ARIAL)}))
    crear_paquete_real(tmp_path / "input", "a")
    return tmp_path, ruta


@requiere_arial
def test_editor_firmas_incrusta_solo_los_nombres(entorno, capsys):
    tmp_path, formato = entorno
    imagenes = [_png(tmp_path / "firmas" / "Persona Uno" / "firma.png"),
                _png(tmp_path / "firmas" / "Persona Dos" / "firma.png", (200, 0, 0, 255)),
                _png(tmp_path / "firmas" / "Persona Dos" / "roja.png", (250, 0, 0, 255))]
    assert main(["editor", str(tmp_path / "input"), "--formato", str(formato), "--salida",
                 str(tmp_path / "editor"), "--firmas", str(tmp_path / "firmas")]) == 0
    out = capsys.readouterr().out
    assert "Personas con firma (solo el nombre): 2: Persona Dos, Persona Uno." in out
    html = (tmp_path / "editor" / "editor.html").read_text(encoding="utf-8")
    datos = datos_incrustados(html)
    assert datos["rotulo"]["personas_firmas"] == ["Persona Dos", "Persona Uno"]
    # Ninguna imagen de firma (ni en base64 ni en sus nombres de archivo) ni la carpeta.
    for contenido in imagenes:
        assert base64.b64encode(contenido).decode("ascii") not in html
    # (El código del diálogo «Cargar firma…» nombra «firma.png», el archivo que guarda; lo que no
    # puede aparecer es ningún archivo de una persona.)
    assert "Persona Uno/firma.png" not in html and "Persona Dos/firma.png" not in html
    assert "roja.png" not in html and "roja" not in json.dumps(datos)
    assert str(tmp_path / "firmas") not in html and "carpeta_firmas" not in html
    assert not list((tmp_path / "editor").rglob("*firma*"))  # tampoco se copió nada al lado
    # Los datos (los mismos que preparar-editor escribe en editor_datos.json) no nombran la firma.
    assert "firma.png" not in json.dumps(datos)
    assert [p.name for p in (tmp_path / "editor").iterdir()] == ["editor.html"]


@requiere_arial
def test_editor_sin_firmas_ni_proyecto_son_null(entorno):
    tmp_path, formato = entorno
    datos, _ = construir_datos_editor(tmp_path / "input", formato, tmp_path / "editor")
    assert datos["rotulo"]["personas_firmas"] is None and datos["rotulo"]["proyecto"] is None


@requiere_arial
def test_editor_proyecto_se_valida_y_se_incrusta(entorno, capsys):
    tmp_path, formato = entorno
    proyecto = {"version": 1, "nombre": "PROYECTO FICTICIO", "disenador": "DISEÑO S.A.S.",
                "prefijo_no_plano": "ERCO-X-",
                "firmas": {"dibujo": {"nombre": "LANP", "matricula": "PRACTICANTE"}}}
    (tmp_path / "proyecto.json").write_text(json.dumps(proyecto), encoding="utf-8")
    assert main(["editor", str(tmp_path / "input"), "--formato", str(formato), "--salida",
                 str(tmp_path / "editor"), "--proyecto", str(tmp_path / "proyecto.json")]) == 0
    out = capsys.readouterr().out
    assert ("Proyecto «PROYECTO FICTICIO»: prellena un plano nuevo con disenador, "
            "prefijo_no_plano, firmas.dibujo.") in out
    html = (tmp_path / "editor" / "editor.html").read_text(encoding="utf-8")
    assert datos_incrustados(html)["rotulo"]["proyecto"] == proyecto

    (tmp_path / "proyecto.json").write_text(json.dumps({"version": 1, "revisr": "x"}), encoding="utf-8")
    assert main(["editor", str(tmp_path / "input"), "--formato", str(formato), "--salida",
                 str(tmp_path / "editor"), "--proyecto", str(tmp_path / "proyecto.json"),
                 "--sobrescribir"]) == 1
    err = capsys.readouterr().err
    assert "tiene 1 problema:\n- proyecto.revisr: campo no reconocido" in err
