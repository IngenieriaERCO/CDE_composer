"""Datos e imágenes para el editor HTML de planos (subfase 3.2; el editor es la 3.3).

`preparar_editor` escribe en una carpeta:
  - editor_datos.json: hoja, zonas (solo `area_dibujo` editable), elementos fijos de la
    plantilla, detalles aceptados (con su miniatura) y rechazados (con sus motivos);
  - plantilla.png: la hoja base con el rótulo, SIN detalles y SIN la rosa de los vientos
    (subfase 4.1: la rosa se mueve, así que el editor la dibuja aparte);
  - rosa.png: la rosa sola, transparente (si el formato tiene plantilla y declara la rosa);
  - miniaturas/<id>.png: una por detalle aceptado (transparente si el PDF no trae fondo de
    página; opaca si es un paquete antiguo con fondo blanco).
Estructura: docs/formato_editor_datos.md.

Las imágenes son SOLO para mostrar en el editor; el PDF final siempre lo genera `componer`,
vectorial, y `componer` revalida todo: estos datos nunca son la fuente de la verdad.
La aceptación de cada paquete sale de `inventario.construir_inventario` (que usa
`importador.evaluar_paquete`): aquí no se repite ninguna validación.
"""

import json
import os
from pathlib import Path

import pymupdf

from componedor.cad_a_papel import limites_dibujo_en_papel
from componedor.composicion import hoja_base_con_rosa
from componedor.comprobacion_dibujo import tiene_fondo_de_pagina
from componedor.datos_rotulo_editor import (
    catalogo_notas,
    definicion_editor,
    rutas_desde_el_plano,
    simbolos_editor,
    tabla_anchos,
)
from componedor.firmas import personas_firmas
from componedor.formato import Formato, cargar_formato
from componedor.fuente import FuenteInvalida, cargar_fuente
from componedor.proyecto import ProyectoInvalido, leer_proyecto
from componedor.inventario import ACEPTADO, EntradaInventario, construir_inventario
from componedor.rosa import NOMBRE as ROSA
from componedor.rosa import documento_rosa_sola
from componedor.transformaciones import rect_papel_a_pdf

VERSION = 1
ZONA_EDITABLE = "area_dibujo"
ARCHIVO_DATOS = "editor_datos.json"
ARCHIVO_PLANTILLA = "plantilla.png"
ARCHIVO_ROSA = "rosa.png"
CARPETA_MINIATURAS = "miniaturas"
MAX_PX_HOJA = 1600
MAX_PX_MINIATURA = 1400  # nítida al acercar en el editor
MAX_PX_ROSA = 600


def construir_datos_editor(carpeta_paquetes: Path | str, ruta_formato: Path | str,
                           carpeta_salida: Path | str, carpeta_notas: Path | str | None = None,
                           carpeta_firmas: Path | str | None = None,
                           ruta_proyecto: Path | str | None = None,
                           ) -> tuple[dict, list[EntradaInventario]]:
    """Estructura de editor_datos.json (sin los tamaños en píxeles de las imágenes, que se
    agregan al generarlas) y las entradas del inventario. Las rutas van relativas a
    `carpeta_salida`, que es donde el editor guardará el plano.json. `carpeta_notas`: las
    notas típicas para el catálogo del rótulo (subfase 4.3a). `carpeta_firmas`: de ella solo
    se toman los NOMBRES de las personas; `ruta_proyecto`: proyecto.json para prellenar un
    plano nuevo (4.3b; si no es válido, `ProyectoInvalido`)."""
    carpeta_salida = Path(carpeta_salida)
    formato = cargar_formato(ruta_formato)
    proyecto = leer_proyecto(ruta_proyecto, formato.rotulo) if ruta_proyecto is not None else None
    entradas = construir_inventario(carpeta_paquetes, formato, ZONA_EDITABLE)

    detalles, rechazados, ids = [], [], set()
    for e in entradas:
        if e.estado != ACEPTADO:
            rechazados.append({
                "prefijo": e.prefijo,
                "manifiesto": _relativa(e.ruta_manifiesto, carpeta_salida),
                "motivos": list(e.motivos),
            })
            continue
        ident = _id_unico(e.prefijo, ids)
        ancho, alto = e.tamano_pagina_mm
        # page_bounds_mm (página, Y abajo) en papel relativo a la esquina inferior izquierda
        # de la página del detalle (Y arriba). La inversión de Y la hace transformaciones.py.
        dibujo = limites_dibujo_en_papel(e.limites_pagina_mm, alto, (0.0, 0.0))
        with pymupdf.open(e.ruta_pdf) as doc:
            tiene_fondo = tiene_fondo_de_pagina(doc[0])
        detalles.append({
            "id": ident,
            "manifiesto": _relativa(e.ruta_manifiesto, carpeta_salida),
            "bloque": e.bloque,
            "escala": e.escala,
            "tamano_pagina_mm": [ancho, alto],
            "limites_dibujo_mm": list(dibujo),
            "cabe": bool(e.cabe),
            "tiene_fondo": tiene_fondo,
            "notas": list(e.notas),
            "miniatura": {"archivo": f"{CARPETA_MINIATURAS}/{ident}.png"},
        })

    datos = {
        "version": VERSION,
        "formato": _relativa(Path(ruta_formato), carpeta_salida),
        "hoja": {"ancho_mm": formato.ancho_mm, "alto_mm": formato.alto_mm},
        "imagen_plantilla": {"archivo": ARCHIVO_PLANTILLA},
        "zonas": [{"nombre": nombre, "rect_mm": list(rect), "editable": nombre == ZONA_EDITABLE}
                  for nombre, rect in formato.zonas.items()],
        "elementos_plantilla": [{"nombre": el.nombre, "rect_mm": list(el.rect)}
                                for el in formato.elementos_plantilla],
        # Subfase 4.1 (aditivo): la rosa se puede mover u ocultar. rect_mm es su sitio original
        # en la plantilla; "imagen" solo si hay plantilla de donde sacarla.
        "rosa_vientos": _datos_rosa(formato),
        "detalles": detalles,
        "rechazados": rechazados,
        # Subfase 4.3a (aditivo): definición del rótulo, tabla de anchos de la fuente, catálogo
        # de notas y símbolos (los PNG se agregan en preparar_editor). Nunca firmas.
        "rotulo": _datos_rotulo(formato, carpeta_notas, carpeta_firmas, proyecto, carpeta_salida),
    }
    return datos, entradas


def _datos_rotulo(formato: Formato, carpeta_notas, carpeta_firmas=None,
                  proyecto: dict | None = None, carpeta_salida=None) -> dict | None:
    if formato.rotulo is None:
        return None
    avisos = []
    # Subfase 4.3b (aditivo): nombres de personas (nunca imágenes) y proyecto.json.
    personas = None
    if carpeta_firmas is not None:
        personas, avisos_firmas = personas_firmas(carpeta_firmas)
        avisos += avisos_firmas
    try:
        fuente = tabla_anchos(cargar_fuente(formato.rotulo.fuente))
    except FuenteInvalida as e:
        fuente = None
        avisos.append(f"fuente: {e}")
    notas = catalogo_notas(carpeta_notas) if carpeta_notas is not None else None
    if notas is not None and carpeta_salida is not None:
        # 4.3c: cómo nombra un plano.json (en la carpeta del editor) a cada .txt del catálogo.
        rutas_desde_el_plano(notas, carpeta_notas, carpeta_salida)
    return {"definicion": definicion_editor(formato.rotulo), "fuente": fuente,
            "notas": notas, "simbolos": [], "avisos": avisos,
            "personas_firmas": personas, "proyecto": proyecto}


def _datos_rosa(formato: Formato) -> dict | None:
    elemento = formato.elemento(ROSA)
    if elemento is None:
        return None
    imagen = {"archivo": ARCHIVO_ROSA} if formato.plantilla is not None else None
    return {"nombre": ROSA, "rect_mm": list(elemento.rect), "imagen": imagen}


def preparar_editor(carpeta_paquetes: Path | str, ruta_formato: Path | str,
                    carpeta_salida: Path | str, sobrescribir: bool = False,
                    max_px_hoja: int = MAX_PX_HOJA,
                    max_px_miniatura: int = MAX_PX_MINIATURA,
                    carpeta_notas: Path | str | None = None,
                    carpeta_firmas: Path | str | None = None,
                    ruta_proyecto: Path | str | None = None) -> dict:
    """Escribe editor_datos.json, plantilla.png y miniaturas/<id>.png en `carpeta_salida`.

    No pisa una carpeta con contenido salvo con `sobrescribir`; en ese caso reemplaza solo
    lo que genera este comando (y borra las miniaturas viejas). Devuelve los datos escritos.
    """
    carpeta_salida = Path(carpeta_salida)
    if carpeta_salida.exists() and not carpeta_salida.is_dir():
        raise FileExistsError(f"'{carpeta_salida}' existe y no es una carpeta.")
    if carpeta_salida.is_dir() and any(carpeta_salida.iterdir()) and not sobrescribir:
        raise FileExistsError(
            f"La carpeta '{carpeta_salida}' ya tiene contenido. Use --sobrescribir para "
            f"reemplazar los datos del editor.")

    datos, entradas = construir_datos_editor(carpeta_paquetes, ruta_formato, carpeta_salida,
                                             carpeta_notas, carpeta_firmas, ruta_proyecto)
    formato = cargar_formato(ruta_formato)
    if datos["rotulo"] is not None:
        simbolos, avisos = simbolos_editor(formato.rotulo, carpeta_salida)
        datos["rotulo"]["simbolos"] = simbolos
        datos["rotulo"]["avisos"] += avisos

    miniaturas = carpeta_salida / CARPETA_MINIATURAS
    miniaturas.mkdir(parents=True, exist_ok=True)
    for vieja in miniaturas.glob("*.png"):
        vieja.unlink()

    datos["imagen_plantilla"].update(
        _png_plantilla(formato, carpeta_salida / ARCHIVO_PLANTILLA, max_px_hoja))
    vieja_rosa = carpeta_salida / ARCHIVO_ROSA
    if vieja_rosa.exists():
        vieja_rosa.unlink()
    if datos["rosa_vientos"] is not None and datos["rosa_vientos"]["imagen"] is not None:
        datos["rosa_vientos"]["imagen"].update(_png_rosa(formato, vieja_rosa, MAX_PX_ROSA))
    aceptadas = [e for e in entradas if e.estado == ACEPTADO]
    for detalle, entrada in zip(datos["detalles"], aceptadas):
        detalle["miniatura"].update(_png_detalle(
            entrada.ruta_pdf, carpeta_salida / detalle["miniatura"]["archivo"], max_px_miniatura,
            transparente=not detalle["tiene_fondo"]))

    (carpeta_salida / ARCHIVO_DATOS).write_text(
        json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return datos


def _png_plantilla(formato: Formato, ruta: Path, max_px: int) -> dict:
    """La hoja base (rótulo, sin detalles y sin la rosa: el editor la dibuja donde esté) como
    PNG, con su lado mayor en `max_px`. Se quita igual que en `componer` (rosa.py)."""
    doc, _, _ = hoja_base_con_rosa(formato, rosa=None)
    try:
        return _png(doc[0], ruta, max_px)
    finally:
        doc.close()


def _png_rosa(formato: Formato, ruta: Path, max_px: int) -> dict:
    """La rosa sola, transparente, recortada justo a su rectángulo (rect_mm)."""
    doc = documento_rosa_sola(formato)
    try:
        page = doc[0]
        recorte = rect_papel_a_pdf(formato.elemento(ROSA).rect, formato.alto_mm)
        zoom = max_px / max(recorte.width, recorte.height)
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=recorte, alpha=True)
        pixmap.save(ruta)
        return {"ancho_px": pixmap.width, "alto_px": pixmap.height}
    finally:
        doc.close()


def _png_detalle(ruta_pdf: Path, ruta: Path, max_px: int, transparente: bool) -> dict:
    """Miniatura del detalle: transparente si el PDF no trae fondo de página (se ve como en
    el PDF final, sin tapar lo de abajo); opaca si lo trae (paquete antiguo)."""
    with pymupdf.open(ruta_pdf) as doc:
        return _png(doc[0], ruta, max_px, transparente)


def _png(pagina: pymupdf.Page, ruta: Path, max_px: int, transparente: bool = False) -> dict:
    zoom = max_px / max(pagina.rect.width, pagina.rect.height)
    pixmap = pagina.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=transparente)
    pixmap.save(ruta)
    return {"ancho_px": pixmap.width, "alto_px": pixmap.height}


def _relativa(ruta: Path, carpeta: Path) -> str:
    """Ruta relativa a `carpeta`, con "/" (para el plano.json que escribirá el editor)."""
    try:
        return Path(os.path.relpath(Path(ruta).resolve(), Path(carpeta).resolve())).as_posix()
    except ValueError:  # otra unidad de disco en Windows: no hay ruta relativa
        return Path(ruta).resolve().as_posix()


def _id_unico(prefijo: str, usados: set[str]) -> str:
    ident, n = prefijo, 2
    while ident in usados:
        ident, n = f"{prefijo}_{n}", n + 1
    usados.add(ident)
    return ident
