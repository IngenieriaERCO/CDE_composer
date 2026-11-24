"""Cliente del protocolo 1.0 del trabajador, contra el trabajador falso (sin cde-exporter)."""

import shutil
import sys
import threading
import time
from pathlib import Path

import pytest
from conftest import comando_falso, dxf_falso

from componedor.trabajador import (
    ARCHIVO_NOTAS,
    ErrorTrabajador,
    Trabajador,
    TrabajadorCaido,
    TrabajadorNoDisponible,
    resolver_comando,
)


@pytest.fixture
def trabajador(tmp_path):
    t = Trabajador(comando_falso(), tmp_path / "trabajo")
    t.iniciar()
    yield t
    t.cerrar()


def cargar(t, ruta, **kw):
    return t.pedir("load", {"dxf": str(ruta), "units": None, "margin_mm": 5.0}, **kw)


def test_arranca_y_presenta_sus_versiones(trabajador, tmp_path):
    assert trabajador.vivo
    assert trabajador.listo["protocol_version"] == "1.1"
    assert trabajador.listo["manifest_schema_version"] == "1.3"
    assert trabajador.listo["work_dir"] == str((tmp_path / "trabajo").resolve())


def test_cargar_con_avance_y_nombres_con_tildes(trabajador, tmp_path):
    ruta = dxf_falso(tmp_path / "Obra Ñandú.dxf",
                     blocks=[{"name": "Pilar Ø0,30 — esquina", "size_cad": [0.4, 0.8]}])
    avances = []
    r = cargar(trabajador, ruta, al_avance=avances.append)
    assert [a["stage"] for a in avances] == ["read", "hash", "blocks", "layers"]
    assert avances[-1]["percent"] == 100.0 and "Ñandú" in avances[0]["message"]
    assert r["dxf"]["name"] == "Obra Ñandú.dxf"
    assert r["blocks"][0]["name"] == "Pilar Ø0,30 — esquina"
    assert r["blocks"][0]["ref"] == "Pilar Ø0,30 — esquina#1"


def test_load_como_dice_el_contrato_final(trabajador, tmp_path):
    """Contrato final (2026-11-17): handle en hexadecimal y mayúsculas, file_stem ya válido
    (§5.1), bounds_with_hidden e include_layers."""
    largo = "HSS-Tubo estructural redondo - Tubo metálico galvanizado Ø2 e 1,9mm-4445096-ISOMÉTRICO"
    ruta = dxf_falso(tmp_path / "a.dxf", blocks=[
        {"name": largo, "size_cad": [1.0, 2.0]},
        {"name": "Pilar Ñ", "size_cad": [1.0, 2.0], "hidden_layer_entities": 3},
        {"name": "Pilar Ñ", "size_cad": [1.0, 2.0]}])
    con = cargar(trabajador, ruta)
    sin = trabajador.pedir("load", {"dxf": str(ruta), "units": None, "margin_mm": 5.0,
                                    "include_layers": False})
    assert len(con["layers"]) == 1 and sin["layers"] == []
    b = sin["blocks"]
    assert [x["handle"] for x in b] == ["1A0", "1A1", "1A2"]
    assert all(x["handle"] == x["handle"].upper() for x in b)
    assert len(b[0]["file_stem"]) == 60 and b[0]["file_stem"].startswith("HSS-Tubo_estructural")
    assert [x["file_stem"] for x in b[1:]] == ["Pilar_N_001", "Pilar_N_002"]
    assert b[0]["bounds_with_hidden"] is None and b[1]["bounds_with_hidden"] is not None


def test_status_dice_la_etapa(trabajador, tmp_path):
    ruta = dxf_falso(tmp_path / "a.dxf", no_cancelable_s=1.0)
    hilo = threading.Thread(target=lambda: cargar(trabajador, ruta))
    hilo.start()
    time.sleep(0.3)
    estado = trabajador.estado()
    hilo.join(10)
    assert estado["busy"] is True and estado["stage"] == "read"
    assert trabajador.estado()["stage"] is None


def test_el_registro_va_a_un_archivo(trabajador, tmp_path):
    cargar(trabajador, dxf_falso(tmp_path / "a.dxf"))
    registro = trabajador.ruta_registro.read_text(encoding="utf-8")
    assert "pedido c-1 load" in registro and "worker" in registro


def test_error_del_trabajador_con_mensaje_y_consejo(trabajador, tmp_path):
    with pytest.raises(ErrorTrabajador) as e:
        cargar(trabajador, tmp_path / "no_existe.dxf")
    assert e.value.codigo == "DXF_NOT_FOUND"
    assert "no_existe.dxf" in e.value.mensaje and e.value.consejo == "Revise la ruta del archivo."
    assert e.value.detalles == {"dxf": str(tmp_path / "no_existe.dxf")}
    assert trabajador.vivo  # un error no lo tumba


def test_status_y_cancel_responden_durante_un_paso_que_no_se_corta(trabajador, tmp_path):
    """Punto 4 del contrato: mientras el trabajador lee (no se puede cortar), status y cancel
    se responden enseguida; la cancelación se nota al terminar ese paso."""
    ruta = dxf_falso(tmp_path / "grande.dxf", no_cancelable_s=1.5, demora_s=0.2)
    resultado = {}

    def en_otro_hilo():
        try:
            cargar(trabajador, ruta, id_pedido="c-99")
        except ErrorTrabajador as e:
            resultado["codigo"] = e.codigo

    hilo = threading.Thread(target=en_otro_hilo)
    hilo.start()
    time.sleep(0.3)
    inicio = time.monotonic()
    estado = trabajador.estado()
    assert estado["busy"] is True and estado["current"] == "c-99"
    assert trabajador.cancelar("c-99") is True
    assert time.monotonic() - inicio < 1.0  # no esperó a que terminara la lectura
    hilo.join(10)
    assert resultado == {"codigo": "CANCELLED"}
    assert trabajador.cancelar("c-99") is False  # ya no está en curso


def test_cerrar_termina_limpio(tmp_path):
    t = Trabajador(comando_falso(), tmp_path / "trabajo")
    t.iniciar()
    t.cerrar()
    assert not t.vivo and t._p.proceso.returncode == 0
    with pytest.raises(TrabajadorCaido, match="no está en marcha"):
        t.pedir("status", {})


def test_caida_durante_un_pedido(trabajador, tmp_path):
    with pytest.raises(TrabajadorCaido, match=r"se cerró inesperadamente \(código 3\)") as e:
        cargar(trabajador, dxf_falso(tmp_path / "a.dxf", caer_en_paso=2))
    assert e.value.codigo_salida == 3 and not trabajador.vivo


def test_linea_que_no_es_json_se_ignora_y_se_anota(tmp_path):
    t = Trabajador(comando_falso("--basura"), tmp_path / "trabajo")
    t.iniciar()
    try:
        assert t.estado()["busy"] is False
        notas = (tmp_path / "trabajo" / ARCHIVO_NOTAS).read_text(encoding="utf-8")
        assert "no es JSON" in notas and "esto no es JSON" in notas
    finally:
        t.cerrar()


def test_otra_version_del_protocolo(tmp_path):
    t = Trabajador(comando_falso("--protocolo", "2.0"), tmp_path / "trabajo")
    with pytest.raises(TrabajadorNoDisponible, match="protocolo '2.0'.*versión mayor 1"):
        t.iniciar()
    assert not t.vivo


def test_no_responde_ready(tmp_path):
    t = Trabajador(comando_falso("--sin-ready"), tmp_path / "trabajo", espera_ready_s=1)
    with pytest.raises(TrabajadorNoDisponible, match="no respondió en 1 s"):
        t.iniciar()
    assert t._p.proceso.poll() is not None  # quedó detenido


def test_exportador_sin_la_orden_worker(tmp_path):
    """Un cde-exporter viejo (sin trabajador) termina con el error de argparse."""
    viejo = tmp_path / "viejo.py"
    viejo.write_text("import sys\nsys.stderr.write(\"cde-exporter: error: argument command: "
                     "invalid choice: 'worker'\\n\")\nsys.exit(2)\n", encoding="utf-8")
    t = Trabajador((sys.executable, str(viejo)), tmp_path / "trabajo")
    with pytest.raises(TrabajadorNoDisponible, match="no tiene la orden «worker»"):
        t.iniciar()


def test_otro_motivo_de_salida_muestra_el_registro(tmp_path):
    malo = tmp_path / "malo.py"
    malo.write_text("import sys\nsys.stderr.write('falta una biblioteca\\n')\nsys.exit(5)\n",
                    encoding="utf-8")
    t = Trabajador((sys.executable, str(malo)), tmp_path / "trabajo")
    with pytest.raises(TrabajadorNoDisponible, match=r"(?s)código 5\).*falta una biblioteca"):
        t.iniciar()


@pytest.mark.skipif(shutil.which("cde-exporter") is None, reason="cde-exporter no instalado")
def test_cde_exporter_instalado_sin_worker_o_con_worker(tmp_path):
    """Con el cde-exporter real: si todavía no tiene la orden worker, el mensaje lo dice; si ya
    la tiene, arranca y habla el protocolo 1."""
    t = Trabajador(("cde-exporter",), tmp_path / "trabajo")
    try:
        listo = t.iniciar()
    except TrabajadorNoDisponible as e:
        assert "no tiene la orden «worker»" in str(e)
    else:
        assert listo["protocol_version"].split(".")[0] == "1"
    finally:
        t.cerrar()


def test_resolver_comando(tmp_path):
    assert resolver_comando((sys.executable, "-x"))[1:] == ["-x"]
    with pytest.raises(TrabajadorNoDisponible, match="No se encontró el comando «no-existe-xyz»"):
        resolver_comando(("no-existe-xyz",))
    with pytest.raises(TrabajadorNoDisponible, match="No hay comando"):
        resolver_comando(())


# --- preview (etapa 2) -----------------------------------------------------------------------

def previar(t, sesion, ref, **kw):
    return t.pedir("preview", {"session": sesion, "ref": ref, "long_side_px": 300,
                               "include_hidden_layers": None}, **kw)


def test_preview_png_transparente_con_la_marca_donde_dice_la_matriz(trabajador, tmp_path):
    """El PNG del falso tiene un cuadrito en el punto CAD «marca»: cad_to_px lo ubica."""
    import pymupdf

    ruta = dxf_falso(tmp_path / "a.dxf", blocks=[
        {"name": "B", "size_cad": [40.0, 20.0], "min": [1000.0, 2000.0], "marca": [1010.0, 2015.0]}])
    sesion = cargar(trabajador, ruta)["session"]
    avances = []
    p = previar(trabajador, sesion, "B#1", al_avance=avances.append)
    assert [a["stage"] for a in avances] == ["draw", "paint"]
    a, b, c, d, e, f = p["cad_to_px"]
    assert b == c == 0 and a == -d == 300 / 40.0
    assert p["px"] == [300, 150] and p["cached"] is False
    assert p["png"].endswith("1A0_300_visible.png") and "previews" in p["png"]
    pix = pymupdf.Pixmap(p["png"])
    assert (pix.width, pix.height, pix.alpha) == (300, 150, 1)
    px, py = int(a * 1010.0 + e), int(d * 2015.0 + f)  # (75, 37)
    assert pix.pixel(px, py) == (0, 0, 0, 255)
    assert pix.pixel(0, 0)[3] == 0 and pix.pixel(px + 5, py)[3] == 0  # el resto, transparente
    assert previar(trabajador, sesion, "B#1")["cached"] is True


def test_preview_por_handle_solo_como_el_contrato(trabajador, tmp_path):
    """El falso acepta el handle solo (sin block), como el real desde 92c2c37: sin distinguir
    mayúsculas; NOT_EXPORTABLE si es de omitted y REFERENCE_NOT_FOUND si no existe."""
    ruta = dxf_falso(tmp_path / "a.dxf", blocks=[
        {"name": "*U76", "anonimo": True, "layer": "PV", "handle": "12A00", "visible_entities": 500},
        {"name": "*U77", "anonimo": True, "layer": "COTAS", "handle": "3F", "visible_entities": 2}])
    sesion = cargar(trabajador, ruta)["session"]
    pedir = lambda handle: trabajador.pedir("preview", {
        "session": sesion, "handle": handle, "long_side_px": 300, "include_hidden_layers": None})
    assert pedir("12a00")["px"][0] == 300
    for handle, codigo in (("3F", "NOT_EXPORTABLE"), ("FFFF", "REFERENCE_NOT_FOUND")):
        with pytest.raises(ErrorTrabajador) as e:
            pedir(handle)
        assert e.value.codigo == codigo


def test_preview_sin_sesion_o_con_el_dxf_cambiado(trabajador, tmp_path):
    ruta = dxf_falso(tmp_path / "a.dxf")
    with pytest.raises(ErrorTrabajador) as e:
        previar(trabajador, "s-1", "B1#1")
    assert e.value.codigo == "NO_SESSION"
    sesion = cargar(trabajador, ruta)["session"]
    with pytest.raises(ErrorTrabajador) as e:
        previar(trabajador, "s-viejo", "B1#1")
    assert e.value.codigo == "NO_SESSION"
    with pytest.raises(ErrorTrabajador) as e:
        previar(trabajador, sesion, "NO#1")
    assert e.value.codigo == "REFERENCE_NOT_FOUND"
    ruta.write_text(ruta.read_text(encoding="utf-8") + " ", encoding="utf-8")  # AutoCAD guardó
    with pytest.raises(ErrorTrabajador) as e:
        previar(trabajador, sesion, "B1#1")
    assert e.value.codigo == "DXF_CHANGED" and e.value.consejo == "Vuelva a cargarlo."


def test_opciones_despues_de_work_dir(tmp_path):
    t = Trabajador(comando_falso(), tmp_path / "trabajo", opciones=("--preview-cache-mb", "7"))
    t.iniciar()
    try:
        assert "'--preview-cache-mb', '7'" in t.ruta_registro.read_text(encoding="utf-8")
    finally:
        t.cerrar()


@pytest.mark.skipif(shutil.which("cde-exporter") is None, reason="cde-exporter no instalado")
def test_cde_exporter_real_con_guamo(tmp_path):
    """Con el exportador real y GUAMO_prueba.dxf (fuera de git): load y, si ya existe, preview.
    La ruta se puede cambiar con la variable COMPONEDOR_DXF_REAL."""
    import os

    from conftest import ZONA_A1

    from componedor.bloques_dxf import catalogo_dxf
    from componedor.previa_dxf import leer_previa, pedido_previa

    dxf = Path(os.environ.get("COMPONEDOR_DXF_REAL", Path(__file__).parents[2]
                              / "Exportador Vectorial" / "data" / "input" / "GUAMO_prueba.dxf"))
    if not dxf.is_file():
        pytest.skip(f"no está {dxf}")
    t = Trabajador(("cde-exporter",), tmp_path / "trabajo", espera_ready_s=90)
    try:
        try:
            t.iniciar()
        except TrabajadorNoDisponible as e:
            pytest.skip(str(e))
        datos = t.pedir("load", {"dxf": str(dxf), "units": None, "margin_mm": 5.0,
                                 "include_layers": False}, espera_s=300)
        carpeta = catalogo_dxf(datos, ZONA_A1)
        assert carpeta["bloques"] and not carpeta["problemas"]
        assert all(b["caja_cad"] is not None for b in carpeta["bloques"])
        # El bloque más chico (la vista previa más rápida).
        b = min(carpeta["bloques"], key=lambda x: (x["entidades"] or 0))
        try:
            r = t.pedir("preview", pedido_previa(carpeta["sesion"], b["handle"]), espera_s=300)
        except ErrorTrabajador as e:
            if e.codigo == "UNKNOWN_COMMAND":
                pytest.skip("el trabajador real todavía no tiene «preview» (etapa 2 del "
                            "exportador)")
            raise
        previa = leer_previa(r, tmp_path / "trabajo" / "previews")  # cumple el contrato
        assert max(previa["px"]) == 1500 and previa["png"].is_file()
        import pymupdf

        pix = pymupdf.Pixmap(str(previa["png"]))
        assert pix.alpha == 1 and [pix.width, pix.height] == previa["px"]  # fondo transparente
        # Mismo marco que load: lo dibujado cae dentro de la caja del bloque (puede ser menor,
        # p. ej. sin los 3DSOLID). Tolerancia: medio píxel.
        tol = 0.5 / previa["cad_a_px"][0]
        (x0, y0), (x1, y1) = b["caja_cad"]["min"], b["caja_cad"]["max"]
        (p0, q0), (p1, q1) = previa["caja_cad"]["min"], previa["caja_cad"]["max"]
        assert x0 - tol <= p0 <= p1 <= x1 + tol and y0 - tol <= q0 <= q1 <= y1 + tol
        # Lo que de verdad se dibujó (píxeles no transparentes), llevado a CAD con cad_to_px,
        # cae dentro de la caja de load (±1 px): el PNG se puede poner por coordenadas CAD.
        ma, _, _, md, me, mf = previa["cad_a_px"]
        opacos = [(x, y) for y in range(0, pix.height, 2) for x in range(0, pix.width, 2)
                  if pix.pixel(x, y)[3] > 0]
        assert opacos, "el PNG real no tiene nada dibujado"
        xs = [(x - me) / ma for x, _ in opacos] + [(x + 1 - me) / ma for x, _ in opacos]
        ys = [(y - mf) / md for _, y in opacos] + [(y + 1 - mf) / md for _, y in opacos]
        un_px = 1 / ma
        assert x0 - 2 * un_px <= min(xs) and max(xs) <= x1 + 2 * un_px
        assert y0 - 2 * un_px <= min(ys) and max(ys) <= y1 + 2 * un_px
        # La segunda vez sale de la caché.
        assert t.pedir("preview", pedido_previa(carpeta["sesion"], b["handle"]))["cached"] is True
    finally:
        t.cerrar()
