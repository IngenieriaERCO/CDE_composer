"""Editor HTML de planos: un solo archivo autocontenido (subfase 3.3).

`generar_editor` reutiliza `datos_editor.preparar_editor` (editor_datos.json, plantilla.png y
.svg, rosa.png, miniaturas, símbolos) y escribe `editor.html`: HTML + CSS + JS + datos +
imágenes en base64, para abrirlo con doble clic (file://), sin servidor, sin internet y sin
ninguna URL externa. Esos subproductos se arman en una carpeta temporal y se descartan: en la
carpeta del editor queda SOLO editor.html (más los plano.json que guarde el usuario). Quien
quiera verlos usa el comando `preparar-editor`. `componer` no lee ninguno.

Los recursos (editor.html, editor.css, editor_logica.js, editor_ui.js) están en
`componedor/editor/`. Las plantillas de texto de las advertencias se incrustan desde
`advertencias.py`, así el editor muestra exactamente los mismos textos que `componer`.
"""

import base64
import copy
import json
import tempfile
from importlib import resources
from pathlib import Path

from componedor.advertencias import PLANTILLAS
from componedor.datos_editor import (
    ARCHIVO_DATOS,
    ARCHIVO_PLANTILLA,
    ARCHIVO_PLANTILLA_SVG,
    ARCHIVO_ROSA,
    CARPETA_MINIATURAS,
    preparar_editor,
)
from componedor.datos_rotulo_editor import CARPETA_SIMBOLOS
from componedor.recorte_detalle import MARGEN_POR_DEFECTO_MM

ARCHIVO_HTML = "editor.html"
MARCADORES = {
    "/*@@CSS@@*/": "editor.css",
    "/*@@JS_SIN_AUTORRELLENO@@*/": "editor_sin_autorrelleno.js",  # el primero: vigila los cuadros
    "/*@@JS_BLOQUES@@*/": "editor_bloques.js",  # antes de la lógica: la usa (plano versión 3)
    "/*@@JS_ORTOFOTO@@*/": "editor_ortofoto.js",  # antes de la lógica: la usa (plano versión 4)
    "/*@@JS_LOCALIZACION@@*/": "editor_localizacion.js",  # imagen de localización (rótulo)
    "/*@@JS_LOGICA@@*/": "editor_logica.js",
    "/*@@JS_ROTULO@@*/": "editor_rotulo.js",
    "/*@@JS_MAQUETACION@@*/": "editor_maquetacion.js",
    "/*@@JS_FORMULARIOS@@*/": "editor_formularios.js",
    "/*@@JS_FIRMA@@*/": "editor_firma.js",
    "/*@@JS_DIALOGO_FIRMA@@*/": "editor_dialogo_firma.js",
    "/*@@JS_PANEL_ROTULO@@*/": "editor_panel_rotulo.js",
    "/*@@JS_NOTAS@@*/": "editor_notas.js",
    "/*@@JS_PANEL_NOTAS@@*/": "editor_panel_notas.js",
    "/*@@JS_MUESTRAS@@*/": "editor_muestras.js",  # antes de convenciones y vista previa (9a)
    "/*@@JS_CONVENCIONES@@*/": "editor_convenciones.js",
    "/*@@JS_VISTA_PREVIA@@*/": "editor_vista_previa.js",
    "/*@@JS_LIENZO_ROTULO@@*/": "editor_lienzo_rotulo.js",
    "/*@@JS_PANEL_CONVENCIONES@@*/": "editor_panel_convenciones.js",
    "/*@@JS_UI@@*/": "editor_ui.js",
    "/*@@JS_SERVIDOR@@*/": "editor_servidor.js",
    "/*@@JS_DXF@@*/": "editor_dxf.js",
    "/*@@JS_ZONAS@@*/": "editor_zonas.js",  # Fase 10d: lógica de «Zonas del modelo»
    "/*@@JS_PANEL_DXF@@*/": "editor_panel_dxf.js",
    "/*@@JS_PANEL_ZONAS@@*/": "editor_panel_zonas.js",  # el diálogo «Zonas del modelo»
    "/*@@JS_PANEL_ORTOFOTO@@*/": "editor_panel_ortofoto.js",
    "/*@@JS_PANEL_LOCALIZACION@@*/": "editor_panel_localizacion.js",
}
MARCADOR_DATOS = "@@DATOS_EDITOR@@"
# Lo que dejaban versiones anteriores junto a editor.html; se quita al regenerar.
SUBPRODUCTOS = (ARCHIVO_DATOS, ARCHIVO_PLANTILLA, ARCHIVO_PLANTILLA_SVG, ARCHIVO_ROSA)
CARPETAS_SUBPRODUCTOS = (CARPETA_MINIATURAS, CARPETA_SIMBOLOS)


def generar_editor(carpeta_paquetes: Path | str, ruta_formato: Path | str,
                   carpeta_salida: Path | str, sobrescribir: bool = False,
                   carpeta_notas: Path | str | None = None,
                   carpeta_firmas: Path | str | None = None,
                   ruta_proyecto: Path | str | None = None,
                   carpeta_simbolos: Path | str | None = None,
                   margen_detalle_mm: float = MARGEN_POR_DEFECTO_MM) -> Path:
    """Escribe `editor.html` en `carpeta_salida` (nada más). Devuelve su ruta.

    Mismas reglas que `preparar-editor`: no pisa una carpeta con contenido salvo con
    `sobrescribir`, y en ese caso reemplaza solo lo que genera y quita los subproductos que
    dejaban versiones anteriores (SUBPRODUCTOS y los PNG de CARPETAS_SUBPRODUCTOS, por su nombre
    exacto; un plano.json u otro archivo del usuario nunca se toca). `carpeta_notas`: notas
    típicas para el catálogo del rótulo (se incrustan). `carpeta_firmas`: solo los NOMBRES de
    las personas (las imágenes nunca). `ruta_proyecto`: proyecto.json para prellenar (4.3b).
    """
    carpeta_salida = Path(carpeta_salida)
    with tempfile.TemporaryDirectory(prefix="componedor_editor_") as temporal:
        datos = preparar_editor(carpeta_paquetes, ruta_formato, carpeta_salida, sobrescribir,
                                carpeta_notas=carpeta_notas, carpeta_firmas=carpeta_firmas,
                                ruta_proyecto=ruta_proyecto, carpeta_archivos=temporal,
                                carpeta_simbolos=carpeta_simbolos,
                                margen_detalle_mm=margen_detalle_mm)
        html = construir_html(datos, Path(temporal), carpeta_salida)
    carpeta_salida.mkdir(parents=True, exist_ok=True)
    ruta = carpeta_salida / ARCHIVO_HTML
    ruta.write_text(html, encoding="utf-8", newline="\n")
    _quitar_subproductos(carpeta_salida)
    return ruta


def _quitar_subproductos(carpeta: Path) -> None:
    """Quita lo que dejaban versiones anteriores del editor, solo por su nombre exacto."""
    for nombre in SUBPRODUCTOS:
        (carpeta / nombre).unlink(missing_ok=True)
    for nombre in CARPETAS_SUBPRODUCTOS:
        sub = carpeta / nombre
        if sub.is_dir():
            for png in sub.glob("*.png"):
                png.unlink()
            if not any(sub.iterdir()):
                sub.rmdir()


def construir_html(datos: dict, carpeta_archivos: Path,
                   carpeta_salida: Path | None = None) -> str:
    """El HTML completo con todo incrustado. Las imágenes se leen de `carpeta_archivos`;
    `carpeta_salida` (por defecto la misma) es la carpeta del editor, solo informativa."""
    carpeta_salida = carpeta_archivos if carpeta_salida is None else carpeta_salida
    incrustados = copy.deepcopy(datos)
    # La plantilla en vector (4.3f) si está; si no, el PNG (datos anteriores).
    svg = datos["imagen_plantilla"].get("svg")
    incrustados["imagen_plantilla"]["data_url"] = (
        _data_url(carpeta_archivos / svg["archivo"], "image/svg+xml") if svg
        else _data_url(carpeta_archivos / datos["imagen_plantilla"]["archivo"]))
    for detalle in incrustados["detalles"]:
        detalle["miniatura"]["data_url"] = _data_url(carpeta_archivos / detalle["miniatura"]["archivo"])
    rosa = incrustados.get("rosa_vientos")
    if rosa and rosa.get("imagen"):
        rosa["imagen"]["data_url"] = _data_url(carpeta_archivos / rosa["imagen"]["archivo"])
    for simbolo in (incrustados.get("rotulo") or {}).get("simbolos", []):
        simbolo["imagen"]["data_url"] = _data_url(carpeta_archivos / simbolo["imagen"]["archivo"])
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


def _data_url(ruta: Path, tipo: str = "image/png") -> str:
    return f"data:{tipo};base64," + base64.b64encode(ruta.read_bytes()).decode("ascii")
