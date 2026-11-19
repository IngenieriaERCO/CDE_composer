"""«Cargar ortofoto» del servidor del editor (sin HTTP): elegir, ficha, vistas previas, quitar."""

import os

import pymupdf
import pytest
from ortofoto_sintetica import ORIGEN, crear_geotiff

from componedor import ortofoto_editor
from componedor.ortofoto_editor import ErrorOrtofoto, OrtofotoEditor

X0, Y1 = ORIGEN
CAJA = [X0 + 100, Y1 - 200, X0 + 200, Y1 - 100]


def armar(tmp_path, ruta=None, **kw):
    editor = tmp_path / "editor"
    editor.mkdir(exist_ok=True)
    ruta = ruta or crear_geotiff(tmp_path / "data" / "ortofotos" / "a.tif", **kw)
    elegidas = []

    def elegir(inicial):
        elegidas.append(inicial)
        return ruta

    o = OrtofotoEditor(editor, elegir=elegir)
    return o, ruta, elegidas


def pedido(**cambios):
    return {"caja_cad": CAJA, "mm_por_unidad": 1000, "crs_dibujo": "EPSG:9377", "px": 100,
            **cambios}


def test_elegir_lee_la_ficha_y_da_la_ruta_para_el_plano(tmp_path):
    o, ruta, elegidas = armar(tmp_path)
    assert o.estado() is None
    r = o.elegir()
    assert r["elegida"] == "a.tif"
    e = r["ortofoto"]
    assert e["archivo_plano"] == "../data/ortofotos/a.tif"  # relativa a la carpeta del editor
    assert e["ficha"]["px"] == [400, 300] and e["cambio"] is False
    assert e["sistemas"][0] == {"codigo": "EPSG:9377",
                                "nombre": "MAGNA-SIRGAS 2018 / Origen-Nacional (CTM12)"}
    o.elegir()
    assert elegidas == [None, ruta.parent]  # la segunda vez abre en la carpeta de la anterior


def test_cancelar_e_invalida(tmp_path):
    o = OrtofotoEditor(tmp_path, elegir=lambda i: None)
    assert o.elegir() == {"elegida": None, "ortofoto": None}
    malo = tmp_path / "roto.tif"
    malo.write_bytes(b"no")
    o = OrtofotoEditor(tmp_path, elegir=lambda i: malo)
    with pytest.raises(ErrorOrtofoto) as e:
        o.elegir()
    assert e.value.estado_http == 400 and "No se pudo leer" in e.value.mensaje
    o = OrtofotoEditor(tmp_path, elegir=lambda i: tmp_path / "foto.png")
    with pytest.raises(ErrorOrtofoto, match="no es un GeoTIFF"):
        o.elegir()


def test_previa_y_su_png(tmp_path):
    o, _, _ = armar(tmp_path)
    with pytest.raises(ErrorOrtofoto) as e:
        o.previa(pedido())
    assert e.value.estado_http == 409  # sin ortofoto cargada
    o.elegir()
    r = o.previa(pedido())
    assert r["url"] == f"/api/ortofoto/previas/{r['id']}" and r["px"] == [100, 100]
    assert r["cobertura"] == 1.0 and r["caja_cad"] == CAJA
    pix = pymupdf.Pixmap(o.png(r["id"]))
    assert (pix.width, pix.height, pix.alpha) == (100, 100, 1)
    assert o.previa(pedido()) is r  # la misma caja: la misma vista previa (sin leer de nuevo)
    otra = o.previa(pedido(crs_dibujo="EPSG:3116", caja_cad=[824780.9, 1134684.9,
                                                              825581.9, 1135186.5]))
    assert otra["id"] != r["id"]
    with pytest.raises(ErrorOrtofoto) as e:
        o.png("o-999")
    assert e.value.estado_http == 404


@pytest.mark.parametrize("cambios, texto", [
    ({"caja_cad": [1, 2, 3]}, "caja_cad"),
    ({"caja_cad": [5, 5, 1, 1]}, "vacía"),
    ({"mm_por_unidad": 0}, "mm_por_unidad"),
    ({"mm_por_unidad": True}, "mm_por_unidad"),
    ({"px": 5}, "px"),
    ({"px": 1.5}, "px"),
    ({"crs_dibujo": None}, "sistema de coordenadas del dibujo"),
    ({"crs_dibujo": "EPSG:4326"}, "no es un sistema proyectado"),
    ({"crs_dibujo": "../../etc"}, "no válido"),
])
def test_pedidos_invalidos(tmp_path, cambios, texto):
    o, _, _ = armar(tmp_path)
    o.elegir()
    with pytest.raises(ErrorOrtofoto, match=texto) as e:
        o.previa(pedido(**cambios))
    assert e.value.estado_http == 400


def test_sin_sistema_propio_hay_que_elegirlo(tmp_path):
    o, _, _ = armar(tmp_path, crs=None)
    o.elegir()
    with pytest.raises(ErrorOrtofoto, match="no se supone ninguno"):
        o.previa(pedido())
    assert o.previa(pedido(crs_ortofoto="EPSG:9377"))["cobertura"] == 1.0
    with pytest.raises(ErrorOrtofoto, match="no válido"):
        o.previa(pedido(crs_ortofoto="9377"))


def test_con_sistema_propio_el_elegido_no_cuenta(tmp_path):
    o, _, _ = armar(tmp_path)
    o.elegir()
    a = o.previa(pedido())
    assert o.previa(pedido(crs_ortofoto="EPSG:3116")) is a  # ignorado: misma clave


def test_si_cambia_en_el_disco_hay_que_volver_a_cargarla(tmp_path):
    o, ruta, _ = armar(tmp_path)
    o.elegir()
    estado = ruta.stat()
    os.utime(ruta, ns=(estado.st_atime_ns, estado.st_mtime_ns + 5_000_000_000))
    assert o.estado()["cambio"] is True
    with pytest.raises(ErrorOrtofoto) as e:
        o.previa(pedido())
    assert e.value.estado_http == 409 and "cambió en el disco" in e.value.mensaje
    o.elegir()  # volver a cargarla
    assert o.estado()["cambio"] is False and o.previa(pedido())["cobertura"] == 1.0


def test_quitar_y_tope_de_vistas_previas(tmp_path, monkeypatch):
    monkeypatch.setattr(ortofoto_editor, "MAX_PREVIAS", 2)
    o, _, _ = armar(tmp_path)
    o.elegir()
    ids = [o.previa(pedido(caja_cad=[CAJA[0] + i, CAJA[1], CAJA[2], CAJA[3]]))["id"]
           for i in range(3)]
    with pytest.raises(ErrorOrtofoto):
        o.png(ids[0])  # la más vieja se descartó
    assert o.png(ids[2])
    # Pedir otra vez la descartada la vuelve a hacer (con otro id).
    assert o.previa(pedido(caja_cad=CAJA))["id"] not in ids
    assert o.quitar() == {"quitada": True}
    assert o.estado() is None
    with pytest.raises(ErrorOrtofoto):
        o.png(ids[2])


def test_ruta_en_otro_disco_queda_absoluta(tmp_path, monkeypatch):
    o, ruta, _ = armar(tmp_path)

    def relpath(*a):
        raise ValueError("otro disco")

    monkeypatch.setattr(ortofoto_editor.os.path, "relpath", relpath)
    assert o.archivo_para_plano(ruta) == str(ruta)


def test_el_cuadro_abre_en_la_carpeta_del_plano(tmp_path):
    """La ruta del plano solo decide dónde se abre el cuadro; no se lee nada con ella."""
    o, ruta, elegidas = armar(tmp_path)
    o.elegir("../data/ortofotos/otra_que_no_existe.tif")
    assert elegidas[-1] == ruta.parent  # la carpeta existe: ahí
    o.elegir("../no_existe/a.tif")
    assert elegidas[-1] == ruta.parent  # no existe: la de la última elegida
    for malo in (None, 3, "", "x" * 2000):
        assert o.carpeta_del_plano(malo) is None
    assert o.carpeta_del_plano(str(ruta)) == ruta.parent  # absoluta (otro disco)
