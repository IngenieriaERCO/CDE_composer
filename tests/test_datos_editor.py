"""Datos e imágenes para el editor (paquetes y plantilla sintéticos, no de ERCO)."""

import json

import pymupdf
import pytest

from componedor.cli import main
from componedor.componer import componer_plano
from componedor.datos_editor import construir_datos_editor, preparar_editor
from componedor.plano import leer_plano
from conftest import crear_paquete_real, crear_plantilla_sintetica, escribir_formato

ROSA = [612.0, 51.0, 652.0, 91.0]


@pytest.fixture
def entorno(tmp_path):
    """formato.json (plantilla con una «rosa»), paquetes en input/: a (cabe), grande (no
    cabe) y sin_escala (rechazado). La salida del editor va en editor/."""
    plantilla = crear_plantilla_sintetica(tmp_path / "rotulo.pdf", elementos_mm=[ROSA])
    escribir_formato(tmp_path / "formato.json", plantilla=plantilla,
                     elementos_plantilla=[{"nombre": "rosa_vientos", "rect_mm": ROSA}])
    crear_paquete_real(tmp_path / "input", "a")
    crear_paquete_real(tmp_path / "input", "grande", pagina_mm=(700.0, 120.0), cambiar={
        "pdf.page_size_mm": [700.0, 120.0], "pdf.expected_page_size_mm": [700.0, 120.0]})
    crear_paquete_real(tmp_path / "input", "sin_escala",
                       cambiar={"scale.physical_scale_guaranteed": False})
    return tmp_path


def _datos(entorno):
    datos, _ = construir_datos_editor(entorno / "input", entorno / "formato.json",
                                      entorno / "editor")
    return datos


def test_hoja_zonas_y_elementos(entorno):
    d = _datos(entorno)
    assert d["version"] == 1
    assert d["formato"] == "../formato.json"  # relativa a la carpeta del editor
    assert d["hoja"] == {"ancho_mm": 841.0, "alto_mm": 594.0}
    editables = [z["nombre"] for z in d["zonas"] if z["editable"]]
    assert editables == ["area_dibujo"]  # SOLO el área de dibujo
    assert {z["nombre"] for z in d["zonas"]} == {
        "area_dibujo", "rotulo", "localizacion", "notas", "convenciones", "cajetin"}
    area = next(z for z in d["zonas"] if z["nombre"] == "area_dibujo")
    assert area["rect_mm"] == [22.7, 22.7, 662.4, 571.3]
    assert d["elementos_plantilla"] == [{"nombre": "rosa_vientos", "rect_mm": ROSA}]


def test_detalles_aceptados(entorno):
    detalles = {x["id"]: x for x in _datos(entorno)["detalles"]}
    assert set(detalles) == {"a", "grande"}  # el rechazado no se puede arrastrar
    a = detalles["a"]
    assert a["manifiesto"] == "../input/a.manifest.json"
    assert (a["bloque"], a["escala"], a["cabe"]) == ("DETALLE_PRUEBA", 50.0, True)
    assert a["tamano_pagina_mm"] == [260.0, 120.0]
    # page_bounds (37,3; 18,7; 237,3; 98,7), Y abajo, en papel relativo a la esquina inferior
    # izquierda de la página (alto 120): Y = 120 - 98,7 = 21,3 a 120 - 18,7 = 101,3.
    assert a["limites_dibujo_mm"] == pytest.approx([37.3, 21.3, 237.3, 101.3])
    assert a["miniatura"] == {"archivo": "miniaturas/a.png"}
    assert detalles["grande"]["cabe"] is False
    assert detalles["grande"]["notas"][0].startswith("no cabe en area_dibujo")


def test_rechazados_con_motivos(entorno):
    (r,) = _datos(entorno)["rechazados"]
    assert r["prefijo"] == "sin_escala"
    assert r["manifiesto"] == "../input/sin_escala.manifest.json"
    assert r["motivos"][0].startswith("[escala] escala física no garantizada")


def test_coordenadas_del_dibujo_coinciden_con_componer(entorno):
    # Lo que el editor calcula (posición + limites_dibujo_mm) es lo que componer coloca.
    a = next(x for x in _datos(entorno)["detalles"] if x["id"] == "a")
    plano = entorno / "plano.json"
    plano.write_text(json.dumps({"version": 1, "formato": "formato.json", "detalles": [
        {"id": "a", "manifiesto": "input/a.manifest.json", "posicion_mm": [30, 430]}]}),
        encoding="utf-8")
    (colocado,) = componer_plano(leer_plano(plano), entorno / "p.pdf").detalles
    x0, y0, x1, y1 = a["limites_dibujo_mm"]
    assert colocado.dibujo == pytest.approx((30 + x0, 430 + y0, 30 + x1, 430 + y1))


def test_preparar_escribe_json_y_png(entorno):
    salida = entorno / "editor"
    datos = preparar_editor(entorno / "input", entorno / "formato.json", salida)
    escrito = json.loads((salida / "editor_datos.json").read_text(encoding="utf-8"))
    assert escrito == datos
    # Hoja A1 horizontal: lado mayor 1600 px (594 / 841 x 1600 = 1130,03, PyMuPDF redondea
    # hacia arriba). El JSON trae el tamaño real de cada imagen.
    assert datos["imagen_plantilla"] == {"archivo": "plantilla.png", "ancho_px": 1600,
                                         "alto_px": 1131}
    png = pymupdf.Pixmap(str(salida / "plantilla.png"))
    assert (png.width, png.height) == (1600, 1131)
    miniatura = next(x for x in datos["detalles"] if x["id"] == "a")["miniatura"]
    # Lado mayor 1400 px (antes 600): 120 / 260 x 1400 = 646,15 -> 647 (redondeo hacia arriba).
    assert miniatura["ancho_px"] == 1400 and miniatura["alto_px"] == 647
    assert (salida / "miniaturas" / "a.png").is_file()
    assert sorted(p.name for p in (salida / "miniaturas").iterdir()) == ["a.png", "grande.png"]


def test_tiene_fondo_y_miniatura_transparente_u_opaca(entorno):
    crear_paquete_real(entorno / "input", "nuevo", sin_fondo=True)
    salida = entorno / "editor"
    datos = preparar_editor(entorno / "input", entorno / "formato.json", salida)
    detalles = {x["id"]: x for x in datos["detalles"]}
    assert detalles["a"]["tiene_fondo"] is True  # paquete antiguo
    assert detalles["nuevo"]["tiene_fondo"] is False
    escrito = json.loads((salida / "editor_datos.json").read_text(encoding="utf-8"))
    assert {x["id"]: x["tiene_fondo"] for x in escrito["detalles"]} == {
        "a": True, "grande": True, "nuevo": False}

    opaca = pymupdf.Pixmap(str(salida / "miniaturas" / "a.png"))
    transparente = pymupdf.Pixmap(str(salida / "miniaturas" / "nuevo.png"))
    assert opaca.alpha == 0  # sin canal alfa: el fondo blanco tapa lo de abajo
    assert transparente.alpha == 1
    # La esquina (fuera del dibujo) es totalmente transparente; las líneas del dibujo, no
    # (son finas y suavizadas: opacas en parte).
    assert transparente.pixel(2, 2)[3] == 0
    assert max(transparente.pixel(x, transparente.height // 2)[3]
               for x in range(transparente.width)) > 100


def test_tamano_de_imagen_configurable(entorno):
    datos = preparar_editor(entorno / "input", entorno / "formato.json", entorno / "editor",
                            max_px_hoja=400, max_px_miniatura=100)
    assert datos["imagen_plantilla"]["ancho_px"] == 400
    assert max(datos["detalles"][0]["miniatura"]["ancho_px"],
               datos["detalles"][0]["miniatura"]["alto_px"]) == 100


def test_carpeta_existente(entorno):
    salida = entorno / "editor"
    salida.mkdir()  # vacía: se puede usar
    preparar_editor(entorno / "input", entorno / "formato.json", salida)
    with pytest.raises(FileExistsError, match="ya tiene contenido. Use --sobrescribir"):
        preparar_editor(entorno / "input", entorno / "formato.json", salida)
    vieja = salida / "miniaturas" / "detalle_viejo.png"
    vieja.write_bytes(b"png viejo")
    nota = salida / "notas_mias.txt"
    nota.write_text("no tocar", encoding="utf-8")
    preparar_editor(entorno / "input", entorno / "formato.json", salida, sobrescribir=True)
    assert not vieja.exists()  # las miniaturas viejas se borran
    assert nota.read_text(encoding="utf-8") == "no tocar"  # lo demás no se toca


def test_cli_preparar_editor(entorno, capsys):
    args = ["preparar-editor", str(entorno / "input"), "--formato",
            str(entorno / "formato.json"), "--salida", str(entorno / "editor")]
    assert main(args) == 0
    out = capsys.readouterr().out
    assert "plantilla.png (1600 x 1131 px) y 2 miniatura(s) en miniaturas/" in out
    assert "Elementos fijos de la plantilla: 1" in out
    assert "  grande: 1:50, página 700.00 x 120.00 mm, NO cabe en area_dibujo" in out
    assert "  sin_escala: rechazado (1 motivo(s))" in out
    assert out.rstrip().endswith("2 aceptado(s), 1 rechazado(s), 1 cabrían en area_dibujo.")
    assert main(args) == 1
    assert "Use --sobrescribir" in capsys.readouterr().err
    assert main(args + ["--sobrescribir"]) == 0
