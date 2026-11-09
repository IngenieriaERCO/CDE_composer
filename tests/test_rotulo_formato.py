"""Sección "rotulo" del formato: esquema versionado, validado y sin campos desconocidos."""

import copy
from pathlib import Path

import pytest

from componedor.formato import FormatoInvalido, cargar_formato, validar_formato
from componedor.rotulo_formato import (
    CampoConvenciones,
    CampoNotas,
    CampoTabla,
    CampoTexto,
    RotuloFormatoInvalido,
    leer_definicion_rotulo,
)
from conftest import RUTA_A1, rotulo_a1

ZONA = (672.4, 12.7, 828.3, 581.3)


def _error(datos) -> str:
    with pytest.raises(RotuloFormatoInvalido) as e:
        leer_definicion_rotulo(datos, ZONA, Path("formatos"))
    return str(e.value)


def test_a1_erco_trae_los_campos_medidos_del_rotulo_v2():
    formato = cargar_formato(RUTA_A1, usar_plantilla=False)
    r = formato.rotulo
    assert r.version == 1 and r.relleno_mm == 0.6 and r.interlineado == 1.6
    assert r.fuente == Path("C:/Windows/Fonts/arial.ttf")
    assert set(r.campos) == {"localizacion_escala", "este", "norte", "revisiones", "disenador",
                             "revisor", "titulo", "firmas", "hoja", "de", "escala", "no_plano",
                             "rev", "notas", "convenciones"}
    revisiones = r.campos["revisiones"]
    assert isinstance(revisiones, CampoTabla)
    assert revisiones.filas == ("0", "C", "B", "A") and revisiones.orden == ("A", "B", "C", "0")
    assert revisiones.columna_clave == "ver"
    assert revisiones.celdas[("A", "fecha")].rect == (680.5, 112.5, 699.7, 118.8)
    firmas = r.campos["firmas"]
    assert firmas.celdas[("reviso", "nombre")].lineas_max == 2
    titulo = r.campos["titulo"]
    assert isinstance(titulo, CampoTexto)
    assert (titulo.celda.altura_mm, titulo.celda.altura_min_mm, titulo.celda.lineas_max) == (2.5, 2.0, 3)
    assert r.campos["localizacion_escala"].por_defecto == "DEFINIR"
    assert r.campos["escala"].calculado == "escala_comun"
    assert r.campos["rev"].calculado == "ultima_revision"
    # 12 celdas simples (con notas), 2 tablas y las convenciones (24 símbolos + 24 descripciones)
    assert len(r.celdas()) == 12 + 4 * 7 + 4 * 4 + 48


def test_notas_en_a1_erco():
    notas = cargar_formato(RUTA_A1, usar_plantilla=False).rotulo.campos["notas"]
    assert isinstance(notas, CampoNotas)
    assert notas.celda.rect == (673.2, 271.3, 827.4, 419.3)
    assert (notas.celda.altura_mm, notas.celda.altura_min_mm) == (1.8, 1.5)
    assert notas.separacion_notas == 0.5


def test_hoja_y_de_tienen_el_mismo_centro_en_x():
    campos = cargar_formato(RUTA_A1, usar_plantilla=False).rotulo.campos
    hoja, de = campos["hoja"].celda, campos["de"].celda
    assert (hoja.rect[0], hoja.rect[2]) == (de.rect[0], de.rect[2]) == (812.9, 827.4)
    assert hoja.alinear == de.alinear == "centro"


def test_convenciones_en_a1_erco_y_orden_de_llenado():
    c = cargar_formato(RUTA_A1, usar_plantilla=False).rotulo.campos["convenciones"]
    assert isinstance(c, CampoConvenciones) and c.capacidad == 24
    # "../simbolos/indice.json" se resuelve desde la carpeta del formato (formatos/).
    assert c.biblioteca == RUTA_A1.parent.parent / "simbolos" / "indice.json"
    # Por columna: 1..12 la pareja izquierda de arriba abajo, 13..24 la derecha.
    assert c.simbolos[0].rect == (672.4, 249.39, 693.84, 259.88)
    assert c.simbolos[11].rect == (672.4, 137.71, 693.84, 147.28)
    assert c.simbolos[12].rect == (750.32, 249.39, 771.82, 259.88)
    assert c.descripciones[12].rect == (771.82, 249.39, 828.2, 259.88)
    assert c.descripciones[0].lineas_max == 2 and c.descripciones[0].altura_mm == 1.8


@pytest.mark.parametrize("cambio, esperado", [
    ({"filas_y_mm": [137.71, 259.88]}, "rotulo.campos.convenciones.filas_y_mm: se esperaba la "
                                       "lista de las Y"),
    ({"columnas_x_mm": [[672.4, 693.84]]}, "rotulo.campos.convenciones.columnas_x_mm: se "
                                           "esperaba una lista de parejas"),
    ({"biblioteca": ""}, "rotulo.campos.convenciones.biblioteca: se esperaba la ruta"),
    ({"colr": 1}, "rotulo.campos.convenciones.colr: campo no reconocido"),
])
def test_convenciones_invalidas(cambio, esperado):
    datos = copy.deepcopy(rotulo_a1())
    datos["campos"]["convenciones"].update(cambio)
    assert esperado in _error(datos)


@pytest.mark.parametrize("cambio, esperado", [
    ({"colr": 1}, "rotulo.campos.notas.colr: campo no reconocido"),
    ({"altura_min_mm": 2.0}, "rotulo.campos.notas.altura_min_mm: se esperaba un número positivo "
                             "no mayor que altura_mm (1.8)"),
    ({"separacion_notas": -1}, "rotulo.campos.notas.separacion_notas: se esperaba un número "
                               "mayor o igual a 0"),
    ({"rect_mm": [673.2, 271.3, 827.4, 430.0]},  # se mete en la fila de coordenadas
     "las celdas 'este' [715.6, 425.1, 749.5, 434] y 'notas' [673.2, 271.3, 827.4, 430] se "
     "traslapan"),
])
def test_notas_invalidas(cambio, esperado):
    datos = copy.deepcopy(rotulo_a1())
    datos["campos"]["notas"].update(cambio)
    assert esperado in _error(datos)


def test_sin_rotulo_el_formato_sigue_valido():
    datos = validar_formato({k: v for k, v in _a1().items() if k != "rotulo"})
    assert datos.rotulo is None


def _a1():
    import json
    datos = json.loads(RUTA_A1.read_text(encoding="utf-8"))
    datos.pop("plantilla")
    return datos


def test_fuente_relativa_a_la_carpeta_del_formato():
    d = leer_definicion_rotulo(rotulo_a1(fuente={"archivo": "../fuentes/x.ttf"}), ZONA,
                               Path("C:/proy/formatos"))
    assert d.fuente == Path("C:/proy/fuentes/x.ttf")


def test_error_del_rotulo_sale_como_formato_invalido():
    datos = _a1()
    datos["rotulo"]["version"] = 2
    with pytest.raises(FormatoInvalido, match="rotulo.version: versión 2 no soportada"):
        validar_formato(datos)


@pytest.mark.parametrize("cambio, esperado", [
    (lambda r: r.update(color="rojo"), "rotulo.color: campo no reconocido"),
    (lambda r: r.pop("fuente"), "rotulo.fuente: falta el campo"),
    (lambda r: r.update(fuente="arial.ttf"), "rotulo.fuente: se esperaba {\"archivo\""),
    (lambda r: r.update(relleno_mm=-1), "rotulo.relleno_mm: se esperaba un número mayor o igual a 0"),
    (lambda r: r.update(interlineado=0.5), "rotulo.interlineado: se esperaba un número mayor o igual a 1"),
    (lambda r: r.update(campos={}), "rotulo.campos: se esperaba un objeto con al menos un campo"),
    (lambda r: r["campos"]["titulo"].update(tipo="parrafo"),
     "rotulo.campos.titulo.tipo: se esperaba \"texto\", \"tabla\", \"notas\" o \"convenciones\""),
    (lambda r: r["campos"]["titulo"].update(colr="x"), "rotulo.campos.titulo.colr: campo no reconocido"),
    (lambda r: r["campos"]["titulo"].update(alinear="justificado"),
     "rotulo.campos.titulo.alinear: se esperaba uno de izq, centro, der"),
    (lambda r: r["campos"]["titulo"].update(altura_mm=0), "rotulo.campos.titulo.altura_mm: se esperaba un número positivo"),
    (lambda r: r["campos"]["titulo"].update(altura_min_mm=3.0),
     "rotulo.campos.titulo.altura_min_mm: se esperaba un número positivo no mayor que altura_mm (2.5)"),
    (lambda r: r["campos"]["titulo"].update(lineas_max=0), "rotulo.campos.titulo.lineas_max: se esperaba un entero"),
    (lambda r: r["campos"]["titulo"].update(rect_mm=[700, 50, 690, 60]),
     "rotulo.campos.titulo.rect_mm: ancho y alto deben ser positivos"),
    (lambda r: r["campos"]["escala"].update(calculado="fecha_hoy"),
     "rotulo.campos.escala.calculado: se esperaba uno de escala_comun, ultima_revision"),
    (lambda r: r["campos"]["escala"].update(por_defecto="1:1"),
     "rotulo.campos.escala: un campo calculado no lleva por_defecto"),
    (lambda r: r["campos"]["revisiones"].update(columna_clave="letra"),
     "rotulo.campos.revisiones.columna_clave: 'letra' no es una de las columnas"),
    (lambda r: r["campos"]["revisiones"].update(orden=["0", "A", "B"]),
     "rotulo.campos.revisiones.orden: se esperaba la lista de las filas"),
    (lambda r: r["campos"]["firmas"].update(orden=["dibujo"]),
     "rotulo.campos.firmas.orden: solo se usa con columna_clave"),
    (lambda r: r["campos"]["firmas"]["filas"]["dibujo"].update(y_mm=[43.5, 39.0]),
     "rotulo.campos.firmas.filas.dibujo.y_mm: se esperaba [mínimo, máximo]"),
    (lambda r: r["campos"]["firmas"]["columnas"]["nombre"].update(ancho=3),
     "rotulo.campos.firmas.columnas.nombre.ancho: campo no reconocido"),
    (lambda r: r["campos"].pop("revisiones"),
     "rotulo.campos.rev: \"ultima_revision\" necesita la tabla 'revisiones'"),
])
def test_esquema_invalido(cambio, esperado):
    datos = copy.deepcopy(rotulo_a1())
    cambio(datos)
    assert esperado in _error(datos)


def test_celda_fuera_del_rotulo_traslapada_o_muy_baja():
    datos = rotulo_a1()
    datos["campos"]["hoja"]["rect_mm"] = [600.0, 38.3, 627.4, 43.6]  # en el área de dibujo
    datos["campos"]["de"]["rect_mm"] = [809.4, 32.3, 827.4, 40.0]  # pisa la celda 'hoja'
    datos["campos"]["no_plano"]["rect_mm"] = [690.9, 13.5, 807.0, 15.5]  # 2 mm de alto
    mensaje = _error(datos)
    assert "celda 'hoja' [600, 38.3, 627.4, 43.6]: se sale de la zona 'rotulo'" in mensaje
    assert "las celdas 'hoja'" not in mensaje  # 'hoja' ya no está ahí
    assert ("celda 'no_plano': mide 2.00 mm de alto; con relleno de 0.6 mm no cabe ni una "
            "línea de 2.5 mm") in mensaje


def test_traslape_entre_celdas_de_campos_distintos():
    datos = rotulo_a1()
    datos["campos"]["de"]["rect_mm"] = [809.4, 32.3, 827.4, 40.0]
    assert ("las celdas 'hoja' [812.9, 38.3, 827.4, 43.6] y 'de' [809.4, 32.3, 827.4, 40] se "
            "traslapan") in _error(datos)


def test_todos_los_problemas_en_un_solo_mensaje():
    datos = rotulo_a1(version=9, color="x")
    mensaje = _error(datos)
    assert "(2 problemas)" in mensaje
    assert mensaje.count("\n- ") == 2
