"""Cuadro nativo de Windows para elegir un DXF («Cargar DXF» del editor).

El navegador no puede dar la RUTA de un archivo elegido (solo su contenido), y subir un DXF
de cientos de MB por HTTP no tiene sentido. Por eso el cuadro lo abre el SERVIDOR, con
`tkinter` (biblioteca estándar), en un PROCESO APARTE: tkinter no convive bien con los hilos
del servidor y así un cuadro colgado no traba nada. El proceso escribe una línea JSON
`{"ruta": "<ruta>" | null}` y termina.

El editor nunca manda una ruta: el servidor carga solo lo que eligió este cuadro, después de
`validar_dxf`.

El mismo cuadro sirve para «Cargar ortofoto» (`--tipo ortofoto`, archivos .tif/.tiff): la ruta
la valida `ortofoto.validar_ruta`.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import componedor

TITULO = "Cargar DXF"
# --tipo → (título del cuadro, tipos de archivo)
TIPOS = {
    "dxf": (TITULO, [("Dibujos DXF", "*.dxf"), ("Todos los archivos", "*.*")]),
    "ortofoto": ("Cargar ortofoto", [("Ortofotos GeoTIFF", "*.tif *.tiff"),
                                     ("Todos los archivos", "*.*")]),
}


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


def comando_dialogo(inicial: Path | None, tipo: str = "dxf") -> list[str]:
    argv = [sys.executable, "-m", "componedor.dialogo_dxf"]
    if tipo != "dxf":
        argv += ["--tipo", tipo]
    if inicial is not None:
        argv += ["--inicial", str(inicial)]
    return argv


def _abrir_cuadro(inicial: Path | None, tipo: str) -> subprocess.CompletedProcess:
    entorno = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    raiz_paquete = str(Path(componedor.__file__).resolve().parent.parent)
    entorno["PYTHONPATH"] = os.pathsep.join(
        p for p in (raiz_paquete, entorno.get("PYTHONPATH")) if p)
    return subprocess.run(comando_dialogo(inicial, tipo), capture_output=True, env=entorno,
                          check=False)


def elegir_dxf(inicial: Path | None = None) -> Path | None:
    """Abre el cuadro y espera. La ruta elegida (validada) o None si se canceló."""
    r = _abrir_cuadro(inicial, "dxf")
    return interpretar_salida(r.returncode, r.stdout.decode("utf-8", "replace"),
                              r.stderr.decode("utf-8", "replace"))


def elegir_ortofoto(inicial: Path | None = None) -> Path | None:
    """«Cargar ortofoto»: la ruta del GeoTIFF elegido (validada) o None si se canceló.
    OrtofotoInvalida si no sirve o si el cuadro falló."""
    from componedor.ortofoto import OrtofotoInvalida, validar_ruta

    r = _abrir_cuadro(inicial, "ortofoto")
    ruta = ruta_elegida(r.returncode, r.stdout.decode("utf-8", "replace"),
                        r.stderr.decode("utf-8", "replace"), "la ortofoto", OrtofotoInvalida)
    return validar_ruta(ruta) if ruta else None


def ruta_elegida(codigo: int, salida: str, errores: str, que: str,
                 error: type[ValueError]) -> str | None:
    """La ruta (sin validar) que devolvió el proceso del cuadro, o None si se canceló."""
    lineas = [linea for linea in salida.splitlines() if linea.strip()]
    if codigo != 0 or not lineas:
        detalle = (errores.strip().splitlines() or ["sin detalle"])[-1]
        raise error(f"No se pudo abrir el cuadro para elegir {que} ({detalle}).")
    try:
        ruta = json.loads(lineas[-1]).get("ruta")
    except (json.JSONDecodeError, AttributeError):
        raise error(f"El cuadro para elegir {que} respondió algo inesperado.") from None
    return ruta or None


def interpretar_salida(codigo: int, salida: str, errores: str = "") -> Path | None:
    """La ruta que devolvió el proceso del cuadro (o None); DxfInvalido si falló."""
    ruta = ruta_elegida(codigo, salida, errores, "el DXF", DxfInvalido)
    return validar_dxf(ruta) if ruta else None


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Cuadro para elegir un DXF (lo usa el servidor).")
    p.add_argument("--inicial", type=Path, help="Carpeta en la que se abre el cuadro.")
    p.add_argument("--tipo", choices=sorted(TIPOS), default="dxf", help="Qué se elige.")
    args = p.parse_args(argv)
    import tkinter
    from tkinter import filedialog

    raiz = tkinter.Tk()
    raiz.withdraw()
    raiz.attributes("-topmost", True)  # delante del navegador
    inicial = args.inicial if args.inicial and args.inicial.is_dir() else None
    titulo, tipos = TIPOS[args.tipo]
    ruta = filedialog.askopenfilename(
        parent=raiz, title=titulo, initialdir=str(inicial) if inicial else None,
        filetypes=tipos)
    raiz.destroy()
    print(json.dumps({"ruta": ruta or None}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
