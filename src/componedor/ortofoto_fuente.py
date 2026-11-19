"""Qué ortofoto usa `componer`: el ORIGINAL si existe y coincide con el plano; si no, la COPIA
reducida de la carpeta del plano (`ortofoto_copia`), avisando. Si no hay ninguna que sirva, no
se compone (error claro): nunca se pone una ortofoto que no es la elegida.

- «Coincide»: mismo tamaño en bytes y misma fecha de modificación (al segundo, UTC) que guardó
  el plano al elegirla (lo que el plano no guardó no se compara).
- Sistemas: el del dibujo (`crs_dibujo`) es obligatorio; el de la ortofoto, el del archivo o,
  si el archivo no trae, el elegido en el plano (`crs`). Nunca se supone ninguno.
- La copia sirve si salió de la misma ortofoto (nombre, bytes, fecha) y está en el mismo
  sistema del dibujo.
"""

from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from rasterio.crs import CRS

from componedor.ortofoto import (
    OrtofotoInvalida,
    SistemaInvalido,
    leer_cabecera,
    leer_sistema,
)
from componedor.ortofoto_copia import archivo_de, leer_indice
from componedor.ortofoto_render import Fuente, abrir_fuente
from componedor.plano_ortofoto import OrtofotoPlano


class OrtofotoNoUsable(ValueError):
    """No hay ortofoto que se pueda poner (mensaje en español: qué falta y qué hacer)."""


@dataclass
class Eleccion:
    origen: str  # "original" o "copia"
    crs_dibujo: CRS
    original: Path
    crs_ortofoto: CRS | None = None  # el elegido a mano (si el original no trae el suyo)
    carpeta_copia: Path | None = None
    indice: dict | None = None
    avisos: list[str] = field(default_factory=list)


def fecha(ruta: Path) -> str:
    """Fecha de modificación como la guarda el plano (UTC, al segundo)."""
    return datetime.fromtimestamp(Path(ruta).stat().st_mtime, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def datos_del_plano(o: OrtofotoPlano) -> dict:
    return {"nombre": o.archivo.name, "bytes": o.bytes, "modificado": o.modificado}


def datos_del_archivo(ruta: Path) -> dict:
    return {"nombre": Path(ruta).name, "bytes": Path(ruta).stat().st_size,
            "modificado": fecha(ruta)}


def diferencias(esperado: dict, real: dict) -> list[str]:
    """Qué no coincide (solo lo que el plano guardó)."""
    textos = {"nombre": "nombre", "bytes": "tamaño", "modificado": "fecha"}
    salida = []
    for clave, texto in textos.items():
        if esperado.get(clave) is None or esperado[clave] == real.get(clave):
            continue
        if clave == "nombre" and str(esperado[clave]).lower() == str(real.get(clave)).lower():
            continue
        salida.append(f"{texto}: el plano dice {esperado[clave]} y es {real.get(clave)}")
    return salida


def elegir(o: OrtofotoPlano, carpeta_copia: Path) -> Eleccion:
    """El original o la copia (con su aviso). OrtofotoNoUsable si no sirve ninguna."""
    if o.crs_dibujo is None:
        raise OrtofotoNoUsable(
            f"el plano tiene la ortofoto «{o.archivo.name}», pero no dice el sistema de "
            f"coordenadas del dibujo. Elíjalo en el editor (panel Ortofoto) y guarde el plano.")
    try:
        crs_dibujo = leer_sistema(o.crs_dibujo)
    except SistemaInvalido as e:
        raise OrtofotoNoUsable(f"ortofoto.crs_dibujo: {e}") from None
    esperado = datos_del_plano(o)
    if not o.archivo.is_file():
        motivo = f"no se encontró «{o.archivo}»"
    else:
        dif = diferencias(esperado, datos_del_archivo(o.archivo))
        if dif:
            motivo = f"«{o.archivo}» cambió desde que se eligió ({'; '.join(dif)})"
        else:
            return _original(o, crs_dibujo)
    indice = leer_indice(carpeta_copia)
    if indice is not None:
        de_la_copia = indice.get("original") or {}
        if (not diferencias(esperado, de_la_copia)
                and indice.get("crs_dibujo") == crs_dibujo.to_string()):
            aviso = (f"La ortofoto original {motivo}: se usó la copia reducida de "
                     f"«{carpeta_copia}» (hecha a {indice.get('ppp')} ppp).")
            return Eleccion("copia", crs_dibujo, o.archivo, carpeta_copia=carpeta_copia,
                            indice=indice, avisos=[aviso])
    raise OrtofotoNoUsable(
        f"la ortofoto {motivo} y no hay una copia reducida que sirva en «{carpeta_copia}». "
        f"Vuelva a elegirla en el editor («Cargar ortofoto») y guarde el plano.")


def _original(o: OrtofotoPlano, crs_dibujo: CRS) -> Eleccion:
    try:
        ficha = leer_cabecera(o.archivo)
    except OrtofotoInvalida as e:
        raise OrtofotoNoUsable(str(e)) from None
    crs_ortofoto = None
    if ficha["sistema"] is None:
        if o.crs is None:
            raise OrtofotoNoUsable(
                f"la ortofoto «{o.archivo.name}» no dice su sistema de coordenadas y el plano "
                f"no lo eligió: elíjalo en el editor (no se supone ninguno).")
        try:
            crs_ortofoto = leer_sistema(o.crs)
        except SistemaInvalido as e:
            raise OrtofotoNoUsable(f"ortofoto.crs: {e}") from None
    return Eleccion("original", crs_dibujo, o.archivo, crs_ortofoto)


@contextmanager
def abrir_fuentes(e: Eleccion, ids: list[str]) -> Iterator[tuple[dict[str, Fuente], list[str]]]:
    """La ortofoto abierta de cada detalle ({id: Fuente}) y avisos. Con el original, la misma
    para todos; con la copia, el archivo de cada detalle (si la copia no lo tiene, sin
    ortofoto y con aviso)."""
    avisos = []
    with ExitStack() as pila:
        if e.origen == "original":
            fuente = pila.enter_context(abrir_fuente(e.original, e.crs_ortofoto))
            yield dict.fromkeys(ids, fuente), avisos
            return
        fuentes = {}
        for ident in ids:
            ruta = archivo_de(e.carpeta_copia, e.indice, ident)
            if ruta is None:
                avisos.append(f"La copia reducida no tiene el detalle '{ident}': va sin "
                              f"ortofoto (componga una vez con el original para rehacerla).")
                continue
            fuentes[ident] = pila.enter_context(abrir_fuente(ruta))
        yield fuentes, avisos
