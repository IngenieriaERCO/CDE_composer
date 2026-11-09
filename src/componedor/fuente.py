"""Fuente TrueType para los textos del rótulo y las etiquetas de escala (subfase 4.1).

En los planos la altura de un texto es la de sus MAYÚSCULAS (como la altura de texto de
AutoCAD), no el tamaño de fuente en puntos. La relación entre las dos la da la fuente:
`sCapHeight / unitsPerEm` de sus tablas OS/2 y head (Arial: 1467 / 2048 = 0,716). Si la
fuente no trae ese dato se usa 0,716 (Arial) y se avisa en `altura_mayusculas_leida`.

La fuente se embebe en el PDF (la inserta `Page.insert_text` con `fontfile`): el plano se
ve igual en cualquier equipo. Solo se aceptan archivos .ttf/.otf sueltos (no colecciones
.ttc) que existan y tengan todos los caracteres que se escriben (tildes, ñ, °, ...).
"""

import struct
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from componedor.unidades import mm_a_pt, pt_a_mm

ALTURA_MAYUSCULAS_POR_DEFECTO = 0.716  # Arial
NOMBRE_EN_PDF = "RotuloF"  # nombre del recurso de fuente dentro de la página


class FuenteInvalida(ValueError):
    """La fuente no existe, no se puede leer o le faltan caracteres."""


@dataclass(frozen=True)
class Fuente:
    ruta: Path
    nombre: str
    altura_mayusculas: float  # fracción del em (Arial 0,716)
    altura_mayusculas_leida: bool  # False: se usó el valor por defecto
    _font: pymupdf.Font

    def tamano_pt(self, altura_mm: float) -> float:
        """Tamaño de fuente (pt) para que las MAYÚSCULAS midan `altura_mm`."""
        return mm_a_pt(altura_mm) / self.altura_mayusculas

    def ancho_mm(self, texto: str, altura_mm: float) -> float:
        """Ancho del texto (mm) escrito con mayúsculas de `altura_mm`."""
        return pt_a_mm(self._font.text_length(texto, fontsize=self.tamano_pt(altura_mm)))

    def caja_vertical_mm(self, altura_mm: float) -> tuple[float, float]:
        """(descenso, ascenso) en mm bajo y sobre la línea base: la caja de línea que el
        lector de PDF da a cada carácter (ascender/descender de la fuente)."""
        tamano = pt_a_mm(self.tamano_pt(altura_mm))
        return -self._font.descender * tamano, self._font.ascender * tamano

    def anchos_em(self, caracteres: str) -> dict[str, float]:
        """Ancho de avance de cada carácter que la fuente tiene, en fracciones del em (el
        ancho de un texto = suma de avances × tamaño en pt; PyMuPDF no aplica kerning). Para la
        tabla de anchos del editor."""
        return {c: self._font.glyph_advance(ord(c)) for c in dict.fromkeys(caracteres)
                if self._font.has_glyph(ord(c))}

    def rangos_unicode(self) -> list[list[int]]:
        """Los caracteres que la fuente tiene, como rangos [desde, hasta] de puntos de código
        (los mismos que `caracteres_faltantes` acepta). Para que el editor valide igual que
        Python (subfase 4.3b): Arial cabe en ~150 rangos."""
        rangos: list[list[int]] = []
        for c in sorted(set(self._font.valid_codepoints())):
            if rangos and c == rangos[-1][1] + 1:
                rangos[-1][1] = c
            else:
                rangos.append([c, c])
        return rangos

    def glifo(self, caracter: str) -> int:
        """Número de glifo del carácter en la fuente (0 si no lo tiene)."""
        return self._font.has_glyph(ord(caracter))

    def caracteres_faltantes(self, texto: str) -> list[str]:
        """Caracteres de `texto` que la fuente no tiene (sin repetir, en orden)."""
        faltan: list[str] = []
        for c in texto:
            if c not in faltan and not c.isspace() and not self._font.has_glyph(ord(c)):
                faltan.append(c)
        return faltan


def cargar_fuente(ruta: Path | str) -> Fuente:
    """Abre la fuente y lee su altura de mayúsculas. Lanza `FuenteInvalida`."""
    ruta = Path(ruta)
    if not ruta.is_file():
        raise FuenteInvalida(
            f"No se encontró la fuente '{ruta}'. Revise rotulo.fuente.archivo en el formato.")
    if ruta.suffix.lower() not in (".ttf", ".otf"):
        raise FuenteInvalida(
            f"La fuente '{ruta}' debe ser un archivo .ttf u .otf (las colecciones .ttc no se "
            f"admiten).")
    datos = ruta.read_bytes()
    try:
        font = pymupdf.Font(fontbuffer=datos)
    except Exception as e:  # PyMuPDF lanza varios tipos según el daño del archivo
        raise FuenteInvalida(f"No se pudo leer la fuente '{ruta}': {e}") from e
    proporcion = altura_mayusculas(datos)
    return Fuente(ruta=ruta, nombre=font.name,
                  altura_mayusculas=proporcion or ALTURA_MAYUSCULAS_POR_DEFECTO,
                  altura_mayusculas_leida=proporcion is not None, _font=font)


def altura_mayusculas(datos: bytes) -> float | None:
    """sCapHeight / unitsPerEm de un archivo TrueType/OpenType, o None si no se puede leer
    (tabla OS/2 anterior a la versión 2, archivo raro)."""
    try:
        tablas = _tablas(datos)
        if "head" not in tablas or "OS/2" not in tablas:
            return None
        unidades = struct.unpack_from(">H", datos, tablas["head"] + 18)[0]
        inicio_os2 = tablas["OS/2"]
        version = struct.unpack_from(">H", datos, inicio_os2)[0]
        if version < 2 or unidades <= 0:
            return None
        cap = struct.unpack_from(">h", datos, inicio_os2 + 88)[0]
    except struct.error:
        return None
    return cap / unidades if cap > 0 else None


def _tablas(datos: bytes) -> dict[str, int]:
    """Directorio de tablas: etiqueta -> posición en el archivo."""
    cantidad = struct.unpack_from(">H", datos, 4)[0]
    tablas = {}
    for i in range(cantidad):
        etiqueta, _, posicion, _ = struct.unpack_from(">4sIII", datos, 12 + 16 * i)
        tablas[etiqueta.decode("latin-1")] = posicion
    return tablas
