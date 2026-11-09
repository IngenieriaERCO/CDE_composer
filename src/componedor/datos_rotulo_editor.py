"""Lo que el editor necesita del RÓTULO (subfase 4.3a): todo se incrusta en editor.html.

- `catalogo_notas(carpeta)`: notas típicas leídas de los .txt de una carpeta, de forma
  recursiva y con las mismas reglas que `componer` (`notas.leer_archivo_notas`: una nota por
  línea, viñetas con «- », comentarios con #, número propio quitado con aviso). Cada subcarpeta
  es un GRUPO del catálogo (su ruta relativa es el título: «vias», «hidraulica», …); los .txt
  de la carpeta raíz van en el grupo «General». Grupos → archivos → notas, con los avisos y
  problemas de lectura de cada archivo.
- `simbolos_editor(...)`: un PNG transparente a 20 px/mm de cada símbolo de la biblioteca de
  convenciones, dibujado con su opacidad (como saldrá en el PDF). Si falta la biblioteca, lista
  vacía y un aviso que dice cómo generarla.
- `tabla_anchos(fuente)`: ancho de avance (em) de cada carácter de Arial que el editor puede
  escribir, y la proporción de las mayúsculas: con eso el JavaScript mide igual que Python.
- `definicion_editor(definicion)`: las celdas del rótulo (mm de papel) en JSON.

Las FIRMAS en imagen nunca se incrustan: aquí no se lee la carpeta de firmas.
"""

from pathlib import Path

import pymupdf

from componedor.fuente import Fuente
from componedor.notas import leer_archivo_notas
from componedor.rotulo_formato import (
    CampoConvenciones,
    CampoNotas,
    CampoTabla,
    CampoTexto,
    DefinicionRotulo,
)
from componedor.simbolos import BibliotecaInvalida, cargar_biblioteca, con_opacidad

GRUPO_RAIZ = "General"
PX_POR_MM_SIMBOLOS = 20
CARPETA_SIMBOLOS = "simbolos"
# Lo que el editor puede escribir: ASCII imprimible, Latin-1 y algunos signos tipográficos.
CARACTERES = ("".join(chr(c) for c in range(32, 127)) + "".join(chr(c) for c in range(160, 256))
              + "–—‘’“”•…€‰")


def catalogo_notas(carpeta: Path | str) -> dict:
    """{"carpeta", "grupos": [{"titulo", "archivos": [{"archivo", "notas", "avisos",
    "problemas"}]}], "avisos"}. Grupos: «General» primero y luego por orden alfabético."""
    carpeta = Path(carpeta)
    if not carpeta.is_dir():
        return {"carpeta": str(carpeta), "grupos": [],
                "avisos": [f"no se encontró la carpeta de notas '{carpeta}'"]}
    grupos: dict[str, list[dict]] = {}
    for txt in sorted(carpeta.rglob("*.txt"), key=lambda r: r.relative_to(carpeta).as_posix()):
        relativa = txt.relative_to(carpeta)
        titulo = relativa.parent.as_posix() if relativa.parent != Path(".") else GRUPO_RAIZ
        notas, avisos, problemas = leer_archivo_notas(txt, relativa.as_posix())
        grupos.setdefault(titulo, []).append({
            "archivo": relativa.as_posix(),
            "notas": [{"texto": n.texto, "vinetas": list(n.vinetas), "origen": n.origen}
                      for n in notas],
            "avisos": avisos,
            "problemas": problemas,
        })
    orden = sorted(grupos, key=lambda t: (t != GRUPO_RAIZ, t.casefold()))
    return {"carpeta": str(carpeta), "grupos": [{"titulo": t, "archivos": grupos[t]} for t in orden],
            "avisos": [] if grupos else [f"la carpeta de notas '{carpeta}' no tiene archivos .txt"]}


def simbolos_editor(definicion: DefinicionRotulo, carpeta_salida: Path) -> tuple[list[dict], list[str]]:
    """(símbolos con su PNG en carpeta_salida/simbolos/, avisos)."""
    campo = next((c for c in definicion.campos.values() if isinstance(c, CampoConvenciones)), None)
    if campo is None:
        return [], []
    try:
        biblioteca = cargar_biblioteca(campo.biblioteca)
    except BibliotecaInvalida as e:
        return [], [f"convenciones: {e}"]
    destino = carpeta_salida / CARPETA_SIMBOLOS
    destino.mkdir(parents=True, exist_ok=True)
    for viejo in destino.glob("*.png"):
        viejo.unlink()
    zoom = PX_POR_MM_SIMBOLOS * 25.4 / 72
    lista = []
    with pymupdf.open(biblioteca.ruta_pdf) as doc:
        for s in biblioteca.simbolos.values():
            if s.opacidad < 1:
                fuente_doc, pagina = con_opacidad(doc, s.pagina - 1, s.opacidad), 0
            else:
                fuente_doc, pagina = doc, s.pagina - 1
            pix = fuente_doc[pagina].get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=True)
            if fuente_doc is not doc:
                fuente_doc.close()
            archivo = f"{CARPETA_SIMBOLOS}/{s.id}.png"
            pix.save(carpeta_salida / archivo)
            ancho, alto = s.tamano_mm
            lista.append({
                "id": s.id, "descripcion": s.descripcion, "opacidad": s.opacidad,
                "tamano_dibujo_mm": [ancho, alto], "margen_mm": biblioteca.margen_mm,
                "imagen": {"archivo": archivo, "ancho_px": pix.width, "alto_px": pix.height},
            })
    return lista, []


def tabla_anchos(fuente: Fuente) -> dict:
    return {"nombre": fuente.nombre, "altura_mayusculas": fuente.altura_mayusculas,
            "anchos_em": fuente.anchos_em(CARACTERES)}


def definicion_editor(definicion: DefinicionRotulo) -> dict:
    """La definición del rótulo en JSON (celdas en mm de papel, Y hacia arriba)."""
    campos = {}
    for nombre, campo in definicion.campos.items():
        if isinstance(campo, CampoTexto):
            campos[nombre] = {"tipo": "texto", **_celda(campo.celda),
                              "por_defecto": campo.por_defecto, "calculado": campo.calculado}
        elif isinstance(campo, CampoTabla):
            primera = next(iter(campo.celdas.values()))
            campos[nombre] = {
                "tipo": "tabla", "altura_mm": primera.altura_mm,
                "altura_min_mm": primera.altura_min_mm,
                "columna_clave": campo.columna_clave, "orden": list(campo.orden),
                "filas": [{"clave": f, "y_mm": [campo.celdas[(f, campo.columnas[0])].rect[1],
                                                campo.celdas[(f, campo.columnas[0])].rect[3]],
                           "lineas_max": campo.celdas[(f, campo.columnas[0])].lineas_max}
                          for f in campo.filas],
                "columnas": [{"clave": c, "x_mm": [campo.celdas[(campo.filas[0], c)].rect[0],
                                                   campo.celdas[(campo.filas[0], c)].rect[2]],
                              "alinear": campo.celdas[(campo.filas[0], c)].alinear,
                              "acepta_imagen": campo.celdas[(campo.filas[0], c)].acepta_imagen,
                              "alto_max_mm": campo.celdas[(campo.filas[0], c)].alto_max_mm}
                             for c in campo.columnas],
            }
        elif isinstance(campo, CampoNotas):
            campos[nombre] = {"tipo": "notas", **_celda(campo.celda),
                              "separacion_notas": campo.separacion_notas}
        elif isinstance(campo, CampoConvenciones):
            campos[nombre] = {"tipo": "convenciones", "capacidad": campo.capacidad,
                              "simbolos": [list(c.rect) for c in campo.simbolos],
                              "descripciones": [_celda(c) for c in campo.descripciones]}
    return {"version": definicion.version, "relleno_mm": definicion.relleno_mm,
            "interlineado": definicion.interlineado, "formato_fecha": definicion.formato_fecha,
            "campos": campos}


def _celda(c) -> dict:
    return {"rect_mm": list(c.rect), "alinear": c.alinear, "altura_mm": c.altura_mm,
            "altura_min_mm": c.altura_min_mm, "lineas_max": c.lineas_max}
