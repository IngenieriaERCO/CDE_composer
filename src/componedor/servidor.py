"""Servidor local del editor (`componedor servidor`): solo 127.0.0.1, con token.

Entrega el mismo `editor.html` de siempre y una API pequeña para «Cargar DXF». El editor
abierto con doble clic (file://) sigue funcionando sin servidor; con servidor se abre en
`http://127.0.0.1:<puerto>/?t=<token>`, el mismo origen que la API (sin CORS).

Controles de cada pedido (`motivo_rechazo`), en este orden:

1. `Host` debe ser exactamente `127.0.0.1:<puerto>` (otra página no puede usarlo con un
   nombre que apunte a 127.0.0.1: «DNS rebinding»).
2. La ruta debe existir (lo demás, 404).
3. Token: en la página, `?t=<token>`; en la API, la cabecera `X-Componedor-Token`.
4. `Origin`, si viene, debe ser el propio; en un POST es obligatorio. `Sec-Fetch-Site`, si
   viene, debe ser `same-origin` (o `none`: la barra de direcciones, solo para la página).
5. POST: cuerpo JSON (`Content-Type: application/json`) de hasta 64 KB.

Ninguna ruta entrega archivos del disco salvo editor.html, el PNG de una vista previa
terminada (y solo si está dentro de la carpeta de vistas previas del trabajador: lo comprueba
`aplicacion_editor`) y el PNG de una vista previa de la ortofoto (hecho en memoria); ninguna
recibe rutas ni opciones para el comando del exportador. Lo único que el editor manda en un
cuerpo es el `ref` de un bloque de la carpeta ya cargada; para «Exportar», la lista de bloques
del plano (id, handle, sha256, escala, centro): la carpeta de salida y los nombres de paquete
los decide el servidor; para la vista previa de una zona del Model Space, números y nombres de
capa (zona, vista, capas o excluir, escala); para exportar una zona, lo mismo más su nombre
y su centro en la hoja (la carpeta y el nombre del paquete los decide el servidor); y para la vista previa de la ortofoto, números y códigos EPSG (la caja
CAD de un detalle, mm por unidad, sistemas): la ortofoto la eligió el cuadro nativo.
"""

import json
import re
import secrets
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from componedor.aplicacion_editor import AplicacionEditor, ErrorAplicacion
from componedor.localizacion_editor import ErrorLocalizacion
from componedor.ortofoto_editor import ErrorOrtofoto

HOST = "127.0.0.1"
CABECERA_TOKEN = "X-Componedor-Token"
LIMITE_CUERPO = 64 * 1024
RUTA_TAREA = re.compile(r"^/api/tareas/(t-\d+)$")
RUTA_CANCELAR = re.compile(r"^/api/tareas/(t-\d+)/cancelar$")
RUTA_PNG = re.compile(r"^/api/previas/(t-\d+)$")
RUTA_PNG_ORTOFOTO = re.compile(r"^/api/ortofoto/previas/(o-\d+)$")
RUTAS_GET = ("/", "/api/estado", "/api/exportados", "/api/ortofoto", "/api/localizacion",
              "/api/localizacion/imagen", "/api/estilos")
RUTAS_POST = ("/api/dxf/elegir", "/api/dxf/recargar", "/api/previa", "/api/previa/zona",
              "/api/exportar", "/api/exportar/zona", "/api/zonas/nombre", "/api/textos/zona",
              "/api/trabajador/reiniciar", "/api/trabajador/detener", "/api/latido",
              "/api/ortofoto/elegir", "/api/ortofoto/quitar", "/api/ortofoto/previa",
              "/api/localizacion/elegir", "/api/localizacion/quitar")


def ruta_conocida(metodo: str, ruta: str) -> bool:
    if metodo == "GET":
        return ruta in RUTAS_GET or bool(RUTA_TAREA.match(ruta) or RUTA_PNG.match(ruta)
                                         or RUTA_PNG_ORTOFOTO.match(ruta))
    if metodo == "POST":
        return ruta in RUTAS_POST or bool(RUTA_CANCELAR.match(ruta))
    return False


def motivo_rechazo(metodo: str, url: str, cabeceras, token: str, puerto: int
                   ) -> tuple[int, str] | None:
    """(código HTTP, motivo) si el pedido no se atiende; None si pasa todos los controles."""
    if cabeceras.get("Host") != f"{HOST}:{puerto}":
        return 403, "Host no permitido."
    partes = urlsplit(url)
    if not ruta_conocida(metodo, partes.path):
        return 404, "No existe."
    pagina = partes.path == "/"
    if pagina:
        dado = (parse_qs(partes.query).get("t") or [""])[0]
    else:
        dado = cabeceras.get(CABECERA_TOKEN) or ""
    if not secrets.compare_digest(dado.encode(), token.encode()):
        return 403, "Falta el token o no es el de este servidor."
    origen = cabeceras.get("Origin")
    if origen is not None and origen != f"http://{HOST}:{puerto}":
        return 403, "Origen no permitido."
    if metodo == "POST" and origen is None:
        return 403, "Falta la cabecera Origin."
    sitio = cabeceras.get("Sec-Fetch-Site")
    if sitio is not None and sitio != "same-origin" and not (pagina and sitio == "none"):
        return 403, "Pedido desde otro sitio."
    if metodo == "POST":
        if not (cabeceras.get("Content-Type") or "").startswith("application/json"):
            return 415, "Se esperaba un cuerpo JSON."
        try:
            largo = int(cabeceras.get("Content-Length") or 0)
        except ValueError:
            return 400, "Content-Length inválido."
        if largo > LIMITE_CUERPO:
            return 413, "Cuerpo demasiado grande."
    return None


class ServidorEditor:
    """El servidor HTTP en un hilo. `url` lleva el token (para abrir el navegador)."""

    def __init__(self, app: AplicacionEditor, puerto: int = 0, token: str | None = None,
                 registro: Path | None = None):
        self.app = app
        self.token = token or secrets.token_urlsafe(32)
        self.registro = registro
        self._parar = threading.Event()
        self._http = ThreadingHTTPServer((HOST, puerto), _manejador(self))
        self._http.daemon_threads = True
        self.puerto = self._http.server_address[1]
        self._hilo: threading.Thread | None = None

    @property
    def origen(self) -> str:
        return f"http://{HOST}:{self.puerto}"

    @property
    def url(self) -> str:
        return f"{self.origen}/?t={self.token}"

    def iniciar(self) -> None:
        self._hilo = threading.Thread(target=self._http.serve_forever, name="servidor-editor",
                                      daemon=True)
        self._hilo.start()

    def esperar(self, inactividad_s: float | None, cada_s: float = 1.0) -> str:
        """Bloquea hasta `detener()` o hasta `inactividad_s` sin latidos del editor.
        Devuelve por qué terminó ("detenido" o "inactividad")."""
        while not self._parar.wait(cada_s):
            if (inactividad_s is not None
                    and time.monotonic() - self.app.ultimo_latido > inactividad_s):
                return "inactividad"
        return "detenido"

    def detener(self) -> None:
        self._parar.set()
        self._http.shutdown()
        self._http.server_close()

    def anotar(self, texto: str) -> None:
        if self.registro is None:
            return
        try:
            self.registro.parent.mkdir(parents=True, exist_ok=True)
            with open(self.registro, "a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {texto}\n")
        except OSError:
            pass


def _manejador(servidor: ServidorEditor):
    class Manejador(BaseHTTPRequestHandler):
        server_version = "Componedor"
        sys_version = ""

        def log_message(self, formato, *args):  # al registro, sin el token
            servidor.anotar(re.sub(r"t=[^ &\"]+", "t=***", formato % args))

        def do_GET(self):
            self._atender("GET")

        def do_POST(self):
            self._atender("POST")

        def do_PUT(self):
            self._responder(405, {"error": "Método no permitido."})

        do_DELETE = do_PATCH = do_PUT

        def _atender(self, metodo: str) -> None:
            rechazo = motivo_rechazo(metodo, self.path, self.headers, servidor.token,
                                     servidor.puerto)
            if rechazo is not None:
                self._responder(rechazo[0], {"error": rechazo[1]})
                return
            ruta = urlsplit(self.path).path
            if ruta != "/":
                servidor.app.latido()  # todo pedido de la API cuenta como señal del editor
            try:
                cuerpo = {}
                if metodo == "POST":
                    largo = int(self.headers.get("Content-Length") or 0)
                    crudo = self.rfile.read(largo) if largo else b"{}"
                    try:
                        cuerpo = json.loads(crudo.decode("utf-8") or "{}")
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        cuerpo = None
                    if not isinstance(cuerpo, dict):
                        self._responder(400, {"error": "El cuerpo no es un objeto JSON."})
                        return
                if ruta == "/":
                    self._pagina()
                    return
                if m := RUTA_PNG.match(ruta):
                    self._enviar(200, servidor.app.png_previa(m.group(1)), "image/png")
                    return
                if m := RUTA_PNG_ORTOFOTO.match(ruta):
                    self._enviar(200, servidor.app.ortofoto.png(m.group(1)), "image/png")
                    return
                if ruta == "/api/localizacion/imagen":
                    self._enviar(200, *servidor.app.localizacion.imagen())
                    return
                self._responder(200, self._api(metodo, ruta, cuerpo))
            except (ErrorAplicacion, ErrorOrtofoto, ErrorLocalizacion) as e:
                self._responder(e.estado_http, {"error": e.mensaje})
            except Exception as e:  # noqa: BLE001 - un pedido no tumba el servidor
                servidor.anotar(f"error interno en {metodo} {ruta}: {e!r}")
                self._responder(500, {"error": f"Error interno del servidor: {e}"})

        def _api(self, metodo: str, ruta: str, cuerpo: dict) -> dict:
            app = servidor.app
            if metodo == "GET" and ruta == "/api/estado":
                return app.estado()
            if metodo == "GET" and ruta == "/api/exportados":
                return app.exportados()
            if metodo == "GET" and ruta == "/api/estilos":
                return app.estilos()
            if metodo == "GET" and (m := RUTA_TAREA.match(ruta)):
                return app.tarea(m.group(1))
            if ruta == "/api/dxf/elegir":
                return app.elegir_y_cargar(cuerpo.get("estilo"))
            if ruta == "/api/dxf/recargar":
                return app.recargar(cuerpo.get("estilo"))
            if ruta == "/api/previa":
                return app.pedir_previa(cuerpo.get("ref"), cuerpo.get("estilo"))
            if ruta == "/api/previa/zona":
                return app.pedir_previa_zona(
                    cuerpo.get("zona"), cuerpo.get("vista"), cuerpo.get("capas"),
                    cuerpo.get("excluir"), cuerpo.get("escala"), cuerpo.get("estilo"))
            if ruta == "/api/textos/zona":
                return app.pedir_textos_zona(cuerpo.get("zona"), cuerpo.get("capas"),
                                             cuerpo.get("excluir"))
            if ruta == "/api/zonas/nombre":
                return app.nombre_zona(cuerpo.get("ocupados"))
            if ruta == "/api/exportar/zona":
                return app.exportar_zona(
                    cuerpo.get("zona"), cuerpo.get("capas"), cuerpo.get("excluir"),
                    cuerpo.get("escala"), cuerpo.get("nombre"), cuerpo.get("centro_mm"),
                    cuerpo.get("estilo"))
            if ruta == "/api/exportar":
                return app.exportar(cuerpo.get("bloques"), cuerpo.get("estilo"))
            if ruta == "/api/trabajador/detener":
                return app.detener()
            if ruta == "/api/trabajador/reiniciar":
                return app.reiniciar()
            if ruta == "/api/latido":
                return app.latido()
            if ruta == "/api/ortofoto":
                return {"ortofoto": app.ortofoto.estado()}
            if ruta == "/api/ortofoto/elegir":
                return app.ortofoto.elegir(cuerpo.get("archivo_plano"))
            if ruta == "/api/ortofoto/quitar":
                return app.ortofoto.quitar()
            if ruta == "/api/ortofoto/previa":
                return app.ortofoto.previa(cuerpo)
            if ruta == "/api/localizacion":
                return {"localizacion": app.localizacion.estado()}
            if ruta == "/api/localizacion/elegir":
                return app.localizacion.elegir(cuerpo.get("archivo_plano"))
            if ruta == "/api/localizacion/quitar":
                return app.localizacion.quitar()
            m = RUTA_CANCELAR.match(ruta)
            return app.cancelar(m.group(1))

        def _pagina(self) -> None:
            try:
                html = servidor.app.ruta_html.read_bytes()
            except OSError:
                self._responder(500, {"error": f"No se encontró {servidor.app.ruta_html}: "
                                               "genere el editor (Abrir editor.bat lo hace)."})
                return
            self._enviar(200, html, "text/html; charset=utf-8")

        def _responder(self, codigo: int, datos: dict) -> None:
            cuerpo = json.dumps(datos, ensure_ascii=False).encode("utf-8")
            self._enviar(codigo, cuerpo, "application/json; charset=utf-8")

        def _enviar(self, codigo: int, cuerpo: bytes, tipo: str) -> None:
            self.send_response(codigo, HTTPStatus(codigo).phrase)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(cuerpo)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(cuerpo)

    return Manejador
