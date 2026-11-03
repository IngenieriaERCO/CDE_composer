"""Localizar paquetes y emparejar archivos (datos sintéticos en tmp_path, no de ERCO).

Los PDF son bytes ficticios: en la 2.2 no se abren ni se calcula su hash.
"""

import pytest

from componedor.cli import main
from componedor.paquete import (
    COMPLETO,
    INCOMPLETO,
    INVALIDO,
    CarpetaInvalida,
    localizar_paquetes,
)
from conftest import escribir_json, manifiesto_paquete


def _paquete(carpeta, prefijo, pdf=True, txt=True, nombre_pdf=None, **kw_manifiesto):
    """Escribe <prefijo>.manifest.json (+ PDF y TXT). El PDF se llama `nombre_pdf`
    (por defecto <prefijo>.pdf) y el manifiesto lo declara en pdf.file_name."""
    carpeta.mkdir(parents=True, exist_ok=True)
    nombre_pdf = nombre_pdf or f"{prefijo}.pdf"
    cambiar = {"pdf.file_name": nombre_pdf, **kw_manifiesto.pop("cambiar", {})}
    escribir_json(carpeta / f"{prefijo}.manifest.json",
                  manifiesto_paquete(cambiar=cambiar, **kw_manifiesto))
    if pdf:
        (carpeta / nombre_pdf).write_bytes(b"%PDF-ficticio")
    if txt:
        (carpeta / f"{prefijo}.txt").write_text("informe", encoding="utf-8")


def _por_prefijo(paquetes):
    return {p.prefijo: p for p in paquetes}


def test_paquete_completo_con_y_sin_txt(tmp_path):
    _paquete(tmp_path, "con_txt")
    _paquete(tmp_path, "sin_txt", txt=False)
    p = _por_prefijo(localizar_paquetes(tmp_path))
    assert p["con_txt"].estado == COMPLETO and p["con_txt"].ruta_txt == tmp_path / "con_txt.txt"
    assert p["sin_txt"].estado == COMPLETO and p["sin_txt"].ruta_txt is None
    assert p["sin_txt"].problemas == []  # el TXT es opcional
    assert p["con_txt"].ruta_pdf == tmp_path / "con_txt.pdf"
    assert p["con_txt"].manifiesto.escala.denominador == 50.0


def test_manifiesto_sin_pdf(tmp_path):
    _paquete(tmp_path, "solo_manifiesto", pdf=False)
    (p,) = localizar_paquetes(tmp_path)
    assert p.estado == INCOMPLETO and p.ruta_pdf is None
    assert p.problemas == ["falta el PDF 'solo_manifiesto.pdf' (indicado en pdf.file_name): "
                           "paquete incompleto"]


def test_pdf_sin_manifiesto(tmp_path):
    (tmp_path / "cortado.pdf").write_bytes(b"%PDF")
    (tmp_path / "cortado.txt").write_text("informe", encoding="utf-8")
    (p,) = localizar_paquetes(tmp_path)
    assert (p.prefijo, p.estado, p.ruta_manifiesto) == ("cortado", INCOMPLETO, None)
    assert p.problemas[0].startswith("PDF sin manifiesto: no se usa")


def test_manifiesto_invalido_junto_a_uno_valido(tmp_path):
    _paquete(tmp_path, "bueno")
    _paquete(tmp_path, "malo", quitar=["scale"], cambiar={"pdf.page_count": 0})
    (tmp_path / "roto.manifest.json").write_text("{ no es json", encoding="utf-8")
    p = _por_prefijo(localizar_paquetes(tmp_path))
    assert p["bueno"].estado == COMPLETO
    assert p["malo"].estado == INVALIDO
    assert "scale: falta el campo" in p["malo"].problemas
    assert "pdf.page_count: debe ser al menos 1; tiene 0" in p["malo"].problemas
    assert p["malo"].ruta_pdf == tmp_path / "malo.pdf"  # su PDF no sale como huérfano
    assert p["roto"].estado == INVALIDO
    assert "no es un JSON válido" in p["roto"].problemas[0]
    assert len(p) == 3


def test_file_name_distinto_del_prefijo(tmp_path):
    _paquete(tmp_path, "detalle_a", nombre_pdf="otro_nombre.pdf")
    (p,) = localizar_paquetes(tmp_path)
    assert p.estado == COMPLETO and p.ruta_pdf == tmp_path / "otro_nombre.pdf"


def test_carpeta_con_pdf_de_otro_nombre(tmp_path):
    _paquete(tmp_path, "detalle_b", pdf=False, nombre_pdf="esperado.pdf")
    (tmp_path / "detalle_b.pdf").write_bytes(b"%PDF")
    (p,) = localizar_paquetes(tmp_path)  # el PDF del prefijo no sale aparte como huérfano
    assert p.estado == INCOMPLETO and p.ruta_pdf is None
    assert p.problemas == ["pdf.file_name: el manifiesto indica 'esperado.pdf' pero la carpeta "
                           "tiene 'detalle_b.pdf'"]


def test_prefijos_numerados(tmp_path):
    for n in ("_002", "_001", "_010"):
        _paquete(tmp_path, f"perfil{n}")
    paquetes = localizar_paquetes(tmp_path)
    assert [p.prefijo for p in paquetes] == ["perfil_001", "perfil_002", "perfil_010"]
    assert all(p.estado == COMPLETO for p in paquetes)
    assert paquetes[0].ruta_pdf.name == "perfil_001.pdf"


def test_archivos_extra_y_pdf_suelto_se_ignoran(tmp_path):
    _paquete(tmp_path, "detalle")
    for extra in ("detalle.dxf", "detalle.svg", "notas.docx", "prueba_suelta.pdf", "LEEME.txt"):
        (tmp_path / extra).write_bytes(b"x")
    paquetes = localizar_paquetes(tmp_path)
    assert [(p.prefijo, p.estado, p.problemas) for p in paquetes] == [("detalle", COMPLETO, [])]


def test_recursivo_y_no_recursivo(tmp_path):
    _paquete(tmp_path, "raiz")
    _paquete(tmp_path / "sub", "hijo")
    _paquete(tmp_path / "sub" / "nieto", "profundo", pdf=False)
    assert [p.prefijo for p in localizar_paquetes(tmp_path)] == ["raiz"]
    paquetes = localizar_paquetes(tmp_path, recursivo=True)
    assert [p.prefijo for p in paquetes] == ["raiz", "hijo", "profundo"]
    # El PDF se busca en la MISMA carpeta del manifiesto.
    assert paquetes[1].ruta_pdf == tmp_path / "sub" / "hijo.pdf"
    assert paquetes[2].estado == INCOMPLETO


def test_pdf_en_otra_carpeta_no_cuenta(tmp_path):
    _paquete(tmp_path / "a", "detalle", pdf=False)
    (tmp_path / "detalle.pdf").write_bytes(b"%PDF")  # en la carpeta de arriba, no al lado
    (p,) = localizar_paquetes(tmp_path, recursivo=True)
    assert p.estado == INCOMPLETO


def test_carpeta_inexistente_o_archivo(tmp_path):
    with pytest.raises(CarpetaInvalida, match="No existe la carpeta"):
        localizar_paquetes(tmp_path / "no_existe")
    archivo = tmp_path / "archivo.txt"
    archivo.write_text("x", encoding="utf-8")
    with pytest.raises(CarpetaInvalida, match="no es una carpeta"):
        localizar_paquetes(archivo)


def test_carpeta_vacia(tmp_path):
    assert localizar_paquetes(tmp_path) == []


# --- CLI paquetes ------------------------------------------------------------------------

def test_cli_todos_completos(tmp_path, capsys):
    _paquete(tmp_path, "detalle_001")
    _paquete(tmp_path, "detalle_002", txt=False)
    assert main(["paquetes", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "Prefijo" in out and "Estado" in out and "Bloque" in out and "Página (mm)" in out
    assert "detalle_001  completo  DETALLE_PRUEBA  1:50    260.00 x 120.00" in out
    assert "Problemas:" not in out
    assert "2 paquete(s): 2 completo(s), 0 incompleto(s), 0 inválido(s)." in out


def test_cli_con_problemas(tmp_path, capsys):
    _paquete(tmp_path, "bueno")
    _paquete(tmp_path, "sin_pdf", pdf=False)
    _paquete(tmp_path / "sub", "malo", cambiar={"schema_version": "2.0"})
    assert main(["paquetes", str(tmp_path), "--recursivo"]) == 1
    out = capsys.readouterr().out
    assert "sub/malo" in out
    assert "  sin_pdf (incompleto):\n    - falta el PDF 'sin_pdf.pdf'" in out
    assert "  sub/malo (invalido):\n    - schema_version: versión 2.0 no soportada" in out
    assert "3 paquete(s): 1 completo(s), 1 incompleto(s), 1 inválido(s)." in out


def test_cli_carpeta_vacia_e_inexistente(tmp_path, capsys):
    assert main(["paquetes", str(tmp_path)]) == 0
    assert "No se encontraron paquetes (<prefijo>.manifest.json)" in capsys.readouterr().out
    assert main(["paquetes", str(tmp_path / "no_hay")]) == 1
    assert "No existe la carpeta" in capsys.readouterr().err


def test_pdf_sueltos_se_devuelven_aparte(tmp_path):
    from componedor.paquete import localizar_con_sueltos

    _paquete(tmp_path, "detalle")
    (tmp_path / "suelto.pdf").write_bytes(b"%PDF")
    (tmp_path / "cortado.pdf").write_bytes(b"%PDF")
    (tmp_path / "cortado.txt").write_text("x", encoding="utf-8")  # PDF + TXT: no es suelto
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "otro.pdf").write_bytes(b"%PDF")
    paquetes, sueltos = localizar_con_sueltos(tmp_path)
    assert [p.prefijo for p in paquetes] == ["cortado", "detalle"]
    assert sueltos == [tmp_path / "suelto.pdf"]
    _, sueltos = localizar_con_sueltos(tmp_path, recursivo=True)
    assert sueltos == [tmp_path / "sub" / "otro.pdf", tmp_path / "suelto.pdf"]


def test_cli_solo_pdf_sueltos(tmp_path, capsys):
    (tmp_path / "suelto.pdf").write_bytes(b"%PDF")
    assert main(["paquetes", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "No se encontraron paquetes" in out
    assert "PDF sin paquete (ignorados): 1 — suelto.pdf" in out
