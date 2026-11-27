"""plano.json versión 8: un proyecto de varias hojas en UN archivo (plano_proyecto.py) y
componerlo entero con el motor de «Componer proyecto»."""

import json

import pymupdf
import pytest
from conftest import (
    ARIAL,
    crear_paquete_real,
    crear_plantilla_sintetica,
    escribir_formato,
    requiere_arial,
    rotulo_a1,
)

from componedor.cli import main
from componedor.componer_proyecto import ProyectoNoComponible, componer_archivo_proyecto
from componedor.plano import PlanoInvalido, leer_plano
from componedor.plano_proyecto import ProyectoInvalido, es_proyecto, leer_proyecto

SHA = "4b1d" + "0" * 60
DETALLE = {"id": "a", "manifiesto": "input/a.manifest.json", "posicion_mm": [30, 300]}
ZONA = {"dxf": "d1", "nombre": "Zona_01", "zona": [4736058.98, 2234185.8, 4736059.65, 2234186.45],
        "capas": None, "excluir": None, "escala": "1:20", "centro_mm": [342.55, 297.0],
        "tamano_m": [0.67, 0.65]}


def _proyecto(carpeta, hojas, **extra):
    datos = {"version": 8, "formato": "formato.json", "hojas": hojas, **extra}
    ruta = carpeta / "Obra.json"
    ruta.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    return ruta


def _tres_hojas():
    return [{"nombre": "Planta", "detalles": [DETALLE], "rotulo": {"titulo": "PLANTA", "no_plano": "ERCO-PL-106"}},
            {"nombre": "Perfil", "detalles": [], "rotulo": {"titulo": "PERFIL"},
             "copiado_de": {"hoja": "Planta", "revisar": ["notas"]}},
            {"nombre": "Detalles", "detalles": [dict(DETALLE, posicion_mm=[200, 100])],
             "rotulo": {"titulo": "DETALLES", "hoja": "C"}}]


@pytest.fixture
def entorno(tmp_path):
    escribir_formato(tmp_path / "formato.json", plantilla=crear_plantilla_sintetica(tmp_path / "r.pdf"),
                     rotulo=rotulo_a1(fuente={"archivo": str(ARIAL)}))
    crear_paquete_real(tmp_path / "input", "a")
    return tmp_path


# --- leer --------------------------------------------------------------------------------

def test_leer_un_proyecto(tmp_path):
    escribir_formato(tmp_path / "formato.json")
    hojas = _tres_hojas()
    hojas[2]["zonas"] = [ZONA]  # una zona borrador en la hoja 3
    ruta = _proyecto(tmp_path, hojas, dxf=[{"id": "d1", "archivo": "obra.dxf", "sha256": SHA, "margen_mm": 5}])
    assert es_proyecto(ruta) and not es_proyecto(tmp_path / "formato.json")
    p = leer_proyecto(ruta)
    assert [h.nombre for h in p.hojas] == ["Planta", "Perfil", "Detalles"] and p.problemas == []
    planta, perfil, detalles = (h.plano for h in p.hojas)
    assert (planta.hoja, planta.posicion, len(planta.detalles)) == ("Planta", 0, 1)
    assert perfil.detalles == () and perfil.revisar == ("notas",) and perfil.copiado_de == "Planta"
    # Las zonas son de su hoja.
    assert planta.zonas == () and [z.nombre for z in detalles.zonas] == ["Zona_01"]
    assert [b.nombre for b in detalles.borradores] == ["Zona_01"]
    # Los rótulos de todas las hojas, para hoja / de / número; cada hoja, su copia de la ortofoto.
    assert detalles.rotulos_proyecto[0]["no_plano"] == "ERCO-PL-106"
    assert perfil.ruta_copia.name == "Obra_hoja2.json" and perfil.ruta == ruta


def test_un_plano_de_una_hoja_no_se_lee_como_proyecto(tmp_path):
    ruta = _proyecto(tmp_path, _tres_hojas())
    with pytest.raises(PlanoInvalido, match="es un proyecto de varias hojas"):
        leer_plano(ruta)


@pytest.mark.parametrize("cambio, texto", [
    ({"hojas": []}, "hojas: se esperaba la lista de hojas del proyecto"),
    ({"detalles": []}, "detalles: campo no reconocido en un proyecto"),
    ({"hojas": [{"nombre": "A"}, {"nombre": "a"}]}, "hojas[1].nombre: 'a' está repetido"),
    ({"hojas": [{"detalles": []}]}, "hojas[0].nombre: se esperaba un texto no vacío"),
])
def test_proyectos_que_no_valen(tmp_path, cambio, texto):
    datos = {"hojas": _tres_hojas(), **cambio}
    with pytest.raises(ProyectoInvalido, match=texto.replace("[", r"\[").replace("]", r"\]")):
        leer_proyecto(_proyecto(tmp_path, **datos))


def test_los_problemas_de_una_hoja_no_impiden_leer_las_otras(tmp_path):
    escribir_formato(tmp_path / "formato.json")
    hojas = _tres_hojas()
    hojas[1]["detalles"] = [{"id": "x", "posicion_mm": [1, 2]}]  # sin manifiesto
    hojas[1]["color"] = "rojo"
    hojas[0]["zonas"] = [ZONA]
    hojas[2]["zonas"] = [dict(ZONA, dxf="no_esta"), ZONA]
    p = leer_proyecto(_proyecto(tmp_path, hojas, dxf=[{"id": "d1", "archivo": "obra.dxf", "sha256": SHA,
                                                       "margen_mm": 5}]))
    assert [h.plano is not None for h in p.hojas] == [True, False, False]
    assert "Hoja 2 de 3 («Perfil»): color: campo no reconocido en una hoja" in p.problemas[0]
    texto = "\n".join(p.problemas)
    assert "Hoja 3 de 3 («Detalles»): zonas[0].dxf: se esperaba el id de un DXF" in texto
    assert "zonas[1].nombre: 'Zona_01' ya es una zona de la hoja 1" in texto


# --- componer -------------------------------------------------------------------------------

@requiere_arial
def test_componer_el_archivo_entero(entorno):
    salida = entorno / "salida" / "Obra.pdf"
    r = componer_archivo_proyecto(_proyecto(entorno, _tres_hojas()), salida)
    assert [h.archivo for h in r.hojas] == ["«Planta»", "«Perfil»", "«Detalles»"]
    # Hoja / de / número por la posición; lo escrito a mano («C») manda.
    assert [(h.resultado.rotulo["hoja"], h.resultado.rotulo["de"], h.resultado.rotulo["no_plano"])
            for h in r.hojas] == [("1", "3", "ERCO-PL-106"), ("2", "3", "ERCO-PL-107"), ("C", "3", "ERCO-PL-108")]
    with pymupdf.open(salida) as doc:
        assert doc.page_count == 3 and "PERFIL" in doc[1].get_text()
    assert "Hoja 2 de 3 («Perfil») · La hoja no tiene detalles: sale solo el rótulo." in r.advertencias
    assert "Hoja 2 de 3 («Perfil») · rotulo.notas: copiado de la hoja «Planta» sin revisar" in "\n".join(r.advertencias)
    assert [p.name for p in salida.parent.iterdir()] == ["Obra.pdf"]


@requiere_arial
def test_si_una_hoja_falla_no_sale_nada(entorno):
    hojas = _tres_hojas()
    hojas[0]["detalles"] = [dict(DETALLE, manifiesto="input/no_esta.manifest.json")]
    hojas[2]["color"] = "rojo"
    salida = entorno / "Obra.pdf"
    with pytest.raises(ProyectoNoComponible) as e:
        componer_archivo_proyecto(_proyecto(entorno, hojas), salida)
    texto = str(e.value)
    assert "2 de 3 hoja(s) con problemas (no se generó el PDF)" in texto
    assert "- Hoja 1 de 3 («Planta»):" in texto and "no_esta.manifest.json" in texto
    assert "- Hoja 3 de 3 («Detalles»):" in texto and "color: campo no reconocido" in texto
    assert not salida.exists()


@requiere_arial
def test_cli_con_el_archivo_del_proyecto(entorno, capsys):
    config = entorno / "componedor.json"
    config.write_text(json.dumps({"version": 1, "formato": "formato.json",
                                  "componer": {"resultados": "resultados"}}), encoding="utf-8")
    ruta = _proyecto(entorno, _tres_hojas())
    assert main(["componer", str(ruta), "--config", str(config)]) == 0
    out = capsys.readouterr().out
    assert (entorno / "resultados" / "Obra.pdf").is_file()  # resultados/<archivo>.pdf
    assert "Hoja 3 de 3: «Detalles» · 1 detalle(s) · No. PLANO ERCO-PL-108 · HOJA C DE 3" in out
    assert "3 hoja(s), 3 página(s)" in out
