"""Los planos de la carpeta del editor, para «Nueva hoja a partir de esta» y el selector de
hojas (plano versión 7, hojas_proyecto.py). Solo con el servidor local: el navegador no puede
escribir varios archivos por su cuenta.

Solo se tocan archivos `.json` de la MISMA carpeta del editor, nombrados sin carpetas: nunca
otra ruta. Un plano se escribe en UTF-8 con saltos LF; uno nuevo no pisa uno que ya existe.
"""

import json
from pathlib import Path

from componedor.aplicacion_editor import ErrorAplicacion
from componedor.hojas_proyecto import AUTOMATICOS as TIPOS_AUTOMATICOS
from componedor.hojas_proyecto import (
    SUFIJO,
    IndiceInvalido,
    escribir_indice,
    indice_de,
    leer_indice,
    nombre_valido,
    valores_automaticos,
)

TAMANO_MAXIMO = 20 * 1024 * 1024  # un plano.json grande (rótulo, notas) cabe holgado


class PlanosEditor:
    def __init__(self, carpeta: Path):
        self.carpeta = Path(carpeta)

    def _ruta(self, archivo) -> Path:
        if not nombre_valido(archivo):
            raise ErrorAplicacion(400, f"«{archivo}» no es un nombre de plano.json válido (sin "
                                       f"carpetas, terminado en .json).")
        return self.carpeta / archivo

    def listar(self) -> dict:
        """Los plano.json de la carpeta del editor y los índices de hojas con sus hojas."""
        planos = sorted(p.name for p in self.carpeta.glob("*.json")
                        if not p.name.lower().endswith(SUFIJO) and nombre_valido(p.name))
        indices = {}
        for ruta in sorted(self.carpeta.glob(f"*{SUFIJO}")):
            try:
                indices[ruta.name[:-len(SUFIJO)]] = leer_indice(ruta)
            except IndiceInvalido:
                continue
        return {"planos": planos, "indices": indices}

    def leer(self, archivo) -> dict:
        ruta = self._ruta(archivo)
        if not ruta.is_file():
            raise ErrorAplicacion(404, f"No está «{archivo}» en la carpeta del editor.")
        return {"archivo": ruta.name, "texto": ruta.read_text(encoding="utf-8")}

    def guardar(self, archivo, texto, nuevo: bool = False) -> dict:
        """Escribe el plano. `nuevo`: falla si ya existe (una hoja nueva nunca pisa otra)."""
        ruta = self._ruta(archivo)
        if not isinstance(texto, str) or len(texto) > TAMANO_MAXIMO:
            raise ErrorAplicacion(400, "Falta el texto del plano.")
        try:
            datos = json.loads(texto)
        except json.JSONDecodeError as e:
            raise ErrorAplicacion(400, f"El plano no es un JSON válido: {e}.") from None
        if not (isinstance(datos, dict) and isinstance(datos.get("version"), int)):
            raise ErrorAplicacion(400, "El plano debe ser un objeto con «version».")
        if nuevo and ruta.exists():
            raise ErrorAplicacion(409, f"Ya existe «{archivo}» en la carpeta del editor: no se pisa.")
        ruta.write_text(texto, encoding="utf-8", newline="\n")
        return {"archivo": ruta.name, "guardado": True}

    def hojas(self, archivo, rotulo=None, campos=None) -> dict:
        """Del plano `archivo`: su índice (o None), sus hojas, su posición y los valores
        automáticos del rótulo que no escribe. `rotulo`: el del editor, sin guardar; `campos`:
        {campo: "hoja_actual" | "total_hojas" | "numero_siguiente"} de la definición."""
        ruta = self._ruta(archivo)
        encontrado = indice_de(ruta)
        if encontrado is None:
            return {"archivo": ruta.name, "indice": None, "hojas": [], "posicion": None,
                    "automaticos": {}}
        indice, hojas = encontrado
        campos = {c: t for c, t in (campos or {}).items()
                  if isinstance(c, str) and t in TIPOS_AUTOMATICOS}
        posicion = [h.casefold() for h in hojas].index(ruta.name.casefold())
        return {"archivo": ruta.name, "indice": indice.name[:-len(SUFIJO)], "hojas": hojas,
                "posicion": posicion,
                "existen": [(self.carpeta / h).is_file() for h in hojas],
                "automaticos": valores_automaticos(ruta, campos,
                                                   rotulo if isinstance(rotulo, dict) else None)}

    def guardar_indice(self, nombre, hojas) -> dict:
        if not (isinstance(hojas, list) and hojas):
            raise ErrorAplicacion(400, "«hojas» debe ser la lista de plano.json del proyecto.")
        for h in hojas:
            if not self._ruta(h).is_file():
                raise ErrorAplicacion(404, f"La hoja «{h}» no está en la carpeta del editor.")
        try:
            ruta = escribir_indice(self.carpeta, nombre, hojas)
        except IndiceInvalido as e:
            raise ErrorAplicacion(400, str(e)) from None
        return {"indice": ruta.name[:-len(SUFIJO)], "hojas": hojas}
