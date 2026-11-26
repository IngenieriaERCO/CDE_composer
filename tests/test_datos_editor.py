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
    # «grande»: página de 700 mm (no cabe), pero su dibujo mide 200 × 80: con el recorte de
    # 1 mm (Fase 11) lo que se ve cabe. Con un margen que deja la página entera, no.
    assert detalles["grande"]["cabe"] is True and detalles["grande"]["notas"] == []
    datos, _ = construir_datos_editor(entorno / "input", entorno / "formato.json",
                                      entorno / "editor", margen_detalle_mm=50)
    grande = {x["id"]: x for x in datos["detalles"]}["grande"]
    # Con 50 mm: X 0..287,3 (no pasa del borde de la página): todavía cabe.
    assert datos["margen_detalle_mm"] == 50 and grande["cabe"] is True


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
                                         "alto_px": 1131, "svg": {"archivo": "plantilla.svg"}}
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


def test_rosa_aparte_y_plantilla_sin_rosa(entorno):
    # WYSIWYG (subfase 4.1): plantilla.png NO trae la rosa (el editor la dibuja donde esté);
    # rosa.png es la rosa sola, transparente, recortada a su rectángulo.
    salida = entorno / "editor"
    datos = preparar_editor(entorno / "input", entorno / "formato.json", salida)
    rosa = datos["rosa_vientos"]
    assert rosa["nombre"] == "rosa_vientos" and rosa["rect_mm"] == ROSA
    assert rosa["imagen"]["archivo"] == "rosa.png"
    png = pymupdf.Pixmap(str(salida / "rosa.png"))
    assert (png.width, png.height) == (rosa["imagen"]["ancho_px"], rosa["imagen"]["alto_px"])
    assert max(png.width, png.height) == 600 and png.alpha == 1
    # Centro del cuadro: transparente; borde izquierdo del cuadro y diagonal: con tinta.
    assert png.pixel(png.width // 4, png.height // 2)[3] == 0
    assert max(png.pixel(x, png.height // 2)[3] for x in range(4)) > 100

    hoja = pymupdf.Pixmap(str(salida / "plantilla.png"))
    escala = hoja.width / 841.0
    # En plantilla.png, donde estaba el borde izquierdo de la rosa (X 612) no queda tinta.
    x = round(612.0 * escala)
    filas = range(round((594 - 91) * escala) + 3, round((594 - 51) * escala) - 3)
    assert all(hoja.pixel(xx, y)[0] > 200 for y in filas for xx in (x - 1, x, x + 1))


def test_plantilla_en_svg_igual_que_el_png_y_sin_rosa(entorno):
    """4.3f: plantilla.svg es la MISMA hoja base que plantilla.png, en vector: A1 (841 x 594
    mm), sin la rosa, con los textos como curvas (no necesita fuentes) y sin cargar nada de
    afuera. Rasterizada al mismo tamaño se ve igual que el PNG."""
    salida = entorno / "editor"
    preparar_editor(entorno / "input", entorno / "formato.json", salida)
    texto = (salida / "plantilla.svg").read_text(encoding="utf-8")
    assert texto.startswith("<svg") and "<text" not in texto
    assert "href=\"http" not in texto and "url(http" not in texto
    with pymupdf.open(stream=texto.encode("utf-8"), filetype="svg") as doc:
        pagina = doc[0]
        assert pagina.rect.width * 25.4 / 72 == pytest.approx(841.0, abs=0.1)
        assert pagina.rect.height * 25.4 / 72 == pytest.approx(594.0, abs=0.1)
        hoja = pagina.get_pixmap(matrix=pymupdf.Matrix(1600 / pagina.rect.width, 1600 / pagina.rect.width))
    png = pymupdf.Pixmap(str(salida / "plantilla.png"))
    assert (hoja.width, hoja.height) == (png.width, png.height)
    # Mismo dibujo: casi todos los píxeles iguales (solo difiere el suavizado de los bordes).
    a, b = hoja.samples, png.samples
    distintos = sum(1 for i in range(0, len(a), 3 * 7) if abs(a[i] - b[i]) > 60)
    assert distintos / (len(a) / (3 * 7)) < 0.002
    tinta = sum(1 for i in range(0, len(a), 3 * 7) if a[i] < 128)
    assert tinta > 100  # hay dibujo (marco y rótulo)
    escala = hoja.width / 841.0
    x = round(612.0 * escala)  # borde izquierdo de la rosa: sin tinta
    filas = range(round((594 - 91) * escala) + 3, round((594 - 51) * escala) - 3)
    assert all(hoja.pixel(xx, y)[0] > 200 for y in filas for xx in (x - 1, x, x + 1))


def test_sin_plantilla_la_rosa_va_sin_imagen(tmp_path):
    escribir_formato(tmp_path / "formato.json",
                     elementos_plantilla=[{"nombre": "rosa_vientos", "rect_mm": ROSA}])
    crear_paquete_real(tmp_path / "input", "a")
    datos = preparar_editor(tmp_path / "input", tmp_path / "formato.json", tmp_path / "editor")
    assert datos["rosa_vientos"] == {"nombre": "rosa_vientos", "rect_mm": ROSA, "imagen": None}
    assert not (tmp_path / "editor" / "rosa.png").exists()
    escribir_formato(tmp_path / "formato.json")  # sin rosa
    datos = preparar_editor(tmp_path / "input", tmp_path / "formato.json", tmp_path / "editor",
                            sobrescribir=True)
    assert datos["rosa_vientos"] is None


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
    # Cabe lo que se ve: el dibujo y 1 mm (la página de 700 mm se recorta al componer).
    assert "  grande: 1:50, página 700.00 x 120.00 mm, cabe en area_dibujo" in out
    assert "  sin_escala: rechazado (1 motivo(s))" in out
    assert out.rstrip().endswith("2 aceptado(s), 1 rechazado(s), 2 cabrían en area_dibujo.")
    assert main(args) == 1
    assert "Use --sobrescribir" in capsys.readouterr().err
    assert main(args + ["--sobrescribir"]) == 0
