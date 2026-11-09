"""Lectura y validación de plano.json (sintético, sin datos de ERCO)."""

import json

import pytest

from componedor.plano import PlanoInvalido, RosaPlano, leer_plano


def _escribir(carpeta, datos, nombre="plano.json"):
    ruta = carpeta / nombre
    ruta.write_text(json.dumps(datos) if not isinstance(datos, str) else datos, encoding="utf-8")
    return ruta


def _base(**cambios):
    datos = {
        "version": 1,
        "formato": "formatos/A1.json",
        "plantilla": None,
        "detalles": [
            {"id": "d1", "manifiesto": "input/a.manifest.json", "posicion_mm": [30, 440.5]},
            {"id": "d2", "manifiesto": "input/b.manifest.json", "centrar": True},
        ],
    }
    datos.update(cambios)
    return datos


def _error(tmp_path, datos) -> str:
    with pytest.raises(PlanoInvalido) as e:
        leer_plano(_escribir(tmp_path, datos))
    return str(e.value)


def test_plano_valido_y_rutas_relativas_a_su_carpeta(tmp_path):
    (tmp_path / "sub").mkdir()
    plano = leer_plano(_escribir(tmp_path / "sub", _base()))
    assert plano.version == 1
    assert plano.formato == tmp_path / "sub" / "formatos" / "A1.json"
    assert plano.plantilla is None
    d1, d2 = plano.detalles
    assert (d1.id, d1.manifiesto, d1.posicion_mm, d1.centrar) == \
        ("d1", tmp_path / "sub" / "input" / "a.manifest.json", (30.0, 440.5), False)
    assert (d2.id, d2.posicion_mm, d2.centrar) == ("d2", None, True)


def test_plantilla_opcional(tmp_path):
    datos = _base()
    del datos["plantilla"]
    assert leer_plano(_escribir(tmp_path, datos)).plantilla is None
    plano = leer_plano(_escribir(tmp_path, _base(plantilla="rotulos/otro.pdf")))
    assert plano.plantilla == tmp_path / "rotulos" / "otro.pdf"


def test_centrar_false_con_posicion_es_valido(tmp_path):
    datos = _base(detalles=[{"id": "a", "manifiesto": "m.manifest.json",
                             "posicion_mm": [1, 2], "centrar": False}])
    (detalle,) = leer_plano(_escribir(tmp_path, datos)).detalles
    assert detalle.posicion_mm == (1.0, 2.0) and not detalle.centrar


@pytest.mark.parametrize("detalles, esperado", [
    ([{"id": "d1", "manifiesto": "a", "centrar": True},
      {"id": "d1", "manifiesto": "b", "centrar": True}],
     "- detalles[1].id: 'd1' está repetido (ya lo usa detalles[0]); cada id debe ser único"),
    ([{"id": "d1", "manifiesto": "a"}],
     "- detalles[0]: falta posicion_mm [x, y] o centrar: true (uno de los dos)"),
    ([{"id": "d1", "manifiesto": "a", "posicion_mm": [1, 2], "centrar": True}],
     "- detalles[0]: lleva posicion_mm y centrar: true a la vez; use solo uno"),
    ([{"manifiesto": "a", "centrar": True}], "- detalles[0].id: falta el campo"),
    ([{"id": "", "manifiesto": "a", "centrar": True}], "- detalles[0].id: se esperaba un texto no vacío"),
    ([{"id": 7, "manifiesto": "a", "centrar": True}], "- detalles[0].id: se esperaba un texto no vacío; tiene int 7"),
    ([{"id": "d1", "centrar": True}], "- detalles[0].manifiesto: falta el campo"),
    ([{"id": "d1", "manifiesto": "a", "posicion_mm": [1, 2, 3]}],
     "- detalles[0].posicion_mm: se esperaba [x, y] con 2 números finitos en mm; tiene [1, 2, 3]"),
    ([{"id": "d1", "manifiesto": "a", "posicion_mm": ["1", 2]}],
     "- detalles[0].posicion_mm: se esperaba [x, y]"),
    ([{"id": "d1", "manifiesto": "a", "centrar": "sí"}],
     "- detalles[0].centrar: se esperaba true o false; tiene texto 'sí'"),
    ([{"id": "d1", "manifiesto": "a", "centar": True}],
     "- detalles[0].centar: campo no reconocido"),
    (["d1"], "- detalles[0]: se esperaba un objeto {...}; tiene texto 'd1'"),
    ([], "- detalles: la lista está vacía; el plano necesita al menos un detalle"),
    ("d1", "- detalles: se esperaba una lista; tiene texto 'd1'"),
])
def test_detalles_invalidos(tmp_path, detalles, esperado):
    assert esperado in _error(tmp_path, _base(detalles=detalles))


@pytest.mark.parametrize("cambio, esperado", [
    ({"version": 3}, "- version: versión 3 no soportada; el componedor entiende las versiones 1 y 2"),
    ({"version": "1"}, "- version: se esperaba un número entero; tiene texto '1'"),
    ({"version": True}, "- version: se esperaba un número entero; tiene un booleano"),
    ({"formato": None}, "- formato: se esperaba una ruta (texto); tiene null"),
    ({"plantilla": 3}, "- plantilla: se esperaba una ruta (texto); tiene int 3"),
    ({"nombre": "mi plano"}, "- nombre: campo no reconocido"),
])
def test_raiz_invalida(tmp_path, cambio, esperado):
    assert esperado in _error(tmp_path, _base(**cambio))


@pytest.mark.parametrize("campo", ["version", "formato", "detalles"])
def test_falta_campo_de_la_raiz(tmp_path, campo):
    datos = _base()
    del datos[campo]
    assert f"- {campo}: falta el campo" in _error(tmp_path, datos)


def test_varios_problemas_en_un_solo_mensaje(tmp_path):
    datos = _base(version=3, detalles=[
        {"id": "a", "manifiesto": "m"},
        {"id": "a", "manifiesto": "m", "centrar": True},
        {"id": "b", "manifiesto": "m", "posicion_mm": [0, 0], "centrar": True},
    ])
    mensaje = _error(tmp_path, datos)
    assert "(4 problemas)" in mensaje
    assert mensaje.count("\n- ") == 4


def test_json_mal_formado_no_objeto_e_inexistente(tmp_path):
    with pytest.raises(PlanoInvalido, match=r"no es un JSON válido \(línea 1, columna"):
        leer_plano(_escribir(tmp_path, '{"version": 1,'))
    with pytest.raises(PlanoInvalido, match="debe ser un objeto JSON"):
        leer_plano(_escribir(tmp_path, "[1, 2]"))
    with pytest.raises(PlanoInvalido, match="No se encontró el plano"):
        leer_plano(tmp_path / "no_existe.json")


# --- versión 2 (subfase 4.1): rótulo, rosa de los vientos y etiqueta_escala -------------------

def test_version_2_completa(tmp_path):
    datos = _base(version=2, rotulo={"titulo": "PLANTA", "hoja": 1},
                  rosa_vientos={"visible": True, "posicion_mm": [600, 500.5]})
    datos["detalles"][0]["etiqueta_escala"] = False
    plano = leer_plano(_escribir(tmp_path, datos))
    assert plano.version == 2
    assert plano.rotulo == {"titulo": "PLANTA", "hoja": 1}  # el contenido lo valida componer
    assert plano.rosa == RosaPlano(True, (600.0, 500.5))
    assert [d.etiqueta_escala for d in plano.detalles] == [False, True]


def test_version_2_todo_opcional(tmp_path):
    plano = leer_plano(_escribir(tmp_path, _base(version=2)))
    assert plano.rotulo is None and plano.rosa is None
    assert leer_plano(_escribir(tmp_path, _base(version=2, rosa_vientos={}))).rosa == RosaPlano()
    oculta = leer_plano(_escribir(tmp_path, _base(version=2, rosa_vientos={"visible": False})))
    assert oculta.rosa == RosaPlano(False, None)


def test_version_1_sigue_valida_y_no_admite_lo_nuevo(tmp_path):
    plano = leer_plano(_escribir(tmp_path, _base()))
    assert plano.version == 1 and plano.rotulo is None and plano.rosa is None
    datos = _base(rotulo={}, rosa_vientos={})
    datos["detalles"][0]["etiqueta_escala"] = False
    mensaje = _error(tmp_path, datos)
    assert "- rotulo: solo existe en la versión 2 del plano (use \"version\": 2)" in mensaje
    assert "- rosa_vientos: solo existe en la versión 2 del plano" in mensaje
    assert "- detalles[0].etiqueta_escala: solo existe en la versión 2 del plano" in mensaje


@pytest.mark.parametrize("cambio, esperado", [
    ({"rotulo": ["PLANTA"]}, "- rotulo: se esperaba un objeto {...} con los valores del rótulo; "
                             "tiene una lista"),
    ({"rosa_vientos": True}, "- rosa_vientos: se esperaba un objeto"),
    ({"rosa_vientos": {"visble": False}}, "- rosa_vientos.visble: campo no reconocido (campos "
                                          "válidos: posicion_mm, visible)"),
    ({"rosa_vientos": {"visible": "no"}}, "- rosa_vientos.visible: se esperaba true o false; "
                                          "tiene texto 'no'"),
    ({"rosa_vientos": {"posicion_mm": [1]}}, "- rosa_vientos.posicion_mm: se esperaba [x, y]"),
    ({"leyenda": "x"}, "- leyenda: campo no reconocido (campos válidos: detalles, formato, "
                       "plantilla, rosa_vientos, rotulo, version)"),
])
def test_version_2_invalida(tmp_path, cambio, esperado):
    assert esperado in _error(tmp_path, _base(version=2, **cambio))


def test_etiqueta_escala_invalida(tmp_path):
    datos = _base(version=2)
    datos["detalles"][1]["etiqueta_escala"] = "no"
    assert ("- detalles[1].etiqueta_escala: se esperaba true o false; tiene texto 'no'"
            in _error(tmp_path, datos))
