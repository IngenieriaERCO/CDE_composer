"""Maquetación de texto en una celda del rótulo (subfase 4.1).

Python decide dónde va cada línea; el PDF solo recibe "este texto, con esta base, a esta
altura". Reglas:

- La altura es la de las MAYÚSCULAS (`altura_mm`). Entre bases de línea hay
  `interlineado * altura`. El bloque de líneas queda centrado en alto en la celda y cada
  línea alineada a la izquierda, al centro o a la derecha, con `relleno` contra los bordes.
- Un texto (str) en una celda de varias líneas se parte por palabras; una lista son líneas
  explícitas (no se parten). En una celda de una sola línea nunca se parte.
- Si no cabe: se reduce la altura de 0,1 en 0,1 mm hasta `altura_min_mm` (el llamador avisa
  con `reducido_desde`). Si ni así cabe: `TextoNoCabe` con el campo, el texto y las medidas.
  Nunca se recorta ni se reduce en silencio.
"""

from dataclasses import dataclass

from componedor.fuente import Fuente
from componedor.rotulo_formato import Celda

PASO_REDUCCION_MM = 0.1
EPS_MM = 1e-6


class TextoNoCabe(ValueError):
    """El texto no cabe en su celda ni a la altura mínima permitida."""


@dataclass(frozen=True)
class Linea:
    texto: str
    base_mm: tuple[float, float]  # inicio de la línea base (mm de papel, Y arriba)
    ancho_mm: float


@dataclass(frozen=True)
class TextoMaquetado:
    ruta: str  # campo o celda ("titulo", "revisiones.A.fecha", "etiqueta_escala.a")
    lineas: tuple[Linea, ...]
    altura_mm: float
    reducido_desde: float | None = None  # altura pedida si hubo que reducir
    # Rectángulo (mm de papel) del que ninguna línea puede salirse: la celda del rótulo o, en
    # una etiqueta ESC, la caja reservada. Lo comprueba textos_pdf.verificar_textos en el PDF.
    celda_mm: tuple[float, float, float, float] | None = None

    def rect(self) -> tuple[float, float, float, float]:
        """Caja de las mayúsculas de todas las líneas (mm de papel)."""
        return (min(l.base_mm[0] for l in self.lineas),
                min(l.base_mm[1] for l in self.lineas),
                max(l.base_mm[0] + l.ancho_mm for l in self.lineas),
                max(l.base_mm[1] for l in self.lineas) + self.altura_mm)


def maquetar(celda: Celda, contenido: str | list[str], fuente: Fuente, relleno_mm: float,
             interlineado: float) -> TextoMaquetado:
    """Acomoda `contenido` en `celda`. Lanza `TextoNoCabe` si no cabe a la altura mínima."""
    explicitas = isinstance(contenido, list)
    parrafos = [p.strip() for p in (contenido if explicitas else str(contenido).split("\n"))]
    if not any(parrafos):
        return TextoMaquetado(celda.ruta, (), celda.altura_mm, celda_mm=celda.rect)

    ancho_util = celda.rect[2] - celda.rect[0] - 2 * relleno_mm
    alto_util = celda.rect[3] - celda.rect[1] - 2 * relleno_mm
    partir = not explicitas and celda.lineas_max > 1
    problema = ""
    for altura in alturas_a_probar(celda):
        lineas = partir_en_lineas(parrafos, ancho_util, altura, fuente) if partir else parrafos
        problema = _problema(celda, contenido, lineas, altura, ancho_util, alto_util, fuente,
                             interlineado)
        if not problema:
            return TextoMaquetado(
                celda.ruta, _colocar(celda, lineas, altura, fuente, relleno_mm, interlineado),
                altura, celda.altura_mm if altura < celda.altura_mm - EPS_MM else None,
                celda.rect)
    raise TextoNoCabe(problema)


def alturas_a_probar(celda: Celda) -> list[float]:
    """altura, altura - 0,1, ..., altura_min (redondeadas a 0,01 mm)."""
    pasos = int(round((celda.altura_mm - celda.altura_min_mm) / PASO_REDUCCION_MM))
    alturas = [round(celda.altura_mm - i * PASO_REDUCCION_MM, 2) for i in range(pasos + 1)]
    alturas[-1] = celda.altura_min_mm
    return alturas


def partir_en_lineas(parrafos: list[str], ancho: float, altura: float,
                     fuente: Fuente) -> list[str]:
    """Corta cada párrafo por palabras para que cada línea mida a lo sumo `ancho`. Una
    palabra más ancha que la celda queda sola en su línea (y luego se informa)."""
    lineas = []
    for parrafo in parrafos:
        actual = ""
        for palabra in parrafo.split():
            candidata = f"{actual} {palabra}" if actual else palabra
            if actual and fuente.ancho_mm(candidata, altura) > ancho + EPS_MM:
                lineas.append(actual)
                actual = palabra
            else:
                actual = candidata
        lineas.append(actual)
    return lineas


def _problema(celda: Celda, contenido, lineas: list[str], altura: float, ancho_util: float,
              alto_util: float, fuente: Fuente, interlineado: float) -> str:
    """Por qué no cabe a esta altura ("" si cabe)."""
    campo = f"campo '{celda.ruta}'"
    medida = f"altura {_mm(altura)} mm" + (", la mínima permitida"
                                            if celda.altura_min_mm < celda.altura_mm else "")
    if len(lineas) > celda.lineas_max:
        texto = " ".join(lineas) if not isinstance(contenido, list) else " | ".join(lineas)
        return (f"{campo}: «{texto}» necesita {len(lineas)} líneas de hasta "
                f"{_mm(ancho_util)} mm y la celda permite {celda.lineas_max} ({medida})")
    for i, linea in enumerate(lineas, start=1):
        ancho = fuente.ancho_mm(linea, altura)
        if ancho > ancho_util + EPS_MM:
            donde = f", línea {i}" if len(lineas) > 1 else ""
            return (f"{campo}{donde}: «{linea}» mide {_mm(ancho)} mm y la celda permite "
                    f"{_mm(ancho_util)} mm ({medida})")
    bloque = altura + (len(lineas) - 1) * interlineado * altura
    if bloque > alto_util + EPS_MM:
        return (f"{campo}: {len(lineas)} líneas ocupan {_mm(bloque)} mm de alto y la celda "
                f"permite {_mm(alto_util)} mm ({medida})")
    return ""


def _colocar(celda: Celda, lineas: list[str], altura: float, fuente: Fuente, relleno: float,
             interlineado: float) -> tuple[Linea, ...]:
    x0, y0, x1, y1 = celda.rect
    paso = interlineado * altura
    bloque = altura + (len(lineas) - 1) * paso
    arriba = (y0 + y1) / 2 + bloque / 2  # tope de las mayúsculas de la primera línea
    colocadas = []
    for i, texto in enumerate(lineas):
        ancho = fuente.ancho_mm(texto, altura)
        if celda.alinear == "izq":
            x = x0 + relleno
        elif celda.alinear == "der":
            x = x1 - relleno - ancho
        else:
            x = (x0 + x1) / 2 - ancho / 2
        colocadas.append(Linea(texto, (x, arriba - altura - i * paso), ancho))
    return tuple(colocadas)


def _mm(valor: float) -> str:
    return f"{valor:.1f}"
