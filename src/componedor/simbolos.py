"""Biblioteca de símbolos de CONVENCIONES (subfase 4.2b).

Los símbolos se copian como VECTORES desde un plano real de ERCO que ya trae la leyenda
(misma rejilla que el rótulo v2) y se guardan en una biblioteca PDF pequeña, una página por
símbolo, con un índice:

    simbolos/indice.json          (se versiona: ids, descripciones, medidas)
    simbolos/convenciones_erco.pdf (NO se versiona: sale de un plano de ERCO)

indice.json (versión 1):
    {"version": 1, "biblioteca": "convenciones_erco.pdf",
     "origen": {"plano": "...pdf", "pagina": 1, "margen_mm": 0.5},
     "simbolos": [{"id": "corte", "descripcion": "CORTE", "casilla_origen": 11,
                   "pagina": 11, "rect_mm": [x0, y0, x1, y1], "trazos": 5}, ...]}
`casilla_origen` es la casilla de la leyenda del plano de origen (1 a 12 la columna izquierda
de arriba abajo, 13 a 24 la derecha); `rect_mm` la caja del dibujo del símbolo en ese plano
(mm de papel) y `trazos` cuántos trazos tiene (para verificar). `opacidad` (opcional, 0 a 1,
por defecto 1) dibuja el símbolo con transparencia al colocarlo (subfase 4.2c): sigue siendo
vector y sus trazos no cambian; `extraer-simbolos` la conserva al regenerar.

`extraer_simbolos` (comando `extraer-simbolos`, una sola vez):
  1. normaliza la página del plano (quita /Rotate, como `colocar.insertar_pagina`);
  2. mide en cada casilla los trazos COMPLETAMENTE dentro de ella (±0,3 mm);
  3. con redacciones borra todo lo que no es la columna de símbolos y, por cada símbolo, todo
     lo que está fuera de su caja + un margen (0,5 mm; más si hace falta para no borrar trazos
     del propio símbolo, ver `_simbolo_solo`). `show_pdf_page` con `clip` NO quita contenido:
     solo lo oculta; por eso se redacta;
  4. copia cada símbolo a una página de la biblioteca del tamaño de su caja + 0,5 mm;
  5. verifica en la biblioteca guardada: mismos trazos y misma caja (±0,1 mm).

Al componer, cada símbolo se coloca centrado en su casilla con `show_pdf_page`, nunca
agrandado: f = min(1, ancho_útil / ancho, alto_útil / alto) (útil = casilla menos el relleno).
Se verifica en el PDF: trazos en la casilla = trazos del índice y caja = la esperada (±0,1 mm).
"""

import json
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from componedor.colocar import abrir_pdf, insertar_pagina, tamano_visible_mm
from componedor.formato import Formato, RectMM
from componedor.hoja import crear_pagina
from componedor.rotulo_formato import CampoConvenciones
from componedor.transformaciones import rect_papel_a_pdf, rect_pdf_a_papel

VERSION = 1
NOMBRE_PDF = "convenciones_erco.pdf"
MARGEN_MM = 0.5  # alrededor del dibujo en cada página de la biblioteca
MARGENES_REDACCION_MM = (0.5, 1.0, 2.0, 3.0)  # para aislar un símbolo (ver _simbolo_solo)
TOL_MM = 0.1  # verificación
TOL_CASILLA_MM = 0.3  # qué trazos son de una casilla del plano de origen
TOL_TAMANO_MM = 0.5  # el plano de origen debe ser de la misma hoja
COMO_GENERAR = ("Genérela con: python -m componedor.cli extraer-simbolos <plano.pdf> "
                "--formato formatos/A1_ERCO.json")


class BibliotecaInvalida(ValueError):
    """Falta la biblioteca o su índice, o no se pueden usar (el mensaje dice cómo arreglarlo)."""


class ExtraccionFallida(ValueError):
    """No se pudo armar la biblioteca a partir del plano."""


@dataclass(frozen=True)
class Simbolo:
    id: str
    descripcion: str
    casilla_origen: int
    pagina: int  # 1, 2, ... en la biblioteca
    rect_mm: RectMM  # caja del dibujo en el plano de origen
    trazos: int
    opacidad: float = 1.0  # 0 < opacidad <= 1; se aplica al colocarlo (sigue siendo vector)

    @property
    def tamano_mm(self) -> tuple[float, float]:
        return self.rect_mm[2] - self.rect_mm[0], self.rect_mm[3] - self.rect_mm[1]


@dataclass(frozen=True)
class Biblioteca:
    ruta_indice: Path
    ruta_pdf: Path
    margen_mm: float
    simbolos: dict[str, Simbolo]  # en el orden del índice


@dataclass(frozen=True)
class ColocacionSimbolo:
    simbolo: Simbolo
    posicion: int  # 1..24: casilla de la convención en el rótulo
    casilla: RectMM
    escala: float  # f (1 = sin reducir)
    destino_pagina: RectMM  # dónde va la página del símbolo (con su margen), mm de papel
    destino_dibujo: RectMM  # dónde debe quedar el dibujo, mm de papel


@dataclass
class InformeExtraccion:
    ruta_pdf: Path
    ruta_indice: Path
    simbolos: list[Simbolo]
    omitidas: list[int]  # casillas con dibujo que no están en el índice


# --- leer la biblioteca --------------------------------------------------------------------

def cargar_biblioteca(ruta_indice: Path | str) -> Biblioteca:
    """Lee y revisa indice.json y que el PDF de la biblioteca exista. Lanza
    `BibliotecaInvalida` con un mensaje que dice qué falta y cómo generarlo."""
    ruta_indice = Path(ruta_indice)
    if not ruta_indice.is_file():
        raise BibliotecaInvalida(
            f"no se encontró el índice de símbolos '{ruta_indice}'. {COMO_GENERAR}")
    try:
        datos = json.loads(ruta_indice.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise BibliotecaInvalida(f"el índice de símbolos '{ruta_indice}' no es un JSON UTF-8 "
                                 f"válido: {e}") from e
    if not isinstance(datos, dict) or datos.get("version") != VERSION:
        raise BibliotecaInvalida(f"el índice de símbolos '{ruta_indice}' no es versión {VERSION}")
    lista = datos.get("simbolos")
    if not isinstance(lista, list) or not lista:
        raise BibliotecaInvalida(f"el índice '{ruta_indice}' no tiene símbolos")
    simbolos, sin_medir = {}, []
    for item in lista:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise BibliotecaInvalida(f"el índice '{ruta_indice}' tiene un símbolo sin id: {item!r}")
        if not all(k in item for k in ("pagina", "rect_mm", "trazos")):
            sin_medir.append(item["id"])
            continue
        simbolos[item["id"]] = Simbolo(item["id"], str(item.get("descripcion", "")),
                                       int(item.get("casilla_origen", 0)), int(item["pagina"]),
                                       tuple(float(v) for v in item["rect_mm"]),
                                       int(item["trazos"]), _opacidad(item, ruta_indice))
    if sin_medir:
        raise BibliotecaInvalida(f"en el índice '{ruta_indice}' hay símbolos sin medir "
                                 f"({', '.join(sin_medir)}). {COMO_GENERAR}")
    ruta_pdf = ruta_indice.parent / str(datos.get("biblioteca", NOMBRE_PDF))
    if not ruta_pdf.is_file():
        raise BibliotecaInvalida(
            f"no se encontró la biblioteca de símbolos '{ruta_pdf}' (va junto a "
            f"'{ruta_indice.name}' y no se versiona). {COMO_GENERAR}")
    with pymupdf.open(ruta_pdf) as doc:
        paginas = doc.page_count
    fuera = [s.id for s in simbolos.values() if not 1 <= s.pagina <= paginas]
    if fuera:
        raise BibliotecaInvalida(f"la biblioteca '{ruta_pdf}' tiene {paginas} páginas y el índice "
                                 f"pide otras para {', '.join(fuera)}. {COMO_GENERAR}")
    margen = float(datos.get("origen", {}).get("margen_mm", MARGEN_MM))
    return Biblioteca(ruta_indice, ruta_pdf, margen, simbolos)


def _opacidad(item: dict, ruta_indice: Path) -> float:
    """"opacidad" opcional de un símbolo del índice: número con 0 < opacidad <= 1 (defecto 1)."""
    valor = item.get("opacidad", 1)
    if (not isinstance(valor, (int, float)) or isinstance(valor, bool)
            or not 0 < valor <= 1):
        raise BibliotecaInvalida(f"en el índice '{ruta_indice}', la opacidad del símbolo "
                                 f"'{item['id']}' debe ser un número mayor que 0 y hasta 1 "
                                 f"(1 = opaco); tiene {valor!r}")
    return float(valor)


# --- colocar y verificar -------------------------------------------------------------------

def colocar_simbolo(simbolo: Simbolo, posicion: int, casilla: RectMM, relleno_mm: float,
                    margen_mm: float) -> ColocacionSimbolo:
    """Centrado en la casilla y, si no cabe en el espacio útil, reducido (nunca agrandado)."""
    ancho, alto = simbolo.tamano_mm
    util_x = casilla[2] - casilla[0] - 2 * relleno_mm
    util_y = casilla[3] - casilla[1] - 2 * relleno_mm
    f = min(1.0, util_x / ancho if ancho > 0 else 1.0, util_y / alto if alto > 0 else 1.0)
    cx, cy = (casilla[0] + casilla[2]) / 2, (casilla[1] + casilla[3]) / 2
    dibujo = (cx - ancho * f / 2, cy - alto * f / 2, cx + ancho * f / 2, cy + alto * f / 2)
    m = margen_mm * f
    pagina = (dibujo[0] - m, dibujo[1] - m, dibujo[2] + m, dibujo[3] + m)
    return ColocacionSimbolo(simbolo, posicion, casilla, f, pagina, dibujo)


def dibujar_simbolos(page: pymupdf.Page, colocaciones: list[ColocacionSimbolo],
                     biblioteca: Biblioteca, alto_hoja_mm: float) -> None:
    """Copia cada símbolo (vector) de la biblioteca a su sitio en la hoja."""
    if not colocaciones:
        return
    with pymupdf.open(biblioteca.ruta_pdf) as doc:
        for c in colocaciones:
            origen = doc[c.simbolo.pagina - 1]
            destino = rect_papel_a_pdf(c.destino_pagina, alto_hoja_mm)
            if c.simbolo.opacidad < 1:
                with con_opacidad(doc, c.simbolo.pagina - 1, c.simbolo.opacidad) as transparente:
                    page.show_pdf_page(destino, transparente, 0, clip=transparente[0].rect)
            else:
                page.show_pdf_page(destino, doc, c.simbolo.pagina - 1, clip=origen.rect)


def con_opacidad(doc: pymupdf.Document, pagina: int, opacidad: float) -> pymupdf.Document:
    """Página intermedia con el símbolo dentro de un estado gráfico de opacidad
    (ExtGState /CA y /ca): `q /GSopacidad gs ... Q`. Los trazos no cambian y siguen siendo
    vector; solo se dibujan con transparencia. `show_pdf_page` no tiene parámetro de opacidad."""
    origen = doc[pagina]
    nuevo = pymupdf.open()
    page = nuevo.new_page(width=origen.rect.width, height=origen.rect.height)
    page.show_pdf_page(page.rect, doc, pagina)
    tipo, valor = nuevo.xref_get_key(page.xref, "Resources")
    recursos = int(valor.split()[0]) if tipo == "xref" else page.xref
    clave = "ExtGState/GSopacidad" if tipo == "xref" else "Resources/ExtGState/GSopacidad"
    nuevo.xref_set_key(recursos, clave, f"<</Type/ExtGState/CA {opacidad:g}/ca {opacidad:g}>>")
    contenidos = page.get_contents()
    actual = b"".join(nuevo.xref_stream(x) for x in contenidos)
    nuevo.update_stream(contenidos[0], b"q /GSopacidad gs\n" + actual + b"\nQ")
    for x in contenidos[1:]:
        nuevo.update_stream(x, b"")
    return nuevo


def verificar_simbolos(page: pymupdf.Page, colocaciones: list[ColocacionSimbolo],
                       alto_hoja_mm: float) -> list[str]:
    """En el PDF: trazos en la casilla = trazos del índice; caja = la esperada y dentro de la
    casilla (±0,1 mm)."""
    trazos = [(rect_pdf_a_papel(d["rect"], alto_hoja_mm), d) for d in page.get_drawings()]
    problemas = []
    for c in colocaciones:
        donde = f"convenciones, casilla {c.posicion} ('{c.simbolo.id}')"
        mios = [(r, d) for r, d in trazos if _dentro(r, c.casilla, TOL_MM)]
        propios = [r for r, _ in mios]
        if len(propios) != c.simbolo.trazos:
            problemas.append(f"{donde}: en la casilla hay {len(propios)} trazos y el símbolo "
                             f"tiene {c.simbolo.trazos}")
            continue
        if c.simbolo.opacidad < 1:
            # Transparencia aplicada: ningún trazo más opaco que lo pedido (±0,01).
            leida = max(max(d.get("fill_opacity") or 0, d.get("stroke_opacity") or 0)
                        for _, d in mios)
            if leida > c.simbolo.opacidad + 0.01:
                problemas.append(f"{donde}: el símbolo debía tener opacidad "
                                 f"{c.simbolo.opacidad:g} y en el PDF tiene {leida:g}")
        caja = _union(propios)
        dif = max(abs(a - b) for a, b in zip(caja, c.destino_dibujo))
        if dif > TOL_MM:
            problemas.append(f"{donde}: el símbolo quedó en {_mm(caja)} y debía quedar en "
                             f"{_mm(c.destino_dibujo)} (diferencia máx. {dif:.3f} mm, tolerancia "
                             f"±{TOL_MM} mm)")
    return problemas


# --- extraer del plano real ---------------------------------------------------------------

def extraer_simbolos(ruta_plano: Path | str, formato: Formato, ruta_indice: Path | str,
                     pagina: int = 1) -> InformeExtraccion:
    """Arma la biblioteca (PDF + indice.json) a partir de la leyenda del plano. Si el índice ya
    existe, conserva sus ids y descripciones y mide la casilla de origen de cada uno; si no,
    crea uno con ids provisionales (simbolo_01, ...). Lanza `ExtraccionFallida`."""
    campo = _campo_convenciones(formato)
    ruta_indice = Path(ruta_indice)
    entradas = _entradas_del_indice(ruta_indice)
    origen = abrir_pdf(ruta_plano, "el plano", ExtraccionFallida)
    try:
        if not 1 <= pagina <= origen.page_count:
            raise ExtraccionFallida(f"el plano tiene {origen.page_count} página(s); no existe la "
                                    f"página {pagina}")
        ancho, alto = tamano_visible_mm(origen[pagina - 1])
        if abs(ancho - formato.ancho_mm) > TOL_TAMANO_MM or abs(alto - formato.alto_mm) > TOL_TAMANO_MM:
            raise ExtraccionFallida(
                f"la página {pagina} del plano mide {ancho:.2f} x {alto:.2f} mm y la hoja del "
                f"formato {formato.ancho_mm:.1f} x {formato.alto_mm:.1f} mm: la leyenda no estaría "
                f"en la rejilla del formato")
        hoja = crear_pagina(formato.ancho_mm, formato.alto_mm)
        insertar_pagina(hoja[0], formato, origen, pagina - 1, (0.0, 0.0))  # quita /Rotate
    finally:
        origen.close()
    try:
        medidas = _medir_casillas(hoja[0], campo, formato.alto_mm)
        if not entradas:
            entradas = [{"id": f"simbolo_{k:02d}", "descripcion": "", "casilla_origen": k}
                        for k in sorted(medidas)]
        faltan = [e for e in entradas if e["casilla_origen"] not in medidas]
        if faltan:
            raise ExtraccionFallida(
                "en el plano no hay dibujo en la casilla de origen de: "
                + ", ".join(f"'{e['id']}' (casilla {e['casilla_origen']})" for e in faltan))
        usadas = {e["casilla_origen"] for e in entradas}
        simbolos = [Simbolo(e["id"], e["descripcion"], e["casilla_origen"], i,
                            medidas[e["casilla_origen"]][0], medidas[e["casilla_origen"]][1],
                            e.get("opacidad", 1.0))
                    for i, e in enumerate(entradas, start=1)]
        ruta_pdf = ruta_indice.parent / NOMBRE_PDF
        _armar_biblioteca(hoja, campo, simbolos, formato, ruta_pdf)
    finally:
        hoja.close()
    problemas = _verificar_biblioteca(ruta_pdf, simbolos)
    if problemas:
        ruta_pdf.unlink(missing_ok=True)
        raise ExtraccionFallida("la biblioteca no quedó igual al plano; no se guardó:\n"
                                + "\n".join(f"- {p}" for p in problemas))
    _escribir_indice(ruta_indice, simbolos, Path(ruta_plano).name, pagina)
    return InformeExtraccion(ruta_pdf, ruta_indice, simbolos,
                             sorted(set(medidas) - usadas))


def _campo_convenciones(formato: Formato) -> CampoConvenciones:
    campos = formato.rotulo.campos.values() if formato.rotulo else []
    campo = next((c for c in campos if isinstance(c, CampoConvenciones)), None)
    if campo is None:
        raise ExtraccionFallida("el formato no tiene un campo de tipo \"convenciones\" en su "
                                "sección \"rotulo\": no se sabe dónde está la leyenda")
    return campo


def _entradas_del_indice(ruta: Path) -> list[dict]:
    """ids, descripciones y casillas de origen de un índice existente ([] si no existe)."""
    if not ruta.is_file():
        return []
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        entradas = [{"id": s["id"], "descripcion": s.get("descripcion", ""),
                     "casilla_origen": int(s["casilla_origen"]),
                     "opacidad": _opacidad(s, ruta)} for s in datos["simbolos"]]
    except BibliotecaInvalida as e:
        raise ExtraccionFallida(str(e)) from e
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
        raise ExtraccionFallida(f"el índice existente '{ruta}' no se puede leer ({e}); cada "
                                f"símbolo necesita \"id\" y \"casilla_origen\"") from e
    ids = [e["id"] for e in entradas]
    repetidos = sorted({i for i in ids if ids.count(i) > 1})
    if repetidos:
        raise ExtraccionFallida(f"el índice '{ruta}' repite ids: {', '.join(repetidos)}")
    return entradas


def _medir_casillas(page: pymupdf.Page, campo: CampoConvenciones,
                    alto_hoja_mm: float) -> dict[int, tuple[RectMM, int]]:
    """{casilla: (caja del dibujo, trazos)} de las casillas de símbolo que tienen algo."""
    rects = [rect_pdf_a_papel(d["rect"], alto_hoja_mm) for d in page.get_drawings()]
    medidas = {}
    for k, celda in enumerate(campo.simbolos, start=1):
        propios = [r for r in rects if _dentro(r, celda.rect, TOL_CASILLA_MM)]
        if propios:
            medidas[k] = (tuple(round(v, 3) for v in _union(propios)), len(propios))
    return medidas


def _armar_biblioteca(hoja: pymupdf.Document, campo: CampoConvenciones,
                      simbolos: list[Simbolo], formato: Formato, ruta_pdf: Path) -> None:
    ancho, alto = hoja[0].rect.width, hoja[0].rect.height
    columnas: dict[tuple, pymupdf.Document] = {}
    biblioteca = pymupdf.open()
    try:
        for s in simbolos:
            celda = campo.simbolos[s.casilla_origen - 1].rect
            clave = (celda[0], celda[2])  # columna de símbolos de esa casilla
            if clave not in columnas:
                filas = [c.rect for c in campo.simbolos if (c.rect[0], c.rect[2]) == clave]
                columna = (clave[0], min(r[1] for r in filas), clave[1], max(r[3] for r in filas))
                columnas[clave] = _solo(hoja, 0, rect_papel_a_pdf(columna, formato.alto_mm),
                                        ancho, alto)
            m = MARGEN_MM
            caja = rect_papel_a_pdf((s.rect_mm[0] - m, s.rect_mm[1] - m, s.rect_mm[2] + m,
                                     s.rect_mm[3] + m), formato.alto_mm)
            uno = _simbolo_solo(columnas[clave], s, formato, ancho, alto)
            destino = biblioteca.new_page(width=caja.width, height=caja.height)
            destino.show_pdf_page(destino.rect, uno, 0, clip=caja)
            uno.close()
        ruta_pdf.parent.mkdir(parents=True, exist_ok=True)
        biblioteca.save(ruta_pdf, garbage=4, deflate=True)
    finally:
        biblioteca.close()
        for doc in columnas.values():
            doc.close()


def _simbolo_solo(columna: pymupdf.Document, s: Simbolo, formato: Formato, ancho: float,
                  alto: float) -> pymupdf.Document:
    """La columna con todo borrado salvo el símbolo `s`. MuPDF decide si un trazo «toca» una
    franja de redacción con su caja ENSANCHADA (grosor y puntas), así que con poco margen
    puede borrar trazos del propio símbolo (pasa con círculos pequeños). Se prueban márgenes
    crecientes y se acepta el primero que deja EXACTAMENTE los trazos medidos en el plano y la
    misma caja (±0,1 mm): si un margen grande metiera trazos de una casilla vecina, el conteo
    no cuadra y se descarta."""
    for margen in MARGENES_REDACCION_MM:
        caja = rect_papel_a_pdf((s.rect_mm[0] - margen, s.rect_mm[1] - margen,
                                 s.rect_mm[2] + margen, s.rect_mm[3] + margen), formato.alto_mm)
        uno = _solo(columna, 0, caja, ancho, alto)
        trazos = uno[0].get_drawings()
        if len(trazos) == s.trazos:
            medida = _union([rect_pdf_a_papel(t["rect"], formato.alto_mm) for t in trazos])
            if max(abs(a - b) for a, b in zip(medida, s.rect_mm)) <= TOL_MM:
                return uno
        uno.close()
    raise ExtraccionFallida(
        f"no se pudo aislar el símbolo '{s.id}' (casilla {s.casilla_origen}): con márgenes de "
        f"{', '.join(f'{m:g}' for m in MARGENES_REDACCION_MM)} mm la redacción no deja "
        f"exactamente sus {s.trazos} trazos")


def _solo(doc: pymupdf.Document, pagina: int, caja: pymupdf.Rect, ancho: float,
          alto: float) -> pymupdf.Document:
    """Copia de la página con TODO lo de fuera de `caja` (pt) borrado: redacción de las cuatro
    franjas, quitando cualquier trazo que las toque, sus textos y sus imágenes."""
    nuevo = pymupdf.open()
    page = nuevo.new_page(width=ancho, height=alto)
    page.show_pdf_page(page.rect, doc, pagina)
    for franja in (pymupdf.Rect(0, 0, ancho, caja.y0), pymupdf.Rect(0, caja.y1, ancho, alto),
                   pymupdf.Rect(0, caja.y0, caja.x0, caja.y1),
                   pymupdf.Rect(caja.x1, caja.y0, ancho, caja.y1)):
        page.add_redact_annot(franja, fill=False)
    page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_REMOVE,
                          graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED,
                          text=pymupdf.PDF_REDACT_TEXT_REMOVE)
    limpio = pymupdf.open("pdf", nuevo.tobytes(garbage=4, deflate=True))
    nuevo.close()
    return limpio


def _verificar_biblioteca(ruta_pdf: Path, simbolos: list[Simbolo]) -> list[str]:
    """Cada página: mismos trazos que el plano y caja igual (±0,1 mm)."""
    problemas = []
    with pymupdf.open(ruta_pdf) as doc:
        for s in simbolos:
            page = doc[s.pagina - 1]
            trazos = page.get_drawings()
            if len(trazos) != s.trazos:
                problemas.append(f"'{s.id}': la página {s.pagina} tiene {len(trazos)} trazos y en "
                                 f"el plano tenía {s.trazos}")
                continue
            alto = page.rect.height
            caja = _union([rect_pdf_a_papel(t["rect"], alto * 25.4 / 72) for t in trazos])
            m = MARGEN_MM
            esperada = (m, m, m + s.tamano_mm[0], m + s.tamano_mm[1])
            dif = max(abs(a - b) for a, b in zip(caja, esperada))
            if dif > TOL_MM:
                problemas.append(f"'{s.id}': la caja difiere {dif:.3f} mm de la del plano")
    return problemas


def _escribir_indice(ruta: Path, simbolos: list[Simbolo], plano: str, pagina: int) -> None:
    datos = {
        "version": VERSION,
        "biblioteca": NOMBRE_PDF,
        "origen": {"plano": plano, "pagina": pagina, "margen_mm": MARGEN_MM},
        "simbolos": [{"id": s.id, "descripcion": s.descripcion,
                      "casilla_origen": s.casilla_origen, "pagina": s.pagina,
                      "rect_mm": list(s.rect_mm), "trazos": s.trazos,
                      **({"opacidad": s.opacidad} if s.opacidad != 1 else {})}
                     for s in simbolos],
    }
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
                    newline="\n")


# --- pequeños ------------------------------------------------------------------------------

def _dentro(r: RectMM, c: RectMM, tol: float) -> bool:
    return (r[0] >= c[0] - tol and r[1] >= c[1] - tol and r[2] <= c[2] + tol
            and r[3] <= c[3] + tol)


def _union(rects: list) -> RectMM:
    return (min(r[0] for r in rects), min(r[1] for r in rects),
            max(r[2] for r in rects), max(r[3] for r in rects))


def _mm(r: RectMM) -> str:
    return "X {:.2f} a {:.2f}, Y {:.2f} a {:.2f} mm".format(r[0], r[2], r[1], r[3])
