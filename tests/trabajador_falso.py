"""Trabajador FALSO del exportador (protocolo 1.0) para las pruebas del Componedor.

Se lanza como el de verdad: `python trabajador_falso.py worker --work-dir CARPETA`. Sigue el
contrato final (`docs/protocolo_trabajador.md` del exportador, aprobado el 2026-11-17) en lo que
usa la etapa 1 (`load`, `status`, `cancel`, `close`):

- stdout solo lleva JSON por líneas, en UTF-8; el registro va a stderr (§1).
- `status` y `cancel` se responden SIEMPRE, también durante un paso que no se puede cortar: un
  hilo lee stdin y otro hace el trabajo (§1, §7). `status` trae `stage`.
- `handle` nunca es null, en hexadecimal y mayúsculas (§2.1); `file_stem` ya cumple §5.1
  (sin acentos, solo A–Z, a–z, 0–9, «.», «-», «_», 60 caracteres como mucho con sufijo de hash).
- `load`: `units` y `margin_mm` valen para la sesión; `include_layers: false` deja `layers`
  vacío (§3); cada bloque trae `bounds_with_hidden` (null si no tiene nada oculto, §3.1).

El «DXF» es un JSON con lo que debe responder `load` y cómo portarse:

    {"blocks": [{"name": "B1", "size_cad": [10, 4], "handle": "1A"}, ...],
     "units": {"name": "m", "millimeters_per_unit": 1000, "verified": true},
     "omitted": [...], "notices": [...],
     "pasos": 4, "demora_s": 0.0,       # avance: cuatro etapas, con esa espera en cada una
     "no_cancelable_s": 0,              # un paso que no mira la cancelación (como ezdxf)
     "caer_en_paso": null,              # termina el proceso (código 3) en ese paso
     "respuesta": null}                 # reemplaza la respuesta entera (para probar errores)

Opciones de arranque para las pruebas: --protocolo 2.0, --sin-ready, --basura (una línea que no
es JSON antes de ready), --nieto RUTA (lanza un proceso nieto y escribe su PID en RUTA).
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
import unicodedata
from pathlib import Path

ETAPAS = ("read", "hash", "blocks", "layers")
MAX_PAQUETE = 60


def nombre_paquete(nombre: str) -> str:
    """El `file_stem` como lo propone el trabajador (§5.1 del contrato)."""
    sin_tildes = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode()
    limpio = re.sub(r"[^A-Za-z0-9._-]", "_", sin_tildes).lstrip(".") or "_"
    if len(limpio) <= MAX_PAQUETE:
        return limpio
    sufijo = hashlib.sha256(nombre.encode()).hexdigest()[:6]
    return limpio[:MAX_PAQUETE - 7] + "_" + sufijo


class Falso:
    def __init__(self, args):
        self.args = args
        self.escritura = threading.Lock()
        self.en_curso: str | None = None
        self.etapa: str | None = None
        self.cancelado = threading.Event()
        self.sesion = 0
        self.dxf: str | None = None

    def enviar(self, mensaje: dict) -> None:
        with self.escritura:
            sys.stdout.buffer.write((json.dumps(mensaje, ensure_ascii=False) + "\n").encode())
            sys.stdout.buffer.flush()

    def responder(self, id_, comando, data):
        self.enviar({"protocol": "1.0", "id": id_, "type": "result", "command": comando,
                     "data": data})

    def error(self, id_, codigo, mensaje, consejo=None, detalles=None):
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
                aceptado = self.en_curso is not None and datos.get("target") == self.en_curso
                if aceptado:
                    self.cancelado.set()
                self.responder(id_, comando, {"accepted": aceptado})
            elif comando == "close":
                self.cancelado.set()
                self.responder(id_, comando, {})
                return 0
            elif comando in ("load", "preview", "export"):
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
            else:
                self.error(id_, "NO_SESSION", "El trabajador falso solo sabe cargar.")
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
                self.error(id_, "CANCELLED", "Carga cancelada.")
                return
            self.enviar({"protocol": "1.0", "id": id_, "type": "progress",
                         "data": {"job": None, "job_index": None, "job_total": None,
                                  "stage": etapa, "stage_index": i, "stage_total": len(ETAPAS),
                                  "percent": 100.0 * i / len(ETAPAS),
                                  "message": f"Etapa {etapa} de «{ruta.name}»"}})
        if spec.get("respuesta") is not None:
            self.responder(id_, "load", spec["respuesta"])
            return
        self.sesion += 1
        self.dxf = ruta.name
        self.responder(id_, "load", self.respuesta_load(ruta, contenido, spec, datos))

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
            bloques.append({
                "ref": f"{b['name']}#{ocurrencia}", "name": b["name"],
                "handle": b.get("handle", f"{0x1A0 + len(bloques):X}"),
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
                    b["name"] + (f"_{ocurrencia:03d}" if total > 1 else ""))})
        return {
            "session": f"s-{self.sesion}",
            "dxf": {"name": ruta.name, "path": str(ruta), "bytes": len(contenido),
                    "modified": "2026-11-17T08:00:00-05:00",
                    "fingerprint": hashlib.sha256(contenido[:4096]).hexdigest(),
                    "sha256": hashlib.sha256(contenido).hexdigest(), "dxf_version": "AC1032",
                    "read_seconds": 0.01, "source_copy": None},
            "units": unidades, "margin_mm": float(datos.get("margin_mm", 5.0)),
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
    p.add_argument("--protocolo", default="1.0")
    p.add_argument("--sin-ready", action="store_true")
    p.add_argument("--basura", action="store_true")
    p.add_argument("--nieto")
    args = p.parse_args()
    return Falso(args).correr()


if __name__ == "__main__":
    sys.exit(main())
