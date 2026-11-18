"""plano.json versión 3: bloques de un DXF colocados en el editor y todavía SIN exportar.

La versión 3 es la versión 2 más (solo cuando el plano usa un DXF):

  "dxf": [{"id": "d1", "archivo": "../data/input/dxf/GUAMO_prueba.dxf",
           "sha256": "4b1d…", "bytes": 6781020, "unidades": "m", "margen_mm": 5}]

y, en "detalles", entradas PENDIENTES (sin "manifiesto"), en el mismo orden de apilado:

  {"id": "BLOQUE1",
   "origen": {"dxf": "d1", "bloque": "BLOQUE1", "handle": "50CA", "ocurrencia": 1,
              "escala": "1:2000", "tamano_m": [957.18, 1350.019], "caja_exacta": true},
   "centro_mm": [342.55, 296.99]}

- `archivo`: relativo a la carpeta del plano (o absoluto, p. ej. en otro disco).
- `centro_mm`: centro de la PÁGINA del bloque en la hoja (mm de papel, Y hacia arriba). Se
  guarda el centro y no la esquina porque la página exacta la dará el manifiesto al exportar
  (con caja aproximada puede salir algo menor); el centro no cambia.
- La página a 1:N es la del contrato: tamano_m × 1000 ÷ N + 2 × margen_mm por eje.

Este módulo solo valida esas dos piezas; `plano.py` las usa. `componer` no puede componer un
plano con pendientes: dice cuáles faltan por exportar.
"""

import math
import re
from dataclasses import dataclass
from pathlib import Path

CLAVES_DXF = {"id", "archivo", "sha256", "bytes", "unidades", "margen_mm"}
CLAVES_PENDIENTE = {"id", "origen", "centro_mm", "etiqueta_escala"}
CLAVES_ORIGEN = {"dxf", "bloque", "handle", "ocurrencia", "escala", "tamano_m", "caja_exacta"}
RE_SHA256 = re.compile(r"^[0-9a-f]{64}$")
RE_HANDLE = re.compile(r"^[0-9A-F]+$")
RE_ESCALA = re.compile(r"^1:(\d+(?:\.\d+)?)$")


@dataclass(frozen=True)
class DxfPlano:
    id: str
    archivo: Path  # resuelta respecto de la carpeta del plano
    sha256: str
    margen_mm: float
    bytes: int | None = None
    unidades: str | None = None


@dataclass(frozen=True)
class BloquePendiente:
    id: str
    dxf: str  # id en la lista "dxf"
    bloque: str
    handle: str
    ocurrencia: int
    escala: float  # N de 1:N
    tamano_m: tuple[float, float]
    centro_mm: tuple[float, float]
    caja_exacta: bool = True
    etiqueta_escala: bool = True


def _numero(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _texto(v) -> bool:
    return isinstance(v, str) and bool(v.strip())


def _desconocidas(valor: dict, validas: set[str], donde: str, errores: list[str]) -> None:
    for clave in sorted(set(valor) - validas):
        errores.append(f"{donde}.{clave}: campo no reconocido (campos válidos: "
                       f"{', '.join(sorted(validas))})")


def leer_lista_dxf(valor, carpeta: Path, errores: list[str]) -> dict[str, DxfPlano]:
    """"dxf": [...] → {id: DxfPlano}. Los problemas van a `errores`."""
    if not isinstance(valor, list):
        errores.append("dxf: se esperaba una lista [{\"id\", \"archivo\", \"sha256\", ...}]")
        return {}
    dxfs: dict[str, DxfPlano] = {}
    for i, item in enumerate(valor):
        donde = f"dxf[{i}]"
        if not isinstance(item, dict):
            errores.append(f"{donde}: se esperaba un objeto {{...}}")
            continue
        n = len(errores)
        _desconocidas(item, CLAVES_DXF, donde, errores)
        ident = item.get("id")
        if not _texto(ident):
            errores.append(f"{donde}.id: se esperaba un texto no vacío")
        elif ident in dxfs:
            errores.append(f"{donde}.id: '{ident}' está repetido")
        archivo = item.get("archivo")
        if not _texto(archivo):
            errores.append(f"{donde}.archivo: se esperaba la ruta del DXF (texto)")
        sha = item.get("sha256")
        if not (isinstance(sha, str) and RE_SHA256.match(sha)):
            errores.append(f"{donde}.sha256: se esperaba el SHA-256 del DXF (64 caracteres "
                           f"hexadecimales en minúsculas)")
        margen = item.get("margen_mm")
        if not (_numero(margen) and margen >= 0):
            errores.append(f"{donde}.margen_mm: se esperaba un número ≥ 0 (mm)")
        tamano = item.get("bytes")
        if tamano is not None and not (isinstance(tamano, int) and not isinstance(tamano, bool)
                                       and tamano >= 0):
            errores.append(f"{donde}.bytes: se esperaba un entero ≥ 0 o null")
        unidades = item.get("unidades")
        if unidades is not None and not _texto(unidades):
            errores.append(f"{donde}.unidades: se esperaba un texto (p. ej. \"m\") o null")
        if len(errores) == n:
            ruta = Path(archivo)
            dxfs[ident] = DxfPlano(ident, ruta if ruta.is_absolute() else carpeta / ruta, sha,
                                   float(margen), tamano, unidades)
    return dxfs


def leer_escala(texto) -> float | None:
    """"1:2000" → 2000.0; None si no es «1:N» con N > 0."""
    m = RE_ESCALA.match(texto) if isinstance(texto, str) else None
    n = float(m.group(1)) if m else 0.0
    return n if n > 0 else None


def leer_pendiente(item: dict, donde: str, dxfs: dict[str, DxfPlano],
                   errores: list[str]) -> BloquePendiente | None:
    """Un detalle pendiente (con "origen"). Los problemas van a `errores`."""
    n = len(errores)
    _desconocidas(item, CLAVES_PENDIENTE, donde, errores)
    ident = item.get("id")
    if not _texto(ident):
        errores.append(f"{donde}.id: se esperaba un texto no vacío")
    origen = item.get("origen")
    datos = {}
    if not isinstance(origen, dict):
        errores.append(f"{donde}.origen: se esperaba un objeto {{\"dxf\", \"bloque\", "
                       f"\"handle\", ...}}")
    else:
        datos = _origen(origen, f"{donde}.origen", dxfs, errores)
    centro = item.get("centro_mm")
    if not (isinstance(centro, list) and len(centro) == 2 and all(_numero(v) for v in centro)):
        errores.append(f"{donde}.centro_mm: se esperaba [x, y] con 2 números finitos en mm; "
                       f"tiene {centro!r}")
    etiqueta = item.get("etiqueta_escala", True)
    if not isinstance(etiqueta, bool):
        errores.append(f"{donde}.etiqueta_escala: se esperaba true o false")
    if len(errores) > n:
        return None
    return BloquePendiente(ident, centro_mm=(float(centro[0]), float(centro[1])),
                           etiqueta_escala=etiqueta, **datos)


def _origen(origen: dict, donde: str, dxfs: dict[str, DxfPlano], errores: list[str]) -> dict:
    _desconocidas(origen, CLAVES_ORIGEN, donde, errores)
    dxf = origen.get("dxf")
    if not _texto(dxf):
        errores.append(f"{donde}.dxf: se esperaba el id de un DXF de la lista \"dxf\"")
    elif dxf not in dxfs:
        errores.append(f"{donde}.dxf: '{dxf}' no está en la lista \"dxf\" del plano")
    bloque = origen.get("bloque")
    if not _texto(bloque):
        errores.append(f"{donde}.bloque: se esperaba el nombre del bloque (texto)")
    handle = origen.get("handle")
    if not (isinstance(handle, str) and RE_HANDLE.match(handle)):
        errores.append(f"{donde}.handle: se esperaba el handle del INSERT (hexadecimal en "
                       f"mayúsculas)")
    ocurrencia = origen.get("ocurrencia")
    if not (isinstance(ocurrencia, int) and not isinstance(ocurrencia, bool) and ocurrencia >= 1):
        errores.append(f"{donde}.ocurrencia: se esperaba un entero ≥ 1")
    escala = leer_escala(origen.get("escala"))
    if escala is None:
        errores.append(f"{donde}.escala: se esperaba «1:N» (p. ej. \"1:50\"); tiene "
                       f"{origen.get('escala')!r}")
    tamano = origen.get("tamano_m")
    if not (isinstance(tamano, list) and len(tamano) == 2
            and all(_numero(v) and v >= 0 for v in tamano)):
        errores.append(f"{donde}.tamano_m: se esperaba [ancho, alto] en m (números ≥ 0)")
    exacta = origen.get("caja_exacta", True)
    if not isinstance(exacta, bool):
        errores.append(f"{donde}.caja_exacta: se esperaba true o false")
    try:
        return {"dxf": dxf, "bloque": bloque, "handle": handle, "ocurrencia": ocurrencia,
                "escala": escala, "tamano_m": (float(tamano[0]), float(tamano[1])),
                "caja_exacta": exacta}
    except (TypeError, IndexError, ValueError):
        return {}


def texto_pendientes(pendientes: tuple[BloquePendiente, ...], dxfs: tuple[DxfPlano, ...],
                     zona: tuple[float, float, float, float], nombre_zona: str) -> str:
    """Por qué `componer` no compone un plano versión 3 con bloques sin exportar: cuáles son,
    a qué escala, de qué DXF, y si alguno no cabe (para arreglarlo antes de exportar)."""
    from componedor.bloques_dxf import pagina_mm  # aquí: plano_dxf no depende del resto
    from componedor.colocar import exceso_de_tamano

    por_id = {d.id: d for d in dxfs}
    lineas = []
    for b in pendientes:
        dxf = por_id.get(b.dxf)
        nombre = dxf.archivo.name if dxf else b.dxf
        ocurrencia = f"ocurrencia {b.ocurrencia}, " if b.ocurrencia > 1 else ""
        linea = (f"- '{b.id}': bloque «{b.bloque}» ({ocurrencia}handle {b.handle}) a "
                 f"1:{b.escala:g}, de {nombre}")
        if dxf is not None:
            pagina = pagina_mm(b.tamano_m, b.escala, dxf.margen_mm)
            dx, dy = exceso_de_tamano(pagina, zona)
            if dx or dy:
                linea += (f" — NO CABE en '{nombre_zona}' a 1:{b.escala:g} (página "
                          f"{pagina[0]:.1f} × {pagina[1]:.1f} mm; sobran {dx:.1f} × "
                          f"{dy:.1f} mm): cambie la escala en el editor")
            if not dxf.archivo.is_file():
                linea += f" (el DXF ya no está en '{dxf.archivo}')"
        lineas.append(linea)
    n = len(pendientes)
    return (f"No se compone el plano: tiene {n} bloque(s) de DXF sin exportar todavía (plano "
            f"versión 3). Componer necesita el paquete (PDF + manifiesto) de cada uno:\n"
            + "\n".join(lineas)
            + "\nExpórtelos primero (desde el editor, cuando esté la exportación —etapa 3—, o "
              "con cde-exporter) y vuelva a componer.")
