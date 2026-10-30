"""Comando `referencia`: compone el detalle de referencia, mide el PDF y escribe el informe."""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pymupdf

from componedor.cad_a_papel import origen_para_ancla
from componedor.colocar import colocar_detalle
from componedor.composicion import hoja_base
from componedor.formato import PlantillaNoEncontrada, cargar_formato
from componedor.informe import escribir_informe, texto_informe
from componedor.referencia import CUADRADO_CAD, generar_detalle_referencia
from componedor.validacion import Comprobacion, validar_detalle_real, validar_hoja_referencia

# La esquina inferior izquierda del cuadrado de referencia cae aquí (dentro del área de dibujo).
ANCLA_PAPEL_MM = (100.0, 100.0)


@dataclass
class ResultadoReferencia:
    ruta_pdf: Path
    ruta_txt: Path
    texto: str
    comprobaciones: list[Comprobacion]
    avisos: list[str] = field(default_factory=list)

    @property
    def pasa(self) -> bool:
        return all(c.pasa for c in self.comprobaciones)


def ejecutar_referencia(ruta_formato: Path, salida: Path, usar_plantilla: bool = True,
                        sobrescribir: bool = False, ruta_detalle: Path | None = None,
                        ruta_manifiesto: Path | None = None) -> ResultadoReferencia:
    """Crea `salida` (PDF) y un TXT con el mismo nombre; devuelve las comprobaciones."""
    ruta_txt = salida.with_suffix(".txt")
    for ruta in (salida, ruta_txt):
        if ruta.exists() and not sobrescribir:
            raise FileExistsError(
                f"El archivo '{ruta}' ya existe. Use --sobrescribir para reemplazarlo."
            )

    avisos = []
    try:
        formato = cargar_formato(ruta_formato, usar_plantilla)
    except PlantillaNoEncontrada as e:
        avisos.append(f"AVISO: {e} Se sigue sin plantilla.")
        formato = cargar_formato(ruta_formato, usar_plantilla=False)

    imagenes_plantilla = 0
    if formato.plantilla is not None:
        with pymupdf.open(formato.plantilla) as plantilla:
            imagenes_plantilla = len(plantilla[0].get_image_info())

    # Composición: plantilla (o marco) y encima el detalle anclado.
    detalle = generar_detalle_referencia()
    doc, informe_plantilla = hoja_base(formato, exigir_marco=False)
    origen = origen_para_ancla(CUADRADO_CAD[:2], ANCLA_PAPEL_MM, detalle.matriz,
                               detalle.alto_pagina_mm)
    colocar_detalle(doc[0], formato, detalle.doc, origen)
    salida.parent.mkdir(parents=True, exist_ok=True)
    doc.save(salida)
    doc.close()

    # Medición sobre el PDF guardado (lo que queda en disco).
    with pymupdf.open(salida) as final:
        comprobaciones = validar_hoja_referencia(final, formato, detalle, ANCLA_PAPEL_MM,
                                                 informe_plantilla, imagenes_plantilla)
    detalle.doc.close()
    if ruta_detalle is not None:
        comprobaciones += validar_detalle_real(formato, ruta_detalle, ruta_manifiesto)

    encabezado = [
        f"Generado: {datetime.now():%Y-%m-%d %H:%M}",
        f"Formato: {ruta_formato} ({formato.nombre})",
        f"PDF: {salida}",
        f"Detalle de referencia: sintético 1:50, esquina inferior izquierda del cuadrado en "
        f"({ANCLA_PAPEL_MM[0]:.1f}, {ANCLA_PAPEL_MM[1]:.1f}) mm de papel (ancla CAD)",
        *avisos,
    ]
    notas = {"Plantilla": [f"plantilla: {formato.plantilla}" if formato.plantilla
                           else "no se usa plantilla: se dibujó el marco del formato"]}
    if ruta_detalle is not None:
        notas["Detalle real"] = [f"{ruta_detalle} con {ruta_manifiesto}, centrado en una hoja "
                                 f"limpia (sin plantilla ni marco)"]
    texto = texto_informe(comprobaciones, encabezado, notas)
    escribir_informe(ruta_txt, texto)
    return ResultadoReferencia(salida, ruta_txt, texto, comprobaciones, avisos)
