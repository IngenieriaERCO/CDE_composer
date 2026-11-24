"""Exportar una ZONA del Model Space a un paquete (Fase 10c, protocolo 1.1 §5.4).

Lo propio de una zona; lo común con un bloque (caché, carpeta de preparación, verificación,
paquete viejo a `_para_borrar`) está en `exportar_dxf.py`.

- **Nombre**: el que escribió el usuario, limpio como pide el contrato (§5.1); si viene vacío,
  el primer `Zona_01`, `Zona_02`… que no tenga ningún paquete en la carpeta del DXF ni se esté
  exportando ahora. Lo elige el Componedor y no el trabajador: el trabajador publica en una
  carpeta de preparación vacía y no vería los paquetes ya publicados. La zona se queda con
  ese nombre (decisión B de la Fase 10), así que volver a exportarla la reemplaza.
- **Paquete**: `<nombre>_1-N<marca del estilo>`, como un bloque (`nombres_paquete`).
- **Página**: la zona a 1:N más los márgenes de `load` (es la que publica el trabajador).
"""

from pathlib import Path

from componedor.nombres_paquete import limpiar
from componedor.previa_zona import PedidoZonaInvalido, caja, capas, escala

PREFIJO_GENERADO = "Zona_"
MAX_GENERADOS = 999
MAX_NOMBRE = 40  # deja sitio a la escala y la marca del estilo dentro de los 60 del contrato


def nombre_de_zona(nombre) -> str | None:
    """El nombre limpio que escribió el usuario, o None si viene vacío (se genera)."""
    if nombre is None:
        return None
    if not isinstance(nombre, str):
        raise PedidoZonaInvalido("«nombre» debe ser un texto (o vacío para generarlo).")
    if not nombre.strip():
        return None
    limpio = limpiar(nombre.strip())
    if not limpio.strip("_"):
        raise PedidoZonaInvalido(f"El nombre «{nombre}» no tiene ninguna letra ni número que se "
                                 f"pueda usar en un nombre de archivo.")
    if len(limpio) > MAX_NOMBRE:
        raise PedidoZonaInvalido(f"El nombre «{nombre}» es muy largo ({len(limpio)} caracteres; "
                                 f"como mucho {MAX_NOMBRE}).")
    return limpio


def usado(carpeta: Path, nombre: str) -> bool:
    """True si en la carpeta del DXF hay algún paquete de ese nombre, a cualquier escala."""
    carpeta = Path(carpeta)
    if not carpeta.is_dir():
        return False
    prefijo = f"{nombre}_1-".lower()
    return any(f.name.lower().startswith(prefijo) for f in carpeta.iterdir() if f.is_file())


def nombre_libre(carpeta: Path, reservados=()) -> str:
    """El primer `Zona_NN` sin paquetes en `carpeta` ni en `reservados` (exportándose ahora)."""
    ocupados = {r.lower() for r in reservados}
    for i in range(1, MAX_GENERADOS + 1):
        nombre = f"{PREFIJO_GENERADO}{i:02d}"
        if nombre.lower() not in ocupados and not usado(carpeta, nombre):
            return nombre
    raise PedidoZonaInvalido(f"Ya hay {MAX_GENERADOS} zonas con nombre generado en esta carpeta: "
                             f"escriba un nombre.")


def pagina_de_zona(zona, mm_por_unidad: float, n: float,
                   margen_mm: float) -> tuple[float, float]:
    """Tamaño (mm) de la página del paquete: la zona a 1:N más los márgenes."""
    x0, y0, x1, y1 = zona
    k = mm_por_unidad / n
    return ((x1 - x0) * k + 2 * margen_mm, (y1 - y0) * k + 2 * margen_mm)


def leer_zona(zona, solo, excluir, n) -> dict:
    """Valida lo que manda el editor: {zona, capas, excluir, n}. PedidoZonaInvalido si no vale.

    Como en la vista previa: `capas` (solo estas) o `excluir` (todas menos estas), nunca las
    dos; la zona y la escala son obligatorias."""
    zona = caja(zona, "zona")
    if zona is None:
        raise PedidoZonaInvalido("Falta «zona» ([xmin, ymin, xmax, ymax], el rectángulo).")
    solo, excluir = capas(solo, "capas") or [], capas(excluir, "excluir") or []
    if solo and excluir:
        raise PedidoZonaInvalido("Use «capas» (solo estas) o «excluir» (todas menos estas), "
                                 "no las dos.")
    n = escala(n)
    if n is None:
        raise PedidoZonaInvalido("Falta «escala» (el N de 1:N).")
    return {"zona": zona, "capas": solo, "excluir": excluir, "n": n}


def trabajo_de_zona(z: dict, paquete: str) -> dict:
    """El trabajo de `export` para el trabajador (§5.4): sin ref ni handle."""
    return {"job": "z1", "zone": z["zona"], "layers": z["capas"] or None,
            "exclude_layers": z["excluir"] or None, "scale": f"1:{z['n']}", "package": paquete}
