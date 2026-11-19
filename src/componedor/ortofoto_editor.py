"""«Cargar ortofoto» del servidor del editor, sin nada de HTTP (lo prueba pytest directo).

- `elegir(archivo_plano)`: abre el cuadro nativo (.tif/.tiff), lee la CABECERA
  (`ortofoto.leer_cabecera`) y la deja como la ortofoto de esta sesión. El archivo lo elige
  SOLO el cuadro, igual que el DXF. `archivo_plano` (la ruta que guardó el plano abierto) sirve
  únicamente para que el cuadro se abra en esa carpeta: no se lee ni se abre nada con ella. Si
  lo elegido no coincide con el plano, lo dice el editor (nombre, tamaño, fecha).
- `estado()`: la ficha (con sus avisos), la ruta para el plano.json y los sistemas del selector.
  Si el archivo cambió en el disco desde que se leyó, lo dice (hay que volver a cargarla).
- `previa(cuerpo)`: la vista previa de UNA caja de detalle. El cuerpo trae solo números y
  códigos EPSG (caja CAD, mm por unidad, sistema del dibujo y, si la ortofoto no trae el suyo,
  el elegido): nada de rutas. La lectura es local y rápida (por ventanas), así que se hace en el
  mismo pedido, de a una (candado), sin la cola del trabajador. Las ya hechas se guardan (las
  últimas `MAX_PREVIAS`) y se entregan por su id como PNG.
- `quitar()`: olvida la ortofoto (el archivo no se toca).
"""

import os
import threading
from collections import OrderedDict
from collections.abc import Callable
from pathlib import Path

from componedor.dialogo_dxf import elegir_ortofoto
from componedor.ortofoto import (
    SISTEMAS_COMUNES,
    OrtofotoInvalida,
    SistemaInvalido,
    firma,
    leer_cabecera,
    leer_sistema,
    validar_ruta,
)
from componedor.previa_ortofoto import LADO_PX, MAX_LADO_PX, hacer_previa, validar_caja

MAX_PREVIAS = 64
CAMBIO = ("La ortofoto cambió en el disco desde que se cargó: vuelva a cargarla («Cargar "
          "ortofoto»).")


class ErrorOrtofoto(Exception):
    """Un pedido de ortofoto que no se puede atender (código HTTP y mensaje en español)."""

    def __init__(self, estado_http: int, mensaje: str):
        super().__init__(mensaje)
        self.estado_http = estado_http
        self.mensaje = mensaje


class OrtofotoEditor:
    def __init__(self, carpeta_editor: Path,
                 elegir: Callable[[Path | None], Path | None] = elegir_ortofoto):
        self.carpeta_editor = Path(carpeta_editor)
        self._elegir = elegir
        self.ruta: Path | None = None
        self.ficha: dict | None = None
        self._firma: tuple[int, int] | None = None
        self._previas: OrderedDict[str, bytes] = OrderedDict()  # id → PNG
        self._por_clave: dict[tuple, dict] = {}  # pedido → respuesta (si su PNG sigue)
        self._n = 0
        self._candado = threading.Lock()
        self._dialogo = threading.Lock()
        self.carpeta_inicial: Path | None = None

    def archivo_para_plano(self, ruta: Path) -> str:
        """Relativa a la carpeta del editor, con «/» (absoluta si está en otro disco)."""
        try:
            return os.path.relpath(ruta, self.carpeta_editor).replace(os.sep, "/")
        except ValueError:
            return str(ruta)

    def cambio_en_disco(self) -> bool:
        if self.ruta is None:
            return False
        try:
            return firma(self.ruta) != self._firma
        except OSError:
            return True

    def estado(self) -> dict | None:
        if self.ficha is None:
            return None
        return {"ficha": self.ficha, "archivo_plano": self.archivo_para_plano(self.ruta),
                "cambio": self.cambio_en_disco(),
                "sistemas": [{"codigo": c, "nombre": n} for c, n in SISTEMAS_COMUNES]}

    def carpeta_del_plano(self, archivo_plano) -> Path | None:
        """La carpeta donde estaba la ortofoto del plano (para abrir ahí el cuadro), si existe."""
        if not isinstance(archivo_plano, str) or not archivo_plano.strip() or len(
                archivo_plano) > 1024:
            return None
        try:
            carpeta = (self.carpeta_editor / archivo_plano).resolve().parent
            return carpeta if carpeta.is_dir() else None
        except (OSError, ValueError):
            return None

    def elegir(self, archivo_plano=None) -> dict:
        """Abre el cuadro (en la carpeta de la ortofoto del plano, si existe; si no, en la de la
        última elegida); si se elige un GeoTIFF que sirve, pasa a ser la ortofoto.
        {"elegida": nombre | None, "ortofoto": estado}."""
        if not self._dialogo.acquire(blocking=False):
            raise ErrorOrtofoto(409, "Ya hay un cuadro abierto para elegir la ortofoto.")
        try:
            ruta = self._elegir(self.carpeta_del_plano(archivo_plano) or self.carpeta_inicial)
            if ruta is None:
                return {"elegida": None, "ortofoto": self.estado()}
            ruta = validar_ruta(ruta)
            ficha = leer_cabecera(ruta)
            huella = firma(ruta)
        except OrtofotoInvalida as e:
            raise ErrorOrtofoto(400, str(e)) from None
        finally:
            self._dialogo.release()
        with self._candado:
            self.ruta, self.ficha, self._firma = ruta, ficha, huella
            self._previas.clear()
            self._por_clave.clear()
        self.carpeta_inicial = ruta.parent
        return {"elegida": ruta.name, "ortofoto": self.estado()}

    def quitar(self) -> dict:
        with self._candado:
            self.ruta = self.ficha = self._firma = None
            self._previas.clear()
            self._por_clave.clear()
        return {"quitada": True}

    def previa(self, cuerpo: dict) -> dict:
        """{caja_cad: [x0, y0, x1, y1], mm_por_unidad, crs_dibujo, crs_ortofoto?, px?} →
        {id, url, px, cobertura, caja_cad}."""
        if self.ficha is None:
            raise ErrorOrtofoto(409, "No hay ortofoto cargada: use «Cargar ortofoto».")
        if self.cambio_en_disco():
            raise ErrorOrtofoto(409, CAMBIO)
        try:
            caja = validar_caja(cuerpo.get("caja_cad"))
        except ValueError as e:
            raise ErrorOrtofoto(400, f"caja_cad: {e}.") from None
        mm = cuerpo.get("mm_por_unidad", 1000.0)
        if isinstance(mm, bool) or not isinstance(mm, (int, float)) or not mm > 0:
            raise ErrorOrtofoto(400, "mm_por_unidad: se esperaba un número > 0.")
        lado = cuerpo.get("px", LADO_PX)
        if isinstance(lado, bool) or not isinstance(lado, int) or not 16 <= lado <= MAX_LADO_PX:
            raise ErrorOrtofoto(400, f"px: se esperaba un entero de 16 a {MAX_LADO_PX}.")
        if cuerpo.get("crs_dibujo") is None:
            raise ErrorOrtofoto(400, "Falta el sistema de coordenadas del dibujo: elíjalo en "
                                     "la ficha de la ortofoto.")
        propio = self.ficha["sistema"]
        elegido = cuerpo.get("crs_ortofoto")
        if propio is None and elegido is None:
            raise ErrorOrtofoto(400, "La ortofoto no dice su sistema de coordenadas: elíjalo en "
                                     "su ficha (no se supone ninguno).")
        try:
            crs_dibujo = leer_sistema(cuerpo["crs_dibujo"])
            # Con sistema propio, el elegido no cuenta (no se le gana al archivo).
            crs_ortofoto = leer_sistema(elegido) if propio is None else None
        except SistemaInvalido as e:
            raise ErrorOrtofoto(400, str(e)) from None
        clave = (caja, float(mm), lado, crs_dibujo.to_string(),
                 crs_ortofoto.to_string() if crs_ortofoto else None)
        with self._candado:  # de a una lectura (el disco y la memoria lo agradecen)
            hecha = self._por_clave.get(clave)
            if hecha is not None and hecha["id"] in self._previas:
                self._previas.move_to_end(hecha["id"])
                return hecha
            try:
                p = hacer_previa(self.ruta, caja, crs_dibujo, crs_ortofoto, float(mm), lado)
            except OrtofotoInvalida as e:
                raise ErrorOrtofoto(400, str(e)) from None
            except OSError as e:
                raise ErrorOrtofoto(409, f"No se pudo leer la ortofoto: {e}") from None
            self._n += 1
            ident = f"o-{self._n}"
            self._previas[ident] = p.png
            while len(self._previas) > MAX_PREVIAS:
                self._previas.popitem(last=False)
            respuesta = {"id": ident, "url": f"/api/ortofoto/previas/{ident}", "px": list(p.px),
                         "cobertura": round(p.cobertura, 4), "caja_cad": list(caja)}
            self._por_clave[clave] = respuesta
            return respuesta

    def png(self, ident: str) -> bytes:
        with self._candado:
            png = self._previas.get(ident)
        if png is None:
            raise ErrorOrtofoto(404, f"No hay vista previa de ortofoto «{ident}» (pídala de "
                                     f"nuevo).")
        return png
