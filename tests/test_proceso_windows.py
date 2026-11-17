"""Job Object: el trabajador (y sus hijos) mueren con el Componedor."""

import ctypes
import subprocess
import sys
import time
from pathlib import Path

import pytest

from componedor.proceso_windows import ES_WINDOWS, cerrar_job, lanzar_en_job

pytestmark = pytest.mark.skipif(not ES_WINDOWS, reason="Job Object solo existe en Windows")

STILL_ACTIVE = 259
# Un proceso que lanza un NIETO (como cde-exporter.exe lanza python.exe) y anota su PID.
CON_NIETO = """
import subprocess, sys, time
n = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
open(sys.argv[1], "w").write(str(n.pid))
time.sleep(120)
"""


def vivo(pid: int) -> bool:
    k = ctypes.WinDLL("kernel32")
    k.OpenProcess.restype = ctypes.c_void_p
    h = k.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    codigo = ctypes.c_ulong()
    try:
        k.GetExitCodeProcess(ctypes.c_void_p(h), ctypes.byref(codigo))
        return codigo.value == STILL_ACTIVE
    finally:
        k.CloseHandle(ctypes.c_void_p(h))


def esperar_archivo(ruta: Path, segundos: float = 15) -> int:
    fin = time.monotonic() + segundos
    while time.monotonic() < fin:
        if ruta.is_file() and ruta.read_text().strip():
            return int(ruta.read_text())
        time.sleep(0.05)
    raise AssertionError(f"no apareció {ruta}")


def esperar_muerte(pid: int, segundos: float = 10) -> bool:
    fin = time.monotonic() + segundos
    while time.monotonic() < fin:
        if not vivo(pid):
            return True
        time.sleep(0.05)
    return False


def test_cerrar_el_job_mata_tambien_al_nieto(tmp_path):
    pid_nieto = tmp_path / "nieto.pid"
    p = lanzar_en_job([sys.executable, "-c", CON_NIETO, str(pid_nieto)])
    assert p.job is not None and p.aviso is None
    nieto = esperar_archivo(pid_nieto)
    assert vivo(p.proceso.pid) and vivo(nieto)
    cerrar_job(p)
    assert esperar_muerte(nieto), "el nieto siguió vivo"
    assert p.proceso.poll() is not None
    cerrar_job(p)  # se puede llamar otra vez sin error


def test_si_el_componedor_muere_el_trabajador_muere(tmp_path):
    """El proceso que lanzó el Job (aquí, uno que hace de servidor) muere a la fuerza: Windows
    cierra su Job y mata al trabajador y al nieto. Es lo que pasa al cerrar la consola."""
    pid_nieto = tmp_path / "nieto.pid"
    pid_hijo = tmp_path / "hijo.pid"
    servidor = f"""
import sys, time
sys.path.insert(0, {str(Path(__file__).parent.parent / 'src')!r})
from componedor.proceso_windows import lanzar_en_job
p = lanzar_en_job([sys.executable, "-c", {CON_NIETO!r}, {str(pid_nieto)!r}])
open({str(pid_hijo)!r}, "w").write(str(p.proceso.pid))
time.sleep(120)
"""
    falso_servidor = subprocess.Popen([sys.executable, "-c", servidor])
    try:
        hijo, nieto = esperar_archivo(pid_hijo), esperar_archivo(pid_nieto)
        assert vivo(hijo) and vivo(nieto)
        falso_servidor.kill()  # TerminateProcess: sin limpieza de Python
        assert esperar_muerte(hijo) and esperar_muerte(nieto)
    finally:
        falso_servidor.kill()


def test_salida_y_entrada_por_tuberias(tmp_path):
    p = lanzar_en_job([sys.executable, "-c", "import sys; print(sys.stdin.readline().upper())"],
                      stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    salida, _ = p.proceso.communicate(b"hola\n", timeout=20)
    assert salida.strip() == b"HOLA"
    cerrar_job(p)
