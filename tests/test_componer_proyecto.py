"""Componer todo un proyecto (<proyecto>.hojas.json) en UN PDF: una página por hoja, en orden,
cada una igual a la de su hoja; si una hoja falla no sale nada y se dicen todos los errores."""

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
from componedor.componer_proyecto import (
    ProyectoNoComponible,
    componer_proyecto,
    es_indice,
    nombre_proyecto,
    verificar_proyecto,
)
from componedor.hojas_proyecto import escribir_indice

pytestmark = requiere_arial


def _hoja(carpeta, nombre, rotulo, detalles=(), version=7):
    datos = {"version": version, "formato": "formato.json", "detalles": list(detalles), "rotulo": rotulo}
    (carpeta / nombre).write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def proyecto(tmp_path):
    """Obra: hoja 1 con un detalle y su número; hoja 2 vacía (solo el rótulo); hoja 3 con otro."""
    escribir_formato(tmp_path / "formato.json", plantilla=crear_plantilla_sintetica(tmp_path / "r.pdf"),
                     rotulo=rotulo_a1(fuente={"archivo": str(ARIAL)}))
    crear_paquete_real(tmp_path / "input", "a")
    detalle = {"id": "a", "manifiesto": "input/a.manifest.json", "posicion_mm": [30, 300]}
    _hoja(tmp_path, "Obra.json", {"titulo": "PLANTA", "no_plano": "ERCO-PL-106"}, [detalle], version=2)
    _hoja(tmp_path, "Obra_02.json", {"titulo": "PERFIL"})
    _hoja(tmp_path, "Obra_03.json", {"titulo": "DETALLES"}, [dict(detalle, posicion_mm=[200, 100])])
    escribir_indice(tmp_path, "Obra", ["Obra.json", "Obra_02.json", "Obra_03.json"])
    return tmp_path


def test_nombres():
    assert es_indice("C:/x/Obra.hojas.json") and es_indice("obra.HOJAS.json") and not es_indice("Obra.json")
    assert nombre_proyecto("C:/x/Obra.hojas.json") == "Obra"


def test_un_pdf_con_todas_las_hojas(proyecto):
    salida = proyecto / "salida" / "Obra_proyecto.pdf"
    r = componer_proyecto(proyecto / "Obra.hojas.json", salida)
    assert [h.archivo for h in r.hojas] == ["Obra.json", "Obra_02.json", "Obra_03.json"]
    # Los automáticos de cada hoja: hoja X de 3 y el número siguiente.
    assert [(h.resultado.rotulo["hoja"], h.resultado.rotulo["de"], h.resultado.rotulo["no_plano"])
            for h in r.hojas] == [("1", "3", "ERCO-PL-106"), ("2", "3", "ERCO-PL-107"), ("3", "3", "ERCO-PL-108")]
    with pymupdf.open(salida) as doc:
        assert doc.page_count == 3
        textos = [p.get_text() for p in doc]
        # Sigue siendo vector: la hoja 1 tiene los trazos de su detalle (sin imágenes nuevas).
        assert len(doc[0].get_drawings()) > len(doc[1].get_drawings())
    assert "PLANTA" in textos[0] and "PERFIL" in textos[1] and "DETALLES" in textos[2]
    assert "ERCO-PL-107" in textos[1]
    # La hoja vacía avisa, con su hoja delante; solo queda el PDF del proyecto.
    assert "Hoja 2 de 3 (Obra_02.json) · La hoja no tiene detalles: sale solo el rótulo." in r.advertencias
    assert [p.name for p in (proyecto / "salida").iterdir()] == ["Obra_proyecto.pdf"]
    with pytest.raises(FileExistsError):
        componer_proyecto(proyecto / "Obra.hojas.json", salida)


def test_si_una_hoja_falla_no_sale_nada_y_se_dicen_todas(proyecto):
    (proyecto / "Obra_03.json").write_text(json.dumps({
        "version": 2, "formato": "formato.json",
        "detalles": [{"id": "x", "manifiesto": "input/no_esta.manifest.json", "posicion_mm": [30, 40]}]}),
        encoding="utf-8")
    escribir_indice(proyecto, "Obra", ["Obra.json", "Obra_02.json", "Obra_03.json", "Obra_04.json"])
    salida = proyecto / "Obra_proyecto.pdf"
    with pytest.raises(ProyectoNoComponible) as e:
        componer_proyecto(proyecto / "Obra.hojas.json", salida)
    texto = str(e.value)
    assert "2 de 4 hoja(s) con problemas (no se generó el PDF)" in texto
    assert "- Hoja 3 de 4 (Obra_03.json):" in texto and "no_esta.manifest.json" in texto
    assert "- Hoja 4 de 4 (Obra_04.json): no está el archivo" in texto
    assert not salida.exists()


def test_la_verificacion_ve_el_orden(proyecto, tmp_path_factory):
    """Una página fuera de su lugar no pasa la verificación del PDF unido."""
    r = componer_proyecto(proyecto / "Obra.hojas.json", proyecto / "p.pdf")
    otra = tmp_path_factory.mktemp("hojas")
    rutas = []
    with pymupdf.open(r.ruta_pdf) as doc:
        for i in range(doc.page_count):
            ruta = otra / f"h{i}.pdf"
            with pymupdf.open() as una:
                una.insert_pdf(doc, from_page=i, to_page=i)
                una.save(ruta)
            rutas.append(ruta)
    assert verificar_proyecto(r.ruta_pdf, rutas) == []
    fallas = verificar_proyecto(r.ruta_pdf, [rutas[1], rutas[0], rutas[2]])
    assert fallas[0].startswith("la página 1 no es igual a su hoja")
    assert verificar_proyecto(r.ruta_pdf, rutas[:2]) == ["el PDF tiene 3 página(s) y el proyecto 2 hoja(s)"]


def test_cli_con_el_indice(proyecto, capsys):
    config = proyecto / "componedor.json"
    config.write_text(json.dumps({"version": 1, "formato": "formato.json",
                                  "componer": {"resultados": "resultados"}}), encoding="utf-8")
    assert main(["componer", str(proyecto / "Obra.hojas.json"), "--config", str(config),
                 "--codigo-avisos"]) == 3  # la hoja vacía avisa
    out = capsys.readouterr().out
    assert (proyecto / "resultados" / "Obra_proyecto.pdf").is_file()
    assert "Hoja 2 de 3: Obra_02.json · 0 detalle(s) · No. PLANO ERCO-PL-107 · HOJA 2 DE 3" in out
    assert "3 hoja(s), 3 página(s); 1 con advertencias." in out
    assert main(["componer", str(proyecto / "Obra.hojas.json")]) == 2
    assert "falta --salida" in capsys.readouterr().err
    # Una hoja suelta, como siempre: su propio PDF.
    assert main(["componer", str(proyecto / "Obra_03.json"), "--config", str(config)]) == 0
    assert (proyecto / "resultados" / "Obra_03.pdf").is_file()
