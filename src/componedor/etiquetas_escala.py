"""Etiqueta "ESC: 1:N" junto a cada detalle (subfase 4.1).

N sale del manifiesto (scale.denominator, la escala real del PDF), escrito con punto de
miles ("ESC: 1:1.000"). Dónde va:
  1. centrada bajo el DIBUJO del detalle (page_bounds_mm), con sus mayúsculas a
     `SEPARACION_MM` del borde inferior del dibujo;
  2. si ahí no cabe, centrada encima del dibujo, a la misma separación.
Un sitio sirve si la caja completa de la línea (con el ascenso y el descenso de la fuente, como
la mide el lector de PDF) queda dentro de `area_dibujo` y no se monta sobre el
dibujo de otro detalle, un elemento fijo visible (la rosa) ni otra etiqueta. Si no sirve
ninguno, la etiqueta NO se dibuja y se avisa (nunca se pone encima de otra cosa). Un detalle
con "etiqueta_escala": false en el plano no lleva etiqueta.
"""

from dataclasses import dataclass

from componedor.fuente import Fuente
from componedor.maquetacion import Linea, TextoMaquetado
from componedor.texto_escala import texto_escala
from componedor.transformaciones import RectMM

ALTURA_MM = 2.5
SEPARACION_MM = 3.0
EPS_MM = 1e-6
PREFIJO = "ESC: "


@dataclass(frozen=True)
class DetalleParaEtiqueta:
    id: str
    dibujo: RectMM  # mm de papel
    denominador: float  # N de 1:N
    con_etiqueta: bool = True


def texto_etiqueta(denominador: float) -> str:
    return PREFIJO + texto_escala(denominador)


def colocar_etiquetas(detalles: list[DetalleParaEtiqueta], area: RectMM,
                      elementos: list[tuple[str, RectMM]], fuente: Fuente,
                      altura_mm: float = ALTURA_MM,
                      separacion_mm: float = SEPARACION_MM) -> tuple[list[TextoMaquetado], list[str]]:
    """Etiquetas que caben (como textos maquetados) y advertencias de las que no."""
    puestas: list[tuple[str, RectMM]] = []
    textos, avisos = [], []
    for d in detalles:
        if not d.con_etiqueta:
            continue
        texto = texto_etiqueta(d.denominador)
        ancho = fuente.ancho_mm(texto, altura_mm)
        cx = (d.dibujo[0] + d.dibujo[2]) / 2
        x0 = cx - ancho / 2
        sitios = {
            "debajo": d.dibujo[1] - separacion_mm - altura_mm,  # base de la línea
            "encima": d.dibujo[3] + separacion_mm,
        }
        descenso, ascenso = fuente.caja_vertical_mm(altura_mm)
        motivos = {}
        for nombre, base in sitios.items():
            # Caja completa de la línea (con ascenso y descenso de la fuente): es lo que no
            # puede montarse sobre nada y de lo que el texto no puede salirse en el PDF.
            rect = (x0, base - descenso, x0 + ancho, base + ascenso)
            motivo = _motivo(rect, d.id, area, detalles, elementos, puestas)
            if motivo is None:
                puestas.append((f"la etiqueta de '{d.id}'", rect))
                textos.append(TextoMaquetado(f"etiqueta_escala.{d.id}",
                                             (Linea(texto, (x0, base), ancho),), altura_mm,
                                             celda_mm=rect))
                break
            motivos[nombre] = motivo
        else:
            avisos.append(
                f"Advertencia: no se dibujó la etiqueta «{texto}» del detalle '{d.id}': no cabe "
                f"a {separacion_mm:g} mm de su dibujo (debajo: {motivos['debajo']}; encima: "
                f"{motivos['encima']}). Mueva el detalle o ponga \"etiqueta_escala\": false.")
    return textos, avisos


def _motivo(rect: RectMM, propio: str, area: RectMM, detalles: list[DetalleParaEtiqueta],
            elementos: list[tuple[str, RectMM]], puestas: list[tuple[str, RectMM]]) -> str | None:
    if (rect[0] < area[0] - EPS_MM or rect[1] < area[1] - EPS_MM
            or rect[2] > area[2] + EPS_MM or rect[3] > area[3] + EPS_MM):
        return "se sale del área de dibujo"
    for otro in detalles:
        if otro.id != propio and _cruzan(rect, otro.dibujo):
            return f"se monta sobre el dibujo de '{otro.id}'"
    for nombre, r in elementos:
        if _cruzan(rect, r):
            return f"se monta sobre '{nombre}'"
    for nombre, r in puestas:
        if _cruzan(rect, r):
            return f"se monta sobre {nombre}"
    return None


def _cruzan(a: RectMM, b: RectMM) -> bool:
    return (a[0] < b[2] - EPS_MM and b[0] < a[2] - EPS_MM
            and a[1] < b[3] - EPS_MM and b[1] < a[3] - EPS_MM)
