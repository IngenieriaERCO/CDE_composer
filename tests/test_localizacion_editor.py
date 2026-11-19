"""«Cargar imagen de localización» del servidor (sin HTTP y por HTTP) y la lógica del editor
(editor_localizacion.js, en Node, comparada con Python)."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from conftest import ZONA_A1
from test_localizacion import CAMPO, RECT, jpg, png
from test_servidor import HTML, pedido

import componedor
from componedor.aplicacion_editor import AplicacionEditor
from componedor.localizacion import contener
from componedor.localizacion_editor import (
    ErrorLocalizacion,
    LocalizacionEditor,
    validar_imagen,
)
from componedor.servidor import ServidorEditor


def test_elegir_ficha_imagen_y_quitar(tmp_path):
    img = png(tmp_path / "qgis" / "loc.png", 900, 600)
    elegidas = []
    loc = LocalizacionEditor(tmp_path / "editor", elegir=lambda i: elegidas.append(i) or img)
    (tmp_path / "editor").mkdir()
    assert loc.estado() is None
    r = loc.elegir("../qgis/otra.png")
    assert elegidas == [img.parent]  # el cuadro se abre en la carpeta del plano
    e = r["localizacion"]
    assert (e["nombre"], e["archivo_plano"], e["px"], e["formato"]) == (
        "loc.png", "../qgis/loc.png", [900, 600], "png")
    assert e["bytes"] == img.stat().st_size and e["cambio"] is False
    assert loc.imagen() == (img.read_bytes(), "image/png")
    estado = img.stat()
    os.utime(img, ns=(estado.st_atime_ns, estado.st_mtime_ns + 5_000_000_000))
    assert loc.estado()["cambio"] is True
    with pytest.raises(ErrorLocalizacion) as err:
        loc.imagen()
    assert err.value.estado_http == 409
    assert loc.quitar() == {"quitada": True} and loc.estado() is None


def test_imagenes_que_no_sirven(tmp_path):
    (tmp_path / "x.png").write_bytes(b"no es png")
    for ruta, texto in ((tmp_path / "a.tif", "no es un .png"), (tmp_path / "no.png", "No existe"),
                        (tmp_path / "x.png", "no es una imagen PNG ni JPG")):
        with pytest.raises(ValueError, match=texto):
            validar_imagen(ruta)
    assert validar_imagen(jpg(tmp_path / "a.JPG", 40, 30))[1:] == ("jpeg", (40, 30))
    loc = LocalizacionEditor(tmp_path, elegir=lambda i: tmp_path / "x.png")
    with pytest.raises(ErrorLocalizacion, match="no es una imagen") as e:
        loc.elegir()
    assert e.value.estado_http == 400


def test_por_http(tmp_path):
    (tmp_path / "editor.html").write_text(HTML, encoding="utf-8")
    img = png(tmp_path / "loc.png", 120, 80)
    app = AplicacionEditor(tmp_path / "editor.html", ZONA_A1, None,
                           elegir_localizacion=lambda inicial: img)
    s = ServidorEditor(app)
    s.iniciar()
    try:
        assert pedido(s, "GET", "/api/localizacion") == (200, {"localizacion": None})
        estado, r = pedido(s, "POST", "/api/localizacion/elegir")
        assert estado == 200 and r["elegida"] == "loc.png"
        assert pedido(s, "GET", "/api/estado")[1]["localizacion"]["px"] == [120, 80]
        estado, datos = pedido(s, "GET", "/api/localizacion/imagen")
        assert estado == 200 and datos.startswith(b"\x89PNG")
        assert pedido(s, "GET", "/api/localizacion/imagen", token=False)[0] == 403
        assert pedido(s, "POST", "/api/localizacion/elegir", origen=False)[0] == 403
        assert pedido(s, "POST", "/api/localizacion/quitar") == (200, {"quitada": True})
        assert pedido(s, "GET", "/api/localizacion/imagen")[0] == 404
    finally:
        s.detener()
        app.cerrar()


# --- editor_localizacion.js ------------------------------------------------------------------------

NODE = shutil.which("node")
JS = Path(componedor.__file__).parent / "editor" / "editor_localizacion.js"


def js(codigo, entrada=None):
    script = (f"const LO = require({json.dumps(str(JS))});"
              "const entrada = JSON.parse(require('fs').readFileSync(0, 'utf8'));"
              f"const salida = (function () {{ {codigo} }})();"
              "process.stdout.write(JSON.stringify(salida === undefined ? null : salida));")
    r = subprocess.run([NODE, "-e", script], input=json.dumps(entrada), capture_output=True,
                       text=True, encoding="utf-8", check=False)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


@pytest.mark.skipif(NODE is None, reason="Node no está instalado")
def test_el_editor_ajusta_igual_que_componer():
    casos = [(2000, 1000), (500, 1000), (1539, 1144), (10, 3000)]
    r = js("return entrada.casos.map(([w, h]) => LO.contener(entrada.rect, w, h));",
           {"casos": casos, "rect": list(RECT)})
    for (w, h), a in zip(casos, r, strict=True):
        assert a == pytest.approx(list(contener(RECT, w, h)), abs=1e-9)
    p = js("""return [LO.enElPdf(entrada.campo, [3000, 2000], "png"), LO.enElPdf(entrada.campo, [3000, 2000], "jpeg"),
                      LO.enElPdf(entrada.campo, [600, 400], "png")];""",
           {"campo": {"rect_mm": list(RECT), "ppp": CAMPO.ppp}})
    assert p[0]["reducida"] and p[0]["pppFinal"] == pytest.approx(300, abs=0.5)
    assert not p[1]["reducida"] and p[1]["ppp"] == pytest.approx(495.1, abs=0.5)  # JPG tal cual
    assert not p[2]["reducida"] and p[2]["ppp"] < 300  # no se agranda


@pytest.mark.skipif(NODE is None, reason="Node no está instalado")
def test_campo_diferencias_y_escala(tmp_path):
    from componedor.datos_rotulo_editor import definicion_editor
    from componedor.formato import cargar_formato
    definicion = definicion_editor(cargar_formato("formatos/A1_ERCO.json", usar_plantilla=False).rotulo)
    ficha = {"nombre": "loc.png", "archivo_plano": "../qgis/loc.png", "bytes": 10,
             "modificado": "2026-11-19T10:00:00Z", "px": [900, 600], "formato": "png"}
    r = js("""return {campo: LO.campoImagen(entrada.def), igual: LO.diferencias(entrada.v, entrada.f),
                      otra: LO.diferencias({archivo: "x.png", bytes: 11, modificado: "2026-01-01T00:00:00Z"}, entrada.f),
                      valor: LO.valorParaPlano(entrada.f),
                      vacias: [undefined, null, "", "  ", "1:25000"].map(LO.escalaVacia),
                      ficha: LO.lineasFicha(LO.campoImagen(entrada.def), entrada.f)};""",
           {"def": definicion, "f": ficha,
            "v": {"archivo": "../qgis/loc.png", "bytes": 10, "modificado": "2026-11-19T10:00:00Z"}})
    assert r["campo"] == {"nombre": "localizacion_imagen", "tipo": "imagen", "rect_mm": list(RECT),
                          "ppp": 300, "campo_escala": "localizacion_escala"}
    assert r["igual"] == [] and len(r["otra"]) == 3
    assert r["valor"] == {"archivo": "../qgis/loc.png", "bytes": 10,
                          "modificado": "2026-11-19T10:00:00Z"}
    assert r["vacias"] == [True, True, True, True, False]
    assert r["ficha"][0] == "loc.png · PNG · 900 × 600 px"
    assert "no se agranda" in r["ficha"][1]
