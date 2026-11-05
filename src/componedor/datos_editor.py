"""Datos e imágenes para el editor HTML de planos (subfase 3.2; el editor es la 3.3).

`preparar_editor` escribe en una carpeta:
  - editor_datos.json: hoja, zonas (solo `area_dibujo` editable), elementos fijos de la
    plantilla, detalles aceptados (con su miniatura) y rechazados (con sus motivos);
  - plantilla.png: la hoja base con el rótulo, SIN detalles;
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
from componedor.composicion import hoja_base
from componedor.comprobacion_dibujo import tiene_fondo_de_pagina
from componedor.formato import Formato, cargar_formato
from componedor.inventario import ACEPTADO, EntradaInventario, construir_inventario

VERSION = 1
ZONA_EDITABLE = "area_dibujo"
ARCHIVO_DATOS = "editor_datos.json"
ARCHIVO_PLANTILLA = "plantilla.png"
CARPETA_MINIATURAS = "miniaturas"
MAX_PX_HOJA = 1600
MAX_PX_MINIATURA = 1400  # nítida al acercar en el editor


def construir_datos_editor(carpeta_paquetes: Path | str, ruta_formato: Path | str,
                           carpeta_salida: Path | str) -> tuple[dict, list[EntradaInventario]]:
    """Estructura de editor_datos.json (sin los tamaños en píxeles de las imágenes, que se
    agregan al generarlas) y las entradas del inventario. Las rutas van relativas a
    `carpeta_salida`, que es donde el editor guardará el plano.json."""
    carpeta_salida = Path(carpeta_salida)
    formato = cargar_formato(ruta_formato)
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
        "detalles": detalles,
        "rechazados": rechazados,
    }
    return datos, entradas


def preparar_editor(carpeta_paquetes: Path | str, ruta_formato: Path | str,
                    carpeta_salida: Path | str, sobrescribir: bool = False,
                    max_px_hoja: int = MAX_PX_HOJA,
                    max_px_miniatura: int = MAX_PX_MINIATURA) -> dict:
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

    datos, entradas = construir_datos_editor(carpeta_paquetes, ruta_formato, carpeta_salida)
    formato = cargar_formato(ruta_formato)

    miniaturas = carpeta_salida / CARPETA_MINIATURAS
    miniaturas.mkdir(parents=True, exist_ok=True)
    for vieja in miniaturas.glob("*.png"):
        vieja.unlink()

    datos["imagen_plantilla"].update(
        _png_plantilla(formato, carpeta_salida / ARCHIVO_PLANTILLA, max_px_hoja))
    aceptadas = [e for e in entradas if e.estado == ACEPTADO]
    for detalle, entrada in zip(datos["detalles"], aceptadas):
        detalle["miniatura"].update(_png_detalle(
            entrada.ruta_pdf, carpeta_salida / detalle["miniatura"]["archivo"], max_px_miniatura,
            transparente=not detalle["tiene_fondo"]))

    (carpeta_salida / ARCHIVO_DATOS).write_text(
        json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return datos


def _png_plantilla(formato: Formato, ruta: Path, max_px: int) -> dict:
    """La hoja base (rótulo, sin detalles) como PNG, con su lado mayor en `max_px`."""
    doc, _ = hoja_base(formato)
    try:
        return _png(doc[0], ruta, max_px)
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
