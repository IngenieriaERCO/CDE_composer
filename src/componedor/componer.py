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

Ortofoto (plano versión 4, `ortofoto_pdf`): detrás de los detalles, recortada a la página de
cada uno. Orden en la hoja: plantilla (y rosa, símbolos) → ortofoto → detalles → rótulo. Se usa
el original si existe y coincide con el plano; si no, la copia reducida de la carpeta del plano
(con aviso); si no hay ninguna, no se compone (`ortofoto_fuente`). En el PDF guardado se
verifica cada mosaico (JPEG, en su sitio ±0,1 mm) y que los detalles siguen siendo vectores. Con
el original, después se escribe (o se deja, si está al día) la copia reducida.

Versión 5: solo los detalles marcados llevan ortofoto. Con «extender» y UN solo detalle con
ortofoto, la foto cubre toda el área de dibujo (mismo mapeo CAD → papel de ese detalle) y los
detalles sin ortofoto llevan un fondo blanco del tamaño de su página. Con «cuadricula», la
cuadrícula de coordenadas (cuadricula.py) va sobre la foto y debajo de los detalles. La rosa
siempre queda encima de la foto (se vuelve a dibujar si la tapa). Orden: plantilla → ortofoto →
cuadrícula → rosa → fondos blancos → detalles → imagen de localización → textos.

Imagen de localización (localizacion.py): un campo "imagen" del rótulo; el original si existe y
coincide (y deja la copia `<plano>_localizacion.<ext>`), si no la copia (con aviso); ajustada al
recuadro sin deformar, ~300 ppp, debajo de los textos del rótulo y verificada en el PDF.
"""

import os
from contextlib import ExitStack
from dataclasses import dataclass, field, replace
from pathlib import Path

import pymupdf

from componedor.advertencias import (
    clave_sobre_elemento,
    clave_traslape_detalles,
    texto_advertencia,
)
from componedor.biblioteca_simbolos import con_carpeta_simbolos
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
    medir_limites_trazos,
    recortar_a_zona,
    tiene_fondo_de_pagina,
)
from componedor.configuracion import ConfigOrtofoto
from componedor.cuadricula import InformeCuadricula
from componedor.cuadricula import armar as armar_cuadricula
from componedor.cuadricula import dibujar as dibujar_cuadricula
from componedor.cuadricula import verificar as verificar_cuadricula
from componedor.etiquetas_escala import DetalleParaEtiqueta, colocar_etiquetas
from componedor.firmas import FirmaPedida, insertar_firmas, verificar_firmas
from componedor.formato import (
    EPS_MM,
    ElementoPlantilla,
    Formato,
    RectMM,
    cargar_formato,
)
from componedor.fuente import Fuente, FuenteInvalida, cargar_fuente
from componedor.hojas_proyecto import automaticos_de_lista, valores_automaticos
from componedor.importador import PaqueteAceptado, PaqueteRechazado, importar_paquete
from componedor.localizacion import ImagenLocalizacion, LocalizacionInvalida
from componedor.localizacion import insertar as insertar_localizacion
from componedor.localizacion import leer_valor as leer_localizacion
from componedor.localizacion import preparar as preparar_localizacion
from componedor.localizacion import verificar as verificar_localizacion
from componedor.maquetacion import TextoMaquetado
from componedor.muestras_leyenda import (
    ColocacionMuestra,
    dibujar_muestras,
    verificar_muestras,
)
from componedor.notas import NotasMaquetadas, verificar_notas
from componedor.ortofoto_copia import InformeCopia, carpeta_copia, escribir_copia
from componedor.ortofoto_fuente import (
    Eleccion,
    OrtofotoNoUsable,
    abrir_fuentes,
    datos_del_archivo,
    elegir,
)
from componedor.ortofoto_pdf import (
    DetalleOrtofoto,
    InformeOrtofoto,
    poner_ortofoto,
    verificar_ortofoto,
)
from componedor.ortofoto_render import abrir_fuente
from componedor.plano import Plano
from componedor.plano_dxf import texto_pendientes
from componedor.plano_zonas import texto_zonas_sin_exportar
from componedor.plantilla import TOLERANCIA_MARCO_MM, InformePlantilla, buscar_marco
from componedor.recorte_detalle import (
    MARGEN_POR_DEFECTO_MM,
    posicion_centrada_recorte,
    recorte_pagina,
    visible_en_papel,
)
from componedor.rosa import NOMBRE as ROSA
from componedor.rosa import (
    InformeRosa,
    RosaInvalida,
    elementos_visibles,
    motivo_fuera,
    rect_destino,
    redibujar_rosa,
    verificar_rosa,
)
from componedor.rotulo import RotuloInvalido, preparar_rotulo
from componedor.simbolos import (
    Biblioteca,
    ColocacionSimbolo,
    dibujar_simbolos,
    verificar_simbolos,
)
from componedor.textos_pdf import corregir_tounicode, escribir_textos, verificar_textos
from componedor.transformaciones import rect_papel_a_pdf

ZONA = "area_dibujo"
TOL_VERIFICACION_MM = 0.1


class PlanoNoComponible(ValueError):
    """El plano es válido como archivo, pero no se puede componer (el mensaje dice por qué)."""


@dataclass(frozen=True)
class DetalleColocado:
    id: str
    prefijo: str  # del paquete
    # Lo que se ve del detalle en la hoja (mm de papel): su página recortada a su dibujo más el
    # margen (recorte_detalle.py). Es lo que debe quedar dentro del área de dibujo.
    ocupado: RectMM
    dibujo: RectMM  # page_bounds_mm trasladado a mm de papel
    tiene_fondo: bool = True  # paquete antiguo con fondo blanco de página (tapa lo de abajo)
    escala: float | None = None  # N de 1:N (manifiesto)
    # Zona de la máscara de recorte (manifiesto 1.5, pdf.drawing.mask) trasladada a mm de papel;
    # None sin máscara. get_drawings() no aplica la máscara: la verificación final recorta a esto.
    mascara: RectMM | None = None
    # Los trazos medidos en el PROPIO PDF del detalle, trasladados a su posición (mm de papel):
    # contra esto se verifica dónde quedó. No es la caja declarada (`dibujo`, page_bounds_mm),
    # que el exportador puede dar hasta 0,5 mm más grande que los trazos (la coherencia h lo
    # admite); así ±0,1 mm mide solo la colocación. None: el PDF no tiene trazos.
    trazos: RectMM | None = None
    # La PÁGINA entera del paquete en la hoja (mm de papel; `posicion_mm` es su esquina): con
    # ella se ubica el dibujo y se reconoce el fondo blanco. None: igual a `ocupado`.
    pagina: RectMM | None = None
    recorte: RectMM | None = None  # mm de la página del detalle (Y abajo); None: sin recorte
    margen_mm: float | None = None  # el margen con que se recortó

    @property
    def pagina_completa(self) -> RectMM:
        return self.pagina if self.pagina is not None else self.ocupado


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
    simbolos: list[ColocacionSimbolo] = field(default_factory=list)  # convenciones (4.2b)
    muestras: list[ColocacionMuestra] = field(default_factory=list)  # línea y relleno (9a)
    firmas: list[FirmaPedida] = field(default_factory=list)  # firmas en imagen (4.2d)
    ortofoto: InformeOrtofoto | None = None  # plano versión 4
    copia: InformeCopia | None = None  # la copia reducida (si se compuso con el original)
    cuadriculas: list[InformeCuadricula] = field(default_factory=list)  # versión 5
    localizacion: ImagenLocalizacion | None = None  # la imagen de localización del rótulo
    extendida: bool = False  # versión 5: la ortofoto cubre toda el área de dibujo


@dataclass
class _Ortofoto:
    """Lo que hace falta para poner la ortofoto (plano versión 4)."""
    eleccion: Eleccion
    detalles: list[DetalleOrtofoto]
    config: ConfigOrtofoto
    opacidad: float
    intervalo_m: float | None = None  # None: sin cuadrícula
    obstaculos: list = field(default_factory=list)  # para las etiquetas: rosa, etiquetas ESC
    rosa: RectMM | None = None  # dónde quedó la rosa (se redibuja si la foto la tapa)
    fondos: list = field(default_factory=list)  # páginas de los detalles sin ortofoto (extendida)
    paginas: dict = field(default_factory=dict)  # id → página de cada detalle (obstáculos)
    extendida: bool = False  # «Extender a todo el layout» (un solo detalle con ortofoto)


@dataclass
class _Textos:
    """Lo que se escribe en el rótulo (textos y símbolos de convenciones) y con qué fuente."""
    fuente: Fuente | None = None
    rotulo: list[TextoMaquetado] = field(default_factory=list)  # incluye notas y descripciones
    etiquetas: list[TextoMaquetado] = field(default_factory=list)
    notas: NotasMaquetadas | None = None
    simbolos: list[ColocacionSimbolo] = field(default_factory=list)
    biblioteca: Biblioteca | None = None
    firmas: list[FirmaPedida] = field(default_factory=list)
    muestras: list[ColocacionMuestra] = field(default_factory=list)  # línea y relleno (9a)


def componer_plano(plano: Plano, salida: Path | str, sobrescribir: bool = False,
                   guias: bool = False, config_ortofoto: ConfigOrtofoto | None = None,
                   carpeta_simbolos: Path | None = None,
                   margen_mm: float | None = MARGEN_POR_DEFECTO_MM) -> ResultadoComposicion:
    """Compone `plano` en `salida`. Lanza `PlanoNoComponible` (o `FileExistsError`).
    config_ortofoto: ppp y calidad JPEG de la ortofoto (por defecto 300 y 85).
    carpeta_simbolos: la biblioteca de convenciones (`carpeta_simbolos` de componedor.json);
    None: la del formato. margen_mm: el borde que se deja alrededor del dibujo de cada detalle
    (`margen_detalle_mm` de componedor.json); un detalle puede traer el suyo. None: la página
    entera, sin recorte (como antes de la Fase 11)."""
    salida = Path(salida)
    if salida.exists() and not sobrescribir:
        raise FileExistsError(
            f"El archivo '{salida}' ya existe. Use --sobrescribir para reemplazarlo.")

    formato = con_carpeta_simbolos(_formato(plano), carpeta_simbolos)
    if plano.pendientes:  # plano versión 3 con bloques de DXF sin exportar
        raise PlanoNoComponible(texto_pendientes(plano.pendientes, plano.dxf,
                                                 formato.zonas[ZONA], ZONA))
    if plano.borradores:  # plano versión 6 con zonas del Model Space sin exportar
        raise PlanoNoComponible(texto_zonas_sin_exportar(plano.borradores))
    eleccion = None
    # Versión 5: solo los detalles marcados; versión 4: todos (plano.py ya lo migró así).
    usan_ortofoto = [d for d in plano.detalles if d.ortofoto]
    if plano.ortofoto is not None and usan_ortofoto:
        try:
            eleccion = elegir(plano.ortofoto, carpeta_copia(plano.ruta_copia))
        except OrtofotoNoUsable as e:
            raise PlanoNoComponible(f"No se compone el plano: {e}") from None
    destino_rosa = _destino_rosa(plano, formato)
    elementos = (list(formato.elementos_plantilla) if destino_rosa == MANTENER
                 else elementos_visibles(formato, destino_rosa))
    aceptados = _importar(plano)
    documentos: dict[Path, pymupdf.Document] = {}
    try:
        colocados = _posiciones(plano, formato, aceptados, documentos, margen_mm)
        advertencias = (avisos_de_hoja(plano) + _traslapes(colocados)
                        + _sobre_elementos(colocados, elementos))
        textos, valores, avisos = _textos(plano, formato, colocados, elementos)
        advertencias += avisos
        localizacion = _localizacion(plano, formato)
        if localizacion is not None:
            advertencias += localizacion.avisos
        ortofoto = None
        if plano.ortofoto is not None and not usan_ortofoto:
            advertencias.append(f"El plano tiene la ortofoto «{plano.ortofoto.archivo.name}», "
                                f"pero ningún detalle la usa («Usar ortofoto» en el editor): "
                                f"sale sin ella.")
        if eleccion is not None:
            advertencias += eleccion.avisos
            ortofoto = _armar_ortofoto(plano, formato, colocados, eleccion,
                                       config_ortofoto or ConfigOrtofoto(), destino_rosa, textos,
                                       advertencias)
        resultado = _componer_y_verificar(formato, colocados, salida, guias, destino_rosa,
                                          textos, ortofoto, localizacion)
    finally:
        for doc in documentos.values():
            doc.close()
    if resultado.ortofoto is not None:
        advertencias += resultado.ortofoto.avisos
        resultado.extendida = ortofoto.extendida
        for c in resultado.cuadriculas:
            advertencias += c.avisos
        if eleccion.origen == "original":
            try:
                resultado.copia = _copia(plano, ortofoto)
            except (OSError, ValueError) as e:  # el PDF ya está: la copia no lo invalida
                advertencias.append(f"No se pudo escribir la copia reducida de la ortofoto en "
                                    f"«{carpeta_copia(plano.ruta_copia)}»: {e}")
    resultado.advertencias = advertencias
    resultado.rotulo = valores
    resultado.etiquetas = [t.ruta.split(".", 1)[1] for t in textos.etiquetas]
    resultado.notas = textos.notas
    resultado.simbolos = textos.simbolos
    resultado.muestras = textos.muestras
    resultado.firmas = textos.firmas
    return resultado


def _localizacion(plano: Plano, formato: Formato) -> ImagenLocalizacion | None:
    """La imagen de localización del rótulo (campo de tipo "imagen"), si el plano la tiene."""
    from componedor.rotulo_formato import CampoImagen

    if formato.rotulo is None or not isinstance(plano.rotulo, dict):
        return None
    for campo in formato.rotulo.campos.values():
        if not isinstance(campo, CampoImagen) or campo.nombre not in plano.rotulo:
            continue
        problemas: list[str] = []
        valor = leer_localizacion(plano.rotulo[campo.nombre], f"rotulo.{campo.nombre}",
                                  problemas)
        if valor is None:
            raise PlanoNoComponible("No se compone el plano:\n"
                                    + "\n".join(f"- {p}" for p in problemas))
        escala = plano.rotulo.get(campo.campo_escala) if campo.campo_escala else "-"
        vacia = escala is None or (isinstance(escala, str) and not escala.strip())
        try:
            return preparar_localizacion(campo, valor, plano.ruta, vacia)
        except LocalizacionInvalida as e:
            raise PlanoNoComponible(f"No se compone el plano: {e}") from None
    return None


def _detalle_ortofoto(aceptado: PaqueteAceptado, colocado: DetalleColocado,
                      region: RectMM | None = None) -> DetalleOrtofoto:
    """La ortofoto va detrás de lo que se ve del detalle (el mismo recorte que su dibujo) o,
    extendida, de `region`; el mapeo CAD → papel es el de su página entera."""
    m = aceptado.manifiesto
    return DetalleOrtofoto(colocado.id, colocado.pagina_completa, m.pdf.dibujo.matriz,
                           m.unidades.milimetros_por_unidad, colocado.tiene_fondo,
                           region if region is not None else colocado.ocupado)


def _armar_ortofoto(plano: Plano, formato: Formato, colocados: list[tuple], eleccion: Eleccion,
                    config: ConfigOrtofoto, destino_rosa, textos: "_Textos",
                    advertencias: list[str]) -> "_Ortofoto":
    """Qué detalles la llevan y dónde (su página o, extendida, el área de dibujo), la
    cuadrícula y los fondos blancos."""
    o = plano.ortofoto
    marcados = [(a, c) for d, a, _, c in colocados if d.ortofoto]
    extender = o.extender
    if extender and len(marcados) != 1:
        advertencias.append(f"«Extender a todo el layout» solo vale con UN detalle con ortofoto "
                            f"y hay {len(marcados)}: cada una va recortada a su página.")
        extender = False
    region = formato.zonas[ZONA] if extender else None
    rosa = destino_rosa if isinstance(destino_rosa, tuple) else None
    # Las etiquetas ESC, con la caja que se les reservó (la misma que usa el editor).
    obstaculos = ([rosa] if rosa else []) + [t.celda_mm or t.rect() for t in textos.etiquetas]
    no_editables = [r for nombre, r in formato.zonas.items() if nombre != ZONA]
    return _Ortofoto(eleccion, [_detalle_ortofoto(a, c, region) for a, c in marcados], config,
                     o.opacidad,
                     (o.intervalo_m or config.cuadricula_intervalo_m) if o.cuadricula else None,
                     obstaculos + no_editables, rosa,
                     [c.ocupado for d, _, _, c in colocados if not d.ortofoto] if extender else [],
                     {c.id: c.ocupado for *_, c in colocados}, extender)


def _copia(plano: Plano, o: _Ortofoto) -> InformeCopia:
    """La copia reducida en la carpeta del plano (o la que ya estaba, si está al día)."""
    e = o.eleccion
    with abrir_fuente(e.original, e.crs_ortofoto) as fuente:
        return escribir_copia(carpeta_copia(plano.ruta_copia), datos_del_archivo(e.original),
                              o.detalles, fuente, e.crs_dibujo, o.config.ppp,
                              o.config.calidad_jpeg)


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
                documentos: dict[Path, pymupdf.Document],
                margen_mm: float | None = MARGEN_POR_DEFECTO_MM) -> list[tuple]:
    """(detalle, aceptado, documento, DetalleColocado) por detalle; junta TODOS los errores.
    Lo que debe caber en el área es lo que se ve: el dibujo más el margen (recorte_detalle)."""
    zona = formato.zonas[ZONA]
    colocados, errores = [], []
    con_fondo: dict[Path, bool] = {}  # por PDF: se mira una sola vez
    trazos_pdf: dict[Path, RectMM | None] = {}  # por PDF: sus trazos, en mm de su página
    for detalle in plano.detalles:
        aceptado = aceptados[detalle.manifiesto.resolve()]
        ruta_pdf = aceptado.paquete.ruta_pdf
        if ruta_pdf not in documentos:
            documentos[ruta_pdf] = abrir_pdf(ruta_pdf, "el detalle", DetalleInvalido)
            con_fondo[ruta_pdf] = tiene_fondo_de_pagina(documentos[ruta_pdf][0])
        doc = documentos[ruta_pdf]
        ancho, alto = tamano_visible_mm(doc[0])
        margen = detalle.margen_mm if detalle.margen_mm is not None else margen_mm
        limites = aceptado.manifiesto.pdf.dibujo.limites_pagina_mm
        # Una página girada (nunca del Exportador) va entera: el recorte supone /Rotate 0.
        recorte = (recorte_pagina((ancho, alto), limites, margen)
                   if margen is not None and doc[0].rotation == 0 else None)
        if detalle.posicion_mm is not None:
            x, y = detalle.posicion_mm
        elif recorte is not None:
            x, y = posicion_centrada_recorte(recorte, alto, zona)
        else:
            x, y = posicion_centrada((ancho, alto), zona)
        pagina = (x, y, x + ancho, y + alto)
        ocupado = visible_en_papel(recorte, alto, (x, y)) if recorte is not None else pagina
        motivo = motivo_fuera_de_zona(ocupado, ZONA, zona)
        if motivo:
            invadidas = [nombre for nombre, rect in formato.zonas.items()
                         if nombre != ZONA and _interseccion(ocupado, rect)]
            if invadidas:
                motivo += (f" Invade {', '.join(repr(n) for n in invadidas)}: el rótulo y las "
                           f"demás zonas no se pueden ocupar.")
            errores.append(f"detalle '{detalle.id}': {motivo}")
            continue
        dibujo = limites_dibujo_en_papel(limites, alto, (x, y))
        mascara = aceptado.manifiesto.pdf.dibujo.mascara_mm
        if ruta_pdf not in trazos_pdf:  # medidos una vez por PDF (sin fondo; con su máscara)
            trazos_pdf[ruta_pdf] = medir_limites_trazos(doc[0], mascara)
        trazos = trazos_pdf[ruta_pdf]
        colocados.append((detalle, aceptado, doc,
                          DetalleColocado(detalle.id, aceptado.paquete.prefijo, ocupado, dibujo,
                                          con_fondo[ruta_pdf],
                                          aceptado.manifiesto.escala.denominador,
                                          limites_dibujo_en_papel(mascara, alto, (x, y))
                                          if mascara is not None else None,
                                          limites_dibujo_en_papel(trazos, alto, (x, y))
                                          if trazos is not None else None,
                                          pagina, recorte,
                                          margen if recorte is not None else None)))
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
        rotulo = preparar_rotulo(formato.rotulo, _rotulo_con_automaticos(plano, formato), escalas,
                                 fuente, plano.carpeta)
    except RotuloInvalido as e:
        raise PlanoNoComponible(f"No se compone el plano. {e}") from e
    etiquetas, avisos = colocar_etiquetas(
        [DetalleParaEtiqueta(c.id, c.dibujo, c.escala, detalle.etiqueta_escala)
         for detalle, _, _, c in colocados],
        formato.zonas[ZONA], [(e.nombre, e.rect) for e in elementos], fuente)
    return (_Textos(fuente, rotulo.textos, etiquetas, rotulo.notas, rotulo.simbolos,
                    rotulo.biblioteca, rotulo.firmas, rotulo.muestras), rotulo.valores,
            rotulo.advertencias + avisos)


def _rotulo_con_automaticos(plano: Plano, formato: Formato) -> dict | None:
    """El rótulo del plano con los campos automáticos que no escribe (hoja, de, número de plano)
    llenos desde el índice de hojas del proyecto (hojas_proyecto.py). Sin índice: tal cual."""
    campos = {n: c.automatico for n, c in formato.rotulo.campos.items()
              if getattr(c, "automatico", None)}
    actual = plano.rotulo if isinstance(plano.rotulo, dict) else {}
    if plano.posicion is not None:  # una hoja de un proyecto versión 8: su lugar en la lista
        automaticos = automaticos_de_lista(list(plano.rotulos_proyecto), plano.posicion, campos,
                                           actual)
    else:
        automaticos = valores_automaticos(plano.ruta, campos, actual)
    if not automaticos:
        return plano.rotulo
    return {**actual, **automaticos}


def avisos_de_hoja(plano: Plano) -> list[str]:
    """Versión 7: hoja sin detalles, y campos del rótulo copiados de otra hoja sin revisar."""
    avisos = []
    if not plano.detalles:
        avisos.append("La hoja no tiene detalles: sale solo el rótulo.")
    for campo in plano.revisar:
        avisos.append(f"rotulo.{campo}: copiado de la hoja «{plano.copiado_de}» sin revisar: "
                      f"revíselo (el editor deja de avisar cuando se cambia).")
    return avisos


# --- 6 y 7. componer, guardar en temporal, verificar y renombrar -------------------------

def _componer_y_verificar(formato: Formato, colocados: list[tuple], salida: Path,
                          guias: bool, destino_rosa: RectMM | None | str = MANTENER,
                          textos: _Textos | None = None,
                          ortofoto: _Ortofoto | None = None,
                          localizacion: ImagenLocalizacion | None = None) -> ResultadoComposicion:
    textos = textos or _Textos()
    informe_orto = None
    cuadriculas: list[InformeCuadricula] = []
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
            if textos.simbolos or textos.muestras:
                # Los símbolos y las muestras de convenciones son parte de la hoja base (van
                # antes que los detalles): así el conteo de trazos por detalle sigue separando.
                if textos.simbolos:
                    dibujar_simbolos(base, textos.simbolos, textos.biblioteca, formato.alto_mm)
                dibujar_muestras(base, textos.muestras, formato.alto_mm)
                trazos_base = len(base.get_drawings())
                imagenes_base = len(base.get_image_info())
            if ortofoto is not None:
                # Detrás de los detalles: va antes que ellos en el contenido de la página.
                imagenes_antes = len(base.get_image_info())
                informe_orto = _poner_ortofoto(base, formato, ortofoto)
                cuadriculas = _cuadricula_rosa_y_fondos(base, formato, ortofoto, textos.fuente)
                # La rosa redibujada puede traer imágenes propias; los trazos de la cuadrícula,
                # la rosa y los fondos son parte de la hoja base (antes de los detalles).
                imagenes_base += (len(base.get_image_info()) - imagenes_antes
                                  - len(informe_orto.mosaicos))
                trazos_base = len(base.get_drawings())
            trazos_por_detalle = []
            for _, _, doc_detalle, colocado in colocados:
                trazos_por_detalle.append(len(doc_detalle[0].get_drawings()))
                insertar_pagina(base, formato, doc_detalle, 0, colocado.pagina_completa[:2],
                                colocado.recorte)
            todos = textos.rotulo + textos.etiquetas
            if localizacion is not None:  # debajo de los textos del rótulo
                insertar_localizacion(base, formato.alto_mm, localizacion)
            escribir_textos(base, todos, textos.fuente, formato.alto_mm)
            etiquetas_cuadricula = "".join(e.texto for c in cuadriculas for e in c.etiquetas)
            if etiquetas_cuadricula and textos.fuente is not None:
                # Una sola fuente embebida para todo: su ToUnicode con lo de ambos.
                corregir_tounicode(base, "".join(l.texto for x in todos for l in x.lineas)
                                   + etiquetas_cuadricula, textos.fuente)
            insertar_firmas(base, textos.firmas, formato.alto_mm)  # PNG con máscara (SMask)
            # deflate_images: las firmas (insert_image) quedarían sin comprimir (~300 KB cada
            # una); se comprimen sin pérdida. Trazos y fuentes no se tocan.
            doc.save(temporal, deflate_images=True)
        finally:
            doc.close()

        problemas = _verificar(temporal, formato, informe, [c for *_, c in colocados],
                               trazos_base, trazos_por_detalle, imagenes_base, todos,
                               textos.notas, textos.simbolos, textos.firmas, informe_orto,
                               cuadriculas, localizacion, textos.muestras)
        if problemas:
            raise PlanoNoComponible(
                "La verificación del PDF compuesto falló; no se generó el plano:\n"
                + "\n".join(f"- {p}" for p in problemas))
        os.replace(temporal, salida)
    finally:
        if temporal.exists():
            temporal.unlink()  # cualquier falla: no queda un PDF a medias
    return ResultadoComposicion(salida, informe, [c for *_, c in colocados], rosa=informe_rosa,
                                ortofoto=informe_orto, cuadriculas=cuadriculas,
                                localizacion=localizacion)


def _cuadricula_rosa_y_fondos(base: pymupdf.Page, formato: Formato, o: "_Ortofoto",
                              fuente: Fuente | None = None) -> list[InformeCuadricula]:
    """Sobre la ortofoto: la cuadrícula (también donde la foto no cubre), la rosa otra vez si la
    foto la tapa y, en modo extendido, el fondo blanco de cada detalle sin ortofoto."""
    cuadriculas = []
    if o.intervalo_m is not None:
        for d in o.detalles:
            otras = [r for ident, r in o.paginas.items() if ident != d.id]
            c = armar_cuadricula(d.id, d.recorte, d.ocupado, d.matriz, d.mm_por_unidad,
                                 o.intervalo_m, o.obstaculos + otras, formato.marco, fuente)
            dibujar_cuadricula(base, formato.alto_mm, c, fuente)
            cuadriculas.append(c)
    if o.rosa is not None and any(_interseccion(o.rosa, d.recorte) for d in o.detalles):
        redibujar_rosa(base, formato, o.rosa)
    for pagina in o.fondos:
        base.draw_rect(rect_papel_a_pdf(pagina, formato.alto_mm), color=None, fill=(1, 1, 1),
                       width=0)
    return cuadriculas


def _poner_ortofoto(base: pymupdf.Page, formato: Formato, o: _Ortofoto) -> InformeOrtofoto:
    e = o.eleccion
    try:
        with ExitStack() as pila:
            fuentes, avisos = pila.enter_context(abrir_fuentes(e, [d.id for d in o.detalles]))
            informe = poner_ortofoto(base, formato.alto_mm, o.detalles, fuentes, e.crs_dibujo,
                                     o.config.ppp, o.config.calidad_jpeg, o.opacidad)
    except (OSError, ValueError) as err:  # OrtofotoInvalida, RasterioIOError (es OSError)
        raise PlanoNoComponible(f"No se compone el plano: no se pudo leer la ortofoto: "
                                f"{err}") from None
    informe.avisos = avisos + informe.avisos
    informe.fuente = e.origen
    informe.archivo = str(e.original if e.origen == "original" else e.carpeta_copia)
    return informe


def _verificar(ruta: Path, formato: Formato, informe: InformePlantilla | None,
               colocados: list[DetalleColocado], trazos_base: int,
               trazos_por_detalle: list[int], imagenes_base: int,
               textos: list[TextoMaquetado] = (),
               notas: NotasMaquetadas | None = None,
               simbolos: list[ColocacionSimbolo] = (),
               firmas: list[FirmaPedida] = (),
               ortofoto: InformeOrtofoto | None = None,
               cuadriculas: list[InformeCuadricula] = (),
               localizacion: ImagenLocalizacion | None = None,
               muestras: list[ColocacionMuestra] = ()) -> list[str]:
    """Mide el PDF guardado. Devuelve la lista de problemas (vacía si todo está bien)."""
    with pymupdf.open(ruta) as final:
        page = final[0]
        textos_mal = verificar_textos(page, list(textos), formato.alto_mm)
        if notas is not None:
            textos_mal += verificar_notas(page, notas, formato.alto_mm)
        textos_mal += verificar_simbolos(page, list(simbolos), formato.alto_mm)
        textos_mal += verificar_muestras(page, list(muestras), formato.alto_mm)
        textos_mal += verificar_firmas(page, list(firmas), formato.alto_mm)
        textos_mal += verificar_ortofoto(page, ortofoto, formato.alto_mm)
        textos_mal += verificar_cuadricula(page, list(cuadriculas), formato.alto_mm)
        textos_mal += verificar_localizacion(page, localizacion, formato.alto_mm)
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
            # Con recorte, get_drawings() da los trazos sin recortar: la página entera.
            pagina = rect_papel_a_pdf(colocado.pagina_completa, formato.alto_mm)
            dibujados = [t for t in propios if not es_fondo_blanco(
                t, pymupdf.Rect(t["rect"].x0, t["rect"].y0, t["rect"].x0 + pagina.width,
                                t["rect"].y0 + pagina.height))]
            if colocado.mascara is not None:
                # Zona del Model Space: lo que cruza el borde está entero en el PDF y la máscara
                # lo oculta; se mide lo que se ve (en mm de la hoja con Y abajo, como los trazos).
                mx0, my0, mx1, my1 = colocado.mascara
                dibujados = recortar_a_zona(dibujados, (mx0, formato.alto_mm - my1,
                                                        mx1, formato.alto_mm - my0))
            limites = limites_de_trazos(dibujados)
            if limites is None or colocado.trazos is None:
                problemas.append(f"detalle '{colocado.id}': no tiene trazos que medir")
                continue
            # Contra los trazos del PROPIO PDF del detalle en su posición (no contra
            # page_bounds_mm): lo que se comprueba es que el detalle quedó donde dice el plano.
            medido = limites_dibujo_en_papel(limites, formato.alto_mm, (0.0, 0.0))
            diferencia = max(abs(a - b) for a, b in zip(medido, colocado.trazos))
            if diferencia > TOL_VERIFICACION_MM:
                problemas.append(
                    f"detalle '{colocado.id}': el dibujo quedó en {_rect(medido)} y, según el "
                    f"plano, debía quedar en {_rect(colocado.trazos)} (los trazos de su PDF en "
                    f"la posición del plano; diferencia máx. {diferencia:.3f} mm, tolerancia "
                    f"±{TOL_VERIFICACION_MM} mm)")

        tolerancia = TOLERANCIA_MARCO_MM if informe is not None else TOL_VERIFICACION_MM
        marco = buscar_marco(page, formato)
        if marco is None or max(abs(d) for d in marco[1]) > tolerancia:
            problemas.append(f"el marco del rótulo no está en {_rect(formato.marco)} "
                             f"(±{tolerancia} mm): el rótulo no debe moverse")
        # Exactamente las imágenes de la hoja base (el logo), una por firma pedida y una por
        # mosaico de la ortofoto: los detalles nunca traen imágenes nuevas (no se rasteriza).
        imagenes = len(page.get_image_info())
        mosaicos = len(ortofoto.mosaicos) if ortofoto is not None else 0
        esperadas = imagenes_base + len(firmas) + mosaicos + (1 if localizacion else 0)
        if imagenes != esperadas:
            firmas_txt = f" + {len(firmas)} firma(s)" if firmas else ""
            orto_txt = f" + {mosaicos} mosaico(s) de la ortofoto" if mosaicos else ""
            if localizacion:
                orto_txt += " + 1 imagen de localización"
            problemas.append(f"la hoja tiene {imagenes} imágenes y debía tener {esperadas} (hoja "
                             f"base {imagenes_base}{firmas_txt}{orto_txt}): no se debe "
                             f"rasterizar ningún detalle")
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
