"""Componer todo un proyecto de una vez → UN PDF con todas las hojas, una por página, en orden:
el índice <proyecto>.hojas.json (hojas_proyecto.py) o un proyecto de varias hojas en un solo
archivo (plano versión 8, plano_proyecto.py). Las dos formas usan el mismo motor:

1. Cada hoja se compone como siempre (`componer_plano`: su verificación, sus campos automáticos
   hoja / de / número de plano, su ortofoto) en un PDF temporal.
2. Si alguna hoja no se puede componer, NO sale el PDF del proyecto: antes se intentan todas, y
   el error junta todos los problemas, cada uno con su hoja.
3. Las páginas se unen con `insert_pdf` (copia cada página tal cual: lo vectorial sigue siendo
   vector; la ortofoto, las mismas imágenes).
4. Se verifica el PDF unido: tantas páginas como hojas, en el orden del índice, y cada página
   igual a la de su hoja (tamaño, trazos, textos e imágenes). Recién entonces se guarda en
   `salida`. Los PDF de cada hoja se borran.
"""

import os
import tempfile
from dataclasses import dataclass, field, replace
from pathlib import Path

import pymupdf

from componedor.componer import PlanoNoComponible, ResultadoComposicion, componer_plano
from componedor.configuracion import ConfigOrtofoto
from componedor.hojas_proyecto import SUFIJO, IndiceInvalido, leer_indice
from componedor.plano import PlanoInvalido, leer_plano
from componedor.plano_proyecto import ProyectoInvalido, leer_proyecto
from componedor.recorte_detalle import MARGEN_POR_DEFECTO_MM

TOL_PT = 0.01  # las páginas se copian tal cual: la tolerancia es solo de redondeo


class ProyectoNoComponible(ValueError):
    """El proyecto no se compone (el mensaje lista cada hoja con su problema)."""


@dataclass
class HojaCompuesta:
    numero: int  # 1, 2, …
    archivo: str
    resultado: ResultadoComposicion


@dataclass
class ResultadoProyecto:
    ruta_pdf: Path
    indice: Path
    hojas: list[HojaCompuesta] = field(default_factory=list)

    @property
    def advertencias(self) -> list[str]:
        """Las de cada hoja, con su hoja delante."""
        total = len(self.hojas)
        return [f"Hoja {h.numero} de {total} ({h.archivo}) · {a}"
                for h in self.hojas for a in h.resultado.advertencias]


def es_indice(ruta: Path | str) -> bool:
    return Path(ruta).name.lower().endswith(SUFIJO)


def nombre_proyecto(indice: Path | str) -> str:
    """«Pruebadecambio.hojas.json» → «Pruebadecambio»."""
    nombre = Path(indice).name
    return nombre[:-len(SUFIJO)]


def componer_proyecto(indice: Path | str, salida: Path | str, sobrescribir: bool = False,
                      config_ortofoto: ConfigOrtofoto | None = None,
                      carpeta_simbolos: Path | None = None,
                      margen_mm: float | None = MARGEN_POR_DEFECTO_MM,
                      formato: Path | None = None) -> ResultadoProyecto:
    """Compone todas las hojas del índice en `salida`. `formato`: el de componedor.json (con
    --config), que reemplaza el de cada hoja. Lanza `ProyectoNoComponible` (o FileExistsError)."""
    indice, salida = Path(indice), Path(salida)
    if salida.exists() and not sobrescribir:
        raise FileExistsError(f"El archivo '{salida}' ya existe. Use --sobrescribir para "
                              f"reemplazarlo.")
    try:
        hojas = leer_indice(indice)
    except IndiceInvalido as e:
        raise ProyectoNoComponible(f"No se compone el proyecto: {e}") from None

    def cargar(archivo):
        def leer():
            ruta = indice.parent / archivo
            if not ruta.is_file():
                raise PlanoInvalido(f"no está el archivo '{ruta}'.")
            return leer_plano(ruta)
        return leer

    entradas = [(archivo, cargar(archivo)) for archivo in hojas]
    return _componer_hojas(indice, nombre_proyecto(indice), entradas, salida, config_ortofoto,
                           carpeta_simbolos, margen_mm, formato)


def componer_archivo_proyecto(ruta: Path | str, salida: Path | str, sobrescribir: bool = False,
                              config_ortofoto: ConfigOrtofoto | None = None,
                              carpeta_simbolos: Path | None = None,
                              margen_mm: float | None = MARGEN_POR_DEFECTO_MM,
                              formato: Path | None = None) -> ResultadoProyecto:
    """Lo mismo para un proyecto de varias hojas en UN archivo (plano versión 8,
    plano_proyecto.py). Los problemas de cada hoja (al leerla o al componerla) se juntan."""
    ruta, salida = Path(ruta), Path(salida)
    if salida.exists() and not sobrescribir:
        raise FileExistsError(f"El archivo '{salida}' ya existe. Use --sobrescribir para "
                              f"reemplazarlo.")
    try:
        proyecto = leer_proyecto(ruta)
    except ProyectoInvalido as e:
        raise ProyectoNoComponible(f"No se compone el proyecto: {e}") from None

    def cargar(h):
        def leer():
            if h.plano is None:
                raise PlanoInvalido(h.problemas[0] if len(h.problemas) == 1
                                    else "\n".join(f"- {p}" for p in h.problemas))
            return h.plano
        return leer

    entradas = [(f"«{h.nombre}»", cargar(h)) for h in proyecto.hojas]
    return _componer_hojas(ruta, ruta.stem, entradas, salida, config_ortofoto, carpeta_simbolos,
                           margen_mm, formato)


def _componer_hojas(origen: Path, nombre: str, entradas: list, salida: Path,
                    config_ortofoto, carpeta_simbolos, margen_mm, formato) -> ResultadoProyecto:
    """Compone cada hoja (`entradas`: [(etiqueta, función que da su Plano)]) en temporal, junta
    los problemas de todas, une las páginas y verifica el PDF unido."""
    total = len(entradas)
    problemas: list[str] = []
    compuestas: list[HojaCompuesta] = []
    with tempfile.TemporaryDirectory(prefix="componedor_proyecto_") as temporal:
        for i, (etiqueta, leer) in enumerate(entradas, start=1):
            donde = f"Hoja {i} de {total} ({etiqueta})"
            try:
                plano = leer()
                if formato is not None:
                    plano = replace(plano, formato=formato)
                resultado = componer_plano(plano, Path(temporal) / f"hoja_{i:03d}.pdf", True,
                                           config_ortofoto=config_ortofoto,
                                           carpeta_simbolos=carpeta_simbolos, margen_mm=margen_mm)
            except (PlanoInvalido, PlanoNoComponible, OSError, ValueError) as e:
                texto = str(e)
                problemas.append(f"{donde}: {texto}" if "\n" not in texto
                                 else f"{donde}:\n" + _sangrar(texto))
                continue
            compuestas.append(HojaCompuesta(i, etiqueta, resultado))
        if problemas:
            raise ProyectoNoComponible(
                f"No se compone el proyecto «{nombre}»: {len(problemas)} de {total} hoja(s) con "
                f"problemas (no se generó el PDF):\n" + "\n".join(f"- {p}" for p in problemas))
        salida.parent.mkdir(parents=True, exist_ok=True)
        temporal_salida = salida.with_name(f".{salida.name}.componiendo.pdf")
        try:
            with pymupdf.open() as unido:
                for h in compuestas:
                    with pymupdf.open(h.resultado.ruta_pdf) as hoja:
                        unido.insert_pdf(hoja)
                unido.save(temporal_salida, garbage=3, deflate=True)
            fallas = verificar_proyecto(temporal_salida, [h.resultado.ruta_pdf for h in compuestas])
            if fallas:
                raise ProyectoNoComponible("La verificación del PDF del proyecto falló; no se "
                                           "generó:\n" + "\n".join(f"- {f}" for f in fallas))
            os.replace(temporal_salida, salida)
        finally:
            if temporal_salida.exists():
                temporal_salida.unlink()
    for h in compuestas:  # el PDF de cada hoja era temporal: queda el del proyecto
        h.resultado.ruta_pdf = salida
    return ResultadoProyecto(salida, origen, compuestas)


def _firma(pagina: pymupdf.Page) -> dict:
    """Lo que debe ser igual entre una página del proyecto y la de su hoja."""
    trazos = [tuple(round(v, 2) for v in d["rect"]) + (d.get("type"),) for d in pagina.get_drawings()]
    imagenes = [tuple(round(v, 2) for v in i["bbox"]) for i in pagina.get_image_info()]
    return {"tamano": (round(pagina.rect.width, 2), round(pagina.rect.height, 2)),
            "trazos": trazos, "texto": pagina.get_text(), "imagenes": imagenes}


def verificar_proyecto(ruta: Path, hojas: list[Path]) -> list[str]:
    """Páginas = hojas, en orden, y cada página igual a la de su hoja. Lista de problemas."""
    fallas = []
    with pymupdf.open(ruta) as unido:
        if unido.page_count != len(hojas):
            return [f"el PDF tiene {unido.page_count} página(s) y el proyecto {len(hojas)} hoja(s)"]
        for i, ruta_hoja in enumerate(hojas):
            with pymupdf.open(ruta_hoja) as hoja:
                esperada, obtenida = _firma(hoja[0]), _firma(unido[i])
            distintas = [k for k in esperada if esperada[k] != obtenida[k]]
            if distintas:
                fallas.append(f"la página {i + 1} no es igual a su hoja ({', '.join(distintas)} "
                              f"distintos)")
    return fallas


def _sangrar(texto: str) -> str:
    return "\n".join(f"  {linea}" for linea in texto.splitlines())
