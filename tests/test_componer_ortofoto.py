"""`componer` con ortofoto (plano versión 4): detrás de los detalles, en su sitio, los detalles
siguen siendo vectores, copia reducida, original contra copia y errores claros."""

import json
import os
import re
import shutil

import pymupdf
import pytest
from conftest import (
    MATRIZ_SINTETICA,
    X0_CAD,
    Y0_CAD,
    crear_paquete_real,
    crear_plantilla_sintetica,
    escribir_formato,
)
from ortofoto_sintetica import crear_geotiff, error_de_posicion, imagenes_pdf

from componedor.cad_a_papel import MatrizCad
from componedor.cli import main
from componedor.componer import PlanoNoComponible, componer_plano
from componedor.configuracion import ConfigOrtofoto
from componedor.ortofoto_copia import leer_indice
from componedor.ortofoto_fuente import diferencias, fecha
from componedor.ortofoto_pdf import papel_a_cad
from componedor.plano import leer_plano

OCUPADO = (30.0, 40.0, 290.0, 160.0)
MATRIZ = MatrizCad(*MATRIZ_SINTETICA)
ALTO = 594.0
POCO = ConfigOrtofoto(100, 85)  # 100 ppp: pruebas rápidas


@pytest.fixture
def entorno(tmp_path):
    escribir_formato(tmp_path / "formato.json",
                     plantilla=crear_plantilla_sintetica(tmp_path / "rotulo.pdf"))
    crear_paquete_real(tmp_path / "input", "a", sin_fondo=True)
    crear_geotiff(tmp_path / "fotos" / "orto.tif", ancho=400, alto=200,
                  origen=(X0_CAD - 2, Y0_CAD + 8), pixel=0.05, sinusoidal=True)
    return tmp_path


def plano(carpeta, ortofoto=True, **cambios):
    tif = carpeta / "fotos" / "orto.tif"
    datos = {"version": 4, "formato": "../formato.json",
             "detalles": [{"id": "a", "manifiesto": "../input/a.manifest.json",
                           "posicion_mm": list(OCUPADO[:2])}]}
    if ortofoto:
        datos["ortofoto"] = {"archivo": "../fotos/orto.tif", "bytes": tif.stat().st_size,
                             "modificado": fecha(tif), "crs": None, "crs_dibujo": "EPSG:9377",
                             "opacidad": 1, **cambios}
    ruta = carpeta / "planos" / "plano.json"
    ruta.parent.mkdir(exist_ok=True)
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    return leer_plano(ruta)


def a_cad(x, y):
    return papel_a_cad((x, y), OCUPADO, MATRIZ)


def test_detras_de_los_detalles_en_su_sitio_y_los_vectores_intactos(entorno):
    sin = componer_plano(plano(entorno, ortofoto=False), entorno / "sin.pdf", config_ortofoto=POCO)
    con = componer_plano(plano(entorno), entorno / "con.pdf", config_ortofoto=POCO)
    assert sin.ortofoto is None
    o = con.ortofoto
    assert o.fuente == "original" and o.ppp == 100 and o.cobertura == {"a": 1.0}
    assert o.px == {"a": (1024, 472)} and len(o.mosaicos) == 1
    with pymupdf.open(entorno / "sin.pdf") as a, pymupdf.open(entorno / "con.pdf") as b:
        # Los mismos trazos y textos: los detalles siguen siendo vectores.
        assert len(a[0].get_drawings()) == len(b[0].get_drawings())
        assert a[0].get_text() == b[0].get_text()
        assert len(b[0].get_image_info()) == len(a[0].get_image_info()) + 1
        # Orden: la imagen de la ortofoto se pinta antes (debajo) que el detalle, que entra
        # como formulario (show_pdf_page): el último formulario de la página.
        orden = re.findall(r"/(\w+) Do", b[0].read_contents().decode("latin-1"))
        (jpeg,) = [i[7] for i in b[0].get_images(full=True) if i[8] == "DCTDecode"]
        formularios = [n for n in orden if n.startswith("fzFrm")]
        # plantilla → ortofoto → detalle
        assert orden.index(formularios[0]) < orden.index(jpeg) < orden.index(formularios[-1])
    nuevas = [i for i in imagenes_pdf(entorno / "con.pdf", ALTO) if i["filtro"] == "/DCTDecode"]
    assert len(nuevas) == 1 and nuevas[0]["rect_mm"] == pytest.approx(OCUPADO, abs=0.01)
    ruta_tif = entorno / "fotos" / "orto.tif"
    assert error_de_posicion(nuevas[0], a_cad, ruta_tif) < 4


def test_copia_reducida_al_lado_del_plano(entorno):
    r = componer_plano(plano(entorno), entorno / "p.pdf", config_ortofoto=POCO)
    carpeta = entorno / "planos" / "plano_ortofoto"
    assert r.copia.carpeta == carpeta and r.copia.escrita and r.copia.archivos == 1
    indice = leer_indice(carpeta)
    tif = entorno / "fotos" / "orto.tif"
    assert indice["original"] == {"nombre": "orto.tif", "bytes": tif.stat().st_size,
                                  "modificado": fecha(tif)}
    assert indice["crs_dibujo"] == "EPSG:9377" and indice["ppp"] == 100
    (d,) = indice["detalles"]
    # Página (13 × 6 m) + 10 % por lado, al píxel de la ortofoto (5 cm: más grueso que 100 ppp).
    assert d["id"] == "a" and d["px"] == [312, 144]
    assert (carpeta / d["archivo"]).is_file()
    # Otra vez, sin cambios: la copia ya está al día y no se reescribe.
    otra = componer_plano(plano(entorno), entorno / "p.pdf", sobrescribir=True,
                          config_ortofoto=POCO)
    assert otra.copia.escrita is False


@pytest.mark.parametrize("como", ["falta", "cambia"])
def test_sin_el_original_usa_la_copia_y_avisa(entorno, como):
    componer_plano(plano(entorno), entorno / "p.pdf", config_ortofoto=POCO)
    leido = plano(entorno)  # el plano guarda bytes y fecha del original de ahora
    tif = entorno / "fotos" / "orto.tif"
    if como == "falta":
        shutil.move(tif, entorno / "otro_lugar.tif")
    else:
        estado = tif.stat()
        os.utime(tif, ns=(estado.st_atime_ns, estado.st_mtime_ns + 7_000_000_000))
    r = componer_plano(leido, entorno / "q.pdf", config_ortofoto=POCO)
    assert r.ortofoto.fuente == "copia" and r.copia is None
    aviso = r.advertencias[0]
    assert "se usó la copia reducida" in aviso
    assert ("no se encontró" in aviso) if como == "falta" else ("cambió" in aviso and "fecha" in aviso)
    (imagen,) = [i for i in imagenes_pdf(entorno / "q.pdf", ALTO) if i["filtro"] == "/DCTDecode"]
    original = entorno / "otro_lugar.tif" if como == "falta" else tif
    bien = error_de_posicion(imagen, a_cad, original)  # misma foto, en su sitio (dos JPEG)
    assert bien < 8 and error_de_posicion(imagen, a_cad, original, corrimiento=(1, 0)) > 2 * bien


def test_sin_original_ni_copia_no_se_compone(entorno):
    leido = plano(entorno)
    (entorno / "fotos" / "orto.tif").unlink()
    with pytest.raises(PlanoNoComponible, match="no se encontró .*orto.tif.* y no hay una copia "
                                                "reducida que sirva"):
        componer_plano(leido, entorno / "p.pdf")
    assert not (entorno / "p.pdf").exists()


def test_la_copia_de_otro_sistema_del_dibujo_no_sirve(entorno):
    componer_plano(plano(entorno), entorno / "p.pdf", config_ortofoto=POCO)
    otro = plano(entorno, crs_dibujo="EPSG:3116")
    (entorno / "fotos" / "orto.tif").unlink()
    with pytest.raises(PlanoNoComponible, match="no hay una copia reducida que sirva"):
        componer_plano(otro, entorno / "q.pdf")


def test_sin_sistema_del_dibujo_no_se_compone(entorno):
    with pytest.raises(PlanoNoComponible, match="no dice el sistema de coordenadas del dibujo"):
        componer_plano(plano(entorno, crs_dibujo=None), entorno / "p.pdf")


def test_ortofoto_sin_sistema_usa_el_elegido_en_el_plano(entorno):
    crear_geotiff(entorno / "fotos" / "orto.tif", ancho=400, alto=200, crs=None,
                  origen=(X0_CAD - 2, Y0_CAD + 8), pixel=0.05, sinusoidal=True)
    with pytest.raises(PlanoNoComponible, match="no dice su sistema de coordenadas y el plano "
                                                "no lo eligió"):
        componer_plano(plano(entorno), entorno / "p.pdf")
    r = componer_plano(plano(entorno, crs="EPSG:9377"), entorno / "p.pdf", config_ortofoto=POCO)
    assert r.ortofoto.cobertura == {"a": 1.0}


def test_opacidad_y_paquete_con_fondo(entorno):
    crear_paquete_real(entorno / "input", "a")  # el mismo, ahora con fondo blanco (antiguo)
    r = componer_plano(plano(entorno, opacidad=0.5), entorno / "p.pdf", config_ortofoto=POCO)
    assert any("tiene fondo blanco de página" in a for a in r.advertencias)
    (imagen,) = [i for i in imagenes_pdf(entorno / "p.pdf", ALTO) if i["filtro"] == "/DCTDecode"]
    assert imagen["mascara"] is not None and int(imagen["mascara"].max()) == 128


def test_diferencias():
    plano_ = {"nombre": "a.tif", "bytes": 10, "modificado": "2026-11-18T21:26:25Z"}
    assert diferencias(plano_, {"nombre": "A.TIF", "bytes": 10,
                                "modificado": "2026-11-18T21:26:25Z"}) == []
    assert diferencias({"nombre": "a.tif", "bytes": None, "modificado": None},
                       {"nombre": "a.tif", "bytes": 99, "modificado": "x"}) == []
    assert diferencias(plano_, {"nombre": "a.tif", "bytes": 11, "modificado": "y"}) == [
        "tamaño: el plano dice 10 y es 11", "fecha: el plano dice 2026-11-18T21:26:25Z y es y"]


def test_cli_resume_la_ortofoto(entorno, capsys):
    p = plano(entorno)
    assert main(["componer", str(p.ruta), "--salida", str(entorno / "p.pdf")]) == 0
    salida = capsys.readouterr().out
    assert "Ortofoto (el original:" in salida and "a 300 ppp, calidad 85, opacidad 100 %" in salida
    assert "a: 3071 × 1417 px, cubre el 100 % de su página" in salida
    assert "Copia reducida escrita:" in salida
    assert "los 6 mosaico(s) de la ortofoto (los detalles siguen siendo vectores)" in salida
    assert "cada mosaico de la ortofoto es JPEG y está en su sitio (±0,1 mm)" in salida
