"""«Zonas del modelo» en el editor (Fase 10d): la lógica de editor_zonas.js, en Node.

Lo de pantalla (el diálogo) se verifica en Edge con el DXF real (data/verificacion)."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from conftest import ZONA_A1

import componedor
from componedor.exportar_zona import pagina_de_zona

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node no está instalado")
CARPETA_JS = Path(componedor.__file__).parent / "editor"
# Como el trabajador: 1500 px en el lado mayor, a = −d, origen arriba a la izquierda.
M = [2208.955224126, 0.0, 0.0, -2208.955224126, -10461742215.640985, 4935217840.489107]
AREA = list(ZONA_A1)


def a_cad(px, py):
    """Inversa de M en Python, para comparar."""
    return [(px - M[4]) / M[0], (py - M[5]) / M[3]]


def js(codigo: str, entrada=None):
    script = (
        f"const E = require({json.dumps(str(CARPETA_JS / 'editor_zonas.js'))});"
        "const entrada = JSON.parse(require('fs').readFileSync(0, 'utf8'));"
        f"const salida = (function () {{ {codigo} }})();"
        "process.stdout.write(JSON.stringify(salida === undefined ? null : salida));"
    )
    r = subprocess.run([NODE, "-e", script], input=json.dumps(entrada), capture_output=True,
                       text=True, encoding="utf-8", check=False)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_px_y_cad_ida_y_vuelta():
    ida = js("const p = E.cadAPx(entrada, 4736059.0, 2234186.0); return [p, E.pxACad(entrada, p[0], p[1])];",
             M)
    assert ida[1] == pytest.approx([4736059.0, 2234186.0], abs=1e-6)
    x0, y1 = a_cad(10, 20)
    caja = js("return E.cajaAPx(entrada[0], entrada[1]);", [M, [x0, y1 - 0.5, x0 + 0.67, y1]])
    assert caja["x"] == pytest.approx(10, abs=1e-3) and caja["y"] == pytest.approx(20, abs=1e-3)
    assert caja["ancho"] == pytest.approx(0.67 * M[0], abs=1e-3)
    assert caja["alto"] == pytest.approx(0.5 * M[0], abs=1e-3)


def test_zona_desde_arrastre():
    """Los dos puntos ya vienen en coordenadas del dibujo (a cualquier zoom); el tamaño en
    pantalla decide si fue un clic."""
    r = js("return [E.zonaDesdeArrastre([10.12345, 5.5], [2.0004, 8.25], [[0, 0], [300, 200]]),"
           " E.zonaDesdeArrastre([10, 5], [2, 8], [[100, 100], [102, 400]]),"
           " E.zonaDesdeArrastre([10, 5], [2, 8], null)];")
    assert r[0] == [2.0, 5.5, 10.123, 8.25]  # normalizada aunque se arrastre al revés, a milésimas
    assert r[1] is None  # 2 px de pantalla de ancho: un clic, no una zona
    assert r[2] == [2, 5, 10, 8]


def test_camara_encuadrar_zoom_y_desplazar():
    # Encuadrar una caja 10 × 4 en un visor 2:1 con 5 % de aire: 11 de ancho → 5,5 de alto.
    c = js("return E.encuadrar([0, 0, 10, 4], 2);")
    assert c == pytest.approx([-0.5, -0.75, 10.5, 4.75])
    assert (c[2] - c[0]) / (c[3] - c[1]) == pytest.approx(2)
    alto = js("return E.encuadrar([0, 0, 2, 10], 2, 0);")
    assert alto == pytest.approx([-9, 0, 11, 10])
    # El zoom deja el punto del cursor en su lugar: en la misma fracción de la ventana.
    antes = [0, 0, 100, 50]
    p = [25, 40]
    despues = js("const [c, p] = entrada; return E.zoomEnPunto(c, p, 0.5);", [antes, p])
    assert despues == pytest.approx([12.5, 20, 62.5, 45])
    fx = lambda c: ((p[0] - c[0]) / (c[2] - c[0]), (p[1] - c[1]) / (c[3] - c[1]))
    assert fx(despues) == pytest.approx(fx(antes))
    assert js("return E.desplazar([0, 0, 10, 5], 3, -2);") == [3, -2, 13, 3]
    # Rueda: ±100 (un clic) es ×1,25 / ÷1,25; limitado a [0,5; 2].
    assert js("return [100, -100, 0, 5000, -5000].map(E.factorRueda);") == pytest.approx(
        [1.25, 0.8, 1, 2, 0.5])


def test_necesita_vista_nitida():
    m = [10.0, 0, 0, -10.0, 0, 500.0]  # imagen 1000 × 500 px de [0, 0, 100, 50]
    assert js("return E.cajaDeImagen(entrada, [1000, 500]);", m) == pytest.approx([0, 0, 100, 50])
    casos = js("""const m = entrada; return [
      E.necesitaVistaNitida(m, [1000, 500], [0, 0, 100, 50], 1000),     // la misma: no
      E.necesitaVistaNitida(m, [1000, 500], [40, 20, 60, 30], 1000),    // acercado: pixelada
      E.necesitaVistaNitida(m, [1000, 500], [-50, 0, 150, 50], 1000),   // alejado: no la cubre
      E.necesitaVistaNitida(m, [1000, 500], [-50, 0, 150, 50], 1000, [0, 0, 100, 50]), // pero no hay más dibujo
      E.necesitaVistaNitida(m, [1000, 500], [500, 500, 600, 550], 1000, [0, 0, 100, 50]), // fuera del dibujo
      E.necesitaVistaNitida(m, [1000, 500], [10, 10, 90, 40], 1000)];   // un poco acercado: aguanta
    """, m)
    assert casos == [False, True, True, False, False, False]
    assert js("return [E.interseccion([0, 0, 10, 10], [5, 5, 20, 20]),"
              " E.interseccion([0, 0, 1, 1], [2, 2, 3, 3])];") == [[5, 5, 10, 10], None]


def test_grupo_en_punto_elige_el_mas_chico():
    grupos = [{"numero": 1, "caja": [0, 0, 100, 100], "entidades": 900},
              {"numero": 2, "caja": [10, 10, 20, 20], "entidades": 5}]
    m = [10.0, 0, 0, -10.0, 0, 1000.0]  # 1 unidad = 10 px
    r = js("const [m, g] = entrada; return [E.grupoEnPunto(m, g, [150, 850]),"
           " E.grupoEnPunto(m, g, [500, 500]), E.grupoEnPunto(m, g, [5000, 5000])];", [m, grupos])
    assert [x and x["numero"] for x in r] == [2, 1, None]
    # Fuera de todos: el más cercano dentro de la tolerancia (grupos-punto lejanos entre sí).
    cerca = js("const [m, g] = entrada; return [E.grupoEnPunto(m, g, [1030, 1000], 40),"
               " E.grupoEnPunto(m, g, [1030, 1000], 20), E.grupoEnPunto(m, g, [1030, 1000])];",
               [m, grupos])
    assert [x and x["numero"] for x in cerca] == [1, None, None]


def test_tamano_en_hoja_igual_que_python():
    zona = [100.0, 200.0, 102.0, 201.0]
    for n in (20, 50, 1):
        r = js("const [z, n, a] = entrada; return E.tamanoEnHoja(z, 1000, n, 5, a);", [zona, n, AREA])
        assert r["pagina"] == pytest.approx(pagina_de_zona(zona, 1000.0, n, 5.0))
    cabe = js("return E.tamanoEnHoja([100, 200, 102, 201], 1000, 50, 5, entrada);", AREA)
    assert cabe["cabe"] is True and cabe["aviso"] is None
    assert cabe["texto"] == ("Dibujo 40,0 × 20,0 mm; página 50,0 × 30,0 mm (con márgenes de 5,0 mm).")
    no = js("return E.tamanoEnHoja([100, 200, 102, 201], 1000, 2, 5, entrada);", AREA)
    assert no["cabe"] is False
    assert no["aviso"].startswith("No cabe en el área de dibujo del A1 (639,7 × 548,6 mm): sobran ")
    assert "Pruebe 1:5" in no["aviso"]
    assert js("return E.escalaSugerida([0, 0, 30, 20], 1000, 5, entrada);", AREA) == 50


def test_filtro_de_capas():
    todas = ["0", "COTAS", "TEXTO", "_001_ACERO"]
    r = js("const t = entrada; return ["
           " E.filtroCapas('excluir', t, new Set()),"
           " E.filtroCapas('excluir', t, new Set(['COTAS', 'TEXTO'])),"
           " E.filtroCapas('solo', t, new Set(['COTAS', 'TEXTO'])),"
           " E.filtroCapas('solo', t, new Set(t)),"
           " E.filtroCapas('otro', t, new Set())];", todas)
    assert r[0] == {"excluir": None, "capas": None}  # todas marcadas: sin filtro
    assert r[1] == {"excluir": ["COTAS", "TEXTO"], "capas": None}
    assert r[2] == {"capas": ["0", "_001_ACERO"], "excluir": None}
    assert "Marque al menos una capa" in r[3]["error"]
    assert "error" in r[4]
    textos = js("return entrada.map(E.textoFiltro);", r[:3])
    assert textos == ["todas las capas", "todas las capas menos 2", "solo 2 capas"]


def test_ordenar_capas_y_estado_cad():
    filas = [{"nombre": "B", "entidades": 0, "estado_cad": None, "se_ve": True},
             {"nombre": "A", "entidades": 3, "estado_cad": None, "se_ve": True},
             {"nombre": "C", "entidades": 9, "estado_cad": "apagada", "se_ve": False}]
    r = js("return [E.ordenarCapas(entrada).map((f) => f.nombre), entrada.map(E.textoEstadoCad)];", filas)
    assert r[0] == ["C", "A", "B"]
    assert r[1] == [None, None, "apagada en el CAD: no se dibuja"]


def test_cuerpos_de_los_pedidos():
    previa = js("return [E.cuerpoPrevia({}), E.cuerpoPrevia({zona: [1, 2, 3, 4], vista: [0, 0, 5, 5],"
                " filtro: {excluir: ['COTAS'], capas: null}, escala: 50,"
                " estilo: {ctb: null, transparencia: true}})];")
    assert previa[0] == {}  # todo el Model Space
    assert previa[1] == {"zona": [1, 2, 3, 4], "vista": [0, 0, 5, 5], "excluir": ["COTAS"],
                         "escala": 50, "estilo": {"ctb": None, "transparencia": True}}


def test_textos():
    assert js("return [E.textoTranscurrido(5.9), E.textoTranscurrido(65), E.textoTranscurrido(600)];") == [
        "5 s", "1 min 05 s", "10 min 00 s"]
    assert js("return E.textoGrupo({numero: 1, caja: [0, 0, 1, 1], entidades: 16824});") == (
        "Grupo 1 · 16 824 entidades")
    assert js("return E.textoZona([1, 2, 3.5, 4], 'm');") == (
        "X 1,000 a 3,500, Y 2,000 a 4,000 (2,500 × 2,000 m)")


def test_el_editor_generado_trae_las_zonas(detalle, tmp_path):
    """El editor.html generado incrusta los dos JS nuevos (sin URLs externas)."""
    from componedor.editor_html import generar_editor

    formato = Path(componedor.__file__).parents[2] / "formatos" / "A1_ERCO.json"
    salida = generar_editor(detalle.parent, formato, tmp_path / "editor")
    html = Path(salida).read_text(encoding="utf-8")
    assert "window.EditorPanelZonas = { abrir, editar }" in html
    assert "raiz.EditorZonas = api" in html
    assert "@@JS_ZONAS@@" not in html and "@@JS_PANEL_ZONAS@@" not in html


# --- zonas borrador en la hoja (Fase 10e) ---------------------------------------------------

def test_limpiar_nombre_como_python():
    from componedor.nombres_paquete import limpiar

    for texto in ("Sección VF", "Zona_01", "  Poste 1a5 ", "Ñandú (2)", ".oculto", "a/b\\c"):
        r = js("return E.limpiarNombre(entrada);", texto)
        assert r == {"nombre": limpiar(texto.strip())}, texto
    assert "al menos una letra" in js("return E.limpiarNombre(entrada);", "¿?")["error"]
    assert "muy largo" in js("return E.limpiarNombre(entrada);", "x" * 41)["error"]


def _zona(id_, escala, centro, nombre=None, sha="ab", rect=(100.0, 200.0, 102.0, 201.0), **zona):
    return {"id": id_, "escala": escala, "centro": list(centro),
            "bloque": {"dxf": {"sha256": sha, "nombre": "PRGD.dxf", "margen_mm": 5},
                       "nombre": nombre or id_, "handle": None, "tamano_m": [rect[2] - rect[0], rect[3] - rect[1]],
                       "zona": {"rect": list(rect), "capas": zona.get("capas"), "excluir": zona.get("excluir"),
                                "modo": "excluir", "desmarcadas": []}}}


def test_pedidos_de_las_zonas_borrador():
    catalogo = {"dxf": {"sha256": "ab", "nombre": "PRGD.dxf"}, "sesion_activa": True}
    colocaciones = [
        _zona("Zona_01", 50, (300, 300), excluir=["COTAS"]),
        _zona("Zona_02", 2, (300, 300)),  # 2 m a 1:2 = 1000 mm: no cabe
        _zona("Zona_03", 50, (30, 30)),  # se sale del área (página 50 × 30)
        _zona("Seccion", 20, (200.004, 150.996), capas=["0"]),
        {"id": "Viga", "escala": 50, "centro": [100, 100],
         "bloque": {"dxf": {"sha256": "ab"}, "handle": "1A", "tamano_m": [1, 1]}},  # un bloque: no
        {"id": "Detalle", "pos": [0, 0], "detalle": {}},
    ]
    r = js("const [c, cat, a] = entrada; return E.pedidosZonas(c, cat, a, {ctb: null, transparencia: false});",
           [colocaciones, catalogo, AREA])
    assert [p["id"] for p in r["pedidos"]] == ["Zona_01", "Seccion"]
    assert r["pedidos"][0]["cuerpo"] == {
        "zona": [100.0, 200.0, 102.0, 201.0], "escala": 50, "nombre": "Zona_01", "centro_mm": [300, 300],
        "excluir": ["COTAS"], "estilo": {"ctb": None, "transparencia": False}}
    assert r["pedidos"][1]["cuerpo"]["capas"] == ["0"]
    assert r["pedidos"][1]["cuerpo"]["centro_mm"] == [200.0, 151.0]  # a centésimas de mm
    assert {o["id"]: o["motivo"] for o in r["omitidos"]} == {
        "Zona_02": "no cabe a 1:2: cambie la escala", "Zona_03": "se sale del área de dibujo: muévala"}
    # Sin el DXF, con otro o con la sesión vencida: no se exporta ninguna.
    otro = js("const [c, a] = entrada; return [E.pedidosZonas(c, null, a), "
              "E.pedidosZonas(c, {dxf: {sha256: 'cd', nombre: 'PRGD.dxf'}, sesion_activa: true}, a), "
              "E.pedidosZonas(c, {dxf: {sha256: 'ab', nombre: 'PRGD.dxf'}, sesion_activa: false}, a)];",
              [colocaciones[:1], AREA])
    assert [x["pedidos"] for x in otro] == [[], [], []]
    assert "cargue «PRGD.dxf»" in otro[0]["omitidos"][0]["motivo"]
    assert "el DXF cambió" in otro[1]["omitidos"][0]["motivo"]
    assert "vuelva a cargar" in otro[2]["omitidos"][0]["motivo"]


def test_zonas_repetidas_mismo_nombre_y_escala():
    colocaciones = [_zona("A", 50, (0, 0), nombre="Seccion"), _zona("B", 20, (0, 0), nombre="Seccion"),
                    _zona("C", 50, (0, 0), nombre="SECCION"), _zona("D", 50, (0, 0), nombre="Otra")]
    assert js("return E.zonasRepetidas(entrada);", colocaciones) == [["A", "C"]]


def test_los_bloques_no_incluyen_las_zonas():
    import json as _json

    script = (f"const B = require({_json.dumps(str(CARPETA_JS / 'editor_bloques.js'))});"
              "const c = JSON.parse(require('fs').readFileSync(0, 'utf8'));"
              "process.stdout.write(JSON.stringify(B.pedidosExportar(c, {dxf: {sha256: 'ab', nombre: 'x'}, "
              "sesion_activa: true, bloques: []}, [22.7, 22.7, 662.4, 571.3])));")
    r = subprocess.run([NODE, "-e", script], input=_json.dumps([_zona("Zona_01", 50, (300, 300))]),
                       capture_output=True, text=True, encoding="utf-8", check=False)
    assert _json.loads(r.stdout) == {"pedidos": [], "omitidos": []}


# --- la escala del dibujo (textos «ESC 1:N», protocolo 1.3) -------------------------------

def _resp(candidatos, propuesta=None):
    return {"propuesta": propuesta, "candidatos": [
        {"escala": f"1:{n:g}", "n": n, "eje": eje, "veces": veces,
         "fuentes": [{"texto": f"TITULO\nESC 1:{n:g}", "x": 1, "y": 2, "capa": capa}]}
        for n, eje, veces, capa in candidatos]}


def test_analizar_escalas():
    una = js("return E.analizarEscalas(entrada, null);", _resp([(10, None, 1, "TEXTOS")], 10))
    assert una["estado"] == "una" and una["propuesta"]["n"] == 10 and una["excluidas"] == []
    assert una["propuesta"]["fuente"]["capa"] == "TEXTOS"
    varias = js("return E.analizarEscalas(entrada, null);", _resp([(10, None, 11, "T"), (20, None, 5, "T")]))
    assert varias["estado"] == "varias" and [c["etiqueta"] for c in varias["candidatos"]] == ["1:10", "1:20"]
    ejes = js("return E.analizarEscalas(entrada, null);", _resp([(1000, "H", 1, "P"), (100, "V", 1, "P")]))
    assert ejes["estado"] == "varias" and [c["etiqueta"] for c in ejes["candidatos"]] == ["H 1:1000", "V 1:100"]
    # Con la capa del texto excluida: ninguna en lo que se exporta, y el aviso de la excluida.
    nada = js("return E.analizarEscalas(entrada[0], entrada[1]);",
              [_resp([]), _resp([(10, None, 1, "_000_Textos_General")], 10)])
    assert nada["estado"] == "ninguna" and nada["propuesta"] is None
    assert nada["excluidas"] == [{"etiqueta": "1:10", "n": 10, "capa": "_000_Textos_General",
                                  "fuente": {"texto": "TITULO\nESC 1:10", "x": 1, "y": 2,
                                             "capa": "_000_Textos_General"}}]
    # La que está en las dos no es «excluida».
    ambas = js("return E.analizarEscalas(entrada, entrada);", _resp([(10, None, 1, "T")], 10))
    assert ambas["excluidas"] == []
    dos_lineas = "SECCIÓN-PEDESTAL 0.40 X 0.40" + chr(10) + "ESC-1:10"  # un MTEXT de dos líneas
    assert js("return E.textoFuente({texto: entrada});", dos_lineas) == (
        "SECCIÓN-PEDESTAL 0.40 X 0.40 · ESC-1:10")


def test_aviso_de_escala_distinta():
    r = js("return [E.avisoEscala(10, 20), E.avisoEscala(20, 10), E.avisoEscala(25, 10), E.avisoEscala(10, 10),"
           " E.avisoEscala(10, null)];")
    assert r == ["El dibujo está a 1:20 y se exportará a 1:10: los textos saldrán al doble de su tamaño.",
                 "El dibujo está a 1:10 y se exportará a 1:20: los textos saldrán a la mitad de su tamaño.",
                 "El dibujo está a 1:10 y se exportará a 1:25: los textos saldrán a 0,4 veces su tamaño.",
                 None, None]
