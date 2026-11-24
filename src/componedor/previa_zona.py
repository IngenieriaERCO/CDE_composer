"""Vista previa de una ZONA del Model Space (protocolo 1.1 del trabajador, §4.1).

Es el mismo `preview` de un bloque, pero con `zone` (o `view`) en lugar del handle:

- `zona` null y sin `vista`: todo el Model Space; la respuesta trae los `groups` (grupos de
  dibujo separados por huecos), que el editor ofrece como `vista` para acercarse.
- `vista`: el trozo que se dibuja (un grupo, o la vista actual del editor).
- `zona`: el rectángulo que dibujó el usuario; con `escala`, el trabajador devuelve el tamaño
  que tendría en la hoja (`paper`).

Capas: `capas` (lista blanca: «solo estas») o `excluir` (exclusión: «todas menos estas»,
el modo con el que empieza el editor). Las dos admiten `*` y `?`; una capa no lleva comas.

Aquí se valida lo que manda el editor (cajas, capas, escala) y se lee la respuesta. La parte
común con la vista previa de un bloque (PNG dentro de la carpeta de vistas previas, `cad_to_px`
sin giro y a = −d) la comprueba `previa_dxf.leer_previa`.
"""

import math

from componedor.previa_dxf import LADO_PX, PreviaInvalida, leer_previa

ESCALA_MIN, ESCALA_MAX = 1, 100000  # las mismas de la escala escrita a mano del editor
MAX_CAPAS = 2000


class PedidoZonaInvalido(ValueError):
    """Lo que mandó el editor para la vista previa de una zona no vale (mensaje en español)."""


def _numero(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def caja(valor, nombre: str) -> list[float] | None:
    """[xmin, ymin, xmax, ymax] en unidades del dibujo, o None. PedidoZonaInvalido si no vale."""
    if valor is None:
        return None
    if not (isinstance(valor, list) and len(valor) == 4 and all(_numero(v) for v in valor)):
        raise PedidoZonaInvalido(f"«{nombre}» debe ser [xmin, ymin, xmax, ymax] (4 números) "
                                 f"o null.")
    x0, y0, x1, y1 = (float(v) for v in valor)
    if not (x1 > x0 and y1 > y0):
        raise PedidoZonaInvalido(f"«{nombre}» debe cumplir xmax > xmin e ymax > ymin.")
    return [x0, y0, x1, y1]


def capas(valor, nombre: str) -> list[str] | None:
    """Lista de nombres de capa (sin comas), o None. PedidoZonaInvalido si no vale."""
    if valor is None:
        return None
    if not (isinstance(valor, list) and len(valor) <= MAX_CAPAS
            and all(isinstance(c, str) and c.strip() for c in valor)):
        raise PedidoZonaInvalido(f"«{nombre}» debe ser una lista de nombres de capa o null.")
    con_coma = [c for c in valor if "," in c]
    if con_coma:
        raise PedidoZonaInvalido(f"La capa «{con_coma[0]}» lleva una coma: el exportador no "
                                 f"admite comas en los nombres de capa.")
    return list(valor)


def escala(valor) -> int | None:
    """El N de 1:N (entero de 1 a 100000), o None."""
    if valor is None:
        return None
    if not (_numero(valor) and float(valor).is_integer()
            and ESCALA_MIN <= valor <= ESCALA_MAX):
        raise PedidoZonaInvalido(f"«escala» debe ser el N de 1:N, un entero de {ESCALA_MIN} a "
                                 f"{ESCALA_MAX}, o null.")
    return int(valor)


def pedido_previa_zona(sesion: str, zona=None, vista=None, solo=None, excluir=None,
                       denominador=None) -> dict:
    """`data` del pedido `preview` de una zona (§4.1), ya validado. Solo capas visibles
    del CAD, como la vista previa de un bloque. PedidoZonaInvalido si algo no vale."""
    zona, vista = caja(zona, "zona"), caja(vista, "vista")
    solo, excluir = capas(solo, "capas"), capas(excluir, "excluir")
    if solo and excluir:
        raise PedidoZonaInvalido("Use «capas» (solo estas) o «excluir» (todas menos estas), "
                                 "no las dos.")
    datos = {"session": sesion, "zone": zona, "layers": solo, "exclude_layers": excluir,
             "scale": escala(denominador), "long_side_px": LADO_PX,
             "include_hidden_layers": None}
    if vista is not None:
        datos["view"] = vista
    return datos


def _caja_respuesta(valor, nombre: str) -> list[float] | None:
    if valor is None:
        return None
    if not (isinstance(valor, list) and len(valor) == 4 and all(_numero(v) for v in valor)):
        raise PreviaInvalida(f"«{nombre}» debe ser [xmin, ymin, xmax, ymax] o null")
    return [float(v) for v in valor]


def _filas_capas(filas) -> list[dict]:
    if not isinstance(filas, list):
        raise PreviaInvalida("«layer_rows» debe ser una lista")
    salida = []
    for f in filas:
        if not (isinstance(f, dict) and isinstance(f.get("name"), str)
                and isinstance(f.get("entities_in_view"), int)
                and isinstance(f.get("shown"), bool)):
            raise PreviaInvalida("cada fila de «layer_rows» debe traer name, entities_in_view "
                                 "y shown")
        estado = f.get("cad_state")
        salida.append({"nombre": f["name"], "entidades": f["entities_in_view"],
                       "estado_cad": estado if isinstance(estado, str) else None,
                       "se_ve": f["shown"]})
    return salida


def _grupos(grupos) -> list[dict]:
    if not isinstance(grupos, list):
        raise PreviaInvalida("«groups» debe ser una lista")
    salida = []
    for g in grupos:
        if not (isinstance(g, dict) and isinstance(g.get("number"), int)
                and isinstance(g.get("entities"), int)):
            raise PreviaInvalida("cada grupo de «groups» debe traer number, box y entities")
        salida.append({"numero": g["number"], "caja": _caja_respuesta(g.get("box"), "box"),
                       "entidades": g["entities"]})
    if any(g["caja"] is None for g in salida):
        raise PreviaInvalida("un grupo de «groups» no trae «box»")
    return salida


def _papel(papel) -> dict | None:
    if papel is None:
        return None
    pares = [papel.get(k) if isinstance(papel, dict) else None
             for k in ("content_mm", "page_mm")]
    if not (all(isinstance(p, list) and len(p) == 2 and all(_numero(v) for v in p)
                for p in pares) and isinstance(papel.get("fits_a1"), bool)):
        raise PreviaInvalida("«paper» debe traer content_mm, page_mm y fits_a1")
    margen = papel.get("margin_mm")
    return {"contenido_mm": [float(v) for v in pares[0]],
            "pagina_mm": [float(v) for v in pares[1]],
            "margen_mm": float(margen) if _numero(margen) else None,
            "cabe_a1": papel["fits_a1"]}


def leer_previa_zona(datos: dict, carpeta_previas) -> dict:
    """Lo de `leer_previa` (png, px, caja_cad, cad_a_px, omitidos, en_cache, segundos) y
    además {zona, vista, capas, excluir, filas_capas, grupos, entidades, escala, papel}.
    PreviaInvalida si algo no cumple el contrato."""
    if not isinstance(datos, dict):
        raise PreviaInvalida("la respuesta de «preview» no es un objeto")
    if datos.get("kind") != "zone":
        raise PreviaInvalida("la respuesta no es de una zona (¿el exportador habla el "
                             "protocolo 1.1?)")
    if datos.get("bounds") is None:
        raise PreviaInvalida("no hay nada que dibujar ahí (sin entidades con caja en esa "
                             "vista)")
    base = leer_previa(datos, carpeta_previas)
    entidades = datos.get("entities")
    if not (isinstance(entidades, dict)
            and all(isinstance(entidades.get(k), int) for k in ("in_view", "drawn",
                                                                 "without_bounds"))):
        raise PreviaInvalida("«entities» debe traer in_view, drawn y without_bounds")
    escala_txt = datos.get("scale")
    return {
        **base,
        "zona": _caja_respuesta(datos.get("zone"), "zone"),
        "vista": _caja_respuesta(datos.get("view"), "view"),
        "capas": [c for c in datos.get("layers") or [] if isinstance(c, str)],
        "excluir": [c for c in datos.get("exclude_layers") or [] if isinstance(c, str)],
        "filas_capas": _filas_capas(datos.get("layer_rows")),
        "grupos": _grupos(datos.get("groups")),
        "entidades": {"en_vista": entidades["in_view"], "dibujadas": entidades["drawn"],
                      "sin_caja": entidades["without_bounds"]},
        "escala": escala_txt if isinstance(escala_txt, str) else None,
        "papel": _papel(datos.get("paper")),
    }
