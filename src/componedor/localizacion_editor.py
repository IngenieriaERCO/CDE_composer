"""«Cargar imagen de localización» del servidor del editor, sin nada de HTTP.

- `elegir(archivo_plano)`: abre el cuadro nativo (PNG o JPG). La imagen la elige SOLO el cuadro;
  `archivo_plano` (la ruta que guardó el plano) sirve únicamente para abrirlo en esa carpeta.
  Se comprueba que sea un PNG o JPG que se pueda leer y se devuelve su ficha: nombre, ruta para
  el plano (relativa a la carpeta del editor), bytes, fecha, píxeles y formato.
- `imagen()`: los bytes de la imagen elegida, para la vista previa (solo esa, y solo si no cambió
  en el disco).
- `quitar()`: la olvida (el archivo no se toca).
"""

import os
import threading
from collections.abc import Callable
from pathlib import Path

import pymupdf

from componedor.dialogo_dxf import elegir_localizacion
from componedor.localizacion import EXTENSIONES, formato_de
from componedor.ortofoto_fuente import datos_del_archivo


class ErrorLocalizacion(Exception):
    """Un pedido que no se puede atender (código HTTP y mensaje en español)."""

    def __init__(self, estado_http: int, mensaje: str):
        super().__init__(mensaje)
        self.estado_http = estado_http
        self.mensaje = mensaje


def validar_imagen(ruta: Path | str) -> tuple[Path, str, tuple[int, int]]:
    """(ruta absoluta, "png" | "jpeg", (ancho, alto) px). ValueError con el motivo si no sirve."""
    ruta = Path(ruta).resolve()
    if ruta.suffix.lower() not in EXTENSIONES:
        raise ValueError(f"«{ruta.name}» no es un .png ni un .jpg.")
    if not ruta.is_file():
        raise ValueError(f"No existe el archivo «{ruta}».")
    datos = ruta.read_bytes()
    formato = formato_de(datos)
    if formato is None:
        raise ValueError(f"«{ruta.name}» no es una imagen PNG ni JPG.")
    try:
        pix = pymupdf.Pixmap(datos)
    except (RuntimeError, ValueError) as e:
        raise ValueError(f"No se pudo leer «{ruta.name}»: {e}") from None
    return ruta, formato, (pix.width, pix.height)


class LocalizacionEditor:
    def __init__(self, carpeta_editor: Path,
                 elegir: Callable[[Path | None], Path | None] = elegir_localizacion):
        self.carpeta_editor = Path(carpeta_editor)
        self._elegir = elegir
        self.ruta: Path | None = None
        self.ficha: dict | None = None
        self.carpeta_inicial: Path | None = None
        self._dialogo = threading.Lock()

    def archivo_para_plano(self, ruta: Path) -> str:
        try:
            return os.path.relpath(ruta, self.carpeta_editor).replace(os.sep, "/")
        except ValueError:  # otro disco
            return str(ruta)

    def carpeta_del_plano(self, archivo_plano) -> Path | None:
        if not isinstance(archivo_plano, str) or not archivo_plano.strip() or len(archivo_plano) > 1024:
            return None
        try:
            carpeta = (self.carpeta_editor / archivo_plano).resolve().parent
            return carpeta if carpeta.is_dir() else None
        except (OSError, ValueError):
            return None

    def estado(self) -> dict | None:
        if self.ficha is None:
            return None
        cambio = not self.ruta.is_file() or datos_del_archivo(self.ruta) != {
            "nombre": self.ficha["nombre"], "bytes": self.ficha["bytes"],
            "modificado": self.ficha["modificado"]}
        return {**self.ficha, "cambio": cambio, "url": "/api/localizacion/imagen"}

    def elegir(self, archivo_plano=None) -> dict:
        if not self._dialogo.acquire(blocking=False):
            raise ErrorLocalizacion(409, "Ya hay un cuadro abierto para elegir la imagen.")
        try:
            ruta = self._elegir(self.carpeta_del_plano(archivo_plano) or self.carpeta_inicial)
            if ruta is None:
                return {"elegida": None, "localizacion": self.estado()}
            ruta, formato, px = validar_imagen(ruta)
        except ValueError as e:
            raise ErrorLocalizacion(400, str(e)) from None
        finally:
            self._dialogo.release()
        datos = datos_del_archivo(ruta)
        self.ruta = ruta
        self.ficha = {"nombre": ruta.name, "archivo_plano": self.archivo_para_plano(ruta),
                      "bytes": datos["bytes"], "modificado": datos["modificado"],
                      "px": list(px), "formato": formato}
        self.carpeta_inicial = ruta.parent
        return {"elegida": ruta.name, "localizacion": self.estado()}

    def quitar(self) -> dict:
        self.ruta = self.ficha = None
        return {"quitada": True}

    def imagen(self) -> tuple[bytes, str]:
        """(bytes, tipo MIME) de la imagen elegida."""
        e = self.estado()
        if e is None:
            raise ErrorLocalizacion(404, "No hay imagen de localización cargada.")
        if e["cambio"]:
            raise ErrorLocalizacion(409, "La imagen de localización cambió en el disco desde que "
                                         "se cargó: vuelva a cargarla.")
        return self.ruta.read_bytes(), "image/png" if e["formato"] == "png" else "image/jpeg"
