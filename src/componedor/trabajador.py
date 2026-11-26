"""Cliente del trabajador del Exportador Vectorial (`cde-exporter worker`, protocolo 1.3).

El Componedor no importa código del exportador: lo lanza como COMANDO EXTERNO y le habla
JSON por líneas (contrato: `docs/protocolo_trabajador.md` del repositorio del exportador).

- stdin: un pedido por línea (UTF-8, `\\n`). stdout: un mensaje por línea (`ready`,
  `progress`, `result`, `error`). stderr: registro libre, va DIRECTO a un archivo
  (`trabajador.log` en la carpeta de trabajo), así esa tubería nunca se llena.
- El proceso corre dentro de un Job Object (`proceso_windows`): si el Componedor muere, el
  trabajador muere con él.
- Un hilo lee stdout y entrega cada mensaje al pedido que tiene su `id`. `pedir` es seguro
  entre hilos: mientras un pedido largo espera, otro hilo puede mandar `cancel` o `status`
  (el trabajador los responde siempre, también en pasos que no se pueden cortar).
- Quien decide «un pedido a la vez» es el canal (`canal_trabajador`), no esta clase.

Errores para el usuario (en español): `TrabajadorNoDisponible` (no arranca: no está
instalado, no tiene la orden `worker`, no responde, otra versión del protocolo),
`TrabajadorCaido` (el proceso terminó sin `close`) y `ErrorTrabajador` (el pedido terminó con
`error`: código estable, mensaje, consejo y detalles del trabajador).

Versión: los pedidos dicen `"protocol": "1.3"` (la 1.3 trae `texts`: la escala escrita en una
zona; `admite_textos`). Un trabajador 1.0 o 1.1 los atiende igual (la
misma versión mayor): el 1.0 no sabe de zonas del Model Space (`admite_zonas`) y ninguno de los
dos manda eventos. Desde la 1.2 llegan mensajes `event` sin pedido (`id` null): la vista previa
preparada en segundo plano (§4.2); van a `al_evento(nombre, data)`, si se asignó.
"""

import itertools
import json
import os
import shutil
import subprocess
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from componedor.proceso_windows import ProcesoEnJob, cerrar_job, lanzar_en_job

PROTOCOLO = "1.3"
MAYOR = "1"
MENOR_ZONAS = 1  # zonas del Model Space en preview y export (protocolo 1.1, §4.1 y §5.4)
MENOR_TEXTOS = 3  # `texts`: los textos de una zona y su escala propuesta (protocolo 1.3, §4.3)
ESPERA_READY_S = 60.0  # arranque en frío del exportador real: >30 s la primera vez (compila .pyc)
ESPERA_CONTROL_S = 10.0  # cancel y status se responden enseguida (punto 4 del contrato)
ESPERA_CIERRE_S = 5.0
ARCHIVO_REGISTRO = "trabajador.log"  # stderr del trabajador
ARCHIVO_NOTAS = "componedor.log"  # lo que anota el Componedor sobre el canal
LINEAS_DE_REGISTRO = 12  # las últimas que se muestran si el trabajador no arranca


class TrabajadorNoDisponible(RuntimeError):
    """El trabajador no se puede usar (mensaje en español, listo para el usuario)."""


class TrabajadorCaido(RuntimeError):
    """El proceso del trabajador terminó sin que se le pidiera."""

    def __init__(self, mensaje: str, codigo_salida: int | None):
        super().__init__(mensaje)
        self.codigo_salida = codigo_salida


class ErrorTrabajador(RuntimeError):
    """El pedido terminó con un mensaje `error` del trabajador."""

    def __init__(self, codigo: str, mensaje: str, consejo: str | None = None,
                 detalles: dict | None = None):
        super().__init__(mensaje)
        self.codigo = codigo
        self.mensaje = mensaje
        self.consejo = consejo
        self.detalles = detalles or {}


@dataclass
class _Pendiente:
    al_avance: Callable[[dict], None] | None
    evento: threading.Event = field(default_factory=threading.Event)
    respuesta: dict | None = None


def resolver_comando(comando: Sequence[str]) -> list[str]:
    """El comando con su programa resuelto (PATH o ruta), o TrabajadorNoDisponible."""
    if not comando:
        raise TrabajadorNoDisponible("No hay comando del exportador configurado.")
    programa = comando[0]
    resuelto = shutil.which(programa)
    if resuelto is None and Path(programa).is_file():
        resuelto = str(Path(programa).resolve())
    if resuelto is None:
        raise TrabajadorNoDisponible(
            f"No se encontró el comando «{programa}» del Exportador Vectorial. Instálelo o "
            f"indique su ruta en componedor.json (exportador.comando).")
    return [resuelto, *comando[1:]]


def _menor(listo: dict | None) -> int | None:
    """La versión menor del protocolo del `ready` (None si no es la mayor 1 o no se entiende)."""
    version = (listo or {}).get("protocol_version")
    partes = str(version).split(".") if isinstance(version, str) else []
    if len(partes) < 2 or partes[0] != MAYOR or not partes[1].isdigit():
        return None
    return int(partes[1])


def admite_zonas(listo: dict | None) -> bool:
    """True si el `ready` del trabajador dice protocolo 1.1 o más (zonas del Model Space)."""
    menor = _menor(listo)
    return menor is not None and menor >= MENOR_ZONAS


def admite_textos(listo: dict | None) -> bool:
    """True si el `ready` dice protocolo 1.3 o más (`texts`: la escala escrita en una zona)."""
    menor = _menor(listo)
    return menor is not None and menor >= MENOR_TEXTOS


def _mayor(version) -> str | None:
    return str(version).split(".")[0] if isinstance(version, str) and version else None


class Trabajador:
    """Un proceso `cde-exporter worker` vivo. Uso: `iniciar()`, `pedir(...)`, `cerrar()`."""

    def __init__(self, comando: Sequence[str], carpeta_trabajo: Path | str,
                 espera_ready_s: float = ESPERA_READY_S, opciones: Sequence[str] = ()):
        self.comando = list(comando)
        self.opciones = list(opciones)  # después de `worker --work-dir …` (--preview-cache-mb)
        self.carpeta = Path(carpeta_trabajo).resolve()
        self.espera_ready_s = espera_ready_s
        self.listo: dict | None = None  # data del mensaje ready
        # Eventos sin pedido (protocolo 1.2, §2.3 y §4.2): al_evento(nombre, data). Se llama
        # desde el hilo lector: debe ser rápido y no lanzar (si lanza, se anota y se sigue).
        self.al_evento: Callable[[str, dict], None] | None = None
        self._p: ProcesoEnJob | None = None
        self._registro = None
        self._lector: threading.Thread | None = None
        self._escritura = threading.Lock()
        self._estado = threading.Lock()
        self._pendientes: dict[str, _Pendiente] = {}
        self._ids = itertools.count(1)
        self._ready = threading.Event()
        self._terminado = threading.Event()  # stdout llegó a su fin
        self._cerrando = False

    # --- ciclo de vida -------------------------------------------------------------------------

    @property
    def vivo(self) -> bool:
        return self._p is not None and not self._terminado.is_set()

    @property
    def ruta_registro(self) -> Path:
        return self.carpeta / ARCHIVO_REGISTRO

    def iniciar(self) -> dict:
        """Lanza el proceso y espera `ready`. Devuelve su `data` (versiones)."""
        argv = (resolver_comando(self.comando) + ["worker", "--work-dir", str(self.carpeta)]
                + self.opciones)
        self.carpeta.mkdir(parents=True, exist_ok=True)
        # Abierto mientras viva el proceso (es su stderr); lo cierra _matar.
        self._registro = open(self.ruta_registro, "ab")  # noqa: SIM115
        self._registro.write(f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')} {argv}\n".encode())
        self._registro.flush()
        entorno = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
        try:
            self._p = lanzar_en_job(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                    stderr=self._registro, cwd=str(self.carpeta), env=entorno)
        except OSError as e:
            self._registro.close()
            raise TrabajadorNoDisponible(f"No se pudo lanzar «{argv[0]}»: {e}") from None
        if self._p.aviso:
            self.anotar(f"aviso al lanzar: {self._p.aviso}")
        self._lector = threading.Thread(target=self._leer, name="trabajador-lector", daemon=True)
        self._lector.start()
        self._ready.wait(self.espera_ready_s)
        if self.listo is None:
            terminado = self._terminado.is_set()
            self._matar()
            if terminado:
                raise TrabajadorNoDisponible(self._motivo_sin_arranque())
            raise TrabajadorNoDisponible(
                f"El trabajador del exportador no respondió en {self.espera_ready_s:g} s. "
                f"Registro: {self.ruta_registro}")
        protocolo = self.listo.get("protocol_version")
        esquema = self.listo.get("manifest_schema_version")
        if _mayor(protocolo) != MAYOR or _mayor(esquema) != MAYOR:
            self.cerrar()
            raise TrabajadorNoDisponible(
                f"El trabajador habla el protocolo {protocolo!r} y escribe manifiestos "
                f"{esquema!r}; el Componedor necesita la versión mayor {MAYOR} de los dos. "
                f"Actualice el Componedor o el Exportador Vectorial.")
        return self.listo

    def _motivo_sin_arranque(self) -> str:
        cola = self._cola_del_registro()
        if "invalid choice: 'worker'" in cola or "argument cad_command" in cola:
            return ("El cde-exporter instalado no tiene la orden «worker» (es una versión sin "
                    "trabajador). Actualice el Exportador Vectorial.")
        codigo = self._p.proceso.returncode if self._p else None
        return (f"El trabajador del exportador terminó al arrancar (código {codigo})."
                + (f" Últimas líneas del registro:\n{cola}" if cola else "")
                + f"\nRegistro: {self.ruta_registro}")

    def _cola_del_registro(self) -> str:
        try:
            texto = self.ruta_registro.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
        lineas = texto.split("\n=== ")[-1].splitlines()[1:]
        return "\n".join(lineas[-LINEAS_DE_REGISTRO:]).strip()

    def cerrar(self, espera_s: float = ESPERA_CIERRE_S) -> None:
        """`close`, luego fin de stdin y, si sigue vivo, cierra el Job (mata el árbol)."""
        if self._p is None:
            return
        self._cerrando = True
        if self.vivo:
            try:
                self.pedir("close", {}, espera_s=espera_s)
            except (ErrorTrabajador, TrabajadorCaido, TimeoutError, OSError):
                pass
        try:
            self._p.proceso.stdin.close()
        except OSError:
            pass
        try:
            self._p.proceso.wait(timeout=espera_s)
        except subprocess.TimeoutExpired:
            self.anotar("no terminó tras close y fin de stdin: se cierra el Job")
        self._matar()

    def matar(self) -> None:
        """Detener a la fuerza (cierra el Job). Los pedidos en espera reciben TrabajadorCaido."""
        self._cerrando = True
        self._matar()

    def _matar(self) -> None:
        if self._p is not None:
            cerrar_job(self._p)
        if self._lector is not None:
            self._lector.join(timeout=5)
        if self._registro is not None and not self._registro.closed:
            self._registro.close()

    # --- pedidos -------------------------------------------------------------------------------

    def pedir(self, comando: str, datos: dict, al_avance: Callable[[dict], None] | None = None,
              espera_s: float | None = None, id_pedido: str | None = None) -> dict:
        """Manda un pedido y espera su `result` (devuelve `data`). Lanza ErrorTrabajador si
        termina con `error`, TrabajadorCaido si el proceso termina y TimeoutError si pasa
        `espera_s`. `al_avance(data)` recibe cada `progress`."""
        if not self.vivo:
            raise TrabajadorCaido("El trabajador del exportador no está en marcha.",
                                  self._codigo_salida())
        id_pedido = id_pedido or self.nuevo_id()
        pendiente = _Pendiente(al_avance)
        with self._estado:
            self._pendientes[id_pedido] = pendiente
        linea = json.dumps({"protocol": PROTOCOLO, "id": id_pedido, "command": comando,
                            "data": datos}, ensure_ascii=False) + "\n"
        try:
            with self._escritura:
                self._p.proceso.stdin.write(linea.encode("utf-8"))
                self._p.proceso.stdin.flush()
        except OSError:
            with self._estado:
                self._pendientes.pop(id_pedido, None)
            self._terminado.wait(2)
            raise TrabajadorCaido(self._texto_caida(), self._codigo_salida()) from None
        if not pendiente.evento.wait(espera_s):
            with self._estado:
                self._pendientes.pop(id_pedido, None)
            raise TimeoutError(f"el trabajador no respondió «{comando}» en {espera_s:g} s")
        respuesta = pendiente.respuesta
        if respuesta is None:
            raise TrabajadorCaido(self._texto_caida(), self._codigo_salida())
        if respuesta.get("type") == "error":
            e = respuesta.get("error") if isinstance(respuesta.get("error"), dict) else {}
            raise ErrorTrabajador(str(e.get("code") or "INTERNAL"),
                                  str(e.get("message") or "Error sin mensaje del trabajador."),
                                  e.get("advice"), e.get("details") if isinstance(
                                      e.get("details"), dict) else {})
        data = respuesta.get("data")
        return data if isinstance(data, dict) else {}

    def nuevo_id(self) -> str:
        return f"c-{next(self._ids)}"

    def cancelar(self, objetivo: str) -> bool:
        """`cancel` del pedido `objetivo`; True si el trabajador lo aceptó."""
        return bool(self.pedir("cancel", {"target": objetivo},
                               espera_s=ESPERA_CONTROL_S).get("accepted"))

    def estado(self) -> dict:
        return self.pedir("status", {}, espera_s=ESPERA_CONTROL_S)

    # --- lectura de stdout ---------------------------------------------------------------------

    def _leer(self) -> None:
        salida = self._p.proceso.stdout
        try:
            for crudo in iter(salida.readline, b""):
                self._despachar(crudo)
        except (OSError, ValueError):
            pass
        finally:
            self._terminado.set()
            self._ready.set()
            with self._estado:
                pendientes = list(self._pendientes.values())
                self._pendientes.clear()
            for p in pendientes:
                p.evento.set()  # sin respuesta: quien espera recibe TrabajadorCaido

    def _despachar(self, crudo: bytes) -> None:
        try:
            mensaje = json.loads(crudo.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.anotar(f"línea de stdout que no es JSON UTF-8 (se ignora): {crudo[:200]!r}")
            return
        if not isinstance(mensaje, dict):
            self.anotar(f"mensaje que no es un objeto (se ignora): {crudo[:200]!r}")
            return
        tipo = mensaje.get("type")
        if tipo == "event":
            nombre, data = mensaje.get("event"), mensaje.get("data")
            if self.al_evento is not None and isinstance(nombre, str) and isinstance(data, dict):
                try:
                    self.al_evento(nombre, data)
                except Exception as e:  # noqa: BLE001 - un fallo al mostrar no corta el canal
                    self.anotar(f"error al procesar el evento {nombre!r}: {e!r}")
            return
        if tipo == "ready":
            data = mensaje.get("data")
            self.listo = data if isinstance(data, dict) else {}
            self._ready.set()
            return
        with self._estado:
            pendiente = self._pendientes.get(mensaje.get("id"))
            if pendiente is not None and tipo in ("result", "error"):
                del self._pendientes[mensaje.get("id")]
        if pendiente is None:
            self.anotar(f"mensaje sin pedido en espera (se ignora): {crudo[:200]!r}")
        elif tipo == "progress":
            if pendiente.al_avance is not None and isinstance(mensaje.get("data"), dict):
                try:
                    pendiente.al_avance(mensaje["data"])
                except Exception as e:  # noqa: BLE001 - un fallo al mostrar no corta el canal
                    self.anotar(f"error al procesar el avance: {e!r}")
        elif tipo in ("result", "error"):
            pendiente.respuesta = mensaje
            pendiente.evento.set()
        else:
            self.anotar(f"mensaje de tipo desconocido {tipo!r} (se ignora)")

    # --- registro ------------------------------------------------------------------------------

    def anotar(self, texto: str) -> None:
        """Una línea en `componedor.log` de la carpeta de trabajo (diagnóstico)."""
        try:
            self.carpeta.mkdir(parents=True, exist_ok=True)
            with open(self.carpeta / ARCHIVO_NOTAS, "a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {texto}\n")
        except OSError:
            pass

    def _codigo_salida(self) -> int | None:
        if self._p is None:
            return None
        if self._terminado.is_set():  # stdout cerrado: el proceso está terminando
            try:
                return self._p.proceso.wait(timeout=2)
            except subprocess.TimeoutExpired:
                return None
        return self._p.proceso.poll()

    def _texto_caida(self) -> str:
        if self._cerrando:
            return "El trabajador del exportador se detuvo."
        codigo = self._codigo_salida()
        return (f"El trabajador del exportador se cerró inesperadamente (código {codigo}). "
                f"Registro: {self.ruta_registro}")
