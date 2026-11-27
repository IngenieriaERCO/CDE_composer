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


def test_copia_automatica(tmp_path):
    """8d: <proyecto>.autoguardado.json nunca pisa el real; se lista con «más nueva»; se lee, y
    se borra; no se lista como plano."""
    import os

    p = PlanosEditor(tmp_path)
    p.guardar("Obra.json", _texto(titulo="GUARDADO"))
    real = (tmp_path / "Obra.json").read_bytes()
    os.utime(tmp_path / "Obra.json", (1_000_000, 1_000_000))  # el real, más viejo
    p.guardar_autoguardado("Obra", "Obra.json", False, _texto(titulo="SIN GUARDAR"))
    assert (tmp_path / "Obra.json").read_bytes() == real  # el real no se toca
    assert p.listar()["planos"] == ["Obra.json"]  # la copia no es un plano
    (copia,) = p.autoguardados()["autoguardados"]
    assert (copia["base"], copia["archivo"], copia["viejo"], copia["mas_nueva"]) == ("Obra", "Obra.json", False, True)
    r = p.leer_autoguardado("Obra")
    assert json.loads(r["texto"])["rotulo"] == {"titulo": "SIN GUARDAR"} and r["archivo"] == "Obra.json"
    # Una copia de un plano viejo recuerda que lo era; una sin archivo (nunca guardado), también se ofrece.
    p.guardar_autoguardado("sin_nombre", None, True, _texto())
    nuevas = {c["base"]: c for c in p.autoguardados()["autoguardados"]}
    assert nuevas["sin_nombre"]["mas_nueva"] is True and nuevas["sin_nombre"]["viejo"] is True
    # Si el real es más nuevo que la copia, no se ofrece.
    os.utime(tmp_path / "Obra.json", None)
    os.utime(tmp_path / "Obra.autoguardado.json", (1_000_000, 1_000_000))
    assert {c["base"]: c["mas_nueva"] for c in p.autoguardados()["autoguardados"]}["Obra"] is False
    assert p.borrar_autoguardado("Obra") == {"borrado": True} and not (tmp_path / "Obra.autoguardado.json").exists()
    assert p.borrar_autoguardado("Obra") == {"borrado": False}
    for malo in ("../x", "a/b", ""):
        with pytest.raises(ErrorAplicacion):
            p.guardar_autoguardado(malo, None, False, _texto())
    with pytest.raises(ErrorAplicacion) as e:
        p.leer_autoguardado("Obra")
    assert e.value.estado_http == 404
