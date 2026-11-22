/*
 * Editor de planos — MUESTRAS de línea y relleno de las convenciones (subfase 9a). Pura, sin
 * pantalla: funciona en el navegador (window.EditorMuestras) y en Node (module.exports).
 * Copia de `muestras_leyenda.py`: mismos valores por defecto, mismos mensajes y la misma
 * ubicación en la casilla (las pruebas comparan las dos).
 *
 *   {"tipo": "linea", "descripcion": "...", "color": "#RRGGBB", "grosor_mm": 0.25, "trazo": "continua"}
 *   {"tipo": "relleno", "descripcion": "...", "color": "#RRGGBB", "opacidad": 1}
 * Un renglón sin `tipo` es un símbolo de la biblioteca (lo de siempre).
 */
(function (raiz, fabrica) {
  "use strict";
  const api = fabrica();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    raiz.EditorMuestras = api;
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const TIPO_SIMBOLO = "simbolo";
  const TIPOS = ["simbolo", "linea", "relleno"];
  const TRAZOS = ["continua", "discontinua"];
  const CLAVES = {
    simbolo: ["descripcion", "simbolo", "tipo"],
    linea: ["color", "descripcion", "grosor_mm", "tipo", "trazo"],
    relleno: ["color", "descripcion", "opacidad", "tipo"],
  };
  const POR_DEFECTO = {
    linea: { color: "#000000", grosor_mm: 0.25, trazo: "continua" },
    relleno: { color: "#808080", opacidad: 1 },
  };
  const GROSOR_MIN_MM = 0.05;
  const GROSOR_MAX_MM = 2.0;
  const LARGO_LINEA_MM = 13.0;
  const TAMANO_RELLENO_MM = [13.0, 6.0];
  const GUION_MM = [2.0, 1.0];
  const HEX = /^#[0-9A-Fa-f]{6}$/;

  const numero = (v) => typeof v === "number" && Number.isFinite(v);
  const esMuestra = (tipo) => tipo === "linea" || tipo === "relleno";

  /** El tipo de un renglón: sin `tipo`, "simbolo". */
  function tipoDe(item) {
    return item.tipo === undefined ? TIPO_SIMBOLO : item.tipo;
  }

  /**
   * La muestra de un renglón "linea" o "relleno" (sin la descripción): {muestra, errores}.
   * `tipoValor`: cómo se nombra un valor en los mensajes (F.tipo = rotulo._tipo).
   */
  function leerMuestra(item, sitio, tipoValor) {
    const errores = [];
    const tipo = item.tipo;
    const base = POR_DEFECTO[tipo];
    const color = "color" in item ? item.color : base.color;
    if (typeof color !== "string" || !HEX.test(color)) {
      errores.push(sitio + ".color: se esperaba un color «#RRGGBB» (p. ej. «#FF0000» = rojo); tiene " + tipoValor(color));
    }
    if (tipo === "linea") {
      const grosor = "grosor_mm" in item ? item.grosor_mm : base.grosor_mm;
      if (!numero(grosor) || grosor < GROSOR_MIN_MM || grosor > GROSOR_MAX_MM) {
        errores.push(sitio + ".grosor_mm: se esperaba un número de 0.05 a 2 mm; tiene " + tipoValor(grosor));
      }
      const trazo = "trazo" in item ? item.trazo : base.trazo;
      if (!TRAZOS.includes(trazo)) {
        errores.push(sitio + ".trazo: se esperaba «continua» o «discontinua»; tiene " + tipoValor(trazo));
      }
      return { muestra: errores.length ? null : { tipo, color: color.toUpperCase(), grosor_mm: grosor, trazo }, errores };
    }
    const opacidad = "opacidad" in item ? item.opacidad : base.opacidad;
    if (!numero(opacidad) || !(opacidad > 0 && opacidad <= 1)) {
      errores.push(sitio + ".opacidad: se esperaba un número mayor que 0 y hasta 1 (1 = opaco); tiene " + tipoValor(opacidad));
    }
    return { muestra: errores.length ? null : { tipo, color: color.toUpperCase(), opacidad }, errores };
  }

  /** ¿La descripción falta o está en blanco? (una muestra no tiene descripción por defecto). */
  function descripcionVacia(v) {
    if (v === undefined || v === null) return true;
    if (Array.isArray(v)) return v.every((x) => typeof x === "string") && !v.join("").trim();
    return typeof v === "string" && !v.trim();
  }

  function errorFaltaDescripcion(sitio) {
    return sitio + ".descripcion: falta la descripción (una línea o un relleno no tiene descripción por defecto)";
  }

  /** Centrada en la casilla; más corta si el espacio útil no alcanza (= colocar_muestra). */
  function colocarMuestra(muestra, posicion, casilla, relleno) {
    const utilX = casilla[2] - casilla[0] - 2 * relleno;
    const utilY = casilla[3] - casilla[1] - 2 * relleno;
    const cx = (casilla[0] + casilla[2]) / 2;
    const cy = (casilla[1] + casilla[3]) / 2;
    let dibujo;
    if (muestra.tipo === "linea") {
      const mitad = Math.min(LARGO_LINEA_MM, utilX) / 2;
      dibujo = [cx - mitad, cy, cx + mitad, cy];
    } else {
      const ancho = Math.min(TAMANO_RELLENO_MM[0], utilX) / 2;
      const alto = Math.min(TAMANO_RELLENO_MM[1], utilY) / 2;
      dibujo = [cx - ancho, cy - alto, cx + ancho, cy + alto];
    }
    return Object.assign({}, muestra, { posicion, casilla: casilla.slice(), dibujo_mm: dibujo });
  }

  return {
    TIPO_SIMBOLO,
    TIPOS,
    TRAZOS,
    CLAVES,
    POR_DEFECTO,
    GROSOR_MIN_MM,
    GROSOR_MAX_MM,
    GUION_MM,
    esMuestra,
    tipoDe,
    leerMuestra,
    descripcionVacia,
    errorFaltaDescripcion,
    colocarMuestra,
  };
});
