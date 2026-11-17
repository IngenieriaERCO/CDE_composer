"""Lanzar un proceso hijo que muere SIEMPRE con el Componedor (Job Object de Windows).

`cde-exporter.exe` es un lanzador de pip que, a su vez, arranca `python.exe`: si se mata solo
el lanzador, el Python hijo queda vivo. Por eso el proceso se crea SUSPENDIDO, se mete en un
Job Object con «matar al cerrar» (JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE) y recién ahí se reanuda:
todo lo que cree después (nietos incluidos) queda en el mismo Job. Cuando el Componedor cierra
el Job, o cuando su proceso termina por cualquier motivo (se cierra la consola, se cae),
Windows mata el árbol entero.

Solo usa `ctypes` de la biblioteca estándar. Fuera de Windows (pruebas en otra máquina) es un
`subprocess.Popen` común y `cerrar_job` mata solo el proceso.
"""

import ctypes
import subprocess
import sys
from ctypes import wintypes
from dataclasses import dataclass

ES_WINDOWS = sys.platform == "win32"
CREATE_SUSPENDED = 0x00000004
CREATE_NO_WINDOW = 0x08000000
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9  # JobObjectExtendedLimitInformation


class _BasicLimit(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD)]


class _IoCounters(ctypes.Structure):
    _fields_ = [(nombre, ctypes.c_uint64) for nombre in (
        "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
        "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class _ExtendedLimit(ctypes.Structure):
    _fields_ = [("BasicLimitInformation", _BasicLimit),
                ("IoInfo", _IoCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t)]


@dataclass
class ProcesoEnJob:
    """El proceso lanzado y su Job (None fuera de Windows o si no se pudo crear)."""
    proceso: subprocess.Popen
    job: int | None
    aviso: str | None = None  # por qué no quedó en un Job (se anota en el registro)


def _kernel32():
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    k.CreateJobObjectW.restype = wintypes.HANDLE
    k.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                          wintypes.DWORD]
    k.SetInformationJobObject.restype = wintypes.BOOL
    k.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    k.AssignProcessToJobObject.restype = wintypes.BOOL
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    k.CloseHandle.restype = wintypes.BOOL
    return k


def _reanudar(proceso: subprocess.Popen) -> None:
    """Reanuda un proceso creado con CREATE_SUSPENDED (Popen no guarda el hilo principal)."""
    ntdll = ctypes.WinDLL("ntdll")
    ntdll.NtResumeProcess.argtypes = [wintypes.HANDLE]
    ntdll.NtResumeProcess.restype = ctypes.c_long
    estado = ntdll.NtResumeProcess(int(proceso._handle))
    if estado != 0:
        raise OSError(f"NtResumeProcess devolvió 0x{estado & 0xFFFFFFFF:08X}")


def _crear_job() -> int:
    k = _kernel32()
    job = k.CreateJobObjectW(None, None)
    if not job:
        raise ctypes.WinError(ctypes.get_last_error())
    info = _ExtendedLimit()
    info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not k.SetInformationJobObject(job, JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                                     ctypes.byref(info), ctypes.sizeof(info)):
        error = ctypes.WinError(ctypes.get_last_error())
        k.CloseHandle(job)
        raise error
    return job


def lanzar_en_job(argv: list[str], **popen) -> ProcesoEnJob:
    """`subprocess.Popen(argv, **popen)` dentro de un Job que lo mata con todo su árbol.

    En Windows agrega CREATE_NO_WINDOW (sin consola propia). Si el Job no se puede crear o
    asignar, el proceso corre igual (se reanuda) y `aviso` dice por qué.
    """
    if not ES_WINDOWS:
        return ProcesoEnJob(subprocess.Popen(argv, **popen), None, "fuera de Windows: sin Job")
    banderas = popen.pop("creationflags", 0) | CREATE_NO_WINDOW
    try:
        job = _crear_job()
    except OSError as e:
        return ProcesoEnJob(subprocess.Popen(argv, creationflags=banderas, **popen), None,
                            f"no se pudo crear el Job Object: {e}")
    proceso = subprocess.Popen(argv, creationflags=banderas | CREATE_SUSPENDED, **popen)
    aviso = None
    if not _kernel32().AssignProcessToJobObject(job, int(proceso._handle)):
        aviso = f"no se pudo asignar el proceso al Job: {ctypes.WinError(ctypes.get_last_error())}"
        _kernel32().CloseHandle(job)
        job = None
    try:
        _reanudar(proceso)
    except OSError:
        proceso.kill()
        if job is not None:
            _kernel32().CloseHandle(job)
        raise
    return ProcesoEnJob(proceso, job, aviso)


def cerrar_job(p: ProcesoEnJob) -> None:
    """Mata el proceso y todo su árbol (cerrando el Job). Se puede llamar varias veces."""
    if p.job is not None:
        _kernel32().CloseHandle(p.job)
        p.job = None
    if p.proceso.poll() is None:
        p.proceso.kill()
    try:
        p.proceso.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass
