"""Cuadro nativo «Cargar DXF»: validación de la ruta y el proceso aparte (tkinter falso)."""

import json
import sys
import types

import pytest

from componedor import dialogo_dxf
from componedor.dialogo_dxf import (
    DxfInvalido,
    comando_dialogo,
    interpretar_salida,
    validar_dxf,
)


def test_validar_dxf(tmp_path):
    dxf = tmp_path / "Obra.DXF"
    dxf.write_text("x")
    assert validar_dxf(dxf) == dxf.resolve()  # mayúsculas en la extensión: vale
    with pytest.raises(DxfInvalido, match="no es un archivo .dxf"):
        validar_dxf(tmp_path / "plano.pdf")
    with pytest.raises(DxfInvalido, match="No existe el archivo"):
        validar_dxf(tmp_path / "falta.dxf")
    carpeta = tmp_path / "carpeta.dxf"
    carpeta.mkdir()
    with pytest.raises(DxfInvalido, match="No existe el archivo"):
        validar_dxf(carpeta)


def test_interpretar_salida(tmp_path):
    dxf = tmp_path / "a.dxf"
    dxf.write_text("x")
    salida = json.dumps({"ruta": str(dxf)}, ensure_ascii=False)
    assert interpretar_salida(0, "Tk avisa algo\n" + salida + "\n") == dxf.resolve()
    assert interpretar_salida(0, '{"ruta": null}\n') is None  # canceló
    with pytest.raises(DxfInvalido, match=r"No se pudo abrir el cuadro .*no hay pantalla"):
        interpretar_salida(1, "", "Traceback…\n_tkinter.TclError: no hay pantalla\n")
    with pytest.raises(DxfInvalido, match="respondió algo inesperado"):
        interpretar_salida(0, "basura\n")
    with pytest.raises(DxfInvalido, match="no es un archivo .dxf"):
        interpretar_salida(0, json.dumps({"ruta": str(tmp_path / "x.txt")}))


def test_comando_dialogo(tmp_path):
    assert comando_dialogo(None) == [sys.executable, "-m", "componedor.dialogo_dxf"]
    assert comando_dialogo(tmp_path)[-2:] == ["--inicial", str(tmp_path)]


@pytest.fixture
def tk_falso(monkeypatch):
    """Un tkinter falso: registra cómo se abrió el cuadro y devuelve `elegido`."""
    registro = {"elegido": ""}

    class Raiz:
        def withdraw(self):
            registro["oculta"] = True

        def attributes(self, *a):
            registro["atributos"] = a

        def destroy(self):
            registro["destruida"] = True

    def askopenfilename(**kw):
        registro["kw"] = kw
        return registro["elegido"]

    tk = types.ModuleType("tkinter")
    tk.Tk = Raiz
    fd = types.ModuleType("tkinter.filedialog")
    fd.askopenfilename = askopenfilename
    tk.filedialog = fd
    monkeypatch.setitem(sys.modules, "tkinter", tk)
    monkeypatch.setitem(sys.modules, "tkinter.filedialog", fd)
    return registro


def test_main_imprime_la_ruta_elegida(tk_falso, tmp_path, capsys):
    tk_falso["elegido"] = "C:/obras/Ñandú.dxf"
    assert dialogo_dxf.main(["--inicial", str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out) == {"ruta": "C:/obras/Ñandú.dxf"}
    assert tk_falso["atributos"] == ("-topmost", True) and tk_falso["destruida"]
    kw = tk_falso["kw"]
    assert kw["title"] == "Cargar DXF" and kw["initialdir"] == str(tmp_path)
    assert kw["filetypes"][0] == ("Dibujos DXF", "*.dxf")


def test_main_cancelado(tk_falso, tmp_path, capsys):
    assert dialogo_dxf.main(["--inicial", str(tmp_path / "no_existe")]) == 0
    assert json.loads(capsys.readouterr().out) == {"ruta": None}
    assert tk_falso["kw"]["initialdir"] is None  # carpeta inicial que no existe: se ignora


def test_elegir_dxf_lanza_el_proceso_del_cuadro(monkeypatch, tmp_path):
    dxf = tmp_path / "a.dxf"
    dxf.write_text("x")
    llamadas = []

    def run(argv, **kw):
        llamadas.append((argv, kw))
        return types.SimpleNamespace(returncode=0, stderr=b"",
                                     stdout=json.dumps({"ruta": str(dxf)}).encode())

    monkeypatch.setattr(dialogo_dxf.subprocess, "run", run)
    assert dialogo_dxf.elegir_dxf(tmp_path) == dxf.resolve()
    argv, kw = llamadas[0]
    assert argv == comando_dialogo(tmp_path)
    assert kw["env"]["PYTHONUTF8"] == "1"
    assert kw["env"]["PYTHONPATH"].split(";")[0].endswith("src")


def test_cuadro_de_la_ortofoto(tk_falso, tmp_path, capsys, monkeypatch):
    tk_falso["elegido"] = "C:/fotos/Túnez.tif"
    assert dialogo_dxf.main(["--tipo", "ortofoto"]) == 0
    assert json.loads(capsys.readouterr().out) == {"ruta": "C:/fotos/Túnez.tif"}
    kw = tk_falso["kw"]
    assert kw["title"] == "Cargar ortofoto"
    assert kw["filetypes"][0] == ("Ortofotos GeoTIFF", "*.tif *.tiff")
    assert comando_dialogo(tmp_path, "ortofoto") == [
        sys.executable, "-m", "componedor.dialogo_dxf", "--tipo", "ortofoto", "--inicial",
        str(tmp_path)]


def test_elegir_ortofoto(monkeypatch, tmp_path):
    from componedor.ortofoto import OrtofotoInvalida

    tif = tmp_path / "a.TIFF"
    tif.write_bytes(b"x")
    salida = {"ruta": str(tif)}

    def run(argv, **kw):
        assert argv[3:5] == ["--tipo", "ortofoto"]
        return types.SimpleNamespace(returncode=0, stderr=b"",
                                     stdout=json.dumps(salida).encode())

    monkeypatch.setattr(dialogo_dxf.subprocess, "run", run)
    assert dialogo_dxf.elegir_ortofoto() == tif.resolve()
    salida["ruta"] = None
    assert dialogo_dxf.elegir_ortofoto() is None
    salida["ruta"] = str(tmp_path / "foto.jpg")
    with pytest.raises(OrtofotoInvalida, match="no es un GeoTIFF"):
        dialogo_dxf.elegir_ortofoto()
    monkeypatch.setattr(dialogo_dxf.subprocess, "run", lambda argv, **kw: types.SimpleNamespace(
        returncode=1, stdout=b"", stderr=b"TclError: sin pantalla\n"))
    with pytest.raises(OrtofotoInvalida, match="elegir la ortofoto .*sin pantalla"):
        dialogo_dxf.elegir_ortofoto()
