"""NOTAS del rótulo: leer, numerar, acomodar en su celda y verificar (subfases 4.2a y 4.2c).

De dónde salen (sección "rotulo" del plano.json, versión 2):
    "notas": {"archivos": ["../notas/generales.txt"],
              "adicionales": ["OTRA NOTA.", {"texto": "NOTA CON VIÑETAS:", "vinetas": ["A", "B"]}]}
Primero las notas de los archivos (en el orden de la lista), luego las adicionales; la
numeración es continua (1, 2, 3, ...) y la pone el componedor. Las viñetas no se numeran.

Archivo de notas (.txt): UTF-8 (con o sin BOM), UNA NOTA POR LÍNEA. Se ignoran las líneas en
blanco y las que empiezan con "#" (comentarios). Si una línea ya trae su número ("3. ...",
"3) ..."), se quita con advertencia ("3.5 M" no es un número de nota: falta el espacio). Una
línea que empieza con "- " es una VIÑETA de la nota anterior del mismo archivo (error si no
hay ninguna nota antes).

Cómo se acomodan:
- Número a la izquierda ("1.", ..., "12.") y texto con SANGRÍA FRANCESA: las líneas que siguen
  de la misma nota empiezan donde empieza el texto, no bajo el número. La sangría es el ancho
  del número más largo y un espacio.
- Viñetas: "•" donde empieza el texto de la nota y el texto de la viñeta un poco más adentro
  (ancho de "• "), también con sangría francesa. Entre la nota y sus viñetas, y entre viñetas,
  no hay espacio extra.
- Corte por palabras (`maquetacion.partir_en_lineas`). Entre nota y nota (después de la última
  viñeta), `separacion_notas` renglones de más (medio renglón en A1 ERCO).
- El bloque va PEGADO ARRIBA de la celda (con el relleno), no centrado.
- Si no caben, TODAS bajan juntas de 0,1 en 0,1 mm hasta `altura_min_mm`, con advertencia. Si
  ni así caben: error con el campo, el tamaño y desde qué nota ya no caben.

Verificación en el PDF guardado: cada línea pasa por `textos_pdf.verificar_textos` (posición y
dentro de la celda, ±0,1 mm) y además `verificar_notas` comprueba que en la celda se leen
tantas líneas como se escribieron (con las viñetas) y que la numeración es 1...N sin saltos
(las viñetas no cuentan).
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

from componedor.fuente import Fuente
from componedor.maquetacion import (
    EPS_MM,
    Linea,
    TextoMaquetado,
    TextoNoCabe,
    alturas_a_probar,
    partir_en_lineas,
)
from componedor.rotulo_formato import CampoNotas
from componedor.textos_pdf import TOL_MM, caracteres_de_pagina, leer_linea
from componedor.transformaciones import rect_papel_a_pdf
from componedor.unidades import mm_a_pt

CLAVES = {"archivos", "adicionales"}
CLAVES_ADICIONAL = {"texto", "vinetas"}
NUMERO_PROPIO = re.compile(r"^(\d+)\s*[.)]\s+")  # "3. texto" o "3) texto"; no "3.5 M"
VINETA = "- "  # en los .txt
SIGNO_VINETA = "•"  # en el plano


@dataclass(frozen=True)
class Nota:
    texto: str
    origen: str  # "generales.txt, línea 4" o "adicionales[0]"
    vinetas: tuple[str, ...] = ()


@dataclass
class NotasMaquetadas:
    textos: list[TextoMaquetado]  # uno por nota: su número, sus líneas y sus viñetas
    altura_mm: float
    reducido_desde: float | None
    celda_mm: tuple[float, float, float, float]
    notas: list[Nota] = field(default_factory=list)
    lineas: int = 0  # líneas de texto escritas (notas y viñetas; número y "•" van en ellas)


# --- leer ------------------------------------------------------------------------------------

def leer_notas(valor, carpeta: Path | None) -> tuple[list[Nota], list[str], list[str]]:
    """El valor "notas" del plano -> (notas en orden, advertencias, problemas). Las rutas son
    relativas a `carpeta` (la del plano.json)."""
    notas, avisos, problemas = [], [], []
    if not isinstance(valor, dict):
        return [], [], [f"rotulo.notas: se esperaba {{\"archivos\": [...], \"adicionales\": "
                         f"[...]}}; tiene {_tipo(valor)}"]
    for clave in sorted(set(valor) - CLAVES):
        problemas.append(f"rotulo.notas.{clave}: campo no reconocido (campos válidos: "
                         f"adicionales, archivos)")
    archivos = valor.get("archivos", [])
    if not isinstance(archivos, list) or not all(isinstance(v, str) for v in archivos):
        problemas.append(f"rotulo.notas.archivos: se esperaba una lista de textos; tiene "
                         f"{_tipo(archivos)}")
        archivos = []
    adicionales = valor.get("adicionales", [])
    if not isinstance(adicionales, list):
        problemas.append(f"rotulo.notas.adicionales: se esperaba una lista de textos u objetos "
                         f"{{\"texto\", \"vinetas\"}}; tiene {_tipo(adicionales)}")
        adicionales = []
    for i, texto in enumerate(archivos):
        ruta = Path(texto)
        if not ruta.is_absolute() and carpeta is not None:
            ruta = carpeta / ruta
        n, a, p = leer_archivo_notas(ruta, f"rotulo.notas.archivos[{i}]")
        notas += n
        avisos += a
        problemas += p
    for i, item in enumerate(adicionales):
        nota, aviso = _adicional(item, i, problemas)
        if nota is not None:
            notas.append(nota)
        if aviso:
            avisos.append(aviso)
    return notas, avisos, problemas


def leer_archivo_notas(ruta: Path, donde: str = "rotulo.notas") -> tuple[list[Nota], list[str],
                                                                          list[str]]:
    """Notas de un .txt (una por línea; "- " = viñeta de la anterior) -> (notas, advertencias,
    problemas)."""
    if not ruta.is_file():
        return [], [], [f"{donde}: no se encontró el archivo de notas '{ruta}'"]
    try:
        contenido = ruta.read_bytes().decode("utf-8-sig")
    except UnicodeDecodeError as e:
        return [], [], [f"{donde}: el archivo '{ruta}' no está en UTF-8 (byte inválido en la "
                        f"posición {e.start}); guárdelo como «UTF-8» en el Bloc de notas"]
    notas, avisos, problemas = [], [], []
    for n, linea in enumerate(contenido.splitlines(), start=1):
        limpia = linea.strip()
        if not limpia or limpia.startswith("#"):
            continue
        if linea.lstrip().startswith(VINETA) or limpia == "-":
            vineta = " ".join(limpia[1:].split())
            if not notas:
                problemas.append(f"{donde}: la línea {n} de '{ruta.name}' es una viñeta "
                                 f"(«{limpia}») y no hay ninguna nota antes en ese archivo; "
                                 f"una viñeta va debajo de su nota")
            elif vineta:
                notas[-1] = Nota(notas[-1].texto, notas[-1].origen,
                                 notas[-1].vinetas + (vineta,))
            continue
        nota, aviso = _nota(linea, f"{ruta.name}, línea {n}")
        if nota is not None:
            notas.append(nota)
        if aviso:
            avisos.append(aviso)
    if not notas and not problemas:
        return [], avisos, [f"{donde}: el archivo '{ruta}' no tiene notas (solo líneas en blanco "
                            f"o comentarios con #)"]
    return notas, avisos, problemas


def _adicional(item, i: int, problemas: list[str]) -> tuple[Nota | None, str]:
    """Una nota adicional: un texto, o {"texto": "...", "vinetas": ["...", ...]}."""
    donde = f"rotulo.notas.adicionales[{i}]"
    if isinstance(item, str):
        if "\n" in item:
            problemas.append(f"{donde}: una nota adicional va en una sola línea (trae un salto "
                             f"de línea); para varias notas use varios textos en la lista")
            return None, ""
        return _nota(item, f"adicionales[{i}]")
    if not isinstance(item, dict):
        problemas.append(f"{donde}: se esperaba un texto o {{\"texto\": ..., \"vinetas\": "
                         f"[...]}}; tiene {_tipo(item)}")
        return None, ""
    n = len(problemas)
    for clave in sorted(set(item) - CLAVES_ADICIONAL):
        problemas.append(f"{donde}.{clave}: campo no reconocido (campos válidos: texto, vinetas)")
    texto = item.get("texto")
    if not isinstance(texto, str) or not texto.strip() or "\n" in texto:
        problemas.append(f"{donde}.texto: se esperaba el texto de la nota (una línea, no vacío); "
                         f"tiene {_tipo(texto)}")
    vinetas = item.get("vinetas", [])
    if (not isinstance(vinetas, list)
            or not all(isinstance(v, str) and "\n" not in v for v in vinetas)):
        problemas.append(f"{donde}.vinetas: se esperaba una lista de textos de una línea; tiene "
                         f"{_tipo(vinetas)}")
    if len(problemas) > n:
        return None, ""
    nota, aviso = _nota(texto, f"adicionales[{i}]")
    limpias = tuple(" ".join(v.split()) for v in vinetas if v.strip())
    return (Nota(nota.texto, nota.origen, limpias) if nota else None), aviso


def _nota(texto: str, origen: str) -> tuple[Nota | None, str]:
    """Una línea de texto -> nota (sin el número que traiga) y la advertencia si lo traía."""
    texto = " ".join(texto.split())
    if not texto:
        return None, ""
    numero = NUMERO_PROPIO.match(texto)
    if numero:
        texto = texto[numero.end():]
        return Nota(texto, origen), (
            f"Advertencia: la nota de {origen} traía su propio número «{numero.group(0).strip()}»;"
            f" se quitó: el componedor numera las notas solo.")
    return Nota(texto, origen), ""


# --- acomodar en la celda --------------------------------------------------------------------

def maquetar_notas(campo: CampoNotas, notas: list[Nota], fuente: Fuente, relleno_mm: float,
                   interlineado: float) -> NotasMaquetadas:
    """Numera y acomoda las notas (y sus viñetas) arriba de la celda. Lanza `TextoNoCabe`."""
    celda = campo.celda
    if not notas:
        return NotasMaquetadas([], celda.altura_mm, None, celda.rect, [])
    problema = ""
    for altura in alturas_a_probar(celda):
        textos, lineas, problema = _a_altura(campo, notas, fuente, relleno_mm, interlineado,
                                             altura)
        if not problema:
            reducido = celda.altura_mm if altura < celda.altura_mm - EPS_MM else None
            return NotasMaquetadas(textos, altura, reducido, celda.rect, list(notas), lineas)
    raise TextoNoCabe(problema)


def _partes(nota: Nota, fuente: Fuente, altura: float, ancho_texto: float,
            ancho_vineta: float) -> list[tuple[str, int, list[str]]]:
    """[("nota" | "vineta", índice de viñeta, líneas)] de una nota a esa altura."""
    partes = [("nota", 0, partir_en_lineas([nota.texto], ancho_texto, altura, fuente))]
    for j, vineta in enumerate(nota.vinetas, start=1):
        partes.append(("vineta", j, partir_en_lineas([vineta], ancho_texto - ancho_vineta,
                                                     altura, fuente)))
    return partes


def _a_altura(campo: CampoNotas, notas: list[Nota], fuente: Fuente, relleno: float,
              interlineado: float, altura: float) -> tuple[list[TextoMaquetado], int, str]:
    """Las notas a una altura dada (textos, líneas escritas) o por qué no caben."""
    x0, y0, x1, y1 = campo.celda.rect
    minima = (" (la mínima permitida)" if campo.celda.altura_min_mm < campo.celda.altura_mm
              else "")
    sangria = fuente.ancho_mm(f"{len(notas)}. ", altura)
    ancho_texto = (x1 - x0) - 2 * relleno - sangria
    ancho_vineta = fuente.ancho_mm(f"{SIGNO_VINETA} ", altura)
    x_texto = x0 + relleno + sangria
    paso = interlineado * altura
    tope = y1 - relleno - altura  # base de la primera línea (mayúsculas pegadas arriba)
    piso = y0 + relleno  # la base de la última línea no puede bajar de aquí
    todas = [_partes(n, fuente, altura, ancho_texto, ancho_vineta) for n in notas]
    total = sum(len(lineas) for partes in todas for _, _, lineas in partes)

    base = tope
    textos = []
    for k, (nota, partes) in enumerate(zip(notas, todas), start=1):
        colocadas = [Linea(f"{k}.", (x0 + relleno, base), fuente.ancho_mm(f"{k}.", altura))]
        for tipo, j, lineas in partes:
            x = x_texto if tipo == "nota" else x_texto + ancho_vineta
            disponible = ancho_texto if tipo == "nota" else ancho_texto - ancho_vineta
            for linea in lineas:
                ancho = fuente.ancho_mm(linea, altura)
                if ancho > disponible + EPS_MM:
                    que = f"nota {k}" + (f", viñeta {j}" if tipo == "vineta" else "")
                    de = "de las notas" if tipo == "nota" else "de las viñetas"
                    return [], 0, (f"campo 'notas', {que} ({nota.origen}): «{linea}» mide "
                                   f"{ancho:.1f} mm y el ancho para el texto {de} es "
                                   f"{disponible:.1f} mm (altura {altura:.1f} mm{minima})")
            if base - (len(lineas) - 1) * paso < piso - EPS_MM:
                ocupado = (y1 - relleno) - (tope - (total - 1) * paso
                                            - (len(notas) - 1) * campo.separacion_notas * paso)
                return [], 0, (f"campo 'notas': {len(notas)} notas ({total} líneas a "
                               f"{altura:.1f} mm{minima}) ocupan {ocupado:.1f} mm de alto y la "
                               f"celda permite {(y1 - y0) - 2 * relleno:.1f} mm; no caben desde "
                               f"la nota {k} ({nota.origen}): «{nota.texto}»")
            if tipo == "vineta":
                colocadas.append(Linea(SIGNO_VINETA, (x_texto, base),
                                       fuente.ancho_mm(SIGNO_VINETA, altura)))
            for i, linea in enumerate(lineas):
                colocadas.append(Linea(linea, (x, base - i * paso),
                                       fuente.ancho_mm(linea, altura)))
            base -= len(lineas) * paso
        textos.append(TextoMaquetado(f"notas.{k}", tuple(colocadas), altura,
                                     celda_mm=campo.celda.rect))
        base -= campo.separacion_notas * paso  # medio renglón solo entre notas
    return textos, total, ""


# --- verificar en el PDF ---------------------------------------------------------------------

def verificar_notas(page: pymupdf.Page, maquetadas: NotasMaquetadas,
                    alto_hoja_mm: float) -> list[str]:
    """Líneas leídas en la celda = líneas escritas, y numeración 1...N sin saltos (las viñetas
    no se numeran)."""
    if not maquetadas.textos:
        return []
    caracteres = caracteres_de_pagina(page)
    problemas = []
    numeros = [leer_linea(caracteres, t.lineas[0], alto_hoja_mm)[0] for t in maquetadas.textos]
    esperados = [f"{k}." for k in range(1, len(maquetadas.textos) + 1)]
    if numeros != esperados:
        problemas.append(f"notas: la numeración leída en el PDF es {numeros} y debía ser "
                         f"{esperados[0]} a {esperados[-1]} sin saltos")
    celda = rect_papel_a_pdf(maquetadas.celda_mm, alto_hoja_mm)
    tol = mm_a_pt(TOL_MM)
    bases = sorted(y for c, x, y, _ in caracteres
                   if not c.isspace() and celda.x0 - tol <= x <= celda.x1 + tol
                   and celda.y0 - tol <= y <= celda.y1 + tol)
    leidas = sum(1 for i, y in enumerate(bases) if i == 0 or y - bases[i - 1] > tol)
    if leidas != maquetadas.lineas:
        problemas.append(f"notas: se escribieron {maquetadas.lineas} líneas y en la celda del "
                         f"PDF se leen {leidas}")
    return problemas


def _tipo(valor) -> str:
    if valor is None:
        return "null"
    if isinstance(valor, str):
        return f"texto {valor!r}"
    if isinstance(valor, list):
        return "una lista con elementos que no son texto"
    if isinstance(valor, dict):
        return "un objeto"
    return f"{type(valor).__name__} {valor!r}"
