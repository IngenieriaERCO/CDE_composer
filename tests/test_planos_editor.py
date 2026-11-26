"""Los planos de la carpeta del editor para «Nueva hoja a partir de esta» (planos_editor.py):
solo archivos .json de esa carpeta, una hoja nueva no pisa otra, el índice y los automáticos."""

import json

import pytest

from componedor.aplicacion_editor import ErrorAplicacion
from componedor.planos_editor import PlanosEditor

CAMPOS = {"hoja": "hoja_actual", "de": "total_hojas", "no_plano": "numero_siguiente"}


def _texto(**rotulo):
    return json.dumps({"version": 7, "formato": "f.json", "detalles": [], "rotulo": rotulo})


def test_guardar_leer_y_listar(tmp_path):
    p = PlanosEditor(tmp_path)
    p.guardar("Plano.json", _texto(no_plano="PL-106"))
    assert p.leer("Plano.json")["texto"] == _texto(no_plano="PL-106")
    assert b"\r\n" not in (tmp_path / "Plano.json").read_bytes()
    with pytest.raises(ErrorAplicacion) as e:  # una hoja nueva no pisa otra
        p.guardar("Plano.json", _texto(), nuevo=True)
    assert e.value.estado_http == 409
    p.guardar("Plano.json", _texto(no_plano="PL-200"))  # guardar la misma hoja sí
    for malo in ("../x.json", "sub/x.json", "C:\\x.json", "x.txt", "p.hojas.json", ""):
        with pytest.raises(ErrorAplicacion) as e:
            p.guardar(malo, _texto())
        assert e.value.estado_http == 400
    for texto in ("{", "[]", json.dumps({"sin": "version"}), None):
        with pytest.raises(ErrorAplicacion):
            p.guardar("y.json", texto)
    with pytest.raises(ErrorAplicacion) as e:
        p.leer("no_esta.json")
    assert e.value.estado_http == 404
    p.guardar("Plano_02.json", _texto())
    p.guardar_indice("Plano", ["Plano.json", "Plano_02.json"])
    assert p.listar() == {"planos": ["Plano.json", "Plano_02.json"],
                          "indices": {"Plano": ["Plano.json", "Plano_02.json"]}}


def test_hojas_y_automaticos(tmp_path):
    p = PlanosEditor(tmp_path)
    p.guardar("A.json", _texto(no_plano="ERCO-PL-106"))
    assert p.hojas("A.json", campos=CAMPOS)["indice"] is None
    p.guardar("A_02.json", _texto())
    with pytest.raises(ErrorAplicacion) as e:  # todas las hojas del índice deben existir
        p.guardar_indice("A", ["A.json", "A_03.json"])
    assert e.value.estado_http == 404
    p.guardar_indice("A", ["A.json", "A_02.json"])
    r = p.hojas("A_02.json", campos=CAMPOS)
    assert (r["indice"], r["hojas"], r["posicion"], r["existen"]) == ("A", ["A.json", "A_02.json"], 1, [True, True])
    assert r["automaticos"] == {"hoja": "2", "de": "2", "no_plano": "ERCO-PL-107"}
    # El rótulo que manda el editor (sin guardar) manda: «hoja» escrita a mano no se pisa.
    assert p.hojas("A_02.json", {"hoja": "X"}, CAMPOS)["automaticos"] == {"de": "2", "no_plano": "ERCO-PL-107"}
    assert p.hojas("A.json", campos={"hoja": "otra_cosa"})["automaticos"] == {}
