"""La escala a la que está DIBUJADA una zona: los textos «ESC 1:N» que trae (orden `texts`
del trabajador, protocolo 1.3, §4.3 de su contrato).

Si el dibujo está a 1:20 y se exporta a 1:10, los textos salen al doble de su tamaño. Por eso,
al dibujar la zona, el editor pide sus textos con el MISMO filtro de capas que se va a
exportar y el trabajador busca en ellos la escala escrita («ESC 1:25», «ESCALA: 1:25»,
«ESC-1:10», «ESC. H 1:1000 V 1:100»…):

- una sola escala y sin eje → `proposed_scale`: el editor la pone sola y dice de dónde salió;
- varias, o con ejes H/V (perfiles) → `scale_candidates`: el editor las muestra para elegir;
- ninguna → aviso suave.

Aquí se valida el pedido (lo mismo que la vista previa de una zona) y se lee la respuesta.
"""

import math

from componedor.previa_zona import PedidoZonaInvalido, caja, capas

MAX_TEXTOS = 200  # los textos en sí no se muestran: la escala se busca siempre en todos
MAX_FUENTES = 3  # textos de origen por escala que se dan al editor


class RespuestaTextosInvalida(ValueError):  # ValueError: el canal la da como respuesta inválida
    """La respuesta de `texts` no cumple el contrato (mensaje en español)."""


def pedido_textos(sesion: str, zona, solo=None, excluir=None) -> dict:
    """`data` del pedido `texts` (§4.3), ya validado. PedidoZonaInvalido si algo no vale."""
    zona = caja(zona, "zona")
    if zona is None:
        raise PedidoZonaInvalido("Falta «zona» ([xmin, ymin, xmax, ymax], el rectángulo).")
    solo, excluir = capas(solo, "capas"), capas(excluir, "excluir")
    if solo and excluir:
        raise PedidoZonaInvalido("Use «capas» (solo estas) o «excluir» (todas menos estas), "
                                 "no las dos.")
    return {"session": sesion, "zone": zona, "layers": solo, "exclude_layers": excluir,
            "include_hidden_layers": None, "max_texts": MAX_TEXTOS}


def _numero(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _fuente(f) -> dict | None:
    if not (isinstance(f, dict) and isinstance(f.get("text"), str)
            and _numero(f.get("x")) and _numero(f.get("y"))):
        return None
    return {"texto": f["text"], "x": float(f["x"]), "y": float(f["y"]),
            "capa": f.get("layer") if isinstance(f.get("layer"), str) else None}


def leer_textos(datos: dict) -> dict:
    """{propuesta, candidatos: [{escala, n, eje, veces, fuentes: [{texto, x, y, capa}]}], total,
    segundos}. propuesta: el N de la única escala sin eje (o None). RespuestaTextosInvalida."""
    if not isinstance(datos, dict):
        raise RespuestaTextosInvalida("la respuesta de «texts» no es un objeto")
    lista = datos.get("scale_candidates")
    if not isinstance(lista, list):
        raise RespuestaTextosInvalida("«scale_candidates» debe ser una lista")
    candidatos = []
    for c in lista:
        if not (isinstance(c, dict) and isinstance(c.get("scale"), str) and _numero(c.get("denominator"))
                and c["denominator"] > 0 and isinstance(c.get("count"), int)):
            raise RespuestaTextosInvalida("cada escala de «scale_candidates» debe traer scale, "
                                          "denominator y count")
        eje = c.get("axis") if c.get("axis") in ("H", "V") else None
        fuentes = [f for f in (_fuente(x) for x in c.get("sources") or []) if f][:MAX_FUENTES]
        candidatos.append({"escala": c["scale"], "n": float(c["denominator"]), "eje": eje,
                           "veces": c["count"], "fuentes": fuentes})
    propuesta = None
    texto = datos.get("proposed_scale")
    if isinstance(texto, str):
        unica = [c for c in candidatos if c["escala"] == texto and c["eje"] is None]
        if len(candidatos) == 1 and unica:
            propuesta = unica[0]["n"]
    total = datos.get("total")
    return {"propuesta": propuesta, "candidatos": candidatos,
            "total": total if isinstance(total, int) else None,
            "segundos": datos.get("seconds") if _numero(datos.get("seconds")) else None}
