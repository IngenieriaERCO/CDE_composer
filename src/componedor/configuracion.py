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
      },
      "exportador": {                          (opcional: «Cargar DXF» del editor con servidor)
        "comando": "cde-exporter",             (obligatorio: comando, o lista [programa, args…])
        "trabajo": "data/cache_exportador",    (obligatorio: carpeta del trabajador; se crea)
        "margen_mm": 5,                        (opcional: margen de página al exportar; 5)
        "cache_previas_mb": 500,               (opcional: tope de la caché de vistas previas
                                                del trabajador, --preview-cache-mb; sin la
                                                clave, el del trabajador: 500)
        "paquetes": "data/input/dxf",          (opcional: dónde «Exportar» publica los
                                                paquetes, en <paquetes>/<dxf>/; ese valor)
        "para_borrar": "_para_borrar",         (opcional: adónde se MUEVEN los paquetes viejos
                                                que se reemplazan; ese valor)
        "anonimos_min_entidades": 100,         (opcional: los bloques anónimos *U que dibujan
                                                al menos esas entidades visibles se ofrecen
                                                en «Anónimos (opcionales)» de la carpeta; va
                                                en load como anonymous_min_entities; 100)
        "carpeta_ctb": "../Exportador Vectorial/data/input/ctb",
                                               (opcional: carpeta de las tablas de estilos
                                                de impresión .ctb que ofrece el editor al
                                                exportar; sin ella, solo «sin CTB»)
        "estilo_impresion": "CTB_ERCO_derivada_PRGD.ctb",
                                               (opcional: la tabla elegida al abrir el editor,
                                                por NOMBRE, de esa carpeta; null: sin CTB)
        "imprimir_transparencia": false        (opcional: con false no se dibujan los rellenos
                                                con transparencia del 80 % o más; true)
      },
      "ortofoto": {                            (opcional: la ortofoto de fondo en el PDF)
        "ppp": 300,                            (opcional: resolución con que se pone en el PDF,
                                                en píxeles por pulgada de papel; de 72 a 1200;
                                                300)
        "calidad_jpeg": 85,                    (opcional: calidad JPEG de 1 a 100; 85)
        "cuadricula_intervalo_m": 50           (opcional: intervalo de la cuadrícula de
                                                coordenadas, en m, si el plano no dice otro; 50)
      }
    }

Cada comando lee solo su sección (`leer_config_editor`, `leer_config_componer`,
`leer_config_exportador`, `leer_config_ortofoto`) y el formato.
Las rutas relativas se toman desde la carpeta donde está el archivo de configuración (no desde
donde se ejecuta el comando), así los accesos directos funcionan desde cualquier lado. Una
opción opcional en null (o ausente) no se usa. A diferencia del manifiesto del exportador, aquí
una clave desconocida es error: el archivo lo escribe una persona y una clave mal escrita
(«nota» en vez de «notas») pasaría inadvertida. Se reportan todos los problemas juntos.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from componedor.estilos_impresion import nombre_valido

VERSION = 1
CLAVES_GENERALES = ("version", "formato", "editor", "componer", "exportador", "ortofoto")
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


@dataclass(frozen=True)
class ConfigExportador:
    """Cómo lanzar el trabajador del Exportador Vectorial (`cde-exporter worker`)."""
    comando: tuple[str, ...]  # programa y argumentos previos a "worker"
    trabajo: Path  # carpeta del trabajador (--work-dir) y de los registros
    margen_mm: float = 5.0
    cache_previas_mb: int | None = None  # --preview-cache-mb; None: el del trabajador
    paquetes: Path | None = None  # «Exportar»: <paquetes>/<dxf>/ (None: no se puede exportar)
    para_borrar: Path | None = None  # adónde se mueven los paquetes viejos
    anonimos_min_entidades: int = 100  # load: anonymous_min_entities
    carpeta_ctb: Path | None = None  # tablas .ctb que ofrece el editor (estilos_impresion)
    estilo_impresion: str | None = None  # la elegida por defecto (nombre de archivo)
    imprimir_transparencia: bool = True  # por defecto (print_transparency)

    def opciones_trabajador(self) -> tuple[str, ...]:
        """Lo que va después de `worker --work-dir <trabajo>`."""
        if self.cache_previas_mb is None:
            return ()
        return ("--preview-cache-mb", str(self.cache_previas_mb))


@dataclass(frozen=True)
class ConfigOrtofoto:
    """Cómo va la ortofoto en el PDF (la usa componer, etapa 2)."""
    ppp: int = 300
    calidad_jpeg: int = 85
    cuadricula_intervalo_m: float = 50.0


CLAVES_EXPORTADOR = ("comando", "trabajo", "margen_mm", "cache_previas_mb", "paquetes",
                     "para_borrar", "anonimos_min_entidades", "carpeta_ctb", "estilo_impresion",
                     "imprimir_transparencia")
PAQUETES_POR_DEFECTO = "data/input/dxf"
PARA_BORRAR_POR_DEFECTO = "_para_borrar"
MARGEN_MM_POR_DEFECTO = 5.0
ANONIMOS_MIN_POR_DEFECTO = 100
CLAVES_ORTOFOTO = ("ppp", "calidad_jpeg", "cuadricula_intervalo_m")
PPP_LIMITES = (72, 1200)


def leer_config_editor(ruta: Path | str, verificar_rutas: bool = True) -> ConfigEditor:
    """Formato y sección "editor", con las rutas resueltas. Con `verificar_rutas`, comprueba
    que formato y proyecto sean archivos y paquetes, notas y firmas, carpetas."""
    return ConfigEditor(**_leer_seccion(ruta, "editor", verificar_rutas))


def leer_config_componer(ruta: Path | str, verificar_rutas: bool = True) -> ConfigComponer:
    """Formato y sección "componer" (la carpeta de resultados se crea si falta)."""
    return ConfigComponer(**_leer_seccion(ruta, "componer", verificar_rutas))


def leer_config_exportador(ruta: Path | str) -> ConfigExportador | None:
    """La sección "exportador", o None si el archivo no la tiene (el editor funciona igual,
    sin «Cargar DXF»). La carpeta de trabajo no tiene que existir: se crea al usarla."""
    ruta = Path(ruta)
    datos = _leer_json(ruta)
    seccion = datos.get("exportador")
    if seccion is None:
        return None
    problemas = []
    if not isinstance(seccion, dict):
        raise ConfigInvalida(f"'{ruta}': \"exportador\" debe ser un objeto con "
                             f"{', '.join(CLAVES_EXPORTADOR)}.")
    for clave in sorted(set(seccion) - set(CLAVES_EXPORTADOR)):
        problemas.append(f"exportador.{clave}: clave desconocida (se admiten "
                         f"{', '.join(CLAVES_EXPORTADOR)}).")
    comando = seccion.get("comando")
    if isinstance(comando, str) and comando.strip():
        comando = (comando,)
    elif (isinstance(comando, list) and comando
          and all(isinstance(c, str) and c.strip() for c in comando)):
        comando = tuple(comando)
    else:
        problemas.append("exportador.comando: se esperaba el comando (texto, p. ej. "
                         "\"cde-exporter\") o una lista de textos no vacíos.")
        comando = None
    trabajo = _ruta(seccion.get("trabajo"), "exportador.trabajo", True, ruta.parent, problemas)
    margen = seccion.get("margen_mm", MARGEN_MM_POR_DEFECTO)
    if isinstance(margen, bool) or not isinstance(margen, (int, float)) or not margen >= 0:
        problemas.append("exportador.margen_mm: se esperaba un número ≥ 0 (mm).")
    cache = seccion.get("cache_previas_mb")
    if cache is not None and (isinstance(cache, bool) or not isinstance(cache, int) or cache < 1):
        problemas.append("exportador.cache_previas_mb: se esperaba un entero ≥ 1 (MB) o null.")
    paquetes = _ruta(seccion.get("paquetes", PAQUETES_POR_DEFECTO), "exportador.paquetes", True,
                     ruta.parent, problemas)
    para_borrar = _ruta(seccion.get("para_borrar", PARA_BORRAR_POR_DEFECTO),
                        "exportador.para_borrar", True, ruta.parent, problemas)
    anonimos = seccion.get("anonimos_min_entidades", ANONIMOS_MIN_POR_DEFECTO)
    if isinstance(anonimos, bool) or not isinstance(anonimos, int) or anonimos < 1:
        problemas.append("exportador.anonimos_min_entidades: se esperaba un entero ≥ 1 (entidades "
                         "visibles que debe dibujar un bloque anónimo para ofrecerlo).")
    carpeta_ctb = _ruta(seccion.get("carpeta_ctb"), "exportador.carpeta_ctb", False, ruta.parent,
                        problemas)
    estilo = seccion.get("estilo_impresion")
    if estilo is not None:
        if not nombre_valido(estilo):
            problemas.append("exportador.estilo_impresion: se esperaba el NOMBRE de una tabla .ctb "
                             "de carpeta_ctb (sin carpetas, p. ej. \"CTB_ERCO_derivada_PRGD.ctb\") "
                             "o null.")
        elif "carpeta_ctb" not in seccion or seccion.get("carpeta_ctb") is None:
            problemas.append("exportador.estilo_impresion: falta exportador.carpeta_ctb (la "
                             "carpeta donde está la tabla).")
    transparencia = seccion.get("imprimir_transparencia", True)
    if not isinstance(transparencia, bool):
        problemas.append("exportador.imprimir_transparencia: se esperaba true o false.")
    if problemas:
        raise ConfigInvalida(f"El archivo de configuración '{ruta}' tiene "
                             f"{len(problemas)} problema(s):\n"
                             + "\n".join(f"- {p}" for p in problemas))
    return ConfigExportador(comando, trabajo, float(margen), cache, paquetes, para_borrar,
                            anonimos, carpeta_ctb, estilo, transparencia)


def leer_config_ortofoto(ruta: Path | str) -> ConfigOrtofoto:
    """La sección "ortofoto" (opcional: sin ella, 300 ppp y calidad JPEG 85)."""
    ruta = Path(ruta)
    seccion = _leer_json(ruta).get("ortofoto")
    if seccion is None:
        return ConfigOrtofoto()
    if not isinstance(seccion, dict):
        raise ConfigInvalida(f"'{ruta}': \"ortofoto\" debe ser un objeto con "
                             f"{', '.join(CLAVES_ORTOFOTO)}.")
    problemas = [f"ortofoto.{clave}: clave desconocida (se admiten "
                 f"{', '.join(CLAVES_ORTOFOTO)})." for clave in sorted(set(seccion) - set(CLAVES_ORTOFOTO))]
    ppp = seccion.get("ppp", ConfigOrtofoto.ppp)
    if (isinstance(ppp, bool) or not isinstance(ppp, int)
            or not PPP_LIMITES[0] <= ppp <= PPP_LIMITES[1]):
        problemas.append(f"ortofoto.ppp: se esperaba un entero de {PPP_LIMITES[0]} a "
                         f"{PPP_LIMITES[1]} (píxeles por pulgada de papel).")
    calidad = seccion.get("calidad_jpeg", ConfigOrtofoto.calidad_jpeg)
    if isinstance(calidad, bool) or not isinstance(calidad, int) or not 1 <= calidad <= 100:
        problemas.append("ortofoto.calidad_jpeg: se esperaba un entero de 1 a 100.")
    intervalo = seccion.get("cuadricula_intervalo_m", ConfigOrtofoto.cuadricula_intervalo_m)
    if (isinstance(intervalo, bool) or not isinstance(intervalo, (int, float))
            or not 0 < intervalo <= 100000):
        problemas.append("ortofoto.cuadricula_intervalo_m: se esperaba un número de m > 0.")
    if problemas:
        raise ConfigInvalida(f"El archivo de configuración '{ruta}' tiene "
                             f"{len(problemas)} problema(s):\n"
                             + "\n".join(f"- {p}" for p in problemas))
    return ConfigOrtofoto(ppp, calidad, float(intervalo))


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
