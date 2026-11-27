"""plano.json versión 8: un proyecto de varias hojas en UN archivo (como varios layouts de un
DWG). Lo que es del proyecto va una vez; lo de cada hoja, en su entrada de "hojas":

    {"version": 8, "formato": "../formatos/A1_ERCO.json", "plantilla": null,
     "dxf": [{"id": "d1", "archivo": "...", "sha256": "…", "margen_mm": 5, "unidades": "m"}],
     "ortofoto": {...},
     "hojas": [
       {"nombre": "Hoja 1", "detalles": [...], "zonas": [{"dxf": "d1", "nombre": "Zona_01", ...}],
        "rosa_vientos": {...}, "rotulo": {...}},
       {"nombre": "Hoja 2", "detalles": [], "rotulo": {...},
        "copiado_de": {"hoja": "Hoja 1", "revisar": ["notas"]}}]}

- "dxf" y "ortofoto" se comparten: una hoja los usa si sus detalles o zonas los nombran.
- Cada hoja es lo mismo que un plano versión 7 (detalles, que pueden ir vacíos; rosa; rótulo;
  "copiado_de"), y sus zonas del Model Space van en su lista "zonas", cada una con "dxf" (el id
  del DXF) y los campos de siempre (plano_zonas.py). Los nombres de zona son únicos en todo el
  proyecto (cada zona da un paquete).
- «Hoja», «de» y el número de plano salen solos de la posición de la hoja en la lista
  (hojas_proyecto.automaticos_de_lista), si la hoja no los escribe.

Cada hoja se valida con las reglas de siempre (plano.plano_desde_datos) y da un `Plano` con su
nombre y su posición. Los problemas de una hoja no impiden leer las otras: `leer_proyecto`
devuelve, por hoja, el plano o sus problemas; los del archivo entero lanzan `ProyectoInvalido`.
"""

import copy
import json
from dataclasses import dataclass, field, replace
from pathlib import Path

from componedor.plano import Plano, PlanoInvalido, plano_desde_datos

VERSION = 8
CLAVES_PROYECTO = {"version", "formato", "plantilla", "dxf", "ortofoto", "hojas"}
CLAVES_HOJA = {"nombre", "detalles", "zonas", "rosa_vientos", "rotulo", "copiado_de"}


class ProyectoInvalido(PlanoInvalido):
    """El archivo del proyecto no se puede leer (el mensaje lista los problemas)."""


@dataclass
class HojaLeida:
    numero: int  # 1, 2, …
    nombre: str
    plano: Plano | None  # None si la hoja tiene problemas
    problemas: list[str] = field(default_factory=list)


@dataclass
class Proyecto:
    ruta: Path
    hojas: list[HojaLeida]

    @property
    def problemas(self) -> list[str]:
        total = len(self.hojas)
        return [f"Hoja {h.numero} de {total} («{h.nombre}»): {p}" for h in self.hojas
                for p in h.problemas]


def es_proyecto(ruta: Path | str) -> bool:
    """¿Es un plano.json versión 8? (sin validar el resto; un archivo que no se lee, no)."""
    try:
        datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    return isinstance(datos, dict) and datos.get("version") == VERSION


def leer_proyecto(ruta: Path | str) -> Proyecto:
    """Lee el proyecto. Lanza `ProyectoInvalido` si el archivo entero no vale; los problemas de
    cada hoja quedan en su `HojaLeida`."""
    ruta = Path(ruta)
    if not ruta.is_file():
        raise ProyectoInvalido(f"No se encontró el proyecto '{ruta}'.")
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ProyectoInvalido(f"El proyecto '{ruta}' no es un JSON válido: {e}.") from None
    errores = []
    if not isinstance(datos, dict) or datos.get("version") != VERSION:
        raise ProyectoInvalido(f"'{ruta.name}' no es un proyecto de varias hojas (versión 8).")
    for clave in sorted(set(datos) - CLAVES_PROYECTO):
        errores.append(f"{clave}: campo no reconocido en un proyecto (campos válidos: "
                       f"{', '.join(sorted(CLAVES_PROYECTO))}); lo de cada hoja va en «hojas»")
    hojas = datos.get("hojas")
    if not isinstance(hojas, list) or not hojas:
        errores.append("hojas: se esperaba la lista de hojas del proyecto (al menos una)")
        hojas = []
    nombres: list[str] = []
    for i, h in enumerate(hojas):
        nombre = h.get("nombre") if isinstance(h, dict) else None
        if not isinstance(h, dict):
            errores.append(f"hojas[{i}]: se esperaba un objeto {{\"nombre\", \"detalles\", ...}}")
        elif not (isinstance(nombre, str) and nombre.strip()):
            errores.append(f"hojas[{i}].nombre: se esperaba un texto no vacío")
        elif nombre.strip().casefold() in (n.casefold() for n in nombres):
            errores.append(f"hojas[{i}].nombre: '{nombre}' está repetido (cada hoja, un nombre)")
        else:
            nombres.append(nombre.strip())
    if errores:
        raise ProyectoInvalido(f"El proyecto '{ruta}' no es válido ({len(errores)} problema(s)):\n"
                               + "\n".join(f"- {e}" for e in errores))

    dxf = datos.get("dxf")
    ids = {d.get("id") for d in dxf if isinstance(d, dict)} if isinstance(dxf, list) else set()
    zonas_vistas: dict[str, int] = {}
    leidas: list[HojaLeida] = []
    rotulos = [h.get("rotulo") if isinstance(h.get("rotulo"), dict) else {} for h in hojas]
    for i, h in enumerate(hojas):
        problemas = [f"{clave}: campo no reconocido en una hoja (campos válidos: "
                     f"{', '.join(sorted(CLAVES_HOJA))})" for clave in sorted(set(h) - CLAVES_HOJA)]
        zonas = h.get("zonas", [])
        if not isinstance(zonas, list):
            problemas.append("zonas: se esperaba una lista de zonas del Model Space")
            zonas = []
        for j, z in enumerate(zonas):
            if not isinstance(z, dict) or z.get("dxf") not in ids:
                problemas.append(f"zonas[{j}].dxf: se esperaba el id de un DXF de la lista «dxf» "
                                 f"del proyecto")
                continue
            nombre_zona = z.get("nombre")
            if isinstance(nombre_zona, str) and nombre_zona in zonas_vistas:
                problemas.append(f"zonas[{j}].nombre: '{nombre_zona}' ya es una zona de la hoja "
                                 f"{zonas_vistas[nombre_zona]} (cada zona da un paquete: use otro "
                                 f"nombre)")
            elif isinstance(nombre_zona, str):
                zonas_vistas[nombre_zona] = i + 1
        if not problemas:
            try:
                plano = plano_desde_datos(_datos_de_hoja(datos, h, zonas), ruta)
            except PlanoInvalido as e:
                problemas += _lineas(str(e))
            else:
                leidas.append(HojaLeida(i + 1, nombres[i], replace(
                    plano, hoja=nombres[i], posicion=i, rotulos_proyecto=tuple(rotulos))))
                continue
        leidas.append(HojaLeida(i + 1, nombres[i], None, problemas))
    return Proyecto(ruta, leidas)


def _datos_de_hoja(datos: dict, hoja: dict, zonas: list) -> dict:
    """La hoja como un plano versión 7: lo del proyecto (formato, plantilla, dxf con las zonas
    de esta hoja, ortofoto) más lo suyo."""
    plano = {"version": 7, "formato": datos.get("formato")}
    if "plantilla" in datos:
        plano["plantilla"] = datos["plantilla"]
    if isinstance(datos.get("dxf"), list):
        lista = []
        for d in copy.deepcopy(datos["dxf"]):
            if isinstance(d, dict):
                propias = [{k: v for k, v in z.items() if k != "dxf"} for z in zonas
                           if z.get("dxf") == d.get("id")]
                d.pop("zonas", None)
                if propias:
                    d["zonas"] = propias
            lista.append(d)
        plano["dxf"] = lista
    if "ortofoto" in datos:
        plano["ortofoto"] = copy.deepcopy(datos["ortofoto"])
    plano["detalles"] = copy.deepcopy(hoja.get("detalles", []))
    for clave in ("rosa_vientos", "rotulo", "copiado_de"):
        if clave in hoja:
            plano[clave] = copy.deepcopy(hoja[clave])
    return plano


def _lineas(mensaje: str) -> list[str]:
    """Los problemas de un `PlanoInvalido` («- …» por línea), sin el encabezado."""
    lineas = [ln[2:] for ln in mensaje.splitlines() if ln.startswith("- ")]
    return lineas or [mensaje]
