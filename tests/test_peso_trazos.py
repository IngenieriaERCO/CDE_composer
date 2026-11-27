"""La verificación final de componer cuenta los trazos por peso: relleno y borde por separado
(un «fs» vale 2). Así no falla cuando get_drawings() junta, al insertar la página en la hoja, un
relleno y un borde del mismo camino que en la página suelta salían separados (pasó con una zona
de PRGD-25 en PLANO-PILOTO-FINAL, hoja 2). Un trazo realmente perdido sigue fallando."""

import json

import pymupdf
import pytest
from conftest import crear_paquete_real, crear_plantilla_sintetica, escribir_formato

from componedor import componer
from componedor.colocar import insertar_pagina
from componedor.componer import PlanoNoComponible, componer_plano
from componedor.comprobacion_dibujo import cortar_por_peso, peso_trazo, peso_trazos
from componedor.formato import cargar_formato
from componedor.plano import leer_plano

# Relleno par-impar y luego borde de «la misma» figura: el primer punto del relleno difiere en
# 0,00002 pt (como en el PDF del exportador). Dentro del dibujo del paquete sintético.
FIGURA = (b"\nq 0.5 g 300.00002 150 m 350 150 l 350 200 l h f* Q "
          b"q 1 j 1 J 0 G 0.5 w 300 150 m 350 150 l 350 200 l h S Q\n")


def _con_figura(pdf):
    doc = pymupdf.open(pdf)
    pagina = doc[0]
    xref = doc.get_new_xref()
    doc.update_object(xref, "<<>>")
    doc.update_stream(xref, FIGURA)
    contenidos = " ".join(f"{c} 0 R" for c in pagina.get_contents())
    doc.xref_set_key(pagina.xref, "Contents", f"[{contenidos} {xref} 0 R]")
    datos = doc.tobytes()
    doc.close()
    return datos


@pytest.fixture
def entorno(tmp_path):
    escribir_formato(tmp_path / "formato.json", plantilla=crear_plantilla_sintetica(tmp_path / "r.pdf"))
    plano_pdf = crear_paquete_real(tmp_path / "base", "plano", sin_fondo=True)
    crear_paquete_real(tmp_path / "input", "fig", sin_fondo=True, contenido=_con_figura(plano_pdf))
    return tmp_path, plano_pdf


def _plano(carpeta, pos):
    ruta = carpeta / "plano.json"
    ruta.write_text(json.dumps({"version": 2, "formato": "formato.json", "detalles": [
        {"id": "fig", "manifiesto": "input/fig.manifest.json", "posicion_mm": list(pos)}]}), encoding="utf-8")
    return leer_plano(ruta)


def test_peso_y_corte():
    f, s, fs = {"type": "f"}, {"type": "s"}, {"type": "fs"}
    assert [peso_trazo(x) for x in (f, s, fs, {"type": None})] == [1, 1, 2, 1]
    assert peso_trazos([f, s, fs]) == 4
    assert cortar_por_peso([s, fs, f, s], [1, 2, 2]) == [[s], [fs], [f, s]]
    assert cortar_por_peso([s, f, s], [1, 2]) == [[s], [f, s]]  # «f» + «s» = el mismo peso que «fs»
    assert cortar_por_peso([s, fs], [1, 1]) is None  # no cuadra: un trazo de más
    assert cortar_por_peso([s, f], [1, 2]) is None  # un trazo perdido


def test_relleno_y_luego_borde_que_se_juntan_al_insertar(entorno):
    """La página suelta tiene «f» y «s»; en la hoja (en esta posición) get_drawings() los junta en
    «fs». Antes la verificación decía «falta un trazo»; con el peso, compone."""
    carpeta, _ = entorno
    formato = cargar_formato(carpeta / "formato.json", usar_plantilla=False)
    with pymupdf.open(carpeta / "input" / "fig.pdf") as src:
        suelta = [d["type"] for d in src[0].get_drawings()]
        hoja = pymupdf.open()
        pagina = hoja.new_page(width=formato.ancho_mm * 72 / 25.4, height=formato.alto_mm * 72 / 25.4)
        insertar_pagina(pagina, formato, src, 0, (400, 300))
        en_hoja = [d["type"] for d in pagina.get_drawings()]
    assert suelta[-2:] == ["f", "s"] and en_hoja[-1] == "fs" and len(en_hoja) == len(suelta) - 1
    r = componer_plano(_plano(carpeta, (400, 300)), carpeta / "p.pdf")
    assert r.detalles[0].id == "fig" and (carpeta / "p.pdf").is_file()


def test_un_trazo_realmente_perdido_sigue_fallando(entorno, monkeypatch):
    """Si en la hoja falta un trazo de verdad (aquí: se inserta la página sin la figura), no se
    genera el PDF."""
    carpeta, sin_figura = entorno
    original = componer.insertar_pagina

    def sin_la_figura(hoja, formato, doc, pagina, posicion, recorte=None):
        with pymupdf.open(sin_figura) as otro:
            return original(hoja, formato, otro, 0, posicion, recorte)

    monkeypatch.setattr(componer, "insertar_pagina", sin_la_figura)
    with pytest.raises(PlanoNoComponible) as e:
        componer_plano(_plano(carpeta, (30, 300)), carpeta / "p.pdf")
    assert "no se pudo separar el dibujo de cada detalle" in str(e.value)
    assert "(relleno y borde por separado)" in str(e.value)
    assert not (carpeta / "p.pdf").exists()
