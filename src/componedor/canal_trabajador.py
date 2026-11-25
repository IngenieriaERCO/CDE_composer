"""Canal hacia el trabajador: una cola de tareas y UN pedido a la vez.

El editor nunca habla con el trabajador. Cada pedido HTTP crea una `Tarea` que espera su
turno; un solo hilo las atiende en orden. Así el Componedor nunca provoca un `BUSY` (el
contrato admite `cancel` y `status` en cualquier momento: van por fuera de la cola).

- El trabajador se lanza la primera vez que hace falta (no al abrir el editor).
- Si se cae, la tarea en curso falla con un mensaje claro y la siguiente lanza otro
  trabajador. Tras `MAX_CAIDAS` caídas seguidas el canal queda DETENIDO: no vuelve a lanzar
  nada hasta `reiniciar()` (botón «Reiniciar trabajador»). Cada trabajador nuevo cambia la
  `generacion`: lo que se había cargado en el anterior (la sesión) ya no existe.
- Cancelar: una tarea en cola se quita; la que está en curso recibe `cancel`. Si el
  trabajador no lo acepta a tiempo, o no responde, se detiene a la fuerza (se cierra su Job).
- Un `BUSY` que llegue igual es un error del Componedor: se anota y se reintenta UNA vez.
- «Detener a la fuerza» (`detener`, etapa 3): el usuario lo pide sin esperar la cancelación; se
  cierra el Job del trabajador, la tarea en curso y las de la cola quedan canceladas y la sesión
  se pierde (hay que volver a cargar el DXF).
- Una tarea puede terminar SIN trabajador (`terminada_sin_trabajador`): p. ej. un paquete que ya
  estaba publicado; el editor la sigue igual que las demás.
"""

import itertools
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from componedor.mensajes_trabajador import para_el_usuario
from componedor.trabajador import (
    ErrorTrabajador,
    Trabajador,
    TrabajadorCaido,
    TrabajadorNoDisponible,
)

EN_COLA, EN_CURSO, TERMINADA, FALLIDA, CANCELADA = (
    "en_cola", "en_curso", "terminada", "fallida", "cancelada")
FINALES = (TERMINADA, FALLIDA, CANCELADA)
MAX_CAIDAS = 2
ESPERA_CANCELAR_S = 60.0  # desde que el trabajador acepta el cancel hasta detenerlo a la fuerza

SIN_INICIAR, ARRANCANDO, LISTO, OCUPADO, DETENIDO = (
    "sin_iniciar", "arrancando", "listo", "ocupado", "detenido")


class FalloDeTarea(ValueError):
    """Lo lanza `procesar` para que la tarea falle con SU código (p. ej. EXPORT_FAILED)."""

    def __init__(self, codigo: str, mensaje: str, consejo: str | None = None,
                 detalle: str | None = None, registro: str | None = None):
        super().__init__(mensaje)
        self.codigo, self.mensaje, self.consejo = codigo, mensaje, consejo
        self.detalle, self.registro = detalle, registro


@dataclass
class Tarea:
    id: str
    tipo: str
    comando: str
    datos: dict
    procesar: Callable[[dict, "Tarea"], Any] | None = None
    estado: str = EN_COLA
    avance: dict = field(default_factory=dict)  # percent, stage, message
    resultado: Any = None
    error: dict | None = None  # {codigo, mensaje, consejo, detalle, registro}
    id_pedido: str | None = None
    generacion: int | None = None  # del trabajador que la atendió
    ultima_noticia: float = field(default_factory=time.monotonic)
    cancelando: bool = False
    forzada: bool = False
    motivo_forzada: str | None = None  # «Detener a la fuerza» del usuario (si no, por tiempo)

    def foto(self) -> dict:
        """Lo que ve el editor (JSON)."""
        return {"id": self.id, "tipo": self.tipo, "estado": self.estado,
                "avance": dict(self.avance), "resultado": self.resultado, "error": self.error,
                "cancelando": self.cancelando,
                "sin_noticias_s": round(time.monotonic() - self.ultima_noticia, 1)}


class Canal:
    def __init__(self, fabrica: Callable[[], Trabajador],
                 espera_cancelar_s: float = ESPERA_CANCELAR_S, max_caidas: int = MAX_CAIDAS):
        self._fabrica = fabrica
        self.espera_cancelar_s = espera_cancelar_s
        self.max_caidas = max_caidas
        self._cola: deque[Tarea] = deque()
        self._tareas: dict[str, Tarea] = {}
        self._ids = itertools.count(1)
        self._cv = threading.Condition()
        self._trabajador: Trabajador | None = None
        self._estado = SIN_INICIAR
        self._mensaje: str | None = None  # por qué no está disponible o se detuvo
        self.listo: dict | None = None  # ready del trabajador actual
        self.generacion = 0
        self._caidas = 0
        self._cerrado = False
        self._hilo = threading.Thread(target=self._atender, name="canal-trabajador", daemon=True)
        self._hilo.start()

    # --- API (la usa el servidor desde sus hilos) ----------------------------------------------

    def encolar(self, tipo: str, comando: str, datos: dict,
                procesar: Callable[[dict, Tarea], Any] | None = None) -> Tarea:
        """Pone una tarea al final de la cola. `procesar(data, tarea)` convierte el resultado
        del trabajador en lo que verá el editor (si lanza ValueError, la tarea falla)."""
        with self._cv:
            tarea = Tarea(f"t-{next(self._ids)}", tipo, comando, datos, procesar)
            self._tareas[tarea.id] = tarea
            if self._estado == DETENIDO:
                self._fallar(tarea, "DETENIDO", self._mensaje or "El trabajador está detenido.",
                             "Pulse «Reiniciar trabajador».")
            else:
                self._cola.append(tarea)
                self._cv.notify_all()
            return tarea

    def terminada_sin_trabajador(self, tipo: str, resultado: Any) -> Tarea:
        """Una tarea que ya nace terminada (no pasa por el trabajador ni por la cola)."""
        with self._cv:
            tarea = Tarea(f"t-{next(self._ids)}", tipo, "", {}, None, estado=TERMINADA,
                          resultado=resultado)
            self._tareas[tarea.id] = tarea
            return tarea

    def detener(self, motivo: str = "Detenido a la fuerza por el usuario.") -> bool:
        """«Detener a la fuerza»: cierra el Job del trabajador sin esperar. La tarea en curso y
        las de la cola quedan canceladas. True si había un trabajador."""
        with self._cv:
            trabajador = self._trabajador
            for tarea in self._cola:
                tarea.estado = CANCELADA
                tarea.error = {"codigo": "CANCELLED", "mensaje": motivo + " (no llegó a empezar)",
                               "consejo": None}
            self._cola.clear()
            en_curso = [t for t in self._tareas.values() if t.estado == EN_CURSO]
            for t in en_curso:
                t.forzada, t.cancelando, t.motivo_forzada = True, True, motivo
        if trabajador is None:
            return False
        trabajador.anotar(f"se detiene a la fuerza a pedido del usuario ({len(en_curso)} en curso)")
        if not en_curso:  # sin tarea que note la caída: se descarta aquí (otra sesión)
            self.reiniciar()
            return True
        trabajador.matar()
        return True

    def tarea(self, id_tarea: str) -> Tarea | None:
        with self._cv:
            return self._tareas.get(id_tarea)

    def estado(self) -> dict:
        with self._cv:
            return {"estado": self._estado, "mensaje": self._mensaje, "listo": self.listo,
                    "generacion": self.generacion, "en_cola": len(self._cola)}

    def cancelar(self, id_tarea: str) -> bool:
        """True si la tarea estaba en cola o en curso (la cancelación sigue su camino)."""
        with self._cv:
            tarea = self._tareas.get(id_tarea)
            if tarea is None or tarea.estado in FINALES:
                return False
            if tarea.estado == EN_COLA:
                self._cola.remove(tarea)
                tarea.estado = CANCELADA
                tarea.error = {"codigo": "CANCELLED", "mensaje": "Cancelado antes de empezar.",
                               "consejo": None}
                return True
            if tarea.cancelando:
                return True
            tarea.cancelando = True
            trabajador = self._trabajador
        threading.Thread(target=self._cancelar_en_curso, args=(tarea, trabajador),
                         daemon=True).start()
        return True

    def reiniciar(self) -> None:
        """Sale de DETENIDO (o descarta el trabajador actual): el próximo pedido lanza otro."""
        with self._cv:
            trabajador, self._trabajador = self._trabajador, None
            if trabajador is not None:
                self.generacion += 1  # la sesión del trabajador anterior ya no existe
            self._caidas = 0
            self._estado = SIN_INICIAR
            self._mensaje = None
            self.listo = None
        if trabajador is not None:
            trabajador.matar()

    def cerrar(self) -> None:
        """Cancela lo pendiente y cierra el trabajador (close, fin de stdin, Job)."""
        with self._cv:
            self._cerrado = True
            for tarea in self._cola:
                tarea.estado = CANCELADA
            self._cola.clear()
            trabajador = self._trabajador
            self._cv.notify_all()
        if trabajador is not None:
            trabajador.cerrar()
        self._hilo.join(timeout=10)

    # --- hilo del canal ------------------------------------------------------------------------

    def _atender(self) -> None:
        while True:
            with self._cv:
                while not self._cola and not self._cerrado:
                    self._cv.wait()
                if self._cerrado:
                    return
                tarea = self._cola.popleft()
                tarea.estado = EN_CURSO
                tarea.ultima_noticia = time.monotonic()
            self._ejecutar(tarea)

    def _ejecutar(self, tarea: Tarea) -> None:
        trabajador = self._asegurar_trabajador(tarea)
        if trabajador is None:
            return
        tarea.generacion = self.generacion
        for intento in (1, 2):
            tarea.id_pedido = trabajador.nuevo_id()
            if tarea.cancelando:  # se pidió cancelar mientras arrancaba el trabajador
                self._terminar_cancelada(tarea, "Cancelado.")
                return
            try:
                data = trabajador.pedir(tarea.comando, tarea.datos,
                                        al_avance=lambda d: self._avance(tarea, d),
                                        id_pedido=tarea.id_pedido)
            except ErrorTrabajador as e:
                if e.codigo == "BUSY" and intento == 1:
                    trabajador.anotar(f"BUSY inesperado en {tarea.id_pedido}; se reintenta")
                    time.sleep(0.5)
                    continue
                if e.codigo == "CANCELLED":
                    self._terminar_cancelada(tarea, e.mensaje)
                else:  # mensaje claro; el texto técnico, en «detalle» (mensajes_trabajador)
                    tarea.error = para_el_usuario(tarea.tipo, e.codigo, e.mensaje, e.consejo,
                                                  e.detalles, trabajador.ruta_registro)
                    tarea.estado = FALLIDA
                with self._cv:
                    self._estado, self._caidas = LISTO, 0
                return
            except TrabajadorCaido as e:
                self._caida(tarea, trabajador, str(e))
                return
            break
        try:
            tarea.resultado = tarea.procesar(data, tarea) if tarea.procesar else data
        except FalloDeTarea as e:
            self._fallar(tarea, e.codigo, e.mensaje, e.consejo, e.detalle, e.registro)
        except ValueError as e:
            self._fallar(tarea, "RESPUESTA_INVALIDA",
                         f"La respuesta del trabajador no se puede usar: {e}",
                         "Revise que el Exportador Vectorial y el Componedor estén al día.")
        else:
            tarea.estado = TERMINADA
        with self._cv:
            self._estado, self._caidas = LISTO, 0

    def _asegurar_trabajador(self, tarea: Tarea) -> Trabajador | None:
        with self._cv:
            if self._trabajador is not None and self._trabajador.vivo:
                self._estado = OCUPADO
                return self._trabajador
            self._estado = ARRANCANDO
        tarea.avance = {"percent": 0.0, "stage": "start",
                        "message": "Arrancando el trabajador del exportador…"}
        trabajador = self._fabrica()
        try:
            listo = trabajador.iniciar()
        except TrabajadorNoDisponible as e:
            with self._cv:
                self._estado, self._mensaje = SIN_INICIAR, str(e)
            self._fallar(tarea, "NO_DISPONIBLE", str(e), None)
            return None
        with self._cv:
            self._trabajador, self.listo = trabajador, listo
            self.generacion += 1
            self._estado, self._mensaje = OCUPADO, None
        return trabajador

    def _avance(self, tarea: Tarea, data: dict) -> None:
        tarea.ultima_noticia = time.monotonic()
        tarea.avance = {"percent": data.get("percent"), "stage": data.get("stage"),
                        "message": data.get("message")}

    def _caida(self, tarea: Tarea, trabajador: Trabajador, mensaje: str) -> None:
        trabajador.matar()
        with self._cv:
            if self._trabajador is trabajador:
                self._trabajador, self.listo = None, None
                self.generacion += 1  # la sesión del trabajador caído ya no existe
            if tarea.forzada:  # lo detuvimos nosotros: no cuenta como caída
                self._estado = SIN_INICIAR
            else:
                self._caidas += 1
                if self._caidas >= self.max_caidas:
                    self._estado = DETENIDO
                    self._mensaje = (f"El trabajador del exportador se cayó {self._caidas} "
                                     f"veces seguidas. Último error: {mensaje}")
                else:
                    self._estado = SIN_INICIAR
        if tarea.forzada:
            self._terminar_cancelada(tarea, tarea.motivo_forzada or (
                "Se detuvo el trabajador a la fuerza: no respondió a la cancelación a tiempo."))
        else:
            self._fallar(tarea, "CAIDO", mensaje,
                         "Vuelva a intentarlo; el próximo pedido arranca otro trabajador.")

    def _cancelar_en_curso(self, tarea: Tarea, trabajador: Trabajador | None) -> None:
        """Manda `cancel` y espera a que la tarea termine; si no termina, a la fuerza.

        Solo si el trabajador NO RESPONDE al `cancel` se lo detiene enseguida. Si responde que
        no lo acepta (el pedido ya estaba terminando y su respuesta viene en camino, o todavía
        no había empezado), se espera lo mismo que con uno aceptado: matarlo perdería la sesión
        (con un DXF grande, más de un minuto de carga) por una tarea que termina sola. Esto
        pasa a menudo con la rueda de «Zonas del modelo», que cancela la vista que esperaba.
        """
        aceptado = False
        respondio = False
        if trabajador is not None and tarea.id_pedido is not None:
            try:
                aceptado = trabajador.cancelar(tarea.id_pedido)
                respondio = True
            except (TimeoutError, TrabajadorCaido, ErrorTrabajador, OSError):
                aceptado = False  # no responde: a la fuerza ya
        limite = time.monotonic() + (self.espera_cancelar_s if respondio else 0)
        while tarea.estado == EN_CURSO and time.monotonic() < limite:
            time.sleep(0.05)
        if tarea.estado == EN_CURSO and trabajador is not None:
            tarea.forzada = True
            trabajador.anotar(f"se detiene a la fuerza (tarea {tarea.id}, aceptado={aceptado})")
            trabajador.matar()

    # --- terminar ------------------------------------------------------------------------------

    def _fallar(self, tarea: Tarea, codigo: str, mensaje: str, consejo: str | None,
                detalle: str | None = None, registro: str | None = None) -> None:
        tarea.error = {"codigo": codigo, "mensaje": mensaje, "consejo": consejo,
                       "detalle": detalle, "registro": registro}
        tarea.estado = FALLIDA

    def _terminar_cancelada(self, tarea: Tarea, mensaje: str) -> None:
        tarea.error = {"codigo": "CANCELLED", "mensaje": mensaje, "consejo": None}
        tarea.estado = CANCELADA
