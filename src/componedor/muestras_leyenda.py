"""Muestras de LÍNEA y RELLENO en las convenciones del rótulo (subfase 9a).

Además de los símbolos de la biblioteca (simbolos.py), un renglón de la leyenda puede ser una
muestra que dibuja el propio Componedor, como VECTOR, centrada en la casilla del símbolo:

    {"tipo": "linea", "descripcion": "RED DE MEDIA TENSIÓN", "color": "#FF0000",
     "grosor_mm": 0.35, "trazo": "discontinua"}
    {"tipo": "relleno", "descripcion": "ZONA VERDE", "color": "#00A000", "opacidad": 0.5}

- `tipo`: "simbolo" (lo de siempre; un renglón sin `tipo` es un símbolo), "linea" o "relleno".
- `descripcion`: obligatoria (una muestra no tiene descripción por defecto).
- `color`: "#RRGGBB" (por defecto negro en la línea y gris en el relleno).
- Línea: `grosor_mm` de 0,05 a 2 (por defecto 0,25) y `trazo` "continua" o "discontinua"
  (guiones de 2 mm con huecos de 1 mm). Se dibuja horizontal, de 13 mm de largo.
- Relleno: `opacidad` mayor que 0 y hasta 1 (por defecto 1). Rectángulo de 13 x 6 mm, sin borde.
Si la casilla es más chica, la muestra se acorta al espacio útil (casilla menos el relleno).

Al componer se verifica en el PDF: un solo trazo en la casilla, en su sitio (±0,1 mm), con su
color, su grosor (±0,01 mm), su trazo y su opacidad.
"""

import re
from dataclasses import dataclass

import pymupdf

from componedor.formato import RectMM
from componedor.transformaciones import (
    punto_papel_a_pdf,
    rect_papel_a_pdf,
    rect_pdf_a_papel,
)
from componedor.unidades import PT_POR_MM

TIPO_SIMBOLO = "simbolo"
TIPO_LINEA = "linea"
TIPO_RELLENO = "relleno"
TIPOS = (TIPO_SIMBOLO, TIPO_LINEA, TIPO_RELLENO)
TRAZOS = ("continua", "discontinua")
CLAVES = {
    TIPO_SIMBOLO: ("descripcion", "simbolo", "tipo"),
    TIPO_LINEA: ("color", "descripcion", "grosor_mm", "tipo", "trazo"),
    TIPO_RELLENO: ("color", "descripcion", "opacidad", "tipo"),
}
COLOR_LINEA = "#000000"
COLOR_RELLENO = "#808080"
GROSOR_MM = 0.25
GROSOR_MIN_MM, GROSOR_MAX_MM = 0.05, 2.0
LARGO_LINEA_MM = 13.0
TAMANO_RELLENO_MM = (13.0, 6.0)
GUION_MM = (2.0, 1.0)  # discontinua: guion y hueco
TOL_MM = 0.1
TOL_GROSOR_MM = 0.01
TOL_COLOR = 0.01  # en 0..1 (1/255 = 0,004)
_HEX = re.compile(r"#[0-9A-Fa-f]{6}")


@dataclass(frozen=True)
class Muestra:
    tipo: str  # "linea" o "relleno"
    color: str  # "#RRGGBB"
    grosor_mm: float = GROSOR_MM  # solo línea
    trazo: str = "continua"  # solo línea
    opacidad: float = 1.0  # solo relleno

    @property
    def rgb(self) -> tuple[float, float, float]:
        return tuple(int(self.color[k:k + 2], 16) / 255 for k in (1, 3, 5))


@dataclass(frozen=True)
class ColocacionMuestra:
    muestra: Muestra
    posicion: int  # 1..24: casilla de la convención en el rótulo
    casilla: RectMM
    dibujo: RectMM  # mm de papel; en la línea, y0 = y1 (el eje de la línea)


def tipo_de(item: dict):
    """El tipo de un renglón de convenciones: sin `tipo`, "simbolo"."""
    return item.get("tipo", TIPO_SIMBOLO)


def leer_muestra(item: dict, sitio: str, problemas: list[str], tipo_valor) -> Muestra | None:
    """La muestra de un renglón "linea" o "relleno" (sin la descripción). None si hay problemas
    (quedan anotados). `tipo_valor`: cómo se nombra un valor en los mensajes (rotulo._tipo)."""
    tipo = item["tipo"]
    antes = len(problemas)
    color = item.get("color", COLOR_LINEA if tipo == TIPO_LINEA else COLOR_RELLENO)
    if not isinstance(color, str) or not _HEX.fullmatch(color):
        problemas.append(f"{sitio}.color: se esperaba un color «#RRGGBB» (p. ej. «#FF0000» = "
                         f"rojo); tiene {tipo_valor(color)}")
    if tipo == TIPO_LINEA:
        grosor = item.get("grosor_mm", GROSOR_MM)
        if not _numero(grosor) or not GROSOR_MIN_MM <= grosor <= GROSOR_MAX_MM:
            problemas.append(f"{sitio}.grosor_mm: se esperaba un número de {GROSOR_MIN_MM:g} a "
                             f"{GROSOR_MAX_MM:g} mm; tiene {tipo_valor(grosor)}")
        trazo = item.get("trazo", TRAZOS[0])
        if trazo not in TRAZOS:
            problemas.append(f"{sitio}.trazo: se esperaba «continua» o «discontinua»; tiene "
                             f"{tipo_valor(trazo)}")
        if len(problemas) > antes:
            return None
        return Muestra(TIPO_LINEA, color.upper(), float(grosor), trazo)
    opacidad = item.get("opacidad", 1)
    if not _numero(opacidad) or not 0 < opacidad <= 1:
        problemas.append(f"{sitio}.opacidad: se esperaba un número mayor que 0 y hasta 1 (1 = "
                         f"opaco); tiene {tipo_valor(opacidad)}")
    if len(problemas) > antes:
        return None
    return Muestra(TIPO_RELLENO, color.upper(), opacidad=float(opacidad))


def colocar_muestra(muestra: Muestra, posicion: int, casilla: RectMM,
                    relleno_mm: float) -> ColocacionMuestra:
    """Centrada en la casilla; más corta si el espacio útil no alcanza."""
    util_x = casilla[2] - casilla[0] - 2 * relleno_mm
    util_y = casilla[3] - casilla[1] - 2 * relleno_mm
    cx, cy = (casilla[0] + casilla[2]) / 2, (casilla[1] + casilla[3]) / 2
    if muestra.tipo == TIPO_LINEA:
        mitad = min(LARGO_LINEA_MM, util_x) / 2
        dibujo = (cx - mitad, cy, cx + mitad, cy)
    else:
        ancho = min(TAMANO_RELLENO_MM[0], util_x) / 2
        alto = min(TAMANO_RELLENO_MM[1], util_y) / 2
        dibujo = (cx - ancho, cy - alto, cx + ancho, cy + alto)
    return ColocacionMuestra(muestra, posicion, casilla, dibujo)


def dibujar_muestras(page: pymupdf.Page, colocaciones: list[ColocacionMuestra],
                     alto_hoja_mm: float) -> None:
    """Cada muestra como un solo trazo vectorial (línea o rectángulo relleno)."""
    for c in colocaciones:
        m = c.muestra
        if m.tipo == TIPO_LINEA:
            x0, y, x1, _ = c.dibujo
            guiones = (f"[{GUION_MM[0] * PT_POR_MM:g} {GUION_MM[1] * PT_POR_MM:g}] 0"
                       if m.trazo == "discontinua" else None)
            page.draw_line(punto_papel_a_pdf(x0, y, alto_hoja_mm),
                           punto_papel_a_pdf(x1, y, alto_hoja_mm), color=m.rgb,
                           width=m.grosor_mm * PT_POR_MM, dashes=guiones)
        else:
            page.draw_rect(rect_papel_a_pdf(c.dibujo, alto_hoja_mm), color=None, fill=m.rgb,
                           fill_opacity=m.opacidad, width=0)


def verificar_muestras(page: pymupdf.Page, colocaciones: list[ColocacionMuestra],
                       alto_hoja_mm: float) -> list[str]:
    """En el PDF: un trazo por casilla, en su sitio, con su color, grosor, trazo y opacidad."""
    if not colocaciones:
        return []
    trazos = [(rect_pdf_a_papel(d["rect"], alto_hoja_mm), d) for d in page.get_drawings()]
    problemas = []
    for c in colocaciones:
        m = c.muestra
        nombre = "línea" if m.tipo == TIPO_LINEA else "relleno"
        donde = f"convenciones, casilla {c.posicion} ({nombre})"
        mios = [(r, d) for r, d in trazos if _dentro(r, c.casilla)]
        if len(mios) != 1:
            problemas.append(f"{donde}: en la casilla hay {len(mios)} trazos y la muestra es 1")
            continue
        caja, d = mios[0]
        dif = max(abs(a - b) for a, b in zip(caja, c.dibujo))
        if dif > TOL_MM:
            problemas.append(f"{donde}: la muestra quedó en {_mm(caja)} y debía quedar en "
                             f"{_mm(c.dibujo)} (diferencia máx. {dif:.3f} mm, tolerancia "
                             f"±{TOL_MM} mm)")
        if m.tipo == TIPO_LINEA:
            color, grosor = d.get("color"), (d.get("width") or 0) / PT_POR_MM
            if abs(grosor - m.grosor_mm) > TOL_GROSOR_MM:
                problemas.append(f"{donde}: el grosor es {grosor:.3f} mm y debía ser "
                                 f"{m.grosor_mm:g} mm")
            guiones = (d.get("dashes") or "[] 0").replace(" ", "")
            if (guiones != "[]0") != (m.trazo == "discontinua"):
                problemas.append(f"{donde}: el trazo debía ser {m.trazo} y en el PDF es "
                                 f"{'discontinuo' if guiones != '[]0' else 'continuo'}")
        else:
            color = d.get("fill")
            opacidad = d.get("fill_opacity")
            opacidad = 1.0 if opacidad is None else opacidad
            if abs(opacidad - m.opacidad) > TOL_COLOR:
                problemas.append(f"{donde}: la opacidad es {opacidad:g} y debía ser "
                                 f"{m.opacidad:g}")
        if color is None or max(abs(a - b) for a, b in zip(color, m.rgb)) > TOL_COLOR:
            problemas.append(f"{donde}: el color en el PDF no es {m.color}")
    return problemas


def _numero(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _dentro(r: RectMM, c: RectMM) -> bool:
    return (r[0] >= c[0] - TOL_MM and r[1] >= c[1] - TOL_MM and r[2] <= c[2] + TOL_MM
            and r[3] <= c[3] + TOL_MM)


def _mm(r: RectMM) -> str:
    return f"X {r[0]:.2f}–{r[2]:.2f}, Y {r[1]:.2f}–{r[3]:.2f} mm"
