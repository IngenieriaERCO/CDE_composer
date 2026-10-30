"""Carga y validación de la definición de formato de hoja (JSON, en mm, origen inferior izquierdo)."""

import json
import os
from dataclasses import dataclass
from pathlib import Path

RectMM = tuple[float, float, float, float]  # (xmin, ymin, xmax, ymax) en mm

ZONAS_REQUERIDAS = ("area_dibujo", "rotulo", "localizacion", "notas", "convenciones", "cajetin")
ZONAS_DEL_ROTULO = ("localizacion", "notas", "convenciones", "cajetin")
GROSORES_REQUERIDOS = ("marco", "guias")

# Holgura numérica para comparar bordes que coinciden (p. ej. rótulo pegado al marco).
EPS_MM = 1e-6


class FormatoInvalido(ValueError):
    """El archivo de formato no cumple las reglas de geometría."""


class PlantillaNoEncontrada(FormatoInvalido):
    """El formato declara una plantilla cuyo archivo no existe."""


@dataclass(frozen=True)
class Formato:
    nombre: str
    hoja: RectMM
    marco: RectMM
    zonas: dict[str, RectMM]
    grosores_mm: dict[str, float]
    plantilla: Path | None = None  # PDF del rótulo, ruta ya resuelta

    @property
    def ancho_mm(self) -> float:
        return self.hoja[2] - self.hoja[0]

    @property
    def alto_mm(self) -> float:
        return self.hoja[3] - self.hoja[1]


def cargar_formato(ruta: Path | str, usar_plantilla: bool = True) -> Formato:
    """Lee un archivo JSON de formato y lo devuelve validado.

    La ruta de la plantilla, si es relativa, se toma desde la carpeta del JSON.
    Con `usar_plantilla=False` la clave "plantilla" se ignora (no se valida).
    """
    ruta = Path(ruta)
    if not ruta.exists():
        raise FormatoInvalido(f"No se encontró el archivo de formato '{ruta}'.")
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise FormatoInvalido(f"El archivo '{ruta}' no es un JSON válido: {e}") from e
    return validar_formato(datos, base=ruta.parent, usar_plantilla=usar_plantilla)


def validar_formato(datos: dict, base: Path | None = None,
                    usar_plantilla: bool = True) -> Formato:
    """Revisa la geometría del formato y devuelve un `Formato`, o lanza `FormatoInvalido`.

    `base` es la carpeta desde la que se resuelve una ruta relativa de plantilla.
    """
    for clave in ("hoja", "marco", "zonas", "grosores_mm"):
        if clave not in datos:
            raise FormatoInvalido(f"Falta la clave '{clave}' en el formato.")

    hoja = _leer_rect("la hoja", datos["hoja"])
    if hoja[0] != 0 or hoja[1] != 0:
        raise FormatoInvalido(
            f"La hoja debe empezar en el origen (0, 0), esquina inferior izquierda; tiene {hoja[:2]}."
        )
    marco = _leer_rect("el marco", datos["marco"])
    _exigir_dentro("el marco", marco, "la hoja", hoja)

    zonas_json = datos["zonas"]
    faltantes = [z for z in ZONAS_REQUERIDAS if z not in zonas_json]
    if faltantes:
        raise FormatoInvalido(f"Faltan zonas en el formato: {', '.join(faltantes)}.")
    zonas = {nombre: _leer_rect(f"la zona '{nombre}'", valor) for nombre, valor in zonas_json.items()}

    for nombre, rect in zonas.items():
        _exigir_dentro(f"la zona '{nombre}'", rect, "el marco", marco)

    if _se_traslapan(zonas["area_dibujo"], zonas["rotulo"]):
        raise FormatoInvalido(
            f"La zona 'area_dibujo' {zonas['area_dibujo']} se traslapa con la zona 'rotulo' "
            f"{zonas['rotulo']}."
        )

    for nombre in ZONAS_DEL_ROTULO:
        _exigir_dentro(f"la zona '{nombre}'", zonas[nombre], "la zona 'rotulo'", zonas["rotulo"])

    grosores = {}
    for nombre in GROSORES_REQUERIDOS:
        valor = datos["grosores_mm"].get(nombre)
        if not isinstance(valor, (int, float)) or valor <= 0:
            raise FormatoInvalido(
                f"El grosor de línea '{nombre}' debe ser un número positivo en mm; tiene {valor!r}."
            )
        grosores[nombre] = float(valor)

    plantilla = None
    if usar_plantilla and "plantilla" in datos:
        plantilla = _leer_plantilla(datos["plantilla"], base)

    return Formato(
        nombre=str(datos.get("nombre", "sin nombre")),
        hoja=hoja,
        marco=marco,
        zonas=zonas,
        grosores_mm=grosores,
        plantilla=plantilla,
    )


def _leer_plantilla(valor, base: Path | None) -> Path:
    if not isinstance(valor, str) or not valor.strip():
        raise FormatoInvalido(
            f"La plantilla debe ser la ruta de un PDF (texto); tiene {valor!r}."
        )
    ruta = Path(valor)
    if not ruta.is_absolute() and base is not None:
        ruta = Path(os.path.normpath(base / ruta))  # "formatos/../plantillas" -> "plantillas"
    if ruta.suffix.lower() != ".pdf":
        raise FormatoInvalido(f"La plantilla debe ser un archivo .pdf; tiene '{valor}'.")
    if not ruta.is_file():
        raise PlantillaNoEncontrada(
            f"No se encontró la plantilla '{valor}' (buscada en '{ruta.resolve()}'). "
            f"Use --sin-plantilla para generar la hoja sin rótulo."
        )
    return ruta


def _leer_rect(nombre: str, valor) -> RectMM:
    if (
        not isinstance(valor, list)
        or len(valor) != 4
        or not all(isinstance(v, (int, float)) for v in valor)
    ):
        raise FormatoInvalido(
            f"{_mayuscula(nombre)} debe ser una lista de 4 números [xmin, ymin, xmax, ymax] en mm; "
            f"tiene {valor!r}."
        )
    xmin, ymin, xmax, ymax = (float(v) for v in valor)
    if xmax - xmin <= 0 or ymax - ymin <= 0:
        raise FormatoInvalido(
            f"{_mayuscula(nombre)} debe tener ancho y alto positivos (xmax > xmin, ymax > ymin); "
            f"tiene {valor}."
        )
    return xmin, ymin, xmax, ymax


def _exigir_dentro(nombre: str, rect: RectMM, nombre_contenedor: str, contenedor: RectMM) -> None:
    dentro = (
        rect[0] >= contenedor[0] - EPS_MM
        and rect[1] >= contenedor[1] - EPS_MM
        and rect[2] <= contenedor[2] + EPS_MM
        and rect[3] <= contenedor[3] + EPS_MM
    )
    if not dentro:
        raise FormatoInvalido(
            f"{_mayuscula(nombre)} {list(rect)} se sale {_de(nombre_contenedor)} {list(contenedor)}."
        )


def _mayuscula(texto: str) -> str:
    return texto[0].upper() + texto[1:]


def _de(texto: str) -> str:
    """'el marco' -> 'del marco'; 'la hoja' -> 'de la hoja'."""
    return "del " + texto[3:] if texto.startswith("el ") else "de " + texto


def _se_traslapan(a: RectMM, b: RectMM) -> bool:
    """True si comparten área (tocarse en un borde no cuenta como traslape)."""
    return (
        a[0] < b[2] - EPS_MM
        and b[0] < a[2] - EPS_MM
        and a[1] < b[3] - EPS_MM
        and b[1] < a[3] - EPS_MM
    )
