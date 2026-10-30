"""Informe de validación en texto (español, UTF-8)."""

from pathlib import Path

from componedor.validacion import Comprobacion

SECCIONES = ("Hoja", "Marco", "Plantilla", "Detalle de referencia", "Escala", "Vector",
             "Detalle real")


def resultado_final(comprobaciones: list[Comprobacion]) -> str:
    fallas = sum(1 for c in comprobaciones if not c.pasa)
    if fallas == 0:
        return "RESULTADO: PASA"
    return f"RESULTADO: FALLA ({fallas} {'comprobación' if fallas == 1 else 'comprobaciones'})"


def texto_informe(comprobaciones: list[Comprobacion], encabezado: list[str],
                  notas: dict[str, list[str]] | None = None) -> str:
    """Texto del informe: encabezado, una sección por tema y el resultado al final.

    `notas` agrega líneas informativas a una sección (p. ej. "no se usa plantilla").
    """
    notas = notas or {}
    lineas = ["INFORME DE VALIDACIÓN — GEOMETRÍA DE REFERENCIA", "=" * 60, *encabezado, ""]
    for seccion in SECCIONES:
        filas = [c for c in comprobaciones if c.seccion == seccion]
        if not filas and seccion not in notas:
            continue
        lineas.append(f"== {seccion.upper()} ==")
        lineas += [f"  ({nota})" for nota in notas.get(seccion, [])]
        for c in filas:
            lineas.append(f"  [{'PASA' if c.pasa else 'FALLA'}] {c.nombre}")
            lineas.append(f"      esperado:   {c.esperado}")
            lineas.append(f"      medido:     {c.medido}")
            lineas.append(f"      tolerancia: {c.tolerancia}")
        lineas.append("")
    lineas.append(resultado_final(comprobaciones))
    return "\n".join(lineas) + "\n"


def escribir_informe(ruta: Path, texto: str) -> None:
    """UTF-8 con saltos de línea LF en cualquier sistema (archivo reproducible)."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(texto, encoding="utf-8", newline="\n")
