"""plano.json versión 3: bloques de un DXF sin exportar (lectura y por qué componer no sigue)."""

import json

import pytest
from conftest import escribir_formato

from componedor.cli import main
from componedor.componer import PlanoNoComponible, componer_plano
from componedor.plano import PlanoInvalido, leer_plano
from componedor.plano_dxf import BloquePendiente, DxfPlano, leer_escala

SHA = "4b1d" + "0" * 60


def dxf(**cambios):
    d = {"id": "d1", "archivo": "../dxf/GUAMO_prueba.dxf", "sha256": SHA, "bytes": 6781020,
         "unidades": "m", "margen_mm": 5}
    d.update(cambios)
    return d


def pendiente(id_="BLOQUE1", **cambios):
    origen = {"dxf": "d1", "bloque": "BLOQUE1", "handle": "50CA", "ocurrencia": 1,
              "escala": "1:5000", "tamano_m": [957.18, 1350.019], "caja_exacta": True}
    otro = cambios.pop("origen", {})
    if otro is None:
        origen = None
    else:
        origen.update(otro)
    p = {"id": id_, "origen": origen, "centro_mm": [342.55, 296.99]}
    p.update(cambios)
    return p


def plano_v3(**cambios):
    datos = {"version": 3, "formato": "formato.json", "dxf": [dxf()],
             "detalles": [pendiente()]}
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


def test_leer_un_plano_v3(tmp_path):
    plano = leer_plano(escribir(tmp_path, plano_v3(detalles=[
        {"id": "listo", "manifiesto": "a.manifest.json", "posicion_mm": [30, 40],
         "etiqueta_escala": False},
        pendiente(), pendiente("Carro", origen={"bloque": "Carro frontal 1", "handle": "1A3",
                                                "ocurrencia": 2, "escala": "1:50"},
                               etiqueta_escala=False)])))
    assert plano.version == 3
    assert plano.dxf == (DxfPlano("d1", tmp_path / "planos" / "../dxf/GUAMO_prueba.dxf", SHA,
                                  5.0, 6781020, "m"),)
    assert [d.id for d in plano.detalles] == ["listo"]  # los ya exportados, como siempre
    assert plano.pendientes == (
        BloquePendiente("BLOQUE1", "d1", "BLOQUE1", "50CA", 1, 5000.0, (957.18, 1350.019),
                        (342.55, 296.99)),
        BloquePendiente("Carro", "d1", "Carro frontal 1", "1A3", 2, 50.0, (957.18, 1350.019),
                        (342.55, 296.99), etiqueta_escala=False))


def test_las_versiones_1_y_2_no_cambian(tmp_path):
    datos = plano_v3(version=2)
    assert "- dxf: solo existe en la versión 3 del plano (use \"version\": 3)" in error(
        tmp_path, datos)
    datos = plano_v3(version=2, dxf=None)
    del datos["dxf"]
    mensaje = error(tmp_path, datos)
    assert "detalles[0].origen: campo no reconocido" in mensaje  # sin v3 no hay pendientes
    assert "detalles[0]: falta posicion_mm [x, y] o centrar: true" in mensaje


@pytest.mark.parametrize("cambio, esperado", [
    ({"dxf": "d1"}, "- dxf: se esperaba una lista"),
    ({"dxf": [dxf(sha256="ABC")]}, "- dxf[0].sha256: se esperaba el SHA-256"),
    ({"dxf": [dxf(margen_mm=-1)]}, "- dxf[0].margen_mm: se esperaba un número ≥ 0"),
    ({"dxf": [dxf(archivo="")]}, "- dxf[0].archivo: se esperaba la ruta"),
    ({"dxf": [dxf(), dxf()]}, "- dxf[1].id: 'd1' está repetido"),
    ({"dxf": [dxf(color="rojo")]}, "- dxf[0].color: campo no reconocido"),
    ({"dxf": [dxf(bytes=-2)]}, "- dxf[0].bytes: se esperaba un entero ≥ 0 o null"),
])
def test_lista_dxf_invalida(tmp_path, cambio, esperado):
    assert esperado in error(tmp_path, plano_v3(**cambio))


@pytest.mark.parametrize("bloque, esperado", [
    (pendiente(origen={"dxf": "d9"}), "detalles[0].origen.dxf: 'd9' no está en la lista"),
    (pendiente(origen={"handle": "50ca"}), "detalles[0].origen.handle: se esperaba el handle"),
    (pendiente(origen={"escala": "1/50"}), "detalles[0].origen.escala: se esperaba «1:N»"),
    (pendiente(origen={"escala": "1:0"}), "detalles[0].origen.escala: se esperaba «1:N»"),
    (pendiente(origen={"ocurrencia": 0}), "detalles[0].origen.ocurrencia: se esperaba un entero"),
    (pendiente(origen={"tamano_m": [1]}), "detalles[0].origen.tamano_m: se esperaba [ancho, alto]"),
    (pendiente(origen={"caja_exacta": "sí"}), "detalles[0].origen.caja_exacta: se esperaba true"),
    (pendiente(origen={"capa": "0"}), "detalles[0].origen.capa: campo no reconocido"),
    (pendiente(centro_mm=[1, "x"]), "detalles[0].centro_mm: se esperaba [x, y]"),
    (pendiente(manifiesto="a.json"), "detalles[0].manifiesto: campo no reconocido"),
    (pendiente(origen=None), "detalles[0].origen: se esperaba un objeto"),
])
def test_bloque_pendiente_invalido(tmp_path, bloque, esperado):
    assert esperado in error(tmp_path, plano_v3(detalles=[bloque]))


def test_id_repetido_entre_pendiente_y_exportado(tmp_path):
    mensaje = error(tmp_path, plano_v3(detalles=[
        {"id": "A", "manifiesto": "a.manifest.json", "centrar": True}, pendiente("A")]))
    assert "detalles[1].id: 'A' está repetido" in mensaje


def test_leer_escala():
    assert leer_escala("1:2000") == 2000.0 and leer_escala("1:3500") == 3500.0  # a mano
    assert leer_escala("1:12.5") is None and leer_escala("1:100001") is None
    assert leer_escala("1:0") is None and leer_escala("2:50") is None
    assert leer_escala(50) is None


def test_componer_explica_que_bloques_faltan(tmp_path, capsys):
    (tmp_path / "planos").mkdir()
    escribir_formato(tmp_path / "planos" / "formato.json")
    (tmp_path / "dxf").mkdir()
    (tmp_path / "dxf" / "GUAMO_prueba.dxf").write_text("0\nEOF\n", encoding="utf-8")
    ruta = escribir(tmp_path, plano_v3(dxf=[dxf(), dxf(id="d2", archivo="../dxf/otro.dxf")],
                                       detalles=[
        pendiente(),
        pendiente("Carro", origen={"bloque": "Carro frontal 1", "handle": "1A3", "ocurrencia": 2,
                                   "escala": "1:50", "tamano_m": [32.0, 4.0]}),
        pendiente("Otro", origen={"dxf": "d2", "escala": "1:10000"})]))
    with pytest.raises(PlanoNoComponible) as e:
        componer_plano(leer_plano(ruta), tmp_path / "salida.pdf")
    texto = str(e.value)
    assert texto.startswith("No se compone el plano: tiene 3 bloque(s) de DXF sin exportar "
                            "todavía (plano versión 3).")
    assert "- 'BLOQUE1': bloque «BLOQUE1» (handle 50CA) a 1:5000, de GUAMO_prueba.dxf\n" in texto
    assert ("- 'Carro': bloque «Carro frontal 1» (ocurrencia 2, handle 1A3) a 1:50, de "
            "GUAMO_prueba.dxf — NO CABE en 'area_dibujo' a 1:50 (página 650.0 × 90.0 mm; "
            "sobran 10.3 × 0.0 mm): cambie la escala en el editor") in texto
    assert "- 'Otro': bloque «BLOQUE1» (handle 50CA) a 1:10000, de otro.dxf (el DXF ya no está" \
        in texto
    assert texto.endswith("y vuelva a componer.")
    assert not (tmp_path / "salida.pdf").exists()
    # Lo mismo por la consola (y por Componer.bat, que llama a esto).
    assert main(["componer", str(ruta), "--salida", str(tmp_path / "salida.pdf")]) == 1
    assert "tiene 3 bloque(s) de DXF sin exportar" in capsys.readouterr().err
