"""Integridad del paquete: ¿el PDF es exactamente el que describe su manifiesto?

Comprobaciones, en este orden (ver docs/contrato_paquete.md):
  a) el PDF existe y es un archivo;
  b) su tamaño en bytes es igual a pdf.bytes;
  c) su SHA-256 es igual a pdf.sha256 (lectura por bloques);
  d) abre con PyMuPDF, sin daños (no hubo que repararlo) y sin cifrar;
  e) tiene 1 página y pdf.page_count también dice 1.
Se detiene solo cuando seguir es imposible: sin PDF no hay nada que medir, y si no abre no
se pueden contar sus páginas. Un tamaño distinto no impide calcular el hash.

NO compara tamaño de página, escala ni matriz (subfase 2.4).
"""

import hashlib
from pathlib import Path

import pymupdf

from componedor.paquete import COMPLETO, Paquete
from componedor.validacion import Comprobacion, ResultadoVerificacion

BLOQUE_BYTES = 1024 * 1024  # el PDF se lee de a 1 MB, nunca entero en memoria
SECCION = "Integridad"


ResultadoIntegridad = ResultadoVerificacion  # mismo resultado que la coherencia


def sha256_archivo(ruta: Path, bloque: int = BLOQUE_BYTES) -> str:
    """SHA-256 en hexadecimal, leyendo el archivo por bloques."""
    digest = hashlib.sha256()
    with open(ruta, "rb") as archivo:
        while datos := archivo.read(bloque):
            digest.update(datos)
    return digest.hexdigest()


def verificar_integridad(paquete: Paquete) -> ResultadoIntegridad:
    """Comprueba el PDF de un paquete completo contra su manifiesto. No lanza errores."""
    if paquete.estado != COMPLETO:
        return ResultadoIntegridad(paquete.prefijo, False,
                                   motivo=f"no verificable (paquete {paquete.estado})")

    resultado = ResultadoIntegridad(paquete.prefijo, True)
    agregar = resultado.comprobaciones.append
    pdf = paquete.manifiesto.pdf
    ruta = paquete.ruta_pdf

    # a) existe
    existe = ruta is not None and ruta.is_file()
    agregar(_comprobacion("El PDF existe", existe, str(ruta), "existe" if existe else "no existe",
                          "" if existe else f"no se encuentra el PDF '{ruta}'"))
    if not existe:
        return resultado

    # b) tamaño en bytes
    tamano = ruta.stat().st_size
    tamano_ok = tamano == pdf.bytes
    agregar(_comprobacion(
        "Tamaño en bytes", tamano_ok, f"{pdf.bytes} bytes", f"{tamano} bytes",
        "" if tamano_ok else f"el PDF tiene {tamano} bytes y el manifiesto dice {pdf.bytes}: "
                             f"el archivo fue modificado o está incompleto"))

    # c) SHA-256
    try:
        digest = sha256_archivo(ruta)
    except OSError as e:
        agregar(_comprobacion("SHA-256", False, pdf.sha256, "no se pudo leer",
                              f"no se pudo leer el PDF: {e}"))
        return resultado
    hash_ok = digest == pdf.sha256
    if hash_ok:
        detalle = ""
    elif tamano_ok:
        detalle = "el contenido del PDF cambió después de exportarse (mismo tamaño, otro SHA-256)"
    else:
        detalle = "el SHA-256 tampoco coincide (era de esperar: el tamaño ya es distinto)"
    agregar(_comprobacion("SHA-256", hash_ok, pdf.sha256, digest, detalle))

    # d) abre con PyMuPDF, sin daños ni cifrado
    try:
        doc = pymupdf.open(ruta)
    except (pymupdf.FileDataError, RuntimeError, ValueError) as e:
        agregar(_comprobacion("Abre como PDF", False, "PDF legible", "no abre",
                              f"PyMuPDF no puede abrir el archivo: {e}"))
        return resultado
    try:
        if not doc.is_pdf:
            motivo = "el archivo no es un PDF"
        elif doc.needs_pass or doc.is_encrypted:
            motivo = "el PDF está cifrado o protegido con contraseña"
        elif doc.is_repaired:
            motivo = "el PDF está dañado (PyMuPDF tuvo que repararlo al abrirlo)"
        else:
            motivo = ""
        agregar(_comprobacion("Abre como PDF", not motivo, "PDF legible, sin daños ni cifrado",
                              "no" if motivo else "sí", motivo))
        if motivo:
            return resultado

        # e) una sola página
        paginas = doc.page_count
    finally:
        doc.close()
    paginas_ok = paginas == 1 and pdf.paginas == 1
    if paginas_ok:
        detalle = ""
    elif paginas != pdf.paginas:
        detalle = (f"el PDF tiene {paginas} página(s) y el manifiesto dice {pdf.paginas}: "
                   f"un detalle es una sola página")
    else:
        detalle = f"el PDF y el manifiesto dicen {paginas} páginas: un detalle es una sola página"
    agregar(_comprobacion("Una sola página", paginas_ok, f"1 (manifiesto: {pdf.paginas})",
                          str(paginas), detalle))
    return resultado


def _comprobacion(nombre: str, pasa: bool, esperado: str, medido: str,
                  detalle: str) -> Comprobacion:
    return Comprobacion(SECCION, nombre, pasa, esperado, medido, "exacto", detalle)
