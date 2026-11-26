"""Trabajador FALSO del exportador (protocolo 1.3) para las pruebas del Componedor.

Se lanza como el de verdad: `python trabajador_falso.py worker --work-dir CARPETA`. Sigue el
contrato final (`docs/protocolo_trabajador.md` del exportador, aprobado el 2026-11-17) en lo que
usan las etapas 1 a 3 (`load`, `preview`, `export`, `status`, `cancel`, `close`):

- stdout solo lleva JSON por líneas, en UTF-8; el registro va a stderr (§1).
- `status` y `cancel` se responden SIEMPRE, también durante un paso que no se puede cortar: un
  hilo lee stdin y otro hace el trabajo (§1, §7). `status` trae `stage`.
- `handle` nunca es null, en hexadecimal y mayúsculas (§2.1); `file_stem` ya cumple §5.1
  (sin acentos, solo A–Z, a–z, 0–9, «.», «-», «_», 60 caracteres como mucho con sufijo de hash).
- `load`: `units` y `margin_mm` valen para la sesión; `include_layers: false` deja `layers`
  vacío (§3); cada bloque trae `bounds_with_hidden` (null si no tiene nada oculto, §3.1).
- Bloques anónimos (§3.1): todos los bloques traen `anonymous`, `label` y `visible_entities`.
  Un bloque del «DXF» con `"anonimo": true` (nombre `*U…`) se ofrece si dibuja al menos
  `anonymous_min_entities` entidades visibles (opción de `load`, 100 por defecto; entero ≥ 1
  o BAD_REQUEST), con `label` = capa + «_» + handle y ese `file_stem`; si no, va a `omitted`
  con `anonymous: true` y `visible_entities`.
- `preview` y `export` aceptan el bloque por `ref` o por `handle` solo (§4; el del INSERT, sin
  distinguir mayúsculas): NOT_EXPORTABLE si es de `omitted`, REFERENCE_NOT_FOUND si no existe,
  BAD_REQUEST si está repetido. `load` devuelve el umbral usado (`anonymous_min_entities`).
- `preview` (§4): PNG transparente hecho con PyMuPDF, con un cuadrito negro de 5 × 5 px centrado
  en el punto CAD `marca` del bloque (por defecto el centro de su caja), para que las pruebas
  comprueben que el PNG cae donde debe. `cad_to_px` sin giro y a = −d; caché en
  `previews/<huella>/<handle>_<px>_visible.png` (`cached: true` la segunda vez).
  `NO_SESSION` si la sesión no es la actual y `DXF_CHANGED` si cambió el tamaño o la fecha (§9).
- `export` (§5): publica paquetes COHERENTES (PDF con el contorno del dibujo donde dice
  page_bounds_mm, manifiesto 1.3 con sha256 del PDF, TXT), a la escala pedida y con el margen de
  load; los prepara en una carpeta `.cde-tmp-*` de la salida y los mueve (manifiesto el último).
  Comprueba antes: sesión, DXF cambiado, referencias, escala, nombres (§5.1), repetidos y
  OUTPUT_EXISTS; `units`/`margin_mm` distintos de load → BAD_REQUEST. Avance por trabajo con las
  etapas del contrato; cancelar deja publicados los ya hechos.
- Estilo de impresión (manifiesto 1.4): `plot_style` (ruta de una .ctb; BAD_REQUEST si no
  existe) y `print_transparency` en `preview` y en `options` de `export`. El manifiesto los
  guarda como el real (`options.plot_style` = {name, sha256}) y la vista previa los devuelve
  y les da otro nombre en la caché (`_p<sha6>`, `_t`). Con "ignorar_estilo": true en el «DXF»,
  publica como si no los hubiera pedido (para probar la verificación).

El «DXF» es un JSON con lo que debe responder `load` y cómo portarse:

    {"blocks": [{"name": "B1", "size_cad": [10, 4], "handle": "1A"}, ...],
     "units": {"name": "m", "millimeters_per_unit": 1000, "verified": true},
     "omitted": [...], "notices": [...],
     "pasos": 4, "demora_s": 0.0,       # avance: cuatro etapas, con esa espera en cada una
     "no_cancelable_s": 0,              # un paso que no mira la cancelación (como ezdxf)
     "caer_en_paso": null,              # termina el proceso (código 3) en ese paso
     "respuesta": null,                 # reemplaza la respuesta entera (para probar errores)
     "previa_demora_s": 0.0,            # espera en cada etapa de preview (draw, paint)
     "respuesta_previa": null,          # reemplaza la respuesta de preview
     "export_demora_s": 0.0,            # espera en cada etapa de export
     "export_no_cancelable_s": 0,       # un paso de export que no mira la cancelación
     "dejar_temporal": false,           # deja una carpeta .cde-tmp-* en la salida
     "error_interno": null,             # ["TypeError", "mensaje"]: INTERNAL en load, como el real
     "export_error_interno": null,      # lo mismo en export
     "ignorar_estilo": false}           # export publica sin la CTB ni la transparencia pedidas
y en cada bloque: "anonimo": true y "visible_entities": n (por defecto "entities"); para
preview: "marca": [x, y] (punto CAD) y "bounds_previa": {"min", "max"}
(la caja de lo dibujado; por defecto la de load); para export: "bounds_exacta" (la caja exacta,
si la de load es aproximada), "falla_export": "mensaje" (EXPORT_FAILED en ese trabajo) y
"escala_no_garantizada": true.

Zonas del Model Space (protocolo 1.1, §4.1): `preview` con `zone` o `view` en lugar del bloque.
El «DXF» puede traer "modelo": {"bounds": [x0, y0, x1, y1] (por defecto, la unión de las cajas
de los bloques), "capas": [{"name", "entities", "cad_state"}] (por defecto la «0" con 10),
"grupos": [{"number", "box", "entities"}]}. La imagen se ajusta a `view`, si no a `zone`, si no
a todo el Model Space; `groups` solo sin zona ni vista; `paper` con `scale`; BAD_REQUEST si
`layers` nombra capas que no existen. Caché `ms-<10 cifras>_<px>_visible.png`.

`export` con trabajos de zona (§5.4): paquete 1.5 de «Model_Space» con `selection` (kind
modelspace, window = zone, layers, exclude_layers) y máscara (`pdf.drawing.mask`). El dibujo es el
contorno de la zona más una línea del centro que se sale de la zona y de la página, como lo que
la máscara oculta (el falso no la recorta de verdad; `get_drawings()` tampoco la aplica). Con
"zona_otra_ventana": true en el «DXF», el manifiesto dice otra ventana (para la verificación).
La fila trae kind, zone, package_name y name_generated.

Vista previa preparada (protocolo 1.2, §4.2): tras responder a `load` (salvo con
`prepare_preview: false` o con --protocolo 1.0/1.1), prepara en segundo plano y manda eventos
`preview_progress` (boxes, draw, index), y `preview_ready` (con la CTB y la transparencia de
`prepare_preview`) o `preview_failed`. `load` responde `preview_preparation` (running). El
«DXF» puede traer "preparar_s" (lo que tarda, 0,3 s por defecto) y "preparar_falla" (el
mensaje de `preview_failed`). La preparación se detiene con otro `load`.

`texts` (protocolo 1.3, §4.3): los textos de "modelo": {"textos": [{"text", "x", "y", "layer",
"scales": ["1:25"], "axis": null | "H" | "V"}]} cuyo punto cae en la zona y cuya capa se ve con
el filtro; `scale_candidates` agrupa por escala y eje (de la que más sale a la que menos) y
`proposed_scale` solo con una sola escala sin eje. Con --protocolo 1.2 o menos: UNKNOWN_COMMAND.

Opciones de arranque para las pruebas: --cancel-no-aceptado (responde `accepted: false` y sigue
trabajando, como el real con un pedido cuya respuesta ya viene en camino), --protocolo 1.0 (un
exportador sin zonas), --protocolo 2.0, --sin-ready, --basura (una línea que no
es JSON antes de ready), --nieto RUTA (lanza un proceso nieto y escribe su PID en RUTA).
"""

import argparse
import fnmatch
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import threading
import time
import unicodedata
from pathlib import Path

ETAPAS = ("read", "hash", "blocks", "layers")
ETAPAS_PREVIA = ("draw", "paint")
ETAPAS_EXPORT = ("extract", "analyze", "draw", "pdf", "checks", "publish")
MENSAJES_EXPORT = {"extract": "Extrayendo", "analyze": "Analizando", "draw": "Dibujando",
                   "pdf": "Escribiendo el PDF de", "checks": "Comprobando", "publish": "Publicando"}
RE_PAQUETE = re.compile(r"^[A-Za-z0-9_-][A-Za-z0-9._-]*$")
MM_A_PT = 72 / 25.4
MAX_PAQUETE = 60


def marca_estilo(estilo) -> str:
    """La del Exportador en la caché de vistas previas: `_p<sha6>` y `_t`."""
    if not estilo:
        return ""
    ps = estilo.get("plot_style")
    return (f"_p{ps['sha256'][:6]}" if ps else "") + ("" if estilo["print_transparency"] else "_t")


def nombre_paquete(nombre: str) -> str:
    """El `file_stem` como lo propone el trabajador (§5.1 del contrato)."""
    sin_tildes = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode()
    limpio = re.sub(r"[^A-Za-z0-9._-]", "_", sin_tildes).lstrip(".") or "_"
    if len(limpio) <= MAX_PAQUETE:
        return limpio
    sufijo = hashlib.sha256(nombre.encode()).hexdigest()[:6]
    return limpio[:MAX_PAQUETE - 7] + "_" + sufijo


def filtrar_anonimos(spec: dict, umbral: int) -> dict:
    """Los anónimos con menos de `umbral` entidades visibles pasan de `blocks` a `omitted`."""
    ofrecidos, omitidos = [], list(spec.get("omitted", []))
    for b in spec.get("blocks", []):
        visibles = b.get("visible_entities", b.get("entities", 10))
        if b.get("anonimo") is True and visibles < umbral:
            omitidos.append({"name": b["name"], "occurrence": 1, "total_occurrences": 1,
                             "handle": b.get("handle", "0"), "anonymous": True,
                             "visible_entities": visibles,
                             "reason": f"bloque anónimo con {visibles} entidades visibles "
                                       f"(se ofrecen desde {umbral})"})
        else:
            ofrecidos.append(b)
    return {**spec, "blocks": ofrecidos, "omitted": omitidos}


class Falso:
    def __init__(self, args):
        self.args = args
        self.escritura = threading.Lock()
        self.en_curso: str | None = None
        self.etapa: str | None = None
        self.cancelado = threading.Event()
        self.sesion = 0
        self.dxf: str | None = None
        self.cargado: dict | None = None  # ruta, firma (tamaño, fecha), spec, bloques por ref

    def enviar(self, mensaje: dict) -> None:
        with self.escritura:
            sys.stdout.buffer.write((json.dumps(mensaje, ensure_ascii=False) + "\n").encode())
            sys.stdout.buffer.flush()

    def _fin(self, id_):
        """El pedido en curso termina: se libera ANTES de responder (como el real), así el
        siguiente pedido que llegue enseguida no recibe BUSY."""
        if id_ is not None and id_ == self.en_curso:
            self.en_curso = None

    def responder(self, id_, comando, data):
        self._fin(id_)
        self.enviar({"protocol": "1.0", "id": id_, "type": "result", "command": comando,
                     "data": data})

    def error(self, id_, codigo, mensaje, consejo=None, detalles=None):
        self._fin(id_)
        self.enviar({"protocol": "1.0", "id": id_, "type": "error",
                     "error": {"code": codigo, "message": mensaje, "advice": consejo,
                               "details": detalles or {}}})

    # --- bucle de lectura (hilo principal) ----------------------------------------------------

    def correr(self) -> int:
        if self.args.basura:
            sys.stdout.buffer.write(b"esto no es JSON\n")
            sys.stdout.buffer.flush()
        if self.args.nieto:
            nieto = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
            Path(self.args.nieto).write_text(str(nieto.pid), encoding="utf-8")
        if self.args.sin_ready:
            time.sleep(120)
            return 0
        self.enviar({"protocol": self.args.protocolo, "id": None, "type": "ready",
                     "data": {"protocol_version": self.args.protocolo,
                              "exporter_version": "0.0-falso", "ezdxf": "-", "pymupdf": "-",
                              "manifest_schema_version": "1.3",
                              "work_dir": self.args.work_dir}})
        for crudo in sys.stdin.buffer:
            try:
                pedido = json.loads(crudo.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self.error(None, "BAD_REQUEST", "La línea no es JSON.")
                continue
            id_, comando = pedido.get("id"), pedido.get("command")
            datos = pedido.get("data") or {}
            print(f"pedido {id_} {comando}", file=sys.stderr, flush=True)
            if str(pedido.get("protocol", "")).split(".")[0] != "1":
                self.error(id_, "PROTOCOL_VERSION", "Versión del protocolo no admitida.")
            elif comando == "status":
                self.responder(id_, comando, {"busy": self.en_curso is not None,
                                              "current": self.en_curso,
                                              "stage": self.etapa if self.en_curso else None,
                                              "session": f"s-{self.sesion}" if self.dxf else None,
                                              "dxf": self.dxf, "memory_mb": 12})
            elif comando == "cancel":
                aceptado = (self.en_curso is not None and datos.get("target") == self.en_curso
                            and not self.args.cancel_no_aceptado)
                if aceptado:
                    self.cancelado.set()
                self.responder(id_, comando, {"accepted": aceptado})
            elif comando == "close":
                self.cancelado.set()
                self.responder(id_, comando, {})
                return 0
            elif comando == "texts" and self.menor() < 3:
                self.error(id_, "UNKNOWN_COMMAND", f"Orden desconocida: {comando!r}.")
            elif comando in ("load", "preview", "export", "texts"):
                if self.en_curso is not None:
                    self.error(id_, "BUSY", f"Ya hay un pedido en curso ({self.en_curso}).")
                    continue
                self.en_curso = id_
                self.cancelado.clear()
                threading.Thread(target=self.atender, args=(id_, comando, datos),
                                 daemon=True).start()
            else:
                self.error(id_, "UNKNOWN_COMMAND", f"Orden desconocida: {comando!r}.")
        return 0  # fin de stdin: cierre limpio

    # --- trabajo (otro hilo) ------------------------------------------------------------------

    def atender(self, id_, comando, datos):
        try:
            if comando == "load":
                self.cargar(id_, datos)
            elif comando == "preview":
                self.previar(id_, datos)
            elif comando == "texts":
                self.textos(id_, datos)
            else:
                self.exportar(id_, datos)
        finally:
            self.en_curso = None

    def cargar(self, id_, datos):
        ruta = Path(str(datos.get("dxf", "")))
        if not ruta.is_file():
            self.error(id_, "DXF_NOT_FOUND", f"No existe el DXF «{ruta}».",
                       "Revise la ruta del archivo.", {"dxf": str(ruta)})
            return
        contenido = ruta.read_bytes()
        try:
            spec = json.loads(contenido.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.error(id_, "DXF_INVALID", f"«{ruta.name}» no es un DXF que se pueda leer.")
            return
        umbral = datos.get("anonymous_min_entities", 100)
        if isinstance(umbral, bool) or not isinstance(umbral, int) or umbral < 1:
            self.error(id_, "BAD_REQUEST", "«anonymous_min_entities» debe ser un entero ≥ 1.")
            return
        spec = filtrar_anonimos(spec, umbral)
        demora = float(spec.get("demora_s", 0))
        for i, etapa in enumerate(ETAPAS[:int(spec.get("pasos", 4))], start=1):
            self.etapa = etapa
            if spec.get("caer_en_paso") == i:
                print("¡caída simulada!", file=sys.stderr, flush=True)
                os._exit(3)
            if i == 1 and spec.get("no_cancelable_s"):
                time.sleep(float(spec["no_cancelable_s"]))  # no mira la cancelación
            fin = time.monotonic() + demora
            while time.monotonic() < fin:
                if self.cancelado.is_set():
                    break
                time.sleep(0.01)
            if self.cancelado.is_set():
                self.dxf = None
                self.cargado = None
                self.error(id_, "CANCELLED", "Carga cancelada.")
                return
            self.enviar({"protocol": "1.0", "id": id_, "type": "progress",
                         "data": {"job": None, "job_index": None, "job_total": None,
                                  "stage": etapa, "stage_index": i, "stage_total": len(ETAPAS),
                                  "percent": 100.0 * i / len(ETAPAS),
                                  "message": f"Etapa {etapa} de «{ruta.name}»"}})
        if spec.get("error_interno"):
            self.interno(id_, spec["error_interno"])
            return
        if spec.get("respuesta") is not None:
            self.responder(id_, "load", spec["respuesta"])
            return
        self.sesion += 1
        self.dxf = ruta.name
        respuesta = self.respuesta_load(ruta, contenido, spec, datos)
        estado = ruta.stat()
        self.cargado = {"ruta": ruta, "firma": (estado.st_size, estado.st_mtime_ns), "spec": spec,
                        "huella": respuesta["dxf"]["fingerprint"], "dxf": respuesta["dxf"],
                        "units": datos.get("units"), "margen": respuesta["margin_mm"],
                        "mm_unidad": respuesta["units"]["millimeters_per_unit"],
                        "bloques": {b["ref"]: (b, s) for b, s in
                                    zip(respuesta["blocks"], spec.get("blocks", []))}}
        prepara = self.menor() >= 2 and datos.get("prepare_preview", True) is not False
        respuesta["preview_preparation"] = (
            {"state": "running", "stage": "boxes", "percent": 0.0, "plot_style": None,
             "print_transparency": True, "error": None} if prepara else None)
        if self.menor() < 2:
            del respuesta["preview_preparation"]  # un trabajador 1.0/1.1 no la conoce
        self.responder(id_, "load", respuesta)
        if prepara:
            self.preparar(f"s-{self.sesion}", spec, datos.get("prepare_preview"))

    def previar(self, id_, datos):
        c = self.cargado
        if c is None or datos.get("session") != f"s-{self.sesion}":
            self.error(id_, "NO_SESSION", "No hay un DXF cargado con esa sesión.",
                       "Vuelva a cargar el DXF.", {"session": datos.get("session")})
            return
        try:
            estado = c["ruta"].stat()
            cambio = (estado.st_size, estado.st_mtime_ns) != c["firma"]
        except OSError:
            cambio = True
        if cambio:
            self.error(id_, "DXF_CHANGED", f"El DXF «{c['ruta'].name}» cambió desde que se cargó.",
                       "Vuelva a cargarlo.", {"dxf": str(c["ruta"])})
            return
        if "zone" in datos or "view" in datos:
            self.previar_zona(id_, c, datos)
            return
        ref = self._referencia(id_, c, datos)
        if ref is None:
            return
        bloque, spec_bloque = c["bloques"][ref]
        demora = float(c["spec"].get("previa_demora_s", 0))
        for i, etapa in enumerate(ETAPAS_PREVIA, start=1):
            self.etapa = etapa
            fin = time.monotonic() + demora
            while time.monotonic() < fin and not self.cancelado.is_set():
                time.sleep(0.01)
            if self.cancelado.is_set():
                self.error(id_, "CANCELLED", "Vista previa cancelada.")
                return
            self.enviar({"protocol": "1.0", "id": id_, "type": "progress",
                         "data": {"job": None, "job_index": None, "job_total": None,
                                  "stage": etapa, "stage_index": i,
                                  "stage_total": len(ETAPAS_PREVIA),
                                  "percent": 100.0 * i / len(ETAPAS_PREVIA),
                                  "message": f"Vista previa de «{bloque['name']}»: {etapa}"}})
        if c["spec"].get("respuesta_previa") is not None:
            self.responder(id_, "preview", c["spec"]["respuesta_previa"])
            return
        estilo = self._estilo(id_, datos)
        if estilo is None:
            return
        self.responder(id_, "preview", self.dibujar_previa(
            bloque, spec_bloque, int(datos.get("long_side_px") or 1500), c["huella"], estilo))

    def previar_zona(self, id_, c, datos):
        """§4.1: vista previa de una zona (o de todo el Model Space, con sus grupos)."""
        import pymupdf  # solo aquí: load no lo necesita

        modelo = c["spec"].get("modelo", {})
        filas = modelo.get("capas") or [{"name": "0", "entities": 10}]
        solo, excluir = datos.get("layers") or [], datos.get("exclude_layers") or []
        casa = lambda capa, patrones: any(
            fnmatch.fnmatchcase(capa.lower(), p.lower()) for p in patrones)
        sin_capa = [p for p in solo if not any(casa(f["name"], [p]) for f in filas)]
        if sin_capa:
            self.error(id_, "BAD_REQUEST", f"La capa «{sin_capa[0]}» no está en el DXF.", None,
                       {"layers": sin_capa})
            return
        estilo = self._estilo(id_, datos)
        if estilo is None:
            return
        fin = time.monotonic() + float(c["spec"].get("previa_demora_s", 0))
        while time.monotonic() < fin:
            if self.cancelado.is_set():
                self.error(id_, "CANCELLED", "Vista previa cancelada.")
                return
            time.sleep(0.01)
        zona, vista = datos.get("zone"), datos.get("view")
        if modelo.get("bounds"):
            todo = modelo["bounds"]
        else:
            cajas = [b["bounds"] for b, _ in c["bloques"].values()]
            todo = [min(k["min"][0] for k in cajas), min(k["min"][1] for k in cajas),
                    max(k["max"][0] for k in cajas), max(k["max"][1] for k in cajas)]
        x0, y0, x1, y1 = vista or zona or todo
        lado = int(datos.get("long_side_px") or 1500)
        s = lado / max(x1 - x0, y1 - y0)
        ancho, alto = max(1, round((x1 - x0) * s)), max(1, round((y1 - y0) * s))
        matriz = [s, 0.0, 0.0, -s, -s * x0, s * y1]
        clave = hashlib.sha1(json.dumps([zona, vista, solo, excluir]).encode()).hexdigest()[:10]
        png = (Path(self.args.work_dir) / "previews" / c["huella"]
               / f"ms-{clave}_{lado}_visible{marca_estilo(estilo)}.png")
        en_cache = png.is_file()
        if not en_cache:
            pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, ancho, alto), 1)
            pix.clear_with()
            png.parent.mkdir(parents=True, exist_ok=True)
            pix.save(str(png))
        filas_resp = []
        for f in filas:
            se_ve = (f.get("cad_state") is None and (not solo or casa(f["name"], solo))
                     and not casa(f["name"], excluir))
            filas_resp.append({"name": f["name"], "entities_in_view": f.get("entities", 10),
                               "cad_state": f.get("cad_state"), "shown": se_ve})
        papel, escala = None, datos.get("scale")
        if escala is not None:
            n = float(str(escala).split(":")[-1])
            bx0, by0, bx1, by1 = zona or vista or todo
            mm = c["mm_unidad"] / n
            contenido = [(bx1 - bx0) * mm, (by1 - by0) * mm]
            pagina = [v + 2 * c["margen"] for v in contenido]
            papel = {"content_mm": contenido, "page_mm": pagina, "margin_mm": c["margen"],
                     "fits_a1": (max(pagina) <= 841 and min(pagina) <= 594)}
            escala = f"1:{n:g}"
        self.responder(id_, "preview", {
            "png": str(png), "kind": "zone", "ref": None, "handle": None, "px": [ancho, alto],
            "bounds": {"min": [x0, y0], "max": [x1, y1]}, "cad_to_px": matriz,
            "zone": zona, "view": [x0, y0, x1, y1], "layers": solo, "exclude_layers": excluir,
            "layer_rows": filas_resp,
            "entities": {"in_view": sum(f["entities_in_view"] for f in filas_resp),
                         "drawn": sum(f["entities_in_view"] for f in filas_resp if f["shown"]),
                         "without_bounds": 0},
            "groups": modelo.get("grupos", []) if zona is None and vista is None else [],
            "scale": escala, "paper": papel, "omitted": {"3DSOLID": 0, "REGION": 0},
            "include_hidden_layers": None, "cached": en_cache, "seconds": 0.01, **estilo})

    def textos(self, id_, datos):
        """§4.3: los textos de la zona (por su punto) con el filtro de capas, y la escala."""
        c = self._sesion_o_error(id_, datos)
        if c is None:
            return
        zona = datos.get("zone")
        if not (isinstance(zona, list) and len(zona) == 4):
            self.error(id_, "BAD_REQUEST", "Falta «zone».")
            return
        solo, excluir = datos.get("layers") or [], datos.get("exclude_layers") or []
        casa = lambda capa, patrones: any(
            fnmatch.fnmatchcase(capa.lower(), p.lower()) for p in patrones)
        vistos = [t for t in c["spec"].get("modelo", {}).get("textos", [])
                  if zona[0] <= t["x"] <= zona[2] and zona[1] <= t["y"] <= zona[3]
                  and (not solo or casa(t["layer"], solo)) and not casa(t["layer"], excluir)]
        grupos = {}
        for t in vistos:
            for escala in t.get("scales", []):
                k = (escala, t.get("axis"))
                g = grupos.setdefault(k, {"scale": escala, "denominator": float(escala.split(":")[1]),
                                          "axis": t.get("axis"), "count": 0, "sources": []})
                g["count"] += 1
                g["sources"].append({"text": t["text"], "x": t["x"], "y": t["y"],
                                     "layer": t["layer"], "handle": "1A"})
        candidatos = sorted(grupos.values(), key=lambda g: -g["count"])
        propuesta = (candidatos[0]["scale"] if len(candidatos) == 1 and candidatos[0]["axis"] is None
                     else None)
        self.responder(id_, "texts", {
            "zone": zona, "layers": solo, "exclude_layers": excluir, "include_hidden_layers": None,
            "total": len(vistos), "truncated": False,
            "texts": [{"text": t["text"], "kind": "TEXT", "x": t["x"], "y": t["y"], "height": 0.1,
                       "rotation": 0.0, "layer": t["layer"], "handle": "1A", "modelspace_handle": "1A",
                       "blocks": [], "scales": t.get("scales", [])} for t in vistos],
            "scale_candidates": candidatos, "proposed_scale": propuesta, "seconds": 0.01})

    def menor(self) -> int:
        """La versión menor del protocolo que habla (2 en la 1.2)."""
        partes = str(self.args.protocolo).split(".")
        return int(partes[1]) if len(partes) > 1 and partes[1].isdigit() else 0

    def preparar(self, sesion, spec, pedido):
        """§4.2: prepara en otro hilo y avisa con eventos (sin pedido: id null)."""
        config = pedido if isinstance(pedido, dict) else {}
        ctb = config.get("plot_style")
        estilo = ({"name": Path(ctb).name, "sha256": "ab" * 32} if isinstance(ctb, str) else None)
        transparencia = config.get("print_transparency", True) is not False
        duracion = float(spec.get("preparar_s", 0.3))

        def evento(nombre, data):
            self.enviar({"protocol": self.args.protocolo, "id": None, "type": "event",
                         "event": nombre, "data": {"session": sesion, **data}})

        def trabajar():
            pasos = (("boxes", 20.0), ("draw", 50.0), ("draw", 80.0), ("index", 100.0))
            for etapa, porcentaje in pasos:
                time.sleep(duracion / len(pasos))
                if f"s-{self.sesion}" != sesion:
                    return  # otro load: se detiene sin aviso
                evento("preview_progress", {"stage": etapa, "percent": porcentaje,
                                            "message": f"Preparando la vista previa: {etapa}"})
            if spec.get("preparar_falla"):
                evento("preview_failed", {"message": spec["preparar_falla"]})
                return
            evento("preview_ready", {"items": 1234, "points": 5678, "memory_mb": 1.5,
                                     "seconds": duracion, "plot_style": estilo,
                                     "print_transparency": transparencia})

        threading.Thread(target=trabajar, daemon=True).start()

    def _estilo(self, id_, datos) -> dict | None:
        """{plot_style: {name, sha256} | None, print_transparency} del pedido (None si no vale)."""
        ruta = datos.get("plot_style")
        transparencia = datos.get("print_transparency", True)
        if not isinstance(transparencia, bool):
            self.error(id_, "BAD_REQUEST", "«print_transparency» debe ser true o false.")
            return None
        if ruta is None:
            return {"plot_style": None, "print_transparency": transparencia}
        if not isinstance(ruta, str) or not Path(ruta).is_file():
            self.error(id_, "BAD_REQUEST", f"No existe el archivo de «plot_style»: {ruta}",
                       None, {"option": "plot_style"})
            return None
        return {"plot_style": {"name": Path(ruta).name,
                               "sha256": hashlib.sha256(Path(ruta).read_bytes()).hexdigest()},
                "print_transparency": transparencia}

    # --- export ---------------------------------------------------------------------------------

    def _referencia(self, id_, c, datos) -> str | None:
        """El ref del bloque pedido por `ref`, o por `handle` solo (sin `block`, §4): sin
        distinguir mayúsculas; NOT_EXPORTABLE si es de `omitted`, REFERENCE_NOT_FOUND si no
        existe, BAD_REQUEST si está repetido. None si ya respondió con el error."""
        if datos.get("ref") is not None:
            if datos["ref"] in c["bloques"]:
                return datos["ref"]
            self.error(id_, "REFERENCE_NOT_FOUND", f"No existe la referencia «{datos['ref']}».")
            return None
        handle = datos.get("handle")
        if "block" in datos or not isinstance(handle, str) or not handle:
            self.error(id_, "BAD_REQUEST", "Falta «ref», o «block» con «occurrence» o «handle».")
            return None
        refs = [r for r, (b, _) in c["bloques"].items() if b["handle"].upper() == handle.upper()]
        if len(refs) == 1:
            return refs[0]
        if refs:
            self.error(id_, "BAD_REQUEST", f"El handle «{handle}» está repetido en el DXF.",
                       None, {"refs": refs})
        elif any(str(o.get("handle", "")).upper() == handle.upper()
                 for o in c["spec"].get("omitted", [])):
            self.error(id_, "NOT_EXPORTABLE", f"La referencia con handle «{handle}» no se puede "
                       "exportar.")
        else:
            self.error(id_, "REFERENCE_NOT_FOUND", f"No existe una referencia con handle "
                       f"«{handle}».")
        return None

    def _sesion_o_error(self, id_, datos) -> dict | None:
        c = self.cargado
        if c is None or datos.get("session") != f"s-{self.sesion}":
            self.error(id_, "NO_SESSION", "No hay un DXF cargado con esa sesión.",
                       "Vuelva a cargar el DXF.", {"session": datos.get("session")})
            return None
        return c

    def _cambio(self, c) -> bool:
        try:
            estado = c["ruta"].stat()
            return (estado.st_size, estado.st_mtime_ns) != c["firma"]
        except OSError:
            return True

    def exportar(self, id_, datos):
        c = self._sesion_o_error(id_, datos)
        if c is None:
            return
        if self._cambio(c):
            self.error(id_, "DXF_CHANGED", f"El DXF «{c['ruta'].name}» cambió desde que se cargó.",
                       "Vuelva a cargarlo.", {"dxf": str(c["ruta"])})
            return
        opciones = datos.get("options") or {}
        if "margin_mm" in opciones and opciones["margin_mm"] != c["margen"]:
            self.error(id_, "BAD_REQUEST", "«margin_mm» distinto del de load.")
            return
        if "units" in opciones and opciones["units"] != c["units"]:
            self.error(id_, "BAD_REQUEST", "«units» distintas de las de load.")
            return
        estilo = self._estilo(id_, opciones)
        if estilo is None:
            return
        if c["spec"].get("ignorar_estilo"):
            estilo = {"plot_style": None, "print_transparency": True}
        c["estilo"] = estilo
        salida = Path(str(datos.get("output_dir") or ""))
        if not salida.is_dir():
            self.error(id_, "OUTPUT_INVALID", f"«{salida}» no es una carpeta.")
            return
        trabajos = datos.get("jobs") or []
        vistos = set()
        for t in trabajos:
            paquete = str(t.get("package", ""))
            if (not RE_PAQUETE.match(paquete) or len(paquete) > 60
                    or len(str(salida / (paquete + ".manifest.json"))) > 240):
                self.error(id_, "OUTPUT_INVALID", f"Nombre de paquete no válido: «{paquete}».")
                return
            if paquete in vistos:
                self.error(id_, "OUTPUT_INVALID", f"Paquete repetido: «{paquete}».")
                return
            vistos.add(paquete)
            if "zone" in t:
                z = t.get("zone")
                if not (isinstance(z, list) and len(z) == 4 and z[2] > z[0] and z[3] > z[1]):
                    self.error(id_, "BAD_REQUEST", "«zone» no válida.", None,
                               {"job": t.get("job")})
                    return
                capas = [f["name"].lower() for f in
                         c["spec"].get("modelo", {}).get("capas") or [{"name": "0"}]]
                sin_capa = [x for x in t.get("layers") or []
                            if not any(fnmatch.fnmatchcase(k, x.lower()) for k in capas)]
                if sin_capa:
                    self.error(id_, "BAD_REQUEST", f"La capa «{sin_capa[0]}» no está en el DXF.")
                    return
                t["ref"] = None
            else:
                ref = self._referencia(id_, c, t)
                if ref is None:
                    return
                t["ref"] = ref  # lo demás del falso sigue por ref
            m = re.match(r"^1:(\d+(?:\.\d+)?)$", str(t.get("scale", "")))
            if not m or float(m.group(1)) <= 0:
                self.error(id_, "BAD_REQUEST", f"Escala no válida: «{t.get('scale')}».")
                return
            if not opciones.get("overwrite"):
                for ext in (".pdf", ".txt", ".manifest.json"):
                    if (salida / (paquete + ext)).exists():
                        self.error(id_, "OUTPUT_EXISTS", f"Ya existe «{paquete}{ext}».",
                                   None, {"file": str(salida / (paquete + ext))})
                        return
        if c["spec"].get("export_error_interno"):
            self.interno(id_, c["spec"]["export_error_interno"])
            return
        resultados = []
        demora = float(c["spec"].get("export_demora_s", 0))
        total = len(ETAPAS_EXPORT) * len(trabajos)
        for j, t in enumerate(trabajos, start=1):
            if self._cambio(c):  # antes de cada trabajo (§9)
                self.error(id_, "DXF_CHANGED", f"El DXF «{c['ruta'].name}» cambió.",
                           "Vuelva a cargarlo.", {"jobs": resultados})
                return
            if t["ref"] is None:
                bloque, spec_bloque = {"name": "Model_Space"}, {}
            else:
                bloque, spec_bloque = c["bloques"][t["ref"]]
            for i, etapa in enumerate(ETAPAS_EXPORT, start=1):
                self.etapa = etapa
                if etapa == "draw" and c["spec"].get("export_no_cancelable_s"):
                    time.sleep(float(c["spec"]["export_no_cancelable_s"]))
                fin = time.monotonic() + demora
                while time.monotonic() < fin and not self.cancelado.is_set():
                    time.sleep(0.01)
                if self.cancelado.is_set():
                    for pendiente in trabajos[j - 1:]:
                        resultados.append({"job": pendiente.get("job"), "ref": pendiente.get("ref"),
                                           "status": "cancelled", "package": None})
                    self.error(id_, "CANCELLED", "Exportación cancelada.", None,
                               {"jobs": resultados})
                    return
                hechas = (j - 1) * len(ETAPAS_EXPORT) + i
                self.enviar({"protocol": "1.0", "id": id_, "type": "progress",
                             "data": {"job": t.get("job"), "job_index": j, "job_total": len(trabajos),
                                      "stage": etapa, "stage_index": i,
                                      "stage_total": len(ETAPAS_EXPORT),
                                      "percent": 100.0 * hechas / total,
                                      "message": f"{MENSAJES_EXPORT[etapa]} «{bloque['name']}»"}})
            if spec_bloque.get("falla_export"):
                resultados.append({"job": t.get("job"), "ref": t["ref"], "status": "failed",
                                   "package": None, "validation_status": None,
                                   "physical_scale_guaranteed": None, "page_size_mm": None,
                                   "notices": [], "seconds": 0.01,
                                   "error": {"code": "EXPORT_FAILED",
                                             "message": spec_bloque["falla_export"]}})
                continue
            resultados.append(self.publicar_zona(salida, t, c) if t["ref"] is None
                              else self.publicar(salida, t, bloque, spec_bloque, c))
        publicados = sum(r["status"] == "published" for r in resultados)
        self.responder(id_, "export", {
            "output_dir": str(salida), "jobs": resultados, "summary": None,
            "totals": {"published": publicados, "failed": len(resultados) - publicados,
                       "cancelled": 0}})

    def interno(self, id_, falla):
        """El error INTERNAL del trabajador real: texto de Python y el consejo de repetir."""
        tipo, texto = falla
        self.error(id_, "INTERNAL", f"Error inesperado del exportador ({tipo}): {texto}",
                   "Repita el pedido; si vuelve a fallar, guarde el registro de stderr.",
                   {"type": tipo})

    def publicar(self, salida, t, bloque, spec_bloque, c):
        import pymupdf

        n = float(t["scale"].split(":")[1])
        margen = c["margen"]
        mm = bloque["units"]["millimeters_per_unit"]
        caja = spec_bloque.get("bounds_exacta") or bloque["bounds"]
        (x0, y0), (x1, y1) = caja["min"], caja["max"]
        k = mm / n
        ancho, alto = (x1 - x0) * k + 2 * margen, (y1 - y0) * k + 2 * margen
        matriz = [k, 0.0, 0.0, -k, margen - k * x0, margen + k * y1]
        dibujo = [margen, margen, margen + (x1 - x0) * k, margen + (y1 - y0) * k]
        doc = pymupdf.open()
        pagina = doc.new_page(width=ancho * MM_A_PT, height=alto * MM_A_PT)
        px0, py0, px1, py1 = (v * MM_A_PT for v in dibujo)
        esquinas = [pymupdf.Point(px0, py0), pymupdf.Point(px1, py0), pymupdf.Point(px1, py1),
                    pymupdf.Point(px0, py1)]
        pagina.draw_polyline(esquinas + [esquinas[0]], color=(0, 0, 0), width=0.5)
        pdf = doc.tobytes()
        doc.close()
        paquete = t["package"]
        manifiesto = {
            "document_type": "cde-detail-manifest", "schema_version": "1.3", "model_version": "2",
            "generated_at": "2026-11-17T10:00:00-05:00",
            "exporter": {"version": "0.0-falso", "ezdxf": "-", "pymupdf": "-"},
            "source": {"dxf_name": c["dxf"]["name"], "dxf_sha256": c["dxf"]["sha256"],
                       "dxf_bytes": c["dxf"]["bytes"], "block_name": bloque["name"],
                       "block_definition_handle": "1F",
                       "reference": {"handle": bloque["handle"], "occurrence": bloque["occurrence"],
                                     "total_occurrences": bloque["total_occurrences"],
                                     "layer": bloque["layer"], "selection_method": "worker"}},
            "units": {"declared_code": 6, "name": bloque["units"]["name"],
                      "millimeters_per_unit": mm, "status": "falso", "user_override": None},
            "scale": {"requested": t["scale"], "denominator": n, "factor_mm_per_cad_unit": k,
                      "physical_scale_guaranteed": not spec_bloque.get("escala_no_garantizada"),
                      "physical_scale_reason": None},
            "pdf": {"file_name": f"{paquete}.pdf", "bytes": len(pdf),
                    "sha256": hashlib.sha256(pdf).hexdigest(), "page_count": 1,
                    "page_size_mm": [ancho, alto], "expected_page_size_mm": [ancho, alto],
                    "margin_mm": margen, "content_size_mm": [ancho - 2 * margen, alto - 2 * margen],
                    "drawing": {"cad_bounds": {"min": [x0, y0], "max": [x1, y1]},
                                "page_bounds_mm": dict(zip(("x0", "y0", "x1", "y1"), dibujo)),
                                "cad_to_page": {"units": "mm", "origin": "top-left",
                                                "y_axis": "down", "matrix": matriz}}},
            "entities": {"total": 1, "by_type": [], "by_layer": [], "not_conserved": []},
            "fonts": [], "dependencies": [],
            "notices": {"counts": {"info": 0, "warning": 0, "critical": 0}, "by_category": {}},
            "validation": {"status": "complete", "checks": []}, "selection": None,
            "options": {"margin_mm": margen, "units": c["units"], "include_hidden_layers": None,
                        **c.get("estilo", {})},
        }
        temporal = salida / f".cde-tmp-{os.getpid()}-{t.get('job')}"
        temporal.mkdir(exist_ok=True)
        (temporal / "pid").write_text(str(os.getpid()), encoding="utf-8")
        (temporal / f"{paquete}.pdf").write_bytes(pdf)
        (temporal / f"{paquete}.txt").write_text(
            f"Paquete falso de «{bloque['name']}» a {t['scale']}\n", encoding="utf-8")
        (temporal / f"{paquete}.manifest.json").write_text(
            json.dumps(manifiesto, ensure_ascii=False, indent=2), encoding="utf-8")
        for ext in (".pdf", ".txt", ".manifest.json"):  # el manifiesto, el último
            os.replace(temporal / f"{paquete}{ext}", salida / f"{paquete}{ext}")
        if not c["spec"].get("dejar_temporal"):
            (temporal / "pid").unlink()
            temporal.rmdir()
        return {"job": t.get("job"), "ref": t["ref"], "status": "published",
                "package": {e: str(salida / f"{paquete}{x}") for e, x in
                            (("pdf", ".pdf"), ("txt", ".txt"), ("manifest", ".manifest.json"))},
                "validation_status": "complete",
                "physical_scale_guaranteed": not spec_bloque.get("escala_no_garantizada"),
                "page_size_mm": [ancho, alto], "notices": [], "error": None, "seconds": 0.01}

    def publicar_zona(self, salida, t, c):
        """Paquete 1.5 de una zona, con máscara (§5.4 y docs/manifiesto.md del exportador)."""
        import pymupdf

        n = float(t["scale"].split(":")[1])
        margen, mm = c["margen"], c["mm_unidad"]
        x0, y0, x1, y1 = t["zone"]
        k = mm / n
        ancho, alto = (x1 - x0) * k + 2 * margen, (y1 - y0) * k + 2 * margen
        matriz = [k, 0.0, 0.0, -k, margen - k * x0, margen + k * y1]
        zona_pag = [margen, margen, ancho - margen, alto - margen]
        doc = pymupdf.open()
        pagina = doc.new_page(width=ancho * MM_A_PT, height=alto * MM_A_PT)
        zx0, zy0, zx1, zy1 = (v * MM_A_PT for v in zona_pag)
        pagina.draw_rect(pymupdf.Rect(zx0, zy0, zx1, zy1), color=(0, 0, 0), width=0.5)
        medio = (zy0 + zy1) / 2  # una «cota» que sale de la zona y de la página
        pagina.draw_line(pymupdf.Point((zx0 + zx1) / 2, medio),
                         pymupdf.Point(ancho * MM_A_PT + 40, medio), color=(0, 0, 0), width=0.25)
        pdf = doc.tobytes()
        doc.close()
        paquete = t["package"]
        ventana = list(t["zone"])
        if c["spec"].get("zona_otra_ventana"):
            ventana[0] -= 1.0
        manifiesto = {
            "document_type": "cde-detail-manifest", "schema_version": "1.5", "model_version": "2",
            "generated_at": "2026-11-24T10:00:00-05:00",
            "exporter": {"version": "0.0-falso", "ezdxf": "-", "pymupdf": "-"},
            "source": {"dxf_name": c["dxf"]["name"], "dxf_sha256": c["dxf"]["sha256"],
                       "dxf_bytes": c["dxf"]["bytes"], "block_name": "Model_Space",
                       "block_definition_handle": "10D",
                       "reference": {"handle": "112", "occurrence": 1, "total_occurrences": 1,
                                     "layer": "0", "selection_method": "automatic"}},
            "units": {"declared_code": 6, "name": "m", "millimeters_per_unit": mm,
                      "status": "falso", "user_override": None},
            "scale": {"requested": t["scale"], "denominator": n, "factor_mm_per_cad_unit": k,
                      "physical_scale_guaranteed": True, "physical_scale_reason": None},
            "pdf": {"file_name": f"{paquete}.pdf", "bytes": len(pdf),
                    "sha256": hashlib.sha256(pdf).hexdigest(), "page_count": 1,
                    "page_size_mm": [ancho, alto], "expected_page_size_mm": [ancho, alto],
                    "margin_mm": margen, "content_size_mm": [ancho - 2 * margen, alto - 2 * margen],
                    "drawing": {"cad_bounds": {"min": [x0, y0], "max": [x1, y1]},
                                "page_bounds_mm": dict(zip(("x0", "y0", "x1", "y1"), zona_pag)),
                                "cad_to_page": {"units": "mm", "origin": "top-left",
                                                "y_axis": "down", "matrix": matriz},
                                "mask": {"zone_cad": list(t["zone"]),
                                         "zone_page_mm": dict(zip(("x0", "y0", "x1", "y1"),
                                                                  zona_pag)),
                                         "bleed_mm": 0.5}}},
            "entities": {"total": 2, "by_type": [], "by_layer": [], "not_conserved": []},
            "fonts": [], "dependencies": [],
            "notices": {"counts": {"info": 0, "warning": 0, "critical": 0}, "by_category": {}},
            "validation": {"status": "complete", "checks": []},
            "selection": {"kind": "modelspace", "layers": t.get("layers") or [],
                          "exclude_layers": t.get("exclude_layers") or [], "window": ventana,
                          "window_from_block": None, "entities": 2},
            "options": {"margin_mm": margen, "units": c["units"], "include_hidden_layers": None,
                        "clip": True, **c.get("estilo", {})},
        }
        (salida / f"{paquete}.pdf").write_bytes(pdf)
        (salida / f"{paquete}.txt").write_text(f"Zona falsa {ventana} a {t['scale']}\n",
                                               encoding="utf-8")
        (salida / f"{paquete}.manifest.json").write_text(
            json.dumps(manifiesto, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"job": t.get("job"), "ref": None, "handle": None, "kind": "zone",
                "zone": list(t["zone"]), "package_name": paquete, "name_generated": False,
                "status": "published",
                "package": {e: str(salida / f"{paquete}{x}") for e, x in
                            (("pdf", ".pdf"), ("txt", ".txt"), ("manifest", ".manifest.json"))},
                "validation_status": "complete", "physical_scale_guaranteed": True,
                "page_size_mm": [ancho, alto], "notices": [], "error": None, "seconds": 0.01}

    def dibujar_previa(self, bloque, spec_bloque, lado, huella, estilo=None):
        import pymupdf  # solo aquí: load no lo necesita

        caja = spec_bloque.get("bounds_previa") or bloque["bounds"]
        (x0, y0), (x1, y1) = caja["min"], caja["max"]
        s = lado / max(x1 - x0, y1 - y0)
        ancho, alto = max(1, round((x1 - x0) * s)), max(1, round((y1 - y0) * s))
        matriz = [s, 0.0, 0.0, -s, -s * x0, s * y1]
        png = (Path(self.args.work_dir) / "previews" / huella
               / f"{bloque['handle']}_{lado}_visible{marca_estilo(estilo)}.png")
        en_cache = png.is_file()
        if not en_cache:
            mx, my = spec_bloque.get("marca") or [(x0 + x1) / 2, (y0 + y1) / 2]
            cx = math.floor(matriz[0] * mx + matriz[4])  # el píxel que contiene el punto
            cy = math.floor(matriz[3] * my + matriz[5])
            pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, ancho, alto), 1)
            pix.clear_with()  # todos los bytes en 0: transparente (alfa 0)
            for x in range(cx - 2, cx + 3):
                for y in range(cy - 2, cy + 3):
                    if 0 <= x < ancho and 0 <= y < alto:
                        pix.set_pixel(x, y, (0, 0, 0, 255))
            png.parent.mkdir(parents=True, exist_ok=True)
            pix.save(str(png))
        return {"png": str(png), "px": [ancho, alto],
                "bounds": {"min": [x0, y0], "max": [x1, y1]}, "cad_to_px": matriz,
                "omitted": {"3DSOLID": bloque["contains"]["solids_3d"], "REGION": 0},
                "cached": en_cache, "seconds": 0.01, **(estilo or {})}

    def respuesta_load(self, ruta, contenido, spec, datos):
        unidades = {"declared_code": 6, "name": "m", "millimeters_per_unit": 1000.0,
                    "status": "declaradas en el DXF y coherentes", "verified": True,
                    "warnings": [], **spec.get("units", {})}
        if datos.get("units"):
            unidades.update(name=datos["units"], verified=True, user_override=True)
        nombres = [b["name"] for b in spec.get("blocks", [])]
        bloques = []
        for b in spec.get("blocks", []):
            ocurrencia = nombres[:len(bloques) + 1].count(b["name"])
            total = nombres.count(b["name"])
            w, h = b.get("size_cad", [1.0, 1.0])
            x0, y0 = b.get("min", [1000.0, 2000.0])
            mm = unidades["millimeters_per_unit"] if unidades["verified"] else None
            u = {**unidades, **b.get("units", {})}
            handle = b.get("handle", f"{0x1A0 + len(bloques):X}")
            anonimo = b.get("anonimo") is True
            etiqueta = f"{b.get('layer', '0')}_{handle}" if anonimo else b["name"]
            bloques.append({
                "ref": f"{b['name']}#{ocurrencia}", "name": b["name"],
                "handle": handle, "anonymous": anonimo, "label": etiqueta,
                "visible_entities": b.get("visible_entities", b.get("entities", 10)),
                "occurrence": ocurrencia,
                "total_occurrences": total, "layer": b.get("layer", "0"),
                "insert": {"point": [0.0, 0.0, 0.0], "rotation_deg": 0.0, "scale": [1, 1, 1]},
                "bounds": {"min": [x0, y0], "max": [x0 + w, y0 + h],
                           "exact": b.get("exact", True)},
                "bounds_with_hidden": ({"min": [x0, y0], "max": [x0 + w, y0 + h + 1.0],
                                        "exact": b.get("exact", True)}
                                       if b.get("hidden_layer_entities") else None),
                "size_cad": [w, h],
                "size_m": b.get("size_m", [w * mm / 1000, h * mm / 1000] if mm else None),
                "units": u, "entities": b.get("entities", 10),
                "contains": {"solids_3d": 0, "regions": 0, "proxies": 0, "texts": 0,
                             "hatches": 0, "images": 0, **b.get("contains", {})},
                "hidden_layer_entities": b.get("hidden_layer_entities", 0),
                "file_stem": b.get("file_stem") or nombre_paquete(
                    etiqueta if anonimo
                    else b["name"] + (f"_{ocurrencia:03d}" if total > 1 else ""))})
        return {
            "session": f"s-{self.sesion}",
            "dxf": {"name": ruta.name, "path": str(ruta), "bytes": len(contenido),
                    "modified": "2026-11-17T08:00:00-05:00",
                    "fingerprint": hashlib.sha256(contenido[:4096]).hexdigest(),
                    "sha256": hashlib.sha256(contenido).hexdigest(), "dxf_version": "AC1032",
                    "read_seconds": 0.01, "source_copy": None,
                    **({"crs": spec["crs"]} if "crs" in spec else {})},
            "units": unidades, "margin_mm": float(datos.get("margin_mm", 5.0)),
            "anonymous_min_entities": datos.get("anonymous_min_entities", 100),
            "blocks": bloques, "omitted": spec.get("omitted", []),
            "layers": ([{"name": "0", "color": {"aci": 7, "rgb": "#000000"},
                         "effective_colors": [], "lineweight_mm": None,
                         "linetype": {"name": "Continuous", "description": ""},
                         "state": {"on": True, "frozen": False, "plot": True},
                         "description": "", "usage": []}]
                       if datos.get("include_layers", True) else []),
            "modelspace_loose": [], "notices": spec.get("notices", [])}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("orden", choices=["worker"])
    p.add_argument("--work-dir", required=True)
    p.add_argument("--protocolo", default="1.3")
    p.add_argument("--sin-ready", action="store_true")
    p.add_argument("--basura", action="store_true")
    p.add_argument("--nieto")
    p.add_argument("--cancel-no-aceptado", action="store_true",
                   help="responde accepted: false y sigue (como el real con un pedido que ya termina)")
    p.add_argument("--preview-cache-mb", type=int, default=500)
    args = p.parse_args()
    return Falso(args).correr()


if __name__ == "__main__":
    sys.exit(main())
