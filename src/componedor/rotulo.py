"""Llenar el rótulo con los valores del plano.json (sección "rotulo", subfase 4.1).

Une tres cosas: la definición de los campos (formato, `rotulo_formato`), los valores del
plano (texto que escribe el usuario) y los campos calculados:
  - ESCALA ("escala_comun"): la de los detalles si todos tienen la misma ("1:1.000"); si no,
    "INDICADAS".
  - REV. ("ultima_revision"): la letra de mayor orden con revisión llena (0 < A < B < C); si
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

from dataclasses import dataclass

from componedor.fuente import Fuente
from componedor.maquetacion import TextoMaquetado, TextoNoCabe, maquetar
from componedor.rotulo_formato import CampoTabla, CampoTexto, DefinicionRotulo
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
    textos: list[TextoMaquetado]  # solo los que tienen algo que escribir
    advertencias: list[str]
    valores: dict[str, str]  # valor final de cada campo de texto (incluye calculados)


def preparar_rotulo(definicion: DefinicionRotulo, valores: dict | None,
                    escalas: list[float], fuente: Fuente) -> RotuloPreparado:
    """Valida los valores, calcula ESCALA y REV. y maqueta cada celda. Lanza `RotuloInvalido`."""
    valores = {} if valores is None else valores
    problemas: list[str] = []
    contenidos: list[tuple] = []  # (celda, contenido)
    for clave in sorted(set(valores) - set(definicion.campos)):
        problemas.append(f"rotulo.{clave}: campo no reconocido (campos válidos: "
                         f"{', '.join(definicion.campos)})")

    letras: list[str] = []
    for campo in definicion.campos.values():
        if isinstance(campo, CampoTabla):
            contenidos += _tabla(campo, valores.get(campo.nombre), problemas, letras)

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

    textos, advertencias = [], []
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
    return RotuloPreparado(textos, advertencias, finales)


def ultima_revision(letras: list[str], orden: tuple[str, ...]) -> str:
    """La letra de mayor orden entre las llenas ("" si no hay)."""
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
            "ultima_revision": "la última letra de las revisiones"}[calculado]


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


def _tabla(campo: CampoTabla, valor, problemas: list[str], letras: list[str]) -> list[tuple]:
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
            contenido = _contenido(item[columna], f"{item['__sitio']}.{columna}",
                                   celda.lineas_max, problemas)
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
