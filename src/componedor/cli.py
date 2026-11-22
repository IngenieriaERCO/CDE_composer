"""Interfaz de línea de comandos: python -m componedor.cli <subcomando> ..."""

import argparse
import json
import sys
import webbrowser
from dataclasses import dataclass, replace
from pathlib import Path

import pymupdf

from componedor.aplicacion_editor import AplicacionEditor
from componedor.cad_a_papel import limites_dibujo_en_papel, origen_para_ancla
from componedor.coherencia import verificar_paquete
from componedor.importador import importar_paquete
from componedor.inventario import RECHAZADO, EntradaInventario, construir_inventario
from componedor.colocar import DetalleInvalido, abrir_pdf, colocar_detalle, tamano_visible_mm
from componedor.comando_referencia import ejecutar_referencia
from componedor.componer import ResultadoComposicion, componer_plano
from componedor.composicion import hoja_base
from componedor.configuracion import (
    ConfigEditor,
    leer_config_componer,
    leer_config_editor,
    leer_config_exportador,
    leer_config_ortofoto,
)
from componedor.editor_html import ARCHIVO_HTML, datos_incrustados, generar_editor
from componedor.datos_editor import (
    ARCHIVO_DATOS,
    ARCHIVO_PLANTILLA,
    CARPETA_MINIATURAS,
    ZONA_EDITABLE,
    preparar_editor,
)
from componedor.elementos_plantilla import Candidato, detectar_elementos, pdf_verificacion
from componedor.plano import Plano, leer_plano
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
from componedor.plantilla_v3 import ORIGEN as PLANTILLA_V2
from componedor.plantilla_v3 import DESTINO as PLANTILLA_V3
from componedor.plantilla_v3 import crear_plantilla_v3
from componedor.plantilla_v3 import texto_informe as texto_informe_v3
from componedor.rotulo_formato import CampoConvenciones
from componedor.servidor import ServidorEditor
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


def opciones_editor(args) -> tuple[ConfigEditor | None, str | None]:
    """Rutas del subcomando `editor`: del archivo --config o de la línea de comandos, nunca
    mezcladas. Devuelve (opciones, None) o (None, mensaje de error de uso)."""
    a_mano = {"carpeta": args.carpeta, "--formato": args.formato, "--salida": args.salida,
              "--notas": args.notas, "--firmas": args.firmas, "--proyecto": args.proyecto}
    if args.config is not None:
        repetidas = [nombre for nombre, valor in a_mano.items() if valor is not None]
        if repetidas:
            return None, (f"con --config las rutas salen del archivo; quite {', '.join(repetidas)} "
                          f"o no use --config.")
        return leer_config_editor(args.config), None  # ConfigInvalida es ValueError
    faltan = [n for n in ("carpeta", "--formato", "--salida") if a_mano[n] is None]
    if faltan:
        return None, (f"falta {', '.join(faltan)} (o use --config componedor.json).")
    return ConfigEditor(args.carpeta, args.formato, args.salida, args.notas, args.firmas,
                        args.proyecto), None


CODIGO_AVISOS = 3  # componer --codigo-avisos: PDF generado, con advertencias


def opciones_componer(args, plano: Plano) -> tuple[Plano, Path | None, str | None]:
    """Plano y salida de `componer`. Con --config: el formato del archivo (avisa si el plano
    indicaba otro) y el PDF en <resultados>/<nombre del plano>.pdf. Sin --config: --salida."""
    if args.config is None:
        if args.salida is None:
            return plano, None, "falta --salida (o use --config componedor.json)."
        return plano, args.salida, None
    if args.salida is not None:
        return plano, None, ("con --config el PDF va a la carpeta de resultados del archivo; "
                             "quite --salida o no use --config.")
    config = leer_config_componer(args.config)  # ConfigInvalida es ValueError
    print(f"Configuración: {args.config.resolve()}")
    if plano.formato.resolve() != config.formato.resolve():
        print(f"Aviso: el plano indica el formato '{plano.formato}'; se usa el de la "
              f"configuración, '{config.formato}'.")
    config.resultados.mkdir(parents=True, exist_ok=True)
    return (replace(plano, formato=config.formato),
            config.resultados / f"{args.plano.stem}.pdf", None)


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


def texto_ortofoto(r: ResultadoComposicion) -> list[str]:
    """Las líneas de la ortofoto en el resumen de `componer` (nada si el plano no tiene)."""
    o = r.ortofoto
    if o is None:
        return []
    de = "la copia reducida" if o.fuente == "copia" else "el original"
    lineas = ["", (f"Ortofoto ({de}: {o.archivo}): {len(o.mosaicos)} mosaico(s) JPEG a "
                   f"{o.ppp} ppp, calidad {o.calidad_jpeg}, opacidad {o.opacidad * 100:.0f} %, "
                   f"{o.bytes_jpeg / 1024 / 1024:.1f} MB.")]
    for ident, cobertura in o.cobertura.items():
        ancho, alto = o.px[ident]
        lineas.append(f"  {ident}: {ancho} × {alto} px, cubre el {cobertura * 100:.0f} % de su "
                      f"página")
    if r.extendida:
        lineas.append("  Extendida a toda el área de dibujo (los detalles sin ortofoto, con fondo "
                      "blanco).")
    for c in r.cuadriculas:
        lineas.append(f"  Cuadrícula de {c.detalle}: cada {c.intervalo_m:g} m, {len(c.este)} "
                      f"línea(s) de Este y {len(c.norte)} de Norte, {len(c.etiquetas)} "
                      f"etiqueta(s)" + (f" ({c.omitidas} omitida(s))" if c.omitidas else "") + ".")
    if r.copia is not None:
        estado = "escrita" if r.copia.escrita else "ya estaba al día"
        lineas.append(f"  Copia reducida {estado}: {r.copia.carpeta} ({r.copia.archivos} "
                      f"archivo(s), {r.copia.bytes / 1024 / 1024:.1f} MB).")
    return lineas


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
    lineas += texto_ortofoto(r)
    if r.localizacion is not None:
        loc = r.localizacion
        de = "la copia" if loc.origen == "copia" else "el original"
        reducida = (f", reducida de {loc.px_original[0]} × {loc.px_original[1]} px"
                    if loc.px != loc.px_original else "")
        lineas += ["", (f"Imagen de localización ({de}: {loc.archivo.name}): "
                        f"{loc.formato.upper()} de {loc.px[0]} × {loc.px[1]} px{reducida}, a "
                        f"{loc.ppp:.0f} ppp, en X {loc.destino[0]:.1f} a {loc.destino[2]:.1f}, "
                        f"Y {loc.destino[1]:.1f} a {loc.destino[3]:.1f} mm.")]
    if r.advertencias:
        lineas += ["", f"Advertencias ({len(r.advertencias)}):"]
        lineas += [f"  - {a}" for a in r.advertencias]
    else:
        lineas += ["", "Advertencias: ninguna (sin traslapes entre detalles)."]
    extras = []
    if r.firmas:
        extras.append(f"las {len(r.firmas)} firma(s)")
    if r.ortofoto is not None and r.ortofoto.mosaicos:
        extras.append(f"los {len(r.ortofoto.mosaicos)} mosaico(s) de la ortofoto")
    if r.localizacion is not None:
        extras.append("la imagen de localización")
    imagenes = (f"no hay más imágenes que las de la plantilla y {' y '.join([', '.join(extras[:-1]), extras[-1]] if len(extras) > 1 else extras)} (los "
                f"detalles siguen siendo vectores)" if extras else "no hay imágenes nuevas")
    verificado = ("el dibujo de cada detalle está donde dice el plano (±0,1 mm), el marco del "
                  f"rótulo no se movió y {imagenes}")
    if r.rosa is not None:
        verificado += "; la rosa quedó donde se pidió (±0,1 mm)"
    if r.rotulo or r.etiquetas:
        verificado += "; cada texto está en su sitio (±0,1 mm) y dentro de su celda"
    if r.simbolos:
        verificado += ("; cada símbolo de convenciones tiene sus trazos y está donde debía en su "
                       "casilla (±0,1 mm)")
    if r.muestras:
        verificado += ("; cada muestra de línea o relleno de las convenciones está en su casilla "
                       "(±0,1 mm) con su color, grosor, trazo y opacidad")
    if r.ortofoto is not None and r.ortofoto.mosaicos:
        verificado += "; cada mosaico de la ortofoto es JPEG y está en su sitio (±0,1 mm)"
    if r.localizacion is not None:
        verificado += ("; la imagen de localización está en su recuadro (±0,1 mm) con los píxeles "
                       "esperados" + (" y sigue siendo el JPEG original" if r.localizacion.formato
                                      == "jpeg" else ""))
    if r.firmas:
        verificado += ("; cada firma en imagen está dentro de su caja en la columna FIRMA sin "
                       "pisar el encabezado (±0,1 mm), con su máscara de transparencia y es la "
                       "del archivo leído")
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
    if r.muestras:
        n_lineas = sum(m.muestra.tipo == "linea" for m in r.muestras)
        lineas.append(f"Convenciones: {n_lineas} línea(s) y {len(r.muestras) - n_lineas} "
                      f"relleno(s) dibujados como vector.")
    if r.firmas:
        lineas.append(f"Firmas en imagen: {len(r.firmas)} ("
                      + ", ".join(f"{f.ruta_celda}: {f.id} al {f.escala * 100:.0f} % de su tamaño "
                                  f"a 300 ppp" for f in r.firmas) + ").")
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
    lineas += texto_rotulo_editor(datos)
    return "\n".join(lineas)


def texto_rotulo_editor(datos: dict) -> list[str]:
    """Qué trae el editor del rótulo (subfase 4.3a): notas típicas, símbolos y avisos."""
    rotulo = datos.get("rotulo")
    if not rotulo:
        return []
    lineas = [""]
    notas = rotulo.get("notas")
    if notas is None:
        lineas.append("Rótulo: sin catálogo de notas típicas (use --notas <carpeta>).")
    else:
        archivos = [a for g in notas["grupos"] for a in g["archivos"]]
        total = sum(len(a["notas"]) for a in archivos)
        vinetas = sum(len(n["vinetas"]) for a in archivos for n in a["notas"])
        lineas.append(f"Rótulo: {total} nota(s) típica(s) ({vinetas} viñeta(s)) en "
                      f"{len(archivos)} archivo(s) y {len(notas['grupos'])} grupo(s): "
                      + ", ".join(g["titulo"] for g in notas["grupos"]) + ".")
        for a in archivos:
            for problema in a["problemas"]:
                lineas.append(f"  - Problema: {problema}")  # ya empieza con el archivo
            for aviso in a["avisos"]:
                lineas.append(f"  - {aviso}")
        for aviso in notas["avisos"]:
            lineas.append(f"  - {aviso}")
    lineas.append(f"Símbolos de convenciones: {len(rotulo['simbolos'])} (PNG a 20 px/mm, solo para "
                  f"mostrar). Firmas en imagen: no se incrustan.")
    personas = rotulo.get("personas_firmas")
    if personas is not None:
        lineas.append(f"Personas con firma (solo el nombre): {len(personas)}"
                      + (": " + ", ".join(personas) if personas else "") + ".")
    proyecto = rotulo.get("proyecto")
    if proyecto is not None:
        prellena = [c for c in ("disenador", "revisor", "prefijo_no_plano") if c in proyecto]
        prellena += [f"firmas.{f}" for f in proyecto.get("firmas", {})]
        lineas.append(f"Proyecto{' «' + proyecto['nombre'] + '»' if proyecto.get('nombre') else ''}"
                      f": prellena un plano nuevo con {', '.join(prellena) or 'nada'}.")
    for aviso in rotulo["avisos"]:
        lineas.append(f"  - {aviso}")
    return lineas


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


INACTIVIDAD_MIN = 30.0


def preparar_servidor(args) -> ServidorEditor:
    """El servidor del editor según componedor.json (sin arrancarlo todavía)."""
    config = leer_config_editor(args.config)
    ruta_html = config.salida / ARCHIVO_HTML
    if not ruta_html.is_file():
        raise ValueError(f"No existe {ruta_html}: genere primero el editor "
                         f"(«Abrir editor.bat» lo hace, o el subcomando editor --config).")
    formato = cargar_formato(config.formato, usar_plantilla=False)
    exportador = leer_config_exportador(args.config)
    app = AplicacionEditor(ruta_html, formato.zonas[ZONA_EDITABLE], exportador,
                           intervalo_cuadricula_m=leer_config_ortofoto(
                               args.config).cuadricula_intervalo_m)
    registro = exportador.trabajo / "servidor.log" if exportador else None
    return ServidorEditor(app, args.puerto, registro=registro)


def correr_servidor(args) -> int:
    servidor = preparar_servidor(args)
    servidor.iniciar()
    motivo = servidor.app.motivo_sin_exportador()
    print(f"Editor con servidor local: {servidor.url}")
    print("«Cargar DXF»: " + ("disponible." if motivo is None else f"no disponible. {motivo}"))
    print("No cierre esta ventana mientras use el editor: al cerrarla se apaga el servidor "
          "(y el trabajador del exportador). Ctrl+C también lo apaga.")
    if not args.no_abrir:
        webbrowser.open(servidor.url)
    inactividad = args.inactividad_min * 60 if args.inactividad_min > 0 else None
    try:
        motivo_fin = servidor.esperar(inactividad)
    except KeyboardInterrupt:
        motivo_fin = "detenido"
    finally:
        servidor.detener()
        servidor.app.cerrar()
    if motivo_fin == "inactividad":
        print(f"Servidor apagado: {args.inactividad_min:g} min sin señal del editor.")
    else:
        print("Servidor apagado.")
    return 0


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
    p_html.add_argument("carpeta", type=Path, nargs="?",
                        help="Carpeta con los paquetes del exportador (sin --config).")
    p_html.add_argument("--config", type=Path,
                        help="componedor.json con todas las rutas del editor (paquetes, formato, "
                             "salida, notas, firmas, proyecto); no se combina con ellas.")
    p_html.add_argument("--formato", type=Path,
                        help="Formato de hoja (p. ej. formatos/A1_ERCO.json).")
    p_html.add_argument("--salida", type=Path,
                        help="Carpeta del editor: editor.html, datos e imágenes (y ahí va el "
                             "plano.json).")
    p_html.add_argument("--notas", type=Path,
                        help="Carpeta con las notas típicas (.txt, una nota por línea; cada "
                             "subcarpeta es un grupo del catálogo).")
    p_html.add_argument("--firmas", type=Path,
                        help="Carpeta de firmas (una subcarpeta por persona): el editor lista "
                             "los NOMBRES; las imágenes nunca se incrustan.")
    p_html.add_argument("--proyecto", type=Path,
                        help="proyecto.json con los datos que se repiten (diseñador, revisor, "
                             "firmas, prefijo del No. PLANO) para prellenar un plano nuevo.")
    p_html.add_argument("--sobrescribir", action="store_true",
                        help="Reemplaza lo que genera el editor si la carpeta ya tiene contenido.")

    p_srv = sub.add_parser("servidor",
                           help="Abre el editor con un servidor local (solo 127.0.0.1) para "
                                "«Cargar DXF» con el trabajador del exportador.")
    p_srv.add_argument("--config", type=Path, required=True,
                       help="componedor.json (editor.html de editor.salida, formato y sección "
                            "exportador).")
    p_srv.add_argument("--puerto", type=int, default=0,
                       help="Puerto local (0: el que elija el sistema).")
    p_srv.add_argument("--no-abrir", action="store_true",
                       help="No abre el navegador (solo muestra la dirección).")
    p_srv.add_argument("--inactividad-min", type=float, default=INACTIVIDAD_MIN,
                       help=f"Se apaga solo tras estos minutos sin señal del editor "
                            f"(por defecto {INACTIVIDAD_MIN:g}; 0: nunca).")

    p_ed = sub.add_parser("preparar-editor",
                          help="Prepara los datos e imágenes del editor de planos.")
    p_ed.add_argument("carpeta", type=Path, help="Carpeta con los paquetes del exportador.")
    p_ed.add_argument("--formato", type=Path, required=True,
                      help="Formato de hoja (p. ej. formatos/A1_ERCO.json).")
    p_ed.add_argument("--salida", type=Path, required=True,
                      help="Carpeta donde escribir editor_datos.json, plantilla.png y miniaturas/.")
    p_ed.add_argument("--notas", type=Path,
                      help="Carpeta con las notas típicas (.txt; cada subcarpeta es un grupo).")
    p_ed.add_argument("--firmas", type=Path,
                      help="Carpeta de firmas: solo se toman los nombres de las personas.")
    p_ed.add_argument("--proyecto", type=Path, help="proyecto.json para prellenar un plano nuevo.")
    p_ed.add_argument("--sobrescribir", action="store_true",
                      help="Reemplaza los datos del editor si la carpeta ya tiene contenido.")

    p_v3 = sub.add_parser("crear-plantilla-v3",
                          help="Crea plantillas/rotulo_A1_ERCO_v3.pdf desde la v2 (sin tocarla): "
                               "quita la fila DISEÑADOR | REVISOR y centra el logo.")
    p_v3.add_argument("--origen", type=Path, default=PLANTILLA_V2,
                      help=f"Plantilla v2 (por defecto {PLANTILLA_V2.as_posix()}).")
    p_v3.add_argument("--salida", type=Path, default=PLANTILLA_V3,
                      help=f"Plantilla v3 a crear (por defecto {PLANTILLA_V3.as_posix()}).")
    p_v3.add_argument("--sobrescribir", action="store_true",
                      help="Reemplaza la salida si ya existe.")

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
    p_comp.add_argument("--salida", type=Path,
                        help="Ruta del PDF a crear (sin --config, obligatoria).")
    p_comp.add_argument("--config", type=Path,
                        help="componedor.json: compone con SU formato (aunque el plano diga otro) "
                             "y deja el PDF en <resultados>/<nombre del plano>.pdf; no se combina "
                             "con --salida.")
    p_comp.add_argument("--sobrescribir", action="store_true",
                        help="Reemplaza el archivo de salida si ya existe.")
    p_comp.add_argument("--guias", action="store_true",
                        help="Dibuja las zonas como guías discontinuas con su nombre.")
    p_comp.add_argument("--codigo-avisos", action="store_true",
                        help=f"Termina con código {CODIGO_AVISOS} si el PDF se generó pero con "
                             f"advertencias (para los accesos directos).")

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
            opciones, error = opciones_editor(args)
            if error:
                print(f"Error: {error}", file=sys.stderr)
                return 2
            if args.config is not None:
                print(f"Configuración: {args.config.resolve()}")
            ruta_html = generar_editor(opciones.paquetes, opciones.formato, opciones.salida,
                                       args.sobrescribir, carpeta_notas=opciones.notas,
                                       carpeta_firmas=opciones.firmas,
                                       ruta_proyecto=opciones.proyecto)
            carpeta = ruta_html.parent.resolve()
            print(f"Editor generado: {ruta_html.resolve()} "
                  f"({ruta_html.stat().st_size / 1024:.0f} KB)")
            datos_html = datos_incrustados(ruta_html.read_text(encoding="utf-8"))
            for linea in texto_rotulo_editor(datos_html)[1:]:
                print(linea)
            print("Ábralo con doble clic (Edge o Chrome); no necesita servidor ni internet.")
            print(f"Guarde el plano.json en la MISMA carpeta que editor.html: {carpeta}")
            print(f"Luego: python -m componedor.cli componer \"{carpeta / 'plano.json'}\" "
                  f"--salida \"{carpeta / 'plano.pdf'}\"")
        elif args.subcomando == "servidor":
            return correr_servidor(args)
        elif args.subcomando == "preparar-editor":
            datos = preparar_editor(args.carpeta, args.formato, args.salida, args.sobrescribir,
                                    carpeta_notas=args.notas, carpeta_firmas=args.firmas,
                                    ruta_proyecto=args.proyecto)
            print(texto_preparar_editor(datos, args.salida))
        elif args.subcomando == "crear-plantilla-v3":
            informe = crear_plantilla_v3(args.origen, args.salida, args.sobrescribir)
            print(texto_informe_v3(informe, args.origen))
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
            plano, salida, error = opciones_componer(args, plano)
            if error:
                print(f"Error: {error}", file=sys.stderr)
                return 2
            config_orto = leer_config_ortofoto(args.config) if args.config else None
            resultado = componer_plano(plano, salida, args.sobrescribir, args.guias,
                                       config_orto)
            print(texto_composicion(args.plano, resultado))
            if args.codigo_avisos and resultado.advertencias:
                return CODIGO_AVISOS
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
