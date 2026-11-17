"""Cliente del protocolo 1.0 del trabajador, contra el trabajador falso (sin cde-exporter)."""

import shutil
import sys
import threading
import time

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
    assert trabajador.listo["protocol_version"] == "1.0"
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
