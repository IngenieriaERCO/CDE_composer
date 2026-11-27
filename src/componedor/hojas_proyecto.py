"""Las hojas de un proyecto: un plano.json por hoja y un índice `<proyecto>.hojas.json`.

    {"version": 1, "hojas": ["Pruebadecambio.json", "Pruebadecambio_02.json"]}

El índice va en la misma carpeta que sus hojas (la del editor) y las nombra en orden, solo por
nombre de archivo. Con él, los campos «automáticos» del rótulo (formato → "automatico") se
llenan solos si la hoja no los escribe:

- "hoja_actual": la posición de la hoja en el índice (1, 2, …);
- "total_hojas": cuántas hojas tiene el índice;
- "numero_siguiente": el número de plano de la hoja anterior con su último número sumado en 1
  (…-PL-106 → …-PL-107, con los mismos ceros a la izquierda). La primera hoja lo escribe a
  mano; si una hoja intermedia lo escribe, las siguientes siguen desde ese.

Lo escrito a mano siempre manda. Una hoja que no está en ningún índice no tiene automáticos
(se compone como siempre).
"""

import json
import re
from pathlib import Path

SUFIJO = ".hojas.json"
VERSION = 1
AUTOMATICOS = ("hoja_actual", "total_hojas", "numero_siguiente")
_NOMBRE = re.compile(r"^[^\\/:*?\"<>|]+\.json$", re.IGNORECASE)
_ULTIMO_NUMERO = re.compile(r"(\d+)(?!.*\d)")


class IndiceInvalido(ValueError):
    """El índice de hojas no se puede usar (mensaje en español)."""


def nombre_valido(nombre) -> bool:
    """Un nombre de archivo .json sin carpetas (ni «..»)."""
    return (isinstance(nombre, str) and bool(_NOMBRE.match(nombre)) and nombre.strip() == nombre
            and ".." not in nombre and not nombre.lower().endswith(SUFIJO))


def leer_indice(ruta: Path | str) -> list[str]:
    """Las hojas del índice, en orden. Lanza `IndiceInvalido`."""
    ruta = Path(ruta)
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        raise IndiceInvalido(f"No se pudo leer el índice de hojas '{ruta.name}': {e}") from None
    if not isinstance(datos, dict) or datos.get("version") != VERSION:
        raise IndiceInvalido(f"'{ruta.name}': se esperaba {{\"version\": 1, \"hojas\": [...]}}.")
    hojas = datos.get("hojas")
    if not (isinstance(hojas, list) and hojas and all(nombre_valido(h) for h in hojas)):
        raise IndiceInvalido(f"'{ruta.name}': «hojas» debe ser una lista de nombres de plano.json "
                             f"(sin carpetas).")
    if len({h.casefold() for h in hojas}) != len(hojas):
        raise IndiceInvalido(f"'{ruta.name}': una hoja está repetida.")
    return list(hojas)


def escribir_indice(carpeta: Path | str, nombre: str, hojas: list[str]) -> Path:
    """Escribe `<nombre>.hojas.json` en `carpeta` (lo reemplaza si existe)."""
    if not (isinstance(nombre, str) and nombre and re.fullmatch(r"[^\\/:*?\"<>|.][^\\/:*?\"<>|]*",
                                                                   nombre)):
        raise IndiceInvalido(f"Nombre de índice no válido: {nombre!r}.")
    if not (hojas and all(nombre_valido(h) for h in hojas)):
        raise IndiceInvalido("Las hojas del índice son nombres de plano.json sin carpetas.")
    if len({h.casefold() for h in hojas}) != len(hojas):
        raise IndiceInvalido("Una hoja está repetida en el índice.")
    ruta = Path(carpeta) / f"{nombre}{SUFIJO}"
    ruta.write_text(json.dumps({"version": VERSION, "hojas": hojas}, ensure_ascii=False, indent=2)
                    + "\n", encoding="utf-8", newline="\n")
    return ruta


def indice_de(plano: Path | str) -> tuple[Path, list[str]] | None:
    """El índice (de la carpeta del plano) que nombra a este plano, y sus hojas; None si
    ninguno. Un índice que no se puede leer se salta."""
    plano = Path(plano)
    for ruta in sorted(plano.parent.glob(f"*{SUFIJO}")):
        try:
            hojas = leer_indice(ruta)
        except IndiceInvalido:
            continue
        if plano.name.casefold() in (h.casefold() for h in hojas):
            return ruta, hojas
    return None


def siguiente_numero(numero: str) -> str | None:
    """El número con su último grupo de cifras sumado en 1, con los mismos ceros
    (…-PL-106 → …-PL-107; «A-009» → «A-010»). None si no tiene cifras."""
    if not isinstance(numero, str):
        return None
    m = _ULTIMO_NUMERO.search(numero)
    if not m:
        return None
    cifras = m.group(1)
    return numero[:m.start()] + str(int(cifras) + 1).zfill(len(cifras)) + numero[m.end():]


def _escrito(valor) -> str | None:
    """Lo escrito a mano (texto no vacío, o un número como «"hoja": 1»); None si nada."""
    if isinstance(valor, bool) or valor is None:
        return None
    if isinstance(valor, (int, float)):
        return str(valor)
    return valor.strip() if isinstance(valor, str) and valor.strip() else None


def _rotulo_de(ruta: Path) -> dict:
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    rotulo = datos.get("rotulo") if isinstance(datos, dict) else None
    return rotulo if isinstance(rotulo, dict) else {}


def valores_automaticos(plano: Path | str, campos: dict[str, str],
                        rotulo_actual: dict | None = None) -> dict[str, str]:
    """{campo: valor} de los campos automáticos que el plano NO escribe. `campos`: {nombre del
    campo: "hoja_actual" | "total_hojas" | "numero_siguiente"} (del formato). `rotulo_actual`:
    el rótulo de este plano tal como está (el editor lo pasa sin guardar); None: el del archivo."""
    plano = Path(plano)
    encontrado = indice_de(plano)
    if encontrado is None or not campos:
        return {}
    _, hojas = encontrado
    posicion = [h.casefold() for h in hojas].index(plano.name.casefold())
    rotulos = [_rotulo_de(plano.parent / h) for h in hojas]
    return automaticos_de_lista(rotulos, posicion, campos, rotulo_actual)


def automaticos_de_lista(rotulos: list[dict], posicion: int, campos: dict[str, str],
                         rotulo_actual: dict | None = None) -> dict[str, str]:
    """Lo mismo, a partir de los rótulos de todas las hojas en orden (un proyecto de varias
    hojas en un solo archivo, versión 8) y la posición de esta (0, 1, …)."""
    actual = rotulo_actual if rotulo_actual is not None else (rotulos[posicion] or {})
    salida: dict[str, str] = {}
    for campo, tipo in campos.items():
        if _escrito(actual.get(campo)) is not None:
            continue  # escrito a mano: manda
        if tipo == "hoja_actual":
            salida[campo] = str(posicion + 1)
        elif tipo == "total_hojas":
            salida[campo] = str(len(rotulos))
        elif tipo == "numero_siguiente":
            numero = _numero_anterior(rotulos, posicion, campo)
            if numero is not None:
                salida[campo] = numero
    return salida


def _numero_anterior(rotulos: list[dict], posicion: int, campo: str) -> str | None:
    """El número de la hoja `posicion`, siguiendo desde la última hoja anterior que lo escribe."""
    for pasos, i in enumerate(range(posicion - 1, -1, -1), start=1):
        escrito = _escrito((rotulos[i] or {}).get(campo))
        if escrito is not None:
            numero = escrito
            for _ in range(pasos):
                numero = siguiente_numero(numero)
                if numero is None:
                    return None
            return numero
    return None
