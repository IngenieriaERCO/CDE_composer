"""Archivo de configuración `componedor.json`: generar siempre el mismo editor y componer
siempre con el mismo formato, sin escribir rutas en la línea de comandos.

Esquema (versión 1):

    {
      "version": 1,
      "formato": "formatos/A1_ERCO.json",      (obligatorio: el de la hoja, para los dos)
      "editor": {
        "paquetes": "data/input",              (obligatorio: carpeta con los paquetes)
        "salida":   "editor",                  (obligatorio: carpeta del editor; se crea)
        "notas":    "notas",                   (opcional: catálogo de notas típicas)
        "firmas":   "firmas",                  (opcional: carpeta de firmas por persona)
        "proyecto": null                       (opcional: proyecto.json para prellenar)
      },
      "componer": {
        "resultados": "resultados"             (obligatorio: carpeta de los PDF; se crea)
      }
    }

Cada comando lee solo su sección (`leer_config_editor`, `leer_config_componer`) y el formato.
Las rutas relativas se toman desde la carpeta donde está el archivo de configuración (no desde
donde se ejecuta el comando), así los accesos directos funcionan desde cualquier lado. Una
opción opcional en null (o ausente) no se usa. A diferencia del manifiesto del exportador, aquí
una clave desconocida es error: el archivo lo escribe una persona y una clave mal escrita
(«nota» en vez de «notas») pasaría inadvertida. Se reportan todos los problemas juntos.
"""

import json
from dataclasses import dataclass
from pathlib import Path

VERSION = 1
CLAVES_GENERALES = ("version", "formato", "editor", "componer")
# Por sección: (obligatorias, opcionales, {clave: "carpeta" | "archivo"} de las que deben existir).
SECCIONES = {
    "editor": (("paquetes", "salida"), ("notas", "firmas", "proyecto"),
               {"paquetes": "carpeta", "notas": "carpeta", "firmas": "carpeta",
                "proyecto": "archivo"}),
    "componer": (("resultados",), (), {}),
}


class ConfigInvalida(ValueError):
    """El archivo de configuración no se puede usar (mensaje en español para el usuario)."""


@dataclass(frozen=True)
class ConfigEditor:
    paquetes: Path
    formato: Path
    salida: Path
    notas: Path | None = None
    firmas: Path | None = None
    proyecto: Path | None = None


@dataclass(frozen=True)
class ConfigComponer:
    formato: Path
    resultados: Path


def leer_config_editor(ruta: Path | str, verificar_rutas: bool = True) -> ConfigEditor:
    """Formato y sección "editor", con las rutas resueltas. Con `verificar_rutas`, comprueba
    que formato y proyecto sean archivos y paquetes, notas y firmas, carpetas."""
    return ConfigEditor(**_leer_seccion(ruta, "editor", verificar_rutas))


def leer_config_componer(ruta: Path | str, verificar_rutas: bool = True) -> ConfigComponer:
    """Formato y sección "componer" (la carpeta de resultados se crea si falta)."""
    return ConfigComponer(**_leer_seccion(ruta, "componer", verificar_rutas))


def _leer_seccion(ruta: Path | str, nombre: str, verificar_rutas: bool) -> dict[str, Path | None]:
    ruta = Path(ruta)
    datos = _leer_json(ruta)
    obligatorias, opcionales, tipos = SECCIONES[nombre]
    problemas = [f"{clave}: clave desconocida (se admiten {', '.join(CLAVES_GENERALES)})."
                 for clave in sorted(set(datos) - set(CLAVES_GENERALES))]
    base = ruta.parent
    rutas = {"formato": _ruta(datos.get("formato"), "formato", True, base, problemas)}
    seccion = datos.get(nombre)
    if not isinstance(seccion, dict):
        problemas.append(f'falta la sección "{nombre}" (un objeto con '
                         f"{', '.join(obligatorias)}).")
        seccion = None
    else:
        for clave in sorted(set(seccion) - set(obligatorias) - set(opcionales)):
            problemas.append(f"{nombre}.{clave}: clave desconocida (se admiten "
                             f"{', '.join(obligatorias + opcionales)}).")
        for clave in obligatorias + opcionales:
            rutas[clave] = _ruta(seccion.get(clave), f"{nombre}.{clave}", clave in obligatorias,
                                 base, problemas)
    if verificar_rutas:
        for clave, tipo in {"formato": "archivo", **tipos}.items():
            r = rutas.get(clave)
            if r is None:
                continue
            if not (r.is_dir() if tipo == "carpeta" else r.is_file()):
                donde = clave if clave == "formato" else f"{nombre}.{clave}"
                articulo = "la" if tipo == "carpeta" else "el"
                problemas.append(f"{donde}: no existe {articulo} {tipo} '{r}'.")
    if problemas:
        raise ConfigInvalida(f"El archivo de configuración '{ruta}' tiene "
                             f"{len(problemas)} problema(s):\n"
                             + "\n".join(f"- {p}" for p in problemas))
    return rutas


def _leer_json(ruta: Path) -> dict:
    if not ruta.is_file():
        raise ConfigInvalida(f"No se encontró el archivo de configuración '{ruta}'.")
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as e:
        raise ConfigInvalida(f"'{ruta}' no es un JSON válido (línea {e.lineno}, columna "
                             f"{e.colno}): {e.msg}.") from None
    if not isinstance(datos, dict):
        raise ConfigInvalida(f"'{ruta}': se esperaba un objeto JSON {{...}}.")
    if datos.get("version") != VERSION:
        raise ConfigInvalida(f"'{ruta}': version debe ser {VERSION} "
                             f"(se encontró {datos.get('version')!r}).")
    return datos


def _ruta(valor, donde: str, obligatoria: bool, base: Path, problemas: list[str]) -> Path | None:
    if valor is None:
        if obligatoria:
            problemas.append(f"{donde}: es obligatorio.")
        return None
    if not isinstance(valor, str) or not valor.strip():
        problemas.append(f"{donde}: se esperaba una ruta (texto no vacío).")
        return None
    return base / valor
