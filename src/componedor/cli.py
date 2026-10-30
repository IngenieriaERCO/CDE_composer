"""Interfaz de línea de comandos: python -m componedor.cli <subcomando> ..."""

import argparse
import sys
from dataclasses import dataclass, replace
from pathlib import Path

import pymupdf

from componedor.cad_a_papel import (
    leer_geometria_manifiesto,
    limites_dibujo_en_papel,
    origen_para_ancla,
)
from componedor.colocar import DetalleInvalido, abrir_pdf, colocar_detalle, tamano_visible_mm
from componedor.comprobacion_dibujo import (
    UMBRAL_ADVERTENCIA_MM,
    ComparacionLimites,
    comparar_con_manifiesto,
    exigir_coherencia,
)
from componedor.comando_referencia import ejecutar_referencia
from componedor.composicion import hoja_base
from componedor.formato import Formato, RectMM, cargar_formato
from componedor.hoja import ORIENTACIONES, crear_hoja
from componedor.plantilla import TOLERANCIA_MARCO_MM, TOLERANCIA_TAMANO_MM, InformePlantilla
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
    comparacion: ComparacionLimites | None = None  # trazos del PDF vs page_bounds_mm


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

    detalle = abrir_pdf(ruta_detalle, "el detalle", DetalleInvalido)
    try:
        geometria = comparacion = None
        if ruta_manifiesto is not None:
            geometria = leer_geometria_manifiesto(ruta_manifiesto)
            exigir_coherencia(detalle[0], geometria)
            # Se usa el tamaño real de la página (coincide con page_size_mm ±0,5 mm): es la
            # que se coloca en la hoja.
            ancho, alto = tamano_visible_mm(detalle[0])
            geometria = replace(geometria, ancho_pagina_mm=ancho, alto_pagina_mm=alto)
            comparacion = comparar_con_manifiesto(detalle[0], geometria)
        if ancla is not None:
            punto_cad, punto_papel = ancla
            posicion_mm = origen_para_ancla(punto_cad, punto_papel, geometria.matriz,
                                            geometria.alto_pagina_mm)

        doc, informe = hoja_base(formato, guias)
        ocupado = colocar_detalle(doc[0], formato, detalle, posicion_mm, zona=zona)
        _guardar(doc, salida)
    finally:
        detalle.close()

    dibujo = limites_dibujo_en_papel(geometria, ocupado[:2]) if geometria else None
    return ResultadoColocar(ocupado, informe, dibujo, comparacion)


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


def texto_comparacion(comparacion: ComparacionLimites | None) -> str:
    if comparacion is None:
        return "Comprobación matriz vs PDF: el detalle no tiene trazos que medir."
    texto = (
        f"Comprobación matriz vs PDF: límites de los trazos "
        f"{[round(v, 2) for v in comparacion.limites_trazos_mm]} vs page_bounds_mm "
        f"{[round(v, 2) for v in comparacion.limites_manifiesto_mm]} (mm de página): "
        f"diferencia máx. {comparacion.diferencia_max_mm:.3f} mm"
    )
    if comparacion.advertencia:
        texto += (
            f"\nADVERTENCIA: la diferencia supera {UMBRAL_ADVERTENCIA_MM} mm. Revise que el "
            f"manifiesto corresponda al PDF; el detalle se colocó de todos modos."
        )
    return texto


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
            if args.manifiesto:
                print(texto_comparacion(r.comparacion))
        elif args.subcomando == "referencia":
            if (args.detalle is None) != (args.manifiesto is None):
                print("Error: --detalle y --manifiesto van juntos.", file=sys.stderr)
                return 2
            r = ejecutar_referencia(args.formato, args.salida, not args.sin_plantilla,
                                    args.sobrescribir, args.detalle, args.manifiesto)
            print(r.texto, end="")
            print(f"PDF: {r.ruta_pdf}\nInforme: {r.ruta_txt}")
            return 0 if r.pasa else 1
    # FormatoInvalido, DetalleInvalido, PlantillaInvalida y ManifiestoInvalido son ValueError.
    except (FileExistsError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
