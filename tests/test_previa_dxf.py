"""Respuesta de `preview` (§4 del contrato) → datos para poner el PNG en la hoja."""

import pytest

from componedor.previa_dxf import (
    LADO_PX,
    PreviaInvalida,
    leer_previa,
    pedido_previa,
    png_dentro,
)


@pytest.fixture
def carpeta(tmp_path):
    previas = tmp_path / "trabajo" / "previews"
    (previas / "8f0c").mkdir(parents=True)
    (previas / "8f0c" / "50CA_1500_visible.png").write_bytes(b"\x89PNG falso")
    return previas


def respuesta(carpeta, **cambios):
    r = {"png": str(carpeta / "8f0c" / "50CA_1500_visible.png"), "px": [1069, 1500],
         "bounds": {"min": [899699.777, 937885.353], "max": [900656.957, 939235.372]},
         "cad_to_px": [1.0947, 0.0, 0.0, -1.0947, -984891.2, 1026714.6],
         "omitted": {"3DSOLID": 2, "REGION": 0}, "cached": False, "seconds": 10.0}
    r.update(cambios)
    return r


def test_pedido_solo_capas_visibles():
    assert pedido_previa("s-1", "50CA") == {
        "session": "s-1", "handle": "50CA", "long_side_px": LADO_PX,
        "include_hidden_layers": None}
    assert LADO_PX == 1500


def test_respuesta_del_contrato(carpeta):
    p = leer_previa(respuesta(carpeta), carpeta)
    assert p["png"] == (carpeta / "8f0c" / "50CA_1500_visible.png").resolve()
    assert p["px"] == [1069, 1500]
    assert p["caja_cad"] == {"min": [899699.777, 937885.353], "max": [900656.957, 939235.372]}
    assert p["cad_a_px"] == [1.0947, 0.0, 0.0, -1.0947, -984891.2, 1026714.6]
    assert p["omitidos"] == {"3DSOLID": 2}  # solo lo que de verdad falta
    assert p["en_cache"] is False and p["segundos"] == 10.0


@pytest.mark.parametrize("cambio, motivo", [
    ({"px": [0, 10]}, "«px» debe ser"),
    ({"px": [1.5, 10]}, "«px» debe ser"),
    ({"cad_to_px": [1, 0, 0, -1, 0]}, "6 números"),
    ({"cad_to_px": [1, 0.1, 0, -1, 0, 0]}, "no cumple el contrato"),   # con giro
    ({"cad_to_px": [1, 0, 0, -1.01, 0, 0]}, "no cumple el contrato"),  # otra escala en Y
    ({"cad_to_px": [-1, 0, 0, 1, 0, 0]}, "no cumple el contrato"),     # espejo
    ({"bounds": {"min": [0, 0]}}, "«bounds» debe traer"),
    ({"png": None}, "no trae «png»"),
])
def test_respuestas_que_no_cumplen_el_contrato(carpeta, cambio, motivo):
    with pytest.raises(PreviaInvalida, match=motivo):
        leer_previa(respuesta(carpeta, **cambio), carpeta)


def test_el_png_debe_estar_en_la_carpeta_de_previas(carpeta, tmp_path):
    """El servidor solo entrega PNG de la carpeta de vistas previas del trabajador."""
    afuera = tmp_path / "firmas" / "persona" / "firma.png"
    afuera.parent.mkdir(parents=True)
    afuera.write_bytes(b"\x89PNG")
    with pytest.raises(PreviaInvalida, match="no está en la carpeta de vistas previas"):
        png_dentro(str(afuera), carpeta)
    escapada = carpeta / ".." / ".." / "firmas" / "persona" / "firma.png"
    with pytest.raises(PreviaInvalida, match="no está en la carpeta de vistas previas"):
        png_dentro(str(escapada), carpeta)
    with pytest.raises(PreviaInvalida, match="no existe el PNG"):
        png_dentro(str(carpeta / "8f0c" / "otro.png"), carpeta)
    (carpeta / "8f0c" / "datos.json").write_text("{}", encoding="utf-8")
    with pytest.raises(PreviaInvalida, match="no existe el PNG"):
        png_dentro(str(carpeta / "8f0c" / "datos.json"), carpeta)
