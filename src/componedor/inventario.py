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

ACEPTADO, RECHAZADO = "aceptado", "rechazado"
ESCALAS_ESTANDAR = (50, 100, 200, 250, 500, 750, 1000, 1500, 2000, 2500, 5000, 10000)


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


def construir_inventario(carpeta: Path | str, formato: Formato | None = None,
                         zona: str = "area_dibujo", recursivo: bool = False,
                         ) -> list[EntradaInventario]:
    """Una entrada por paquete de `carpeta` (en el orden de `localizar_paquetes`)."""
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
        )
        if rect_zona is not None and m is not None:
            _evaluar_cabida(entrada, m, zona, rect_zona)
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


def _evaluar_cabida(entrada: EntradaInventario, m, zona: str, rect_zona) -> None:
    dx, dy = exceso_de_tamano(m.pdf.tamano_pagina_mm, rect_zona)
    entrada.cabe = not (dx or dy)
    if entrada.cabe:
        return
    entrada.notas.append(f"no cabe en {zona}: se pasa {dx:.1f} mm de ancho y {dy:.1f} mm de alto")
    entrada.notas.append(_sugerir_escala(m, rect_zona))


def _sugerir_escala(m, rect_zona) -> str:
    """La primera escala estándar mayor que la actual con la que la página cabría.

    Aproximada: se escala el contenido (página menos 2 veces el margen) y se le vuelve a
    sumar el margen; el exportador real puede dar unas décimas distintas.
    """
    margen = m.pdf.margen_mm
    if margen is None:
        return "sin escala sugerida: el manifiesto no indica pdf.margin_mm"
    ancho, alto = m.pdf.tamano_pagina_mm
    contenido = (ancho - 2 * margen, alto - 2 * margen)
    actual = m.escala.denominador
    for n in ESCALAS_ESTANDAR:
        if n <= actual:
            continue
        pagina = tuple(c * actual / n + 2 * margen for c in contenido)
        if exceso_de_tamano(pagina, rect_zona) == (0.0, 0.0):
            return (f"escala sugerida (aproximada): 1:{n}, página ≈ {pagina[0]:.1f} x "
                    f"{pagina[1]:.1f} mm")
    return (f"sin escala sugerida: ni a 1:{ESCALAS_ESTANDAR[-1]} cabe (la mayor de la lista "
            f"estándar)")


def _ruta_relativa(entrada: EntradaInventario, carpeta: Path) -> str:
    ruta = entrada.ruta_pdf or entrada.carpeta / entrada.prefijo
    try:
        return ruta.relative_to(carpeta).as_posix()
    except ValueError:
        return str(ruta)
