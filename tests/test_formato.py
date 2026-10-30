import copy
import json
from pathlib import Path

import pytest

from componedor.formato import FormatoInvalido, cargar_formato, validar_formato

RUTA_A1 = Path(__file__).parent.parent / "formatos" / "A1_ERCO.json"


@pytest.fixture
def datos_a1():
    """Datos de A1_ERCO.json sin la plantilla real (las pruebas no dependen del rótulo)."""
    datos = json.loads(RUTA_A1.read_text(encoding="utf-8"))
    datos.pop("plantilla", None)
    return datos


def test_a1_erco_declara_la_plantilla():
    datos = json.loads(RUTA_A1.read_text(encoding="utf-8"))
    assert datos["plantilla"] == "../plantillas/rotulo_A1_ERCO.pdf"


def test_carga_formato_a1_erco():
    formato = cargar_formato(RUTA_A1, usar_plantilla=False)
    assert formato.plantilla is None
    assert (formato.ancho_mm, formato.alto_mm) == (841.0, 594.0)
    assert formato.marco == (12.7, 12.7, 828.3, 581.3)
    assert set(formato.zonas) == {
        "area_dibujo", "rotulo", "localizacion", "notas", "convenciones", "cajetin"
    }
    assert formato.grosores_mm == {"marco": 0.5, "guias": 0.13}


def test_zona_fuera_del_marco_en_archivo(tmp_path, datos_a1):
    datos_a1["zonas"]["area_dibujo"] = [5.0, 22.7, 662.4, 571.3]
    ruta = tmp_path / "malo.json"
    ruta.write_text(json.dumps(datos_a1), encoding="utf-8")
    with pytest.raises(FormatoInvalido, match=r"La zona 'area_dibujo' .* se sale del marco"):
        cargar_formato(ruta)


def _invalido(datos, cambio):
    datos = copy.deepcopy(datos)
    cambio(datos)
    return datos


@pytest.mark.parametrize(
    "cambio, mensaje",
    [
        (lambda d: d["marco"].__setitem__(2, d["marco"][0] - 1),
         r"El marco debe tener ancho y alto positivos"),
        (lambda d: d.__setitem__("marco", [-1, 12.7, 828.3, 581.3]),
         r"El marco .* se sale de la hoja"),
        (lambda d: d["zonas"].__setitem__("area_dibujo", [22.7, 22.7, 700.0, 571.3]),
         r"'area_dibujo' .* se traslapa con la zona 'rotulo'"),
        (lambda d: d["zonas"].__setitem__("notas", [600.0, 270.5, 828.3, 424.4]),
         r"La zona 'notas' .* se sale de la zona 'rotulo'"),
        (lambda d: d["zonas"].pop("cajetin"),
         r"Faltan zonas en el formato: cajetin"),
        (lambda d: d["grosores_mm"].__setitem__("marco", 0),
         r"grosor de línea 'marco' debe ser un número positivo"),
        (lambda d: d["zonas"].__setitem__("rotulo", [672.4, 12.7, 828.3]),
         r"La zona 'rotulo' debe ser una lista de 4 números"),
    ],
)
def test_validaciones(datos_a1, cambio, mensaje):
    with pytest.raises(FormatoInvalido, match=mensaje):
        validar_formato(_invalido(datos_a1, cambio))


def test_plantilla_relativa_a_la_carpeta_del_json(tmp_path, datos_a1):
    (tmp_path / "plantillas").mkdir()
    (tmp_path / "plantillas" / "rotulo.pdf").write_bytes(b"%PDF-1.7")
    (tmp_path / "formatos").mkdir()
    datos_a1["plantilla"] = "../plantillas/rotulo.pdf"
    ruta = tmp_path / "formatos" / "f.json"
    ruta.write_text(json.dumps(datos_a1), encoding="utf-8")
    formato = cargar_formato(ruta)
    assert formato.plantilla.resolve() == (tmp_path / "plantillas" / "rotulo.pdf").resolve()


@pytest.mark.parametrize(
    "valor, mensaje",
    [
        ("no_existe.pdf", r"No se encontró la plantilla 'no_existe.pdf'.*--sin-plantilla"),
        ("rotulo.dwg", r"La plantilla debe ser un archivo \.pdf"),
        (42, r"La plantilla debe ser la ruta de un PDF"),
    ],
)
def test_plantilla_invalida(tmp_path, datos_a1, valor, mensaje):
    datos_a1["plantilla"] = valor
    with pytest.raises(FormatoInvalido, match=mensaje):
        validar_formato(datos_a1, base=tmp_path)


def test_sin_plantilla_ignora_la_clave(tmp_path, datos_a1):
    datos_a1["plantilla"] = "no_existe.pdf"
    assert validar_formato(datos_a1, base=tmp_path, usar_plantilla=False).plantilla is None


def test_archivo_inexistente(tmp_path):
    with pytest.raises(FormatoInvalido, match="No se encontró el archivo de formato"):
        cargar_formato(tmp_path / "no_existe.json")


def test_plantilla_no_encontrada_es_un_formato_invalido(tmp_path, datos_a1):
    from componedor.formato import PlantillaNoEncontrada

    datos_a1["plantilla"] = "no_existe.pdf"
    with pytest.raises(PlantillaNoEncontrada):
        validar_formato(datos_a1, base=tmp_path)
    assert issubclass(PlantillaNoEncontrada, FormatoInvalido)
