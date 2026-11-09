"""Llenar el rótulo con los valores del plano.json (sección "rotulo", subfase 4.1).

Une tres cosas: la definición de los campos (formato, `rotulo_formato`), los valores del
plano (texto que escribe el usuario) y los campos calculados:
  - ESCALA ("escala_comun"): la de los detalles si todos tienen la misma ("1:1.000"); si no,
    "INDICADAS".
  - REV. ("ultima_revision"): la letra de mayor `orden` con revisión llena. En A1 ERCO el orden
    es A < B < C < 0: la «0» es la emisión final (para construcción) y A, B, C son emisiones
    previas; con «0», REV. = 0; sin ella, la mayor letra llena entre C, B y A; si
    no hay revisiones, vacía.

Valores del plano (todos opcionales; un campo que falta queda vacío, salvo su `por_defecto`):
  - campo de texto: "texto" (o número entero); en una celda de varias líneas también
    ["línea 1", "línea 2"] (líneas explícitas). Un texto largo se parte solo por palabras.
  - tabla con columna_clave (revisiones): [{"ver": "A", "fecha": ..., ...}, ...]; cada
    revisión va en la fila de SU letra (no por orden de llegada); letras repetidas: error.
  - tabla sin columna_clave (firmas): {"<fila>": {"<columna>": ...}}.
Campos desconocidos, calculados escritos a mano y textos que no caben: error, con TODOS los
problemas juntos.
"""

from dataclasses import dataclass, field
from pathlib import Path

from componedor.firmas import FirmaPedida, montajes, pedir_firma
from componedor.fuente import Fuente
from componedor.maquetacion import TextoMaquetado, TextoNoCabe, maquetar
from componedor.notas import SIGNO_VINETA, NotasMaquetadas, leer_notas, maquetar_notas
from componedor.rotulo_formato import (
    CampoConvenciones,
    CampoNotas,
    CampoTabla,
    CampoTexto,
    DefinicionRotulo,
)
from componedor.simbolos import (
    Biblioteca,
    BibliotecaInvalida,
    ColocacionSimbolo,
    cargar_biblioteca,
    colocar_simbolo,
)
from componedor.texto_escala import texto_escala

ESCALAS_DISTINTAS = "INDICADAS"


class RotuloInvalido(ValueError):
    """Los valores del rótulo no son válidos o no caben (el mensaje lista todo)."""

    def __init__(self, problemas: list[str]):
        self.problemas = problemas
        n = len(problemas)
        super().__init__(f"El rótulo tiene {n} {'problema' if n == 1 else 'problemas'}:\n"
                         + "\n".join(f"- {p}" for p in problemas))


@dataclass
class RotuloPreparado:
    textos: list[TextoMaquetado]  # solo los que tienen algo que escribir (incluye las notas)
    advertencias: list[str]
    valores: dict[str, str]  # valor final de cada campo de texto (incluye calculados)
    notas: NotasMaquetadas | None = None  # para verificar_notas y el resumen
    simbolos: list[ColocacionSimbolo] = field(default_factory=list)  # convenciones (4.2b)
    biblioteca: Biblioteca | None = None
    firmas: list[FirmaPedida] = field(default_factory=list)  # firmas en imagen (4.2d)


def preparar_rotulo(definicion: DefinicionRotulo, valores: dict | None,
                    escalas: list[float], fuente: Fuente,
                    carpeta: Path | None = None) -> RotuloPreparado:
    """Valida los valores, calcula ESCALA y REV. y maqueta cada celda. Lanza `RotuloInvalido`.
    `carpeta`: la del plano.json (las rutas de los archivos de notas son relativas a ella)."""
    valores = {} if valores is None else valores
    problemas: list[str] = []
    contenidos: list[tuple] = []  # (celda, contenido)
    for clave in sorted(set(valores) - set(definicion.campos)):
        problemas.append(f"rotulo.{clave}: campo no reconocido (campos válidos: "
                         f"{', '.join(definicion.campos)})")
    textos, advertencias = [], []
    notas = None
    simbolos, biblioteca = [], None
    for campo in definicion.campos.values():
        if isinstance(campo, CampoNotas) and campo.nombre in valores:
            notas = _notas(campo, valores[campo.nombre], definicion, fuente, carpeta,
                           problemas, advertencias)
        if isinstance(campo, CampoConvenciones) and campo.nombre in valores:
            simbolos, biblioteca = _convenciones(campo, valores[campo.nombre], definicion,
                                                 problemas, advertencias, contenidos)

    letras: list[str] = []
    imagenes: list[tuple] = []  # (celda, {"imagen": id}, sitio)
    for campo in definicion.campos.values():
        if isinstance(campo, CampoTabla):
            contenidos += _tabla(campo, valores.get(campo.nombre), problemas, letras, imagenes)
    firmas = []
    for celda, valor, sitio in imagenes:
        firma = pedir_firma(valor, celda, sitio, definicion.carpetas_firmas,
                            definicion.relleno_mm, problemas, advertencias)
        if firma is not None:
            firmas.append(firma)
    advertencias += montajes(firmas)

    finales: dict[str, str] = {}
    for campo in definicion.campos.values():
        if not isinstance(campo, CampoTexto):
            continue
        donde = f"rotulo.{campo.nombre}"
        if campo.calculado:
            if campo.nombre in valores:
                problemas.append(f"{donde}: se calcula automáticamente "
                                 f"({_explicar(campo.calculado)}); no se escribe en el plano")
            contenido = _calcular(campo, definicion, escalas, letras)
        elif campo.nombre in valores:
            contenido = _contenido(valores[campo.nombre], donde, campo.celda.lineas_max, problemas)
        else:
            contenido = campo.por_defecto or ""
        if contenido is None:
            continue
        finales[campo.nombre] = (" | ".join(contenido) if isinstance(contenido, list)
                                 else contenido)
        contenidos.append((campo.celda, contenido))

    for celda, contenido in contenidos:
        texto = " ".join(contenido) if isinstance(contenido, list) else contenido
        faltan = fuente.caracteres_faltantes(texto)
        if faltan:
            problemas.append(f"campo '{celda.ruta}': la fuente {fuente.nombre} no tiene los "
                             f"caracteres {' '.join(repr(c) for c in faltan)}")
            continue
        try:
            maquetado = maquetar(celda, contenido, fuente, definicion.relleno_mm,
                                 definicion.interlineado)
        except TextoNoCabe as e:
            problemas.append(str(e))
            continue
        if maquetado.lineas:
            textos.append(maquetado)
        if maquetado.reducido_desde is not None:
            advertencias.append(
                f"Advertencia: en el rótulo, el campo '{celda.ruta}' se escribió a "
                f"{maquetado.altura_mm:.1f} mm de altura (pedida {maquetado.reducido_desde:.1f} "
                f"mm) para que quepa en su celda.")
    if problemas:
        raise RotuloInvalido(problemas)
    if notas is not None:
        textos += notas.textos
        finales["notas"] = f"{len(notas.textos)} nota(s)"
    if simbolos:
        finales["convenciones"] = f"{len(simbolos)} convención(es)"
    return RotuloPreparado(textos, advertencias, finales, notas, simbolos, biblioteca, firmas)


def _convenciones(campo: CampoConvenciones, valor, definicion: DefinicionRotulo,
                  problemas: list[str], advertencias: list[str],
                  contenidos: list) -> tuple[list[ColocacionSimbolo], Biblioteca | None]:
    """Valida "convenciones" (lista de {"simbolo", "descripcion"}), las acomoda por columna
    (pareja izquierda de arriba abajo, luego la derecha) y agrega la descripción de cada una a
    `contenidos` (se maqueta como cualquier texto). Anota problemas y advertencias."""
    donde = f"rotulo.{campo.nombre}"
    if not isinstance(valor, list):
        problemas.append(f"{donde}: se esperaba una lista de {{\"simbolo\": ..., "
                         f"\"descripcion\": ...}}; tiene {_tipo(valor)}")
        return [], None
    if not valor:
        return [], None  # sin convenciones: no hace falta la biblioteca
    if len(valor) > campo.capacidad:
        problemas.append(f"{donde}: hay {len(valor)} convenciones y la tabla admite "
                         f"{campo.capacidad} (dos columnas de {campo.capacidad // 2})")
    try:
        biblioteca = cargar_biblioteca(campo.biblioteca)
    except BibliotecaInvalida as e:
        problemas.append(f"{donde}: {e}")
        return [], None
    validos = list(biblioteca.simbolos)
    vistos: dict[str, int] = {}
    colocaciones = []
    for i, item in enumerate(valor):
        sitio = f"{donde}[{i}]"
        if not isinstance(item, dict):
            problemas.append(f"{sitio}: se esperaba un objeto {{\"simbolo\": ...}}; tiene "
                             f"{_tipo(item)}")
            continue
        _desconocidas(item, ("descripcion", "simbolo"), sitio, problemas)
        ident = item.get("simbolo")
        if ident not in biblioteca.simbolos:
            problemas.append(f"{sitio}.simbolo: {_tipo(ident)} no está en la biblioteca "
                             f"(símbolos válidos: {', '.join(validos)})")
            continue
        if ident in vistos:
            problemas.append(f"{sitio}.simbolo: '{ident}' está repetido (ya está en "
                             f"{donde}[{vistos[ident]}])")
            continue
        vistos[ident] = i
        if i >= campo.capacidad:
            continue
        simbolo = biblioteca.simbolos[ident]
        celda = campo.descripciones[i]
        texto = (_contenido(item["descripcion"], f"{sitio}.descripcion", celda.lineas_max,
                            problemas) if "descripcion" in item else simbolo.descripcion)
        if texto is not None:
            contenidos.append((celda, texto))
        c = colocar_simbolo(simbolo, i + 1, campo.simbolos[i].rect, definicion.relleno_mm,
                            biblioteca.margen_mm)
        colocaciones.append(c)
        if c.escala < 1:
            ancho, alto = simbolo.tamano_mm
            casilla = c.casilla
            advertencias.append(
                f"Advertencia: en las convenciones, el símbolo '{ident}' (casilla {i + 1}) se "
                f"redujo al {c.escala * 100:.1f} % para caber en su casilla (dibujo {ancho:.2f} x "
                f"{alto:.2f} mm; espacio útil {casilla[2] - casilla[0] - 2 * definicion.relleno_mm:.2f}"
                f" x {casilla[3] - casilla[1] - 2 * definicion.relleno_mm:.2f} mm).")
    return colocaciones, biblioteca


def _notas(campo: CampoNotas, valor, definicion: DefinicionRotulo, fuente: Fuente,
           carpeta: Path | None, problemas: list[str],
           advertencias: list[str]) -> NotasMaquetadas | None:
    """Lee, revisa y acomoda las notas. Anota problemas y advertencias."""
    lista, avisos, errores = leer_notas(valor, carpeta)
    advertencias += avisos
    problemas += errores
    for k, nota in enumerate(lista, start=1):
        texto = " ".join((nota.texto, *nota.vinetas)) + (f" {SIGNO_VINETA}" if nota.vinetas else "")
        faltan = fuente.caracteres_faltantes(texto)
        if faltan:
            errores.append(f"rotulo.notas: la nota {k} ({nota.origen}) tiene caracteres que la "
                           f"fuente {fuente.nombre} no tiene: {' '.join(repr(c) for c in faltan)}")
            problemas.append(errores[-1])
    if errores:
        return None
    try:
        maquetadas = maquetar_notas(campo, lista, fuente, definicion.relleno_mm,
                                    definicion.interlineado)
    except TextoNoCabe as e:
        problemas.append(str(e))
        return None
    if maquetadas.reducido_desde is not None:
        advertencias.append(
            f"Advertencia: en el rótulo, las notas se escribieron a {maquetadas.altura_mm:.1f} "
            f"mm de altura (pedida {maquetadas.reducido_desde:.1f} mm) para que quepan en su "
            f"celda.")
    return maquetadas


def ultima_revision(letras: list[str], orden: tuple[str, ...]) -> str:
    """La letra de mayor orden entre las llenas ("" si no hay). `orden` va de menor a mayor
    (A1 ERCO: A, B, C, 0: la emisión final «0» manda sobre las previas)."""
    presentes = [l for l in orden if l in letras]
    return presentes[-1] if presentes else ""


def escala_comun(escalas: list[float]) -> str:
    """"1:N" si todos los detalles tienen la misma escala; si no, "INDICADAS"."""
    distintas = sorted(set(escalas))
    if not distintas:
        return ""
    return texto_escala(distintas[0]) if len(distintas) == 1 else ESCALAS_DISTINTAS


# --- partes ------------------------------------------------------------------------------

def _calcular(campo: CampoTexto, definicion: DefinicionRotulo, escalas: list[float],
              letras: list[str]) -> str:
    if campo.calculado == "escala_comun":
        return escala_comun(escalas)
    tabla = definicion.campos["revisiones"]
    return ultima_revision(letras, tabla.orden)


def _explicar(calculado: str) -> str:
    return {"escala_comun": "la escala de los detalles, o INDICADAS si son distintas",
            "ultima_revision": "0 si hay emisión final; si no, la mayor letra llena entre C, "
                               "B y A"}[calculado]


def _contenido(valor, donde: str, lineas_max: int, problemas: list[str]) -> str | list | None:
    """Texto de un valor del plano: str, entero o (si la celda tiene varias líneas) lista de
    textos. None si no es válido (el problema queda anotado). null = vacío."""
    if valor is None:
        return ""
    if isinstance(valor, int) and not isinstance(valor, bool):
        return str(valor)
    if isinstance(valor, str):
        if "\n" in valor and lineas_max == 1:
            problemas.append(f"{donde}: la celda es de una sola línea y el texto trae un salto "
                             f"de línea")
            return None
        return valor
    if isinstance(valor, list) and lineas_max > 1:
        if all(isinstance(v, str) and "\n" not in v for v in valor):
            return list(valor)
        problemas.append(f"{donde}: se esperaba una lista de líneas de texto; tiene {valor!r}")
        return None
    permitido = "un texto o una lista de líneas" if lineas_max > 1 else "un texto"
    problemas.append(f"{donde}: se esperaba {permitido}; tiene {_tipo(valor)}")
    return None


def _tabla(campo: CampoTabla, valor, problemas: list[str], letras: list[str],
           imagenes: list | None = None) -> list[tuple]:
    """(celda, contenido) de cada celda llena de la tabla. Anota las letras usadas."""
    donde = f"rotulo.{campo.nombre}"
    if valor is None:
        return []
    filas: dict[str, dict] = {}
    if campo.columna_clave is not None:
        if not isinstance(valor, list):
            problemas.append(f"{donde}: se esperaba una lista de objetos "
                             f"{{\"{campo.columna_clave}\": ..., ...}}; tiene {_tipo(valor)}")
            return []
        vistas: dict[str, int] = {}
        for i, item in enumerate(valor):
            sitio = f"{donde}[{i}]"
            if not isinstance(item, dict):
                problemas.append(f"{sitio}: se esperaba un objeto {{...}}; tiene {_tipo(item)}")
                continue
            letra = item.get(campo.columna_clave)
            letra = str(letra) if isinstance(letra, int) and not isinstance(letra, bool) else letra
            if letra not in campo.filas:
                problemas.append(f"{sitio}.{campo.columna_clave}: se esperaba una de "
                                 f"{', '.join(campo.orden)}; tiene {_tipo(letra)}")
                continue
            if letra in vistas:
                problemas.append(f"{sitio}.{campo.columna_clave}: la revisión '{letra}' está "
                                 f"repetida (ya está en {donde}[{vistas[letra]}])")
                continue
            vistas[letra] = i
            letras.append(letra)
            filas[letra] = dict(item, **{campo.columna_clave: letra})
            _desconocidas(item, campo.columnas, sitio, problemas)
            filas[letra]["__sitio"] = sitio
    else:
        if not isinstance(valor, dict):
            problemas.append(f"{donde}: se esperaba un objeto con las filas "
                             f"({', '.join(campo.filas)}); tiene {_tipo(valor)}")
            return []
        for fila in sorted(set(valor) - set(campo.filas)):
            problemas.append(f"{donde}.{fila}: fila no reconocida (filas válidas: "
                             f"{', '.join(campo.filas)})")
        for fila in campo.filas:
            if fila not in valor or valor[fila] is None:
                continue
            item = valor[fila]
            sitio = f"{donde}.{fila}"
            if not isinstance(item, dict):
                problemas.append(f"{sitio}: se esperaba un objeto con las columnas "
                                 f"({', '.join(campo.columnas)}); tiene {_tipo(item)}")
                continue
            _desconocidas(item, campo.columnas, sitio, problemas)
            filas[fila] = dict(item, __sitio=sitio)

    contenidos = []
    for fila in campo.filas:  # en el orden del formato
        if fila not in filas:
            continue
        item = filas[fila]
        for columna in campo.columnas:
            if columna not in item:
                continue
            celda = campo.celdas[(fila, columna)]
            sitio = f"{item['__sitio']}.{columna}"
            if isinstance(item[columna], dict) and imagenes is not None:
                imagenes.append((celda, item[columna], sitio))  # firma en imagen (4.2d)
                continue
            contenido = _contenido(item[columna], sitio, celda.lineas_max, problemas)
            if contenido is not None:
                contenidos.append((celda, contenido))
    return contenidos


def _desconocidas(item: dict, validas, donde: str, problemas: list[str]) -> None:
    for clave in sorted(set(item) - set(validas)):
        problemas.append(f"{donde}.{clave}: campo no reconocido (campos válidos: "
                         f"{', '.join(validas)})")


def _tipo(valor) -> str:
    if valor is None:
        return "null"
    if isinstance(valor, bool):
        return f"un booleano ({str(valor).lower()})"
    if isinstance(valor, str):
        return f"texto {valor!r}"
    if isinstance(valor, list):
        return "una lista"
    if isinstance(valor, dict):
        return "un objeto"
    return f"{type(valor).__name__} {valor!r}"
