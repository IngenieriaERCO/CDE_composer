"""Lo que el servidor del editor sabe hacer, sin nada de HTTP (lo prueba pytest directo).

Etapa 1: «Cargar DXF». El servidor abre el cuadro nativo, valida la ruta, pide `load` al
trabajador por el canal y convierte la respuesta en la carpeta de bloques (`bloques_dxf`).
Todavía no se arrastra ni se exporta.

Datos: aquí no pasa nada de `firmas/` (el editor ya trae solo los nombres) y la única ruta que
se carga es la que eligió el cuadro; el editor nunca manda rutas.
"""

import threading
import time
from collections.abc import Callable
from pathlib import Path

from componedor.bloques_dxf import catalogo_dxf
from componedor.canal_trabajador import EN_COLA, EN_CURSO, Canal, Tarea
from componedor.configuracion import ConfigExportador
from componedor.dialogo_dxf import DxfInvalido, elegir_dxf, validar_dxf
from componedor.formato import RectMM
from componedor.trabajador import Trabajador, TrabajadorNoDisponible, resolver_comando

SIN_SECCION = ("componedor.json no tiene la sección «exportador»: el editor funciona, pero sin "
               "«Cargar DXF».")


class ErrorAplicacion(Exception):
    """Un pedido del editor que no se puede atender (código HTTP y mensaje en español)."""

    def __init__(self, estado_http: int, mensaje: str):
        super().__init__(mensaje)
        self.estado_http = estado_http
        self.mensaje = mensaje


class AplicacionEditor:
    def __init__(self, ruta_html: Path, zona: RectMM, config: ConfigExportador | None,
                 elegir: Callable[[Path | None], Path | None] = elegir_dxf,
                 fabrica: Callable[[], Trabajador] | None = None):
        self.ruta_html = Path(ruta_html)
        self.zona = zona
        self.config = config
        self._elegir = elegir
        self._fabrica = fabrica or (
            (lambda: Trabajador(config.comando, config.trabajo)) if config else None)
        self.canal: Canal | None = None
        self.dxf: dict | None = None  # la carpeta del último DXF cargado
        self._generacion_dxf: int | None = None
        self._tarea_carga: str | None = None
        self.carpeta_inicial: Path | None = None
        self.ultimo_latido = time.monotonic()
        self._dialogo = threading.Lock()

    # --- exportador ----------------------------------------------------------------------------

    def motivo_sin_exportador(self) -> str | None:
        """None si «Cargar DXF» se puede usar; si no, por qué (para el editor)."""
        if self.config is None:
            return SIN_SECCION
        try:
            resolver_comando(self.config.comando)
        except TrabajadorNoDisponible as e:
            return str(e)
        return None

    def _asegurar_canal(self) -> Canal:
        if self.canal is None:
            self.canal = Canal(self._fabrica)
        return self.canal

    # --- pedidos del editor --------------------------------------------------------------------

    def estado(self) -> dict:
        motivo = self.motivo_sin_exportador()
        trabajador = self.canal.estado() if self.canal else None
        dxf = None
        if self.dxf is not None:
            activa = (trabajador is not None
                      and trabajador["generacion"] == self._generacion_dxf)
            dxf = {**self.dxf, "sesion_activa": activa}
        tarea = self.canal.tarea(self._tarea_carga) if self.canal and self._tarea_carga else None
        return {"servidor": True,
                "exportador": {"disponible": motivo is None, "mensaje": motivo,
                               "trabajador": trabajador},
                "dxf": dxf, "tarea": tarea.foto() if tarea else None}

    def elegir_y_cargar(self) -> dict:
        """Abre el cuadro; si se elige un DXF, encola su carga. {"elegido", "tarea"}."""
        motivo = self.motivo_sin_exportador()
        if motivo is not None:
            raise ErrorAplicacion(409, motivo)
        actual = self.canal.tarea(self._tarea_carga) if self.canal and self._tarea_carga else None
        if actual is not None and actual.estado in (EN_COLA, EN_CURSO):
            raise ErrorAplicacion(409, "Ya se está cargando un DXF: espere o cancélelo.")
        if not self._dialogo.acquire(blocking=False):
            raise ErrorAplicacion(409, "Ya hay un cuadro abierto para elegir el DXF.")
        try:
            ruta = self._elegir(self.carpeta_inicial)
            if ruta is not None:
                ruta = validar_dxf(ruta)
        except DxfInvalido as e:
            raise ErrorAplicacion(400, str(e)) from None
        finally:
            self._dialogo.release()
        if ruta is None:
            return {"elegido": None, "tarea": None}
        self.carpeta_inicial = ruta.parent
        tarea = self._asegurar_canal().encolar(
            "cargar_dxf", "load",
            # Sin tabla de capas: la carpeta no la usa todavía (ahorra 1–2 s en bloques grandes).
            {"dxf": str(ruta), "units": None, "margin_mm": self.config.margen_mm,
             "include_layers": False},
            procesar=self._al_cargar)
        self._tarea_carga = tarea.id
        return {"elegido": ruta.name, "tarea": tarea.foto()}

    def _al_cargar(self, data: dict, tarea: Tarea) -> dict:
        catalogo = catalogo_dxf(data, self.zona)  # RespuestaInvalida es ValueError
        self.dxf, self._generacion_dxf = catalogo, tarea.generacion
        return catalogo

    def tarea(self, id_tarea: str) -> dict:
        t = self.canal.tarea(id_tarea) if self.canal else None
        if t is None:
            raise ErrorAplicacion(404, f"No existe la tarea «{id_tarea}».")
        return t.foto()

    def cancelar(self, id_tarea: str) -> dict:
        if self.canal is None or self.canal.tarea(id_tarea) is None:
            raise ErrorAplicacion(404, f"No existe la tarea «{id_tarea}».")
        return {"cancelando": self.canal.cancelar(id_tarea)}

    def reiniciar(self) -> dict:
        if self.canal is not None:
            self.canal.reiniciar()
        return {"reiniciado": True}

    def latido(self) -> dict:
        self.ultimo_latido = time.monotonic()
        return {"ok": True}

    def cerrar(self) -> None:
        if self.canal is not None:
            self.canal.cerrar()
