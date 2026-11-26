"""plano.json versión 6 (Fase 10e3): zonas del Model Space en la lista "dxf", detalles
exportados desde una zona ("origen": {"zona"}) y borradores que componer todavía no compone."""

import json

import pytest
from conftest import crear_paquete_real, escribir_formato

from componedor.componer import PlanoNoComponible, componer_plano
from componedor.plano import PlanoInvalido, leer_plano
from componedor.plano_zonas import ZonaPlano

SHA = "4b1d" + "0" * 60


def zona(nombre="Zona_01", **cambios):
    z = {"nombre": nombre, "zona": [4736058.98, 2234185.8, 4736059.65, 2234186.45],
         "capas": None, "excluir": ["EDD_COTAS"], "escala": "1:20", "centro_mm": [342.55, 297.0],
         "tamano_m": [0.67, 0.65]}
    z.update(cambios)
    return z


def plano_v6(zonas=None, detalles=None, **cambios):
    datos = {"version": 6, "formato": "../formato.json",
             "dxf": [{"id": "d1", "archivo": "../dxf/PRGD.dxf", "sha256": SHA, "unidades": "m",
                      "margen_mm": 5, "zonas": zonas if zonas is not None else [zona()]}],
             "detalles": detalles if detalles is not None else [
                 {"id": "Zona_01", "manifiesto": "../paquetes/Zona_01.manifest.json",
                  "posicion_mm": [320.85, 275.75], "origen": {"zona": "Zona_01"}}]}
    datos.update(cambios)
    return datos


def escribir(carpeta, datos):
    ruta = carpeta / "planos" / "plano.json"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    return ruta


def error(tmp_path, datos):
    with pytest.raises(PlanoInvalido) as e:
        leer_plano(escribir(tmp_path, datos))
    return str(e.value)


def test_leer_zonas_exportadas_y_borradores(tmp_path):
    plano = leer_plano(escribir(tmp_path, plano_v6(
        zonas=[zona(), zona("Seccion_copia", escala="1:10", excluir=None, capas=["0", "_001_*"],
                            centro_mm=[520, 180])])))
    assert plano.version == 6
    assert plano.zonas[0] == ZonaPlano("d1", "Zona_01", (4736058.98, 2234185.8, 4736059.65, 2234186.45),
                                       20.0, (342.55, 297.0), (0.67, 0.65), None, ("EDD_COTAS",))
    (detalle,) = plano.detalles
    assert detalle.zona == "Zona_01" and detalle.posicion_mm == (320.85, 275.75)
    # Seccion_copia no la nombra ningún detalle: es un borrador.
    assert [z.nombre for z in plano.borradores] == ["Seccion_copia"]
    assert plano.borradores[0].capas == ("0", "_001_*") and plano.borradores[0].escala == 10.0


def test_planos_viejos_siguen_igual(tmp_path):
    """Un plano v5 (o anterior) no puede traer zonas ni "origen" en un detalle exportado."""
    v5 = plano_v6(version=5)
    texto = error(tmp_path, v5)
    assert "dxf[0].zonas: solo existe en la versión 6 del plano" in texto
    sin_zonas = plano_v6(version=5)
    del sin_zonas["dxf"][0]["zonas"]
    texto = error(tmp_path, sin_zonas)
    assert "detalles[0]: lleva «origen»" in texto or "origen" in texto
    sin_nada = plano_v6(version=5, detalles=[{"id": "a", "manifiesto": "a.manifest.json",
                                              "posicion_mm": [30, 40]}])
    del sin_nada["dxf"][0]["zonas"]
    assert leer_plano(escribir(tmp_path, sin_nada)).zonas == ()


@pytest.mark.parametrize("cambio, texto", [
    ({"zonas": [zona(color="rojo")]}, "dxf[0].zonas[0].color: campo no reconocido"),
    ({"zonas": [zona(zona=[1, 2, 1, 4])]}, "dxf[0].zonas[0].zona: se esperaba [xmin, ymin, xmax, ymax]"),
    ({"zonas": [zona(capas=["0"])]}, "dxf[0].zonas[0]: lleva «capas» y «excluir» a la vez"),
    ({"zonas": [zona(escala="1/20")]}, "dxf[0].zonas[0].escala: se esperaba «1:N»"),
    ({"zonas": [zona(centro_mm=[1])]}, "dxf[0].zonas[0].centro_mm"),
    ({"zonas": [zona(tamano_m=[0, 1])]}, "dxf[0].zonas[0].tamano_m"),
    ({"zonas": [zona(nombre="")]}, "dxf[0].zonas[0].nombre"),
    ({"zonas": [zona(), zona()]}, "zonas: el nombre 'Zona_01' está repetido"),
    ({"zonas": "no"}, "dxf[0].zonas: se esperaba una lista"),
])
def test_zonas_que_no_valen(tmp_path, cambio, texto):
    assert texto in error(tmp_path, plano_v6(**cambio))


def test_origen_de_un_detalle_exportado(tmp_path):
    otra = plano_v6(detalles=[{"id": "x", "manifiesto": "x.manifest.json", "posicion_mm": [1, 2],
                               "origen": {"zona": "NO_EXISTE"}}])
    assert "detalles[0].origen.zona: 'NO_EXISTE' no está en las «zonas»" in error(tmp_path, otra)
    raro = plano_v6(detalles=[{"id": "x", "manifiesto": "x.manifest.json", "posicion_mm": [1, 2],
                               "origen": {"zona": "Zona_01", "handle": "1A"}}])
    assert "detalles[0].origen.handle: campo no reconocido" in error(tmp_path, raro)
    dos = plano_v6(detalles=[
        {"id": "a", "manifiesto": "a.manifest.json", "posicion_mm": [1, 2], "origen": {"zona": "Zona_01"}},
        {"id": "b", "manifiesto": "b.manifest.json", "posicion_mm": [3, 4], "origen": {"zona": "Zona_01"}}])
    assert "la zona 'Zona_01' ya la usa el detalle 'a'" in error(tmp_path, dos)


def test_componer_no_compone_con_borradores(tmp_path):
    escribir_formato(tmp_path / "formato.json")
    plano = escribir(tmp_path, plano_v6(
        zonas=[zona(), zona("Seccion_copia", escala="1:10")],
        detalles=[{"id": "a", "manifiesto": "a.manifest.json", "posicion_mm": [30, 40]}]))
    with pytest.raises(PlanoNoComponible) as e:
        componer_plano(leer_plano(plano), tmp_path / "plano.pdf")
    texto = str(e.value)
    assert "tiene 2 zona(s) del Model Space sin exportar todavía" in texto
    assert "- 'Zona_01': zona del Model Space a 1:20" in texto and "'Seccion_copia'" in texto
    assert "«Exportar bloques y zonas»" in texto


def test_componer_compone_las_zonas_exportadas(tmp_path):
    """Todas exportadas: el detalle con "origen": {"zona"} se compone como cualquier otro."""
    crear_paquete_real(tmp_path / "paquetes", "Zona_01", sin_fondo=True)
    escribir_formato(tmp_path / "formato.json")
    plano = escribir(tmp_path, plano_v6())
    resultado = componer_plano(leer_plano(plano), tmp_path / "plano.pdf")
    assert [c.id for c in resultado.detalles] == ["Zona_01"]
    assert (tmp_path / "plano.pdf").is_file()
