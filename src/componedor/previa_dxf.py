"""La respuesta de `preview` del trabajador → lo que el editor necesita para poner el PNG.

El contrato (§4) garantiza un solo marco de coordenadas para `load`, `preview` y el manifiesto,
y una matriz `cad_to_px` sin giro (b = c = 0) y con la misma escala en X e Y (a = −d). Con eso,
el editor lleva cada esquina del PNG al papel con la misma fórmula de la caja del bloque:

    X = (px − e) ÷ a,   Y = (py − f) ÷ d                      (píxel → CAD)
    papel = P + k·(X − Cx, Y − Cy),   k = mm por unidad ÷ N   (CAD → papel)

(C: centro de la caja de `load`; P: centro de la caja en la hoja.) Aquí solo se comprueba que
la respuesta cumple eso y que el PNG está dentro de la carpeta de vistas previas del
trabajador: el servidor no entrega ningún otro archivo del disco.
"""

import math
from pathlib import Path

LADO_PX = 1500  # lado mayor del PNG (el del contrato)
CARPETA_PREVIAS = "previews"  # dentro de la carpeta de trabajo del trabajador
TOL_MATRIZ = 1e-9  # relativa: a = −d «exactamente», salvo ruido de coma flotante


class PreviaInvalida(ValueError):
    """La respuesta de `preview` no se puede usar (mensaje en español)."""


def pedido_previa(sesion: str, handle: str) -> dict:
    """`data` del pedido `preview`: solo capas visibles (decisión de la etapa 2).

    El bloque va por su HANDLE (el del INSERT), solo, sin `block` ni `ref`: el `ref` de un *U
    (`*U76#1`) puede cambiar entre sesiones porque AutoCAD renumera los *U al guardar, y el
    handle no (contrato del trabajador, §3.1 y §4)."""
    return {"session": sesion, "handle": handle, "long_side_px": LADO_PX,
            "include_hidden_layers": None}


def _numero(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def png_dentro(ruta, carpeta_previas: Path) -> Path:
    """La ruta del PNG, resuelta, si es un .png que existe DENTRO de `carpeta_previas`."""
    if not isinstance(ruta, str) or not ruta:
        raise PreviaInvalida("no trae «png» (la ruta de la imagen)")
    png = Path(ruta).resolve()
    if not png.is_relative_to(Path(carpeta_previas).resolve()):
        raise PreviaInvalida(f"el PNG «{ruta}» no está en la carpeta de vistas previas del "
                             f"trabajador ({carpeta_previas})")
    if png.suffix.lower() != ".png" or not png.is_file():
        raise PreviaInvalida(f"no existe el PNG «{ruta}»")
    return png


def leer_previa(datos: dict, carpeta_previas: Path) -> dict:
    """{png (Path), px, caja_cad, cad_a_px, omitidos, en_cache, segundos}. PreviaInvalida si
    algo no cumple el contrato."""
    if not isinstance(datos, dict):
        raise PreviaInvalida("la respuesta de «preview» no es un objeto")
    png = png_dentro(datos.get("png"), carpeta_previas)
    px = datos.get("px")
    if not (isinstance(px, list) and len(px) == 2
            and all(isinstance(v, int) and not isinstance(v, bool) and v > 0 for v in px)):
        raise PreviaInvalida("«px» debe ser [ancho, alto] en píxeles (enteros > 0)")
    m = datos.get("cad_to_px")
    if not (isinstance(m, list) and len(m) == 6 and all(_numero(v) for v in m)):
        raise PreviaInvalida("«cad_to_px» debe ser [a, b, c, d, e, f] (6 números)")
    a, b, c, d = m[:4]
    if b != 0 or c != 0 or a <= 0 or abs(a + d) > TOL_MATRIZ * abs(a):
        raise PreviaInvalida(f"«cad_to_px» {m} no cumple el contrato (b = c = 0, a = −d > 0)")
    caja = datos.get("bounds")
    puntos = [caja.get(k) for k in ("min", "max")] if isinstance(caja, dict) else []
    if not (len(puntos) == 2 and all(isinstance(p, list) and len(p) >= 2
                                     and all(_numero(v) for v in p[:2]) for p in puntos)):
        raise PreviaInvalida("«bounds» debe traer «min» y «max» [x, y]")
    omitidos = datos.get("omitted") if isinstance(datos.get("omitted"), dict) else {}
    return {
        "png": png,
        "px": list(px),
        "caja_cad": {"min": [float(v) for v in puntos[0][:2]],
                     "max": [float(v) for v in puntos[1][:2]]},
        "cad_a_px": [float(v) for v in m],
        "omitidos": {str(k): int(v) for k, v in omitidos.items() if _numero(v) and v > 0},
        "en_cache": datos.get("cached") is True,
        "segundos": datos.get("seconds") if _numero(datos.get("seconds")) else None,
    }
