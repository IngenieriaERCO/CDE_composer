"""Textos de las advertencias de traslape, en un solo lugar.

Los usa `componer` (Python) y se incrustan en el editor HTML (JS), para que el usuario lea
exactamente lo mismo en los dos lados. Marcadores: {a} y {b} (ids de detalles; b es el que
queda encima), {elemento} (nombre de un elemento fijo de la plantilla), {ancho} y {alto}
(mm del traslape, ya con un decimal).

Niveles, de menor a mayor: aviso, fuerte, muy_fuerte. Ninguno es error.

Con o sin fondo: los paquetes antiguos del exportador traen un fondo blanco de página
completa que tapa lo que queda debajo; los nuevos no. Lo que tapa es solo el detalle de
ENCIMA (el que va después en el plano), así que la regla depende de si ese tiene fondo:
  - con fondo: "paginas", "dibujos", "pagina_sobre_elemento", "dibujo_sobre_elemento";
  - sin fondo: un traslape solo de páginas no avisa (no tapa nada); se avisa con
    "dibujos_sin_fondo" y "dibujo_sobre_elemento_sin_fondo" (sin mencionar el fondo).
"""

PLANTILLAS = {
    # Dos detalles: se traslapan sus páginas, pero no sus dibujos.
    "paginas": {
        "nivel": "aviso",
        "texto": ("Advertencia: las PÁGINAS de '{a}' y '{b}' se traslapan ({ancho} x {alto} mm), "
                  "aunque sus dibujos no. Mientras el exportador deje fondo blanco, el margen de "
                  "'{b}' (encima) tapa esa franja de '{a}'."),
    },
    # Dos detalles: se traslapan sus dibujos (page_bounds_mm).
    "dibujos": {
        "nivel": "fuerte",
        "texto": ("ADVERTENCIA FUERTE: los DIBUJOS de '{a}' y '{b}' se traslapan ({ancho} x "
                  "{alto} mm). Mientras el exportador deje fondo blanco, '{b}' (encima) tapa "
                  "parte del dibujo de '{a}'."),
    },
    # Un detalle y un elemento fijo de la plantilla: solo la página lo toca.
    "pagina_sobre_elemento": {
        "nivel": "fuerte",
        "texto": ("ADVERTENCIA FUERTE: el detalle '{a}' tapa '{elemento}' de la plantilla con su "
                  "fondo blanco ({ancho} x {alto} mm), aunque su dibujo no lo toca."),
    },
    # Un detalle y un elemento fijo de la plantilla: el dibujo se monta encima.
    "dibujo_sobre_elemento": {
        "nivel": "muy_fuerte",
        "texto": ("ADVERTENCIA MUY FUERTE: el dibujo '{a}' se monta sobre '{elemento}' de la "
                  "plantilla ({ancho} x {alto} mm); además su fondo blanco lo tapa."),
    },
    # Sin fondo (el de encima): se traslapan los dibujos.
    "dibujos_sin_fondo": {
        "nivel": "fuerte",
        "texto": ("ADVERTENCIA FUERTE: los DIBUJOS de '{a}' y '{b}' se traslapan ({ancho} x "
                  "{alto} mm): en el plano sus líneas quedarán superpuestas."),
    },
    # Sin fondo: el dibujo se monta sobre un elemento fijo de la plantilla.
    "dibujo_sobre_elemento_sin_fondo": {
        "nivel": "muy_fuerte",
        "texto": ("ADVERTENCIA MUY FUERTE: el dibujo '{a}' se monta sobre '{elemento}' de la "
                  "plantilla ({ancho} x {alto} mm): sus líneas quedarán encima."),
    },
}


def clave_traslape_detalles(dibujos: bool, paginas: bool, encima_tiene_fondo: bool) -> str | None:
    """Qué advertencia corresponde a dos detalles (None: ninguna). Solo tapa el de encima."""
    if dibujos:
        return "dibujos" if encima_tiene_fondo else "dibujos_sin_fondo"
    if paginas and encima_tiene_fondo:
        return "paginas"
    return None


def clave_sobre_elemento(dibujo: bool, pagina: bool, tiene_fondo: bool) -> str | None:
    """Qué advertencia corresponde a un detalle sobre un elemento fijo (None: ninguna)."""
    if dibujo:
        return "dibujo_sobre_elemento" if tiene_fondo else "dibujo_sobre_elemento_sin_fondo"
    if pagina and tiene_fondo:
        return "pagina_sobre_elemento"
    return None


def texto_advertencia(clave: str, ancho: float, alto: float, **nombres: str) -> str:
    """Texto de la advertencia `clave` con el tamaño del traslape (mm) y los nombres."""
    return PLANTILLAS[clave]["texto"].format(ancho=f"{ancho:.1f}", alto=f"{alto:.1f}", **nombres)
