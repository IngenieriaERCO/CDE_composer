"""Convenciones (subfase 4.2b): biblioteca de símbolos extraída de un plano, su índice, la
colocación en el rótulo y la verificación. Todo con un plano y una biblioteca SINTÉTICOS
(conftest.crear_plano_con_leyenda), nunca con el plano real de ERCO."""

import json
from dataclasses import replace

import pymupdf
import pytest

from componedor import componer as modulo_componer
from componedor.cli import main
from componedor.componer import PlanoNoComponible, componer_plano
from componedor.formato import cargar_formato
from componedor.plano import leer_plano
from componedor.simbolos import (
    BibliotecaInvalida,
    ExtraccionFallida,
    Simbolo,
    cargar_biblioteca,
    colocar_simbolo,
    extraer_simbolos,
)
from conftest import (
    ARIAL,
    TRAZOS_POR_TIPO,
    casilla_conv,
    crear_paquete_real,
    crear_plano_con_leyenda,
    crear_plantilla_sintetica,
    dibujo_de_tipo,
    escribir_formato,
    requiere_arial,
    rotulo_a1,
)

# 14 símbolos: los 12 de la columna izquierda y 2 de la derecha (para que sobren ids).
TIPOS = ["linea", "relleno", "puntos", "malla", "ancho", "alto", "linea", "relleno", "puntos",
         "malla", "relleno", "linea"]
LEYENDA = {k: t for k, t in enumerate(TIPOS, start=1)} | {13: "malla", 14: "puntos"}
IDS = ["limite", "corte", "via", "panel", "linea_larga", "alto", "limite_2", "relleno",
       "via_2", "panel_2", "relleno_2", "limite_3", "panel_3", "via_3"]


def _formato(carpeta, plantilla=None):
    rotulo = rotulo_a1(fuente={"archivo": str(ARIAL)})
    rotulo["campos"]["convenciones"]["biblioteca"] = str(carpeta / "simbolos" / "indice.json")
    return escribir_formato(carpeta / "formato.json", plantilla=plantilla, rotulo=rotulo)


def _indice_previo(carpeta, ids=IDS, casillas=None):
    casillas = casillas or list(LEYENDA)
    datos = {"version": 1, "simbolos": [
        {"id": i, "descripcion": f"DESCRIPCIÓN {i.upper()}", "casilla_origen": k}
        for i, k in zip(ids, casillas)]}
    (carpeta / "simbolos").mkdir(exist_ok=True)
    (carpeta / "simbolos" / "indice.json").write_text(json.dumps(datos, ensure_ascii=False),
                                                      encoding="utf-8")


@pytest.fixture
def biblioteca(tmp_path):
    """Plano sintético girado 270°, índice previo con ids y la biblioteca extraída."""
    plano = crear_plano_con_leyenda(tmp_path / "plano_con_leyenda.pdf", LEYENDA)
    formato = cargar_formato(_formato(tmp_path), usar_plantilla=False)
    _indice_previo(tmp_path)
    informe = extraer_simbolos(plano, formato, tmp_path / "simbolos" / "indice.json")
    return tmp_path, informe


# --- extraer la biblioteca --------------------------------------------------------------------

def test_extrae_cada_simbolo_como_vector_con_sus_trazos_y_su_caja(biblioteca):
    carpeta, informe = biblioteca
    assert [s.id for s in informe.simbolos] == IDS  # el orden y los ids del índice previo
    assert informe.omitidas == []
    with pymupdf.open(informe.ruta_pdf) as doc:
        assert doc.page_count == 14
        for s, k in zip(informe.simbolos, LEYENDA):
            tipo = LEYENDA[k]
            assert s.trazos == TRAZOS_POR_TIPO[tipo], s.id
            esperado = dibujo_de_tipo(tipo, casilla_conv(k))
            if tipo == "puntos":  # círculos de 0,3 mm de radio dentro de la caja
                esperado = (esperado[0] + 0.2, esperado[1] + 0.2, esperado[2] - 0.2,
                            esperado[3] - 0.2)
            assert s.rect_mm == pytest.approx(esperado, abs=0.1), s.id
            page = doc[s.pagina - 1]
            assert len(page.get_drawings()) == s.trazos  # SOLO el símbolo, nada más
            assert page.get_image_info() == [] and page.get_text().strip() == ""
            ancho, alto = s.tamano_mm
            assert page.rect.width * 25.4 / 72 == pytest.approx(ancho + 1.0, abs=0.01)
            assert page.rect.height * 25.4 / 72 == pytest.approx(alto + 1.0, abs=0.01)
    indice = json.loads((carpeta / "simbolos" / "indice.json").read_text(encoding="utf-8"))
    assert indice["version"] == 1 and indice["biblioteca"] == "convenciones_erco.pdf"
    assert indice["origen"] == {"plano": "plano_con_leyenda.pdf", "pagina": 1, "margen_mm": 0.5}
    assert indice["simbolos"][1] == {"id": "corte", "descripcion": "DESCRIPCIÓN CORTE",
                                     "casilla_origen": 2, "pagina": 2,
                                     "rect_mm": indice["simbolos"][1]["rect_mm"], "trazos": 1}


def test_sin_indice_crea_ids_provisionales_y_avisa_las_omitidas(tmp_path):
    plano = crear_plano_con_leyenda(tmp_path / "p.pdf", {1: "relleno", 3: "malla", 13: "linea"},
                                    rotacion=0)
    formato = cargar_formato(_formato(tmp_path), usar_plantilla=False)
    informe = extraer_simbolos(plano, formato, tmp_path / "simbolos" / "indice.json")
    assert [s.id for s in informe.simbolos] == ["simbolo_01", "simbolo_03", "simbolo_13"]
    _indice_previo(tmp_path, ids=["solo_uno"], casillas=[3])  # el 1 y el 13 quedan afuera
    informe = extraer_simbolos(plano, formato, tmp_path / "simbolos" / "indice.json")
    assert [s.id for s in informe.simbolos] == ["solo_uno"] and informe.omitidas == [1, 13]


def test_extraccion_con_errores_claros(tmp_path):
    plano = crear_plano_con_leyenda(tmp_path / "p.pdf", {1: "relleno"})
    formato = cargar_formato(_formato(tmp_path), usar_plantilla=False)
    _indice_previo(tmp_path, ids=["corte", "vacio"], casillas=[1, 5])
    with pytest.raises(ExtraccionFallida, match=r"no hay dibujo en la casilla de origen de: "
                                                r"'vacio' \(casilla 5\)"):
        extraer_simbolos(plano, formato, tmp_path / "simbolos" / "indice.json")
    _indice_previo(tmp_path, ids=["corte", "corte"], casillas=[1, 1])
    with pytest.raises(ExtraccionFallida, match="repite ids: corte"):
        extraer_simbolos(plano, formato, tmp_path / "simbolos" / "indice.json")
    pequeno = pymupdf.open()
    pequeno.new_page(width=595, height=842)
    pequeno.save(tmp_path / "a4.pdf")
    with pytest.raises(ExtraccionFallida, match="mide 209.90 x 297.04 mm y la hoja del formato"):
        extraer_simbolos(tmp_path / "a4.pdf", formato, tmp_path / "otro" / "indice.json")
    with pytest.raises(ExtraccionFallida, match="no existe la página 3"):
        extraer_simbolos(plano, formato, tmp_path / "otro" / "indice.json", pagina=3)


def test_cli_extraer_simbolos(tmp_path, capsys):
    plano = crear_plano_con_leyenda(tmp_path / "p.pdf", {1: "relleno", 2: "malla"})
    ruta_formato = _formato(tmp_path)
    _indice_previo(tmp_path, ids=["corte", "panel"], casillas=[1, 2])
    assert main(["extraer-simbolos", str(plano), "--formato", str(ruta_formato)]) == 0
    out = capsys.readouterr().out
    assert "2 símbolo(s), uno por página" in out and "corte" in out and "panel" in out
    assert "misma caja (±0,1 mm)" in out and "no se versiona" in out
    assert main(["extraer-simbolos", str(tmp_path / "no.pdf"), "--formato",
                 str(ruta_formato)]) == 1
    assert "No se encontró el plano" in capsys.readouterr().err


# --- leer la biblioteca ----------------------------------------------------------------------

def test_biblioteca_ausente_o_incompleta_dice_que_falta_y_como_generarla(tmp_path, biblioteca):
    carpeta, _ = biblioteca
    with pytest.raises(BibliotecaInvalida, match=r"no se encontró el índice de símbolos .*"
                                                 r"extraer-simbolos <plano.pdf>"):
        cargar_biblioteca(tmp_path / "nada" / "indice.json")
    (carpeta / "simbolos" / "convenciones_erco.pdf").unlink()
    with pytest.raises(BibliotecaInvalida, match=r"no se encontró la biblioteca de símbolos .*"
                                                 r"no se versiona\)\. Genérela con"):
        cargar_biblioteca(carpeta / "simbolos" / "indice.json")
    _indice_previo(carpeta)  # sin medir
    with pytest.raises(BibliotecaInvalida, match="hay símbolos sin medir"):
        cargar_biblioteca(carpeta / "simbolos" / "indice.json")


# --- colocar ---------------------------------------------------------------------------------

def test_colocar_centrado_sin_agrandar_y_reducido_si_no_cabe():
    casilla = (672.4, 249.39, 693.84, 259.88)  # 21,44 x 10,49 -> útil 20,24 x 9,29
    chico = Simbolo("s", "", 1, 1, (0.0, 0.0, 6.0, 3.0), 1)
    c = colocar_simbolo(chico, 1, casilla, 0.6, 0.5)
    assert c.escala == 1.0  # nunca se agranda
    assert c.destino_dibujo == pytest.approx((680.12, 253.135, 686.12, 256.135))
    assert c.destino_pagina == pytest.approx((679.62, 252.635, 686.62, 256.635))
    ancho = Simbolo("a", "", 1, 1, (0.0, 0.0, 21.0, 0.0), 1)
    c = colocar_simbolo(ancho, 1, casilla, 0.6, 0.5)
    assert c.escala == pytest.approx(20.24 / 21.0)
    assert c.destino_dibujo[2] - c.destino_dibujo[0] == pytest.approx(20.24)


# --- en el plano --------------------------------------------------------------------------------

@pytest.fixture
def entorno(biblioteca):
    carpeta, _ = biblioteca
    plantilla = crear_plantilla_sintetica(carpeta / "rotulo.pdf")
    _formato(carpeta, plantilla)
    crear_paquete_real(carpeta / "input", "a")
    return carpeta


def _plano(carpeta, convenciones):
    datos = {"version": 2, "formato": "formato.json",
             "detalles": [{"id": "d1", "manifiesto": "input/a.manifest.json",
                           "posicion_mm": [40, 300]}],
             "rotulo": {"convenciones": convenciones}}
    (carpeta / "plano.json").write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    return leer_plano(carpeta / "plano.json")


def _trazos_en(ruta, rect):
    k = 72 / 25.4
    caja = pymupdf.Rect(rect[0] * k - 0.3, (594 - rect[3]) * k - 0.3, rect[2] * k + 0.3,
                        (594 - rect[1]) * k + 0.3)
    with pymupdf.open(ruta) as doc:
        return sum(caja.contains(d["rect"]) for d in doc[0].get_drawings())


@requiere_arial
def test_llenado_por_columna_y_desborde_a_la_derecha(entorno):
    # 13 convenciones: 12 en la columna izquierda (de arriba abajo) y la 13.ª arriba a la derecha.
    convenciones = [{"simbolo": i} for i in IDS[:13] if i != "linea_larga"] + [{"simbolo": "via_3"}]
    r = componer_plano(_plano(entorno, convenciones), entorno / "p.pdf")
    assert [c.posicion for c in r.simbolos] == list(range(1, 14))
    assert [c.simbolo.id for c in r.simbolos] == [c["simbolo"] for c in convenciones]
    assert r.simbolos[12].casilla == casilla_conv(13)  # la 13.ª pasó a la columna derecha
    for c in r.simbolos:
        assert _trazos_en(entorno / "p.pdf", c.casilla) == c.simbolo.trazos
    with pymupdf.open(entorno / "p.pdf") as doc:
        texto = doc[0].get_text()
    assert "DESCRIPCIÓN CORTE" in texto and "DESCRIPCIÓN VIA_3" in texto
    assert r.advertencias == []


@requiere_arial
def test_descripcion_propia_y_simbolo_reducido_con_advertencia(entorno):
    convenciones = [{"simbolo": "linea_larga", "descripcion": "VÍA SUÁREZ – LA GLORIA"},
                    {"simbolo": "corte"}]
    r = componer_plano(_plano(entorno, convenciones), entorno / "p.pdf")
    reducido = r.simbolos[0]
    assert reducido.escala == pytest.approx(20.24 / 21.0, abs=0.001)
    assert r.advertencias == [
        f"Advertencia: en las convenciones, el símbolo 'linea_larga' (casilla 1) se redujo al "
        f"{reducido.escala * 100:.1f} % para caber en su casilla (dibujo 21.00 x 0.00 mm; espacio "
        f"útil 20.24 x 9.29 mm)."]
    assert r.simbolos[1].escala == 1.0
    with pymupdf.open(entorno / "p.pdf") as doc:
        assert "VÍA SUÁREZ – LA GLORIA" in doc[0].get_text()


@requiere_arial
def test_simbolo_alto_cabe_arriba_y_se_reduce_en_las_filas_bajas(entorno):
    relleno = [{"simbolo": i} for i in ["limite", "corte", "via", "panel", "relleno", "via_2",
                                        "panel_2", "relleno_2"]]
    arriba = componer_plano(_plano(entorno, [{"simbolo": "alto"}]), entorno / "p.pdf")
    assert arriba.simbolos[0].escala == 1.0
    abajo = componer_plano(_plano(entorno, relleno + [{"simbolo": "limite_2"}, {"simbolo": "alto"}]),
                           entorno / "p.pdf", sobrescribir=True)
    alto = abajo.simbolos[-1]
    assert alto.posicion == 10 and alto.escala < 1
    assert any("'alto' (casilla 10) se redujo" in a for a in abajo.advertencias)


@requiere_arial
def test_todos_los_problemas_juntos(entorno):
    convenciones = ([{"simbolo": "corte"}, {"simbolo": "corte"}, {"simbolo": "no_existe"},
                     {"simbolo": "via", "color": "rojo"}, {"simbolo": "panel", "descripcion": "中"},
                     "corte"] + [{"simbolo": f"x{i}"} for i in range(19)])
    with pytest.raises(PlanoNoComponible) as e:
        componer_plano(_plano(entorno, convenciones), entorno / "p.pdf")
    m = str(e.value)
    assert "- rotulo.convenciones: hay 25 convenciones y la tabla admite 24 (dos columnas de 12)" in m
    assert "- rotulo.convenciones[1].simbolo: 'corte' está repetido (ya está en " \
           "rotulo.convenciones[0])" in m
    assert ("- rotulo.convenciones[2].simbolo: texto 'no_existe' no está en la biblioteca "
            "(símbolos válidos: limite, corte, via, panel,") in m
    assert "- rotulo.convenciones[3].color: campo no reconocido" in m
    assert "- campo 'convenciones.5.descripcion': la fuente Arial" in m
    assert "- rotulo.convenciones[5]: se esperaba un objeto" in m
    assert not (entorno / "p.pdf").exists()


@requiere_arial
def test_biblioteca_ausente_al_componer(entorno):
    (entorno / "simbolos" / "convenciones_erco.pdf").unlink()
    with pytest.raises(PlanoNoComponible, match=r"rotulo.convenciones: no se encontró la "
                                                r"biblioteca de símbolos .* Genérela con: python "
                                                r"-m componedor.cli extraer-simbolos"):
        componer_plano(_plano(entorno, [{"simbolo": "corte"}]), entorno / "p.pdf")
    # Sin convenciones en el plano, la biblioteca no hace falta.
    componer_plano(_plano(entorno, []), entorno / "p.pdf")


@requiere_arial
def test_descripcion_que_no_cabe_error_con_campo_texto_y_tamano(entorno):
    larga = "DESCRIPCIÓN EXCESIVAMENTE LARGA " * 6
    with pytest.raises(PlanoNoComponible, match=r"campo 'convenciones.1.descripcion': «.*» "
                                                r"necesita \d+ líneas de hasta 55.3 mm y la "
                                                r"celda permite 2 \(altura 1.5 mm"):
        componer_plano(_plano(entorno, [{"simbolo": "corte", "descripcion": larga}]),
                       entorno / "p.pdf")


@requiere_arial
def test_falla_forzada_de_la_verificacion_sin_pdf(entorno, monkeypatch):
    # El símbolo se dibuja 0,3 mm a la derecha de donde debía: la verificación lo detecta.
    original = modulo_componer.dibujar_simbolos

    def corrido(page, colocaciones, biblioteca, alto):
        movidas = [replace(c, destino_pagina=(c.destino_pagina[0] + 0.3, c.destino_pagina[1],
                                              c.destino_pagina[2] + 0.3, c.destino_pagina[3]))
                   for c in colocaciones]
        return original(page, movidas, biblioteca, alto)

    monkeypatch.setattr(modulo_componer, "dibujar_simbolos", corrido)
    with pytest.raises(PlanoNoComponible) as e:
        componer_plano(_plano(entorno, [{"simbolo": "corte"}]), entorno / "p.pdf")
    m = str(e.value)
    assert m.startswith("La verificación del PDF compuesto falló; no se generó el plano:")
    assert "- convenciones, casilla 1 ('corte'): el símbolo quedó en X " in m
    assert "(diferencia máx. 0.300 mm, tolerancia ±0.1 mm)" in m
    assert not (entorno / "p.pdf").exists() and not list(entorno.glob(".*.componiendo.pdf"))


@requiere_arial
def test_cli_resume_las_convenciones(entorno, capsys):
    _plano(entorno, [{"simbolo": "corte"}, {"simbolo": "linea_larga"}])
    assert main(["componer", str(entorno / "plano.json"), "--salida", str(entorno / "p.pdf")]) == 0
    out = capsys.readouterr().out
    assert "Convenciones: 2 símbolo(s): 1 a escala 1:1, 1 reducido(s) (linea_larga al 96.4 %)." in out


# --- opacidad por símbolo (subfase 4.2c) -------------------------------------------------------

def _con_opacidad_en_indice(carpeta, ident, opacidad):
    ruta = carpeta / "simbolos" / "indice.json"
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    for s in datos["simbolos"]:
        if s["id"] == ident:
            s["opacidad"] = opacidad
    ruta.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")


def test_opacidad_se_lee_se_valida_y_extraer_la_conserva(biblioteca):
    carpeta, _ = biblioteca
    ruta = carpeta / "simbolos" / "indice.json"
    _con_opacidad_en_indice(carpeta, "limite_2", 0.5)
    b = cargar_biblioteca(ruta)
    assert b.simbolos["limite_2"].opacidad == 0.5 and b.simbolos["corte"].opacidad == 1.0
    # Regenerar la biblioteca no la pierde.
    formato = cargar_formato(carpeta / "formato.json", usar_plantilla=False)
    extraer_simbolos(carpeta / "plano_con_leyenda.pdf", formato, ruta)
    escrito = {s["id"]: s for s in json.loads(ruta.read_text(encoding="utf-8"))["simbolos"]}
    assert escrito["limite_2"]["opacidad"] == 0.5 and "opacidad" not in escrito["corte"]
    for malo in (0, 1.5, "media", True):
        _con_opacidad_en_indice(carpeta, "limite_2", malo)
        with pytest.raises(BibliotecaInvalida, match=r"la opacidad del símbolo 'limite_2' debe "
                                                     r"ser un número mayor que 0 y hasta 1"):
            cargar_biblioteca(ruta)
    with pytest.raises(ExtraccionFallida, match="la opacidad del símbolo 'limite_2'"):
        extraer_simbolos(carpeta / "plano_con_leyenda.pdf", formato, ruta)


@requiere_arial
def test_opacidad_al_colocar_vector_y_mismos_trazos(entorno):
    _con_opacidad_en_indice(entorno, "corte", 0.5)  # relleno naranja con borde
    r = componer_plano(_plano(entorno, [{"simbolo": "corte"}, {"simbolo": "panel"}]),
                       entorno / "p.pdf")
    assert [c.simbolo.opacidad for c in r.simbolos] == [0.5, 1.0]
    k = 72 / 25.4
    with pymupdf.open(entorno / "p.pdf") as doc:
        page = doc[0]
        assert len(page.get_image_info()) == 1  # solo el logo: nada rasterizado
        def en(casilla):
            c = pymupdf.Rect(casilla[0] * k - 0.3, (594 - casilla[3]) * k - 0.3,
                             casilla[2] * k + 0.3, (594 - casilla[1]) * k + 0.3)
            return [d for d in page.get_drawings() if c.contains(d["rect"])]
        corte, panel = en(casilla_conv(1)), en(casilla_conv(2))
    assert len(corte) == TRAZOS_POR_TIPO["relleno"] and len(panel) == TRAZOS_POR_TIPO["malla"]
    assert all(d["fill_opacity"] == pytest.approx(0.5) and d["stroke_opacity"] == pytest.approx(0.5)
               for d in corte)
    assert corte[0]["fill"] == pytest.approx((1, 0.55, 0.1), abs=0.01)  # mismo color
    assert all(d.get("stroke_opacity", 1) == pytest.approx(1) for d in panel)  # el otro, opaco


@requiere_arial
def test_falla_forzada_si_la_opacidad_no_se_aplica(entorno, monkeypatch):
    from componedor import simbolos as modulo_simbolos
    _con_opacidad_en_indice(entorno, "corte", 0.5)

    def sin_opacidad(doc, pagina, opacidad):  # copia la página tal cual, opaca
        nuevo = pymupdf.open()
        nuevo.insert_pdf(doc, from_page=pagina, to_page=pagina)
        return nuevo

    monkeypatch.setattr(modulo_simbolos, "con_opacidad", sin_opacidad)
    with pytest.raises(PlanoNoComponible, match=r"convenciones, casilla 1 \('corte'\): el símbolo "
                                                r"debía tener opacidad 0.5 y en el PDF tiene 1"):
        componer_plano(_plano(entorno, [{"simbolo": "corte"}]), entorno / "p.pdf")
    assert not (entorno / "p.pdf").exists()
