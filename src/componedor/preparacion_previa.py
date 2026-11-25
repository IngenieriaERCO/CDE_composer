"""La vista previa preparada en segundo plano (protocolo 1.2 del trabajador, §4.2).

Tras `load`, un trabajador 1.2 dibuja una vez todo el Model Space en segundo plano y avisa con
eventos sin pedido: `preview_progress` (avance), `preview_ready` («lista»: desde entonces cada
vista de zona sale en menos de medio segundo) y `preview_failed` (las vistas se siguen dibujando
como en la 1.1). Aquí se guarda, por sesión, lo último que se supo, para que el editor lo
muestre («Preparando la vista previa… 61 % · lleva 32 s» / «lista» / el error).

- Los eventos llegan desde el hilo lector del trabajador: todo va con un candado.
- Cada evento trae `session`: el editor solo pregunta por la sesión del DXF cargado, así los de
  una sesión vieja no se mezclan.
- Un trabajador 1.0 o 1.1 no manda eventos ni `preview_preparation` en `load`: no hay estado
  (None) y el editor no muestra nada.
- El tiempo transcurrido lo cuenta el servidor (reloj monótono), desde la respuesta de `load`.
"""

import math
import threading
import time

PREPARANDO, LISTA, FALLIDA, DETENIDA = "preparando", "lista", "fallida", "detenida"
_ESTADOS_LOAD = {"running": PREPARANDO, "ready": LISTA, "failed": FALLIDA, "stopped": DETENIDA}
MAX_SESIONES = 4  # solo hacen falta la actual y quizá la anterior


def _numero(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _texto(v) -> str | None:
    return v if isinstance(v, str) and v else None


def pedido_preparar(ruta_ctb, imprimir_transparencia: bool) -> dict:
    """La opción `prepare_preview` de `load` (§3): la CTB (ruta o None) y la transparencia que
    usará el editor en `preview`, para que lo preparado sirva (si no, se prepara otra vez)."""
    return {"plot_style": str(ruta_ctb) if ruta_ctb is not None else None,
            "print_transparency": bool(imprimir_transparencia)}


class PreparacionPrevia:
    def __init__(self, reloj=time.monotonic):
        self._reloj = reloj
        self._candado = threading.Lock()
        self._sesiones: dict[str, dict] = {}

    def _de(self, sesion: str) -> dict:
        """El estado de la sesión (lo crea, preparando, si es nueva). Con el candado tomado."""
        e = self._sesiones.get(sesion)
        if e is None:
            e = {"estado": PREPARANDO, "etapa": None, "porcentaje": None, "mensaje": None,
                 "inicio": self._reloj(), "fin": None, "segundos": None, "error": None,
                 "estilo": None}
            self._sesiones[sesion] = e
            while len(self._sesiones) > MAX_SESIONES:
                del self._sesiones[next(iter(self._sesiones))]
        return e

    def al_cargar(self, sesion: str, preparacion) -> None:
        """La respuesta de `load`: su `preview_preparation` (§4.2), o nada con un trabajador
        1.0/1.1 (entonces no hay estado). Los eventos que ya llegaron se conservan."""
        if not isinstance(preparacion, dict):
            return
        estado = _ESTADOS_LOAD.get(preparacion.get("state"))
        if estado is None:
            return
        with self._candado:
            e = self._de(sesion)
            if e["estado"] == PREPARANDO and estado != PREPARANDO:
                e["estado"] = estado
                e["fin"] = self._reloj()
            if estado == FALLIDA:
                e["error"] = _texto(preparacion.get("error")) or e["error"]
            if _numero(preparacion.get("percent")) and e["porcentaje"] is None:
                e["porcentaje"] = float(preparacion["percent"])

    def al_evento(self, nombre: str, data: dict) -> None:
        """Un evento del trabajador (Trabajador.al_evento). Los desconocidos se ignoran."""
        sesion = _texto(data.get("session"))
        if sesion is None or nombre not in ("preview_progress", "preview_ready", "preview_failed"):
            return
        with self._candado:
            e = self._de(sesion)
            if nombre == "preview_progress":
                if e["estado"] != PREPARANDO:  # otra configuración: se prepara de nuevo
                    e.update(estado=PREPARANDO, inicio=self._reloj(), fin=None, segundos=None,
                             error=None, porcentaje=None)
                if _numero(data.get("percent")):
                    e["porcentaje"] = max(0.0, min(100.0, float(data["percent"])))
                e["etapa"] = _texto(data.get("stage"))
                e["mensaje"] = _texto(data.get("message"))
            elif nombre == "preview_ready":
                e.update(estado=LISTA, fin=self._reloj(), porcentaje=100.0, error=None,
                         segundos=float(data["seconds"]) if _numero(data.get("seconds")) else None)
                estilo = data.get("plot_style")
                e["estilo"] = {"ctb": _texto(estilo.get("name")) if isinstance(estilo, dict) else None,
                               "transparencia": data.get("print_transparency") is not False}
            else:
                e.update(estado=FALLIDA, fin=self._reloj(),
                         error=_texto(data.get("message")) or "la preparación falló")

    def estado(self, sesion: str | None) -> dict | None:
        """Para el editor: {estado, porcentaje, etapa, mensaje, transcurrido_s, segundos, error,
        estilo}, o None si no se sabe nada de esa sesión (trabajador 1.0/1.1)."""
        if sesion is None:
            return None
        with self._candado:
            e = self._sesiones.get(sesion)
            if e is None:
                return None
            hasta = e["fin"] if e["fin"] is not None else self._reloj()
            return {"estado": e["estado"], "porcentaje": e["porcentaje"], "etapa": e["etapa"],
                    "mensaje": e["mensaje"], "transcurrido_s": round(hasta - e["inicio"], 1),
                    "segundos": e["segundos"], "error": e["error"], "estilo": e["estilo"]}
