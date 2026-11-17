"""Campos retirados del rótulo (DISEÑADOR y REVISOR ya no están en la franja del logo).

Un plano.json o proyecto.json viejo que los traiga sigue abriendo y componiendo: se ignoran y
se avisa UNA sola vez, con el mismo texto en Python (componer, editor --proyecto) y en el editor.
Datos sintéticos (plantilla sintética, sección "rotulo" de A1_ERCO.json y Arial).
"""

import json

import pymupdf
import pytest
from conftest import (
    ARIAL,
    RUTA_A1,
    crear_paquete_real,
    crear_plantilla_sintetica,
    escribir_formato,
    requiere_arial,
    rotulo_a1,
)
from test_editor_formularios_js import NODE, js

from componedor.componer import componer_plano
from componedor.datos_editor import construir_datos_editor
from componedor.formato import cargar_formato
from componedor.fuente import cargar_fuente
from componedor.plano import leer_plano
from componedor.proyecto import validar_proyecto
from componedor.rotulo import RotuloInvalido, preparar_rotulo
from componedor.rotulo_formato import (
    AVISO_CAMPOS_RETIRADOS,
    RotuloFormatoInvalido,
    aviso_campos_retirados,
    leer_definicion_rotulo,
)

AMBOS = AVISO_CAMPOS_RETIRADOS.format(campos="rotulo.disenador, rotulo.revisor")
ZONA_ROTULO = (672.4, 12.7, 828.3, 581.3)
VIEJO = {"titulo": "PLANTA GENERAL", "disenador": "Luis Angel", "revisor": "Alan Ruiz "}


@pytest.fixture(scope="module")
def entorno(tmp_path_factory):
    carpeta = tmp_path_factory.mktemp("retirados")
    escribir_formato(carpeta / "formato.json", plantilla=crear_plantilla_sintetica(
        carpeta / "rotulo.pdf"), rotulo=rotulo_a1(fuente={"archivo": str(ARIAL)}))
    crear_paquete_real(carpeta / "input", "a", sin_fondo=True)
    (carpeta / "editor").mkdir()
    return carpeta


@pytest.fixture(scope="module")
def definicion(entorno):
    return cargar_formato(entorno / "formato.json", usar_plantilla=False).rotulo


# --- formato ------------------------------------------------------------------------------------

def test_a1_erco_retira_disenador_y_revisor():
    r = cargar_formato(RUTA_A1, usar_plantilla=False).rotulo
    assert r.campos_retirados == ("disenador", "revisor")
    assert "disenador" not in r.campos and "revisor" not in r.campos


@pytest.mark.parametrize("valor, mensaje", [
    ("disenador", "se esperaba una lista de nombres de campo"),
    (["disenador", 3], "se esperaba una lista de nombres de campo"),
    (["titulo"], "'titulo' sigue en rotulo.campos; un campo no puede estar vigente y retirado"),
])
def test_campos_retirados_invalidos(valor, mensaje):
    with pytest.raises(RotuloFormatoInvalido, match=mensaje):
        leer_definicion_rotulo(rotulo_a1(campos_retirados=valor), ZONA_ROTULO, RUTA_A1.parent)


def test_aviso_uno_solo_para_todos(definicion):
    assert aviso_campos_retirados({"titulo": "X"}, definicion) is None
    assert aviso_campos_retirados(None, definicion) is None
    assert aviso_campos_retirados(VIEJO, definicion) == AMBOS
    assert aviso_campos_retirados({"revisor": 1}, definicion, "proyecto") == (
        AVISO_CAMPOS_RETIRADOS.format(campos="proyecto.revisor"))


# --- componer -----------------------------------------------------------------------------------

@requiere_arial
def test_plano_viejo_se_compone_sin_esos_textos_y_avisa_una_vez(entorno, definicion):
    p = preparar_rotulo(definicion, {**VIEJO, "disenador": True}, [50.0],  # valor que no sirve:
                        cargar_fuente(ARIAL))                              # igual se ignora
    assert p.advertencias == [AMBOS]
    assert not any(t.ruta in ("disenador", "revisor") for t in p.textos)
    # Un campo de verdad desconocido sigue siendo error (no todo se ignora).
    with pytest.raises(RotuloInvalido, match="rotulo.disenadr: campo no reconocido"):
        preparar_rotulo(definicion, {"disenadr": "x"}, [50.0], cargar_fuente(ARIAL))


@requiere_arial
def test_componer_un_plano_viejo(entorno):
    ruta = entorno / "plano_viejo.json"
    ruta.write_text(json.dumps({
        "version": 2, "formato": "formato.json",
        "detalles": [{"id": "d1", "manifiesto": "input/a.manifest.json", "posicion_mm": [40, 300]}],
        "rotulo": VIEJO}, ensure_ascii=False), encoding="utf-8")
    r = componer_plano(leer_plano(ruta), entorno / "viejo.pdf", sobrescribir=True)
    assert r.advertencias.count(AMBOS) == 1
    assert "disenador" not in r.rotulo and "revisor" not in r.rotulo
    with pymupdf.open(entorno / "viejo.pdf") as doc:
        texto = doc[0].get_text()
    assert "PLANTA GENERAL" in texto and "Luis Angel" not in texto and "Alan Ruiz" not in texto


# --- proyecto.json y datos del editor -----------------------------------------------------------

def test_proyecto_viejo_sigue_valiendo(definicion):
    validar_proyecto({"version": 1, "disenador": True, "revisor": ["A\nB"] * 5,
                      "prefijo_no_plano": "ERCO-"}, definicion)  # no lanza


def test_editor_con_proyecto_viejo_avisa_una_vez(entorno):
    proyecto = entorno / "proyecto.json"
    proyecto.write_text(json.dumps({"version": 1, "disenador": "D", "revisor": "R"}),
                        encoding="utf-8")
    datos, _ = construir_datos_editor(entorno / "input", entorno / "formato.json",
                                      entorno / "editor", ruta_proyecto=proyecto)
    avisos = datos["rotulo"]["avisos"]
    assert avisos.count(AVISO_CAMPOS_RETIRADOS.format(
        campos="proyecto.disenador, proyecto.revisor")) == 1
    d = datos["rotulo"]["definicion"]
    assert d["campos_retirados"] == ["disenador", "revisor"]
    assert d["aviso_campos_retirados"] == AVISO_CAMPOS_RETIRADOS
    assert "disenador" not in d["campos"] and "revisor" not in d["campos"]


# --- editor (JS): el mismo aviso, una sola vez, y el plano se conserva --------------------------

@pytest.mark.skipif(NODE is None, reason="Node no está instalado")
@requiere_arial
def test_editor_abre_un_plano_viejo_con_el_mismo_aviso(entorno, definicion):
    datos, _ = construir_datos_editor(entorno / "input", entorno / "formato.json",
                                      entorno / "editor")
    r = js("""
        const def = entrada.datos.rotulo.definicion;
        const modelo = R.crearModelo(entrada.rotulo, def);
        return {validacion: F.validarRotulo(R.serializar(modelo), def, entrada.datos.rotulo.fuente, null),
                noEditable: R.noRepresentable(modelo), guardado: R.serializar(modelo),
                simples: F.camposSimples(def).map((c) => c.campo)};
    """, {"datos": datos, "rotulo": VIEJO})
    python = preparar_rotulo(definicion, VIEJO, [50.0], cargar_fuente(ARIAL)).advertencias
    assert r["validacion"] == {"errores": [], "avisos": python} == {"errores": [], "avisos": [AMBOS]}
    assert r["noEditable"] == []  # el aviso no se repite en la lista de «no editable»
    assert r["guardado"] == VIEJO  # el modelo los conserva (para avisar); al GUARDAR se quitan
    assert "disenador" not in r["simples"] and "revisor" not in r["simples"]


@pytest.mark.skipif(NODE is None, reason="Node no está instalado")
@requiere_arial
def test_al_guardar_el_editor_quita_los_campos_retirados(entorno):
    """Abrir un plano viejo y guardarlo: el plano.json nuevo ya no trae disenador ni revisor, lo
    demás del rótulo se conserva y componer ya no avisa. Si el rótulo solo traía esos dos
    campos, el plano queda sin rótulo. El plano viejo, sin guardar, sigue componiendo."""
    datos, _ = construir_datos_editor(entorno / "input", entorno / "formato.json",
                                      entorno / "editor")
    viejo = {"version": 2, "formato": datos["formato"],
             "detalles": [{"id": "d1", "manifiesto": datos["detalles"][0]["manifiesto"],
                           "posicion_mm": [40, 300]}],
             "rotulo": {**VIEJO, "no_plano": "ERCO-0001"}}
    r = js("""
        const d = entrada.datos, def = d.rotulo.definicion;
        const guardar = (plano) => {   // lo mismo que «Guardar plano» (editor_ui.textoPlano)
          const modelo = R.crearModelo(plano.rotulo, def);
          const avisos = F.validarRotulo(R.serializar(modelo), def, d.rotulo.fuente, null).avisos;
          const col = plano.detalles.map((x) => ({id: x.id, detalle: d.detalles[0], pos: x.posicion_mm,
                                                 posOriginal: x.posicion_mm, original: x}));
          return {avisos, texto: L.serializarPlano(col, d, {rotulo: R.paraGuardar(modelo), original: plano})};
        };
        return {completo: guardar(entrada.viejo),
                solo: guardar(Object.assign({}, entrada.viejo, {rotulo: {disenador: "D", revisor: "R"}}))};
    """, {"datos": datos, "viejo": viejo})
    assert r["completo"]["avisos"] == [AMBOS]  # al abrir: se avisa una vez
    guardado = json.loads(r["completo"]["texto"])
    assert guardado["rotulo"] == {"titulo": "PLANTA GENERAL", "no_plano": "ERCO-0001"}
    assert list(guardado) == list(viejo) and guardado["detalles"] == viejo["detalles"]
    solo = json.loads(r["solo"]["texto"])
    assert "rotulo" not in solo and solo["version"] == 2  # no se baja de versión

    for nombre, plano in (("guardado", guardado), ("solo", solo), ("viejo", viejo)):
        ruta = entorno / "editor" / f"{nombre}.json"
        ruta.write_text(json.dumps(plano, ensure_ascii=False), encoding="utf-8")
        resultado = componer_plano(leer_plano(ruta), entorno / f"{nombre}.pdf", sobrescribir=True)
        assert resultado.advertencias.count(AMBOS) == (1 if nombre == "viejo" else 0), nombre
