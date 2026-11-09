"""Firmas en imagen en la celda FIRMA del rótulo (subfases 4.2d a 4.2f).

En el plano.json (versión 2), una celda cuya columna tiene "acepta_imagen": true en el formato
admite, en vez de texto, una imagen guardada en una CARPETA POR PERSONA dentro de alguna de
las carpetas de `rotulo.carpeta_firmas` del formato (A1 ERCO: firmas/ y data/firmas/, las dos
fuera de git):
  - {"imagen": "<persona>"} usa <carpeta>/<persona>/firma.png; si no hay firma.png y la carpeta
    tiene un solo PNG, usa ese; si tiene varios, error (nombre uno firma.png o elija una
    variante);
  - {"imagen": "<persona>/<archivo>"} (sin .png) elige una variante concreta.
El nombre de la persona y el del archivo admiten letras (con tildes y ñ), números, espacio,
«_» y «-» (p. ej. «Luis Ángel Núñez»); se rechazan «..», rutas absolutas y cualquier separador
que no sea el único «/» entre persona y archivo. En Windows la búsqueda no distingue
mayúsculas; las tildes se comparan normalizadas (Unicode NFC).

Reglas:
- PNG de hasta 600 x 200 px y 100 KB; sin canal alfa es advertencia (su fondo blanco tapará
  las líneas de la celda).
- Caja de la firma (subfase 4.2e): el ANCHO de su celda (menos el relleno) y de alto
  max(`alto_max_mm`, alto útil de su fila) (A1 ERCO: 5 mm; REVISÓ, ~7,9 mm), centrada en SU
  fila y corrida hacia adentro si se
  saldría del cuerpo de la tabla (menos el relleno): puede montarse sobre las filas vecinas,
  pero nunca sobre el encabezado (la etiqueta «FIRMA») ni fuera de la tabla. Los textos de
  las otras columnas no se tocan. Sin `alto_max_mm`, la caja es la celda menos el relleno.
- Colocación proporcional y centrada en esa caja, nunca más grande que su tamaño a 300 ppp:
  una imagen chica queda chica, nunca pixelada. Si dos firmas quedan una sobre otra:
  advertencia (`montajes`).
- Se inserta con `Page.insert_image`; el canal alfa queda como máscara de transparencia
  (SMask), no con fondo blanco.
- Verificación en el PDF guardado: la hoja tiene exactamente las imágenes de la hoja base más
  una por firma; cada firma con su caja igual a la esperada y dentro de la celda (±0,1 mm),
  con su máscara, y su huella igual a la del archivo leído (la máscara es byte a byte el
  canal alfa del PNG; sin alfa, el `digest` de los píxeles). Se registra el SHA-256 del
  archivo.

Privacidad: una firma es un dato personal. Las imágenes van fuera de git (toda la carpeta
firmas/ y data/ están en .gitignore), no se incrustan en editor.html y deberían ponerse solo
en los PDF emitidos.
"""

import hashlib
import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from componedor.rotulo_formato import Celda
from componedor.transformaciones import RectMM, rect_papel_a_pdf, rect_pdf_a_papel

FIRMA_PNG = b"\x89PNG\r\n\x1a\n"
MAX_ANCHO_PX, MAX_ALTO_PX = 600, 200
MAX_BYTES = 100 * 1024
PPP_MAX = 300  # nunca más grande que su tamaño a 300 ppp
TOL_MM = 0.1
# Un nombre (persona o archivo): letras de cualquier idioma (con tildes y ñ), números, espacio,
# «_» y «-»; sin espacios al principio ni al final. Sin punto: «..», «./» y extensiones quedan
# fuera.
NOMBRE_VALIDO = re.compile(r"^[\w\-](?:[\w \-]*[\w\-])?$")
ARCHIVO_POR_DEFECTO = "firma"
SIN_MAYUSCULAS = os.name == "nt"  # Windows: la búsqueda no distingue mayúsculas


@dataclass(frozen=True)
class FirmaPedida:
    ruta_celda: str  # "firmas.dibujo.firma"
    id: str
    archivo: Path
    datos: bytes
    sha256: str  # del archivo leído (trazabilidad)
    ancho_px: int
    alto_px: int
    alfa: bool
    huella: bytes  # md5 de la máscara (con alfa) o digest de los píxeles (sin alfa)
    celda: RectMM
    destino: RectMM  # dónde queda la imagen, mm de papel
    escala: float  # destino / tamaño a 300 ppp (<= 1)
    caja: RectMM  # dónde puede ir la imagen (ancho de la columna, hasta alto_max_mm)
    cuerpo_y: tuple[float, float] | None = None  # Y del cuerpo de la tabla (sin encabezado)


def pedir_firma(valor: dict, celda: Celda, donde: str, carpetas: tuple[Path, ...],
                relleno_mm: float, problemas: list[str],
                advertencias: list[str]) -> FirmaPedida | None:
    """{"imagen": id} en `celda` -> la firma lista para insertar, o None (anota el problema)."""
    if not celda.acepta_imagen:
        problemas.append(f"{donde}: la celda '{celda.ruta}' no acepta imagen (solo texto); "
                         f"las firmas en imagen van en la columna FIRMA")
        return None
    n = len(problemas)
    for clave in sorted(set(valor) - {"imagen"}):
        problemas.append(f"{donde}.{clave}: campo no reconocido (campos válidos: imagen)")
    ident = valor.get("imagen")
    partes = _partes_del_id(ident)
    if partes is None:
        problemas.append(
            f"{donde}.imagen: se esperaba \"<persona>\" o \"<persona>/<archivo>\" (letras con "
            f"tildes y ñ, números, espacio, _ o -; sin «..», sin ruta absoluta y sin otros "
            f"separadores; el archivo va sin .png); tiene {ident!r}")
        return None
    if len(problemas) > n:
        return None
    persona, variante = partes
    archivo = _buscar_firma(persona, variante, carpetas, f"{donde}.imagen", problemas)
    if archivo is None:
        return None
    datos = archivo.read_bytes()
    if not datos.startswith(FIRMA_PNG):
        problemas.append(f"{donde}.imagen: '{archivo}' no es un PNG")
        return None
    if len(datos) > MAX_BYTES:
        problemas.append(f"{donde}.imagen: '{archivo}' pesa {len(datos) / 1024:.1f} KB y el "
                         f"máximo es {MAX_BYTES // 1024} KB")
    try:
        pix = pymupdf.Pixmap(datos)
    except Exception as e:  # PNG dañado
        problemas.append(f"{donde}.imagen: '{archivo}' no se pudo leer como imagen: {e}")
        return None
    if pix.width > MAX_ANCHO_PX or pix.height > MAX_ALTO_PX:
        problemas.append(f"{donde}.imagen: '{archivo}' mide {pix.width} x {pix.height} px y el "
                         f"máximo es {MAX_ANCHO_PX} x {MAX_ALTO_PX} px")
    if len(problemas) > n:
        return None
    alfa = bool(pix.alpha)
    if not alfa:
        advertencias.append(f"Advertencia: la firma de '{persona}' ({archivo.name}) no tiene "
                            f"canal alfa (transparencia): su fondo tapará las líneas de la celda "
                            f"'{celda.ruta}'. Límpiela antes de emitir el plano.")
    huella = (hashlib.md5(bytes(pix.samples[pix.n - 1::pix.n])).digest() if alfa
              else pix.digest)
    caja = caja_firma(celda, relleno_mm)
    destino, escala = colocar_firma(pix.width, pix.height, caja)
    return FirmaPedida(celda.ruta, ident, archivo, datos, hashlib.sha256(datos).hexdigest(),
                       pix.width, pix.height, alfa, huella, celda.rect, destino, escala, caja,
                       celda.cuerpo_y)


def _partes_del_id(ident) -> tuple[str, str | None] | None:
    """"<persona>" o "<persona>/<archivo>" -> (persona, archivo o None); None si no es válido
    (tipo, «..», ruta absoluta, «\\», «:», más de un «/», caracteres fuera de lo permitido)."""
    if not isinstance(ident, str) or not ident or ident != ident.strip():
        return None
    if "\\" in ident or ":" in ident or ident.startswith("/") or Path(ident).is_absolute():
        return None
    partes = ident.split("/")
    if len(partes) > 2 or not all(NOMBRE_VALIDO.match(p) for p in partes):
        return None
    return partes[0], (partes[1] if len(partes) == 2 else None)


def _clave(nombre: str) -> str:
    """Cómo se comparan nombres de carpeta y archivo: tildes normalizadas (NFC) y, en
    Windows, sin distinguir mayúsculas."""
    nombre = unicodedata.normalize("NFC", nombre)
    return nombre.casefold() if SIN_MAYUSCULAS else nombre


def _buscar_firma(persona: str, variante: str | None, carpetas: tuple[Path, ...], donde: str,
                  problemas: list[str]) -> Path | None:
    """El PNG de la persona (firma.png, el único PNG de su carpeta, o la variante pedida)."""
    buscadas = ", ".join(str(c) for c in carpetas) or "(ninguna carpeta)"
    encontradas = [d for c in carpetas if c.is_dir() for d in c.iterdir()
                   if d.is_dir() and _clave(d.name) == _clave(persona)]
    if not encontradas:
        problemas.append(f"{donde}: no se encontró la carpeta de la persona '{persona}' (se buscó "
                         f"en: {buscadas})")
        return None
    if len(encontradas) > 1:
        problemas.append(f"{donde}: la persona '{persona}' tiene carpeta en más de un lugar "
                         f"({', '.join(str(d) for d in encontradas)}); deje una sola")
        return None
    carpeta = encontradas[0]
    pngs = sorted((a for a in carpeta.iterdir() if a.is_file() and a.suffix.lower() == ".png"),
                  key=lambda a: a.name)
    nombres = ", ".join(a.name for a in pngs) or "ninguno"
    if variante is not None:
        elegidas = [a for a in pngs if _clave(a.stem) == _clave(variante)]
        if not elegidas:
            problemas.append(f"{donde}: la persona '{persona}' no tiene la variante "
                             f"'{variante}.png' en '{carpeta}' (PNG que tiene: {nombres})")
            return None
        return elegidas[0]
    principal = [a for a in pngs if _clave(a.stem) == _clave(ARCHIVO_POR_DEFECTO)]
    if principal:
        return principal[0]
    if len(pngs) == 1:
        return pngs[0]
    if not pngs:
        problemas.append(f"{donde}: la carpeta de la persona '{persona}' ('{carpeta}') no tiene "
                         f"ningún PNG")
    else:
        problemas.append(f"{donde}: la carpeta de la persona '{persona}' ('{carpeta}') tiene "
                         f"varios PNG ({nombres}) y ninguno se llama firma.png: nombre uno "
                         f"firma.png o use {{\"imagen\": \"{persona}/<archivo>\"}}")
    return None


def caja_firma(celda: Celda, relleno_mm: float) -> RectMM:
    """Dónde puede ir la firma (mm de papel): el ancho de la celda menos el relleno y, con
    `alto_max_mm`, un alto de max(alto_max_mm, alto útil de su fila) centrado en la fila,
    corrido hacia adentro del cuerpo de la tabla si se saldría (y nunca más alto que el
    cuerpo). Sin `alto_max_mm`: la celda menos el relleno."""
    x0, y0, x1, y1 = celda.rect
    r = relleno_mm
    if celda.alto_max_mm <= 0 or celda.cuerpo_y is None:
        return x0 + r, y0 + r, x1 - r, y1 - r
    abajo, arriba = celda.cuerpo_y[0] + r, celda.cuerpo_y[1] - r
    # Una fila más alta que alto_max_mm (REVISÓ, ~7,9 mm útiles) puede usar toda su altura.
    alto = min(max(celda.alto_max_mm, (y1 - y0) - 2 * r), arriba - abajo)
    cy = (y0 + y1) / 2
    inferior, superior = cy - alto / 2, cy + alto / 2
    if superior > arriba:  # se saldría por arriba (encabezado): se corre hacia abajo
        inferior, superior = arriba - alto, arriba
    if inferior < abajo:  # se saldría por abajo (fuera de la tabla): se corre hacia arriba
        inferior, superior = abajo, abajo + alto
    return x0 + r, inferior, x1 - r, superior


def colocar_firma(ancho_px: int, alto_px: int, caja: RectMM) -> tuple[RectMM, float]:
    """La imagen proporcional y centrada en su caja, nunca mayor que su tamaño a 300 ppp.
    Devuelve (rectángulo en mm de papel, escala respecto de 300 ppp)."""
    ancho = ancho_px / PPP_MAX * 25.4
    alto = alto_px / PPP_MAX * 25.4
    f = min(1.0, (caja[2] - caja[0]) / ancho, (caja[3] - caja[1]) / alto)
    cx, cy = (caja[0] + caja[2]) / 2, (caja[1] + caja[3]) / 2
    return (cx - ancho * f / 2, cy - alto * f / 2, cx + ancho * f / 2, cy + alto * f / 2), f


def montajes(firmas: list[FirmaPedida]) -> list[str]:
    """Advertencias de firmas que quedan una sobre otra (sus imágenes se cruzan)."""
    avisos = []
    for i, a in enumerate(firmas):
        for b in firmas[i + 1:]:
            ancho = min(a.destino[2], b.destino[2]) - max(a.destino[0], b.destino[0])
            alto = min(a.destino[3], b.destino[3]) - max(a.destino[1], b.destino[1])
            if ancho > 1e-6 and alto > 1e-6:
                avisos.append(
                    f"Advertencia: las firmas de las filas '{_fila(a)}' y '{_fila(b)}' se montan "
                    f"una sobre otra ({ancho:.1f} x {alto:.1f} mm). Si estorba, use firmas más "
                    f"bajas o baje \"alto_max_mm\" en el formato.")
    return avisos


def _fila(f: FirmaPedida) -> str:
    partes = f.ruta_celda.split(".")
    return partes[1] if len(partes) == 3 else f.ruta_celda


def insertar_firmas(page: pymupdf.Page, firmas: list[FirmaPedida], alto_hoja_mm: float) -> None:
    """Inserta cada firma (PNG con su máscara de transparencia)."""
    for f in firmas:
        page.insert_image(rect_papel_a_pdf(f.destino, alto_hoja_mm), stream=f.datos,
                          keep_proportion=False)


def verificar_firmas(page: pymupdf.Page, firmas: list[FirmaPedida],
                     alto_hoja_mm: float) -> list[str]:
    """Cada firma en su sitio, dentro de su celda, con su máscara y su huella."""
    if not firmas:
        return []
    doc = page.parent
    mascaras = {img[0]: img[1] for img in page.get_images(full=True)}
    infos = [(rect_pdf_a_papel(pymupdf.Rect(i["bbox"]), alto_hoja_mm), i)
             for i in page.get_image_info(hashes=True, xrefs=True)]
    problemas = []
    for f in firmas:
        donde = f"firma '{f.id}' en '{f.ruta_celda}'"
        cerca = [(r, i) for r, i in infos
                 if max(abs(a - b) for a, b in zip(r, f.destino)) <= TOL_MM]
        if len(cerca) != 1:
            problemas.append(f"{donde}: se esperaba una imagen en {_mm(f.destino)} (±{TOL_MM} mm) "
                             f"y hay {len(cerca)}")
            continue
        rect, info = cerca[0]
        if not (rect[0] >= f.caja[0] - TOL_MM and rect[1] >= f.caja[1] - TOL_MM
                and rect[2] <= f.caja[2] + TOL_MM and rect[3] <= f.caja[3] + TOL_MM):
            problemas.append(f"{donde}: la imagen {_mm(rect)} se sale de su caja {_mm(f.caja)}")
        if f.cuerpo_y is not None and (rect[3] > f.cuerpo_y[1] + TOL_MM
                                       or rect[1] < f.cuerpo_y[0] - TOL_MM):
            problemas.append(f"{donde}: la imagen {_mm(rect)} pisa el encabezado de la tabla o "
                             f"se sale de ella (cuerpo: Y {f.cuerpo_y[0]:.2f} a "
                             f"{f.cuerpo_y[1]:.2f} mm)")
        if (info["width"], info["height"]) != (f.ancho_px, f.alto_px):
            problemas.append(f"{donde}: la imagen del PDF mide {info['width']} x {info['height']} "
                             f"px y el archivo {f.ancho_px} x {f.alto_px} px")
            continue
        smask = mascaras.get(info["xref"], 0)
        if f.alfa:
            if not smask:
                problemas.append(f"{donde}: la imagen no tiene máscara de transparencia (SMask)")
                continue
            leida = hashlib.md5(bytes(pymupdf.Pixmap(doc, smask).samples)).digest()
        else:
            leida = info["digest"]
        if leida != f.huella:
            problemas.append(f"{donde}: la imagen del PDF no es la del archivo leído "
                             f"({f.archivo.name}, SHA-256 {f.sha256[:12]}…)")
    return problemas


def _mm(r: RectMM) -> str:
    return "X {:.2f} a {:.2f}, Y {:.2f} a {:.2f} mm".format(r[0], r[2], r[1], r[3])
