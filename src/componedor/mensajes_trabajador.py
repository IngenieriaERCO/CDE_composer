"""Errores del trabajador → lo que lee el usuario en el editor.

El trabajador manda `code`, `message`, `advice` y `details` (contrato §8). Casi todos los
mensajes ya son para personas, pero dos traen el texto técnico de Python:

- `INTERNAL` («Error inesperado del exportador (TypeError): 'NoneType' object…»): el
  exportador encontró algo que no sabe manejar;
- `DXF_INVALID` («No se pudo leer el DXF: File '…' is not a DXF file»): ezdxf no pudo leerlo.

Y los errores por trabajo de `export` (`EXPORT_FAILED`…) traen el mensaje de la terminal.

Para esos, el editor muestra un mensaje CLARO según lo que se estaba haciendo (cargar, vista
previa, exportar) y guarda el texto técnico en `detalle`, junto con la ruta del registro del
trabajador (`registro`), para el botón «Ver detalle».

El consejo «Repita el pedido» solo se deja si el fallo puede no repetirse (memoria, disco, un
archivo que AutoCAD estaba guardando). Un error de programa con el mismo DXF sale igual cada
vez: entonces el consejo es avisar con el detalle.
"""

from pathlib import Path

# Tipos de excepción de Python que pueden NO repetirse al volver a intentar.
TRANSITORIOS = {"MemoryError", "OSError", "PermissionError", "TimeoutError", "InterruptedError",
                "BlockingIOError", "ConnectionError", "BrokenPipeError"}
QUE = {"cargar_dxf": "leer el DXF", "previa": "dibujar la vista previa",
       "exportar": "exportar el bloque"}
AVISAR = ("Es un fallo del exportador con este dibujo: repetir no sirve. Copie el detalle "
          "(«Ver detalle») y el registro, y avise a quien mantiene el Exportador Vectorial.")


def ruta_para_mostrar(ruta: Path | str | None) -> str | None:
    """La ruta del registro como la ve el usuario: relativa a la carpeta desde donde corre el
    servidor si está dentro (data\\cache_exportador\\trabajador.log), si no, absoluta."""
    if ruta is None:
        return None
    ruta = Path(ruta)
    try:
        return str(ruta.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(ruta)


def para_el_usuario(tipo_tarea: str, codigo: str, mensaje: str, consejo: str | None,
                    detalles: dict | None, registro: Path | str | None) -> dict:
    """{codigo, mensaje, consejo, detalle, registro} para la foto de la tarea."""
    detalles = detalles if isinstance(detalles, dict) else {}
    que = QUE.get(tipo_tarea, "atender el pedido")
    tipo = str(detalles.get("type") or "")
    tecnico = None
    if codigo == "INTERNAL":
        tecnico = mensaje
        mensaje = f"No se pudo {que}: el exportador encontró un objeto que no entiende."
        consejo = ("Vuelva a intentarlo; si se repite, copie el detalle y avise."
                   if tipo in TRANSITORIOS else AVISAR)
    elif codigo == "DXF_INVALID":
        tecnico = mensaje
        mensaje = ("No se pudo leer el DXF: el archivo está dañado o no es un DXF que el "
                   "exportador sepa leer.")
        consejo = ("Si AutoCAD lo estaba guardando, espere a que termine y vuelva a cargarlo. Si "
                   "no, ábralo en AutoCAD, revíselo (AUDIT) y guárdelo de nuevo como DXF.")
    elif codigo in ("EXPORT_FAILED", "VALIDATION_FAILED", "CRITICAL_NOTICE"):
        tecnico = mensaje
        mensaje = {"EXPORT_FAILED": "No se pudo exportar el bloque: el exportador no pudo "
                                    "dibujarlo.",
                   "VALIDATION_FAILED": "El exportador dibujó el bloque, pero el paquete no pasó "
                                        "sus propias comprobaciones: no se publicó.",
                   "CRITICAL_NOTICE": "El exportador se detuvo por un aviso crítico (por ejemplo "
                                      "una referencia externa o un bloque sin resolver)."}[codigo]
        consejo = AVISAR if codigo != "CRITICAL_NOTICE" else (
            "Revise el detalle: casi siempre hay que resolver la referencia en AutoCAD.")
    if tecnico is not None and detalles.get("traceback"):
        tecnico += "\n\n" + str(detalles["traceback"])
    return {"codigo": codigo, "mensaje": mensaje, "consejo": consejo, "detalle": tecnico,
            "registro": ruta_para_mostrar(registro) if tecnico is not None else None}
