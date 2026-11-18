"""Exportar un bloque de un DXF a un paquete (etapa 3): lo que hace el Componedor alrededor de
la orden `export` del trabajador.

- **Dónde**: `<paquetes>/<nombre del DXF>/<file_stem>_1-N.{pdf,txt,manifest.json}`
  (`paquetes` = `exportador.paquetes`, por defecto `data/input/dxf`). Nombre del paquete:
  `nombres_paquete.nombre_paquete`.
- **Caché**: si ese paquete ya está publicado y es el de este bloque (mismo SHA-256 del DXF,
  mismo handle, misma escala y mismo margen) y pasa `importar_paquete`, se usa sin exportar.
- **Paquetes viejos**: si en su lugar hay otro (de otra versión del DXF, a medio publicar…), sus
  archivos se MUEVEN a `_para_borrar/paquetes_<fecha>/<ruta relativa>` (nunca se borran) y
  recién entonces se exporta.
- **Verificación**: cada paquete exportado pasa por `importar_paquete` (completo, íntegro y
  coherente, escala física garantizada) y además debe ser el pedido: SHA-256 del DXF, handle,
  escala y margen, y una página que no pase de la caja que se vio en el editor.
- **Colocación por el centro CAD**: el punto CAD que estaba en el centro de la caja del editor
  (centro de la caja de `load`) va a `centro_mm`. Con la matriz `cad_to_page` del manifiesto
  (mm de página, origen arriba a la izquierda, Y abajo):

      (px, py) = cad_to_page · C
      posicion_mm = (centro_x − px, centro_y − (alto − py))   # esquina inferior izquierda

  Con caja exacta es la página centrada en `centro_mm`; con caja aproximada, el dibujo queda
  donde se veía.
"""

import json
import math
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from componedor.importador import PaqueteAceptado, PaqueteRechazado, importar_paquete
from componedor.nombres_paquete import limpiar, nombre_paquete

EXTENSIONES = (".manifest.json", ".pdf", ".txt")
TOL_MM = 0.1  # tolerancia de medidas del proyecto
TOL_RELATIVA = 1e-9


@dataclass(frozen=True)
class Pedido:
    """Lo que se espera del paquete de un bloque."""
    sha256: str  # del DXF cargado
    handle: str
    denominador: float  # N de 1:N
    margen_mm: float
    pagina_max_mm: tuple[float, float]  # la caja del editor (con caja aproximada, un máximo)
    caja_exacta: bool = True


class PaqueteNoValido(ValueError):
    """El paquete exportado (o el de la caché) no es el pedido o no se puede usar."""

    def __init__(self, motivos: list[str]):
        super().__init__("; ".join(motivos))
        self.motivos = motivos


def carpeta_del_dxf(paquetes: Path, nombre_dxf: str) -> Path:
    """`<paquetes>/<nombre del DXF sin extensión, limpio>`."""
    return Path(paquetes) / limpiar(Path(nombre_dxf).stem)


def nombre_del_paquete(file_stem: str, denominador: float) -> str:
    n = int(denominador) if float(denominador).is_integer() else denominador
    return nombre_paquete(file_stem, n)


def archivos_del_paquete(carpeta: Path, paquete: str) -> list[Path]:
    """Los archivos de ese paquete que existen (para la caché o para moverlos)."""
    return [carpeta / f"{paquete}{ext}" for ext in EXTENSIONES
            if (carpeta / f"{paquete}{ext}").exists()]


def _leer_json(ruta: Path) -> dict:
    try:
        datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        raise PaqueteNoValido([f"no se pudo leer el manifiesto: {e}"]) from None
    if not isinstance(datos, dict):
        raise PaqueteNoValido(["el manifiesto no es un objeto JSON"])
    return datos


def _get(datos: dict, ruta: str):
    for parte in ruta.split("."):
        datos = datos.get(parte) if isinstance(datos, dict) else None
    return datos


def _numero(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def motivos_de_otro_pedido(datos: dict, pedido: Pedido) -> list[str]:
    """Por qué el manifiesto `datos` NO es el paquete de `pedido` ([] si lo es)."""
    motivos = []
    sha = _get(datos, "source.dxf_sha256")
    if sha != pedido.sha256:
        motivos.append(f"es de otra versión del DXF (SHA-256 {str(sha)[:12]}…, se esperaba "
                       f"{pedido.sha256[:12]}…)")
    handle = _get(datos, "source.reference.handle")
    if handle != pedido.handle:
        motivos.append(f"es de otra referencia (handle {handle}, se esperaba {pedido.handle})")
    n = _get(datos, "scale.denominator")
    if not (_numero(n) and abs(n - pedido.denominador) <= TOL_RELATIVA * pedido.denominador):
        motivos.append(f"está a otra escala (1:{n}, se esperaba 1:{pedido.denominador:g})")
    margen = _get(datos, "pdf.margin_mm")
    if not (_numero(margen) and abs(margen - pedido.margen_mm) <= 1e-6):
        motivos.append(f"tiene otro margen ({margen} mm, se esperaba {pedido.margen_mm:g} mm)")
    pagina = _get(datos, "pdf.page_size_mm")
    if isinstance(pagina, list) and len(pagina) == 2 and all(_numero(v) for v in pagina):
        for eje, medido, maximo in (("ancho", pagina[0], pedido.pagina_max_mm[0]),
                                    ("alto", pagina[1], pedido.pagina_max_mm[1])):
            if medido > maximo + TOL_MM:
                motivos.append(f"la página mide {medido:.2f} mm de {eje}, más que la caja del "
                               f"editor ({maximo:.2f} mm)")
            elif pedido.caja_exacta and medido < maximo - TOL_MM:
                motivos.append(f"la página mide {medido:.2f} mm de {eje} y la caja exacta "
                               f"{maximo:.2f} mm")
    return motivos


def verificar(ruta_manifiesto: Path, pedido: Pedido) -> PaqueteAceptado:
    """`importar_paquete` + que sea el paquete pedido. PaqueteNoValido con los motivos."""
    try:
        aceptado = importar_paquete(ruta_manifiesto)
    except PaqueteRechazado as e:
        raise PaqueteNoValido([str(e)]) from None
    motivos = motivos_de_otro_pedido(_leer_json(ruta_manifiesto), pedido)
    if motivos:
        raise PaqueteNoValido(motivos)
    return aceptado


def de_la_cache(carpeta: Path, paquete: str, pedido: Pedido) -> Path | None:
    """El manifiesto del paquete ya publicado si es el pedido y se puede usar; None si no."""
    manifiesto = carpeta / f"{paquete}.manifest.json"
    if not manifiesto.is_file():
        return None
    try:
        verificar(manifiesto, pedido)
    except PaqueteNoValido:
        return None
    return manifiesto


def mover_a_para_borrar(archivos: list[Path], raiz: Path, para_borrar: Path,
                        momento: str | None = None) -> list[Path]:
    """Mueve `archivos` a `<para_borrar>/paquetes_<momento>/<ruta relativa a raiz>`, sin pisar
    nada (si ya existe, agrega _2, _3…). Devuelve las rutas nuevas. Nunca borra."""
    momento = momento or time.strftime("%Y%m%d-%H%M%S")
    destino_base = Path(para_borrar) / f"paquetes_{momento}"
    nuevas = []
    for archivo in archivos:
        try:
            relativa = Path(archivo).resolve().relative_to(Path(raiz).resolve())
        except ValueError:
            relativa = Path(Path(archivo).name)
        destino = destino_base / relativa
        n = 2
        while destino.exists():
            destino = destino.with_name(f"{destino.stem}_{n}{destino.suffix}")
            n += 1
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(archivo), str(destino))
        nuevas.append(destino)
    return nuevas


def posicion_por_centro(ruta_manifiesto: Path, centro_cad: tuple[float, float],
                        centro_mm: tuple[float, float]) -> tuple[float, float]:
    """Esquina inferior izquierda de la página (mm de papel) para que el punto CAD
    `centro_cad` quede en `centro_mm`."""
    datos = _leer_json(ruta_manifiesto)
    m = _get(datos, "pdf.drawing.cad_to_page.matrix")
    pagina = _get(datos, "pdf.page_size_mm")
    if not (isinstance(m, list) and len(m) == 6 and all(_numero(v) for v in m)
            and isinstance(pagina, list) and len(pagina) == 2):
        raise PaqueteNoValido(["el manifiesto no trae cad_to_page o page_size_mm"])
    a, b, c, d, e, f = m
    px = a * centro_cad[0] + c * centro_cad[1] + e
    py = b * centro_cad[0] + d * centro_cad[1] + f
    return (centro_mm[0] - px, centro_mm[1] - (pagina[1] - py))
