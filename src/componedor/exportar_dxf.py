"""Exportar un bloque de un DXF a un paquete (etapa 3): lo que hace el Componedor alrededor de
la orden `export` del trabajador.

- **Dónde**: `<paquetes>/<nombre del DXF>/<file_stem>_1-N.{pdf,txt,manifest.json}`
  (`paquetes` = `exportador.paquetes`, por defecto `data/input/dxf`). Nombre del paquete:
  `nombres_paquete.nombre_paquete`.
- **Caché**: si ese paquete ya está publicado y es el de este bloque (mismo SHA-256 del DXF,
  mismo handle, misma escala, mismo margen y mismo estilo de impresión: CTB por su SHA-256 y
  transparencia) y pasa `importar_paquete`, se usa sin exportar.
- **Estilo de impresión** (estilos_impresion.py): el nombre lleva la marca `_p<sha6>` / `_t`,
  así un paquete con CTB no pisa el viejo sin CTB del mismo bloque y escala.
- **Paquetes viejos**: si en su lugar hay otro (de otra versión del DXF, a medio publicar…), sus
  archivos se MUEVEN a `_para_borrar/paquetes_<fecha>/<ruta relativa>` (nunca se borran) y
  recién entonces se exporta.
- **Verificación**: cada paquete exportado pasa por `importar_paquete` (completo, íntegro y
  coherente, escala física garantizada) y además debe ser el pedido: SHA-256 del DXF, handle,
  escala y margen, y una página que no pase de la caja que se vio en el editor. Una zona del
  Model Space (Fase 10c, `exportar_zona.py`) no tiene handle: se compara que sea del Model
  Space, su ventana y su filtro de capas.
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

from componedor.estilos_impresion import estilo_del_manifiesto, texto_estilo
from componedor.importador import PaqueteAceptado, PaqueteRechazado, importar_paquete
from componedor.nombres_paquete import limpiar, nombre_paquete

EXTENSIONES = (".manifest.json", ".pdf", ".txt")
TOL_MM = 0.1  # tolerancia de medidas del proyecto
TOL_RELATIVA = 1e-9
TOL_ZONA = 1e-9  # relativa: la ventana del manifiesto es la zona pedida (salvo coma flotante)


@dataclass(frozen=True)
class Pedido:
    """Lo que se espera del paquete de un bloque, o de una zona del Model Space (`zona`)."""
    sha256: str  # del DXF cargado
    handle: str  # del INSERT; "" en una zona
    denominador: float  # N de 1:N
    margen_mm: float
    pagina_max_mm: tuple[float, float]  # la caja del editor (con caja aproximada, un máximo)
    caja_exacta: bool = True
    ctb_sha256: str | None = None  # la tabla de estilos pedida (None: sin CTB)
    imprimir_transparencia: bool = True
    # Zona del Model Space (exportar_zona.py): la ventana y el filtro de capas pedidos. Con
    # zona no se mira el handle sino source.block_name, selection.kind/window/layers.
    zona: tuple[float, float, float, float] | None = None
    capas: tuple[str, ...] = ()
    excluir: tuple[str, ...] = ()


class PaqueteNoValido(ValueError):
    """El paquete exportado (o el de la caché) no es el pedido o no se puede usar."""

    def __init__(self, motivos: list[str]):
        super().__init__("; ".join(motivos))
        self.motivos = motivos


def carpeta_del_dxf(paquetes: Path, nombre_dxf: str) -> Path:
    """`<paquetes>/<nombre del DXF sin extensión, limpio>`."""
    return Path(paquetes) / limpiar(Path(nombre_dxf).stem)


def nombre_del_paquete(file_stem: str, denominador: float, marca: str = "") -> str:
    n = int(denominador) if float(denominador).is_integer() else denominador
    return nombre_paquete(file_stem, n, marca)


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
    if pedido.zona is None:
        handle = _get(datos, "source.reference.handle")
        if handle != pedido.handle:
            motivos.append(f"es de otra referencia (handle {handle}, se esperaba "
                           f"{pedido.handle})")
    else:
        motivos += motivos_de_otra_zona(datos, pedido)
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
    estilo = estilo_del_manifiesto(datos)
    if estilo["sha256"] != pedido.ctb_sha256:
        motivos.append(f"tiene otro estilo de impresión ({texto_estilo(estilo)}; se pidió "
                       + (f"la CTB {pedido.ctb_sha256[:6]}…)" if pedido.ctb_sha256 else "sin CTB)"))
    if estilo["transparencia"] != pedido.imprimir_transparencia:
        motivos.append("imprime la transparencia de los rellenos y se pidió que no"
                       if estilo["transparencia"] else
                       "no imprime la transparencia de los rellenos y se pidió que sí")
    return motivos


def motivos_de_otra_zona(datos: dict, pedido: Pedido) -> list[str]:
    """Por qué el manifiesto no es el de la zona pedida: Model Space, misma ventana (la zona en
    unidades del dibujo) y el mismo filtro de capas (si no, la caché daría otra zona)."""
    if (_get(datos, "source.block_name") != "Model_Space"
            or _get(datos, "selection.kind") != "modelspace"):
        return ["no es una zona del Model Space"]
    motivos = []
    ventana = _get(datos, "selection.window")
    if not (isinstance(ventana, list) and len(ventana) == 4 and all(_numero(v) for v in ventana)
            and all(abs(a - b) <= TOL_ZONA * max(1.0, abs(b))
                    for a, b in zip(ventana, pedido.zona))):
        motivos.append(f"es de otra zona ({ventana}, se esperaba {list(pedido.zona)})")
    for clave, nombre, esperadas in (("layers", "capas", pedido.capas),
                                     ("exclude_layers", "capas excluidas", pedido.excluir)):
        tiene = _get(datos, f"selection.{clave}") or []
        if [str(c).lower() for c in tiene] != [c.lower() for c in esperadas]:
            motivos.append(f"tiene otras {nombre} ({tiene}, se esperaba {list(esperadas)})")
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


# --- preparación: el paquete viejo no se toca hasta que el nuevo esté publicado y verificado --

PREFIJO_PREPARACION = ".componedor-nuevo-"  # la ignora localizar_paquetes (paquete.es_temporal)


def carpeta_de_preparacion(carpeta: Path, id_tarea: str) -> Path:
    """Donde el trabajador publica el paquete nuevo (dentro de la carpeta del DXF: mismo disco,
    así mover a su lugar es atómico)."""
    preparacion = Path(carpeta) / f"{PREFIJO_PREPARACION}{id_tarea}"
    preparacion.mkdir(parents=True, exist_ok=True)
    return preparacion


def instalar(preparacion: Path, carpeta: Path, paquete: str, raiz: Path,
             para_borrar: Path) -> tuple[Path, list[Path]]:
    """El paquete nuevo (ya verificado en `preparacion`) a su lugar: primero el viejo a
    `_para_borrar`, luego los archivos nuevos (el manifiesto el último). (manifiesto, movidos)."""
    movidos = mover_a_para_borrar(archivos_del_paquete(carpeta, paquete), raiz, para_borrar)
    for ext in (".pdf", ".txt", ".manifest.json"):
        origen = Path(preparacion) / f"{paquete}{ext}"
        if origen.exists():
            origen.replace(Path(carpeta) / f"{paquete}{ext}")
    limpiar_preparacion(preparacion, raiz, para_borrar)
    return Path(carpeta) / f"{paquete}.manifest.json", movidos


def limpiar_preparacion(preparacion: Path, raiz: Path, para_borrar: Path) -> list[Path]:
    """Deja la carpeta de preparación como si no hubiera existido: lo publicado que no se usó
    (p. ej. un paquete que no pasó la verificación) se MUEVE a `_para_borrar`; las carpetas
    vacías se quitan. Las `.cde-tmp-*` del trabajador se respetan (puede estar usándolas)."""
    preparacion = Path(preparacion)
    if not preparacion.is_dir():
        return []
    sueltos = [f for f in preparacion.iterdir() if f.is_file()]
    movidos = mover_a_para_borrar(sueltos, raiz, para_borrar) if sueltos else []
    for sub in sorted(preparacion.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if sub.is_dir() and not any(sub.iterdir()):
            sub.rmdir()
    if not any(preparacion.iterdir()):
        preparacion.rmdir()
    return movidos
