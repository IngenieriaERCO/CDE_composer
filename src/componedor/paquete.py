"""Localizar los paquetes del exportador en una carpeta y emparejar sus archivos.

Un paquete es <prefijo>.manifest.json + el PDF que indica su `pdf.file_name` (en la misma
carpeta) + <prefijo>.txt (opcional). Ver docs/contrato_paquete.md, «Cómo se localiza».

Aquí NO se abre el PDF ni se calcula ningún hash (subfase 2.3): solo se mira qué archivos
hay y se lee cada manifiesto con `leer_manifiesto`.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

from componedor.manifiesto import Manifiesto, ManifiestoInvalido, leer_manifiesto

SUFIJO_MANIFIESTO = ".manifest.json"

COMPLETO, INCOMPLETO, INVALIDO = "completo", "incompleto", "invalido"


class CarpetaInvalida(ValueError):
    """La carpeta de paquetes no existe o no es una carpeta."""


@dataclass
class Paquete:
    prefijo: str
    ruta_manifiesto: Path | None  # None: PDF sin manifiesto
    ruta_pdf: Path | None = None
    ruta_txt: Path | None = None
    manifiesto: Manifiesto | None = None
    problemas_manifiesto: list[str] = field(default_factory=list)  # leer_manifiesto
    problemas_archivos: list[str] = field(default_factory=list)  # PDF que falta, nombres

    @property
    def problemas(self) -> list[str]:
        return self.problemas_manifiesto + self.problemas_archivos

    @property
    def carpeta(self) -> Path:
        return (self.ruta_manifiesto or self.ruta_pdf).parent

    @property
    def estado(self) -> str:
        if self.ruta_manifiesto is None:
            return INCOMPLETO  # PDF sin manifiesto
        if self.manifiesto is None:
            return INVALIDO  # el manifiesto no pasa leer_manifiesto
        if self.ruta_pdf is None:
            return INCOMPLETO  # falta el PDF que indica el manifiesto
        return COMPLETO


PREFIJO_TEMPORAL = ".cde-tmp-"  # temporales del trabajador del exportador (contrato §1.1)


def es_temporal(ruta: Path, carpeta: Path) -> bool:
    """True si `ruta` está dentro de (o es) una carpeta `.cde-tmp-*` bajo `carpeta`, o es un
    archivo con ese prefijo: el exportador la está usando o quedó de una publicación cortada."""
    try:
        partes = Path(ruta).relative_to(carpeta).parts
    except ValueError:
        partes = (Path(ruta).name,)
    return any(p.startswith(PREFIJO_TEMPORAL) for p in partes)


def localizar_paquetes(carpeta: Path | str, recursivo: bool = False) -> list[Paquete]:
    """Paquetes de `carpeta` (y subcarpetas si `recursivo`), ordenados por carpeta y prefijo.

    Un manifiesto inválido no detiene el recorrido: se lista con sus problemas. Las carpetas y
    archivos `.cde-tmp-*` (temporales del exportador) se ignoran.
    """
    return localizar_con_sueltos(carpeta, recursivo)[0]


def localizar_con_sueltos(carpeta: Path | str,
                          recursivo: bool = False) -> tuple[list[Paquete], list[Path]]:
    """Como `localizar_paquetes`, y además los PDF sueltos que se ignoran (sin manifiesto
    ni TXT con su prefijo), ordenados por ruta."""
    carpeta = Path(carpeta)
    if not carpeta.exists():
        raise CarpetaInvalida(f"No existe la carpeta '{carpeta}'.")
    if not carpeta.is_dir():
        raise CarpetaInvalida(f"'{carpeta}' no es una carpeta.")

    carpetas = [carpeta]
    if recursivo:
        carpetas += sorted(p for p in carpeta.rglob("*")
                           if p.is_dir() and not es_temporal(p, carpeta))

    paquetes, sueltos = [], []
    for actual in carpetas:
        de_aqui, sueltos_aqui = _paquetes_de_una_carpeta(actual)
        paquetes += de_aqui
        sueltos += sueltos_aqui
    paquetes.sort(key=lambda p: (str(p.carpeta.relative_to(carpeta)).lower(), p.prefijo.lower()))
    sueltos.sort(key=lambda r: str(r.relative_to(carpeta)).lower())
    return paquetes, sueltos


def paquete_de_manifiesto(ruta_manifiesto: Path | str) -> Paquete:
    """El paquete al que pertenece un <prefijo>.manifest.json (su carpeta y su prefijo)."""
    ruta = Path(ruta_manifiesto)
    if not ruta.name.lower().endswith(SUFIJO_MANIFIESTO):
        raise CarpetaInvalida(
            f"'{ruta.name}' no es un manifiesto de paquete: debe llamarse "
            f"<prefijo>{SUFIJO_MANIFIESTO}."
        )
    if not ruta.is_file():
        raise CarpetaInvalida(f"No se encontró el manifiesto '{ruta}'.")
    paquetes, _ = _paquetes_de_una_carpeta(ruta.parent)
    return next(p for p in paquetes
                if p.ruta_manifiesto is not None and p.ruta_manifiesto.name == ruta.name)


def _paquetes_de_una_carpeta(carpeta: Path) -> tuple[list[Paquete], list[Path]]:
    archivos = {p.name: p for p in carpeta.iterdir()
                if p.is_file() and not p.name.startswith(PREFIJO_TEMPORAL)}
    usados: set[str] = set()  # PDF que ya pertenecen a algún paquete
    paquetes = []

    for nombre in sorted(archivos):
        if not nombre.lower().endswith(SUFIJO_MANIFIESTO):
            continue
        prefijo = nombre[: -len(SUFIJO_MANIFIESTO)]
        paquete = Paquete(prefijo, archivos[nombre])
        txt = archivos.get(f"{prefijo}.txt")
        paquete.ruta_txt = txt
        try:
            paquete.manifiesto = leer_manifiesto(archivos[nombre])
            nombre_pdf = paquete.manifiesto.pdf.nombre_archivo
        except ManifiestoInvalido as e:
            paquete.problemas_manifiesto += _lineas_de_error(e)
            nombre_pdf = _nombre_pdf_declarado(archivos[nombre])

        pdf_del_prefijo = f"{prefijo}.pdf"
        if nombre_pdf is not None and nombre_pdf in archivos:
            paquete.ruta_pdf = archivos[nombre_pdf]
            usados.add(nombre_pdf)
        elif paquete.manifiesto is None and pdf_del_prefijo in archivos:
            # Manifiesto ilegible: el PDF del mismo prefijo es suyo (no es un PDF huérfano).
            paquete.ruta_pdf = archivos[pdf_del_prefijo]
            usados.add(pdf_del_prefijo)
        elif nombre_pdf is not None and pdf_del_prefijo in archivos:
            paquete.problemas_archivos.append(
                f"pdf.file_name: el manifiesto indica '{nombre_pdf}' pero la carpeta tiene "
                f"'{pdf_del_prefijo}'"
            )
            usados.add(pdf_del_prefijo)
        elif nombre_pdf is not None:
            paquete.problemas_archivos.append(
                f"falta el PDF '{nombre_pdf}' (indicado en pdf.file_name): paquete incompleto"
            )
        paquetes.append(paquete)

    # PDF sin manifiesto: un <p>.pdf con su <p>.txt pero sin <p>.manifest.json es una
    # publicación cortada a medias (el exportador publica el manifiesto el último).
    # Un PDF solo, sin TXT, se toma como suelto y se ignora (se devuelve aparte, informativo).
    sueltos = []
    for nombre in sorted(archivos):
        if not nombre.lower().endswith(".pdf") or nombre in usados:
            continue
        prefijo = nombre[:-4]
        if f"{prefijo}.txt" in archivos and f"{prefijo}{SUFIJO_MANIFIESTO}" not in archivos:
            paquetes.append(Paquete(
                prefijo, None, ruta_pdf=archivos[nombre], ruta_txt=archivos[f"{prefijo}.txt"],
                problemas_archivos=[f"PDF sin manifiesto: no se usa (falta {prefijo}{SUFIJO_MANIFIESTO}; "
                           f"la publicación quedó a medias)"],
            ))
        else:
            sueltos.append(archivos[nombre])
    return paquetes, sueltos


def _lineas_de_error(error: ManifiestoInvalido) -> list[str]:
    """Problemas de un ManifiestoInvalido, uno por elemento (sin el encabezado)."""
    lineas = [linea[2:] for linea in str(error).splitlines() if linea.startswith("- ")]
    return lineas or [str(error)]


def _nombre_pdf_declarado(ruta_manifiesto: Path) -> str | None:
    """pdf.file_name de un manifiesto inválido, si se puede leer como texto sin ruta."""
    try:
        nombre = json.loads(ruta_manifiesto.read_text(encoding="utf-8"))["pdf"]["file_name"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if isinstance(nombre, str) and nombre and "/" not in nombre and "\\" not in nombre:
        return nombre
    return None
