"""Definición de los campos de texto del rótulo (sección "rotulo" del formato, subfase 4.1).

La plantilla PDF es solo geometría; QUÉ se escribe y DÓNDE lo dice esta sección del JSON del
formato (todo en mm de papel, Y hacia arriba). Esquema (versión 1):

    "rotulo": {
      "version": 1,
      "fuente": {"archivo": "C:/Windows/Fonts/arial.ttf"},
      "relleno_mm": 0.6,          # holgura del texto contra los bordes de la celda
      "interlineado": 1.6,        # de base a base de línea, en alturas de texto
      "campos": {
        "<nombre>": {"tipo": "texto", "rect_mm": [x0, y0, x1, y1], "alinear": "izq",
                     "altura_mm": 2.0, "altura_min_mm": 2.0, "lineas_max": 1,
                     "por_defecto": "DEFINIR" | "calculado": "escala_comun"},
        "<nombre>": {"tipo": "tabla", "altura_mm": 2.0, "altura_min_mm": 2.0,
                     "filas": {"<fila>": {"y_mm": [y0, y1], "lineas_max": 1}},
                     "columnas": {"<columna>": {"x_mm": [x0, x1], "alinear": "centro"}},
                     "columna_clave": "ver", "orden": ["0", "A", "B", "C"]},
        "<nombre>": {"tipo": "notas", "rect_mm": [x0, y0, x1, y1], "altura_mm": 1.8,
                     "altura_min_mm": 1.5, "separacion_notas": 0.5}
      }
    }

- `altura_mm` es la altura de las MAYÚSCULAS. Si un texto no cabe, se reduce de 0,1 en
  0,1 mm hasta `altura_min_mm` (por defecto igual a `altura_mm`: sin reducción).
- Tabla con `columna_clave` (revisiones): cada fila la elige el valor de esa columna
  ("ver": "A") y la columna se rellena con esa letra; `orden` va de menor a mayor.
- Tabla sin `columna_clave` (firmas): los valores van por nombre de fila.
- Calculados: "escala_comun" (escala de los detalles) y "ultima_revision" (letra de mayor
  orden de la tabla "revisiones").
- Notas (subfase 4.2a, aditivo): una celda con notas numeradas solas (notas.py);
  `separacion_notas` es el espacio extra entre notas, en renglones (0,5 = medio renglón).
- Convenciones (subfase 4.2b, aditivo): rejilla de símbolos y descripciones (simbolos.py):
      {"tipo": "convenciones", "filas_y_mm": [y_arriba, ..., y_abajo],
       "columnas_x_mm": [[x0, x1] símbolo, [x0, x1] descripción, [x0, x1] símbolo, [...]],
       "altura_mm": 1.8, "altura_min_mm": 1.5, "lineas_max": 2,
       "biblioteca": "../simbolos/indice.json"}
  Se llena por columna: la pareja izquierda de arriba abajo y luego la derecha.
- Firmas en imagen (subfase 4.2d, aditivo): en una columna de tabla, "acepta_imagen": true
  deja poner {"imagen": "<id>"} en vez de texto; la imagen es <carpeta>/<id>.png, con
  "carpeta_firmas": "../firmas" (o una lista de carpetas) en la sección "rotulo".
  "alto_max_mm" (por defecto 5,0; subfase 4.2e) deja que la imagen sea más alta que su fila y
  pase a las vecinas, siempre dentro del cuerpo de la tabla (sin el encabezado); una fila más
  alta usa su propia altura útil.

Campos desconocidos se rechazan. Todos los problemas se juntan en un solo error.
"""

import math
import os
from dataclasses import dataclass
from pathlib import Path

from componedor.transformaciones import RectMM

VERSION = 1
EPS_MM = 1e-6
ALINEACIONES = ("izq", "centro", "der")
CALCULADOS = ("escala_comun", "ultima_revision")
TABLA_REVISIONES = "revisiones"  # la que usa "ultima_revision"

CLAVES_ROTULO = {"version", "fuente", "relleno_mm", "interlineado", "campos", "carpeta_firmas"}
CLAVES_TEXTO = {"tipo", "rect_mm", "alinear", "altura_mm", "altura_min_mm", "lineas_max",
                "por_defecto", "calculado"}
CLAVES_TABLA = {"tipo", "altura_mm", "altura_min_mm", "filas", "columnas", "columna_clave",
                "orden"}
CLAVES_NOTAS = {"tipo", "rect_mm", "altura_mm", "altura_min_mm", "separacion_notas"}
CLAVES_CONVENCIONES = {"tipo", "filas_y_mm", "columnas_x_mm", "altura_mm", "altura_min_mm",
                       "lineas_max", "biblioteca"}
CLAVES_FILA = {"y_mm", "lineas_max"}
SEPARACION_NOTAS_POR_DEFECTO = 0.5
CLAVES_COLUMNA = {"x_mm", "alinear", "acepta_imagen", "alto_max_mm"}
ALTO_MAX_FIRMA_POR_DEFECTO = 5.0
RELLENO_POR_DEFECTO = 0.6
INTERLINEADO_POR_DEFECTO = 1.6


class RotuloFormatoInvalido(ValueError):
    """La sección "rotulo" del formato no cumple el esquema (el mensaje lista todo)."""


@dataclass(frozen=True)
class Celda:
    ruta: str  # "titulo", "revisiones.A.fecha", "firmas.reviso.nombre"
    rect: RectMM
    alinear: str
    altura_mm: float
    altura_min_mm: float
    lineas_max: int
    acepta_imagen: bool = False  # la celda admite {"imagen": id} (firma, subfase 4.2d)
    alto_max_mm: float = 0.0  # alto máximo de la imagen (puede pasar a filas vecinas; 4.2e)
    cuerpo_y: tuple[float, float] | None = None  # Y del cuerpo de la tabla (sin encabezado)


@dataclass(frozen=True)
class CampoTexto:
    nombre: str
    celda: Celda
    por_defecto: str | None = None
    calculado: str | None = None


@dataclass(frozen=True)
class CampoTabla:
    nombre: str
    filas: tuple[str, ...]  # en el orden del formato
    columnas: tuple[str, ...]
    celdas: dict[tuple[str, str], Celda]  # (fila, columna) -> celda
    columna_clave: str | None = None
    orden: tuple[str, ...] = ()  # de menor a mayor (solo con columna_clave)


@dataclass(frozen=True)
class CampoNotas:
    nombre: str
    celda: Celda  # lineas_max no se usa: caben las que quepan en el alto
    separacion_notas: float = SEPARACION_NOTAS_POR_DEFECTO  # renglones extra entre notas


@dataclass(frozen=True)
class CampoConvenciones:
    nombre: str
    simbolos: tuple[Celda, ...]  # casillas de símbolo, EN ORDEN DE LLENADO (izq. y luego der.)
    descripciones: tuple[Celda, ...]  # su descripción, mismo orden
    biblioteca: Path  # indice.json de la biblioteca de símbolos (ruta resuelta)

    @property
    def capacidad(self) -> int:
        return len(self.simbolos)


@dataclass(frozen=True)
class DefinicionRotulo:
    version: int
    fuente: Path  # ruta ya resuelta
    relleno_mm: float
    interlineado: float
    campos: dict[str, CampoTexto | CampoTabla | CampoNotas | CampoConvenciones]
    carpetas_firmas: tuple[Path, ...] = ()  # dónde se buscan las firmas en imagen (rutas resueltas)

    def celdas(self) -> list[Celda]:
        """Todas las celdas, en el orden del formato."""
        return [c for campo in self.campos.values() for c in _celdas(campo)]


def _celdas(campo) -> list[Celda]:
    if isinstance(campo, CampoTabla):
        return list(campo.celdas.values())
    if isinstance(campo, CampoConvenciones):
        return list(campo.simbolos) + list(campo.descripciones)
    return [campo.celda]


def leer_definicion_rotulo(datos, zona_rotulo: RectMM, base: Path | None = None) -> DefinicionRotulo:
    """Valida la sección "rotulo" y devuelve la definición. Lanza `RotuloFormatoInvalido`
    con todos los problemas. `base`: carpeta del formato (para una ruta de fuente relativa)."""
    errores: list[str] = []
    if not isinstance(datos, dict):
        raise RotuloFormatoInvalido(f"rotulo: se esperaba un objeto {{...}}; tiene {datos!r}.")
    _desconocidas(datos, CLAVES_ROTULO, "rotulo", errores)
    for clave in ("version", "fuente", "campos"):
        if clave not in datos:
            errores.append(f"rotulo.{clave}: falta el campo")

    version = datos.get("version")
    if "version" in datos and version != VERSION:
        errores.append(f"rotulo.version: versión {version!r} no soportada; el componedor "
                       f"entiende la versión {VERSION}")

    fuente = _fuente(datos.get("fuente"), base, errores) if "fuente" in datos else None
    relleno = _numero(datos, "relleno_mm", "rotulo", errores, RELLENO_POR_DEFECTO, minimo=0.0)
    interlineado = _numero(datos, "interlineado", "rotulo", errores, INTERLINEADO_POR_DEFECTO,
                           minimo=1.0)

    campos: dict[str, CampoTexto | CampoTabla] = {}
    valor_campos = datos.get("campos")
    if "campos" in datos:
        if not isinstance(valor_campos, dict) or not valor_campos:
            errores.append("rotulo.campos: se esperaba un objeto con al menos un campo")
        else:
            for nombre, valor in valor_campos.items():
                campo = _campo(nombre, valor, errores, base)
                if campo is not None:
                    campos[nombre] = campo

    if relleno is not None:
        _revisar_celdas(campos, zona_rotulo, relleno, errores)
    _revisar_calculados(campos, errores)
    carpetas = _carpetas_firmas(datos.get("carpeta_firmas"), base, errores)
    if not carpetas and "carpeta_firmas" not in datos and any(
            c.acepta_imagen for campo in campos.values() for c in _celdas(campo)):
        errores.append("rotulo.carpeta_firmas: hay celdas que aceptan imagen (\"acepta_imagen\": "
                       "true) y falta la carpeta donde buscar las firmas")

    if errores:
        n = len(errores)
        raise RotuloFormatoInvalido(
            f"La sección 'rotulo' del formato no es válida ({n} "
            f"{'problema' if n == 1 else 'problemas'}):\n" + "\n".join(f"- {e}" for e in errores))
    return DefinicionRotulo(version, fuente, relleno, interlineado, campos, carpetas)


def _carpetas_firmas(valor, base: Path | None, errores: list[str]) -> tuple[Path, ...]:
    """"carpeta_firmas": una ruta o una lista de rutas (relativas a la carpeta del formato)."""
    if valor is None:
        return ()
    lista = [valor] if isinstance(valor, str) else valor
    if (not isinstance(lista, list) or not lista
            or not all(isinstance(v, str) and v.strip() for v in lista)):
        errores.append(f"rotulo.carpeta_firmas: se esperaba una ruta o una lista de rutas; tiene "
                       f"{valor!r}")
        return ()
    rutas = []
    for v in lista:
        ruta = Path(v)
        if not ruta.is_absolute() and base is not None:
            ruta = Path(os.path.normpath(base / ruta))
        rutas.append(ruta)
    return tuple(rutas)


# --- partes ------------------------------------------------------------------------------

def _fuente(valor, base: Path | None, errores: list[str]) -> Path | None:
    if not isinstance(valor, dict) or set(valor) != {"archivo"}:
        errores.append(f"rotulo.fuente: se esperaba {{\"archivo\": \"ruta .ttf\"}}; tiene {valor!r}")
        return None
    archivo = valor["archivo"]
    if not isinstance(archivo, str) or not archivo.strip():
        errores.append(f"rotulo.fuente.archivo: se esperaba una ruta (texto); tiene {archivo!r}")
        return None
    ruta = Path(archivo)
    if not ruta.is_absolute() and base is not None:
        ruta = Path(os.path.normpath(base / ruta))
    return ruta  # que exista se comprueba al componer (cargar_fuente)


def _campo(nombre: str, valor, errores: list[str], base: Path | None = None):
    donde = f"rotulo.campos.{nombre}"
    if not isinstance(valor, dict):
        errores.append(f"{donde}: se esperaba un objeto {{...}}; tiene {valor!r}")
        return None
    tipo = valor.get("tipo")
    if tipo == "texto":
        return _campo_texto(nombre, valor, donde, errores)
    if tipo == "tabla":
        return _campo_tabla(nombre, valor, donde, errores)
    if tipo == "notas":
        return _campo_notas(nombre, valor, donde, errores)
    if tipo == "convenciones":
        return _campo_convenciones(nombre, valor, donde, errores, base)
    errores.append(f"{donde}.tipo: se esperaba \"texto\", \"tabla\", \"notas\" o "
                   f"\"convenciones\"; tiene {tipo!r}")
    return None


def _campo_convenciones(nombre: str, valor: dict, donde: str, errores: list[str],
                        base: Path | None) -> CampoConvenciones | None:
    """Rejilla de convenciones: filas (de arriba abajo) por parejas símbolo + descripción."""
    n = len(errores)
    _desconocidas(valor, CLAVES_CONVENCIONES, donde, errores)
    filas = valor.get("filas_y_mm")
    if (not isinstance(filas, list) or len(filas) < 2 or not all(map(_es_numero, filas))
            or any(a <= b for a, b in zip(filas, filas[1:]))):
        errores.append(f"{donde}.filas_y_mm: se esperaba la lista de las Y de las líneas de las "
                       f"filas, de arriba abajo (decreciente, al menos 2); tiene {filas!r}")
    columnas = valor.get("columnas_x_mm")
    if not isinstance(columnas, list) or not columnas or len(columnas) % 2:
        errores.append(f"{donde}.columnas_x_mm: se esperaba una lista de parejas [símbolo, "
                       f"descripción] de intervalos [x0, x1]; tiene {columnas!r}")
        columnas = []
    intervalos = [_intervalo(c, f"{donde}.columnas_x_mm[{i}]", errores)
                  for i, c in enumerate(columnas)]
    altura, minima = _alturas(valor, donde, errores)
    lineas = _lineas_max(valor, donde, errores)
    biblioteca = valor.get("biblioteca")
    if not isinstance(biblioteca, str) or not biblioteca.strip():
        errores.append(f"{donde}.biblioteca: se esperaba la ruta del indice.json de la "
                       f"biblioteca de símbolos; tiene {biblioteca!r}")
    if len(errores) > n:
        return None
    ruta = Path(biblioteca)
    if not ruta.is_absolute() and base is not None:
        ruta = Path(os.path.normpath(base / ruta))
    simbolos, descripciones = [], []
    for par in range(len(intervalos) // 2):  # llenado por columna: pareja izq., luego der.
        (sx0, sx1), (dx0, dx1) = intervalos[2 * par], intervalos[2 * par + 1]
        for f, (y1, y0) in enumerate(zip(filas, filas[1:]), start=1):
            k = par * (len(filas) - 1) + f
            simbolos.append(Celda(f"{nombre}.{k}.simbolo", (sx0, y0, sx1, y1), "centro",
                                  altura, minima, 1))
            descripciones.append(Celda(f"{nombre}.{k}.descripcion", (dx0, y0, dx1, y1), "izq",
                                       altura, minima, lineas))
    return CampoConvenciones(nombre, tuple(simbolos), tuple(descripciones), ruta)


def _campo_notas(nombre: str, valor: dict, donde: str, errores: list[str]) -> CampoNotas | None:
    n = len(errores)
    _desconocidas(valor, CLAVES_NOTAS, donde, errores)
    rect = _rect(valor.get("rect_mm"), f"{donde}.rect_mm", errores)
    altura, minima = _alturas(valor, donde, errores)
    separacion = _numero(valor, "separacion_notas", donde, errores,
                         SEPARACION_NOTAS_POR_DEFECTO, minimo=0.0)
    if len(errores) > n:
        return None
    return CampoNotas(nombre, Celda(nombre, rect, "izq", altura, minima, 1), separacion)


def _campo_texto(nombre: str, valor: dict, donde: str, errores: list[str]) -> CampoTexto | None:
    n = len(errores)
    _desconocidas(valor, CLAVES_TEXTO, donde, errores)
    rect = _rect(valor.get("rect_mm"), f"{donde}.rect_mm", errores)
    alinear = _alinear(valor.get("alinear"), f"{donde}.alinear", errores)
    altura, minima = _alturas(valor, donde, errores)
    lineas = _lineas_max(valor, donde, errores)
    por_defecto = valor.get("por_defecto")
    if por_defecto is not None and not isinstance(por_defecto, str):
        errores.append(f"{donde}.por_defecto: se esperaba un texto; tiene {por_defecto!r}")
    calculado = valor.get("calculado")
    if calculado is not None and calculado not in CALCULADOS:
        errores.append(f"{donde}.calculado: se esperaba uno de {', '.join(CALCULADOS)}; "
                       f"tiene {calculado!r}")
    if calculado is not None and por_defecto is not None:
        errores.append(f"{donde}: un campo calculado no lleva por_defecto")
    if len(errores) > n:
        return None
    return CampoTexto(nombre, Celda(nombre, rect, alinear, altura, minima, lineas),
                      por_defecto, calculado)


def _campo_tabla(nombre: str, valor: dict, donde: str, errores: list[str]) -> CampoTabla | None:
    n = len(errores)
    _desconocidas(valor, CLAVES_TABLA, donde, errores)
    altura, minima = _alturas(valor, donde, errores)

    filas: dict[str, tuple[tuple[float, float], int]] = {}
    for fila, item in _objeto(valor.get("filas"), f"{donde}.filas", errores).items():
        sitio = f"{donde}.filas.{fila}"
        if not isinstance(item, dict):
            errores.append(f"{sitio}: se esperaba {{\"y_mm\": [y0, y1]}}; tiene {item!r}")
            continue
        _desconocidas(item, CLAVES_FILA, sitio, errores)
        y = _intervalo(item.get("y_mm"), f"{sitio}.y_mm", errores)
        lineas = _lineas_max(item, sitio, errores)
        if y is not None and lineas is not None:
            filas[fila] = (y, lineas)

    columnas: dict[str, tuple[tuple[float, float], str, bool, float]] = {}
    for columna, item in _objeto(valor.get("columnas"), f"{donde}.columnas", errores).items():
        sitio = f"{donde}.columnas.{columna}"
        if not isinstance(item, dict):
            errores.append(f"{sitio}: se esperaba {{\"x_mm\": [x0, x1], \"alinear\": ...}}; "
                           f"tiene {item!r}")
            continue
        _desconocidas(item, CLAVES_COLUMNA, sitio, errores)
        x = _intervalo(item.get("x_mm"), f"{sitio}.x_mm", errores)
        alinear = _alinear(item.get("alinear"), f"{sitio}.alinear", errores)
        imagen = item.get("acepta_imagen", False)
        if not isinstance(imagen, bool):
            errores.append(f"{sitio}.acepta_imagen: se esperaba true o false; tiene {imagen!r}")
        alto_max = item.get("alto_max_mm", ALTO_MAX_FIRMA_POR_DEFECTO if imagen is True else 0.0)
        if "alto_max_mm" in item and imagen is not True:
            errores.append(f"{sitio}.alto_max_mm: solo se usa con \"acepta_imagen\": true")
        elif not _es_numero(alto_max) or (imagen is True and alto_max <= 0):
            errores.append(f"{sitio}.alto_max_mm: se esperaba un número positivo (mm); tiene "
                           f"{alto_max!r}")
        if x is not None and alinear is not None:
            columnas[columna] = (x, alinear, imagen is True,
                                 float(alto_max) if _es_numero(alto_max) else 0.0)

    clave = valor.get("columna_clave")
    orden = valor.get("orden")
    if clave is not None and clave not in columnas:
        errores.append(f"{donde}.columna_clave: {clave!r} no es una de las columnas "
                       f"({', '.join(columnas)})")
    if clave is None and orden is not None:
        errores.append(f"{donde}.orden: solo se usa con columna_clave")
    if clave is not None:
        if not isinstance(orden, list) or sorted(map(str, orden)) != sorted(filas) \
                or len(set(orden)) != len(orden):
            errores.append(f"{donde}.orden: se esperaba la lista de las filas "
                           f"({', '.join(filas)}) de menor a mayor; tiene {orden!r}")
    if len(errores) > n:
        return None

    celdas = {}
    cuerpo = (min(y[0] for y, _ in filas.values()), max(y[1] for y, _ in filas.values()))
    for fila, ((y0, y1), lineas) in filas.items():
        for columna, ((x0, x1), alinear, imagen, alto_max) in columnas.items():
            celdas[(fila, columna)] = Celda(f"{nombre}.{fila}.{columna}", (x0, y0, x1, y1),
                                            alinear, altura, minima, lineas, imagen, alto_max,
                                            cuerpo)
    return CampoTabla(nombre, tuple(filas), tuple(columnas), celdas, clave,
                      tuple(orden) if clave is not None else ())


def _revisar_celdas(campos: dict, zona: RectMM, relleno: float, errores: list[str]) -> None:
    """Cada celda dentro de la zona del rótulo, con alto para una línea y sin traslapes."""
    celdas = [c for campo in campos.values() for c in _celdas(campo)]
    for c in celdas:
        x0, y0, x1, y1 = c.rect
        if (x0 < zona[0] - EPS_MM or y0 < zona[1] - EPS_MM or x1 > zona[2] + EPS_MM
                or y1 > zona[3] + EPS_MM):
            errores.append(f"celda '{c.ruta}' {_lista(c.rect)}: se sale de la zona 'rotulo' "
                           f"{_lista(zona)}")
        alto_util = (y1 - y0) - 2 * relleno
        if alto_util < c.altura_min_mm - EPS_MM:
            errores.append(f"celda '{c.ruta}': mide {y1 - y0:.2f} mm de alto; con relleno de "
                           f"{relleno} mm no cabe ni una línea de {c.altura_min_mm} mm")
    for i, a in enumerate(celdas):
        for b in celdas[i + 1:]:
            if (a.rect[0] < b.rect[2] - EPS_MM and b.rect[0] < a.rect[2] - EPS_MM
                    and a.rect[1] < b.rect[3] - EPS_MM and b.rect[1] < a.rect[3] - EPS_MM):
                errores.append(f"las celdas '{a.ruta}' {_lista(a.rect)} y '{b.ruta}' "
                               f"{_lista(b.rect)} se traslapan")


def _revisar_calculados(campos: dict, errores: list[str]) -> None:
    for campo in campos.values():
        if isinstance(campo, CampoTexto) and campo.calculado == "ultima_revision":
            tabla = campos.get(TABLA_REVISIONES)
            if not isinstance(tabla, CampoTabla) or tabla.columna_clave is None:
                errores.append(f"rotulo.campos.{campo.nombre}: \"ultima_revision\" necesita la "
                               f"tabla '{TABLA_REVISIONES}' con columna_clave y orden")


# --- lectores pequeños --------------------------------------------------------------------

def _desconocidas(valor: dict, validas: set[str], donde: str, errores: list[str]) -> None:
    for clave in sorted(set(valor) - validas):
        errores.append(f"{donde}.{clave}: campo no reconocido (campos válidos: "
                       f"{', '.join(sorted(validas))})")


def _objeto(valor, donde: str, errores: list[str]) -> dict:
    if not isinstance(valor, dict) or not valor:
        errores.append(f"{donde}: se esperaba un objeto con al menos un elemento; tiene {valor!r}")
        return {}
    return valor


def _es_numero(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _numero(datos: dict, clave: str, donde: str, errores: list[str], defecto: float,
            minimo: float) -> float | None:
    if clave not in datos:
        return defecto
    v = datos[clave]
    if not _es_numero(v) or v < minimo:
        errores.append(f"{donde}.{clave}: se esperaba un número mayor o igual a {minimo}; "
                       f"tiene {v!r}")
        return None
    return float(v)


def _rect(valor, donde: str, errores: list[str]) -> RectMM | None:
    if not isinstance(valor, list) or len(valor) != 4 or not all(map(_es_numero, valor)):
        errores.append(f"{donde}: se esperaba [x0, y0, x1, y1] con 4 números en mm; tiene {valor!r}")
        return None
    x0, y0, x1, y1 = (float(v) for v in valor)
    if x1 - x0 <= 0 or y1 - y0 <= 0:
        errores.append(f"{donde}: ancho y alto deben ser positivos (x1 > x0, y1 > y0); tiene {valor}")
        return None
    return x0, y0, x1, y1


def _intervalo(valor, donde: str, errores: list[str]) -> tuple[float, float] | None:
    if (not isinstance(valor, list) or len(valor) != 2 or not all(map(_es_numero, valor))
            or valor[1] <= valor[0]):
        errores.append(f"{donde}: se esperaba [mínimo, máximo] en mm con máximo > mínimo; "
                       f"tiene {valor!r}")
        return None
    return float(valor[0]), float(valor[1])


def _alinear(valor, donde: str, errores: list[str]) -> str | None:
    if valor not in ALINEACIONES:
        errores.append(f"{donde}: se esperaba uno de {', '.join(ALINEACIONES)}; tiene {valor!r}")
        return None
    return valor


def _alturas(valor: dict, donde: str, errores: list[str]) -> tuple[float | None, float | None]:
    altura = valor.get("altura_mm")
    if not _es_numero(altura) or altura <= 0:
        errores.append(f"{donde}.altura_mm: se esperaba un número positivo (mm); tiene {altura!r}")
        return None, None
    minima = valor.get("altura_min_mm", altura)
    if not _es_numero(minima) or minima <= 0 or minima > altura + EPS_MM:
        errores.append(f"{donde}.altura_min_mm: se esperaba un número positivo no mayor que "
                       f"altura_mm ({altura}); tiene {minima!r}")
        return float(altura), None
    return float(altura), float(minima)


def _lineas_max(valor: dict, donde: str, errores: list[str]) -> int | None:
    lineas = valor.get("lineas_max", 1)
    if not isinstance(lineas, int) or isinstance(lineas, bool) or lineas < 1:
        errores.append(f"{donde}.lineas_max: se esperaba un entero mayor o igual a 1; "
                       f"tiene {lineas!r}")
        return None
    return lineas


def _lista(rect) -> str:
    return "[" + ", ".join(f"{v:g}" for v in rect) + "]"
