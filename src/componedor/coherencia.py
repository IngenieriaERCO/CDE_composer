"""Coherencia del paquete: ¿el manifiesto describe de verdad la geometría del PDF?

Solo se verifica un paquete completo cuya integridad pasa (integridad.py). Comprobaciones,
en este orden (ver docs/contrato_paquete.md):
  a) rotación de la página = 0 (la matriz supone una página sin girar). Si no, se detiene:
     las demás medidas no tendrían sentido;
  b) tamaño visible del PDF = pdf.page_size_mm (±0,1 mm);
  c) pdf.page_size_mm = pdf.expected_page_size_mm (±0,1 mm);
  d) factor_mm_per_cad_unit = millimeters_per_unit / denominator (relativa < 1e-6);
  e) matriz: a = factor, d = -factor (relativa < 1e-6), b = c = 0 (|b|, |c| <= 1e-9·factor);
  f) las esquinas de cad_bounds pasadas por la matriz = page_bounds_mm (±0,01 mm);
  g) page_bounds_mm dentro de la página;
  h) trazos medidos en el PDF (sin el fondo blanco) = page_bounds_mm (±0,5 mm);
  i) regla de uso: scale.physical_scale_guaranteed debe ser true.
"""

import pymupdf

from componedor.colocar import tamano_visible_mm
from componedor.comprobacion_dibujo import medir_limites_trazos
from componedor.integridad import verificar_integridad
from componedor.paquete import COMPLETO, Paquete
from componedor.validacion import Comprobacion, ResultadoVerificacion

SECCION = "Coherencia"
TOL_TAMANO_MM = 0.1
TOL_RELATIVA = 1e-6
TOL_ESQUINAS_MM = 0.01
TOL_TRAZOS_MM = 0.5
_EPS_MM = 1e-6  # holgura numérica para "dentro de la página"

ResultadoCoherencia = ResultadoVerificacion  # mismo resultado que la integridad


def verificar_paquete(paquete: Paquete) -> tuple[ResultadoVerificacion, ResultadoVerificacion]:
    """Integridad y coherencia de un paquete (la integridad se calcula una sola vez)."""
    integridad = verificar_integridad(paquete)
    return integridad, verificar_coherencia(paquete, integridad)


def verificar_coherencia(paquete: Paquete,
                         integridad: ResultadoVerificacion | None = None) -> ResultadoVerificacion:
    """Comprueba la geometría del manifiesto contra el PDF. No lanza errores."""
    if paquete.estado != COMPLETO:
        return ResultadoVerificacion(paquete.prefijo, False,
                                     motivo=f"no verificable (paquete {paquete.estado})")
    integridad = integridad or verificar_integridad(paquete)
    if not integridad.pasa:
        return ResultadoVerificacion(paquete.prefijo, False,
                                     motivo="no verificable (la integridad no pasa)")

    resultado = ResultadoVerificacion(paquete.prefijo, True)
    agregar = resultado.comprobaciones.append
    m = paquete.manifiesto
    pdf, dibujo, matriz = m.pdf, m.pdf.dibujo, m.pdf.dibujo.matriz

    doc = pymupdf.open(paquete.ruta_pdf)
    try:
        pagina = doc[0]
        # a) rotación
        rotacion = pagina.rotation
        agregar(_c("a) Rotación de la página", rotacion == 0, "0", str(rotacion), "exacto",
                   "" if rotacion == 0 else
                   f"incompatible: el PDF tiene /Rotate {rotacion} y la matriz cad_to_page "
                   f"supone una página sin girar"))
        if rotacion != 0:
            return resultado
        visible = tamano_visible_mm(pagina)
        trazos = medir_limites_trazos(pagina)
    finally:
        doc.close()

    # b) tamaño visible del PDF = page_size_mm
    ok = _cerca(visible, pdf.tamano_pagina_mm, TOL_TAMANO_MM)
    agregar(_c("b) Tamaño del PDF vs page_size_mm", ok, _tam(pdf.tamano_pagina_mm), _tam(visible),
               f"±{TOL_TAMANO_MM} mm", "" if ok else
               "la página del PDF no mide lo que dice pdf.page_size_mm"))

    # c) page_size_mm = expected_page_size_mm
    ok = _cerca(pdf.tamano_pagina_mm, pdf.tamano_esperado_mm, TOL_TAMANO_MM)
    agregar(_c("c) page_size_mm vs expected_page_size_mm", ok, _tam(pdf.tamano_esperado_mm),
               _tam(pdf.tamano_pagina_mm), f"±{TOL_TAMANO_MM} mm", "" if ok else
               "el tamaño medido de la página no es el que se calculó con la escala"))

    # d) factor = mm por unidad / denominador
    factor_esperado = m.unidades.milimetros_por_unidad / m.escala.denominador
    factor = m.escala.factor_mm_por_unidad_cad
    ok = _relativa(factor, factor_esperado) < TOL_RELATIVA
    agregar(_c("d) Escala: factor_mm_per_cad_unit", ok,
               f"{factor_esperado:.9g} ({m.unidades.milimetros_por_unidad:g} / "
               f"{m.escala.denominador:g})", f"{factor:.9g}",
               f"relativa < {TOL_RELATIVA:g}", "" if ok else
               "el factor de escala no corresponde a las unidades y al denominador 1:N"))

    # e) matriz = escala pura (sin giro ni inclinación)
    texto_matriz = f"a={matriz.a:.9g}, b={matriz.b:g}, c={matriz.c:g}, d={matriz.d:.9g}"
    cero = 1e-9 * abs(factor)  # b y c por debajo de esto son ruido numérico, no un giro
    if abs(matriz.b) > cero or abs(matriz.c) > cero:
        ok, detalle = False, ("matriz con giro o inclinación: todavía no soportada (es una "
                              "limitación del componedor, no un manifiesto inválido)")
    else:
        ok = (_relativa(matriz.a, factor) < TOL_RELATIVA
              and _relativa(matriz.d, -factor) < TOL_RELATIVA)
        detalle = "" if ok else "la escala de la matriz no es la del manifiesto (a = factor, d = -factor)"
    agregar(_c("e) Matriz cad_to_page", ok,
               f"a={factor:.9g}, b=0, c=0, d={-factor:.9g}", texto_matriz,
               f"relativa < {TOL_RELATIVA:g}", detalle))

    # f) cad_bounds por la matriz = page_bounds_mm (las 4 esquinas, por si hubiera giro)
    xmin, ymin, xmax, ymax = dibujo.limites_cad
    esquinas = [matriz.cad_a_pagina(x, y) for x in (xmin, xmax) for y in (ymin, ymax)]
    calculado = (min(x for x, _ in esquinas), min(y for _, y in esquinas),
                 max(x for x, _ in esquinas), max(y for _, y in esquinas))
    ok = _cerca(calculado, dibujo.limites_pagina_mm, TOL_ESQUINAS_MM)
    agregar(_c("f) cad_bounds por la matriz vs page_bounds_mm", ok,
               _rect(dibujo.limites_pagina_mm), _rect(calculado), f"±{TOL_ESQUINAS_MM} mm",
               "" if ok else "page_bounds_mm no es cad_bounds pasado por la matriz "
                             f"(diferencia máx. {_dif_max(calculado, dibujo.limites_pagina_mm):.3f} mm)"))

    # g) page_bounds_mm dentro de la página
    x0, y0, x1, y1 = dibujo.limites_pagina_mm
    ancho, alto = pdf.tamano_pagina_mm
    ok = (-_EPS_MM <= x0 < x1 <= ancho + _EPS_MM) and (-_EPS_MM <= y0 < y1 <= alto + _EPS_MM)
    agregar(_c("g) page_bounds_mm dentro de la página", ok,
               f"0 <= x0 < x1 <= {ancho:.3f}, 0 <= y0 < y1 <= {alto:.3f}",
               _rect(dibujo.limites_pagina_mm), "exacto",
               "" if ok else "el dibujo declarado se sale de la página del PDF"))

    # h) trazos reales del PDF = page_bounds_mm
    if trazos is None:
        agregar(_c("h) Trazos del PDF vs page_bounds_mm", False, _rect(dibujo.limites_pagina_mm),
                   "sin trazos", f"±{TOL_TRAZOS_MM} mm", "el PDF no tiene trazos que medir"))
    else:
        dif = _dif_max(trazos, dibujo.limites_pagina_mm)
        resultado.datos["diferencia_trazos_mm"] = dif
        ok = dif <= TOL_TRAZOS_MM
        agregar(_c("h) Trazos del PDF vs page_bounds_mm", ok, _rect(dibujo.limites_pagina_mm),
                   f"{_rect(trazos)} (dif. máx. {dif:.3f} mm)", f"±{TOL_TRAZOS_MM} mm",
                   "" if ok else f"los trazos del PDF no están donde dice page_bounds_mm "
                                 f"(diferencia máx. {dif:.3f} mm)"))

    # i) regla de uso de la escala física
    garantizada = m.escala.fisica_garantizada
    if garantizada:
        detalle = ""
    else:
        detalle = "escala física no garantizada: el paquete no se usa para componer a escala"
        if m.escala.motivo_no_garantizada:
            detalle += f" (motivo del exportador: {m.escala.motivo_no_garantizada})"
    agregar(_c("i) Escala física garantizada", garantizada, "true", str(garantizada).lower(),
               "exacto", detalle))
    return resultado


def _c(nombre, pasa, esperado, medido, tolerancia, detalle="") -> Comprobacion:
    return Comprobacion(SECCION, nombre, pasa, esperado, medido, tolerancia, detalle)


def _cerca(a, b, tol) -> bool:
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def _dif_max(a, b) -> float:
    return max(abs(x - y) for x, y in zip(a, b))


def _relativa(valor: float, referencia: float) -> float:
    return abs(valor - referencia) / abs(referencia) if referencia else abs(valor)


def _tam(t) -> str:
    return f"{t[0]:.3f} x {t[1]:.3f} mm"


def _rect(r) -> str:
    return "x0 {:.3f}, y0 {:.3f}, x1 {:.3f}, y1 {:.3f}".format(*r)
