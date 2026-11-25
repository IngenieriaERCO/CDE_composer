"""Comando `componer`: varios detalles en un plano (paquetes sintéticos, no de ERCO).

Paquete sintético: página 260 x 120 mm, dibujo de 200 x 80 mm en page_bounds
(37,3; 18,7; 237,3; 98,7) mm de página (Y abajo). Área de dibujo A1: 22,7..662,4 x 22,7..571,3.
"""

import json

import pymupdf
import pytest

from componedor import componer
from componedor.cli import main
from componedor.componer import PlanoNoComponible, componer_plano
from componedor.plano import leer_plano
from componedor.transformaciones import rect_pdf_a_papel
from componedor.unidades import mm_a_pt
from conftest import crear_paquete_real, crear_plantilla_sintetica, escribir_formato

TOL = 0.1


@pytest.fixture
def entorno(tmp_path):
    """Carpeta con formato (plantilla sintética) y dos paquetes coherentes."""
    plantilla = crear_plantilla_sintetica(tmp_path / "rotulo.pdf")
    escribir_formato(tmp_path / "formato.json", plantilla=plantilla)
    crear_paquete_real(tmp_path / "input", "a")
    crear_paquete_real(tmp_path / "input", "b")
    return tmp_path


def _plano(carpeta, detalles, **extra):
    datos = {"version": 1, "formato": "formato.json", "detalles": detalles, **extra}
    ruta = carpeta / "plano.json"
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    return ruta


def _d(id_, prefijo, pos=None, centrar=False):
    d = {"id": id_, "manifiesto": f"input/{prefijo}.manifest.json"}
    if centrar:
        d["centrar"] = True
    else:
        d["posicion_mm"] = list(pos)
    return d


def _dibujo_esperado(x, y):
    """page_bounds del paquete sintético con la página en (x, y) mm de papel."""
    return (x + 37.3, y + 120 - 98.7, x + 237.3, y + 120 - 18.7)


def _rects_200x80(ruta_pdf):
    """Rectángulos de 200 x 80 mm (el dibujo de cada detalle) en mm de papel."""
    with pymupdf.open(ruta_pdf) as doc:
        return sorted(rect_pdf_a_papel(d["rect"], 594.0) for d in doc[0].get_drawings()
                      if abs(d["rect"].width - mm_a_pt(200)) < 1
                      and abs(d["rect"].height - mm_a_pt(80)) < 1)


def _cerca(a, b, tol=TOL):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def _sin_temporales(carpeta):
    return not list(carpeta.glob(".*.componiendo.pdf"))


def test_dos_detalles_bien_puestos(entorno):
    plano = leer_plano(_plano(entorno, [_d("d1", "a", (30, 430)), _d("d2", "b", (380, 40))]))
    salida = entorno / "salida" / "plano.pdf"
    r = componer_plano(plano, salida)
    assert salida.is_file() and _sin_temporales(salida.parent)
    assert [c.id for c in r.detalles] == ["d1", "d2"]
    assert _cerca(r.detalles[0].ocupado, (30, 430, 290, 550))
    assert r.advertencias == []
    rects = _rects_200x80(salida)
    assert len(rects) == 2
    assert _cerca(rects[0], _dibujo_esperado(30, 430))
    assert _cerca(rects[1], _dibujo_esperado(380, 40))
    with pymupdf.open(salida) as doc:
        assert len(doc[0].get_image_info()) == 1  # solo el logo de la plantilla


def test_centrar(entorno):
    plano = leer_plano(_plano(entorno, [_d("d1", "a", (30, 430)), _d("d2", "b", centrar=True)]))
    r = componer_plano(plano, entorno / "p.pdf")
    # Centro del área de dibujo: (342,55; 297,0); página de 260 x 120 mm.
    assert _cerca(r.detalles[1].ocupado, (212.55, 237.0, 472.55, 357.0))
    assert any(_cerca(rect, _dibujo_esperado(212.55, 237.0)) for rect in _rects_200x80(entorno / "p.pdf"))


def test_mismo_paquete_dos_veces(entorno):
    plano = leer_plano(_plano(entorno, [_d("izq", "a", (30, 430)), _d("der", "a", (380, 40))]))
    r = componer_plano(plano, entorno / "p.pdf")
    assert [c.prefijo for c in r.detalles] == ["a", "a"]
    assert len(_rects_200x80(entorno / "p.pdf")) == 2


def test_guias(entorno):
    plano = leer_plano(_plano(entorno, [_d("d1", "a", (30, 430))]))
    componer_plano(plano, entorno / "p.pdf", guias=True)  # la verificación cuenta las guías
    with pymupdf.open(entorno / "p.pdf") as doc:
        assert [d for d in doc[0].get_drawings() if d.get("dashes") not in (None, "[] 0")]


def test_detalle_fuera_del_area(entorno):
    plano = leer_plano(_plano(entorno, [_d("d1", "a", (30, 430)), _d("lejos", "b", (500, 40))]))
    with pytest.raises(PlanoNoComponible) as e:
        componer_plano(plano, entorno / "p.pdf")
    mensaje = str(e.value)
    assert "1 detalle(s) fuera de 'area_dibujo'" in mensaje
    assert "- detalle 'lejos': " in mensaje
    assert "se pasa 97.6 mm por la derecha" in mensaje
    assert "Invade 'rotulo'" in mensaje
    assert not (entorno / "p.pdf").exists()


def test_detalle_encima_del_rotulo(entorno):
    plano = leer_plano(_plano(entorno, [_d("en_rotulo", "a", (680, 300))]))
    with pytest.raises(PlanoNoComponible) as e:
        componer_plano(plano, entorno / "p.pdf")
    mensaje = str(e.value)
    assert "detalle 'en_rotulo'" in mensaje and "Invade 'rotulo'" in mensaje
    assert "el rótulo y las demás zonas no se pueden ocupar" in mensaje
    assert not (entorno / "p.pdf").exists()


def test_detalle_mas_grande_que_el_area(entorno):
    crear_paquete_real(entorno / "input", "grande", pagina_mm=(700.0, 120.0), cambiar={
        "pdf.page_size_mm": [700.0, 120.0], "pdf.expected_page_size_mm": [700.0, 120.0]})
    plano = leer_plano(_plano(entorno, [_d("g", "grande", (22.7, 40))]))
    with pytest.raises(PlanoNoComponible, match=r"detalle 'g'.*se pasa 60\.3 mm a lo ancho"):
        componer_plano(plano, entorno / "p.pdf")


def test_paquete_rechazado_entre_varios(entorno):
    crear_paquete_real(entorno / "input", "sin_escala",
                       cambiar={"scale.physical_scale_guaranteed": False})
    crear_paquete_real(entorno / "input", "corrido", desplazar_dibujo_mm=(0.0, 2.0))
    plano = leer_plano(_plano(entorno, [
        _d("bueno", "a", (30, 430)),
        _d("malo1", "sin_escala", (380, 40)),
        _d("malo2", "corrido", (30, 40)),
    ]))
    with pytest.raises(PlanoNoComponible) as e:
        componer_plano(plano, entorno / "p.pdf")
    mensaje = str(e.value)
    assert mensaje.startswith("No se compone el plano: 2 detalle(s) con paquete rechazado.")
    assert "detalle 'malo1'" in mensaje and "[escala] escala física no garantizada" in mensaje
    assert "detalle 'malo2'" in mensaje and "[coherencia] los trazos del PDF no están" in mensaje
    assert "detalle 'bueno'" not in mensaje
    assert not (entorno / "p.pdf").exists()


def test_traslape_de_paginas_es_advertencia(entorno):
    # Páginas: X 30..290 y 280..540 (10 mm de traslape); dibujos: 67,3..267,3 y 317,3..517,3.
    plano = leer_plano(_plano(entorno, [_d("d1", "a", (30, 300)), _d("d2", "b", (280, 300))]))
    r = componer_plano(plano, entorno / "p.pdf")
    (aviso,) = r.advertencias
    assert aviso.startswith("Advertencia: las PÁGINAS de 'd1' y 'd2' se traslapan (10.0 x 120.0 mm)")
    assert "fondo blanco" in aviso
    assert (entorno / "p.pdf").is_file()


def test_traslape_de_dibujos_es_advertencia_fuerte(entorno):
    plano = leer_plano(_plano(entorno, [_d("d1", "a", (30, 300)), _d("d2", "b", (130, 320))]))
    r = componer_plano(plano, entorno / "p.pdf")
    (aviso,) = r.advertencias
    assert aviso.startswith("ADVERTENCIA FUERTE: los DIBUJOS de 'd1' y 'd2' se traslapan")
    assert "'d2' (encima) tapa parte del dibujo de 'd1'" in aviso
    assert len(_rects_200x80(entorno / "p.pdf")) == 2  # y la verificación pasó igual


def test_salida_existente(entorno):
    plano = leer_plano(_plano(entorno, [_d("d1", "a", (30, 430))]))
    salida = entorno / "p.pdf"
    salida.write_bytes(b"no tocar")
    with pytest.raises(FileExistsError, match="Use --sobrescribir"):
        componer_plano(plano, salida)
    assert salida.read_bytes() == b"no tocar"
    componer_plano(plano, salida, sobrescribir=True)
    assert salida.read_bytes().startswith(b"%PDF")


def test_plantilla_del_plano(entorno):
    # Formato sin plantilla; el plano trae la suya.
    escribir_formato(entorno / "formato_sin.json")
    plano = leer_plano(_plano(entorno, [_d("d1", "a", (30, 430))],
                              formato="formato_sin.json", plantilla="rotulo.pdf"))
    r = componer_plano(plano, entorno / "p.pdf")
    assert r.plantilla is not None and r.plantilla.ruta.name == "rotulo.pdf"
    plano = leer_plano(_plano(entorno, [_d("d1", "a", (30, 430))], plantilla="no_hay.pdf"))
    with pytest.raises(PlanoNoComponible, match="plantilla: no se encontró el PDF"):
        componer_plano(plano, entorno / "q.pdf")


def test_conteo_de_trazos_que_no_cuadra(entorno, monkeypatch):
    original = componer.insertar_pagina

    def insertar_y_ensuciar(hoja, *args):
        ocupado = original(hoja, *args)
        hoja.draw_line(pymupdf.Point(10, 10), pymupdf.Point(20, 20))  # un trazo de más
        return ocupado

    monkeypatch.setattr(componer, "insertar_pagina", insertar_y_ensuciar)
    plano = leer_plano(_plano(entorno, [_d("d1", "a", (30, 430))]))
    with pytest.raises(PlanoNoComponible) as e:
        componer_plano(plano, entorno / "p.pdf")
    assert "no se pudo separar el dibujo de cada detalle" in str(e.value)
    assert "se esperaban" in str(e.value)
    assert not (entorno / "p.pdf").exists() and _sin_temporales(entorno)


def test_verificacion_detecta_detalle_corrido(entorno, monkeypatch):
    original = componer.insertar_pagina

    def insertar_corrido(hoja, formato, doc, pagina, posicion):
        return original(hoja, formato, doc, pagina, (posicion[0] + 1.0, posicion[1]))

    monkeypatch.setattr(componer, "insertar_pagina", insertar_corrido)
    plano = leer_plano(_plano(entorno, [_d("d1", "a", (30, 430))]))
    with pytest.raises(PlanoNoComponible) as e:
        componer_plano(plano, entorno / "p.pdf")
    assert "La verificación del PDF compuesto falló" in str(e.value)
    assert "detalle 'd1': el dibujo quedó en X 68.30" in str(e.value)
    assert "diferencia máx. 1.000 mm" in str(e.value)
    assert not (entorno / "p.pdf").exists() and _sin_temporales(entorno)


# --- CLI y rutas relativas al plano -------------------------------------------------------

def test_cli_desde_otra_carpeta(entorno, tmp_path_factory, monkeypatch, capsys):
    plano = _plano(entorno, [_d("d1", "a", (30, 430)), _d("d2", "b", centrar=True)])
    otra = tmp_path_factory.mktemp("otra_carpeta")
    monkeypatch.chdir(otra)  # las rutas del plano no dependen del directorio actual
    assert main(["componer", str(plano), "--salida", "salida.pdf"]) == 0
    out = capsys.readouterr().out
    assert (otra / "salida.pdf").is_file()
    assert "Plano: " in out and "(2 detalle(s))" in out
    assert "  d1: paquete a, esquina inferior izquierda (30.00, 430.00) mm" in out
    assert "  d2: paquete b, esquina inferior izquierda (212.55, 237.00) mm" in out
    assert "Advertencias: ninguna" in out
    assert "PDF: salida.pdf" in out


def test_cli_errores(entorno, capsys):
    plano = _plano(entorno, [_d("d1", "a", (30, 430)), _d("d1", "b", (380, 40))])
    assert main(["componer", str(plano), "--salida", str(entorno / "p.pdf")]) == 1
    assert "'d1' está repetido" in capsys.readouterr().err
    plano = _plano(entorno, [_d("d1", "a", (600, 430))])
    assert main(["componer", str(plano), "--salida", str(entorno / "p.pdf")]) == 1
    assert "detalle 'd1'" in capsys.readouterr().err
    plano = _plano(entorno, [_d("d1", "a", (30, 430))])
    (entorno / "p.pdf").write_bytes(b"x")
    assert main(["componer", str(plano), "--salida", str(entorno / "p.pdf")]) == 1
    assert "Use --sobrescribir" in capsys.readouterr().err
    assert main(["componer", str(plano), "--salida", str(entorno / "p.pdf"),
                 "--sobrescribir", "--guias"]) == 0


# --- La verificación final compara con los trazos del PROPIO PDF del detalle ------------------

def test_caja_declarada_algo_mayor_que_los_trazos_compone_bien(entorno):
    """El exportador puede declarar page_bounds_mm algo mayor que lo dibujado (el recuadro de un
    texto, el ancho de una línea…): la coherencia h lo admite hasta ±0,5 mm. Con la caja 0,2 mm
    más abajo que los trazos, el detalle compone: la verificación final mide la colocación
    contra los trazos de su PDF, no contra la caja (antes fallaba por 0,2 > 0,1 mm)."""
    from conftest import LIMITES_RECT_PAGINA_MM, RECT_CAD

    x0, y0, x1, y1 = LIMITES_RECT_PAGINA_MM
    crear_paquete_real(entorno / "input", "caja", sin_fondo=True, cambiar={
        "pdf.drawing.page_bounds_mm": {"x0": x0, "y0": y0, "x1": x1, "y1": y1 + 0.2},
        # La caja CAD, coherente con la de la página (1:50 en m: 0,2 mm = 0,01 m).
        "pdf.drawing.cad_bounds": {"min": [RECT_CAD[0], RECT_CAD[1] - 0.01], "max": [RECT_CAD[2], RECT_CAD[3]]}})
    plano = leer_plano(_plano(entorno, [_d("d1", "caja", (30, 430))]))
    resultado = componer_plano(plano, entorno / "p.pdf")
    (colocado,) = resultado.detalles
    assert colocado.dibujo[1] == pytest.approx(colocado.trazos[1] - 0.2, abs=1e-3)  # la caja, 0,2 más abajo
    assert (entorno / "p.pdf").is_file()


def test_detalle_realmente_corrido_medio_milimetro_falla(entorno, monkeypatch):
    """Si el detalle queda de verdad 0,5 mm fuera de su sitio, la verificación lo detecta
    (la tolerancia sigue siendo ±0,1 mm)."""
    original = componer.insertar_pagina

    def insertar_corrido(hoja, formato, doc, pagina, posicion):
        return original(hoja, formato, doc, pagina, (posicion[0], posicion[1] + 0.5))

    monkeypatch.setattr(componer, "insertar_pagina", insertar_corrido)
    plano = leer_plano(_plano(entorno, [_d("d1", "a", (30, 430))]))
    with pytest.raises(PlanoNoComponible) as e:
        componer_plano(plano, entorno / "p.pdf")
    texto = str(e.value)
    assert "detalle 'd1': el dibujo quedó en" in texto and "según el plano, debía quedar en" in texto
    assert "diferencia máx. 0.500 mm, tolerancia ±0.1 mm" in texto
    assert not (entorno / "p.pdf").exists()
