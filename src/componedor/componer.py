"""Componer un plano con varios detalles a partir de un plano.json (subfase 3.1).

Pasos (si uno falla, no se genera el PDF):
  1. El plano ya viene leído y validado (`plano.leer_plano`).
  2. Formato y plantilla (la del plano.json si la trae; si no, la del formato).
  3. Cada detalle pasa por `importar_paquete` (la única puerta). Si hay rechazados, se
     listan TODOS y no se compone.
  4. Posiciones: la PÁGINA completa de cada detalle debe quedar dentro de `area_dibujo`
     (la misma regla estricta de `colocar`). El rótulo es inamovible: no se permite poner
     detalles sobre él ni sobre otras zonas.
  5. Traslapes entre detalles: advertencia, no error (páginas, o más grave, dibujos).
  6. Hoja base (`composicion.hoja_base`) y detalles en orden con `insertar_pagina`, sin
     reescalar y como vector.
  7. Se guarda en un archivo TEMPORAL junto a la salida y se verifica: el dibujo de cada
     detalle está donde dice el plano (±0,1 mm), el marco del rótulo no se movió y no hay
     imágenes nuevas. Solo entonces se renombra a la salida. Si algo falla, el temporal se
     borra.

Subfase 4.1 (si el formato trae la sección "rotulo"):
  - Rosa de los vientos (rosa.py): siempre se quita de la plantilla y, si es visible, se
    vuelve a dibujar en su sitio o donde diga el plano (completa dentro de `area_dibujo`).
    Las advertencias de "detalle sobre elemento" usan su posición nueva; oculta no avisa.
  - Rótulo (rotulo.py): los valores del plano, ESCALA y REV. calculadas; si un texto no cabe,
    error con el campo, el texto y las medidas.
  - Etiqueta "ESC: 1:N" junto a cada detalle (etiquetas_escala.py); si no cabe, advertencia.
  - Los textos se verifican en el PDF guardado (posición de cada línea ±0,1 mm).
"""

import os
from dataclasses import dataclass, field, replace
from pathlib import Path

import pymupdf

from componedor.advertencias import (
    clave_sobre_elemento,
    clave_traslape_detalles,
    texto_advertencia,
)
from componedor.cad_a_papel import limites_dibujo_en_papel
from componedor.colocar import (
    DetalleInvalido,
    abrir_pdf,
    insertar_pagina,
    motivo_fuera_de_zona,
    posicion_centrada,
    tamano_visible_mm,
)
from componedor.composicion import MANTENER, hoja_base_con_rosa
from componedor.comprobacion_dibujo import (
    es_fondo_blanco,
    limites_de_trazos,
    tiene_fondo_de_pagina,
)
from componedor.etiquetas_escala import DetalleParaEtiqueta, colocar_etiquetas
from componedor.formato import EPS_MM, ElementoPlantilla, Formato, RectMM, cargar_formato
from componedor.fuente import Fuente, FuenteInvalida, cargar_fuente
from componedor.importador import PaqueteAceptado, PaqueteRechazado, importar_paquete
from componedor.maquetacion import TextoMaquetado
from componedor.plano import Plano
from componedor.plantilla import TOLERANCIA_MARCO_MM, InformePlantilla, buscar_marco
from componedor.rosa import NOMBRE as ROSA
from componedor.rosa import (
    InformeRosa,
    RosaInvalida,
    elementos_visibles,
    motivo_fuera,
    rect_destino,
    verificar_rosa,
)
from componedor.notas import NotasMaquetadas, verificar_notas
from componedor.rotulo import RotuloInvalido, preparar_rotulo
from componedor.textos_pdf import escribir_textos, verificar_textos
from componedor.transformaciones import rect_papel_a_pdf

ZONA = "area_dibujo"
TOL_VERIFICACION_MM = 0.1


class PlanoNoComponible(ValueError):
    """El plano es válido como archivo, pero no se puede componer (el mensaje dice por qué)."""


@dataclass(frozen=True)
class DetalleColocado:
    id: str
    prefijo: str  # del paquete
    ocupado: RectMM  # página del detalle en la hoja, mm de papel
    dibujo: RectMM  # page_bounds_mm trasladado a mm de papel
    tiene_fondo: bool = True  # paquete antiguo con fondo blanco de página (tapa lo de abajo)
    escala: float | None = None  # N de 1:N (manifiesto)


@dataclass
class ResultadoComposicion:
    ruta_pdf: Path
    plantilla: InformePlantilla | None
    detalles: list[DetalleColocado]
    advertencias: list[str] = field(default_factory=list)
    rosa: InformeRosa | None = None  # None: el formato no tiene rosa (o no tiene plantilla)
    rotulo: dict[str, str] = field(default_factory=dict)  # valor final de cada campo de texto
    etiquetas: list[str] = field(default_factory=list)  # ids de detalles con etiqueta ESC
    notas: NotasMaquetadas | None = None  # cuántas notas, líneas y a qué altura (4.2a)


@dataclass
class _Textos:
    """Lo que se escribe como texto en la hoja (rótulo y etiquetas) y con qué fuente."""
    fuente: Fuente | None = None
    rotulo: list[TextoMaquetado] = field(default_factory=list)  # incluye las notas
    etiquetas: list[TextoMaquetado] = field(default_factory=list)
    notas: NotasMaquetadas | None = None


def componer_plano(plano: Plano, salida: Path | str, sobrescribir: bool = False,
                   guias: bool = False) -> ResultadoComposicion:
    """Compone `plano` en `salida`. Lanza `PlanoNoComponible` (o `FileExistsError`)."""
    salida = Path(salida)
    if salida.exists() and not sobrescribir:
        raise FileExistsError(
            f"El archivo '{salida}' ya existe. Use --sobrescribir para reemplazarlo.")

    formato = _formato(plano)
    destino_rosa = _destino_rosa(plano, formato)
    elementos = (list(formato.elementos_plantilla) if destino_rosa == MANTENER
                 else elementos_visibles(formato, destino_rosa))
    aceptados = _importar(plano)
    documentos: dict[Path, pymupdf.Document] = {}
    try:
        colocados = _posiciones(plano, formato, aceptados, documentos)
        advertencias = _traslapes(colocados) + _sobre_elementos(colocados, elementos)
        textos, valores, avisos = _textos(plano, formato, colocados, elementos)
        advertencias += avisos
        resultado = _componer_y_verificar(formato, colocados, salida, guias, destino_rosa,
                                          textos)
    finally:
        for doc in documentos.values():
            doc.close()
    resultado.advertencias = advertencias
    resultado.rotulo = valores
    resultado.etiquetas = [t.ruta.split(".", 1)[1] for t in textos.etiquetas]
    resultado.notas = textos.notas
    return resultado


# --- 2. formato y plantilla ------------------------------------------------------------

def _formato(plano: Plano) -> Formato:
    if plano.plantilla is None:
        return cargar_formato(plano.formato)  # con la plantilla del formato, si la tiene
    if not plano.plantilla.is_file():
        raise PlanoNoComponible(f"plantilla: no se encontró el PDF '{plano.plantilla}'.")
    formato = cargar_formato(plano.formato, usar_plantilla=False)
    return replace(formato, plantilla=plano.plantilla)


def _destino_rosa(plano: Plano, formato: Formato) -> RectMM | None | str:
    """Dónde va la rosa: su rectángulo (mm de papel), None (oculta) o `MANTENER` si el formato
    no declara la rosa (entonces no se toca nada)."""
    elemento = formato.elemento(ROSA)
    if elemento is None:
        if plano.rosa is not None:
            raise PlanoNoComponible(
                f"rosa_vientos: el formato no declara el elemento '{ROSA}' en "
                f"elementos_plantilla; no hay rosa que mostrar, ocultar ni mover.")
        return MANTENER
    if plano.rosa is None:
        return elemento.rect
    if not plano.rosa.visible:
        return None
    destino = rect_destino(elemento.rect, plano.rosa.posicion_mm)
    motivo = motivo_fuera(destino, formato)
    if motivo:
        raise PlanoNoComponible(f"rosa_vientos.posicion_mm: {motivo} La rosa debe quedar "
                                f"completa dentro del área de dibujo.")
    return destino


# --- 3. importar todos los paquetes -----------------------------------------------------

def _importar(plano: Plano) -> dict[Path, PaqueteAceptado]:
    """Importa cada manifiesto una sola vez (el mismo paquete puede ir en varios detalles)."""
    aceptados: dict[Path, PaqueteAceptado] = {}
    rechazados: dict[Path, PaqueteRechazado] = {}
    for detalle in plano.detalles:
        clave = detalle.manifiesto.resolve()
        if clave in aceptados or clave in rechazados:
            continue
        try:
            aceptados[clave] = importar_paquete(detalle.manifiesto)
        except PaqueteRechazado as e:
            rechazados[clave] = e
    if rechazados:
        bloques = []
        for detalle in plano.detalles:
            error = rechazados.get(detalle.manifiesto.resolve())
            if error is not None:
                bloques.append(f"detalle '{detalle.id}' ({detalle.manifiesto}):\n"
                               + _sangrar(str(error)))
        n = len(bloques)
        raise PlanoNoComponible(
            f"No se compone el plano: {n} detalle(s) con paquete rechazado.\n"
            + "\n".join(bloques))
    return aceptados


# --- 4. posiciones dentro del área de dibujo ---------------------------------------------

def _posiciones(plano: Plano, formato: Formato, aceptados: dict[Path, PaqueteAceptado],
                documentos: dict[Path, pymupdf.Document]) -> list[tuple]:
    """(detalle, aceptado, documento, DetalleColocado) por detalle; junta TODOS los errores."""
    zona = formato.zonas[ZONA]
    colocados, errores = [], []
    con_fondo: dict[Path, bool] = {}  # por PDF: se mira una sola vez
    for detalle in plano.detalles:
        aceptado = aceptados[detalle.manifiesto.resolve()]
        ruta_pdf = aceptado.paquete.ruta_pdf
        if ruta_pdf not in documentos:
            documentos[ruta_pdf] = abrir_pdf(ruta_pdf, "el detalle", DetalleInvalido)
            con_fondo[ruta_pdf] = tiene_fondo_de_pagina(documentos[ruta_pdf][0])
        doc = documentos[ruta_pdf]
        ancho, alto = tamano_visible_mm(doc[0])
        x, y = (detalle.posicion_mm if detalle.posicion_mm is not None
                else posicion_centrada((ancho, alto), zona))
        ocupado = (x, y, x + ancho, y + alto)
        motivo = motivo_fuera_de_zona(ocupado, ZONA, zona)
        if motivo:
            invadidas = [nombre for nombre, rect in formato.zonas.items()
                         if nombre != ZONA and _interseccion(ocupado, rect)]
            if invadidas:
                motivo += (f" Invade {', '.join(repr(n) for n in invadidas)}: el rótulo y las "
                           f"demás zonas no se pueden ocupar.")
            errores.append(f"detalle '{detalle.id}': {motivo}")
            continue
        dibujo = limites_dibujo_en_papel(aceptado.manifiesto.pdf.dibujo.limites_pagina_mm,
                                         alto, (x, y))
        colocados.append((detalle, aceptado, doc,
                          DetalleColocado(detalle.id, aceptado.paquete.prefijo, ocupado, dibujo,
                                          con_fondo[ruta_pdf],
                                          aceptado.manifiesto.escala.denominador)))
    if errores:
        raise PlanoNoComponible(
            f"No se compone el plano: {len(errores)} detalle(s) fuera de '{ZONA}' "
            f"({zona[0]:.1f}, {zona[1]:.1f}, {zona[2]:.1f}, {zona[3]:.1f} mm).\n"
            + "\n".join(f"- {e}" for e in errores))
    return colocados


# --- 5. traslapes (advertencias) ---------------------------------------------------------

def _traslapes(colocados: list[tuple]) -> list[str]:
    """Pares de detalles que se traslapan. Lo que tapa es el de encima (b, el que va
    después): si no tiene fondo, un traslape solo de páginas no avisa (advertencias.py)."""
    avisos = []
    for i, (_, _, _, a) in enumerate(colocados):
        for _, _, _, b in colocados[i + 1:]:
            dibujos = _interseccion(a.dibujo, b.dibujo)
            paginas = _interseccion(a.ocupado, b.ocupado)
            clave = clave_traslape_detalles(bool(dibujos), bool(paginas), b.tiene_fondo)
            if clave:
                avisos.append(texto_advertencia(clave, *(dibujos or paginas), a=a.id, b=b.id))
    return avisos


def _sobre_elementos(colocados: list[tuple], elementos: list[ElementoPlantilla]) -> list[str]:
    """Detalles que tapan elementos fijos de la plantilla dentro del área de dibujo (p. ej.
    la rosa de los vientos, en su posición final; oculta no está en la lista). Advertencia,
    no error: misma filosofía que los traslapes."""
    avisos = []
    for _, _, _, c in colocados:
        for elemento in elementos:
            dibujo = _interseccion(c.dibujo, elemento.rect)
            pagina = _interseccion(c.ocupado, elemento.rect)
            clave = clave_sobre_elemento(bool(dibujo), bool(pagina), c.tiene_fondo)
            if clave:
                avisos.append(texto_advertencia(clave, *(dibujo or pagina),
                                                a=c.id, elemento=elemento.nombre))
    return avisos


# --- 5b. textos: rótulo y etiquetas de escala ---------------------------------------------

def _textos(plano: Plano, formato: Formato, colocados: list[tuple],
            elementos: list[ElementoPlantilla]) -> tuple[_Textos, dict[str, str], list[str]]:
    """Maqueta el rótulo y las etiquetas "ESC: 1:N". Sin sección "rotulo" en el formato no se
    escribe nada. Devuelve (textos, valores finales del rótulo, advertencias)."""
    if formato.rotulo is None:
        return _Textos(), {}, []
    try:
        fuente = cargar_fuente(formato.rotulo.fuente)
    except FuenteInvalida as e:
        raise PlanoNoComponible(f"No se compone el plano: {e}") from e
    escalas = [c.escala for *_, c in colocados]
    try:
        rotulo = preparar_rotulo(formato.rotulo, plano.rotulo, escalas, fuente, plano.carpeta)
    except RotuloInvalido as e:
        raise PlanoNoComponible(f"No se compone el plano. {e}") from e
    etiquetas, avisos = colocar_etiquetas(
        [DetalleParaEtiqueta(c.id, c.dibujo, c.escala, detalle.etiqueta_escala)
         for detalle, _, _, c in colocados],
        formato.zonas[ZONA], [(e.nombre, e.rect) for e in elementos], fuente)
    return (_Textos(fuente, rotulo.textos, etiquetas, rotulo.notas), rotulo.valores,
            rotulo.advertencias + avisos)


# --- 6 y 7. componer, guardar en temporal, verificar y renombrar -------------------------

def _componer_y_verificar(formato: Formato, colocados: list[tuple], salida: Path,
                          guias: bool, destino_rosa: RectMM | None | str = MANTENER,
                          textos: _Textos | None = None) -> ResultadoComposicion:
    textos = textos or _Textos()
    salida.parent.mkdir(parents=True, exist_ok=True)
    temporal = salida.with_name(f".{salida.name}.componiendo.pdf")
    try:
        try:
            doc, informe, informe_rosa = hoja_base_con_rosa(formato, guias, rosa=destino_rosa)
        except RosaInvalida as e:
            raise PlanoNoComponible(f"No se compone el plano: {e}") from e
        try:
            base = doc[0]
            trazos_base = len(base.get_drawings())
            imagenes_base = len(base.get_image_info())
            if informe_rosa is not None:
                # La rosa se mide ANTES de poner los detalles: así nada de ellos se confunde
                # con sus trazos o sus letras.
                problemas = verificar_rosa(base, informe_rosa, formato, trazos_base)
                if problemas:
                    raise PlanoNoComponible(
                        "La verificación de la rosa de los vientos falló; no se generó el "
                        "plano:\n" + "\n".join(f"- {p}" for p in problemas))
            trazos_por_detalle = []
            for _, _, doc_detalle, colocado in colocados:
                trazos_por_detalle.append(len(doc_detalle[0].get_drawings()))
                insertar_pagina(base, formato, doc_detalle, 0, colocado.ocupado[:2])
            todos = textos.rotulo + textos.etiquetas
            escribir_textos(base, todos, textos.fuente, formato.alto_mm)
            doc.save(temporal)
        finally:
            doc.close()

        problemas = _verificar(temporal, formato, informe, [c for *_, c in colocados],
                               trazos_base, trazos_por_detalle, imagenes_base, todos,
                               textos.notas)
        if problemas:
            raise PlanoNoComponible(
                "La verificación del PDF compuesto falló; no se generó el plano:\n"
                + "\n".join(f"- {p}" for p in problemas))
        os.replace(temporal, salida)
    finally:
        if temporal.exists():
            temporal.unlink()  # cualquier falla: no queda un PDF a medias
    return ResultadoComposicion(salida, informe, [c for *_, c in colocados], rosa=informe_rosa)


def _verificar(ruta: Path, formato: Formato, informe: InformePlantilla | None,
               colocados: list[DetalleColocado], trazos_base: int,
               trazos_por_detalle: list[int], imagenes_base: int,
               textos: list[TextoMaquetado] = (),
               notas: NotasMaquetadas | None = None) -> list[str]:
    """Mide el PDF guardado. Devuelve la lista de problemas (vacía si todo está bien)."""
    with pymupdf.open(ruta) as final:
        page = final[0]
        textos_mal = verificar_textos(page, list(textos), formato.alto_mm)
        if notas is not None:
            textos_mal += verificar_notas(page, notas, formato.alto_mm)
        trazos = page.get_drawings()
        esperados = trazos_base + sum(trazos_por_detalle)
        if len(trazos) != esperados:
            # Los trazos de cada detalle se separan por su orden de dibujo; si el conteo no
            # cuadra no se puede saber cuáles son de quién: error, nunca verificación a ciegas.
            return [f"no se pudo separar el dibujo de cada detalle: la hoja tiene "
                    f"{len(trazos)} trazos y se esperaban {esperados} (hoja base "
                    f"{trazos_base} + detalles {' + '.join(map(str, trazos_por_detalle))})"]
        problemas = []
        inicio = trazos_base
        for colocado, n in zip(colocados, trazos_por_detalle):
            propios = trazos[inicio:inicio + n]
            inicio += n
            # Su fondo blanco se reconoce por el TAMAÑO de la página (no por la posición
            # esperada): así, si el detalle quedó corrido, se mide su dibujo y no su fondo.
            pagina = rect_papel_a_pdf(colocado.ocupado, formato.alto_mm)
            limites = limites_de_trazos([t for t in propios if not es_fondo_blanco(
                t, pymupdf.Rect(t["rect"].x0, t["rect"].y0, t["rect"].x0 + pagina.width,
                                t["rect"].y0 + pagina.height))])
            if limites is None:
                problemas.append(f"detalle '{colocado.id}': no tiene trazos que medir")
                continue
            medido = limites_dibujo_en_papel(limites, formato.alto_mm, (0.0, 0.0))
            diferencia = max(abs(a - b) for a, b in zip(medido, colocado.dibujo))
            if diferencia > TOL_VERIFICACION_MM:
                problemas.append(
                    f"detalle '{colocado.id}': el dibujo quedó en {_rect(medido)} y el plano "
                    f"dice {_rect(colocado.dibujo)} (diferencia máx. {diferencia:.3f} mm, "
                    f"tolerancia ±{TOL_VERIFICACION_MM} mm)")

        tolerancia = TOLERANCIA_MARCO_MM if informe is not None else TOL_VERIFICACION_MM
        marco = buscar_marco(page, formato)
        if marco is None or max(abs(d) for d in marco[1]) > tolerancia:
            problemas.append(f"el marco del rótulo no está en {_rect(formato.marco)} "
                             f"(±{tolerancia} mm): el rótulo no debe moverse")
        imagenes = len(page.get_image_info())
        if imagenes != imagenes_base:
            problemas.append(f"la hoja tiene {imagenes} imágenes y la hoja base tenía "
                             f"{imagenes_base}: no se debe rasterizar ningún detalle")
        problemas += textos_mal
    return problemas


def _interseccion(a: RectMM, b: RectMM) -> tuple[float, float] | None:
    """(ancho, alto) del traslape de dos rectángulos, o None si solo se tocan o no se cruzan."""
    ancho = min(a[2], b[2]) - max(a[0], b[0])
    alto = min(a[3], b[3]) - max(a[1], b[1])
    return (ancho, alto) if ancho > EPS_MM and alto > EPS_MM else None


def _sangrar(texto: str) -> str:
    return "\n".join(f"  {linea}" for linea in texto.splitlines())


def _rect(r: RectMM) -> str:
    return "X {:.2f} a {:.2f}, Y {:.2f} a {:.2f}".format(r[0], r[2], r[1], r[3])
