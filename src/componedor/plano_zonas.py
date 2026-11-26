"""plano.json versión 6: zonas del Model Space de un DXF (Fase 10e3).

La versión 6 es la versión 5 más, en cada entrada de "dxf", la lista "zonas" (solo cuando el
plano tiene zonas):

  "dxf": [{"id": "d1", "archivo": "...", "sha256": "…", "margen_mm": 5, "unidades": "m",
           "zonas": [{"nombre": "Zona_01", "zona": [x0, y0, x1, y1],
                      "capas": null, "excluir": ["COTAS"], "escala": "1:20",
                      "centro_mm": [342.55, 297.0], "tamano_m": [0.67, 0.65]}]}]

- `zona`: el rectángulo en el Model Space, en unidades del dibujo (el marco del exportador).
- `capas` (solo estas) o `excluir` (todas menos estas): el filtro de capas; nunca las dos.
- `escala` («1:N») y `centro_mm` (centro de la PÁGINA en la hoja, mm de papel, Y hacia arriba):
  dónde y a qué escala va. `tamano_m`: el tamaño real de la zona (para la caja en la hoja).
- `nombre`: el del paquete (`<nombre>_1-N…`); único en el plano.

Una zona exportada es un detalle normal ("manifiesto", "posicion_mm") que además lleva
`"origen": {"zona": "<nombre>"}`. Una zona sin ningún detalle que la nombre es un BORRADOR
(todavía sin exportar): el editor la muestra en la hoja y `componer` no compone el plano hasta
exportarla (dice cuáles faltan). Las dos sirven para «Volver a exportar zonas» cuando cambie el
DXF: cada una se exporta otra vez con su nombre, capas, escala y centro.
"""

import math
from dataclasses import dataclass

from componedor.plano_dxf import leer_escala

CLAVES_ZONA = {"nombre", "zona", "capas", "excluir", "escala", "centro_mm", "tamano_m"}
CLAVES_ORIGEN_ZONA = {"zona"}


@dataclass(frozen=True)
class ZonaPlano:
    dxf: str  # id en la lista "dxf"
    nombre: str
    zona: tuple[float, float, float, float]
    escala: float  # N de 1:N
    centro_mm: tuple[float, float]
    tamano_m: tuple[float, float]
    capas: tuple[str, ...] | None = None
    excluir: tuple[str, ...] | None = None


def _numero(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _lista_capas(valor, donde: str, errores: list[str]) -> tuple[str, ...] | None:
    if valor is None:
        return None
    if not (isinstance(valor, list) and all(isinstance(c, str) and c.strip() for c in valor)):
        errores.append(f"{donde}: se esperaba una lista de nombres de capa o null")
        return None
    return tuple(valor)


def leer_zonas(valor, dxf: str, donde: str, errores: list[str]) -> list[ZonaPlano]:
    """"zonas": [...] de una entrada "dxf" → [ZonaPlano]. Los problemas van a `errores`."""
    if not isinstance(valor, list):
        errores.append(f"{donde}: se esperaba una lista de zonas [{{\"nombre\", \"zona\", ...}}]")
        return []
    zonas = []
    for i, z in enumerate(valor):
        aqui = f"{donde}[{i}]"
        if not isinstance(z, dict):
            errores.append(f"{aqui}: se esperaba un objeto {{...}}")
            continue
        n = len(errores)
        for clave in sorted(set(z) - CLAVES_ZONA):
            errores.append(f"{aqui}.{clave}: campo no reconocido (campos válidos: "
                           f"{', '.join(sorted(CLAVES_ZONA))})")
        nombre = z.get("nombre")
        if not (isinstance(nombre, str) and nombre.strip()):
            errores.append(f"{aqui}.nombre: se esperaba un texto no vacío")
        rect = z.get("zona")
        if not (isinstance(rect, list) and len(rect) == 4 and all(_numero(v) for v in rect)
                and rect[2] > rect[0] and rect[3] > rect[1]):
            errores.append(f"{aqui}.zona: se esperaba [xmin, ymin, xmax, ymax] con xmax > xmin "
                           f"e ymax > ymin")
        capas = _lista_capas(z.get("capas"), f"{aqui}.capas", errores)
        excluir = _lista_capas(z.get("excluir"), f"{aqui}.excluir", errores)
        if capas and excluir:
            errores.append(f"{aqui}: lleva «capas» y «excluir» a la vez; use solo una")
        escala = leer_escala(z.get("escala"))
        if escala is None:
            errores.append(f"{aqui}.escala: se esperaba «1:N» con N entero de 1 a 100000")
        centro = z.get("centro_mm")
        if not (isinstance(centro, list) and len(centro) == 2 and all(_numero(v) for v in centro)):
            errores.append(f"{aqui}.centro_mm: se esperaba [x, y] en mm de la hoja")
        tamano = z.get("tamano_m")
        if not (isinstance(tamano, list) and len(tamano) == 2
                and all(_numero(v) and v > 0 for v in tamano)):
            errores.append(f"{aqui}.tamano_m: se esperaba [ancho, alto] en m (> 0)")
        if len(errores) == n:
            zonas.append(ZonaPlano(dxf, nombre, tuple(float(v) for v in rect), escala,
                                   (float(centro[0]), float(centro[1])),
                                   (float(tamano[0]), float(tamano[1])), capas, excluir))
    return zonas


def leer_origen_zona(origen, donde: str, nombres: set[str], errores: list[str]) -> str | None:
    """El "origen" de un detalle exportado desde una zona: {"zona": "<nombre>"} → nombre."""
    if not isinstance(origen, dict):
        errores.append(f"{donde}: se esperaba {{\"zona\": \"<nombre de la zona>\"}}")
        return None
    for clave in sorted(set(origen) - CLAVES_ORIGEN_ZONA):
        errores.append(f"{donde}.{clave}: campo no reconocido en un detalle exportado (solo "
                       f"\"zona\")")
    nombre = origen.get("zona")
    if not (isinstance(nombre, str) and nombre.strip()):
        errores.append(f"{donde}.zona: se esperaba el nombre de una zona")
        return None
    if nombre not in nombres:
        errores.append(f"{donde}.zona: '{nombre}' no está en las «zonas» de la lista \"dxf\"")
        return None
    return nombre


def texto_zonas_sin_exportar(zonas: tuple[ZonaPlano, ...]) -> str:
    """Por qué `componer` no compone un plano con zonas borrador: cuáles faltan exportar."""
    lineas = [f"- '{z.nombre}': zona del Model Space a 1:{z.escala:g}" for z in zonas]
    return (f"No se compone el plano: tiene {len(zonas)} zona(s) del Model Space sin exportar "
            f"todavía (borradores). Componer necesita el paquete (PDF + manifiesto) de cada una:\n"
            + "\n".join(lineas)
            + "\nExpórtelas desde el editor («Exportar bloques y zonas») y vuelva a componer.")
