"""Importador: la ÚNICA puerta de entrada de un paquete del exportador al componedor.

Flujo: localizar (paquete.py) -> integridad (integridad.py) -> coherencia (coherencia.py).
Un paquete se acepta solo si está completo, íntegro y coherente (incluida la escala física
garantizada). Si no, `PaqueteRechazado` lista TODOS los motivos, cada uno con su categoría:

  [manifiesto]  la estructura del manifiesto no es válida;
  [archivos]    falta el PDF, el nombre no coincide, PDF sin manifiesto, manifiesto ausente…;
  [integridad]  bytes, SHA-256, que abra, una página;
  [coherencia]  geometría del manifiesto contra el PDF (comprobaciones a-h);
  [escala]      escala física no garantizada (comprobación i).
"""

from dataclasses import dataclass, field
from pathlib import Path

from componedor.coherencia import verificar_coherencia
from componedor.integridad import verificar_integridad
from componedor.paquete import (
    COMPLETO,
    SUFIJO_MANIFIESTO,
    CarpetaInvalida,
    Paquete,
    paquete_de_manifiesto,
)
from componedor.validacion import Comprobacion, ResultadoVerificacion

CATEGORIAS = ("manifiesto", "archivos", "integridad", "coherencia", "escala")
_ESCALA = "i)"  # prefijo de la comprobación de coherencia de la escala física

Motivo = tuple[str, str]  # (categoría, texto)


class PaqueteRechazado(ValueError):
    """El paquete no se acepta; `motivos` trae todos los problemas con su categoría."""

    def __init__(self, prefijo: str, motivos: list[Motivo]):
        self.prefijo = prefijo
        self.motivos = list(motivos)
        n = len(self.motivos)
        super().__init__(
            f"Paquete '{prefijo}' rechazado ({n} {'motivo' if n == 1 else 'motivos'}):\n"
            + "\n".join(f"  - {texto_motivo(m)}" for m in self.motivos)
        )


@dataclass
class PaqueteAceptado:
    paquete: Paquete
    integridad: ResultadoVerificacion
    coherencia: ResultadoVerificacion

    @property
    def manifiesto(self):
        return self.paquete.manifiesto


@dataclass
class Evaluacion:
    """Lo que se sabe de un paquete sin lanzar errores (lo usa también el inventario)."""

    paquete: Paquete
    motivos: list[Motivo] = field(default_factory=list)
    integridad: ResultadoVerificacion | None = None
    coherencia: ResultadoVerificacion | None = None

    @property
    def aceptado(self) -> bool:
        return not self.motivos


def texto_motivo(motivo: Motivo) -> str:
    categoria, texto = motivo
    return f"[{categoria}] {texto}"


def evaluar_paquete(paquete: Paquete) -> Evaluacion:
    """Motivos de rechazo de un paquete ya localizado (lista vacía si se acepta)."""
    evaluacion = Evaluacion(paquete)
    motivos = evaluacion.motivos
    motivos += [("manifiesto", p) for p in paquete.problemas_manifiesto]
    motivos += [("archivos", p) for p in paquete.problemas_archivos]
    if paquete.estado != COMPLETO:
        return evaluacion

    evaluacion.integridad = verificar_integridad(paquete)
    motivos += [("integridad", _texto(c)) for c in evaluacion.integridad.fallas]
    evaluacion.coherencia = verificar_coherencia(paquete, evaluacion.integridad)
    for c in evaluacion.coherencia.fallas:
        motivos.append(("escala" if c.nombre.startswith(_ESCALA) else "coherencia", _texto(c)))
    return evaluacion


def importar_paquete(ruta_manifiesto: Path | str,
                     pdf_esperado: Path | str | None = None) -> PaqueteAceptado:
    """Localiza el paquete de `ruta_manifiesto` y lo acepta solo si está completo, íntegro
    y coherente. `pdf_esperado` (opcional): el PDF que se quiere usar debe ser el del
    paquete. Lanza `PaqueteRechazado` con todos los motivos."""
    ruta = Path(ruta_manifiesto)
    try:
        paquete = paquete_de_manifiesto(ruta)
    except CarpetaInvalida as e:
        raise PaqueteRechazado(_prefijo(ruta), [("archivos", str(e))]) from e

    evaluacion = evaluar_paquete(paquete)
    if (pdf_esperado is not None and paquete.ruta_pdf is not None
            and Path(pdf_esperado).resolve() != paquete.ruta_pdf.resolve()):
        evaluacion.motivos.insert(0, ("archivos",
            f"el PDF indicado '{pdf_esperado}' no es el del paquete: el manifiesto indica "
            f"'{paquete.ruta_pdf.name}' ({paquete.ruta_pdf})"))
    if not evaluacion.aceptado:
        raise PaqueteRechazado(paquete.prefijo, evaluacion.motivos)
    return PaqueteAceptado(paquete, evaluacion.integridad, evaluacion.coherencia)


def _texto(c: Comprobacion) -> str:
    return c.detalle or f"{c.nombre}: esperado {c.esperado}, medido {c.medido}"


def _prefijo(ruta: Path) -> str:
    nombre = ruta.name
    return nombre[: -len(SUFIJO_MANIFIESTO)] if nombre.lower().endswith(SUFIJO_MANIFIESTO) else nombre
