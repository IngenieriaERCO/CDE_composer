"""La respuesta de `load` del trabajador → la carpeta del DXF que muestra el editor.

Para cada referencia de bloque: nombre y ocurrencia, tamaño real en m, unidades (y si están
verificadas), la ESCALA SUGERIDA y notas en español. Lo que no se pueda usar de la respuesta
se descarta con un problema (un bloque mal descrito no tumba la carpeta entera); si falta lo
esencial, `RespuestaInvalida`.

Escala sugerida: la primera de `inventario.ESCALAS_ESTANDAR` (de mayor a menor detalle) con la
que la PÁGINA del bloque cabe en el área de dibujo, con la misma regla que `colocar` y el
inventario (`colocar.exceso_de_tamano`). La página es la del contrato del trabajador:

    página_mm = tamaño_m × 1000 ÷ N + 2 × margen_mm   (por eje, a 1:N)

Si la caja del bloque no es exacta (`bounds.exact = false`: bloques anidados girados), la
página real puede salir algo menor: la sugerida es prudente y se dice en una nota.
"""

import math

from componedor.colocar import exceso_de_tamano
from componedor.formato import RectMM
from componedor.inventario import ESCALAS_ESTANDAR


class RespuestaInvalida(ValueError):
    """La respuesta de `load` no trae lo esencial (mensaje en español)."""


def pagina_mm(tamano_m: tuple[float, float], n: float, margen_mm: float) -> tuple[float, float]:
    """Tamaño de la página del paquete a 1:N (fórmula del contrato del trabajador)."""
    return tuple(t * 1000.0 / n + 2.0 * margen_mm for t in tamano_m)


def escala_sugerida(tamano_m: tuple[float, float], margen_mm: float,
                    zona: RectMM) -> int | None:
    """La primera escala estándar con la que la página cabe en la zona, o None."""
    for n in ESCALAS_ESTANDAR:
        if exceso_de_tamano(pagina_mm(tamano_m, n, margen_mm), zona) == (0.0, 0.0):
            return n
    return None


def _numero(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _par(v) -> tuple[float, float] | None:
    if isinstance(v, list) and len(v) == 2 and all(_numero(x) and x >= 0 for x in v):
        return float(v[0]), float(v[1])
    return None


def _texto(v) -> str | None:
    return v if isinstance(v, str) and v else None


def _unidades(u) -> dict:
    u = u if isinstance(u, dict) else {}
    return {"nombre": _texto(u.get("name")),
            "mm_por_unidad": u.get("millimeters_per_unit") if _numero(
                u.get("millimeters_per_unit")) else None,
            "verificadas": u.get("verified") is True,
            "estado": _texto(u.get("status")),
            "avisos": [str(a) for a in u.get("warnings") or [] if a]}


def _cuenta(contiene: dict, clave: str) -> int:
    v = contiene.get(clave)
    return int(v) if _numero(v) and v > 0 else 0


def _notas(b: dict, unidades: dict, tamano_m, exacta: bool, sugerida: int | None,
           zona_nombre: str) -> list[str]:
    notas = []
    if tamano_m is None:
        notas.append("Unidades sin verificar: no se puede calcular el tamaño en papel. "
                     "Indique las unidades del dibujo al cargar el DXF.")
    elif sugerida is None:
        notas.append(f"No cabe en {zona_nombre} ni a 1:{ESCALAS_ESTANDAR[-1]} "
                     f"(la mayor de la lista estándar).")
    if not exacta:
        notas.append("Caja aproximada (hay bloques anidados girados): la página real puede "
                     "salir algo menor.")
    for aviso in unidades["avisos"]:
        notas.append(f"Unidades: {aviso}")
    contiene = b.get("contains") if isinstance(b.get("contains"), dict) else {}
    solidos = _cuenta(contiene, "solids_3d")
    if solidos:
        notas.append(f"Tiene {solidos} sólido(s) 3D: la vista previa no los muestra; la "
                     f"exportación los dibuja como huella en planta.")
    for clave, que in (("proxies", "objeto(s) proxy (pueden no dibujarse)"),
                       ("regions", "región(es)"),
                       ("images", "imagen(es) raster insertada(s)")):
        if _cuenta(contiene, clave):
            notas.append(f"Tiene {_cuenta(contiene, clave)} {que}.")
    ocultas = b.get("hidden_layer_entities")
    if _numero(ocultas) and ocultas > 0:
        notas.append(f"{int(ocultas)} objeto(s) en capas apagadas o congeladas: no se dibujan.")
    return notas


def _bloque(b, margen_mm: float, zona: RectMM, zona_nombre: str) -> dict:
    """Una entrada de la carpeta; ValueError con el motivo si no se puede usar."""
    if not isinstance(b, dict):
        raise ValueError("no es un objeto")  # noqa: TRY004 - dato del trabajador, no del programa
    for clave in ("ref", "name", "handle"):
        if _texto(b.get(clave)) is None:
            raise ValueError(f"falta «{clave}» (texto no vacío)")
    for clave in ("occurrence", "total_occurrences"):
        if not (isinstance(b.get(clave), int) and not isinstance(b.get(clave), bool)
                and b[clave] >= 1):
            raise ValueError(f"«{clave}» debe ser un entero ≥ 1")
    caja = b.get("bounds")
    if not isinstance(caja, dict) or not isinstance(caja.get("exact"), bool):
        raise ValueError("falta «bounds» con «exact»")  # noqa: TRY004
    tamano_m = None if b.get("size_m") is None else _par(b.get("size_m"))
    if b.get("size_m") is not None and tamano_m is None:
        raise ValueError("«size_m» debe ser [ancho, alto] en m, o null")
    unidades = _unidades(b.get("units"))
    sugerida = (escala_sugerida(tamano_m, margen_mm, zona) if tamano_m is not None else None)
    return {
        "ref": b["ref"], "nombre": b["name"], "handle": b["handle"],
        "ocurrencia": b["occurrence"], "total_ocurrencias": b["total_occurrences"],
        "capa": _texto(b.get("layer")),
        "tamano_m": list(tamano_m) if tamano_m else None,
        "unidades": unidades,
        "caja_exacta": caja["exact"],
        "escala_sugerida": sugerida,
        "pagina_sugerida_mm": (list(pagina_mm(tamano_m, sugerida, margen_mm))
                               if sugerida is not None else None),
        "entidades": b.get("entities") if _numero(b.get("entities")) else None,
        "archivo": _texto(b.get("file_stem")),
        "notas": _notas(b, unidades, tamano_m, caja["exact"], sugerida, zona_nombre),
    }


def catalogo_dxf(datos: dict, zona: RectMM, zona_nombre: str = "el área de dibujo") -> dict:
    """La carpeta del DXF para el editor, a partir del `data` de `load`."""
    if not isinstance(datos, dict):
        raise RespuestaInvalida("la respuesta de «load» no es un objeto")
    dxf = datos.get("dxf")
    if not isinstance(dxf, dict) or _texto(dxf.get("name")) is None:
        raise RespuestaInvalida("la respuesta de «load» no trae «dxf.name»")
    if _texto(datos.get("session")) is None:
        raise RespuestaInvalida("la respuesta de «load» no trae «session»")
    if not isinstance(datos.get("blocks"), list):
        raise RespuestaInvalida("la respuesta de «load» no trae la lista «blocks»")
    margen = datos.get("margin_mm")
    if not (_numero(margen) and margen >= 0):
        raise RespuestaInvalida("la respuesta de «load» no trae «margin_mm» (número ≥ 0)")
    bloques, problemas = [], []
    for i, b in enumerate(datos["blocks"], start=1):
        try:
            bloques.append(_bloque(b, float(margen), zona, zona_nombre))
        except ValueError as e:
            nombre = b.get("name") if isinstance(b, dict) else None
            problemas.append(f"bloque {i}" + (f" («{nombre}»)" if nombre else "")
                             + f": {e}; se omite.")
    omitidos = [{"nombre": str(o.get("name", "?")), "ocurrencia": o.get("occurrence"),
                 "total_ocurrencias": o.get("total_occurrences"),
                 "motivo": str(o.get("reason", ""))}
                for o in datos.get("omitted") or [] if isinstance(o, dict)]
    avisos = [str(n.get("message")) for n in datos.get("notices") or []
              if isinstance(n, dict) and n.get("message")]
    return {
        "sesion": datos["session"],
        "dxf": {"nombre": dxf["name"], "ruta": _texto(dxf.get("path")),
                "bytes": dxf.get("bytes") if _numero(dxf.get("bytes")) else None,
                "sha256": _texto(dxf.get("sha256")), "huella": _texto(dxf.get("fingerprint")),
                "modificado": _texto(dxf.get("modified")),
                "version_dxf": _texto(dxf.get("dxf_version")),
                "segundos_lectura": dxf.get("read_seconds") if _numero(
                    dxf.get("read_seconds")) else None,
                "copia_reducida": isinstance(dxf.get("source_copy"), dict)},
        "unidades": _unidades(datos.get("units")),
        "margen_mm": float(margen),
        "escalas": list(ESCALAS_ESTANDAR),
        "bloques": bloques,
        "omitidos": omitidos,
        "avisos": avisos,
        "problemas": problemas,
    }
