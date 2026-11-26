"""Inventario de los detalles de una carpeta: qué hay, qué se acepta y qué cabe en la hoja.

Cada paquete pasa por la misma evaluación que el importador (`importador.evaluar_paquete`):
aceptado o rechazado con los mismos motivos. Si se da un formato, se mira si la PÁGINA del
detalle cabe en la zona con la misma regla que `colocar` (`colocar.exceso_de_tamano`). Un
detalle que no cabe NO se rechaza: queda aceptado con una nota y, si se conoce el margen,
una escala sugerida (aproximada) de la lista estándar.
"""

from dataclasses import dataclass, field
from pathlib import Path

from componedor.colocar import exceso_de_tamano
from componedor.formato import Formato
from componedor.importador import evaluar_paquete, texto_motivo
from componedor.paquete import localizar_paquetes
from componedor.recorte_detalle import (
    MARGEN_POR_DEFECTO_MM,
    recorte_pagina,
    tamano_visible,
)

ACEPTADO, RECHAZADO = "aceptado", "rechazado"
# Escalas normalizadas de ingeniería, de mayor a menor detalle. La sugerida es la PRIMERA con la
# que la página cabe (la más grande posible). Igual que ESCALAS en editor/editor_bloques.js.
ESCALAS_ESTANDAR = (5, 10, 20, 25, 50, 75, 100, 200, 250, 500, 750, 1000, 1500, 2000, 2500,
                    3000, 4000, 5000, 7500, 10000)
ESCALA_MAXIMA = 100000  # una escala escrita a mano: entero de 1 a este valor


def es_normalizada(n: float) -> bool:
    return n in ESCALAS_ESTANDAR


@dataclass
class EntradaInventario:
    prefijo: str
    carpeta: Path
    bloque: str | None
    escala: float | None  # el N de 1:N
    tamano_pagina_mm: tuple[float, float] | None
    tamano_dibujo_mm: tuple[float, float] | None  # de page_bounds_mm
    estado: str  # aceptado o rechazado
    motivos: list[str] = field(default_factory=list)  # «[categoría] texto», como el importador
    cabe: bool | None = None  # None: sin formato o sin tamaño de página
    notas: list[str] = field(default_factory=list)
    sha256: str | None = None
    ruta_pdf: Path | None = None
    ruta_manifiesto: Path | None = None
    limites_pagina_mm: tuple[float, float, float, float] | None = None  # page_bounds_mm, Y abajo
    # cad_to_page [a, b, c, d, e, f] y mm reales por unidad CAD: para ubicar la ortofoto.
    cad_a_pagina: tuple[float, float, float, float, float, float] | None = None
    mm_por_unidad: float | None = None


def _matriz(m) -> tuple[float, ...] | None:
    if m is None:
        return None
    k = m.pdf.dibujo.matriz
    return (k.a, k.b, k.c, k.d, k.e, k.f)


def construir_inventario(carpeta: Path | str, formato: Formato | None = None,
                         zona: str = "area_dibujo", recursivo: bool = False,
                         margen_hoja_mm: float = MARGEN_POR_DEFECTO_MM,
                         ) -> list[EntradaInventario]:
    """Una entrada por paquete de `carpeta` (en el orden de `localizar_paquetes`).
    `margen_hoja_mm`: lo que «cabe» es el dibujo más este margen (la página se recorta al
    componer, recorte_detalle.py), no la página con el margen de la exportación."""
    carpeta = Path(carpeta)
    rect_zona = None
    if formato is not None:
        if zona not in formato.zonas:
            raise ValueError(f"La zona '{zona}' no existe en el formato. Zonas disponibles: "
                             f"{', '.join(formato.zonas)}.")
        rect_zona = formato.zonas[zona]

    entradas = []
    vistos: dict[str, EntradaInventario] = {}  # sha256 -> primera entrada con ese hash
    for paquete in localizar_paquetes(carpeta, recursivo):
        evaluacion = evaluar_paquete(paquete)
        m = paquete.manifiesto
        entrada = EntradaInventario(
            prefijo=paquete.prefijo,
            carpeta=paquete.carpeta,
            bloque=m.bloque if m else None,
            escala=m.escala.denominador if m else None,
            tamano_pagina_mm=m.pdf.tamano_pagina_mm if m else None,
            tamano_dibujo_mm=_tamano_dibujo(m) if m else None,
            estado=ACEPTADO if evaluacion.aceptado else RECHAZADO,
            motivos=[texto_motivo(motivo) for motivo in evaluacion.motivos],
            sha256=m.pdf.sha256 if m else None,
            ruta_pdf=paquete.ruta_pdf,
            ruta_manifiesto=paquete.ruta_manifiesto,
            limites_pagina_mm=m.pdf.dibujo.limites_pagina_mm if m else None,
            cad_a_pagina=_matriz(m),
            mm_por_unidad=m.unidades.milimetros_por_unidad if m else None,
        )
        if rect_zona is not None and m is not None:
            _evaluar_cabida(entrada, m, zona, rect_zona, margen_hoja_mm)
        if entrada.sha256 is not None:
            if entrada.sha256 in vistos:
                original = vistos[entrada.sha256]
                entrada.notas.append(f"duplicado de {_ruta_relativa(original, carpeta)}")
            else:
                vistos[entrada.sha256] = entrada
        entradas.append(entrada)
    return entradas


def _tamano_dibujo(m) -> tuple[float, float]:
    x0, y0, x1, y1 = m.pdf.dibujo.limites_pagina_mm
    return x1 - x0, y1 - y0


def _evaluar_cabida(entrada: EntradaInventario, m, zona: str, rect_zona,
                    margen_hoja_mm: float = MARGEN_POR_DEFECTO_MM) -> None:
    recorte = recorte_pagina(m.pdf.tamano_pagina_mm, m.pdf.dibujo.limites_pagina_mm,
                             margen_hoja_mm)
    dx, dy = exceso_de_tamano(tamano_visible(recorte), rect_zona)
    entrada.cabe = not (dx or dy)
    if entrada.cabe:
        return
    entrada.notas.append(f"no cabe en {zona}: el dibujo y {margen_hoja_mm:g} mm de margen se "
                         f"pasan {dx:.1f} mm de ancho y {dy:.1f} mm de alto")
    entrada.notas.append(_sugerir_escala(m, rect_zona, margen_hoja_mm))


def _sugerir_escala(m, rect_zona, margen_hoja_mm: float = MARGEN_POR_DEFECTO_MM) -> str:
    """La primera escala estándar mayor que la actual con la que el dibujo (más el margen de
    la hoja) cabría. Aproximada: se escala el dibujo; el exportador real puede dar unas
    décimas distintas."""
    contenido = _tamano_dibujo(m)
    actual = m.escala.denominador
    for n in ESCALAS_ESTANDAR:
        if n <= actual:
            continue
        pagina = tuple(c * actual / n + 2 * margen_hoja_mm for c in contenido)
        if exceso_de_tamano(pagina, rect_zona) == (0.0, 0.0):
            return (f"escala sugerida (aproximada): 1:{n}, dibujo y margen ≈ {pagina[0]:.1f} x "
                    f"{pagina[1]:.1f} mm")
    return (f"sin escala sugerida: ni a 1:{ESCALAS_ESTANDAR[-1]} cabe (la mayor de la lista "
            f"estándar)")


def _ruta_relativa(entrada: EntradaInventario, carpeta: Path) -> str:
    ruta = entrada.ruta_pdf or entrada.carpeta / entrada.prefijo
    try:
        return ruta.relative_to(carpeta).as_posix()
    except ValueError:
        return str(ruta)
