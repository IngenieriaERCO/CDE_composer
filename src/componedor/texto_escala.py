"""Escalas escritas como en los planos de ERCO: "1:50", "1:1.000", "1:10.000".

Separador de miles con punto SIEMPRE (también en la celda ESCALA y en la etiqueta
"ESC: 1:N" de cada detalle). Si N no es entero (raro), los decimales van con coma: "1:12,5".
"""


def numero_con_miles(n: float) -> str:
    """1000 -> "1.000"; 12.5 -> "12,5"; 50 -> "50"."""
    if abs(n - round(n)) < 1e-9:
        return f"{int(round(n)):,}".replace(",", ".")
    entero, decimales = f"{n:.4f}".rstrip("0").split(".")
    return f"{int(entero):,}".replace(",", ".") + "," + decimales


def texto_escala(denominador: float) -> str:
    """El N de 1:N como texto: 1000 -> "1:1.000"."""
    return "1:" + numero_con_miles(denominador)
