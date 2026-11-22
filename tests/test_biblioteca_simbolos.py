"""Biblioteca de símbolos versión 2 (subfase 9b): índice con tipo, origen y fecha, un PDF por
símbolo, migración desde la versión 1 sin cambiar ningún dibujo y `carpeta_simbolos`."""

import json
import shutil
from pathlib import Path

import pymupdf
import pytest

from componedor import biblioteca_simbolos as modulo
from componedor.biblioteca_simbolos import (
    MigracionFallida,
    con_carpeta_simbolos,
    migrar_v1,
)
from componedor.cli import main
from componedor.componer import PlanoNoComponible, componer_plano
from componedor.configuracion import ConfigInvalida, leer_config_componer, leer_config_editor
from componedor.datos_editor import preparar_editor
from componedor.formato import cargar_formato
from componedor.rotulo_formato import CampoConvenciones
from componedor.simbolos import BibliotecaInvalida, cargar_biblioteca, extraer_simbolos
from conftest import crear_paquete_real, requiere_arial
from test_simbolos import _plano, biblioteca, entorno  # noqa: F401 (fixtures)

FECHA = "2026-11-21"
CONVENCIONES = [{"simbolo": "corte"}, {"simbolo": "limite_2"}, {"simbolo": "panel", "descripcion": "MÍO"},
                {"simbolo": "alto"}, {"simbolo": "via_3"}]


def _a_v1(carpeta: Path) -> None:
    """Convierte la biblioteca versión 2 extraída en la versión 1 de siempre (un PDF con una
    página por símbolo, convenciones_erco.pdf), como la que hoy tiene el usuario."""
    simbolos = carpeta / "simbolos"
    v2 = json.loads((simbolos / "indice.json").read_text(encoding="utf-8"))
    todos = pymupdf.open()
    lista = []
    for k, s in enumerate(v2["simbolos"], start=1):
        with pymupdf.open(simbolos / "biblioteca" / f"{s['id']}.pdf") as uno:
            todos.insert_pdf(uno)
        lista.append({"id": s["id"], "descripcion": s["descripcion"],
                      "casilla_origen": s["origen"]["casilla"], "pagina": k,
                      "rect_mm": s["origen"]["rect_mm"], "trazos": s["trazos"],
                      **({"opacidad": s["opacidad"]} if "opacidad" in s else {})})
    todos.save(simbolos / "convenciones_erco.pdf")
    todos.close()
    (simbolos / "indice.json").write_text(json.dumps({
        "version": 1, "biblioteca": "convenciones_erco.pdf",
        "origen": {"plano": "plano_con_leyenda.pdf", "pagina": 1, "margen_mm": 0.5},
        "simbolos": lista}, ensure_ascii=False), encoding="utf-8")
    shutil.rmtree(simbolos / "biblioteca")


def _dibujos(ruta):
    with pymupdf.open(ruta) as doc:
        return [(tuple(round(v, 4) for v in d["rect"]), d["type"], d.get("color"), d.get("fill"),
                 d.get("width"), d.get("fill_opacity"), d.get("stroke_opacity"))
                for d in doc[0].get_drawings()]


@pytest.fixture
def v1(entorno):  # noqa: F811
    _a_v1(entorno)
    return entorno


def test_v1_se_sigue_leyendo_con_su_pdf_y_su_margen(v1):
    b = cargar_biblioteca(v1 / "simbolos" / "indice.json")
    corte = b.simbolos["corte"]
    assert b.ruta_pdf.name == "convenciones_erco.pdf" and corte.ruta_pdf == b.ruta_pdf
    assert corte.pagina == 2 and corte.margen_mm == 0.5


@requiere_arial
def test_migrar_no_cambia_ningun_dibujo_ni_el_plano_compuesto(v1):
    antes = componer_plano(_plano(v1, CONVENCIONES), v1 / "antes.pdf")
    indice = v1 / "simbolos" / "indice.json"
    viejo = indice.read_text(encoding="utf-8")
    informe = migrar_v1(indice, v1 / "_para_borrar", FECHA)
    assert informe.ids[:3] == ["limite", "corte", "via"] and len(informe.ids) == 14
    # El PDF viejo y una copia del índice viejo se MOVIERON (no se borró nada).
    guardado = v1 / "_para_borrar" / f"simbolos_v1_{FECHA}"
    assert (guardado / "convenciones_erco.pdf").is_file() and not (v1 / "simbolos" / "convenciones_erco.pdf").exists()
    assert (guardado / "indice.json").read_text(encoding="utf-8") == viejo
    datos = json.loads(indice.read_text(encoding="utf-8"))
    assert datos["version"] == 2 and all(s["fecha"] == FECHA and s["tipo"] == "vector" for s in datos["simbolos"])
    assert datos["simbolos"][1]["origen"]["clase"] == "plano_pdf" and datos["simbolos"][1]["origen"]["casilla"] == 2
    assert sorted(p.name for p in (v1 / "simbolos" / "biblioteca").iterdir()) == sorted(f"{i}.pdf" for i in informe.ids)
    despues = componer_plano(_plano(v1, CONVENCIONES), v1 / "despues.pdf")
    assert [(s.simbolo.id, s.posicion, s.escala) for s in despues.simbolos] == \
        [(s.simbolo.id, s.posicion, s.escala) for s in antes.simbolos]
    for a, d in zip(antes.simbolos, despues.simbolos):
        assert d.destino_dibujo == pytest.approx(a.destino_dibujo, abs=1e-9)
        assert d.destino_pagina == pytest.approx(a.destino_pagina, abs=1e-9)
    assert _dibujos(v1 / "despues.pdf") == _dibujos(v1 / "antes.pdf")
    assert despues.advertencias == antes.advertencias


def test_migrar_se_niega_sin_tocar_nada(v1, monkeypatch):
    indice = v1 / "simbolos" / "indice.json"
    viejo = indice.read_bytes()
    (v1 / "simbolos" / "biblioteca").mkdir()
    (v1 / "simbolos" / "biblioteca" / "corte.pdf").write_bytes(b"de otra persona")
    with pytest.raises(MigracionFallida, match="ya hay PDF de corte; no se pisan"):
        migrar_v1(indice, v1 / "_para_borrar", FECHA)
    (v1 / "simbolos" / "biblioteca" / "corte.pdf").unlink()
    # Una página que no queda igual: se detiene, borra solo lo suyo y deja la versión 1 intacta.
    original = modulo.guardar_pagina

    def vacia(doc, pagina, destino):
        if destino.stem == "via":
            with pymupdf.open() as nuevo:
                nuevo.new_page()
                nuevo.save(destino)
        else:
            original(doc, pagina, destino)

    monkeypatch.setattr(modulo, "guardar_pagina", vacia)
    with pytest.raises(MigracionFallida, match="'via': la página nueva no mide lo mismo"):
        migrar_v1(indice, v1 / "_para_borrar", FECHA)
    assert indice.read_bytes() == viejo and (v1 / "simbolos" / "convenciones_erco.pdf").is_file()
    assert not list((v1 / "simbolos" / "biblioteca").iterdir()) and not (v1 / "_para_borrar").exists()
    monkeypatch.undo()
    migrar_v1(indice, v1 / "_para_borrar", FECHA)
    with pytest.raises(MigracionFallida, match="ya es versión 2: no hay nada que migrar"):
        migrar_v1(indice, v1 / "_para_borrar", FECHA)


def test_indice_v2_con_problemas_los_dice_todos(biblioteca):  # noqa: F811
    carpeta, _ = biblioteca
    ruta = carpeta / "simbolos" / "indice.json"
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    s = datos["simbolos"]
    s[0]["id"] = "con espacio"
    s[2]["id"] = "corte"  # repetido
    s[3]["tipo"] = "imagen"
    s[4]["tamano_mm"] = [3]
    s[5]["fecha"] = "21/11/2026"
    del s[6]["origen"]
    s[7]["trazos"] = -1
    ruta.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(BibliotecaInvalida) as e:
        cargar_biblioteca(ruta)
    m = str(e.value)
    assert "tiene 7 problema(s)" in m
    for texto in ["símbolo 1: el id debe tener solo letras, números, «_» o «-» (es el nombre de su PDF)",
                  "'corte': el id está repetido", "'panel': tipo debe ser 'vector'; tiene 'imagen'",
                  "'linea_larga': tamano_mm debe ser [ancho, alto] en mm", "'alto': fecha debe ser AAAA-MM-DD",
                  "'limite_2': falta origen", "'relleno': trazos debe ser un entero ≥ 0"]:
        assert texto in m


def test_extraer_conserva_los_simbolos_de_otro_origen(biblioteca):  # noqa: F811
    carpeta, _ = biblioteca
    ruta = carpeta / "simbolos" / "indice.json"
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    otro = dict(datos["simbolos"][0], id="caja_electrica", descripcion="CAJA ELÉCTRICA",
                origen={"clase": "dxf", "dxf": "plano.dxf", "bloque": "CAJA"})
    shutil.copy(carpeta / "simbolos" / "biblioteca" / "limite.pdf", carpeta / "simbolos" / "biblioteca" / "caja_electrica.pdf")
    datos["simbolos"].append(otro)
    ruta.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    formato = cargar_formato(carpeta / "formato.json", usar_plantilla=False)
    extraer_simbolos(carpeta / "plano_con_leyenda.pdf", formato, ruta)
    escrito = json.loads(ruta.read_text(encoding="utf-8"))["simbolos"]
    assert escrito[-1] == otro and len(escrito) == 15
    assert "caja_electrica" in cargar_biblioteca(ruta).simbolos


# --- carpeta_simbolos ------------------------------------------------------------------------

def _mover_biblioteca(carpeta: Path) -> Path:
    """La biblioteca pasa a otra carpeta; la que dice el formato queda vacía."""
    otra = carpeta / "compartida" / "simbolos"
    otra.parent.mkdir()
    shutil.move(str(carpeta / "simbolos"), otra)
    return otra


def test_con_carpeta_simbolos_cambia_solo_la_biblioteca(tmp_path, biblioteca):  # noqa: F811
    carpeta, _ = biblioteca
    formato = cargar_formato(carpeta / "formato.json", usar_plantilla=False)
    assert con_carpeta_simbolos(formato, None) is formato
    nuevo = con_carpeta_simbolos(formato, tmp_path / "x")
    campo = next(c for c in nuevo.rotulo.campos.values() if isinstance(c, CampoConvenciones))
    assert campo.biblioteca == tmp_path / "x" / "indice.json"
    assert nuevo.rotulo.campos["titulo"] == formato.rotulo.campos["titulo"]


@requiere_arial
def test_componer_y_editor_usan_carpeta_simbolos(entorno):  # noqa: F811
    antes = componer_plano(_plano(entorno, CONVENCIONES), entorno / "antes.pdf")
    otra = _mover_biblioteca(entorno)
    with pytest.raises(PlanoNoComponible, match="no se encontró el índice de símbolos"):
        componer_plano(_plano(entorno, CONVENCIONES), entorno / "sin.pdf")
    despues = componer_plano(_plano(entorno, CONVENCIONES), entorno / "con.pdf", carpeta_simbolos=otra)
    assert _dibujos(entorno / "con.pdf") == _dibujos(entorno / "antes.pdf")
    assert [s.simbolo.id for s in despues.simbolos] == [s.simbolo.id for s in antes.simbolos]
    datos = preparar_editor(entorno / "input", entorno / "formato.json", entorno / "editor",
                            carpeta_simbolos=otra)
    assert [s["id"] for s in datos["rotulo"]["simbolos"]][:3] == ["limite", "corte", "via"]
    assert datos["rotulo"]["avisos"] == []
    assert preparar_editor(entorno / "input", entorno / "formato.json", entorno / "editor2")["rotulo"]["simbolos"] == []


def _config(carpeta: Path, **extra) -> Path:
    ruta = carpeta / "componedor.json"
    (carpeta / "resultados").mkdir(exist_ok=True)
    ruta.write_text(json.dumps({"version": 1, "formato": "formato.json", **extra,
                                "editor": {"paquetes": "input", "salida": "editor"},
                                "componer": {"resultados": "resultados"}}), encoding="utf-8")
    return ruta


def test_config_lee_carpeta_simbolos(tmp_path, biblioteca):  # noqa: F811
    carpeta, _ = biblioteca
    crear_paquete_real(carpeta / "input", "a")
    assert leer_config_componer(_config(carpeta)).simbolos is None
    assert leer_config_editor(_config(carpeta, carpeta_simbolos="simbolos")).simbolos == carpeta / "simbolos"
    assert leer_config_componer(_config(carpeta, carpeta_simbolos="simbolos")).simbolos == carpeta / "simbolos"
    with pytest.raises(ConfigInvalida, match="carpeta_simbolos: no existe la carpeta"):
        leer_config_componer(_config(carpeta, carpeta_simbolos="no_hay"))
    with pytest.raises(ConfigInvalida, match="carpeta_simbolos: se esperaba una ruta"):
        leer_config_editor(_config(carpeta, carpeta_simbolos=3))


@requiere_arial
def test_cli_componer_con_config_usa_carpeta_simbolos(entorno, capsys):  # noqa: F811
    otra = _mover_biblioteca(entorno)
    config = _config(entorno, carpeta_simbolos=str(otra.relative_to(entorno)))
    _plano(entorno, CONVENCIONES)
    assert main(["componer", str(entorno / "plano.json"), "--config", str(config)]) == 0
    assert "Convenciones: 5 símbolo(s)" in capsys.readouterr().out
    assert (entorno / "resultados" / "plano.pdf").is_file()


def test_cli_migrar_simbolos(v1, capsys):
    config = _config(v1, carpeta_simbolos="simbolos")
    assert main(["migrar-simbolos", "--config", str(config)]) == 0
    out = capsys.readouterr().out
    assert "pasada a la versión 2: 14 símbolo(s)" in out and "ningún dibujo cambió" in out
    assert str(v1 / "_para_borrar") in out
    assert json.loads((v1 / "simbolos" / "indice.json").read_text(encoding="utf-8"))["version"] == 2
    assert main(["migrar-simbolos", "--config", str(config)]) == 1
    assert "ya es versión 2" in capsys.readouterr().err
    assert main(["migrar-simbolos"]) == 1
    assert "indique --config componedor.json o --indice" in capsys.readouterr().err
