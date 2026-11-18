"""Lo que el servidor del editor sabe hacer, sin nada de HTTP (lo prueba pytest directo).

Etapa 1: «Cargar DXF». El servidor abre el cuadro nativo, valida la ruta, pide `load` al
trabajador por el canal y convierte la respuesta en la carpeta de bloques (`bloques_dxf`).

Etapa 2: vista previa de un bloque (`preview`, solo capas visibles). El editor pide la de un
`ref` de la carpeta actual; el servidor la encola (dos pedidos del mismo bloque son una sola
tarea), comprueba la respuesta (`previa_dxf`) y entrega el PNG por su tarea, solo si está
dentro de la carpeta de vistas previas del trabajador. «Volver a cargar» repite `load` con la
ruta que el servidor ya conoce (si el DXF cambió o el trabajador se reinició).

Etapa 3: «Exportar». Cada bloque es UN pedido `export` con un solo trabajo (se cancela o se
detiene por separado). Antes de pedirlo: si el paquete ya está publicado y es el de este bloque,
se usa (caché). El trabajador publica en una carpeta de preparación: solo si el paquete nuevo
se publicó y pasó la verificación (`exportar_dxf.verificar`), el viejo se mueve a
`_para_borrar/` y el nuevo pasa a su lugar; si se cancela o falla, el viejo queda donde estaba.
Después se calcula su posición por el centro CAD. «Detener a la
fuerza» cierra el trabajador sin esperar (`Canal.detener`).

Datos: aquí no pasa nada de `firmas/` (el editor ya trae solo los nombres) y la única ruta que
se carga es la que eligió el cuadro; el editor nunca manda rutas.
"""

import itertools
import os
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import ClassVar

from componedor.bloques_dxf import catalogo_dxf, pagina_mm
from componedor.canal_trabajador import (
    EN_COLA,
    EN_CURSO,
    FINALES,
    Canal,
    FalloDeTarea,
    Tarea,
)
from componedor.colocar import exceso_de_tamano
from componedor.configuracion import ConfigExportador
from componedor.detalle_exportado import detalle_para_editor, ruta_para_el_editor
from componedor.dialogo_dxf import DxfInvalido, elegir_dxf, validar_dxf
from componedor.exportar_dxf import (
    PaqueteNoValido,
    Pedido,
    carpeta_de_preparacion,
    carpeta_del_dxf,
    de_la_cache,
    instalar,
    limpiar_preparacion,
    nombre_del_paquete,
    posicion_por_centro,
    verificar,
)
from componedor.formato import RectMM
from componedor.importador import importar_paquete
from componedor.inventario import ESCALA_MAXIMA
from componedor.mensajes_trabajador import para_el_usuario
from componedor.previa_dxf import (
    CARPETA_PREVIAS,
    leer_previa,
    pedido_previa,
    png_dentro,
)
from componedor.trabajador import (
    ARCHIVO_REGISTRO,
    Trabajador,
    TrabajadorNoDisponible,
    resolver_comando,
)

SIN_SECCION = ("componedor.json no tiene la sección «exportador»: el editor funciona, pero sin "
               "«Cargar DXF».")


def firma_archivo(ruta: Path) -> tuple[int, int] | None:
    """(bytes, fecha de modificación en ns), lo que mira el trabajador para DXF_CHANGED."""
    try:
        estado = Path(ruta).stat()
    except OSError:
        return None
    return estado.st_size, estado.st_mtime_ns


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
        self._exportacion: dict[tuple[str, str, float], str] = {}  # (sha, handle, N) → tarea
        self._exportados: dict[str, dict] = {}  # manifiesto (para el editor) → entrada de catálogo
        self._firma_dxf: tuple[int, int] | None = None  # (bytes, fecha) del DXF al cargarlo (§9)
        self._preparaciones: dict[str, Path] = {}  # tarea de exportar → su carpeta de preparación
        self._n_preparacion = itertools.count(1)
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
        firma = firma_archivo(ruta)  # antes de que el trabajador lo lea
        tarea = canal.encolar(
            "cargar_dxf", "load",
            # Sin tabla de capas: la carpeta no la usa todavía (ahorra 1–2 s en bloques grandes).
            # Los anónimos *U se ofrecen desde ese número de entidades visibles (el umbral lo
            # manda el Componedor; se configura en componedor.json).
            {"dxf": str(ruta), "units": None, "margin_mm": self.config.margen_mm,
             "include_layers": False,
             "anonymous_min_entities": self.config.anonimos_min_entidades},
            procesar=lambda data, t: self._al_cargar(data, t, ruta, firma))
        self._tarea_carga = tarea.id
        return tarea.foto()

    def _al_cargar(self, data: dict, tarea: Tarea, ruta: Path,
                   firma: tuple[int, int] | None = None) -> dict:
        catalogo = catalogo_dxf(data, self.zona,  # RespuestaInvalida es ValueError
                                anonimos_min=self.config.anonimos_min_entidades)
        catalogo["dxf"]["archivo_plano"] = self.archivo_para_plano(ruta)
        self.dxf, self._generacion_dxf = catalogo, tarea.generacion
        self._firma_dxf = firma
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
        bloque = next((b for b in dxf["bloques"] if b["ref"] == ref), None)
        if bloque is None:
            raise ErrorAplicacion(404, f"El bloque «{ref}» no está en la carpeta del DXF "
                                       f"cargado.")
        clave = (dxf["sesion"], ref)
        with self._candado:
            previa = self.canal.tarea(self._previa_por_ref.get(clave, ""))
            if previa is not None and previa.estado in (EN_COLA, EN_CURSO):
                return {"tarea": previa.foto()}
            tarea = self.canal.encolar(
                "previa", "preview", pedido_previa(dxf["sesion"], bloque["handle"]),
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

    # --- exportar (etapa 3) ---------------------------------------------------------------------

    MAX_BLOQUES = 200
    OPCIONES_EXPORT: ClassVar[dict] = {"solids": "footprint", "omit_unsupported": True, "overwrite": False,
                       "write_summary": False}  # las recomendadas por el contrato (§5)

    def exportar(self, bloques) -> dict:
        """Un pedido `export` (un trabajo) por bloque. bloques: [{id, handle, sha256, escala,
        centro_mm}] del plano. {"tareas": [foto, …]} en el mismo orden."""
        if self.config is None or self.config.paquetes is None:
            raise ErrorAplicacion(409, SIN_SECCION)
        if not isinstance(bloques, list) or not bloques or len(bloques) > self.MAX_BLOQUES:
            raise ErrorAplicacion(400, f"Se esperaba la lista «bloques» (de 1 a "
                                       f"{self.MAX_BLOQUES}).")
        dxf = self.estado()["dxf"]
        if dxf is None:
            raise ErrorAplicacion(409, "Todavía no se cargó ningún DXF: use «Cargar DXF».")
        if not dxf["sesion_activa"]:
            raise ErrorAplicacion(409, "El trabajador se reinició desde que se cargó el DXF: "
                                       "vuelva a cargarlo («Volver a cargar»).")
        if self._ruta_dxf is not None and firma_archivo(self._ruta_dxf) != self._firma_dxf:
            # La misma regla del trabajador (§9), también para lo que sale de la caché.
            raise ErrorAplicacion(409, "El DXF cambió en el disco desde que se cargó: vuelva a "
                                       "cargarlo («Volver a cargar») y exporte de nuevo.")
        pedidos = [self._leer_bloque(b, dxf) for b in bloques]  # todo validado antes de encolar
        carpeta = carpeta_del_dxf(self.config.paquetes, dxf["dxf"]["nombre"])
        carpeta.mkdir(parents=True, exist_ok=True)
        return {"tareas": [self._exportar_uno(p, dxf, carpeta) for p in pedidos]}

    def _leer_bloque(self, b, dxf: dict) -> dict:
        if not isinstance(b, dict):
            raise ErrorAplicacion(400, "Cada bloque debe ser un objeto.")
        ident = b.get("id")
        n, centro = b.get("escala"), b.get("centro_mm")
        if not (isinstance(ident, str) and ident and isinstance(n, (int, float))
                and not isinstance(n, bool) and n == int(n) and 1 <= n <= ESCALA_MAXIMA
                and isinstance(centro, list)
                and len(centro) == 2 and all(isinstance(v, (int, float)) for v in centro)):
            raise ErrorAplicacion(400, "Cada bloque lleva id, handle, sha256, escala (entero de 1 "
                                       "a 100000) y centro_mm.")
        if b.get("sha256") != dxf["dxf"]["sha256"]:
            raise ErrorAplicacion(409, f"'{ident}' es de otro DXF (o de otra versión de este): "
                                       f"cargue ese DXF para exportarlo.")
        bloque = next((x for x in dxf["bloques"] if x["handle"] == b.get("handle")), None)
        if bloque is None:
            raise ErrorAplicacion(404, f"'{ident}': el bloque (handle {b.get('handle')}) no está "
                                       f"en el DXF cargado.")
        if bloque["tamano_m"] is None or bloque["caja_cad"] is None:
            raise ErrorAplicacion(409, f"'{ident}': sin unidades verificadas o sin caja: no se "
                                       f"puede exportar.")
        pagina = pagina_mm(bloque["tamano_m"], n, dxf["margen_mm"])
        dx, dy = exceso_de_tamano(pagina, self.zona)
        if dx or dy:
            raise ErrorAplicacion(400, f"'{ident}' no cabe en el área de dibujo a 1:{n:g} "
                                       f"(sobran {dx:.1f} × {dy:.1f} mm): cambie la escala.")
        return {"id": ident, "bloque": bloque, "n": float(n), "centro": tuple(centro),
                "pagina": pagina}

    def _exportar_uno(self, p: dict, dxf: dict, carpeta) -> dict:
        b, n = p["bloque"], p["n"]
        paquete = nombre_del_paquete(b["archivo"] or b["nombre"], n)
        pedido = Pedido(dxf["dxf"]["sha256"], b["handle"], n, dxf["margen_mm"],
                        tuple(p["pagina"]), b["caja_exacta"])
        clave = (pedido.sha256, pedido.handle, n)
        with self._candado:
            vivo = self.canal.tarea(self._exportacion.get(clave, "")) if self.canal else None
            if vivo is not None and vivo.estado in (EN_COLA, EN_CURSO):
                return vivo.foto()  # el mismo paquete ya se está exportando
            manifiesto = de_la_cache(carpeta, paquete, pedido)
            if manifiesto is not None:
                resultado = self._resultado(manifiesto, p, importar_paquete(manifiesto),
                                            en_cache=True, movidos=[])
                return self._asegurar_canal().terminada_sin_trabajador("exportar", resultado).foto()
            # El viejo (si hay) no se toca todavía: el nuevo se publica aparte.
            preparacion = carpeta_de_preparacion(carpeta, str(next(self._n_preparacion)))
            tarea = self._asegurar_canal().encolar(
                "exportar", "export",
                {"session": dxf["sesion"], "output_dir": str(preparacion.resolve()),
                 # Por el handle solo (no el ref, que en un *U cambia entre sesiones).
                 "jobs": [{"job": "j1", "handle": b["handle"], "scale": f"1:{n:g}",
                           "package": paquete}],
                 "options": dict(self.OPCIONES_EXPORT)},
                procesar=lambda data, t: self._al_exportar(data, t, p, pedido, carpeta,
                                                           preparacion, paquete))
            self._exportacion[clave] = tarea.id
            self._preparaciones[tarea.id] = preparacion
        return tarea.foto()

    def _al_exportar(self, data: dict, tarea: Tarea, p: dict, pedido: Pedido, carpeta: Path,
                     preparacion: Path, paquete: str) -> dict:
        trabajos = data.get("jobs") if isinstance(data, dict) else None
        if not (isinstance(trabajos, list) and len(trabajos) == 1
                and isinstance(trabajos[0], dict)):
            raise ValueError("la respuesta de «export» no trae un trabajo")
        t = trabajos[0]
        if t.get("status") != "published":
            error = t.get("error") if isinstance(t.get("error"), dict) else {}
            u = para_el_usuario("exportar", str(error.get("code") or "EXPORT_FAILED"),
                                str(error.get("message") or t.get("status")), None,
                                error.get("details"), self.config.trabajo / ARCHIVO_REGISTRO)
            raise FalloDeTarea(u["codigo"], f"'{p['id']}': {u['mensaje']}", u["consejo"],
                               u["detalle"], u["registro"])
        manifiesto = (t.get("package") or {}).get("manifest")
        if not isinstance(manifiesto, str):
            raise ValueError("el trabajo publicado no trae «package.manifest»")  # noqa: TRY004
        tarea.avance = {"percent": 100.0, "stage": "verificar",
                        "message": "Verificando el paquete (integridad y coherencia)…"}
        try:
            verificar(manifiesto, pedido)  # en la preparación: el viejo sigue en su lugar
        except PaqueteNoValido as e:
            raise FalloDeTarea("PAQUETE_NO_VALIDO",
                               f"El paquete de '{p['id']}' no pasó la verificación: {e}",
                               "No se usa (va a _para_borrar) y el paquete anterior, si había, "
                               "queda donde estaba. Vuelva a exportarlo; si se repite, avise al "
                               "Exportador Vectorial.") from None
        # Publicado y verificado: recién ahora el viejo a _para_borrar y el nuevo a su lugar.
        manifiesto, movidos = instalar(preparacion, carpeta, paquete, self.config.paquetes,
                                       self.config.para_borrar)
        self._preparaciones.pop(tarea.id, None)
        aceptado = importar_paquete(manifiesto)
        return self._resultado(manifiesto, p, aceptado, en_cache=False, movidos=movidos,
                               avisos=[str(n.get("message")) for n in t.get("notices") or []
                                       if isinstance(n, dict) and n.get("message")])

    def _resultado(self, manifiesto, p: dict, aceptado, en_cache: bool, movidos: list,
                   avisos: list | None = None) -> dict:
        """Lo que el editor necesita para cambiar el bloque por un detalle normal."""
        caja = p["bloque"]["caja_cad"]
        centro_cad = ((caja["min"][0] + caja["max"][0]) / 2, (caja["min"][1] + caja["max"][1]) / 2)
        carpeta_editor = self.ruta_html.parent
        prefijo = aceptado.paquete.prefijo
        posicion = posicion_por_centro(manifiesto, centro_cad, p["centro"])
        detalle = detalle_para_editor(aceptado, prefijo, carpeta_editor, self.zona)
        self._exportados[detalle["manifiesto"]] = detalle
        return {
            "id": p["id"], "handle": p["bloque"]["handle"], "escala": p["n"],
            "paquete": prefijo,
            "manifiesto": detalle["manifiesto"],
            "posicion_mm": list(posicion),
            # Esquina = centro − esto: sirve para cualquier copia del bloque a esta escala.
            "desde_centro_mm": [p["centro"][0] - posicion[0], p["centro"][1] - posicion[1]],
            "detalle": detalle,
            "en_cache": en_cache,
            "movidos": [ruta_para_el_editor(m, carpeta_editor) for m in movidos],
            "avisos": avisos or [],
        }

    def exportados(self) -> dict:
        """Los paquetes exportados en esta sesión del servidor (entradas de catálogo), para el
        editor que se recarga: así los reconoce al abrir un plano sin regenerar editor.html."""
        return {"detalles": list(self._exportados.values())}

    def detener(self) -> dict:
        """«Detener a la fuerza»: cierra el trabajador sin esperar la cancelación."""
        return {"detenido": self.canal.detener() if self.canal is not None else False}

    def tarea(self, id_tarea: str) -> dict:
        t = self.canal.tarea(id_tarea) if self.canal else None
        if t is None:
            raise ErrorAplicacion(404, f"No existe la tarea «{id_tarea}».")
        self.limpiar_preparaciones()
        return t.foto()

    def limpiar_preparaciones(self, todas: bool = False) -> None:
        """Las carpetas de preparación de exportaciones que terminaron sin instalarse (canceladas
        o fallidas): lo que haya publicado se mueve a _para_borrar; el paquete viejo no se toca."""
        for id_tarea, preparacion in list(self._preparaciones.items()):
            t = self.canal.tarea(id_tarea) if self.canal else None
            if todas or t is None or t.estado in FINALES:
                limpiar_preparacion(preparacion, self.config.paquetes, self.config.para_borrar)
                self._preparaciones.pop(id_tarea, None)

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
        if self._preparaciones:
            self.limpiar_preparaciones(todas=True)
