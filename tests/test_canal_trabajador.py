"""Canal hacia el trabajador: cola, un pedido a la vez, cancelar, caídas (trabajador falso)."""

import time

import pytest
from conftest import comando_falso, dxf_falso

from componedor.canal_trabajador import (
    CANCELADA,
    DETENIDO,
    EN_COLA,
    FALLIDA,
    FINALES,
    LISTO,
    SIN_INICIAR,
    TERMINADA,
    Canal,
)
from componedor.trabajador import Trabajador


def esperar(tarea, segundos=20):
    fin = time.monotonic() + segundos
    while tarea.estado not in FINALES:
        assert time.monotonic() < fin, f"la tarea quedó en {tarea.estado}"
        time.sleep(0.02)
    return tarea


@pytest.fixture
def canal(tmp_path):
    lanzados = []

    def fabrica():
        t = Trabajador(comando_falso(), tmp_path / "trabajo")
        lanzados.append(t)
        return t

    c = Canal(fabrica, espera_cancelar_s=0.3)
    c.lanzados = lanzados
    yield c
    c.cerrar()


def cargar(canal, ruta, **kw):
    return canal.encolar("cargar_dxf", "load", {"dxf": str(ruta), "units": None,
                                                "margin_mm": 5.0}, **kw)


def test_el_trabajador_se_lanza_al_primer_pedido(canal, tmp_path):
    assert canal.estado()["estado"] == SIN_INICIAR and canal.lanzados == []
    t = esperar(cargar(canal, dxf_falso(tmp_path / "a.dxf")))
    assert t.estado == TERMINADA and t.resultado["blocks"][0]["name"] == "B1"
    assert t.avance["percent"] == 100.0 and t.generacion == 1
    e = canal.estado()
    assert e["estado"] == LISTO and e["listo"]["protocol_version"] == "1.3"
    assert len(canal.lanzados) == 1


def test_un_pedido_a_la_vez_sin_busy(canal, tmp_path):
    """Tres cargas seguidas: el canal las manda de a una (el falso respondería BUSY)."""
    tareas = [cargar(canal, dxf_falso(tmp_path / f"{i}.dxf", demora_s=0.05)) for i in range(3)]
    assert tareas[2].estado == EN_COLA
    for t in tareas:
        assert esperar(t).estado == TERMINADA, t.error
    assert len(canal.lanzados) == 1  # el mismo trabajador para las tres


def test_procesar_convierte_el_resultado_y_un_valueerror_falla(canal, tmp_path):
    ruta = dxf_falso(tmp_path / "a.dxf")
    bien = esperar(cargar(canal, ruta, procesar=lambda d, t: len(d["blocks"])))
    assert bien.resultado == 1

    def mal(data, tarea):
        raise ValueError("falta «blocks»")

    t = esperar(cargar(canal, ruta, procesar=mal))
    assert t.estado == FALLIDA and t.error["codigo"] == "RESPUESTA_INVALIDA"
    assert "falta «blocks»" in t.error["mensaje"]


def test_error_del_trabajador(canal, tmp_path):
    t = esperar(cargar(canal, tmp_path / "no.dxf"))
    assert t.estado == FALLIDA and t.error["codigo"] == "DXF_NOT_FOUND"
    assert t.error["consejo"] == "Revise la ruta del archivo."
    assert canal.estado()["estado"] == LISTO


def test_cancelar_en_cola_y_en_curso(canal, tmp_path):
    lenta = cargar(canal, dxf_falso(tmp_path / "lenta.dxf", demora_s=0.5))
    otra = cargar(canal, dxf_falso(tmp_path / "otra.dxf"))
    assert canal.cancelar(otra.id) and otra.estado == CANCELADA  # en cola: al instante
    while lenta.id_pedido is None or lenta.avance.get("stage") != "read":
        time.sleep(0.02)
    assert canal.cancelar(lenta.id)
    assert esperar(lenta).estado == CANCELADA and lenta.error["codigo"] == "CANCELLED"
    assert not lenta.forzada
    assert canal.cancelar(lenta.id) is False  # ya terminó
    assert canal.cancelar("t-999") is False


def test_cancelar_a_la_fuerza_si_no_se_nota_a_tiempo(canal, tmp_path):
    """El trabajador acepta el cancel pero sigue en un paso que no se corta: pasada la
    espera, el canal lo detiene (Job) y la tarea queda cancelada, sin contar como caída."""
    t = cargar(canal, dxf_falso(tmp_path / "grande.dxf", no_cancelable_s=10))
    while t.generacion is None:  # el pedido ya salió hacia el trabajador
        time.sleep(0.02)
    time.sleep(0.3)
    inicio = time.monotonic()
    canal.cancelar(t.id)
    assert esperar(t).estado == CANCELADA and t.forzada
    assert "a la fuerza" in t.error["mensaje"]
    assert time.monotonic() - inicio < 5
    assert canal.estado()["estado"] == SIN_INICIAR
    siguiente = esperar(cargar(canal, dxf_falso(tmp_path / "a.dxf")))
    assert siguiente.estado == TERMINADA and siguiente.generacion > t.generacion
    assert len(canal.lanzados) == 2


def test_cancel_no_aceptado_no_mata_al_trabajador(tmp_path):
    """El trabajador responde «no aceptado» (su respuesta ya venía en camino): el canal espera
    a que la tarea termine sola y NO lo detiene a la fuerza (se perdería la sesión del DXF)."""
    lanzados = []

    def fabrica():
        t = Trabajador(comando_falso("--cancel-no-aceptado"), tmp_path / "trabajo")
        lanzados.append(t)
        return t

    c = Canal(fabrica, espera_cancelar_s=5)
    try:
        t = cargar(c, dxf_falso(tmp_path / "lenta.dxf", demora_s=0.3))
        while t.id_pedido is None or t.avance.get("stage") != "read":
            time.sleep(0.02)
        assert c.cancelar(t.id)
        assert esperar(t).estado == TERMINADA and not t.forzada
        assert len(lanzados) == 1 and lanzados[0].vivo  # el mismo trabajador, con su sesión
    finally:
        c.cerrar()


def test_dos_caidas_seguidas_detienen_el_canal(canal, tmp_path):
    cae = dxf_falso(tmp_path / "cae.dxf", caer_en_paso=1)
    t1 = esperar(cargar(canal, cae))
    assert t1.estado == FALLIDA and t1.error["codigo"] == "CAIDO"
    assert "código 3" in t1.error["mensaje"] and canal.estado()["estado"] == SIN_INICIAR
    t2 = esperar(cargar(canal, cae))
    assert t2.estado == FALLIDA and canal.estado()["estado"] == DETENIDO
    assert "2 veces seguidas" in canal.estado()["mensaje"]
    t3 = cargar(canal, dxf_falso(tmp_path / "a.dxf"))  # no lanza otro trabajador
    assert t3.estado == FALLIDA and t3.error["codigo"] == "DETENIDO"
    assert len(canal.lanzados) == 2
    canal.reiniciar()
    assert esperar(cargar(canal, dxf_falso(tmp_path / "a.dxf"))).estado == TERMINADA
    assert len(canal.lanzados) == 3


def test_reiniciar_cambia_la_generacion(canal, tmp_path):
    t = esperar(cargar(canal, dxf_falso(tmp_path / "a.dxf")))
    antes = canal.generacion
    assert t.generacion == antes
    canal.reiniciar()
    assert canal.generacion > antes  # la sesión del trabajador anterior ya no existe


def test_trabajador_no_disponible(tmp_path):
    c = Canal(lambda: Trabajador(("no-existe-xyz",), tmp_path / "trabajo"))
    try:
        t = esperar(cargar(c, dxf_falso(tmp_path / "a.dxf")))
        assert t.estado == FALLIDA and t.error["codigo"] == "NO_DISPONIBLE"
        assert "No se encontró el comando «no-existe-xyz»" in t.error["mensaje"]
        assert c.estado()["estado"] == SIN_INICIAR and "no-existe-xyz" in c.estado()["mensaje"]
    finally:
        c.cerrar()


def test_cerrar_detiene_el_trabajador(tmp_path):
    lanzados = []
    c = Canal(lambda: lanzados.append(Trabajador(comando_falso(), tmp_path / "w")) or lanzados[-1])
    esperar(cargar(c, dxf_falso(tmp_path / "a.dxf")))
    pendiente = cargar(c, dxf_falso(tmp_path / "b.dxf", demora_s=5))
    time.sleep(0.3)
    c.cerrar()
    assert not lanzados[0].vivo and lanzados[0]._p.proceso.returncode is not None
    assert pendiente.estado in FINALES
