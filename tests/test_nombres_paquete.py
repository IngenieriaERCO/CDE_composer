"""Nombre del paquete de un bloque a 1:N: §5.1 del contrato, con nuestro sufijo de hash."""

import re

from componedor.nombres_paquete import MAX_PAQUETE, limpiar, nombre_paquete

VALIDO = re.compile(r"^[A-Za-z0-9_-][A-Za-z0-9._-]*$")
LARGO = "HSS-Tubo_estructural_redondo_-_Tubo_metalico_galvanizado_2_e_1_9mm-4445096-ISOMETRICO"


def test_corto_lleva_la_escala_al_final():
    assert nombre_paquete("BLOQUE1", 2000) == "BLOQUE1_1-2000"
    assert nombre_paquete("Pilar_N_002", 50) == "Pilar_N_002_1-50"


def test_largo_se_recorta_con_nuestro_hash_antes_de_la_escala():
    n = nombre_paquete(LARGO, 10000)
    assert len(n) <= MAX_PAQUETE and VALIDO.match(n)  # el recorte no termina en «_»
    assert n.startswith("HSS-Tubo_estructural") and re.search(r"_[0-9a-f]{6}_1-10000$", n)
    # Mismo nombre y escala: mismo paquete. Otra escala: solo cambia el final.
    assert nombre_paquete(LARGO, 10000) == n
    assert nombre_paquete(LARGO, 50).endswith("_1-50")


def test_dos_nombres_largos_parecidos_no_chocan():
    a = nombre_paquete(LARGO + "_A", 500)
    b = nombre_paquete(LARGO + "_B", 500)
    assert a != b and len(a) <= MAX_PAQUETE and len(b) <= MAX_PAQUETE


def test_justo_en_el_limite():
    stem = "x" * (MAX_PAQUETE - len("_1-50"))
    assert nombre_paquete(stem, 50) == stem + "_1-50"
    assert len(nombre_paquete(stem + "y", 50)) == MAX_PAQUETE


def test_limpia_si_el_nombre_no_venia_limpio():
    assert limpiar("Pilar Ø0,30 — ñandú") == "Pilar_0_30__nandu"
    assert limpiar(".oculto") == "oculto" and limpiar("ØØ") == "_"
    assert nombre_paquete("Viga Ñ", 50) == "Viga_N_1-50"
