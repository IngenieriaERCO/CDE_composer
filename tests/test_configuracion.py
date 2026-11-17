"""componedor.json, `editor --config`, `componer --config` y los accesos directos .bat
(datos sintéticos, no de ERCO)."""

import json
from pathlib import Path

import pytest

from componedor.cli import CODIGO_AVISOS, main
from componedor.configuracion import (
    ConfigExportador,
    ConfigInvalida,
    leer_config_componer,
    leer_config_editor,
    leer_config_exportador,
)
from conftest import crear_paquete_real, crear_plantilla_sintetica, escribir_formato

RAIZ = Path(__file__).parent.parent


def _config(carpeta: Path, editor: dict | None = None, componer: dict | None = None,
            formato="formato.json", version=1, **extra) -> Path:
    datos = {"version": version, "formato": formato, **extra}
    if editor is not None:
        datos["editor"] = editor
    if componer is not None:
        datos["componer"] = componer
    ruta = carpeta / "componedor.json"
    ruta.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    return ruta


@pytest.fixture
def entorno(tmp_path):
    escribir_formato(tmp_path / "formato.json",
                     plantilla=crear_plantilla_sintetica(tmp_path / "rotulo.pdf"))
    crear_paquete_real(tmp_path / "input", "a")
    crear_paquete_real(tmp_path / "input", "b")
    (tmp_path / "notas").mkdir()
    (tmp_path / "firmas").mkdir()
    return tmp_path


EDITOR = {"paquetes": "input", "salida": "editor"}
COMPONER = {"resultados": "resultados"}


# --- leer_config_editor -------------------------------------------------------------------------

def test_rutas_relativas_a_la_carpeta_del_archivo(entorno, monkeypatch, tmp_path_factory):
    ruta = _config(entorno, {**EDITOR, "notas": "notas", "firmas": "firmas", "proyecto": None})
    monkeypatch.chdir(tmp_path_factory.mktemp("otro_lado"))  # el directorio actual no importa
    c = leer_config_editor(ruta)
    assert c.paquetes == entorno / "input" and c.formato == entorno / "formato.json"
    assert c.salida == entorno / "editor"
    assert c.notas == entorno / "notas" and c.firmas == entorno / "firmas"
    assert c.proyecto is None


def test_opcionales_ausentes_son_none(entorno):
    c = leer_config_editor(_config(entorno, EDITOR))
    assert (c.notas, c.firmas, c.proyecto) == (None, None, None)


def test_salida_no_tiene_que_existir(entorno):
    assert not (entorno / "editor").exists()
    leer_config_editor(_config(entorno, EDITOR))


def test_acepta_bom(entorno):
    ruta = _config(entorno, EDITOR)
    ruta.write_bytes(b"\xef\xbb\xbf" + ruta.read_bytes())
    assert leer_config_editor(ruta).salida == entorno / "editor"


def test_cada_comando_lee_solo_su_seccion(entorno):
    """Sin sección "componer", el editor funciona; sin "editor", componer funciona."""
    leer_config_editor(_config(entorno, EDITOR))
    assert leer_config_componer(_config(entorno, componer=COMPONER)).resultados == \
        entorno / "resultados"
    with pytest.raises(ConfigInvalida, match='falta la sección "componer"'):
        leer_config_componer(_config(entorno, EDITOR))


def test_archivo_que_no_existe(tmp_path):
    with pytest.raises(ConfigInvalida, match="No se encontró el archivo de configuración"):
        leer_config_editor(tmp_path / "componedor.json")


def test_json_invalido(tmp_path):
    ruta = tmp_path / "componedor.json"
    ruta.write_text('{"version": 1,', encoding="utf-8")
    with pytest.raises(ConfigInvalida, match="no es un JSON válido"):
        leer_config_editor(ruta)


@pytest.mark.parametrize("contenido, mensaje", [
    ("[]", "se esperaba un objeto"),
    ('{"version": 2, "editor": {}}', "version debe ser 1"),
    ('{"version": 1, "formato": "f.json"}', 'falta la sección "editor"'),
])
def test_estructura_invalida(tmp_path, contenido, mensaje):
    ruta = tmp_path / "componedor.json"
    ruta.write_text(contenido, encoding="utf-8")
    with pytest.raises(ConfigInvalida, match=mensaje):
        leer_config_editor(ruta)


def test_reporta_todos_los_problemas_juntos(entorno):
    ruta = _config(entorno, {"paquetes": "no_hay", "salida": "", "nota": "notas",
                             "firmas": 3, "proyecto": "falta.json"},
                   formato=None, edtor={})
    with pytest.raises(ConfigInvalida) as e:
        leer_config_editor(ruta)
    texto = str(e.value)
    assert "tiene 7 problema(s)" in texto
    assert "edtor: clave desconocida" in texto
    assert "formato: es obligatorio" in texto
    assert "editor.nota: clave desconocida" in texto
    assert "editor.salida: se esperaba una ruta" in texto
    assert "editor.firmas: se esperaba una ruta" in texto
    assert "editor.paquetes: no existe la carpeta" in texto
    assert "editor.proyecto: no existe el archivo" in texto


def test_formato_que_no_existe(entorno):
    ruta = _config(entorno, EDITOR, formato="input")  # una carpeta, no un archivo
    with pytest.raises(ConfigInvalida, match="- formato: no existe el archivo"):
        leer_config_editor(ruta)


def test_sin_verificar_rutas(tmp_path):
    ruta = _config(tmp_path, {"paquetes": "x", "salida": "z"}, formato="y.json")
    assert leer_config_editor(ruta, verificar_rutas=False).paquetes == tmp_path / "x"


def test_componedor_json_del_repositorio():
    """El componedor.json de la raíz: rutas de la estructura acordada y el formato existe."""
    c = leer_config_editor(RAIZ / "componedor.json", verificar_rutas=False)
    assert c.paquetes == RAIZ / "data" / "input"
    assert c.formato == RAIZ / "formatos" / "A1_ERCO.json" and c.formato.is_file()
    assert (c.salida, c.notas, c.firmas) == (RAIZ / "editor", RAIZ / "notas", RAIZ / "firmas")
    assert c.proyecto is None
    k = leer_config_componer(RAIZ / "componedor.json", verificar_rutas=False)
    assert (k.formato, k.resultados) == (c.formato, RAIZ / "resultados")
    x = leer_config_exportador(RAIZ / "componedor.json")
    assert x == ConfigExportador(("cde-exporter",), RAIZ / "data" / "cache_exportador", 5.0)


# --- sección exportador («Cargar DXF») ----------------------------------------------------------

def test_exportador_ausente_es_none(entorno):
    assert leer_config_exportador(_config(entorno, EDITOR, COMPONER)) is None


def test_exportador_completo_y_por_defecto(entorno):
    ruta = _config(entorno, EDITOR, COMPONER,
                   exportador={"comando": ["py", "-m", "cde"], "trabajo": "w", "margen_mm": 7.5})
    assert leer_config_exportador(ruta) == ConfigExportador(("py", "-m", "cde"), entorno / "w", 7.5)
    ruta = _config(entorno, EDITOR, COMPONER, exportador={"comando": "cde-exporter",
                                                          "trabajo": "w"})
    assert leer_config_exportador(ruta).margen_mm == 5.0
    # Las otras secciones siguen leyéndose con la sección nueva presente.
    assert leer_config_editor(ruta).paquetes == entorno / "input"


@pytest.mark.parametrize("seccion, mensaje", [
    ("x", '"exportador" debe ser un objeto'),
    ({"comando": "", "trabajo": "w"}, "exportador.comando: se esperaba el comando"),
    ({"comando": ["a", 3], "trabajo": "w"}, "exportador.comando: se esperaba el comando"),
    ({"comando": "c"}, "exportador.trabajo: es obligatorio"),
    ({"comando": "c", "trabajo": "w", "margen_mm": -1}, "exportador.margen_mm: se esperaba"),
    ({"comando": "c", "trabajo": "w", "margen_mm": True}, "exportador.margen_mm: se esperaba"),
    ({"comando": "c", "trabajo": "w", "puerto": 1}, "exportador.puerto: clave desconocida"),
])
def test_exportador_invalido(entorno, seccion, mensaje):
    with pytest.raises(ConfigInvalida, match=mensaje):
        leer_config_exportador(_config(entorno, EDITOR, COMPONER, exportador=seccion))


# --- editor --config ----------------------------------------------------------------------------

def test_cli_editor_con_config(entorno, capsys):
    ruta = _config(entorno, {**EDITOR, "notas": "notas", "firmas": "firmas"})
    assert main(["editor", "--config", str(ruta)]) == 0
    out = capsys.readouterr().out
    assert f"Configuración: {ruta.resolve()}" in out
    assert (entorno / "editor" / "editor.html").is_file()
    # Regenerar con --sobrescribir no borra un plano.json guardado en la carpeta del editor.
    (entorno / "editor" / "plano.json").write_text("{}", encoding="utf-8")
    assert main(["editor", "--config", str(ruta)]) == 1
    assert "Use --sobrescribir" in capsys.readouterr().err
    assert main(["editor", "--config", str(ruta), "--sobrescribir"]) == 0
    assert (entorno / "editor" / "plano.json").read_text(encoding="utf-8") == "{}"


def test_cli_config_no_se_mezcla_con_rutas(entorno, capsys):
    ruta = _config(entorno, EDITOR)
    assert main(["editor", str(entorno / "input"), "--config", str(ruta),
                 "--notas", str(entorno / "notas")]) == 2
    err = capsys.readouterr().err
    assert "con --config las rutas salen del archivo; quite carpeta, --notas" in err
    assert not (entorno / "editor").exists()


def test_cli_config_invalida(entorno, capsys):
    ruta = _config(entorno, {**EDITOR, "paquetes": "no_hay"})
    assert main(["editor", "--config", str(ruta)]) == 1
    assert "editor.paquetes: no existe la carpeta" in capsys.readouterr().err


def test_cli_sin_config_exige_las_rutas(entorno, capsys):
    assert main(["editor", str(entorno / "input")]) == 2
    assert "falta --formato, --salida (o use --config componedor.json)" in capsys.readouterr().err


# --- componer --config --------------------------------------------------------------------------

def _plano(carpeta: Path, nombre: str, detalles, formato="formato.json") -> Path:
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / nombre
    ruta.write_text(json.dumps({"version": 1, "formato": formato, "detalles": detalles}),
                    encoding="utf-8")
    return ruta


def _d(id_, prefijo, pos, raiz="..", ):
    return {"id": id_, "manifiesto": f"{raiz}/input/{prefijo}.manifest.json",
            "posicion_mm": list(pos)}


def test_cli_componer_con_config_deja_el_pdf_en_resultados(entorno, monkeypatch,
                                                           tmp_path_factory, capsys):
    """El plano puede estar en cualquier carpeta (aquí planos/, no editor/), y se ejecuta
    desde otro lado: el PDF va a <resultados>/<nombre del plano>.pdf."""
    ruta = _config(entorno, componer=COMPONER)
    plano = _plano(entorno / "planos", "via_norte.json", [_d("d1", "a", (30, 300))],
                   formato="../formato.json")
    monkeypatch.chdir(tmp_path_factory.mktemp("otro_lado"))
    assert main(["componer", str(plano), "--config", str(ruta), "--codigo-avisos"]) == 0
    out = capsys.readouterr().out
    pdf = entorno / "resultados" / "via_norte.pdf"
    assert pdf.is_file() and f"PDF: {pdf}" in out
    assert "Aviso: el plano indica el formato" not in out
    # Sin --sobrescribir no lo reemplaza; con --sobrescribir, sí.
    assert main(["componer", str(plano), "--config", str(ruta)]) == 1
    assert main(["componer", str(plano), "--config", str(ruta), "--sobrescribir"]) == 0


def test_cli_componer_usa_el_formato_de_la_config(entorno, capsys):
    """Aunque el plano apunte a otro formato (aquí uno roto), se usa el de componedor.json."""
    (entorno / "viejo.json").write_text("esto no es un formato", encoding="utf-8")
    plano = _plano(entorno / "planos", "p.json", [_d("d1", "a", (30, 300))],
                   formato="../viejo.json")
    assert main(["componer", str(plano), "--salida", str(entorno / "x.pdf")]) == 1  # sin config
    capsys.readouterr()
    assert main(["componer", str(plano), "--config", str(_config(entorno, componer=COMPONER))]) == 0
    out = capsys.readouterr().out
    assert "Aviso: el plano indica el formato" in out and "viejo.json" in out
    assert (entorno / "resultados" / "p.pdf").is_file()


def test_cli_componer_codigo_de_avisos(entorno, capsys):
    """Con advertencias (páginas que se traslapan): 0 sin la opción, 3 con --codigo-avisos."""
    detalles = [_d("d1", "a", (30, 300)), _d("d2", "b", (280, 300))]
    plano = _plano(entorno / "planos", "traslape.json", detalles, formato="../formato.json")
    ruta = _config(entorno, componer=COMPONER)
    assert main(["componer", str(plano), "--config", str(ruta)]) == 0
    assert "Advertencias (1)" in capsys.readouterr().out
    assert main(["componer", str(plano), "--config", str(ruta), "--sobrescribir",
                 "--codigo-avisos"]) == CODIGO_AVISOS == 3


def test_cli_componer_opciones(entorno, capsys):
    plano = _plano(entorno / "planos", "p.json", [_d("d1", "a", (30, 300))],
                   formato="../formato.json")
    assert main(["componer", str(plano)]) == 2
    assert "falta --salida (o use --config componedor.json)" in capsys.readouterr().err
    ruta = _config(entorno, componer=COMPONER)
    assert main(["componer", str(plano), "--config", str(ruta), "--salida", "x.pdf"]) == 2
    assert "quite --salida" in capsys.readouterr().err
    assert not (entorno / "resultados").exists()
    assert main(["componer", str(plano), "--config", str(_config(entorno, EDITOR))]) == 1
    assert 'falta la sección "componer"' in capsys.readouterr().err


# --- accesos directos ---------------------------------------------------------------------------

def _bat(nombre: str) -> str:
    contenido = (RAIZ / nombre).read_bytes()
    assert b"\r\n" in contenido and b"\n" not in contenido.replace(b"\r\n", b"")  # CRLF
    return contenido.decode("utf-8")


def test_acceso_directo_editor():
    texto = _bat("Abrir editor.bat")
    assert 'if exist ".venv\\Scripts\\python.exe"' in texto
    assert 'set "PY=python"' in texto
    assert "-m componedor.cli editor --config componedor.json --sobrescribir" in texto
    # Después del editor, el servidor local; si no arranca, el editor sin servidor, como antes.
    lineas = texto.splitlines()
    i_servidor = lineas.index('"%PY%" -m componedor.cli servidor --config componedor.json')
    assert lineas[i_servidor + 1] == "if errorlevel 1 goto :sin_servidor"
    i_sin = lineas.index(":sin_servidor")
    assert i_sin > i_servidor and 'start "" "editor\\editor.html"' in lineas[i_sin:]
    assert "pause" in lineas[i_sin:]


def test_acceso_directo_componer():
    texto = _bat("Componer.bat")
    assert 'set "PLANO=%~1"' in texto  # arrastrar un plano.json sobre el .bat
    assert 'set /p "PLANO=> "' in texto  # doble clic: pregunta por el plano
    assert 'if not exist "%PY%" set "PY=python"' in texto
    assert ('componer "%PLANO%" --config componedor.json --sobrescribir --codigo-avisos'
            in texto)
    assert f'if "%CODIGO%"=="{CODIGO_AVISOS}" goto :avisos' in texto
    assert 'start "" "resultados\\%NOMBRE%.pdf"' in texto
    # Sin bloques ( ... ) que usen la ruta: un nombre con paréntesis los rompería.
    lineas = texto.splitlines()
    assert not any(l.rstrip().endswith("(") for l in lineas)
    # Con avisos o errores espera una tecla; con error no abre nada.
    i_avisos, i_abrir = lineas.index(":avisos"), lineas.index(":abrir")
    assert "pause" in lineas[i_avisos:i_abrir]
    assert lineas[lineas.index('if "%CODIGO%"=="3" goto :avisos') + 1:i_avisos].count("pause") == 1
