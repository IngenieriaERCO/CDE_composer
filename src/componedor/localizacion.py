"""Imagen de localización en el rótulo (un PNG o JPG exportado de QGIS).

El formato la declara como un campo del rótulo de tipo "imagen" (rotulo_formato.CampoImagen):
el recuadro libre de Localización (sin tapar el título, «ESC:» ni las coordenadas). El plano la
guarda en `rotulo.<campo>` como {"archivo", "bytes", "modificado"} (la ruta, relativa a la
carpeta del plano; tamaño y fecha del archivo cuando se eligió). La imagen nunca va dentro del
plano.json ni de editor.html.

`componer`:
1. Usa el ORIGINAL si existe y coincide (tamaño y fecha, lo que el plano guardó) y deja una
   COPIA al lado del plano: `<plano>_localizacion.<ext>` (si ya está igual, no la reescribe).
   Si el original no está o cambió, usa la copia (si tiene el tamaño que guardó el plano) y lo
   avisa, como con la ortofoto. Si no hay ninguna, no se compone (error claro).
2. La ajusta al recuadro SIN deformarla («contener»): entera, centrada; lo que sobra queda en
   blanco (el papel).
3. Resolución ~300 ppp (`ppp` del campo): un PNG con más se reduce a 300 ppp (sin pérdida); con
   menos no se agranda. Un JPG va TAL CUAL (sin recomprimir), tenga los ppp que tenga.
4. Se pone debajo de los textos del rótulo y se verifica en el PDF guardado (en su sitio
   ±0,1 mm, con los píxeles esperados; el JPG, como JPEG).

Si hay imagen y la escala de localización («ESC:», el campo `campo_escala`) está vacía, sale
«DEFINIR» y se avisa: se escribe a mano.
"""

import shutil
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

from componedor.formato import RectMM
from componedor.ortofoto_fuente import datos_del_archivo, diferencias
from componedor.transformaciones import rect_papel_a_pdf, rect_pdf_a_papel

EXTENSIONES = (".png", ".jpg", ".jpeg")
CLAVES_VALOR = {"archivo", "bytes", "modificado"}
TOL_MM = 0.1
MARGEN_PPP = 1.02  # hasta 2 % sobre el objetivo no se reduce


class LocalizacionInvalida(ValueError):
    """No hay imagen de localización que se pueda poner (mensaje en español)."""


@dataclass
class ImagenLocalizacion:
    campo: str
    archivo: Path  # el que se usó (original o copia)
    origen: str  # "original" o "copia"
    formato: str  # "png" o "jpeg"
    datos: bytes  # lo que entra al PDF
    px_original: tuple[int, int]
    px: tuple[int, int]  # los del PDF (reducida o igual)
    destino: RectMM  # dentro del recuadro, centrada, sin deformar
    ppp: float  # efectivos en el PDF
    copia: Path | None = None  # la copia junto al plano
    avisos: list[str] = field(default_factory=list)


def formato_de(datos: bytes) -> str | None:
    if datos[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if datos[:3] == b"\xff\xd8\xff":
        return "jpeg"
    return None


def copia_junto_al_plano(ruta_plano: Path, extension: str) -> Path:
    ruta_plano = Path(ruta_plano)
    return ruta_plano.parent / f"{ruta_plano.stem}_localizacion{extension.lower()}"


def contener(rect: RectMM, ancho_px: int, alto_px: int) -> RectMM:
    """La imagen entera dentro del recuadro, centrada y sin deformar."""
    ancho, alto = rect[2] - rect[0], rect[3] - rect[1]
    escala = min(ancho / ancho_px, alto / alto_px)  # mm por píxel
    w, h = ancho_px * escala, alto_px * escala
    x0 = rect[0] + (ancho - w) / 2
    y0 = rect[1] + (alto - h) / 2
    return x0, y0, x0 + w, y0 + h


def leer_valor(valor, donde: str, problemas: list[str]) -> dict | None:
    """{"archivo", "bytes"?, "modificado"?} del plano (o None, con sus problemas)."""
    if not isinstance(valor, dict):
        problemas.append(f"{donde}: se esperaba un objeto {{\"archivo\": ...}} (la imagen de "
                         f"localización); tiene {valor!r}")
        return None
    n = len(problemas)
    for clave in sorted(set(valor) - CLAVES_VALOR):
        problemas.append(f"{donde}.{clave}: campo no reconocido (campos válidos: archivo, bytes, "
                         f"modificado)")
    archivo = valor.get("archivo")
    if not isinstance(archivo, str) or not archivo.strip():
        problemas.append(f"{donde}.archivo: se esperaba la ruta de la imagen (texto no vacío)")
    elif Path(archivo).suffix.lower() not in EXTENSIONES:
        problemas.append(f"{donde}.archivo: '{archivo}' no es un .png ni un .jpg")
    b = valor.get("bytes")
    if b is not None and (isinstance(b, bool) or not isinstance(b, int) or b < 0):
        problemas.append(f"{donde}.bytes: se esperaba un entero ≥ 0; tiene {b!r}")
    m = valor.get("modificado")
    if m is not None and not isinstance(m, str):
        problemas.append(f"{donde}.modificado: se esperaba la fecha como texto; tiene {m!r}")
    return valor if len(problemas) == n else None


def _elegir(valor: dict, ruta_plano: Path, donde: str) -> tuple[Path, str, list[str]]:
    """(archivo a usar, "original" | "copia", avisos). LocalizacionInvalida si no hay."""
    original = (Path(ruta_plano).parent / valor["archivo"]).resolve()
    esperado = {"nombre": original.name, "bytes": valor.get("bytes"),
                "modificado": valor.get("modificado")}
    if original.is_file():
        dif = diferencias(esperado, datos_del_archivo(original))
        if not dif:
            return original, "original", []
        motivo = f"«{original}» cambió desde que se eligió ({'; '.join(dif)})"
    else:
        motivo = f"no se encontró «{original}»"
    copia = copia_junto_al_plano(ruta_plano, original.suffix)
    if copia.is_file() and (valor.get("bytes") is None or copia.stat().st_size == valor["bytes"]):
        aviso = (f"{donde}: la imagen de localización original {motivo}: se usó la copia "
                 f"«{copia.name}» de la carpeta del plano.")
        return copia, "copia", [aviso]
    raise LocalizacionInvalida(f"{donde}: la imagen de localización {motivo} y no hay una copia "
                               f"«{copia.name}» que sirva junto al plano. Vuelva a cargarla en el "
                               f"editor («Cargar imagen de localización») y guarde el plano.")


def preparar(campo, valor: dict, ruta_plano: Path, escala_vacia: bool) -> ImagenLocalizacion:
    """Elige el archivo, deja la copia, ajusta y reduce. `campo`: rotulo_formato.CampoImagen."""
    donde = f"rotulo.{campo.nombre}"
    archivo, origen, avisos = _elegir(valor, ruta_plano, donde)
    datos = archivo.read_bytes()
    formato = formato_de(datos)
    if formato is None:
        raise LocalizacionInvalida(f"{donde}: «{archivo.name}» no es un PNG ni un JPG.")
    try:
        pix = pymupdf.Pixmap(datos)
    except (RuntimeError, ValueError) as e:
        raise LocalizacionInvalida(f"{donde}: no se pudo leer «{archivo.name}»: {e}") from None
    px_original = (pix.width, pix.height)
    destino = contener(campo.rect, *px_original)
    pulgadas = (destino[2] - destino[0]) / 25.4
    ppp = px_original[0] / pulgadas
    px = px_original
    if formato == "png" and ppp > campo.ppp * MARGEN_PPP:
        ancho = max(1, round(pulgadas * campo.ppp))
        alto = max(1, round(ancho * px_original[1] / px_original[0]))
        datos = pymupdf.Pixmap(pix, ancho, alto, None).tobytes("png")
        px = (ancho, alto)
        ppp = ancho / pulgadas
    copia = None
    if origen == "original":
        copia = copia_junto_al_plano(ruta_plano, archivo.suffix)
        if not (copia.is_file() and copia.stat().st_size == archivo.stat().st_size
                and copia.read_bytes() == archivo.read_bytes()):
            shutil.copy2(archivo, copia)
    if escala_vacia:
        nombre = campo.campo_escala or "la escala"
        avisos.append(f"rotulo.{nombre}: la imagen de localización no tiene escala: sale "
                      f"«DEFINIR». Escríbala a mano en el editor (Rótulo).")
    return ImagenLocalizacion(campo.nombre, archivo, origen, formato, datos, px_original, px,
                              destino, ppp, copia, avisos)


def insertar(page: pymupdf.Page, alto_hoja_mm: float, img: ImagenLocalizacion) -> None:
    page.insert_image(rect_papel_a_pdf(img.destino, alto_hoja_mm), stream=img.datos,
                      keep_proportion=False)


def verificar(page: pymupdf.Page, img: ImagenLocalizacion | None, alto_hoja_mm: float) -> list[str]:
    """En el PDF guardado: una imagen en su sitio (±0,1 mm), con los píxeles esperados; el JPG
    sin recomprimir (DCTDecode)."""
    if img is None:
        return []
    doc = page.parent
    for info in page.get_images(full=True):
        for r in page.get_image_rects(info[0]):
            rect = rect_pdf_a_papel(r, alto_hoja_mm)
            if max(abs(a - b) for a, b in zip(rect, img.destino)) > TOL_MM:
                continue
            if (info[2], info[3]) != img.px:
                return [(f"imagen de localización: mide {info[2]} × {info[3]} px en el PDF y "
                         f"se esperaban {img.px[0]} × {img.px[1]}")]
            filtro = doc.xref_get_key(info[0], "Filter")[1]
            if img.formato == "jpeg" and "/DCTDecode" not in filtro:
                return ["imagen de localización: el JPG no quedó como JPEG (se recomprimió)"]
            return []
    return [(f"imagen de localización: no está en X {img.destino[0]:.2f} a {img.destino[2]:.2f}, "
             f"Y {img.destino[1]:.2f} a {img.destino[3]:.2f} mm (±{TOL_MM} mm)")]
