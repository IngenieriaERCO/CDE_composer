"""Lo que el servidor del editor sabe hacer, sin nada de HTTP (lo prueba pytest directo).

Etapa 1: «Cargar DXF». El servidor abre el cuadro nativo, valida la ruta, pide `load` al
trabajador por el canal y convierte la respuesta en la carpeta de bloques (`bloques_dxf`).

Etapa 2: vista previa de un bloque (`preview`, solo capas visibles). El editor pide la de un
`ref` de la carpeta actual; el servidor la encola (dos pedidos del mismo bloque son una sola
tarea), comprueba la respuesta (`previa_dxf`) y entrega el PNG por su tarea, solo si está
dentro de la carpeta de vistas previas del trabajador. «Volver a cargar» repite `load` con la
ruta que el servidor ya conoce (si el DXF cambió o el trabajador se reinició). Todavía no se
exporta.

Datos: aquí no pasa nada de `firmas/` (el editor ya trae solo los nombres) y la única ruta que
se carga es la que eligió el cuadro; el editor nunca manda rutas.
"""

import os
import threading
import time
from collections.abc import Callable
from pathlib import Path

from componedor.bloques_dxf import catalogo_dxf
from componedor.canal_trabajador import EN_COLA, EN_CURSO, Canal, Tarea
from componedor.configuracion import ConfigExportador
from componedor.dialogo_dxf import DxfInvalido, elegir_dxf, validar_dxf
from componedor.formato import RectMM
from componedor.previa_dxf import (
    CARPETA_PREVIAS,
    leer_previa,
    pedido_previa,
    png_dentro,
)
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
            (lambda: Trabajador(config.comando, config.trabajo,
                                opciones=config.opciones_trabajador())) if config else None)
        self.canal: Canal | None = None
        self.dxf: dict | None = None  # la carpeta del último DXF cargado
        self._generacion_dxf: int | None = None
        self._tarea_carga: str | None = None
        self._ruta_dxf: Path | None = None  # la del último DXF elegido (para «Volver a cargar»)
        self._previas: dict[str, Path] = {}  # tarea de vista previa terminada → su PNG
        self._previa_por_ref: dict[tuple[str, str], str] = {}  # (sesión, ref) → tarea
        self._candado = threading.Lock()
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
        return {"elegido": ruta.name, "tarea": self._cargar(ruta)}

    def recargar(self) -> dict:
        """«Volver a cargar»: `load` otra vez con la ruta del último DXF elegido."""
        motivo = self.motivo_sin_exportador()
        if motivo is not None:
            raise ErrorAplicacion(409, motivo)
        if self._ruta_dxf is None:
            raise ErrorAplicacion(409, "Todavía no se cargó ningún DXF: use «Cargar DXF».")
        actual = self.canal.tarea(self._tarea_carga) if self.canal and self._tarea_carga else None
        if actual is not None and actual.estado in (EN_COLA, EN_CURSO):
            raise ErrorAplicacion(409, "Ya se está cargando un DXF: espere o cancélelo.")
        try:
            ruta = validar_dxf(self._ruta_dxf)
        except DxfInvalido as e:
            raise ErrorAplicacion(400, str(e)) from None
        return {"elegido": ruta.name, "tarea": self._cargar(ruta)}

    def _cargar(self, ruta: Path) -> dict:
        """Encola `load` (las vistas previas que esperaban turno ya no sirven: se cancelan)."""
        canal = self._asegurar_canal()
        with self._candado:
            pendientes = list(self._previa_por_ref.values())
            self._previa_por_ref.clear()
        for id_tarea in pendientes:
            canal.cancelar(id_tarea)
        self._ruta_dxf = ruta
        tarea = canal.encolar(
            "cargar_dxf", "load",
            # Sin tabla de capas: la carpeta no la usa todavía (ahorra 1–2 s en bloques grandes).
            {"dxf": str(ruta), "units": None, "margin_mm": self.config.margen_mm,
             "include_layers": False},
            procesar=lambda data, t: self._al_cargar(data, t, ruta))
        self._tarea_carga = tarea.id
        return tarea.foto()

    def _al_cargar(self, data: dict, tarea: Tarea, ruta: Path) -> dict:
        catalogo = catalogo_dxf(data, self.zona)  # RespuestaInvalida es ValueError
        catalogo["dxf"]["archivo_plano"] = self.archivo_para_plano(ruta)
        self.dxf, self._generacion_dxf = catalogo, tarea.generacion
        return catalogo

    def archivo_para_plano(self, ruta: Path) -> str:
        """Ruta del DXF para el plano.json: relativa a la carpeta del editor (los planos van
        ahí o en planos/, al mismo nivel), con «/»; absoluta si está en otro disco."""
        try:
            return os.path.relpath(ruta, self.ruta_html.parent).replace(os.sep, "/")
        except ValueError:  # otro disco (Windows)
            return str(ruta)

    # --- vista previa (etapa 2) ----------------------------------------------------------------

    @property
    def carpeta_previas(self) -> Path | None:
        return self.config.trabajo / CARPETA_PREVIAS if self.config else None

    def pedir_previa(self, ref) -> dict:
        """Encola `preview` de un bloque de la carpeta actual. {"tarea": foto}. Si ya hay una
        tarea en cola o en curso para ese bloque en esta sesión, devuelve esa. Una terminada no
        se reutiliza: el trabajador la devuelve de su caché enseguida y, de paso, comprueba que
        el DXF no cambió en el disco (DXF_CHANGED)."""
        if not isinstance(ref, str) or not ref:
            raise ErrorAplicacion(400, "Falta «ref» (el bloque de la carpeta del DXF).")
        dxf = self.estado()["dxf"]
        if dxf is None:
            raise ErrorAplicacion(409, "Todavía no se cargó ningún DXF: use «Cargar DXF».")
        if not dxf["sesion_activa"]:
            raise ErrorAplicacion(409, "El trabajador se reinició desde que se cargó el DXF: "
                                       "vuelva a cargarlo («Volver a cargar»).")
        if not any(b["ref"] == ref for b in dxf["bloques"]):
            raise ErrorAplicacion(404, f"El bloque «{ref}» no está en la carpeta del DXF "
                                       f"cargado.")
        clave = (dxf["sesion"], ref)
        with self._candado:
            previa = self.canal.tarea(self._previa_por_ref.get(clave, ""))
            if previa is not None and previa.estado in (EN_COLA, EN_CURSO):
                return {"tarea": previa.foto()}
            tarea = self.canal.encolar(
                "previa", "preview", pedido_previa(dxf["sesion"], ref),
                procesar=lambda data, t: self._al_previar(data, t, ref))
            self._previa_por_ref[clave] = tarea.id
        return {"tarea": tarea.foto()}

    def _al_previar(self, data: dict, tarea: Tarea, ref: str) -> dict:
        previa = leer_previa(data, self.carpeta_previas)  # PreviaInvalida es ValueError
        self._previas[tarea.id] = previa.pop("png")
        return {**previa, "ref": ref, "url": f"/api/previas/{tarea.id}"}

    def png_previa(self, id_tarea: str) -> bytes:
        """Los bytes del PNG de una vista previa terminada (solo de la carpeta de previas)."""
        png = self._previas.get(id_tarea)
        if png is None:
            raise ErrorAplicacion(404, f"No hay vista previa «{id_tarea}».")
        try:
            return png_dentro(str(png), self.carpeta_previas).read_bytes()
        except (ValueError, OSError):
            raise ErrorAplicacion(404, "La imagen de la vista previa ya no está (la caché del "
                                       "trabajador la borró): pídala de nuevo.") from None

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
