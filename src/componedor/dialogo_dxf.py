"""Cuadro nativo de Windows para elegir un DXF («Cargar DXF» del editor).

El navegador no puede dar la RUTA de un archivo elegido (solo su contenido), y subir un DXF
de cientos de MB por HTTP no tiene sentido. Por eso el cuadro lo abre el SERVIDOR, con
`tkinter` (biblioteca estándar), en un PROCESO APARTE: tkinter no convive bien con los hilos
del servidor y así un cuadro colgado no traba nada. El proceso escribe una línea JSON
`{"ruta": "<ruta>" | null}` y termina.

El editor nunca manda una ruta: el servidor carga solo lo que eligió este cuadro, después de
`validar_dxf`.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import componedor

TITULO = "Cargar DXF"


class DxfInvalido(ValueError):
    """La ruta elegida no es un DXF que se pueda cargar (mensaje en español)."""


def validar_dxf(ruta: Path | str) -> Path:
    """Ruta absoluta de un archivo .dxf que existe; DxfInvalido si no."""
    ruta = Path(ruta).resolve()
    if ruta.suffix.lower() != ".dxf":
        raise DxfInvalido(f"«{ruta.name}» no es un archivo .dxf.")
    if not ruta.is_file():
        raise DxfInvalido(f"No existe el archivo «{ruta}».")
    return ruta


def comando_dialogo(inicial: Path | None) -> list[str]:
    argv = [sys.executable, "-m", "componedor.dialogo_dxf"]
    if inicial is not None:
        argv += ["--inicial", str(inicial)]
    return argv


def elegir_dxf(inicial: Path | None = None) -> Path | None:
    """Abre el cuadro y espera. La ruta elegida (validada) o None si se canceló."""
    entorno = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    raiz_paquete = str(Path(componedor.__file__).resolve().parent.parent)
    entorno["PYTHONPATH"] = os.pathsep.join(
        p for p in (raiz_paquete, entorno.get("PYTHONPATH")) if p)
    r = subprocess.run(comando_dialogo(inicial), capture_output=True, env=entorno, check=False)
    return interpretar_salida(r.returncode, r.stdout.decode("utf-8", "replace"),
                              r.stderr.decode("utf-8", "replace"))


def interpretar_salida(codigo: int, salida: str, errores: str = "") -> Path | None:
    """La ruta que devolvió el proceso del cuadro (o None); DxfInvalido si falló."""
    lineas = [linea for linea in salida.splitlines() if linea.strip()]
    if codigo != 0 or not lineas:
        detalle = (errores.strip().splitlines() or ["sin detalle"])[-1]
        raise DxfInvalido(f"No se pudo abrir el cuadro para elegir el DXF ({detalle}).")
    try:
        ruta = json.loads(lineas[-1]).get("ruta")
    except (json.JSONDecodeError, AttributeError):
        raise DxfInvalido("El cuadro para elegir el DXF respondió algo inesperado.") from None
    return validar_dxf(ruta) if ruta else None


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Cuadro para elegir un DXF (lo usa el servidor).")
    p.add_argument("--inicial", type=Path, help="Carpeta en la que se abre el cuadro.")
    args = p.parse_args(argv)
    import tkinter
    from tkinter import filedialog

    raiz = tkinter.Tk()
    raiz.withdraw()
    raiz.attributes("-topmost", True)  # delante del navegador
    inicial = args.inicial if args.inicial and args.inicial.is_dir() else None
    ruta = filedialog.askopenfilename(
        parent=raiz, title=TITULO, initialdir=str(inicial) if inicial else None,
        filetypes=[("Dibujos DXF", "*.dxf"), ("Todos los archivos", "*.*")])
    raiz.destroy()
    print(json.dumps({"ruta": ruta or None}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
