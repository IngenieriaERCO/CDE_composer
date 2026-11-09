"""Interfaz de línea de comandos: python -m componedor.cli <subcomando> ..."""

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from componedor.cad_a_papel import limites_dibujo_en_papel, origen_para_ancla
from componedor.coherencia import verificar_paquete
from componedor.importador import importar_paquete
from componedor.inventario import RECHAZADO, EntradaInventario, construir_inventario
from componedor.colocar import DetalleInvalido, abrir_pdf, colocar_detalle, tamano_visible_mm
from componedor.comando_referencia import ejecutar_referencia
from componedor.componer import ResultadoComposicion, componer_plano
from componedor.composicion import hoja_base
from componedor.editor_html import generar_editor
from componedor.datos_editor import (
    ARCHIVO_DATOS,
    ARCHIVO_PLANTILLA,
    CARPETA_MINIATURAS,
    ZONA_EDITABLE,
    preparar_editor,
)
from componedor.elementos_plantilla import Candidato, detectar_elementos, pdf_verificacion
from componedor.plano import leer_plano
from componedor.formato import Formato, RectMM, cargar_formato
from componedor.hoja import ORIENTACIONES, crear_hoja
from componedor.manifiesto import Manifiesto, leer_manifiesto
from componedor.paquete import (
    COMPLETO,
    INCOMPLETO,
    INVALIDO,
    SUFIJO_MANIFIESTO,
    Paquete,
    localizar_con_sueltos,
    paquete_de_manifiesto,
)
from componedor.informe import resultado_final
from componedor.validacion import Comprobacion, ResultadoVerificacion
from componedor.plantilla import TOLERANCIA_MARCO_MM, TOLERANCIA_TAMANO_MM, InformePlantilla
from componedor.rotulo_formato import CampoConvenciones
from componedor.simbolos import InformeExtraccion, extraer_simbolos
from componedor.transformaciones import PuntoMM
from componedor.unidades import pt_a_mm


def _exigir_que_no_exista(salida: Path, sobrescribir: bool) -> None:
    if salida.exists() and not sobrescribir:
        raise FileExistsError(
            f"El archivo '{salida}' ya existe. Use --sobrescribir para reemplazarlo."
        )


def hoja_vacia(orientacion: str, salida: Path, sobrescribir: bool = False) -> tuple[float, float]:
    """Guarda una hoja A1 vacía en `salida` y devuelve su tamaño (ancho, alto) en mm."""
    _exigir_que_no_exista(salida, sobrescribir)
    doc = crear_hoja(orientacion)
    salida.parent.mkdir(parents=True, exist_ok=True)
    rect = doc[0].rect
    doc.save(salida)
    doc.close()
    return pt_a_mm(rect.width), pt_a_mm(rect.height)


def _guardar(doc: pymupdf.Document, salida: Path) -> None:
    salida.parent.mkdir(parents=True, exist_ok=True)
    doc.save(salida)
    doc.close()


def hoja_formato(ruta_formato: Path, salida: Path, guias: bool = False,
                 sobrescribir: bool = False, usar_plantilla: bool = True,
                 ) -> tuple[Formato, InformePlantilla | None]:
    """Guarda en `salida` la hoja del formato: plantilla o marco, y guías si se piden."""
    _exigir_que_no_exista(salida, sobrescribir)
    formato = cargar_formato(ruta_formato, usar_plantilla)
    doc, informe = hoja_base(formato, guias)
    _guardar(doc, salida)
    return formato, informe


@dataclass(frozen=True)
class ResultadoColocar:
    ocupado: RectMM  # rectángulo de la página del detalle en la hoja, mm de papel
    plantilla: InformePlantilla | None
    dibujo_en_papel: RectMM | None = None  # page_bounds_mm en mm de papel (con manifiesto)
    coherencia: ResultadoVerificacion | None = None  # con manifiesto: verificación del paquete


def _texto_falla(c: Comprobacion) -> str:
    return f"{c.nombre}: {c.detalle or f'esperado {c.esperado}, medido {c.medido}'}"


def hoja_con_detalle(ruta_formato: Path, ruta_detalle: Path, salida: Path,
                     posicion_mm: tuple[float, float] | None = None, zona: str = "area_dibujo",
                     guias: bool = False, sobrescribir: bool = False,
                     usar_plantilla: bool = True, ruta_manifiesto: Path | None = None,
                     ancla: tuple[PuntoMM, PuntoMM] | None = None) -> ResultadoColocar:
    """Guarda en `salida` la hoja del formato con el detalle encima, sin escalar.

    `posicion_mm` None centra el detalle en la zona. `ancla` = (punto CAD, punto de papel
    en mm) reemplaza a `posicion_mm` y requiere `ruta_manifiesto` (matriz cad_to_page).
    Si algo falla, lanza el error antes de crear el archivo.
    """
    _exigir_que_no_exista(salida, sobrescribir)
    if ancla is not None and ruta_manifiesto is None:
        raise ValueError("Para usar un ancla CAD hace falta el manifiesto del detalle.")
    formato = cargar_formato(ruta_formato, usar_plantilla)
    manifiesto = coherencia = None
    if ruta_manifiesto is not None:
        aceptado = importar_paquete(ruta_manifiesto, pdf_esperado=ruta_detalle)
        manifiesto, coherencia = aceptado.manifiesto, aceptado.coherencia

    detalle = abrir_pdf(ruta_detalle, "el detalle", DetalleInvalido)
    try:
        # Alto real de la página que se coloca (coherente con page_size_mm ±0,1 mm).
        alto = tamano_visible_mm(detalle[0])[1]
        if ancla is not None:
            punto_cad, punto_papel = ancla
            posicion_mm = origen_para_ancla(punto_cad, punto_papel,
                                            manifiesto.pdf.dibujo.matriz, alto)
        doc, informe = hoja_base(formato, guias)
        ocupado = colocar_detalle(doc[0], formato, detalle, posicion_mm, zona=zona)
        _guardar(doc, salida)
    finally:
        detalle.close()

    dibujo = (limites_dibujo_en_papel(manifiesto.pdf.dibujo.limites_pagina_mm, alto, ocupado[:2])
              if manifiesto else None)
    return ResultadoColocar(ocupado, informe, dibujo, coherencia)


def _validar_opciones_colocar(args) -> str | None:
    """Mensaje de error si la combinación de opciones de `colocar` no es válida."""
    modos = [nombre for nombre, activo in (("--posicion", args.posicion is not None),
                                           ("--centrar", args.centrar),
                                           ("--ancla-cad", args.ancla_cad is not None))
             if activo]
    if len(modos) > 1:
        return f"Las opciones {' y '.join(modos)} son excluyentes: use solo una."
    if args.ancla_papel is not None and args.ancla_cad is None:
        return "--ancla-papel va junto con --ancla-cad."
    if args.ancla_cad is not None and args.ancla_papel is None:
        return "--ancla-cad requiere --ancla-papel X Y (dónde debe caer ese punto, mm de papel)."
    if args.ancla_cad is not None and args.manifiesto is None:
        return "--ancla-cad requiere --manifiesto (de ahí sale la matriz cad_to_page)."
    if not modos:
        return ("Indique dónde colocar el detalle: --posicion X Y, --centrar, o --ancla-cad X Y "
                "con --ancla-papel X Y.")
    return None


def texto_informe_plantilla(informe: InformePlantilla | None) -> str:
    if informe is None:
        return "Plantilla: no se usa (sin rótulo; se dibujó el marco del formato)."
    ancho, alto = informe.tamano_mm
    dx, dy = informe.diferencia_tamano_mm
    xmin, ymin, xmax, ymax = informe.marco_leido
    return (
        f"Plantilla: {informe.ruta} ({ancho:.2f} x {alto:.2f} mm; diferencia con la hoja "
        f"{dx:+.2f} x {dy:+.2f} mm, tolerancia ±{TOLERANCIA_TAMANO_MM} mm)\n"
        f"Marco del rótulo leído: X {xmin:.2f} a {xmax:.2f}, Y {ymin:.2f} a {ymax:.2f} mm "
        f"(diferencia máx. con el formato {informe.diferencia_marco_max_mm:.2f} mm, "
        f"tolerancia ±{TOLERANCIA_MARCO_MM} mm): coincide"
    )


def texto_verificacion_colocar(coherencia: ResultadoVerificacion) -> str:
    dif = coherencia.datos.get("diferencia_trazos_mm")
    return ("Paquete verificado: completo, integridad OK y coherencia OK "
            f"(trazos del PDF vs page_bounds_mm: diferencia máx. {dif:.3f} mm)")


def resumen_manifiesto(m: Manifiesto) -> str:
    """Resumen legible de un manifiesto ya validado."""
    ancho, alto = m.pdf.tamano_pagina_mm
    e_ancho, e_alto = m.pdf.tamano_esperado_mm
    x0, y0, x1, y1 = m.pdf.dibujo.limites_pagina_mm
    margen = "no indicado" if m.pdf.margen_mm is None else f"{m.pdf.margen_mm:g} mm"
    return "\n".join([
        f"Manifiesto: {m.ruta}",
        f"  Documento: {m.tipo_documento}, esquema {m.version_esquema}, modelo {m.version_modelo}",
        f"  Bloque: {m.bloque or '(no indicado)'}",
        f"  Escala: 1:{m.escala.denominador:g} ({m.escala.factor_mm_por_unidad_cad:g} mm de papel "
        f"por unidad CAD; {m.unidades.milimetros_por_unidad:g} mm reales por unidad CAD); "
        f"escala física garantizada: {'sí' if m.escala.fisica_garantizada else 'no'}",
        f"  PDF: {m.pdf.nombre_archivo}, {m.pdf.paginas} página(s), {m.pdf.bytes} bytes",
        f"  Tamaño de página: {ancho:.2f} x {alto:.2f} mm (esperado {e_ancho:.2f} x "
        f"{e_alto:.2f} mm, margen {margen})",
        f"  Dibujo en la página (page_bounds_mm): X {x0:.2f} a {x1:.2f}, Y {y0:.2f} a {y1:.2f}",
        f"  Estado de validación del exportador: {m.estado_validacion}",
        "Estructura del manifiesto: válida",
    ])


def texto_paquetes(paquetes: list[Paquete], carpeta: Path, recursivo: bool,
                   verificaciones: list[tuple[ResultadoVerificacion, ResultadoVerificacion]]
                   | None = None, sueltos: list[Path] = ()) -> str:
    """Tabla de paquetes (prefijo, estado, bloque, escala, página[, integridad, coherencia])
    y sus problemas.

    `verificaciones` (opción --verificar): (integridad, coherencia) en el mismo orden que
    `paquetes`. `sueltos`: PDF ignorados (sin manifiesto ni TXT), línea informativa al final.
    """
    donde = f"'{carpeta}'" + (" y sus subcarpetas" if recursivo else "")
    linea_sueltos = []
    if sueltos:
        nombres = ", ".join(r.relative_to(carpeta).as_posix() for r in sueltos)
        linea_sueltos = [f"PDF sin paquete (ignorados): {len(sueltos)} — {nombres}"]
    if not paquetes:
        return "\n".join([f"No se encontraron paquetes (<prefijo>{SUFIJO_MANIFIESTO}) en "
                          f"{donde}.", *(["", *linea_sueltos] if linea_sueltos else [])])

    def nombre(p: Paquete) -> str:
        relativa = p.carpeta.relative_to(carpeta)
        return p.prefijo if relativa == Path(".") else f"{relativa.as_posix()}/{p.prefijo}"

    filas = []
    for i, p in enumerate(paquetes):
        m = p.manifiesto
        filas.append((
            nombre(p), p.estado,
            (m.bloque or "-") if m else "-",
            f"1:{m.escala.denominador:g}" if m else "-",
            "{:.2f} x {:.2f}".format(*m.pdf.tamano_pagina_mm) if m else "-",
            *([r.etiqueta for r in verificaciones[i]] if verificaciones is not None else []),
        ))
    titulos = ("Prefijo", "Estado", "Bloque", "Escala", "Página (mm)",
               *(["Integridad", "Coherencia"] if verificaciones is not None else []))
    anchos = [max(len(str(f[i])) for f in [titulos, *filas]) for i in range(len(titulos))]
    linea = lambda f: "  ".join(str(v).ljust(a) for v, a in zip(f, anchos)).rstrip()  # noqa: E731
    lineas = [f"Paquetes en {donde}:", "", linea(titulos), "  ".join("-" * a for a in anchos)]
    lineas += [linea(f) for f in filas]

    con_problemas = [p for p in paquetes if p.problemas]
    if con_problemas:
        lineas += ["", "Problemas:"]
        for p in con_problemas:
            lineas.append(f"  {nombre(p)} ({p.estado}):")
            lineas += [f"    - {problema}" for problema in p.problemas]

    resumen = ""
    for indice, titulo in ((0, "integridad"), (1, "coherencia")):
        if verificaciones is None:
            break
        fallan = [(p, v[indice]) for p, v in zip(paquetes, verificaciones)
                  if v[indice].verificable and not v[indice].pasa]
        if fallan:
            lineas += ["", f"Problemas de {titulo}:"]
            for p, r in fallan:
                lineas.append(f"  {nombre(p)}:")
                lineas += [f"    - {_texto_falla(c)}" for c in r.fallas]
        ok = sum(1 for v in verificaciones if v[indice].etiqueta == "OK")
        resumen += f" {titulo.capitalize()}: {ok} OK, {len(fallan)} con falla."

    cuenta = {e: sum(1 for p in paquetes if p.estado == e) for e in (COMPLETO, INCOMPLETO, INVALIDO)}
    resumen = (f"{len(paquetes)} paquete(s): {cuenta[COMPLETO]} completo(s), "
               f"{cuenta[INCOMPLETO]} incompleto(s), {cuenta[INVALIDO]} inválido(s)." + resumen)
    lineas += ["", resumen, *linea_sueltos]
    return "\n".join(lineas)


def texto_verificar_paquete(paquete: Paquete,
                            verificacion: tuple[ResultadoVerificacion, ResultadoVerificacion]
                            ) -> str:
    """Todas las comprobaciones de integridad y coherencia de un paquete, y el resultado."""
    lineas = [f"Paquete: {paquete.prefijo} ({paquete.carpeta})", f"Estado: {paquete.estado}"]
    lineas += [f"  - {problema}" for problema in paquete.problemas]
    comprobaciones = []
    for titulo, r in zip(("INTEGRIDAD", "COHERENCIA"), verificacion):
        lineas += ["", f"== {titulo} =="]
        if not r.verificable:
            lineas.append(f"  ({r.motivo})")
            continue
        for c in r.comprobaciones:
            lineas.append(f"  [{'PASA' if c.pasa else 'FALLA'}] {c.nombre}")
            lineas.append(f"      esperado:   {c.esperado}")
            lineas.append(f"      medido:     {c.medido}")
            lineas.append(f"      tolerancia: {c.tolerancia}")
            if c.detalle:
                lineas.append(f"      detalle:    {c.detalle}")
        comprobaciones += r.comprobaciones
    if paquete.estado != COMPLETO:
        lineas += ["", f"RESULTADO: FALLA (paquete {paquete.estado}: no verificable)"]
    else:
        # Si la integridad falla, la coherencia queda sin verificar: cuentan las de integridad.
        lineas += ["", resultado_final(comprobaciones)]
    return "\n".join(lineas)


def texto_inventario(entradas: list[EntradaInventario], carpeta: Path, recursivo: bool,
                     zona: str | None) -> str:
    """Tabla del inventario, motivos de rechazo, notas y resumen. `zona` None: sin formato."""
    donde = f"'{carpeta}'" + (" y sus subcarpetas" if recursivo else "")
    if not entradas:
        return f"No se encontraron paquetes (<prefijo>{SUFIJO_MANIFIESTO}) en {donde}."

    def nombre(e: EntradaInventario) -> str:
        relativa = e.carpeta.relative_to(carpeta)
        return e.prefijo if relativa == Path(".") else f"{relativa.as_posix()}/{e.prefijo}"

    def tam(t) -> str:
        return "-" if t is None else f"{t[0]:.2f} x {t[1]:.2f}"

    titulos = ["Prefijo", "Bloque", "Escala", "Dibujo (mm)", "Página (mm)", "Estado"]
    if zona is not None:
        titulos.append("Cabe")
    filas = []
    for e in entradas:
        fila = [nombre(e), e.bloque or "-", f"1:{e.escala:g}" if e.escala else "-",
                tam(e.tamano_dibujo_mm), tam(e.tamano_pagina_mm), e.estado]
        if zona is not None:
            fila.append({True: "sí", False: "no", None: "-"}[e.cabe])
        filas.append(fila)
    anchos = [max(len(str(f[i])) for f in [titulos, *filas]) for i in range(len(titulos))]
    linea = lambda f: "  ".join(str(v).ljust(a) for v, a in zip(f, anchos)).rstrip()  # noqa: E731
    lineas = [f"Inventario de {donde}:", "", linea(titulos), "  ".join("-" * a for a in anchos)]
    lineas += [linea(f) for f in filas]

    rechazados = [e for e in entradas if e.estado == RECHAZADO]
    if rechazados:
        lineas += ["", "Motivos de rechazo:"]
        for e in rechazados:
            lineas.append(f"  {nombre(e)}:")
            lineas += [f"    - {motivo}" for motivo in e.motivos]
    con_notas = [e for e in entradas if e.notas]
    if con_notas:
        lineas += ["", "Notas:"]
        for e in con_notas:
            lineas.append(f"  {nombre(e)}:")
            lineas += [f"    - {nota}" for nota in e.notas]

    resumen = (f"{len(entradas)} detalle(s): {len(entradas) - len(rechazados)} aceptado(s), "
               f"{len(rechazados)} rechazado(s)")
    if zona is not None:
        resumen += f", {sum(1 for e in entradas if e.cabe is False)} no caben en {zona}"
    lineas += ["", resumen + "."]
    return "\n".join(lineas)


def texto_composicion(plano_ruta: Path, r: ResultadoComposicion) -> str:
    """Resumen de `componer`: detalles y su posición final, advertencias y ruta del PDF."""
    lineas = [f"Plano: {plano_ruta} ({len(r.detalles)} detalle(s))",
              texto_informe_plantilla(r.plantilla), "",
              "Detalles (en orden de apilado: el último queda encima):"]
    for c in r.detalles:
        x0, y0, x1, y1 = c.ocupado
        lineas.append(f"  {c.id}: paquete {c.prefijo}, esquina inferior izquierda "
                      f"({x0:.2f}, {y0:.2f}) mm; página X {x0:.2f} a {x1:.2f}, "
                      f"Y {y0:.2f} a {y1:.2f}")
    lineas += texto_rosa_y_rotulo(r)
    if r.advertencias:
        lineas += ["", f"Advertencias ({len(r.advertencias)}):"]
        lineas += [f"  - {a}" for a in r.advertencias]
    else:
        lineas += ["", "Advertencias: ninguna (sin traslapes entre detalles)."]
    verificado = ("el dibujo de cada detalle está donde dice el plano (±0,1 mm), el marco del "
                  "rótulo no se movió y no hay imágenes nuevas")
    if r.rosa is not None:
        verificado += "; la rosa quedó donde se pidió (±0,1 mm)"
    if r.rotulo or r.etiquetas:
        verificado += "; cada texto está en su sitio (±0,1 mm) y dentro de su celda"
    if r.simbolos:
        verificado += ("; cada símbolo de convenciones tiene sus trazos y está donde debía en su "
                       "casilla (±0,1 mm)")
    lineas += ["", f"Verificación: {verificado}.", f"PDF: {r.ruta_pdf}"]
    return "\n".join(lineas)


def texto_rosa_y_rotulo(r: ResultadoComposicion) -> list[str]:
    """Líneas del resumen sobre la rosa, el rótulo y las etiquetas de escala (subfase 4.1)."""
    lineas = []
    if r.rosa is not None:
        if r.rosa.destino is None:
            estado = "oculta"
        elif r.rosa.destino == r.rosa.original:
            estado = "en su sitio"
        else:
            estado = (f"movida: esquina inferior izquierda ({r.rosa.destino[0]:.2f}, "
                      f"{r.rosa.destino[1]:.2f}) mm")
        lineas += ["", f"Rosa de los vientos: {estado}."]
    if r.rotulo:
        llenos = sum(1 for v in r.rotulo.values() if v)
        lineas += ["", f"Rótulo: {llenos} campo(s) de texto con valor; ESCALA "
                       f"{r.rotulo.get('escala') or '(vacía)'}, REV. {r.rotulo.get('rev') or '(vacía)'}."]
    if r.notas is not None and r.notas.textos:
        reducida = (f" (pedida {r.notas.reducido_desde:.1f} mm)"
                    if r.notas.reducido_desde is not None else "")
        lineas.append(f"Notas: {len(r.notas.textos)} nota(s) en {r.notas.lineas} línea(s), "
                      f"a {r.notas.altura_mm:.1f} mm{reducida}.")
    if r.simbolos:
        reducidos = [s for s in r.simbolos if s.escala < 1]
        detalle = (" (" + ", ".join(f"{s.simbolo.id} al {s.escala * 100:.1f} %" for s in reducidos)
                   + ")" if reducidos else "")
        lineas.append(f"Convenciones: {len(r.simbolos)} símbolo(s): "
                      f"{len(r.simbolos) - len(reducidos)} a escala 1:1, {len(reducidos)} "
                      f"reducido(s){detalle}.")
    if r.rotulo or r.etiquetas:
        ids = ", ".join(r.etiquetas) if r.etiquetas else "ninguno"
        lineas.append(f"Etiquetas \"ESC: 1:N\": {len(r.etiquetas)} ({ids}).")
    return lineas


def _indice_del_formato(formato: Formato) -> Path:
    for campo in (formato.rotulo.campos.values() if formato.rotulo else []):
        if isinstance(campo, CampoConvenciones):
            return campo.biblioteca
    raise ValueError("El formato no tiene un campo de tipo \"convenciones\"; indique --indice.")


def texto_extraccion(informe: InformeExtraccion) -> str:
    """Resumen de `extraer-simbolos`."""
    lineas = [f"Biblioteca de símbolos: {informe.ruta_pdf} "
              f"({informe.ruta_pdf.stat().st_size / 1024:.1f} KB, {len(informe.simbolos)} "
              f"símbolo(s), uno por página)", f"Índice: {informe.ruta_indice}", ""]
    for s in informe.simbolos:
        ancho, alto = s.tamano_mm
        lineas.append(f"  {s.pagina:2d}. {s.id:<26} casilla {s.casilla_origen:2d}  "
                      f"{ancho:6.2f} x {alto:5.2f} mm  {s.trazos:4d} trazo(s)  "
                      f"«{s.descripcion}»")
    if informe.omitidas:
        lineas += ["", "Casillas con dibujo que no están en el índice (no se copiaron): "
                       + ", ".join(map(str, informe.omitidas))]
    lineas += ["", "Verificación: cada símbolo de la biblioteca tiene los mismos trazos que en el "
                   "plano y la misma caja (±0,1 mm); todo es vector.",
               "La biblioteca (simbolos/*.pdf) sale de un plano de ERCO: no se versiona."]
    return "\n".join(lineas)


def texto_preparar_editor(datos: dict, salida: Path) -> str:
    detalles, rechazados = datos["detalles"], datos["rechazados"]
    caben = sum(1 for d in detalles if d["cabe"])
    lineas = [f"Datos del editor en '{salida}':",
              f"  {ARCHIVO_DATOS}, {ARCHIVO_PLANTILLA} "
              f"({datos['imagen_plantilla']['ancho_px']} x {datos['imagen_plantilla']['alto_px']} px)"
              f" y {len(detalles)} miniatura(s) en {CARPETA_MINIATURAS}/",
              f"  Elementos fijos de la plantilla: {len(datos['elementos_plantilla'])}", ""]
    for d in detalles:
        lineas.append(f"  {d['id']}: 1:{d['escala']:g}, página {d['tamano_pagina_mm'][0]:.2f} x "
                      f"{d['tamano_pagina_mm'][1]:.2f} mm, "
                      f"{'cabe' if d['cabe'] else 'NO cabe'} en {ZONA_EDITABLE}")
    for r in rechazados:
        lineas.append(f"  {r['prefijo']}: rechazado ({len(r['motivos'])} motivo(s))")
    lineas += ["", f"{len(detalles)} aceptado(s), {len(rechazados)} rechazado(s), {caben} "
                   f"cabrían en {ZONA_EDITABLE}."]
    return "\n".join(lineas)


def texto_candidatos(candidatos: list[Candidato], salida: Path) -> str:
    """Candidatos a elementos de la plantilla y el bloque JSON listo para revisar."""
    if not candidatos:
        return (f"No se encontraron elementos de la plantilla dentro del área de dibujo.\n"
                f"PDF de verificación: {salida}")
    lineas = [f"Elementos de la plantilla dentro del área de dibujo ({len(candidatos)}):"]
    for i, c in enumerate(candidatos, start=1):
        contenido = [f"{c.trazos} trazo(s)"]
        if c.imagenes:
            contenido.append(f"{c.imagenes} imagen(es)")
        if c.textos:
            contenido.append("texto: " + " | ".join(c.textos))
        lineas.append(f"  {i}: X {c.rect[0]:.2f} a {c.rect[2]:.2f}, Y {c.rect[1]:.2f} a "
                      f"{c.rect[3]:.2f} mm ({c.rect[2] - c.rect[0]:.2f} x "
                      f"{c.rect[3] - c.rect[1]:.2f}); {', '.join(contenido)}")
    lineas += ["", "Para el formato (ponga un nombre a cada uno, después de revisar el PDF):",
               '"elementos_plantilla": [']
    filas = [f'  {{"nombre": "elemento_{i}", "rect_mm": [{c.rect[0]:.2f}, {c.rect[1]:.2f}, '
             f'{c.rect[2]:.2f}, {c.rect[3]:.2f}]}}' for i, c in enumerate(candidatos, start=1)]
    lineas += [",\n".join(filas), "]", "", f"PDF de verificación: {salida}"]
    return "\n".join(lineas)


def tabla_zonas(formato: Formato) -> str:
    """Tabla de texto con hoja, marco y cada zona: coordenadas y tamaño en mm."""
    filas = [("hoja", formato.hoja), ("marco", formato.marco), *formato.zonas.items()]
    lineas = [
        f"{'Elemento':<14}{'X min':>8}{'Y min':>8}{'X max':>8}{'Y max':>8}   Tamaño (mm)",
        "-" * 70,
    ]
    for nombre, (xmin, ymin, xmax, ymax) in filas:
        lineas.append(
            f"{nombre:<14}{xmin:>8.1f}{ymin:>8.1f}{xmax:>8.1f}{ymax:>8.1f}"
            f"   {xmax - xmin:.1f} x {ymax - ymin:.1f}"
        )
    return "\n".join(lineas)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="componedor", description="Componedor de planos PDF.")
    sub = parser.add_subparsers(dest="subcomando", required=True)

    p_hoja = sub.add_parser("hoja-vacia", help="Crea una hoja A1 vacía en PDF.")
    p_hoja.add_argument("--orientacion", default="horizontal",
                        help=f"{' o '.join(ORIENTACIONES)}: horizontal (841 x 594 mm), "
                             "vertical (594 x 841 mm).")
    p_hoja.add_argument("--salida", type=Path, required=True, help="Ruta del PDF a crear.")
    p_hoja.add_argument("--sobrescribir", action="store_true",
                        help="Reemplaza el archivo de salida si ya existe.")

    p_formato = sub.add_parser("hoja-formato", help="Crea una hoja con el marco de un formato.")
    p_formato.add_argument("--formato", type=Path, required=True,
                           help="Archivo JSON del formato (p. ej. formatos/A1_ERCO.json).")
    p_formato.add_argument("--salida", type=Path, required=True, help="Ruta del PDF a crear.")
    p_formato.add_argument("--guias", action="store_true",
                           help="Dibuja las zonas como guías discontinuas con su nombre.")
    p_formato.add_argument("--sobrescribir", action="store_true",
                           help="Reemplaza el archivo de salida si ya existe.")
    p_formato.add_argument("--sin-plantilla", action="store_true",
                           help="No usa la plantilla del rótulo aunque el formato la tenga.")

    p_colocar = sub.add_parser("colocar",
                               help="Coloca un detalle PDF (ya a escala) en una zona de la hoja.")
    p_colocar.add_argument("--formato", type=Path, required=True,
                           help="Archivo JSON del formato (p. ej. formatos/A1_ERCO.json).")
    p_colocar.add_argument("--detalle", type=Path, required=True,
                           help="PDF del detalle, ya a escala física (se coloca sin escalar).")
    p_colocar.add_argument("--salida", type=Path, required=True, help="Ruta del PDF a crear.")
    # Las combinaciones se validan en _validar_opciones_colocar (mensajes en español).
    p_colocar.add_argument("--posicion", type=float, nargs=2, metavar=("X", "Y"),
                           help="Esquina inferior izquierda del detalle en mm de papel.")
    p_colocar.add_argument("--centrar", action="store_true",
                           help="Centra el detalle en la zona.")
    p_colocar.add_argument("--manifiesto", type=Path,
                           help="Manifiesto JSON del detalle (matriz cad_to_page, page_bounds_mm).")
    p_colocar.add_argument("--ancla-cad", type=float, nargs=2, metavar=("X", "Y"),
                           help="Punto en coordenadas CAD (unidades del dibujo). "
                                "Requiere --ancla-papel y --manifiesto.")
    p_colocar.add_argument("--ancla-papel", type=float, nargs=2, metavar=("X", "Y"),
                           help="Dónde debe caer el punto --ancla-cad, en mm de papel.")
    p_colocar.add_argument("--zona", default="area_dibujo",
                           help="Zona destino del formato (por defecto area_dibujo).")
    p_colocar.add_argument("--guias", action="store_true",
                           help="Dibuja las zonas como guías discontinuas con su nombre.")
    p_colocar.add_argument("--sobrescribir", action="store_true",
                           help="Reemplaza el archivo de salida si ya existe.")
    p_colocar.add_argument("--sin-plantilla", action="store_true",
                           help="No usa la plantilla del rótulo aunque el formato la tenga.")

    p_ref = sub.add_parser("referencia",
                           help="Compone un detalle de medidas conocidas, mide el PDF e informa.")
    p_ref.add_argument("--formato", type=Path, required=True,
                       help="Archivo JSON del formato (p. ej. formatos/A1_ERCO.json).")
    p_ref.add_argument("--salida", type=Path, required=True,
                       help="PDF a crear; el informe se guarda junto con extensión .txt.")
    p_ref.add_argument("--sin-plantilla", action="store_true",
                       help="No usa la plantilla del rótulo aunque el formato la tenga.")
    p_ref.add_argument("--sobrescribir", action="store_true",
                       help="Reemplaza el PDF y el TXT si ya existen.")
    p_ref.add_argument("--detalle", type=Path,
                       help="Opcional: PDF de un detalle real para comparar con su manifiesto.")
    p_ref.add_argument("--manifiesto", type=Path,
                       help="Manifiesto del --detalle (van juntos).")

    p_man = sub.add_parser("leer-manifiesto",
                           help="Lee un manifiesto del exportador y muestra un resumen.")
    p_man.add_argument("ruta", type=Path, help="Archivo <prefijo>.manifest.json.")

    p_paq = sub.add_parser("paquetes",
                           help="Localiza los paquetes del exportador en una carpeta.")
    p_paq.add_argument("carpeta", type=Path, help="Carpeta con <prefijo>.manifest.json y PDF.")
    p_paq.add_argument("--recursivo", action="store_true", help="Busca también en subcarpetas.")
    p_paq.add_argument("--verificar", action="store_true",
                       help="Verifica integridad (bytes, SHA-256, abre, 1 página) y coherencia "
                            "(geometría del manifiesto contra el PDF).")

    p_ver = sub.add_parser("verificar-paquete",
                           help="Muestra todas las comprobaciones de integridad y coherencia.")
    p_ver.add_argument("manifiesto", type=Path, help="Archivo <prefijo>.manifest.json.")

    p_html = sub.add_parser("editor",
                            help="Genera el editor HTML de planos (un solo archivo, sin servidor).")
    p_html.add_argument("carpeta", type=Path, help="Carpeta con los paquetes del exportador.")
    p_html.add_argument("--formato", type=Path, required=True,
                        help="Formato de hoja (p. ej. formatos/A1_ERCO.json).")
    p_html.add_argument("--salida", type=Path, required=True,
                        help="Carpeta del editor: editor.html, datos e imágenes (y ahí va el "
                             "plano.json).")
    p_html.add_argument("--sobrescribir", action="store_true",
                        help="Reemplaza lo que genera el editor si la carpeta ya tiene contenido.")

    p_ed = sub.add_parser("preparar-editor",
                          help="Prepara los datos e imágenes del editor de planos.")
    p_ed.add_argument("carpeta", type=Path, help="Carpeta con los paquetes del exportador.")
    p_ed.add_argument("--formato", type=Path, required=True,
                      help="Formato de hoja (p. ej. formatos/A1_ERCO.json).")
    p_ed.add_argument("--salida", type=Path, required=True,
                      help="Carpeta donde escribir editor_datos.json, plantilla.png y miniaturas/.")
    p_ed.add_argument("--sobrescribir", action="store_true",
                      help="Reemplaza los datos del editor si la carpeta ya tiene contenido.")

    p_det = sub.add_parser("detectar-elementos",
                           help="Mide los elementos fijos de la plantilla dentro del área de "
                                "dibujo y genera un PDF de verificación.")
    p_det.add_argument("--formato", type=Path, required=True,
                       help="Formato con plantilla (p. ej. formatos/A1_ERCO.json).")
    p_det.add_argument("--salida", type=Path, required=True,
                       help="PDF de verificación a crear.")
    p_det.add_argument("--sobrescribir", action="store_true",
                       help="Reemplaza el archivo de salida si ya existe.")

    p_sim = sub.add_parser("extraer-simbolos",
                           help="Arma la biblioteca de símbolos de convenciones (vector) a "
                                "partir de la leyenda de un plano real.")
    p_sim.add_argument("plano", type=Path, help="PDF del plano con la leyenda CONVENCIONES.")
    p_sim.add_argument("--formato", type=Path, default=Path("formatos/A1_ERCO.json"),
                       help="Formato con la rejilla de convenciones (por defecto "
                            "formatos/A1_ERCO.json).")
    p_sim.add_argument("--pagina", type=int, default=1,
                       help="Página del plano con la leyenda (desde 1; por defecto 1).")
    p_sim.add_argument("--indice", type=Path,
                       help="indice.json a escribir (por defecto, la biblioteca del formato).")

    p_comp = sub.add_parser("componer",
                            help="Compone un plano con varios detalles a partir de un plano.json.")
    p_comp.add_argument("plano", type=Path, help="Archivo plano.json (ver docs/formato_plano.md).")
    p_comp.add_argument("--salida", type=Path, required=True, help="Ruta del PDF a crear.")
    p_comp.add_argument("--sobrescribir", action="store_true",
                        help="Reemplaza el archivo de salida si ya existe.")
    p_comp.add_argument("--guias", action="store_true",
                        help="Dibuja las zonas como guías discontinuas con su nombre.")

    p_inv = sub.add_parser("inventario",
                           help="Inventario de detalles: aceptados, rechazados y si caben.")
    p_inv.add_argument("carpeta", type=Path, help="Carpeta con los paquetes del exportador.")
    p_inv.add_argument("--recursivo", action="store_true", help="Busca también en subcarpetas.")
    p_inv.add_argument("--formato", type=Path,
                       help="Formato de hoja (p. ej. formatos/A1_ERCO.json): agrega «Cabe».")
    p_inv.add_argument("--zona", default="area_dibujo",
                       help="Zona del formato para «Cabe» (por defecto area_dibujo).")

    args = parser.parse_args(argv)

    try:
        if args.subcomando == "hoja-vacia":
            ancho, alto = hoja_vacia(args.orientacion, args.salida, args.sobrescribir)
            print(f"Hoja creada: {args.salida}")
            print(f"Tamaño de la página: {ancho:.1f} x {alto:.1f} mm ({args.orientacion})")
        elif args.subcomando == "hoja-formato":
            formato, informe = hoja_formato(args.formato, args.salida, args.guias,
                                            args.sobrescribir, not args.sin_plantilla)
            print(f"Hoja creada: {args.salida} (formato {formato.nombre})")
            print(texto_informe_plantilla(informe))
            print(tabla_zonas(formato))
        elif args.subcomando == "colocar":
            error = _validar_opciones_colocar(args)
            if error:
                print(f"Error: {error}", file=sys.stderr)
                return 2
            posicion = tuple(args.posicion) if args.posicion else None
            ancla = (tuple(args.ancla_cad), tuple(args.ancla_papel)) if args.ancla_cad else None
            r = hoja_con_detalle(
                args.formato, args.detalle, args.salida, posicion, args.zona,
                args.guias, args.sobrescribir, not args.sin_plantilla,
                args.manifiesto, ancla,
            )
            xmin, ymin, xmax, ymax = r.ocupado
            print(f"Hoja creada: {args.salida}")
            print(texto_informe_plantilla(r.plantilla))
            if ancla:
                print(f"Ancla: punto CAD ({ancla[0][0]}, {ancla[0][1]}) -> papel "
                      f"({ancla[1][0]:.2f}, {ancla[1][1]:.2f}) mm")
            print(f"Tamaño del detalle: {xmax - xmin:.1f} x {ymax - ymin:.1f} mm")
            print(f"Rectángulo ocupado (mm): X {xmin:.2f} a {xmax:.2f}, Y {ymin:.2f} a {ymax:.2f}"
                  f" (zona {args.zona})")
            if r.dibujo_en_papel:
                dx0, dy0, dx1, dy1 = r.dibujo_en_papel
                print(f"Rectángulo del dibujo (page_bounds_mm en papel): X {dx0:.2f} a {dx1:.2f}, "
                      f"Y {dy0:.2f} a {dy1:.2f}")
            if r.coherencia is not None:
                print(texto_verificacion_colocar(r.coherencia))
        elif args.subcomando == "referencia":
            if (args.detalle is None) != (args.manifiesto is None):
                print("Error: --detalle y --manifiesto van juntos.", file=sys.stderr)
                return 2
            r = ejecutar_referencia(args.formato, args.salida, not args.sin_plantilla,
                                    args.sobrescribir, args.detalle, args.manifiesto)
            print(r.texto, end="")
            print(f"PDF: {r.ruta_pdf}\nInforme: {r.ruta_txt}")
            return 0 if r.pasa else 1
        elif args.subcomando == "leer-manifiesto":
            print(resumen_manifiesto(leer_manifiesto(args.ruta)))
        elif args.subcomando == "paquetes":
            paquetes, sueltos = localizar_con_sueltos(args.carpeta, args.recursivo)
            verificaciones = ([verificar_paquete(p) for p in paquetes] if args.verificar
                              else None)
            print(texto_paquetes(paquetes, args.carpeta, args.recursivo, verificaciones, sueltos))
            todos_completos = all(p.estado == COMPLETO for p in paquetes)
            sin_fallas = all(r.pasa or not r.verificable
                             for v in verificaciones or [] for r in v)
            return 0 if todos_completos and sin_fallas else 1
        elif args.subcomando == "editor":
            ruta_html = generar_editor(args.carpeta, args.formato, args.salida, args.sobrescribir)
            carpeta = ruta_html.parent.resolve()
            print(f"Editor generado: {ruta_html.resolve()}")
            print("Ábralo con doble clic (Edge o Chrome); no necesita servidor ni internet.")
            print(f"Guarde el plano.json en la MISMA carpeta que editor.html: {carpeta}")
            print(f"Luego: python -m componedor.cli componer \"{carpeta / 'plano.json'}\" "
                  f"--salida \"{carpeta / 'plano.pdf'}\"")
        elif args.subcomando == "preparar-editor":
            datos = preparar_editor(args.carpeta, args.formato, args.salida, args.sobrescribir)
            print(texto_preparar_editor(datos, args.salida))
        elif args.subcomando == "detectar-elementos":
            _exigir_que_no_exista(args.salida, args.sobrescribir)
            formato = cargar_formato(args.formato)
            candidatos = detectar_elementos(formato)
            pdf_verificacion(formato, candidatos, args.salida)
            print(texto_candidatos(candidatos, args.salida))
        elif args.subcomando == "extraer-simbolos":
            formato = cargar_formato(args.formato, usar_plantilla=False)
            indice = args.indice or _indice_del_formato(formato)
            informe = extraer_simbolos(args.plano, formato, indice, args.pagina)
            print(texto_extraccion(informe))
        elif args.subcomando == "componer":
            plano = leer_plano(args.plano)
            resultado = componer_plano(plano, args.salida, args.sobrescribir, args.guias)
            print(texto_composicion(args.plano, resultado))
        elif args.subcomando == "inventario":
            formato = (cargar_formato(args.formato, usar_plantilla=False)
                       if args.formato else None)
            entradas = construir_inventario(args.carpeta, formato, args.zona, args.recursivo)
            print(texto_inventario(entradas, args.carpeta, args.recursivo,
                                   args.zona if formato else None))
            return 1 if any(e.estado == RECHAZADO for e in entradas) else 0
        elif args.subcomando == "verificar-paquete":
            paquete = paquete_de_manifiesto(args.manifiesto)
            verificacion = verificar_paquete(paquete)
            print(texto_verificar_paquete(paquete, verificacion))
            return 0 if paquete.estado == COMPLETO and all(r.pasa for r in verificacion) else 1
    # FormatoInvalido, DetalleInvalido, PlantillaInvalida y ManifiestoInvalido son ValueError.
    except (FileExistsError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
