"""Integridad del paquete (PDF y manifiesto sintéticos con bytes y SHA-256 reales)."""

import hashlib

import pytest

from componedor import integridad
from componedor.cli import main
from componedor.integridad import sha256_archivo, verificar_integridad
from componedor.paquete import localizar_paquetes
from conftest import crear_paquete_real, escribir_json, manifiesto_paquete


def _verificar(carpeta):
    (paquete,) = localizar_paquetes(carpeta)
    return verificar_integridad(paquete)


def _por_nombre(resultado):
    return {c.nombre: c for c in resultado.comprobaciones}


def test_paquete_integro(tmp_path):
    crear_paquete_real(tmp_path)
    r = _verificar(tmp_path)
    assert r.verificable and r.pasa and r.etiqueta == "OK"
    assert [c.nombre for c in r.comprobaciones] == [
        "El PDF existe", "Tamaño en bytes", "SHA-256", "Abre como PDF", "Una sola página"]
    assert all(c.seccion == "Integridad" and c.tolerancia == "exacto" for c in r.comprobaciones)


def test_un_byte_cambiado_mismo_tamano(tmp_path):
    ruta = crear_paquete_real(tmp_path)
    datos = bytearray(ruta.read_bytes())
    datos[len(datos) // 2] ^= 0xFF  # un solo byte, el tamaño no cambia
    ruta.write_bytes(bytes(datos))
    r = _verificar(tmp_path)
    c = _por_nombre(r)
    assert c["Tamaño en bytes"].pasa
    assert not c["SHA-256"].pasa
    assert c["SHA-256"].detalle == ("el contenido del PDF cambió después de exportarse "
                                    "(mismo tamaño, otro SHA-256)")
    assert r.etiqueta == "FALLA"


def test_archivo_recortado(tmp_path):
    ruta = crear_paquete_real(tmp_path)
    original = ruta.read_bytes()
    ruta.write_bytes(original[: len(original) // 2])
    c = _por_nombre(_verificar(tmp_path))
    assert not c["Tamaño en bytes"].pasa
    assert c["Tamaño en bytes"].detalle == (
        f"el PDF tiene {len(original) // 2} bytes y el manifiesto dice {len(original)}: "
        f"el archivo fue modificado o está incompleto")
    assert "tampoco coincide" in c["SHA-256"].detalle  # se sigue midiendo


def test_no_es_pdf_aunque_el_hash_coincida(tmp_path):
    crear_paquete_real(tmp_path, contenido=b"esto no es un PDF, solo texto\n" * 10)
    r = _verificar(tmp_path)
    c = _por_nombre(r)
    assert c["Tamaño en bytes"].pasa and c["SHA-256"].pasa
    assert not c["Abre como PDF"].pasa
    assert c["Abre como PDF"].detalle.startswith("PyMuPDF no puede abrir el archivo")
    assert "Una sola página" not in c  # sin abrir no se pueden contar páginas


def test_pdf_de_dos_paginas_con_manifiesto_de_una(tmp_path):
    crear_paquete_real(tmp_path, paginas=2)
    c = _por_nombre(_verificar(tmp_path))
    assert c["SHA-256"].pasa and c["Abre como PDF"].pasa
    assert not c["Una sola página"].pasa
    assert c["Una sola página"].detalle == ("el PDF tiene 2 página(s) y el manifiesto dice 1: "
                                            "un detalle es una sola página")


def test_pdf_y_manifiesto_de_dos_paginas(tmp_path):
    crear_paquete_real(tmp_path, paginas=2, cambiar={"pdf.page_count": 2})
    c = _por_nombre(_verificar(tmp_path))
    assert not c["Una sola página"].pasa
    assert "dicen 2 páginas" in c["Una sola página"].detalle


def test_pdf_ausente_despues_de_localizar(tmp_path):
    ruta = crear_paquete_real(tmp_path)
    (paquete,) = localizar_paquetes(tmp_path)
    ruta.unlink()  # desapareció entre la localización y la verificación
    r = verificar_integridad(paquete)
    assert [c.nombre for c in r.comprobaciones] == ["El PDF existe"]  # se detiene aquí
    assert not r.pasa and "no se encuentra el PDF" in r.comprobaciones[0].detalle


def test_paquete_incompleto_o_invalido_no_verificable(tmp_path):
    crear_paquete_real(tmp_path / "a", "sin_pdf").unlink()
    crear_paquete_real(tmp_path / "b", "invalido", cambiar={"schema_version": "2.0"})
    for carpeta, estado in ((tmp_path / "a", "incompleto"), (tmp_path / "b", "invalido")):
        r = _verificar(carpeta)
        assert not r.verificable and r.comprobaciones == []
        assert r.motivo == f"no verificable (paquete {estado})"
        assert r.etiqueta == "—"


def test_hash_de_archivo_grande_por_bloques(tmp_path, monkeypatch):
    datos = bytes(range(256)) * (5 * 1024 * 1024 // 256)  # 5 MB
    ruta = tmp_path / "grande.bin"
    ruta.write_bytes(datos)
    lecturas = []
    abrir_original = open

    class Espia:
        """Envuelve el archivo real y anota el tamaño de cada lectura."""

        def __init__(self, archivo):
            self.archivo = archivo

        def read(self, n=-1):
            lecturas.append(n)
            return self.archivo.read(n)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self.archivo.close()

    def abrir(ruta_, modo="r", *args, **kwargs):
        return Espia(abrir_original(ruta_, modo, *args, **kwargs))

    monkeypatch.setattr(integridad, "open", abrir, raising=False)
    assert sha256_archivo(ruta) == hashlib.sha256(datos).hexdigest()
    assert lecturas and all(0 < n <= integridad.BLOQUE_BYTES for n in lecturas)
    assert len(lecturas) >= 5  # 5 bloques de 1 MB más la lectura final vacía


def test_paquete_grande_integro(tmp_path):
    datos = b"%PDF-ficticio\n" + b"0" * (5 * 1024 * 1024)
    crear_paquete_real(tmp_path, contenido=datos)
    c = _por_nombre(_verificar(tmp_path))
    assert c["SHA-256"].pasa and c["Tamaño en bytes"].pasa


# --- CLI paquetes --verificar ------------------------------------------------------------

def test_cli_verificar_todo_ok(tmp_path, capsys):
    crear_paquete_real(tmp_path, "detalle_001")
    crear_paquete_real(tmp_path, "detalle_002")
    assert main(["paquetes", str(tmp_path), "--verificar"]) == 0
    out = capsys.readouterr().out
    assert "Integridad" in out
    assert "detalle_001  completo  DETALLE_PRUEBA  1:50    260.00 x 120.00  OK" in out
    assert "Integridad: 2 OK, 0 con falla." in out


def test_cli_verificar_con_falla(tmp_path, capsys):
    crear_paquete_real(tmp_path, "bueno")
    ruta = crear_paquete_real(tmp_path, "tocado")
    datos = bytearray(ruta.read_bytes())
    datos[100] ^= 0x01
    ruta.write_bytes(bytes(datos))
    escribir_json(tmp_path / "sin_pdf.manifest.json", manifiesto_paquete(
        cambiar={"pdf.file_name": "sin_pdf.pdf"}))
    assert main(["paquetes", str(tmp_path), "--verificar"]) == 1
    out = capsys.readouterr().out
    # Columnas finales: Integridad y Coherencia (la coherencia de "tocado" no se verifica).
    filas = {linea.split()[0]: linea.split()[-2:] for linea in out.splitlines()
             if linea.startswith(("bueno", "tocado", "sin_pdf"))}
    assert filas == {"bueno": ["OK", "OK"], "tocado": ["FALLA", "—"], "sin_pdf": ["—", "—"]}
    assert ("Problemas de integridad:\n  tocado:\n    - SHA-256: el contenido del PDF cambió "
            "después de exportarse") in out
    assert "Integridad: 1 OK, 1 con falla." in out


def test_cli_sin_verificar_no_hay_columna(tmp_path, capsys):
    ruta = crear_paquete_real(tmp_path)
    ruta.write_bytes(ruta.read_bytes()[:-10])  # dañado, pero no se verifica
    assert main(["paquetes", str(tmp_path)]) == 0
    assert "Integridad" not in capsys.readouterr().out


@pytest.mark.parametrize("verificar", [False, True])
def test_cli_pdf_sueltos(tmp_path, capsys, verificar):
    crear_paquete_real(tmp_path, "detalle")
    (tmp_path / "prueba_b.pdf").write_bytes(b"%PDF")
    (tmp_path / "prueba_a.pdf").write_bytes(b"%PDF")
    args = ["paquetes", str(tmp_path)] + (["--verificar"] if verificar else [])
    assert main(args) == 0  # los sueltos no cambian el código
    out = capsys.readouterr().out
    assert out.rstrip().endswith("PDF sin paquete (ignorados): 2 — prueba_a.pdf, prueba_b.pdf")
