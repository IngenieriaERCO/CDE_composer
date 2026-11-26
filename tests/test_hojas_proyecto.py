"""Varias hojas de un proyecto (plano versión 7, «Nueva hoja a partir de esta»): el índice
<proyecto>.hojas.json, los campos automáticos del rótulo (hoja, de, número de plano), la hoja
vacía y los campos copiados sin revisar."""

import json

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

from componedor.componer import avisos_de_hoja, componer_plano
from componedor.hojas_proyecto import (
    IndiceInvalido,
    escribir_indice,
    indice_de,
    leer_indice,
    nombre_valido,
    siguiente_numero,
    valores_automaticos,
)
from componedor.plano import PlanoInvalido, leer_plano

CAMPOS = {"hoja": "hoja_actual", "de": "total_hojas", "no_plano": "numero_siguiente"}


def _hoja(carpeta, nombre, rotulo=None, detalles=(), version=7, **extra):
    datos = {"version": version, "formato": "formato.json", "detalles": list(detalles), **extra}
    if rotulo is not None:
        datos["rotulo"] = rotulo
    ruta = carpeta / nombre
    ruta.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    return ruta


# --- índice y números ---------------------------------------------------------------------

@pytest.mark.parametrize("numero, siguiente", [
    ("PRGD-25-1365-CIV-PL-106", "PRGD-25-1365-CIV-PL-107"), ("A-009", "A-010"),
    ("PL-099", "PL-100"), ("7", "8"), ("SIN NÚMERO", None)])
def test_siguiente_numero(numero, siguiente):
    assert siguiente_numero(numero) == siguiente


def test_indice(tmp_path):
    ruta = escribir_indice(tmp_path, "obra", ["a.json", "b.json"])
    assert ruta.name == "obra.hojas.json" and leer_indice(ruta) == ["a.json", "b.json"]
    assert indice_de(tmp_path / "B.json") == (ruta, ["a.json", "b.json"])  # sin mayúsculas
    assert indice_de(tmp_path / "otro.json") is None
    for malas in (["../a.json"], ["a/b.json"], ["a.json", "A.json"], [], ["a.txt"]):
        with pytest.raises(IndiceInvalido):
            escribir_indice(tmp_path, "x", malas)
    (tmp_path / "roto.hojas.json").write_text("{", encoding="utf-8")
    assert indice_de(tmp_path / "a.json")[0] == ruta  # el roto se salta
    assert nombre_valido("Plano 1.json") and not nombre_valido("p.hojas.json")


def test_valores_automaticos(tmp_path):
    _hoja(tmp_path, "h1.json", {"no_plano": "ERCO-PL-106", "hoja": "1"})
    _hoja(tmp_path, "h2.json", {})
    _hoja(tmp_path, "h3.json", {"de": "9"})
    escribir_indice(tmp_path, "obra", ["h1.json", "h2.json", "h3.json"])
    assert valores_automaticos(tmp_path / "h1.json", CAMPOS) == {"de": "3"}  # lo escrito manda
    assert valores_automaticos(tmp_path / "h2.json", CAMPOS) == {
        "hoja": "2", "de": "3", "no_plano": "ERCO-PL-107"}
    assert valores_automaticos(tmp_path / "h3.json", CAMPOS) == {"hoja": "3", "no_plano": "ERCO-PL-108"}
    # Una hoja intermedia que escribe su número: las siguientes siguen desde él.
    _hoja(tmp_path, "h2.json", {"no_plano": "ERCO-PL-200"})
    assert valores_automaticos(tmp_path / "h3.json", CAMPOS)["no_plano"] == "ERCO-PL-201"
    # El rótulo sin guardar (lo que pasa el editor) manda sobre el del archivo.
    assert valores_automaticos(tmp_path / "h3.json", CAMPOS, {})["de"] == "3"
    assert valores_automaticos(tmp_path / "suelta.json", CAMPOS) == {}  # sin índice


# --- plano versión 7 ----------------------------------------------------------------------

def test_plano_version_7(tmp_path):
    escribir_formato(tmp_path / "formato.json")
    plano = leer_plano(_hoja(tmp_path, "h2.json", {}, copiado_de={
        "hoja": "h1.json", "revisar": ["notas", "revisiones"]}))
    assert plano.version == 7 and plano.detalles == ()
    assert plano.copiado_de == "h1.json" and plano.revisar == ("notas", "revisiones")
    assert avisos_de_hoja(plano) == [
        "La hoja no tiene detalles: sale solo el rótulo.",
        ("rotulo.notas: copiado de la hoja «h1.json» sin revisar: revíselo (el editor deja de "
         "avisar cuando se cambia)."),
        ("rotulo.revisiones: copiado de la hoja «h1.json» sin revisar: revíselo (el editor deja "
         "de avisar cuando se cambia).")]
    # Los planos viejos siguen igual: una lista vacía o "copiado_de" no son de la versión 6.
    with pytest.raises(PlanoInvalido, match="una hoja con solo el rótulo es de la versión 7"):
        leer_plano(_hoja(tmp_path, "v6.json", version=6))
    with pytest.raises(PlanoInvalido, match="copiado_de: solo existe en la versión 7"):
        leer_plano(_hoja(tmp_path, "v6.json", version=6, copiado_de={"hoja": "a.json"},
                         detalles=[{"id": "a", "manifiesto": "a.manifest.json",
                                    "posicion_mm": [30, 40]}]))
    with pytest.raises(PlanoInvalido, match="copiado_de.revisar"):
        leer_plano(_hoja(tmp_path, "x.json", copiado_de={"hoja": "a.json", "revisar": "notas"}))


# --- componer -------------------------------------------------------------------------------

@requiere_arial
def test_componer_dos_hojas_con_automaticos(tmp_path):
    """La hoja 1 con un detalle y su número escrito; la 2 vacía (solo el rótulo): hoja, de y
    número de plano salen solos, y componer avisa que está vacía."""
    escribir_formato(tmp_path / "formato.json", plantilla=crear_plantilla_sintetica(tmp_path / "r.pdf"),
                     rotulo=rotulo_a1(fuente={"archivo": str(ARIAL)}))
    crear_paquete_real(tmp_path / "input", "a")
    rotulo = {"titulo": "PLANTA", "no_plano": "ERCO-PSF-CIV-PL-106"}
    h1 = _hoja(tmp_path, "h1.json", rotulo, version=2, detalles=[
        {"id": "a", "manifiesto": "input/a.manifest.json", "posicion_mm": [30, 300]}])
    h2 = _hoja(tmp_path, "h2.json", {"titulo": "PERFIL"}, copiado_de={"hoja": "h1.json", "revisar": []})
    escribir_indice(tmp_path, "obra", ["h1.json", "h2.json"])
    r1 = componer_plano(leer_plano(h1), tmp_path / "h1.pdf")
    r2 = componer_plano(leer_plano(h2), tmp_path / "h2.pdf")
    assert (r1.rotulo["hoja"], r1.rotulo["de"], r1.rotulo["no_plano"]) == ("1", "2", "ERCO-PSF-CIV-PL-106")
    assert (r2.rotulo["hoja"], r2.rotulo["de"], r2.rotulo["no_plano"]) == ("2", "2", "ERCO-PSF-CIV-PL-107")
    assert r2.detalles == [] and r2.advertencias[0] == "La hoja no tiene detalles: sale solo el rótulo."
    with pymupdf.open(tmp_path / "h2.pdf") as doc:
        texto = doc[0].get_text()
    assert "ERCO-PSF-CIV-PL-107" in texto and "PERFIL" in texto
    # Sin índice, como siempre: no inventa la hoja ni el número.
    (tmp_path / "obra.hojas.json").unlink()
    r = componer_plano(leer_plano(h2), tmp_path / "h2b.pdf")
    assert r.rotulo.get("no_plano", "") == ""
