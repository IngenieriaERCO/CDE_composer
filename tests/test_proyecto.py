"""proyecto.json (subfase 4.3b): esquema versión 1, validación contra el formato con todos los
problemas juntos, y errores claros de archivo. Datos ficticios."""

import json

import pytest

from componedor.formato import cargar_formato
from componedor.proyecto import ProyectoInvalido, leer_proyecto, validar_proyecto
from conftest import ARIAL, escribir_formato, rotulo_a1

PROYECTO = {
    "version": 1,
    "nombre": "PARQUE SOLAR FICTICIO",
    "disenador": "INGENIERÍA DE DISEÑO S.A.S.",
    "revisor": ["INTERVENTORÍA", "ÑANDÚ LTDA."],
    "prefijo_no_plano": "ERCO-PSF-CIV-PL-",
    "firmas": {
        "dibujo": {"nombre": "LUIS Á. NÚÑEZ P.", "matricula": "PRACTICANTE"},
        "reviso": {"nombre": ["ANDRÉS GÓMEZ", "(DIRECTOR TÉCNICO)"], "matricula": "25202-654321"},
    },
}


@pytest.fixture(scope="module")
def definicion(tmp_path_factory):
    carpeta = tmp_path_factory.mktemp("proyecto")
    ruta = escribir_formato(carpeta / "formato.json", rotulo=rotulo_a1(fuente={"archivo": str(ARIAL)}))
    return cargar_formato(ruta, usar_plantilla=False).rotulo


def _escribir(tmp_path, datos) -> str:
    ruta = tmp_path / "proyecto.json"
    ruta.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    return ruta


def test_proyecto_valido_se_lee_tal_cual(tmp_path, definicion):
    assert leer_proyecto(_escribir(tmp_path, PROYECTO), definicion) == PROYECTO
    assert leer_proyecto(_escribir(tmp_path, {"version": 1}), definicion) == {"version": 1}


def test_todos_los_problemas_juntos(definicion):
    malo = {
        "nombre": 3,  # y falta la versión
        "disenadr": "x",
        "disenador": True,  # retirado del rótulo: se ignora (aunque su valor no sirva)
        "revisor": "LÍNEA 1\nLÍNEA 2",
        "prefijo_no_plano": "ERCO\n",
        "firmas": {"dibujo": {"nombre": "A", "firma": {"imagen": "x"}}, "jefe": {},
                   "diseno": "LANP", "reviso": {"matricula": ["A", 1]}},
    }
    with pytest.raises(ProyectoInvalido) as e:
        validar_proyecto(malo, definicion, "p.json")
    assert e.value.problemas == [
        "proyecto.version: falta (use \"version\": 1)",
        "proyecto.disenadr: campo no reconocido (campos válidos: version, nombre, disenador, "
        "revisor, prefijo_no_plano, firmas)",
        "proyecto.nombre: se esperaba un texto; tiene int 3",
        "proyecto.prefijo_no_plano: la celda es de una sola línea y el texto trae un salto de línea",
        "proyecto.firmas.jefe: fila no reconocida (filas válidas: dibujo, diseno, reviso, aprobo)",
        "proyecto.firmas.dibujo.firma: campo no reconocido (el proyecto solo prellena nombre, "
        "matricula)",
        "proyecto.firmas.diseno: se esperaba un objeto con nombre, matricula; tiene texto 'LANP'",
        "proyecto.firmas.reviso.matricula: se esperaba una lista de líneas de texto; tiene "
        "['A', 1]",
    ]
    assert str(e.value).startswith("El proyecto 'p.json' tiene 8 problemas:\n- proyecto.version")


def test_version_y_tipo(definicion):
    with pytest.raises(ProyectoInvalido, match="versión 2 no soportada"):
        validar_proyecto({"version": 2}, definicion)
    with pytest.raises(ProyectoInvalido, match="se esperaba un objeto"):
        validar_proyecto([1], definicion)


def test_errores_de_archivo(tmp_path, definicion):
    with pytest.raises(ProyectoInvalido, match="no se encontró el archivo"):
        leer_proyecto(tmp_path / "no.json", definicion)
    (tmp_path / "malo.json").write_text("{\"version\": 1,", encoding="utf-8")
    with pytest.raises(ProyectoInvalido, match=r"no es un JSON válido \(línea 1"):
        leer_proyecto(tmp_path / "malo.json", definicion)
    (tmp_path / "ansi.json").write_bytes('{"nombre": "DISEÑO"}'.encode("cp1252"))
    with pytest.raises(ProyectoInvalido, match="no está en UTF-8"):
        leer_proyecto(tmp_path / "ansi.json", definicion)


def test_formato_sin_rotulo(definicion):
    assert validar_proyecto({"version": 1, "nombre": "X"}, None) is None
    with pytest.raises(ProyectoInvalido, match="el formato no tiene sección \"rotulo\""):
        validar_proyecto({"version": 1, "disenador": "X"}, None)
