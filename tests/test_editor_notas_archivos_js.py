"""Notas típicas que ya entran por rotulo.notas.archivos (ajuste de la subfase 4.3c), con Node:

- «mismo archivo»: el editor compara la ruta de "archivos" con la de cada .txt del catálogo vista
  desde la carpeta del plano.json; se compara con lo que hace `componer` (la ruta resuelta desde
  la carpeta del plano, `os.path.samefile`), con barras invertidas, «.», «..», mayúsculas y ruta
  absoluta; un .txt con el mismo contenido en OTRA carpeta no cuenta;
- «mismo texto»: el aviso «esta nota ya viene en …» sale para las mismas notas adicionales que
  repiten el texto de una nota de esos .txt según `notas.leer_notas` (espacios y número propio
  normalizados como en Python);
- esas notas típicas no se pueden marcar ni se enlazan al abrir un plano.
Archivos sintéticos en tmp."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

import componedor
from componedor.datos_editor import construir_datos_editor
from componedor.notas import leer_notas
from conftest import ARIAL, crear_paquete_real, escribir_formato, requiere_arial, rotulo_a1

NODE = shutil.which("node")
pytestmark = [pytest.mark.skipif(NODE is None, reason="Node no está instalado"), requiere_arial]
CARPETA_JS = Path(componedor.__file__).parent / "editor"

GENERALES = "LAS COTAS ESTÁN EN METROS.\n2. LAS ABSCISAS SE MIDEN SOBRE EL EJE.\nVER PLANTA:\n- K0+000.\n"
DRENAJE = "LAS CUNETAS SERÁN EN CONCRETO.\nLAS ALCANTARILLAS TENDRÁN PENDIENTE DEL 2 %.\n"


def js(codigo: str, entrada=None):
    script = (
        f"const N = require({json.dumps(str(CARPETA_JS / 'editor_notas.js'))});"
        "const entrada = JSON.parse(require('fs').readFileSync(0, 'utf8'));"
        f"const salida = (function () {{ {codigo} }})();"
        "process.stdout.write(JSON.stringify(salida === undefined ? null : salida));"
    )
    r = subprocess.run([NODE, "-e", script], input=json.dumps(entrada), capture_output=True,
                       text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


@pytest.fixture(scope="module")
def entorno(tmp_path_factory):
    raiz = tmp_path_factory.mktemp("notas_archivos")
    notas = raiz / "notas"
    (notas / "vias").mkdir(parents=True)
    (notas / "hidraulica").mkdir()
    (notas / "vias" / "generales.txt").write_text(GENERALES, encoding="utf-8")
    (notas / "hidraulica" / "drenaje.txt").write_text(DRENAJE, encoding="utf-8")
    (notas / "raiz.txt").write_text("NOTA DE LA RAÍZ.\n", encoding="utf-8")
    (raiz / "otra").mkdir()  # mismo contenido, OTRO archivo
    (raiz / "otra" / "generales.txt").write_text(GENERALES, encoding="utf-8")
    ruta = escribir_formato(raiz / "formato.json", rotulo=rotulo_a1(fuente={"archivo": str(ARIAL)}))
    crear_paquete_real(raiz / "input", "a")
    editor = raiz / "editor"  # aquí va el plano.json
    editor.mkdir()
    datos, _ = construir_datos_editor(raiz / "input", ruta, editor, carpeta_notas=notas)
    return {"raiz": raiz, "editor": editor, "notas": notas, "catalogo": datos["rotulo"]["notas"]}


def test_rutas_del_catalogo_vistas_desde_el_plano(entorno):
    archivos = {a["archivo"]: a for g in entorno["catalogo"]["grupos"] for a in g["archivos"]}
    assert archivos["vias/generales.txt"]["ruta_plano"] == "../notas/vias/generales.txt"
    assert archivos["raiz.txt"]["ruta_plano"] == "../notas/raiz.txt"
    assert archivos["hidraulica/drenaje.txt"]["absoluta"] == \
        (entorno["notas"] / "hidraulica" / "drenaje.txt").resolve().as_posix()


def _incluidos_python(entorno, archivos_plan) -> dict[str, str]:
    """Como `componer`: cada ruta resuelta desde la carpeta del plano; mismo archivo en disco."""
    resultado = {}
    for g in entorno["catalogo"]["grupos"]:
        for a in g["archivos"]:
            txt = entorno["notas"] / a["archivo"]
            for ruta in archivos_plan:
                destino = Path(ruta) if Path(ruta).is_absolute() else entorno["editor"] / ruta
                if destino.is_file() and os.path.samefile(destino, txt):
                    resultado[a["archivo"]] = ruta
                    break
    return resultado


@pytest.mark.parametrize("archivos_plan", [
    ["../notas/vias/generales.txt"],
    ["..\\notas\\vias\\generales.txt", "./../notas/./hidraulica/../hidraulica/drenaje.txt"],
    ["../NOTAS/RAIZ.TXT"],  # Windows no distingue mayúsculas
    ["../otra/generales.txt", "../notas/no_existe.txt", "notas/raiz.txt"],  # ninguno
    ["ABSOLUTA_DRENAJE"],
])
def test_mismo_archivo_que_componer(entorno, archivos_plan):
    absoluta = str((entorno["notas"] / "hidraulica" / "drenaje.txt").resolve())
    archivos_plan = [absoluta if a == "ABSOLUTA_DRENAJE" else a for a in archivos_plan]
    if os.name != "nt" and any(a != a.lower() and "NOTAS" in a for a in archivos_plan):
        pytest.skip("sin distinguir mayúsculas solo en Windows")
    esperado = _incluidos_python(entorno, archivos_plan)
    r = js("return [...N.archivosIncluidos(entrada.archivos, entrada.catalogo)];",
           {"archivos": archivos_plan, "catalogo": entorno["catalogo"]})
    assert dict(r) == esperado


ADICIONALES = [
    "LAS COTAS ESTÁN EN METROS.",                       # igual a generales, línea 1
    "  LAS   CUNETAS SERÁN EN CONCRETO.  ",             # espacios de más: igual (drenaje, 1)
    "7. LAS ABSCISAS SE MIDEN SOBRE EL EJE.",           # número propio en las dos: igual (línea 2)
    {"texto": "VER PLANTA:", "vinetas": ["OTRA."]},    # mismo texto (las viñetas no cuentan)
    "LAS COTAS ESTÁN EN METROS",                        # sin punto: distinta
    "las cotas están en metros.",                       # mayúsculas: distinta
    "NOTA NUEVA.",
]


def test_mismo_texto_que_python(entorno):
    archivos_plan = ["../notas/vias/generales.txt", "../notas/hidraulica/drenaje.txt",
                     "../otra/generales.txt"]
    notas, _, problemas = leer_notas({"archivos": archivos_plan, "adicionales": ADICIONALES},
                                     entorno["editor"])
    assert problemas == []
    # Python: notas de los .txt (solo los del catálogo: el editor no puede leer otros) y adicionales.
    origen_a_ruta = {"generales.txt": archivos_plan[0], "drenaje.txt": archivos_plan[1]}
    de_archivos = []
    for n in notas:
        nombre, _, linea = n.origen.partition(", línea ")
        if linea and nombre in origen_a_ruta and not any(d[0] == n.texto for d in de_archivos):
            de_archivos.append((n.texto, origen_a_ruta[nombre], linea))
    esperado = []
    for n in notas:
        if n.origen.startswith("adicionales["):
            igual = next((d for d in de_archivos if d[0] == n.texto), None)
            if igual:
                esperado.append(f"rotulo.notas.{n.origen}: esta nota ya viene en {igual[1]} "
                                f"(línea {igual[2]}); saldría dos veces en el plano")
    assert len(esperado) == 4
    r = js("return N.avisosRepetidas(entrada.valor, entrada.catalogo);",
           {"valor": {"archivos": archivos_plan, "adicionales": ADICIONALES},
            "catalogo": entorno["catalogo"]})
    assert r == esperado
    # Y van en validarNotas, después de los avisos de Python (número propio) y sin errores.
    v = js("return N.validarNotas(entrada.valor, null, entrada.catalogo);",
           {"valor": {"archivos": archivos_plan, "adicionales": ADICIONALES},
            "catalogo": entorno["catalogo"]})
    assert v["errores"] == [] and v["avisos"][-4:] == esperado
    assert v["avisos"][0].startswith("Advertencia: la nota de adicionales[2] traía su propio número")


def test_sin_archivos_del_catalogo_no_hay_avisos(entorno):
    r = js("return N.avisosRepetidas(entrada.valor, entrada.catalogo);",
           {"valor": {"archivos": ["../otra/generales.txt"], "adicionales": ADICIONALES},
            "catalogo": entorno["catalogo"]})
    assert r == []  # mismo contenido pero OTRO archivo, que el editor no puede leer


def test_incluidas_no_se_marcan_ni_se_enlazan(entorno):
    r = js("""
        const cat = entrada.catalogo;
        const archivos = ["../notas/vias/generales.txt"];
        const incluidas = [...N.clavesIncluidas(archivos, cat)];
        const marcar = N.marcar([], "vias/generales.txt, línea 1", cat, archivos).length;
        const otra = N.marcar([], "hidraulica/drenaje.txt, línea 1", cat, archivos).length;
        const l = N.lista({archivos, adicionales: ["LAS COTAS ESTÁN EN METROS.", "LAS CUNETAS SERÁN EN CONCRETO."]}, cat);
        return {incluidas, marcar, otra, claves: l.items.map((x) => x.clave),
                notas: N.notasDeArchivos(archivos, cat)};
    """, {"catalogo": entorno["catalogo"]})
    assert r["incluidas"] == ["vias/generales.txt, línea 1", "vias/generales.txt, línea 2",
                              "vias/generales.txt, línea 3"]
    assert r["marcar"] == 0 and r["otra"] == 1
    assert r["claves"] == [None, "hidraulica/drenaje.txt, línea 1"]  # la incluida no se enlaza
    assert [n["linea"] for n in r["notas"]] == [1, 2, 3]
    assert r["notas"][1]["texto"] == "LAS ABSCISAS SE MIDEN SOBRE EL EJE."  # sin número propio
