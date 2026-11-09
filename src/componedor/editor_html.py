"""Editor HTML de planos: un solo archivo autocontenido (subfase 3.3).

`generar_editor` reutiliza `datos_editor.preparar_editor` (editor_datos.json, plantilla.png,
miniaturas) y escribe además `editor.html`: HTML + CSS + JS + datos + imágenes en base64,
para abrirlo con doble clic (file://), sin servidor, sin internet y sin ninguna URL externa.

Los recursos (editor.html, editor.css, editor_logica.js, editor_ui.js) están en
`componedor/editor/`. Las plantillas de texto de las advertencias se incrustan desde
`advertencias.py`, así el editor muestra exactamente los mismos textos que `componer`.
"""

import base64
import copy
import json
from importlib import resources
from pathlib import Path

from componedor.advertencias import PLANTILLAS
from componedor.datos_editor import preparar_editor

ARCHIVO_HTML = "editor.html"
MARCADORES = {
    "/*@@CSS@@*/": "editor.css",
    "/*@@JS_LOGICA@@*/": "editor_logica.js",
    "/*@@JS_UI@@*/": "editor_ui.js",
}
MARCADOR_DATOS = "@@DATOS_EDITOR@@"


def generar_editor(carpeta_paquetes: Path | str, ruta_formato: Path | str,
                   carpeta_salida: Path | str, sobrescribir: bool = False) -> Path:
    """Escribe en `carpeta_salida` los datos del editor y `editor.html`. Devuelve su ruta.

    Mismas reglas que `preparar-editor`: no pisa una carpeta con contenido salvo con
    `sobrescribir`, y en ese caso reemplaza solo lo que genera.
    """
    carpeta_salida = Path(carpeta_salida)
    datos = preparar_editor(carpeta_paquetes, ruta_formato, carpeta_salida, sobrescribir)
    ruta = carpeta_salida / ARCHIVO_HTML
    ruta.write_text(construir_html(datos, carpeta_salida), encoding="utf-8", newline="\n")
    return ruta


def construir_html(datos: dict, carpeta_salida: Path) -> str:
    """El HTML completo con todo incrustado. Las imágenes se leen de `carpeta_salida`."""
    incrustados = copy.deepcopy(datos)
    incrustados["imagen_plantilla"]["data_url"] = _data_url(
        carpeta_salida / datos["imagen_plantilla"]["archivo"])
    for detalle in incrustados["detalles"]:
        detalle["miniatura"]["data_url"] = _data_url(carpeta_salida / detalle["miniatura"]["archivo"])
    rosa = incrustados.get("rosa_vientos")
    if rosa and rosa.get("imagen"):
        rosa["imagen"]["data_url"] = _data_url(carpeta_salida / rosa["imagen"]["archivo"])
    incrustados["advertencias"] = PLANTILLAS
    # Solo informativa: dentro de un HTML no se conoce la ruta real del disco.
    incrustados["carpeta_editor"] = str(Path(carpeta_salida).resolve())

    html = _recurso("editor.html")
    for marcador, archivo in MARCADORES.items():
        html = html.replace(marcador, _recurso(archivo))
    # "</" se escribe "<\/" (equivalente en JSON) para que nada cierre el <script> antes.
    json_datos = json.dumps(incrustados, ensure_ascii=False).replace("</", "<\\/")
    return html.replace(MARCADOR_DATOS, json_datos)


def datos_incrustados(html: str) -> dict:
    """Los datos del editor tal como quedaron dentro de `html` (para pruebas y revisión)."""
    inicio = html.index('<script id="datos-editor" type="application/json">')
    inicio = html.index(">", inicio) + 1
    fin = html.index("</script>", inicio)
    return json.loads(html[inicio:fin])


def _recurso(nombre: str) -> str:
    return resources.files("componedor").joinpath("editor", nombre).read_text(encoding="utf-8")


def _data_url(ruta: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(ruta.read_bytes()).decode("ascii")
