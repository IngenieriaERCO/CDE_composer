"""Estilo de impresión al exportar desde el editor: tabla CTB y transparencia de los rellenos.

El Exportador (manifiesto 1.4) acepta en `export` y `preview`:
- `plot_style`: la RUTA de una tabla `.ctb` de AutoCAD (colores, grises, grosores al imprimir);
- `print_transparency`: con `false` no dibuja los rellenos con transparencia del 80 % o más.

Reglas del Componedor:
- Las tablas viven en UNA carpeta (`componedor.json` → `exportador.carpeta_ctb`, hoy la del
  Exportador). El servidor arma la lista; el editor elige por NOMBRE (o «sin CTB») y nunca manda
  rutas: `elegir` solo acepta un nombre de esa lista y la ruta la pone el servidor.
- Valores por defecto en `componedor.json` (`estilo_impresion`, `imprimir_transparencia`). La
  elección no se guarda en el plano.json: cada detalle dice en su manifiesto con qué se exportó.
- Nombre del paquete: `marca` agrega `_p<6 cifras del SHA-256 de la CTB>` y `_t` (sin
  transparencia), como la caché de vistas previas del Exportador. Sin opciones, el nombre de
  siempre. Así no choca con los paquetes viejos del mismo bloque a la misma escala, y si la CTB
  cambia en el disco sale un paquete nuevo.
"""

import hashlib
import json
import re
import zlib
from dataclasses import dataclass
from pathlib import Path

EXTENSION = ".ctb"
CABECERA_CTB = 60  # bytes de cabecera antes del texto comprimido (zlib)
LARGO_MARCA = 6
RE_NOMBRE = re.compile(r"^[^\\/:*?\"<>|]+\.ctb$", re.IGNORECASE)


class EstiloInvalido(ValueError):
    """El estilo pedido no se puede usar (mensaje en español)."""


@dataclass(frozen=True)
class EstiloImpresion:
    nombre: str  # el del archivo (lo único que ve el editor)
    sha256: str
    descripcion: str
    ruta: Path  # solo para el servidor y el trabajador

    def para_el_editor(self) -> dict:
        return {"nombre": self.nombre, "sha256": self.sha256, "descripcion": self.descripcion}


def descripcion_ctb(datos: bytes) -> str:
    """La descripción guardada en la tabla («Derivada del PDF de AutoCAD…»), o ""."""
    try:
        texto = zlib.decompress(datos[CABECERA_CTB:]).rstrip(b"\0")
    except zlib.error:
        return ""
    try:
        texto = texto.decode("utf-8")
    except UnicodeDecodeError:
        texto = texto.decode("cp1252", errors="replace")
    for linea in texto.splitlines():
        if linea.startswith("description="):
            return linea.split("=", 1)[1].strip().strip('"').strip()
    return ""


def nombre_valido(nombre) -> bool:
    """Un nombre de archivo .ctb sin carpetas (ni «..», ni «/», ni «\\»)."""
    return (isinstance(nombre, str) and bool(RE_NOMBRE.match(nombre))
            and Path(nombre).name == nombre and ".." not in nombre)


def listar(carpeta: Path | None) -> list[EstiloImpresion]:
    """Las tablas .ctb de la carpeta (solo ese nivel), por nombre. [] si no hay carpeta."""
    if carpeta is None or not Path(carpeta).is_dir():
        return []
    estilos = []
    for ruta in sorted(Path(carpeta).iterdir(), key=lambda p: p.name.lower()):
        if not (ruta.is_file() and ruta.suffix.lower() == EXTENSION and nombre_valido(ruta.name)):
            continue
        try:
            datos = ruta.read_bytes()
        except OSError:
            continue
        estilos.append(EstiloImpresion(ruta.name, hashlib.sha256(datos).hexdigest(),
                                       descripcion_ctb(datos), ruta.resolve()))
    return estilos


def elegir(carpeta: Path | None, nombre) -> EstiloImpresion | None:
    """La tabla de ese NOMBRE en la carpeta (None = «sin CTB»). EstiloInvalido si el nombre no
    es de la lista: nunca se arma una ruta con lo que manda el editor."""
    if nombre is None:
        return None
    if not nombre_valido(nombre):
        raise EstiloInvalido(f"«{nombre}» no es el nombre de una tabla .ctb (solo el nombre del "
                             f"archivo, sin carpetas).")
    for estilo in listar(carpeta):
        if estilo.nombre.lower() == nombre.lower():
            return estilo
    raise EstiloInvalido(f"La tabla de estilos «{nombre}» no está en la carpeta de tablas "
                         f"({carpeta}).")


def marca(sha256: str | None, imprimir_transparencia: bool) -> str:
    """Lo que se agrega al nombre del paquete: `_p<6>` con CTB y `_t` sin transparencia."""
    texto = f"_p{sha256[:LARGO_MARCA]}" if sha256 else ""
    return texto + ("" if imprimir_transparencia else "_t")


def opciones(estilo: EstiloImpresion | None, imprimir_transparencia: bool) -> dict:
    """Lo que va en `options` de export (o en `data` de preview). Sin opciones, nada: el
    pedido queda igual que antes del manifiesto 1.4."""
    datos = {}
    if estilo is not None:
        datos["plot_style"] = str(estilo.ruta)
    if not imprimir_transparencia:
        datos["print_transparency"] = False
    return datos


def estilo_del_manifiesto(datos: dict) -> dict:
    """{ctb: nombre | None, sha256: … | None, transparencia: bool} de `options` del manifiesto.
    Un manifiesto anterior al 1.4 no trae esas opciones: sin CTB y con transparencia."""
    opciones_m = datos.get("options") if isinstance(datos, dict) else None
    opciones_m = opciones_m if isinstance(opciones_m, dict) else {}
    ps = opciones_m.get("plot_style")
    ps = ps if isinstance(ps, dict) else {}
    nombre = ps.get("name") if isinstance(ps.get("name"), str) else None
    sha = ps.get("sha256") if isinstance(ps.get("sha256"), str) else None
    return {"ctb": nombre, "sha256": sha,
            "transparencia": opciones_m.get("print_transparency") is not False}


def leer_estilo_del_manifiesto(ruta: Path) -> dict | None:
    try:
        return estilo_del_manifiesto(json.loads(Path(ruta).read_text(encoding="utf-8")))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def texto_estilo(estilo: dict | None) -> str:
    """«CTB_ERCO_derivada_PRGD.ctb (b4a909…), sin transparencia» o «sin CTB»."""
    if not estilo:
        return "desconocido"
    texto = (f"{estilo['ctb']} ({str(estilo.get('sha256') or '')[:LARGO_MARCA]}…)"
             if estilo.get("ctb") else "sin CTB")
    return texto + ("" if estilo.get("transparencia", True) else ", sin transparencia")
