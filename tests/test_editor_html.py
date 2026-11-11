"""Comando `editor`: un solo editor.html autocontenido (datos sintéticos, no de ERCO)."""

import base64
import re

import pytest

from componedor.advertencias import PLANTILLAS
from componedor.cli import main
from componedor.datos_editor import preparar_editor
from componedor.editor_html import construir_html, datos_incrustados, generar_editor
from conftest import crear_paquete_real, crear_plantilla_sintetica, escribir_formato

ROSA = [612.0, 51.0, 652.0, 91.0]


@pytest.fixture
def entorno(tmp_path):
    plantilla = crear_plantilla_sintetica(tmp_path / "rotulo.pdf", elementos_mm=[ROSA])
    escribir_formato(tmp_path / "formato.json", plantilla=plantilla,
                     elementos_plantilla=[{"nombre": "rosa_vientos", "rect_mm": ROSA}])
    crear_paquete_real(tmp_path / "input", "a")
    crear_paquete_real(tmp_path / "input", "sin_escala",
                       cambiar={"scale.physical_scale_guaranteed": False})
    return tmp_path


def _generar(entorno, **kw):
    return generar_editor(entorno / "input", entorno / "formato.json", entorno / "editor", **kw)


def test_genera_un_solo_html_autocontenido(entorno):
    ruta = _generar(entorno)
    assert ruta == entorno / "editor" / "editor.html"
    html = ruta.read_text(encoding="utf-8")
    assert html.startswith("<!DOCTYPE html>") and "\r" not in html
    assert not re.search(r"https?://", html)  # ninguna URL externa
    assert not re.search(r"<(script|link|img)[^>]+\b(src|href)=", html)  # nada se carga de afuera
    assert not re.findall(r"@@\w+@@", html)  # todos los marcadores reemplazados
    # El CSS y los dos JS quedaron dentro.
    assert "--acento" in html
    assert "function papelAPantalla" in html and "function serializarPlano" in html
    assert "function empezarArrastre" in html


def test_datos_incrustados(entorno):
    datos = datos_incrustados(_generar(entorno).read_text(encoding="utf-8"))
    assert datos["version"] == 1 and datos["formato"] == "../formato.json"
    assert [z["nombre"] for z in datos["zonas"] if z["editable"]] == ["area_dibujo"]
    assert [d["id"] for d in datos["detalles"]] == ["a"]
    assert [r["prefijo"] for r in datos["rechazados"]] == ["sin_escala"]
    assert datos["elementos_plantilla"] == [{"nombre": "rosa_vientos", "rect_mm": ROSA}]
    assert datos["advertencias"] == PLANTILLAS  # mismos textos que componer
    assert datos["carpeta_editor"] == str((entorno / "editor").resolve())
    # Imágenes incrustadas en base64: la plantilla en SVG (4.3f), las miniaturas en PNG.
    url = datos["imagen_plantilla"]["data_url"]
    assert url.startswith("data:image/svg+xml;base64,")
    # La misma plantilla.svg que deja preparar-editor (generar_editor ya no la deja al lado).
    preparar_editor(entorno / "input", entorno / "formato.json", entorno / "editor",
                    sobrescribir=True, carpeta_archivos=entorno / "subproductos")
    svg = (entorno / "subproductos" / "plantilla.svg").read_bytes()
    assert base64.b64decode(url.split(",", 1)[1]) == svg
    url = datos["detalles"][0]["miniatura"]["data_url"]
    assert url.startswith("data:image/png;base64,")
    assert base64.b64decode(url.split(",", 1)[1])[:8] == b"\x89PNG\r\n\x1a\n"


def test_sin_svg_usa_el_png(entorno):
    """Datos sin "svg" (anteriores a la 4.3f): el editor incrusta plantilla.png como antes."""
    datos = preparar_editor(entorno / "input", entorno / "formato.json", entorno / "editor")
    del datos["imagen_plantilla"]["svg"]
    url = datos_incrustados(construir_html(datos, entorno / "editor"))["imagen_plantilla"]["data_url"]
    assert url.startswith("data:image/png;base64,")


def test_vista_previa_del_rotulo_incrustada(entorno):
    """4.3f: la casilla «Vista previa del rótulo» y sus dos módulos van dentro del HTML."""
    html = _generar(entorno).read_text(encoding="utf-8")
    assert 'id="vista-previa"' in html and "Vista previa del rótulo" in html
    # Orden: la vista previa necesita maquetación, formularios y notas; la interfaz, las dos.
    marcas = ["raiz.EditorMaquetacion = api", "raiz.EditorFormularios = api", "raiz.EditorNotas = api",
              "raiz.EditorVistaPrevia = api", "raiz.EditorLienzoRotulo =", "function empezarArrastre"]
    posiciones = [html.index(m) for m in marcas]
    assert posiciones == sorted(posiciones)


def test_en_la_carpeta_solo_queda_editor_html(entorno):
    """Todo va incrustado: datos, plantilla, rosa y miniaturas no quedan al lado."""
    _generar(entorno)
    assert [p.name for p in (entorno / "editor").iterdir()] == ["editor.html"]


def test_las_rutas_siguen_relativas_a_la_carpeta_del_editor(entorno):
    """Los subproductos se arman en otra carpeta, pero el plano.json se guarda junto a
    editor.html: formato y manifiestos van relativos a la carpeta del editor."""
    datos = datos_incrustados(_generar(entorno).read_text(encoding="utf-8"))
    assert datos["formato"] == "../formato.json"
    assert datos["detalles"][0]["manifiesto"] == "../input/a.manifest.json"


def test_quita_los_subproductos_de_versiones_anteriores(entorno):
    """Una carpeta generada antes (con editor_datos.json, PNG, SVG, miniaturas/ y simbolos/)
    queda solo con editor.html y lo que es del usuario."""
    preparar_editor(entorno / "input", entorno / "formato.json", entorno / "editor")
    carpeta = entorno / "editor"
    (carpeta / "simbolos").mkdir()
    (carpeta / "simbolos" / "corte.png").write_bytes(b"png")
    (carpeta / "plano.json").write_text("{}", encoding="utf-8")
    (carpeta / "miniaturas" / "mio.txt").write_text("del usuario", encoding="utf-8")
    assert {"editor_datos.json", "plantilla.png", "plantilla.svg", "rosa.png"} <= {
        p.name for p in carpeta.iterdir()}
    _generar(entorno, sobrescribir=True)
    assert sorted(p.name for p in carpeta.iterdir()) == ["editor.html", "miniaturas", "plano.json"]
    assert [p.name for p in (carpeta / "miniaturas").iterdir()] == ["mio.txt"]  # solo los PNG


def test_preparar_editor_en_otra_carpeta(entorno):
    """`carpeta_archivos`: los archivos van ahí y las rutas, relativas a `carpeta_salida`."""
    datos = preparar_editor(entorno / "input", entorno / "formato.json", entorno / "editor",
                            carpeta_archivos=entorno / "tmp")
    assert not (entorno / "editor").exists()
    assert (entorno / "tmp" / "editor_datos.json").is_file()
    assert (entorno / "tmp" / "miniaturas" / "a.png").is_file()
    assert datos["formato"] == "../formato.json"


def test_carpeta_existente(entorno):
    _generar(entorno)
    with pytest.raises(FileExistsError, match="Use --sobrescribir"):
        _generar(entorno)
    carpeta = entorno / "editor"
    mio = carpeta / "plano.json"
    mio.write_text("{}", encoding="utf-8")  # un plano guardado por el usuario
    (carpeta / "editor.html").write_text("viejo", encoding="utf-8")
    _generar(entorno, sobrescribir=True)
    assert (carpeta / "editor.html").read_text(encoding="utf-8").startswith("<!DOCTYPE html>")
    assert mio.read_text(encoding="utf-8") == "{}"  # lo que no genera el editor no se toca


def test_cli_editor(entorno, capsys):
    args = ["editor", str(entorno / "input"), "--formato", str(entorno / "formato.json"),
            "--salida", str(entorno / "editor")]
    assert main(args) == 0
    out = capsys.readouterr().out
    carpeta = (entorno / "editor").resolve()
    assert f"Editor generado: {carpeta / 'editor.html'}" in out
    assert f"Guarde el plano.json en la MISMA carpeta que editor.html: {carpeta}" in out
    assert "python -m componedor.cli componer" in out
    assert main(args) == 1
    assert "Use --sobrescribir" in capsys.readouterr().err
    assert main(args + ["--sobrescribir"]) == 0
