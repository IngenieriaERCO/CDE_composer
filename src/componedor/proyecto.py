"""proyecto.json: los datos del rótulo que se repiten en todos los planos de un proyecto
(subfase 4.3b). Esquema en docs/formato_proyecto.md.

    {
      "version": 1,
      "nombre": "PARQUE SOLAR …",              (opcional, informativo: no va al rótulo)
      "disenador": "INGENIERÍA DE DISEÑO S.A.S.",
      "revisor": "INTERVENTORÍA …",
      "prefijo_no_plano": "ERCO-PSF-CIV-PL-",
      "firmas": {"dibujo": {"nombre": "…", "matricula": "…"}, "reviso": {…}, …}
    }

Todo es opcional salvo "version". `editor --proyecto` lo valida aquí contra el formato y lo
incrusta en editor.html: el editor PRELLENA con él el rótulo de un plano NUEVO (al guardar,
los valores quedan COPIADOS en el plano.json; `componer` no lee proyecto.json). Un plano que
se abre no se toca. Los textos siguen las reglas de los valores del rótulo (`rotulo.py`):
texto o entero; lista de líneas solo en celdas de varias líneas; sin saltos de línea en una
celda de una sola línea. Todos los problemas en un solo error.

"disenador" y "revisor" ya no están en el rótulo A1 ERCO (`campos_retirados` del formato): un
proyecto.json viejo que los traiga sigue valiendo; se ignoran y `editor --proyecto` avisa una vez.
"""

import json
from pathlib import Path

from componedor.rotulo import _contenido, _tipo
from componedor.rotulo_formato import CampoTabla, CampoTexto, DefinicionRotulo

VERSION = 1
CLAVES = ("version", "nombre", "disenador", "revisor", "prefijo_no_plano", "firmas")
CAMPOS_TEXTO = ("disenador", "revisor")
CAMPO_NO_PLANO = "no_plano"
TABLA_FIRMAS = "firmas"
COLUMNAS_FIRMAS = ("nombre", "matricula")


class ProyectoInvalido(ValueError):
    """proyecto.json no es válido (el mensaje lista todos los problemas)."""

    def __init__(self, origen: str, problemas: list[str]):
        self.problemas = problemas
        n = len(problemas)
        super().__init__(f"El proyecto '{origen}' tiene {n} "
                         f"{'problema' if n == 1 else 'problemas'}:\n"
                         + "\n".join(f"- {p}" for p in problemas))


def leer_proyecto(ruta: Path | str, definicion: DefinicionRotulo | None) -> dict:
    """Lee y valida proyecto.json. Devuelve sus datos tal como vienen (ya validados)."""
    ruta = Path(ruta)
    if not ruta.is_file():
        raise ProyectoInvalido(str(ruta), ["no se encontró el archivo"])
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except UnicodeDecodeError:
        raise ProyectoInvalido(str(ruta), ["el archivo no está en UTF-8"]) from None
    except json.JSONDecodeError as e:
        raise ProyectoInvalido(str(ruta), [f"no es un JSON válido (línea {e.lineno}, columna "
                                           f"{e.colno}: {e.msg})"]) from None
    validar_proyecto(datos, definicion, str(ruta))
    return datos


def validar_proyecto(datos, definicion: DefinicionRotulo | None, origen: str = "proyecto.json") -> None:
    """Lanza `ProyectoInvalido` con todos los problemas."""
    if not isinstance(datos, dict):
        raise ProyectoInvalido(origen, [f"se esperaba un objeto {{...}}; tiene {_tipo(datos)}"])
    problemas: list[str] = []
    if "version" not in datos:
        problemas.append(f"proyecto.version: falta (use \"version\": {VERSION})")
    elif datos["version"] != VERSION or isinstance(datos["version"], bool):
        problemas.append(f"proyecto.version: versión {datos['version']!r} no soportada (se "
                         f"entiende la {VERSION})")
    for clave in sorted(set(datos) - set(CLAVES)):
        problemas.append(f"proyecto.{clave}: campo no reconocido (campos válidos: "
                         f"{', '.join(CLAVES)})")
    if "nombre" in datos and not isinstance(datos["nombre"], str):
        problemas.append(f"proyecto.nombre: se esperaba un texto; tiene {_tipo(datos['nombre'])}")
    campos = definicion.campos if definicion is not None else {}
    if definicion is None and set(datos) & {"disenador", "revisor", "prefijo_no_plano", "firmas"}:
        problemas.append("el formato no tiene sección \"rotulo\": el proyecto no se puede usar")
        raise ProyectoInvalido(origen, problemas)

    retirados = definicion.campos_retirados if definicion is not None else ()
    for nombre in CAMPOS_TEXTO:
        if nombre in datos and nombre not in retirados:  # retirados: se ignoran (aviso al usarlo)
            _texto(datos[nombre], nombre, campos, problemas)
    if "prefijo_no_plano" in datos:
        campo = campos.get(CAMPO_NO_PLANO)
        if not isinstance(campo, CampoTexto):
            problemas.append("proyecto.prefijo_no_plano: el formato no tiene el campo "
                             f"'{CAMPO_NO_PLANO}'")
        elif not isinstance(datos["prefijo_no_plano"], str):
            problemas.append(f"proyecto.prefijo_no_plano: se esperaba un texto; tiene "
                             f"{_tipo(datos['prefijo_no_plano'])}")
        elif "\n" in datos["prefijo_no_plano"]:
            problemas.append("proyecto.prefijo_no_plano: la celda es de una sola línea y el "
                             "texto trae un salto de línea")
    if "firmas" in datos:
        _firmas(datos["firmas"], campos.get(TABLA_FIRMAS), problemas)
    if problemas:
        raise ProyectoInvalido(origen, problemas)


def _texto(valor, nombre: str, campos: dict, problemas: list[str]) -> None:
    campo = campos.get(nombre)
    if not isinstance(campo, CampoTexto) or campo.calculado:
        problemas.append(f"proyecto.{nombre}: el formato no tiene un campo de texto '{nombre}'")
        return
    _contenido(valor, f"proyecto.{nombre}", campo.celda.lineas_max, problemas)


def _firmas(valor, tabla, problemas: list[str]) -> None:
    if not isinstance(tabla, CampoTabla) or tabla.columna_clave is not None:
        problemas.append(f"proyecto.firmas: el formato no tiene la tabla '{TABLA_FIRMAS}'")
        return
    if not isinstance(valor, dict):
        problemas.append(f"proyecto.firmas: se esperaba un objeto con las filas "
                         f"({', '.join(tabla.filas)}); tiene {_tipo(valor)}")
        return
    for fila in sorted(set(valor) - set(tabla.filas)):
        problemas.append(f"proyecto.firmas.{fila}: fila no reconocida (filas válidas: "
                         f"{', '.join(tabla.filas)})")
    validas = [c for c in COLUMNAS_FIRMAS if c in tabla.columnas]
    for fila in tabla.filas:
        if fila not in valor:
            continue
        item = valor[fila]
        sitio = f"proyecto.firmas.{fila}"
        if not isinstance(item, dict):
            problemas.append(f"{sitio}: se esperaba un objeto con {', '.join(validas)}; tiene "
                             f"{_tipo(item)}")
            continue
        for clave in sorted(set(item) - set(validas)):
            problemas.append(f"{sitio}.{clave}: campo no reconocido (el proyecto solo prellena "
                             f"{', '.join(validas)})")
        for columna in validas:
            if columna in item:
                _contenido(item[columna], f"{sitio}.{columna}",
                           tabla.celdas[(fila, columna)].lineas_max, problemas)
