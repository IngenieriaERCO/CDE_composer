"""Zonas del Model Space en el plano.json del editor (Fase 10e3, versión 6) y «Volver a exportar
zonas» (10e4), en Node: lo que escribe el editor lo lee Python, y al abrirlo reaparecen los
borradores y las zonas exportadas recuerdan su zona."""

import json

from test_editor_bloques_js import CATALOGO, SHA, entorno_editor, js  # noqa: F401 (fixture)

from componedor.plano import leer_plano

RECT = [4736058.98, 2234185.8, 4736059.65, 2234186.45]


def borrador(nombre, escala, centro, excluir=None, capas=None):
    zona = {"rect": RECT, "capas": capas, "excluir": excluir, "modo": "solo" if capas else "excluir",
            "desmarcadas": list(excluir or [])}
    return {"id": nombre, "escala": escala, "centro": list(centro),
            "bloque": {"nombre": nombre, "etiqueta": nombre, "handle": None, "ocurrencia": 1,
                       "total_ocurrencias": 1, "tamano_m": [0.67, 0.65], "caja_exacta": True, "zona": zona}}


def guardar(datos, colocados, exportada=None):
    """serializarPlano con borradores (y, si `exportada`, el detalle «a» del catálogo exportado
    desde la zona `exportada`)."""
    return js("""
      const dxf = B.entradaDxf(entrada.catalogo);
      const cs = entrada.colocados.map((c) => Object.assign(c, {bloque: Object.assign(c.bloque, {dxf})}));
      if (entrada.exportada) {
        const detalle = entrada.datos.detalles[0];
        cs.unshift({id: entrada.exportada, detalle, pos: [100, 120],
          zona: {nombre: entrada.exportada, rect: entrada.rect, capas: null, excluir: ["EDD_COTAS"],
                 modo: "excluir", desmarcadas: ["EDD_COTAS"], tamano_m: [0.67, 0.65], dxf}});
      }
      return L.serializarPlano(cs, entrada.datos);""",
              {"catalogo": CATALOGO, "datos": datos, "colocados": colocados, "exportada": exportada,
               "rect": RECT})


def test_el_editor_escribe_la_version_6_y_python_la_lee(entorno_editor):  # noqa: F811
    carpeta, datos = entorno_editor
    texto = guardar(datos, [borrador("Zona_02", 10, (520, 180), excluir=["EDD_COTAS"]),
                            borrador("Seccion", 50, (300.004, 200), capas=["0", "_001_*"])],
                    exportada="Zona_01")
    plano = json.loads(texto)
    assert plano["version"] == 6
    pagina = datos["detalles"][0]["tamano_pagina_mm"]
    assert plano["dxf"][0]["zonas"] == [
        {"nombre": "Zona_01", "zona": RECT, "capas": None, "excluir": ["EDD_COTAS"],
         "escala": "1:" + str(int(datos["detalles"][0]["escala"])),
         "centro_mm": [round(100 + pagina[0] / 2, 2), round(120 + pagina[1] / 2, 2)], "tamano_m": [0.67, 0.65]},
        {"nombre": "Zona_02", "zona": RECT, "capas": None, "excluir": ["EDD_COTAS"], "escala": "1:10",
         "centro_mm": [520, 180], "tamano_m": [0.67, 0.65]},
        {"nombre": "Seccion", "zona": RECT, "capas": ["0", "_001_*"], "excluir": None, "escala": "1:50",
         "centro_mm": [300.0, 200], "tamano_m": [0.67, 0.65]}]
    # Solo el exportado es un detalle (con su origen); los borradores no.
    assert [d["id"] for d in plano["detalles"]] == ["Zona_01"]
    assert plano["detalles"][0]["origen"] == {"zona": "Zona_01"}
    ruta = carpeta / "editor" / "plano.json"
    ruta.write_text(texto, encoding="utf-8")
    leido = leer_plano(ruta)
    assert leido.version == 6 and leido.detalles[0].zona == "Zona_01"
    assert [z.nombre for z in leido.borradores] == ["Zona_02", "Seccion"]
    assert leido.borradores[1].capas == ("0", "_001_*")


def test_solo_borradores_y_abrirlo_otra_vez(entorno_editor):  # noqa: F811
    """Un plano con solo zonas borrador (sin detalles todavía) se guarda y se abre: vuelven a
    la hoja con su nombre, rectángulo, capas, escala y centro."""
    carpeta, datos = entorno_editor
    texto = guardar(datos, [borrador("Zona_01", 20, (342.55, 297.0), excluir=["EDD_COTAS"])])
    assert json.loads(texto)["detalles"] == []
    ruta = carpeta / "editor" / "plano.json"
    ruta.write_text(texto, encoding="utf-8")
    assert [z.nombre for z in leer_plano(ruta).borradores] == ["Zona_01"]
    r = js("""const l = L.leerPlano(entrada.texto, entrada.datos);
      return {errores: l.errores, c: l.colocaciones.map((c) => ({id: c.id, escala: c.escala, centro: c.centro,
        zona: c.bloque.zona, nombre: c.bloque.nombre, handle: c.bloque.handle, tamano: c.bloque.tamano_m,
        dxf: c.bloque.dxf.sha256}))};""", {"texto": texto, "datos": datos})
    assert r["errores"] == []
    assert r["c"] == [{"id": "Zona_01", "escala": 20, "centro": [342.55, 297.0], "nombre": "Zona_01",
                       "handle": None, "tamano": [0.67, 0.65], "dxf": SHA,
                       "zona": {"rect": RECT, "capas": None, "excluir": ["EDD_COTAS"], "modo": "excluir",
                                "desmarcadas": ["EDD_COTAS"], "escala_dibujo": None}}]


def test_abrir_un_plano_con_una_zona_exportada_y_guardarlo_igual(entorno_editor):  # noqa: F811
    _, datos = entorno_editor
    texto = guardar(datos, [borrador("Zona_02", 10, (520, 180))], exportada="Zona_01")
    r = js("""const l = L.leerPlano(entrada.texto, entrada.datos);
      const otra = L.serializarPlano(l.colocaciones, entrada.datos, {original: l.original});
      const e = l.colocaciones[0];
      return {errores: l.errores, ids: l.colocaciones.map((c) => c.id),
        exportada: {detalle: !!e.detalle, zona: e.zona.nombre, rect: e.zona.rect, dxf: e.zona.dxf.sha256},
        borrador: !!l.colocaciones[1].bloque.zona, igual: otra === entrada.texto};""",
           {"texto": texto, "datos": datos})
    assert r["errores"] == [] and r["ids"] == ["Zona_01", "Zona_02"]
    assert r["exportada"] == {"detalle": True, "zona": "Zona_01", "rect": RECT, "dxf": SHA}
    assert r["borrador"] is True
    assert r["igual"] is True  # abrir y guardar sin tocar nada da el mismo JSON


def test_planos_mal_escritos_y_viejos(entorno_editor):  # noqa: F811
    _, datos = entorno_editor
    dxf = {"id": "d1", "archivo": "a.dxf", "sha256": SHA, "margen_mm": 5}
    zona = {"nombre": "Z", "zona": RECT, "capas": None, "excluir": None, "escala": "1:20",
            "centro_mm": [300, 200], "tamano_m": [0.67, 0.65]}
    planos = {
        "zonas_en_v5": {"version": 5, "dxf": [{**dxf, "zonas": [zona]}], "detalles": []},
        "origen_desconocido": {"version": 6, "dxf": [{**dxf, "zonas": [zona]}], "detalles": [
            {"id": "a", "manifiesto": datos["detalles"][0]["manifiesto"], "posicion_mm": [30, 40],
             "origen": {"zona": "NO"}}]},
        "capas_y_excluir": {"version": 6, "dxf": [{**dxf, "zonas": [{**zona, "capas": ["0"], "excluir": ["x"]}]}],
                            "detalles": []},
        "viejo_v3": {"version": 3, "dxf": [dxf], "detalles": [
            {"id": "a", "manifiesto": datos["detalles"][0]["manifiesto"], "posicion_mm": [30, 40]}]},
    }
    r = js("""const res = {};
      for (const [k, p] of Object.entries(entrada.planos)) {
        const l = L.leerPlano(JSON.stringify(p), entrada.datos);
        res[k] = {errores: l.errores, n: l.colocaciones.length};
      }
      return res;""", {"planos": planos, "datos": datos})
    assert "dxf[0].zonas: solo existe en la versión 6 del plano" in r["zonas_en_v5"]["errores"][0]
    assert "origen: se esperaba {\"zona\"" in r["origen_desconocido"]["errores"][0]
    assert "lleva «capas» y «excluir» a la vez" in r["capas_y_excluir"]["errores"][0]
    assert r["viejo_v3"] == {"errores": [], "n": 1}  # los planos viejos abren igual


def test_volver_a_exportar_incluye_las_zonas_exportadas(entorno_editor):  # noqa: F811
    _, datos = entorno_editor
    catalogo = {"dxf": {"sha256": SHA, "nombre": "GUAMO_prueba.dxf"}, "sesion_activa": True}
    r = js("""
      const dxf = {sha256: entrada.sha, nombre: "GUAMO_prueba.dxf", margen_mm: 5};
      const detalle = entrada.datos.detalles[0];
      const cs = [
        {id: "Zona_01", detalle, pos: [100, 120], zona: {nombre: "Zona_01", rect: entrada.rect, capas: null,
          excluir: ["EDD_COTAS"], tamano_m: [0.67, 0.65], dxf}},
        {id: "Zona_02", escala: 10, centro: [520, 180], bloque: {nombre: "Zona_02", dxf, tamano_m: [0.67, 0.65],
          zona: {rect: entrada.rect, capas: ["0"], excluir: null}}},
        {id: "otro", detalle, pos: [10, 10]}];
      const E = require(entrada.zonas);
      return [E.pedidosZonas(cs, entrada.catalogo, [22.7, 22.7, 662.4, 571.3], null),
              E.pedidosZonas(cs, entrada.catalogo, [22.7, 22.7, 662.4, 571.3], null, true), detalle];""",
           {"sha": SHA, "datos": datos, "rect": RECT, "catalogo": catalogo,
            "zonas": str(__import__("componedor").__path__[0] + "/editor/editor_zonas.js")})
    solo_borradores, todas, detalle = r
    assert [p["id"] for p in solo_borradores["pedidos"]] == ["Zona_02"]
    assert [p["id"] for p in todas["pedidos"]] == ["Zona_01", "Zona_02"]
    t = detalle["tamano_pagina_mm"]
    # La exportada: con la escala de su detalle y el centro de su página de hoy.
    assert todas["pedidos"][0]["cuerpo"] == {
        "zona": RECT, "escala": round(detalle["escala"]), "nombre": "Zona_01",
        "centro_mm": [round(100 + t[0] / 2, 2), round(120 + t[1] / 2, 2)], "excluir": ["EDD_COTAS"]}


def test_escala_del_dibujo_se_guarda_y_se_lee(entorno_editor):  # noqa: F811
    carpeta, datos = entorno_editor
    b = borrador("Zona_01", 10, (342.55, 297.0))
    b["bloque"]["zona"]["escala_dibujo"] = 20
    texto = guardar(datos, [b])
    assert json.loads(texto)["dxf"][0]["zonas"][0]["escala_dibujo"] == "1:20"
    ruta = carpeta / "editor" / "plano.json"
    ruta.write_text(texto, encoding="utf-8")
    assert leer_plano(ruta).zonas[0].escala_dibujo == 20.0
    r = js("const l = L.leerPlano(entrada.texto, entrada.datos); return [l.errores, l.colocaciones[0].bloque.zona.escala_dibujo];",
           {"texto": texto, "datos": datos})
    assert r == [[], 20]


def test_mostrar_escala_de_un_borrador(entorno_editor):  # noqa: F811
    """«Mostrar escala» desmarcado en una zona borrador: se guarda (etiqueta_escala: false),
    Python lo lee y al abrir vuelve desmarcado; marcado no escribe nada."""
    carpeta, datos = entorno_editor
    oculta = borrador("Zona_01", 10, (342.55, 297.0))
    oculta["etiqueta_escala"] = False
    texto = guardar(datos, [oculta, borrador("Zona_02", 20, (520, 180))])
    zonas = json.loads(texto)["dxf"][0]["zonas"]
    assert zonas[0]["etiqueta_escala"] is False and "etiqueta_escala" not in zonas[1]
    ruta = carpeta / "editor" / "plano.json"
    ruta.write_text(texto, encoding="utf-8")
    assert [z.etiqueta_escala for z in leer_plano(ruta).zonas] == [False, True]
    r = js("const l = L.leerPlano(entrada.texto, entrada.datos); return [l.errores, l.colocaciones.map((c) => c.etiqueta_escala === false)];",
           {"texto": texto, "datos": datos})
    assert r == [[], [True, False]]


def test_valor_inicial_de_mostrar_escala():
    """Desmarcado solo si el dibujo trae su escala y es la misma con que se exporta."""
    r = js("return [L.etiquetaInicial(10, 10), L.etiquetaInicial(10, 20), L.etiquetaInicial(null, 10), L.etiquetaInicial(undefined, 50)];")
    assert r == [False, True, True, True]
