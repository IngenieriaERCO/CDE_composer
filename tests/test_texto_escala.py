"""Escalas escritas con punto de miles: "1:1.000"."""

import pytest

from componedor.texto_escala import numero_con_miles, texto_escala


@pytest.mark.parametrize("n, texto", [
    (50, "1:50"), (50.0, "1:50"), (500, "1:500"), (1000, "1:1.000"), (1500.0, "1:1.500"),
    (10000, "1:10.000"), (25000, "1:25.000"), (1_000_000, "1:1.000.000"), (12.5, "1:12,5"),
    (1250.25, "1:1.250,25"),
])
def test_texto_escala(n, texto):
    assert texto_escala(n) == texto


def test_numero_con_miles():
    assert numero_con_miles(999) == "999"
    assert numero_con_miles(1000.0000000001) == "1.000"  # ruido numérico: entero
