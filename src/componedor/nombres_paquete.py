"""Nombre del paquete de un bloque exportado a una escala (§5.1 del contrato del trabajador).

El trabajador propone en `load` un `file_stem` que ya cumple las reglas (sin acentos, solo
A–Z, a–z, 0–9, «.», «-», «_», 60 caracteres como mucho). Al exportarlo a 1:N el Componedor le
agrega la escala, `<file_stem>_1-N`, y eso puede pasar de 60: entonces se recorta el nombre y
se pone NUESTRO sufijo de hash antes de la escala (`<recorte>_<hash6>_1-N`), para que dos
bloques de nombre largo parecido no terminen con el mismo paquete. La escala (y la marca del estilo de
impresión) quedan siempre al final, a la vista.

Lo usará la exportación desde el editor (etapa 3).
"""

import hashlib
import re
import unicodedata

MAX_PAQUETE = 60
LARGO_HASH = 6


def limpiar(nombre: str) -> str:
    """Las mismas reglas que el trabajador (§5.1), por si el nombre no vino ya limpio."""
    sin_tildes = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9._-]", "_", sin_tildes).lstrip(".") or "_"


def nombre_paquete(file_stem: str, denominador: float, marca: str = "") -> str:
    """`<file_stem>_1-N<marca>`, o `<recorte>_<hash6>_1-N<marca>` si pasaría de 60 caracteres.
    `marca`: la del estilo de impresión (`_p<sha6>`, `_t`; estilos_impresion.marca)."""
    base = limpiar(file_stem)
    escala = f"_1-{float(denominador):g}" + marca  # 1:2000 → _1-2000; 1:12.5 → _1-12.5
    if len(base) + len(escala) <= MAX_PAQUETE:
        return base + escala
    sufijo = "_" + hashlib.sha256(file_stem.encode("utf-8")).hexdigest()[:LARGO_HASH] + escala
    return base[:MAX_PAQUETE - len(sufijo)].rstrip("._-") + sufijo
