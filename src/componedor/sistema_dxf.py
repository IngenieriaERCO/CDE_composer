"""El sistema de coordenadas que declara el DXF (`dxf.crs` de `load`, sacado del GEODATA).

El Exportador lo copia SIN interpretar (protocolo del trabajador, `dxf.crs`): `epsg` puede no
coincidir con el nombre. Ejemplo real: PRGD dice «MAGNA_Colombia CTM12» (que es EPSG:9377,
Origen-Nacional), pero su autoridad trae 3115 (Colombia West zone). Aquí se decide qué hacer:

- el código (`epsg`) se usa para prellenar «Sistema del dibujo» del editor, siempre editable,
  SOLO si salió de un `Alias` del GEODATA (`epsg_from: "alias"`). Si salió del texto de la
  autoridad (`epsg_from: "authority"`, como en PRGD), el selector queda sin preseleccionar
  (`prellenar: false`): el aviso y la sugerencia se muestran igual;
- se compara la ZONA que dice el nombre del DXF con la del nombre oficial de ese código (GDAL).
  Si no coinciden, `aviso` lo dice (amarillo en el editor) y, si se reconoce la zona del
  nombre, `sugerido` da el código que le corresponde. No se cambia nada solo: el usuario elige.

También acepta formas simples (texto "EPSG:9377", entero, {"code": …}) por si cambia el formato.
"""

import re
import unicodedata

from componedor.ortofoto import SistemaInvalido, leer_sistema, texto_sistema

# Zona → cómo puede aparecer en un nombre (normalizado: minúsculas, sin tildes ni signos) y el
# código de esa zona en MAGNA-SIRGAS. En orden: lo más específico primero.
ZONAS = (
    ("Origen-Nacional", ("ctm12", "ctm 12", "origen nacional"), "EPSG:9377"),
    ("Far West", ("far west", "extremo oeste"), "EPSG:3114"),
    ("East Central", ("east central", "este central"), "EPSG:3117"),
    ("West", ("west", "oeste"), "EPSG:3115"),
    ("East", ("east", "este"), "EPSG:3118"),
    ("Bogotá", ("bogota",), "EPSG:3116"),
)


def normalizar(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return " " + re.sub(r"[^a-z0-9]+", " ", sin_tildes.lower()).strip() + " "


def zona(texto: str | None) -> tuple[str, str] | None:
    """(zona, código sugerido) que menciona un nombre de sistema, o None."""
    if not texto:
        return None
    t = normalizar(texto)
    for nombre, formas, codigo in ZONAS:
        if any(f" {f} " in t for f in formas):
            return nombre, codigo
    return None


def _codigo(valor) -> str | None:
    if isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        valor = str(valor)
    if not isinstance(valor, str):
        return None
    m = re.match(r"^\s*(?:EPSG\s*:\s*)?(\d{4,6})\s*$", valor, re.IGNORECASE)
    return f"EPSG:{m.group(1)}" if m else None


def sistema_del_dxf(valor) -> dict | None:
    """`dxf.crs` de load → {codigo, nombre, oficial, aviso, sugerido, prellenar}, o None si no
    hay código (falta, null o no se entiende): entonces el selector queda vacío."""
    textos = []
    de_autoridad = isinstance(valor, dict) and valor.get("epsg_from") == "authority"
    if isinstance(valor, dict):
        textos = [valor.get(k) for k in ("name", "description", "id")
                  if isinstance(valor.get(k), str) and valor.get(k).strip()]
        valor = valor.get("epsg", valor.get("code"))
    codigo = _codigo(valor)
    if codigo is None:
        return None
    nombre = textos[0] if textos else None
    try:
        oficial = texto_sistema(leer_sistema(codigo))["nombre"]
    except SistemaInvalido as e:
        return {"codigo": codigo, "nombre": nombre, "oficial": None, "sugerido": None,
                "prellenar": False,
                "aviso": f"El DXF dice {codigo}, pero no sirve como sistema del dibujo: {e}"}
    aviso = sugerido = None
    del_dxf = next((z for z in (zona(t) for t in textos) if z), None)
    de_codigo = zona(oficial)
    if del_dxf and de_codigo and del_dxf[0] != de_codigo[0]:
        sugerido = del_dxf[1]
        aviso = (f"El DXF dice «{nombre}», pero su código es {codigo} ({oficial}): no coinciden. "
                 f"«{nombre}» corresponde a {sugerido} ({del_dxf[0]}). Revise el sistema del "
                 f"dibujo.")
    return {"codigo": codigo, "nombre": nombre, "oficial": oficial, "aviso": aviso,
            "sugerido": sugerido, "prellenar": not de_autoridad}
