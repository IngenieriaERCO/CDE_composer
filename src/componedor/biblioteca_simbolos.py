"""Biblioteca de símbolos de convenciones, versión 2 (subfase 9b).

Un PDF por símbolo y un índice con sus datos:

    simbolos/indice.json              (se versiona)
    simbolos/biblioteca/<id>.pdf      (NO se versiona: los dibujos salen de planos de ERCO)

indice.json (versión 2):
    {"version": 2,
     "simbolos": [{"id": "corte", "descripcion": "CORTE", "tipo": "vector",
                   "tamano_mm": [17.695, 7.578], "margen_mm": 0.5, "trazos": 5,
                   "opacidad": 0.5,                                  (opcional, por defecto 1)
                   "origen": {"clase": "plano_pdf", "plano": "PRGE-...pdf", "pagina": 1,
                              "casilla": 11, "rect_mm": [x0, y0, x1, y1]},
                   "fecha": "2026-11-21"}, ...]}

- `id`: letras, números, «_» o «-» (es el nombre del PDF).
- `tipo`: "vector" (el único por ahora; las imágenes llegan en otra subfase).
- `tamano_mm`: el dibujo sin el margen; la página del PDF mide eso más `margen_mm` por lado.
- `trazos`: cuántos trazos tiene el PDF (se verifica al componer).
- `origen`: de dónde salió; con `"clase": "plano_pdf"`, la casilla de la leyenda de ese plano.
- `fecha`: cuándo entró a la biblioteca (AAAA-MM-DD).

La carpeta de la biblioteca se puede elegir con `carpeta_simbolos` en componedor.json
(`con_carpeta_simbolos`). `migrar_v1` pasa la biblioteca versión 1 (un PDF con una página por
símbolo, `convenciones_erco.pdf`) a la versión 2 copiando cada página TAL CUAL (vector, sin
redibujar) y verificando que cada PDF nuevo tenga los mismos trazos en el mismo lugar.
"""

import json
import re
import shutil
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path

import pymupdf

from componedor.formato import Formato
from componedor.rotulo_formato import CampoConvenciones

VERSION = 2
CARPETA_PDF = "biblioteca"
NOMBRE_INDICE = "indice.json"
TIPOS = ("vector",)
TOL_MIGRACION_PT = 1e-3
_ID = re.compile(r"[A-Za-z0-9_-]+")
_FECHA = re.compile(r"\d{4}-\d{2}-\d{2}")
COMO_MIGRAR = ("Si tiene la biblioteca versión 1 (convenciones_erco.pdf), pásela a la versión 2 "
               "con: python -m componedor.cli migrar-simbolos --config componedor.json")


class MigracionFallida(ValueError):
    """No se pudo pasar la biblioteca a la versión 2 (no se cambió nada)."""


@dataclass
class InformeMigracion:
    ruta_indice: Path
    carpeta_pdf: Path
    ids: list[str]
    movidos: list[Path]  # lo que se movió a la carpeta para borrar


def ruta_pdf_simbolo(ruta_indice: Path, ident: str) -> Path:
    return Path(ruta_indice).parent / CARPETA_PDF / f"{ident}.pdf"


def con_carpeta_simbolos(formato: Formato, carpeta: Path | None) -> Formato:
    """El formato con la biblioteca de convenciones en `carpeta`/indice.json (`carpeta_simbolos`
    de componedor.json). Sin carpeta, o sin campo de convenciones, el formato tal cual."""
    if carpeta is None or formato.rotulo is None:
        return formato
    campos = {nombre: (replace(c, biblioteca=Path(carpeta) / NOMBRE_INDICE)
                       if isinstance(c, CampoConvenciones) else c)
              for nombre, c in formato.rotulo.campos.items()}
    return replace(formato, rotulo=replace(formato.rotulo, campos=campos))


# --- leer --------------------------------------------------------------------------------------

def leer_entradas_v2(datos: dict, ruta_indice: Path) -> tuple[list[dict], list[str]]:
    """(símbolos del índice versión 2 ya revisados, problemas). Cada símbolo: el dict del índice
    con "tamano_mm" como tupla, "opacidad" y "margen_mm" como float, y "ruta_pdf"."""
    lista = datos.get("simbolos")
    if not isinstance(lista, list) or not lista:
        return [], [f"el índice '{ruta_indice}' no tiene símbolos"]
    problemas, salida, vistos = [], [], set()
    for k, item in enumerate(lista):
        donde = f"símbolo {k + 1}"
        if not isinstance(item, dict):
            problemas.append(f"{donde}: se esperaba un objeto; tiene {item!r}")
            continue
        ident = item.get("id")
        if not isinstance(ident, str) or not _ID.fullmatch(ident):
            problemas.append(f"{donde}: el id debe tener solo letras, números, «_» o «-» (es el "
                             f"nombre de su PDF); tiene {ident!r}")
            continue
        donde = f"'{ident}'"
        if ident in vistos:
            problemas.append(f"{donde}: el id está repetido")
            continue
        vistos.add(ident)
        antes = len(problemas)
        if not isinstance(item.get("descripcion", ""), str):
            problemas.append(f"{donde}: la descripción debe ser un texto")
        if item.get("tipo") not in TIPOS:
            problemas.append(f"{donde}: tipo debe ser {' o '.join(map(repr, TIPOS))}; tiene "
                             f"{item.get('tipo')!r}")
        tamano = item.get("tamano_mm")
        if not (isinstance(tamano, list) and len(tamano) == 2 and all(_num(v) and v >= 0 for v in tamano)):
            problemas.append(f"{donde}: tamano_mm debe ser [ancho, alto] en mm; tiene {tamano!r}")
        margen = item.get("margen_mm")
        if not (_num(margen) and margen >= 0):
            problemas.append(f"{donde}: margen_mm debe ser un número ≥ 0; tiene {margen!r}")
        trazos = item.get("trazos")
        if not (isinstance(trazos, int) and not isinstance(trazos, bool) and trazos >= 0):
            problemas.append(f"{donde}: trazos debe ser un entero ≥ 0; tiene {trazos!r}")
        opacidad = item.get("opacidad", 1)
        if not (_num(opacidad) and 0 < opacidad <= 1):
            problemas.append(f"la opacidad del símbolo '{ident}' debe ser un número mayor que 0 "
                             f"y hasta 1 (1 = opaco); tiene {opacidad!r}")
        if not isinstance(item.get("origen"), dict):
            problemas.append(f"{donde}: falta origen (de dónde salió el símbolo)")
        fecha = item.get("fecha")
        if not (isinstance(fecha, str) and _FECHA.fullmatch(fecha)):
            problemas.append(f"{donde}: fecha debe ser AAAA-MM-DD; tiene {fecha!r}")
        if len(problemas) > antes:
            continue
        salida.append({**item, "tamano_mm": (float(tamano[0]), float(tamano[1])),
                       "margen_mm": float(margen), "opacidad": float(opacidad),
                       "ruta_pdf": ruta_pdf_simbolo(ruta_indice, ident)})
    faltan = [e["id"] for e in salida if not e["ruta_pdf"].is_file()]
    if faltan:
        problemas.append(f"faltan los PDF de {', '.join(faltan)} en "
                         f"'{ruta_indice.parent / CARPETA_PDF}' (no se versionan). {COMO_MIGRAR}")
    return salida, problemas


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


# --- escribir ----------------------------------------------------------------------------------

def entrada_v2(ident: str, descripcion: str, tamano_mm, margen_mm: float, trazos: int,
               opacidad: float, origen: dict, fecha: str) -> dict:
    """Un símbolo del índice versión 2 (opacidad solo si es menor que 1)."""
    return {"id": ident, "descripcion": descripcion, "tipo": "vector",
            "tamano_mm": [round(float(v), 3) for v in tamano_mm], "margen_mm": margen_mm,
            "trazos": trazos, **({"opacidad": opacidad} if opacidad != 1 else {}),
            "origen": origen, "fecha": fecha}


def escribir_indice_v2(ruta: Path, entradas: list[dict]) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    texto = json.dumps({"version": VERSION, "simbolos": entradas}, ensure_ascii=False, indent=2)
    ruta.write_text(texto + "\n", encoding="utf-8", newline="\n")


def guardar_pagina(doc: pymupdf.Document, pagina: int, destino: Path) -> None:
    """Copia la página `pagina` (desde 0) de `doc`, tal cual, a un PDF propio."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    with pymupdf.open() as nuevo:
        nuevo.insert_pdf(doc, from_page=pagina, to_page=pagina)
        nuevo.save(destino, garbage=4, deflate=True)


def trazos_de(page: pymupdf.Page) -> list[tuple]:
    """Los trazos de una página como (caja en pt, tipo, color, relleno, grosor) para comparar."""
    return [(tuple(d["rect"]), d["type"], d.get("color"), d.get("fill"), d.get("width"))
            for d in page.get_drawings()]


# --- migrar de la versión 1 --------------------------------------------------------------------

def migrar_v1(ruta_indice: Path | str, carpeta_para_borrar: Path | str,
              fecha: str | None = None) -> InformeMigracion:
    """Pasa la biblioteca versión 1 a la versión 2 sin cambiar ningún dibujo. Orden seguro: los
    PDF nuevos se escriben y se verifican primero; solo entonces el PDF viejo y una copia del
    índice viejo se MUEVEN a <carpeta_para_borrar>/simbolos_v1_<fecha>/ y se escribe el índice
    nuevo. Si algo falla, no queda nada a medias. Lanza `MigracionFallida`."""
    from componedor.simbolos import BibliotecaInvalida, cargar_biblioteca  # evita ciclo

    ruta_indice = Path(ruta_indice)
    fecha = fecha or date.today().isoformat()
    try:
        datos = json.loads(ruta_indice.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        raise MigracionFallida(f"no se pudo leer el índice '{ruta_indice}': {e}") from e
    if isinstance(datos, dict) and datos.get("version") == VERSION:
        raise MigracionFallida(f"el índice '{ruta_indice}' ya es versión {VERSION}: no hay nada "
                               f"que migrar")
    try:
        biblioteca = cargar_biblioteca(ruta_indice)
    except BibliotecaInvalida as e:
        raise MigracionFallida(f"la biblioteca versión 1 no se puede usar: {e}") from e
    carpeta = ruta_indice.parent / CARPETA_PDF
    ocupados = [s.id for s in biblioteca.simbolos.values()
                if ruta_pdf_simbolo(ruta_indice, s.id).exists()]
    if ocupados:
        raise MigracionFallida(f"en '{carpeta}' ya hay PDF de {', '.join(ocupados)}; no se "
                               f"pisan. Muévalos a _para_borrar si sobran y vuelva a intentar.")
    origen = datos.get("origen", {})
    carpeta_nueva = not carpeta.exists()  # si falla, solo se quita si la creó la migración
    creados, entradas = [], []
    try:
        with pymupdf.open(biblioteca.ruta_pdf) as viejo:
            for s in biblioteca.simbolos.values():
                destino = ruta_pdf_simbolo(ruta_indice, s.id)
                guardar_pagina(viejo, s.pagina - 1, destino)
                creados.append(destino)
                with pymupdf.open(destino) as nuevo:
                    _comparar(s.id, viejo[s.pagina - 1], nuevo[0], s.trazos)
                entradas.append(entrada_v2(
                    s.id, s.descripcion, s.tamano_mm, biblioteca.margen_mm, s.trazos, s.opacidad,
                    {"clase": "plano_pdf", "plano": origen.get("plano"),
                     "pagina": origen.get("pagina", 1), "casilla": s.casilla_origen,
                     "rect_mm": list(s.rect_mm)}, fecha))
    except Exception:
        for c in creados:
            c.unlink(missing_ok=True)
        if carpeta_nueva and carpeta.is_dir() and not any(carpeta.iterdir()):
            carpeta.rmdir()
        raise
    guardado = Path(carpeta_para_borrar) / f"simbolos_v1_{fecha}"
    guardado.mkdir(parents=True, exist_ok=True)
    movidos = [guardado / ruta_indice.name, guardado / biblioteca.ruta_pdf.name]
    shutil.copy2(ruta_indice, movidos[0])  # copia del índice viejo (también queda en git)
    shutil.move(str(biblioteca.ruta_pdf), movidos[1])
    escribir_indice_v2(ruta_indice, entradas)
    return InformeMigracion(ruta_indice, carpeta, [e["id"] for e in entradas], movidos)


def _comparar(ident: str, pagina_vieja: pymupdf.Page, pagina_nueva: pymupdf.Page,
              trazos: int) -> None:
    """El PDF nuevo tiene la misma página y los mismos trazos que la página vieja."""
    if abs(pagina_vieja.rect.width - pagina_nueva.rect.width) > TOL_MIGRACION_PT or \
            abs(pagina_vieja.rect.height - pagina_nueva.rect.height) > TOL_MIGRACION_PT:
        raise MigracionFallida(f"'{ident}': la página nueva no mide lo mismo que la vieja")
    viejos, nuevos = trazos_de(pagina_vieja), trazos_de(pagina_nueva)
    if len(nuevos) != trazos or len(viejos) != trazos:
        raise MigracionFallida(f"'{ident}': el PDF nuevo tiene {len(nuevos)} trazos, la página "
                               f"vieja {len(viejos)} y el índice dice {trazos}")
    for a, b in zip(viejos, nuevos):
        if a[1:] != b[1:] or max(abs(x - y) for x, y in zip(a[0], b[0])) > TOL_MIGRACION_PT:
            raise MigracionFallida(f"'{ident}': un trazo del PDF nuevo no es igual al de la "
                                   f"página vieja")
