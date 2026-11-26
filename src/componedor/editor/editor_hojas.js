/*
 * Varias hojas de un proyecto (plano versión 7, «Nueva hoja a partir de esta»): lógica sin
 * pantalla, la misma en el navegador y en las pruebas de Node.
 *
 * Un plano.json por hoja, en la carpeta del editor, y un índice <proyecto>.hojas.json con sus
 * nombres en orden (hojas_proyecto.py). La hoja nueva copia TODO el rótulo de la actual menos el
 * título (se vacía) y los campos automáticos (hoja, de, número de plano: salen solos del
 * índice). Notas, convenciones y revisiones se copian pero quedan «por revisar»
 * ("copiado_de": {"hoja", "revisar"}) hasta que el usuario las cambie. El área de dibujo queda
 * vacía: sin detalles, bloques ni zonas. La ortofoto se copia (ningún detalle la usa todavía).
 */
(function (raiz, fabrica) {
  "use strict";
  const api = fabrica();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    raiz.EditorHojas = api;
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const SUFIJO = ".hojas.json";
  const TITULO = "titulo";
  const TABLA_REVISIONES = "revisiones";
  // Los que solo cuentan la hoja (no el número de plano, que la primera hoja escribe a mano).
  const SOLO_INDICE = ["hoja_actual", "total_hojas"];

  const clonar = (v) => (v === undefined ? undefined : JSON.parse(JSON.stringify(v)));
  const vacio = (v) => v === undefined || v === null || (typeof v === "string" && !v.trim()) ||
    (Array.isArray(v) && !v.length) || (typeof v === "object" && !Array.isArray(v) && !Object.keys(v).length);

  /** {campo: "hoja_actual" | "total_hojas" | "numero_siguiente"} de la definición del rótulo. */
  function camposAutomaticos(definicion) {
    const salida = {};
    const campos = (definicion && definicion.campos) || {};
    for (const [nombre, c] of Object.entries(campos)) if (c && c.tipo === "texto" && c.automatico) salida[nombre] = c.automatico;
    return salida;
  }

  /** Los campos que se copian «por revisar»: notas, convenciones y la tabla de revisiones. */
  function camposRevisar(definicion) {
    const campos = (definicion && definicion.campos) || {};
    return Object.entries(campos).filter(([nombre, c]) => c && (c.tipo === "notas" || c.tipo === "convenciones" ||
      (c.tipo === "tabla" && nombre === TABLA_REVISIONES))).map(([nombre]) => nombre);
  }

  const sinJson = (archivo) => String(archivo).replace(/\.json$/i, "");

  /** El primer «<base>_NN.json» (NN desde 02) que no está en `existentes`. */
  function nombreNuevaHoja(base, existentes) {
    const usados = new Set((existentes || []).map((n) => String(n).toLowerCase()));
    for (let n = 2; n < 1000; n++) {
      const nombre = base + "_" + String(n).padStart(2, "0") + ".json";
      if (!usados.has(nombre.toLowerCase())) return nombre;
    }
    return null;
  }

  /** El rótulo sin «hoja» ni «de» escritos (pasan a salir del índice). */
  function sinHojaNiDe(rotulo, definicion) {
    if (!rotulo || typeof rotulo !== "object") return rotulo;
    const auto = camposAutomaticos(definicion);
    const salida = clonar(rotulo);
    for (const [campo, tipo] of Object.entries(auto)) if (SOLO_INDICE.includes(tipo)) delete salida[campo];
    return salida;
  }

  /**
   * La hoja nueva a partir del objeto plano.json de la actual: {plano, revisar}. Copia formato,
   * plantilla, rosa, ortofoto y el rótulo (sin título ni automáticos); detalles vacíos.
   */
  function planoNuevaHoja(actual, archivoActual, definicion) {
    const rotulo = clonar(actual.rotulo) || {};
    delete rotulo[TITULO];
    for (const campo of Object.keys(camposAutomaticos(definicion))) delete rotulo[campo];
    const revisar = camposRevisar(definicion).filter((c) => !vacio(rotulo[c]));
    const plano = { version: 7, formato: actual.formato };
    if ("plantilla" in actual) plano.plantilla = actual.plantilla;
    plano.detalles = [];
    if (actual.ortofoto) plano.ortofoto = clonar(actual.ortofoto);
    if (actual.rosa_vientos !== undefined) plano.rosa_vientos = clonar(actual.rosa_vientos);
    plano.rotulo = rotulo;
    plano.copiado_de = { hoja: archivoActual, revisar };
    return { plano, revisar };
  }

  /** Los campos por revisar que el usuario todavía no cambió: `original` = {campo: valor al
   *  abrir}, `valor(campo)` = el de ahora. */
  function porRevisar(revisar, original, valor) {
    return (revisar || []).filter((c) => JSON.stringify(valor(c)) === JSON.stringify(original[c]));
  }

  /** «copiado_de» leído de un plano versión 7, o null si no vale. */
  function leerCopiado(valor, errores) {
    if (valor === undefined) return null;
    const ok = valor && typeof valor === "object" && !Array.isArray(valor) && typeof valor.hoja === "string" &&
      valor.hoja.trim() && (valor.revisar === undefined || (Array.isArray(valor.revisar) &&
        valor.revisar.every((c) => typeof c === "string" && c.trim()))) &&
      Object.keys(valor).every((k) => k === "hoja" || k === "revisar");
    if (!ok) {
      errores.push("copiado_de: se esperaba {\"hoja\": \"<plano.json>\", \"revisar\": [campos del rótulo]}.");
      return null;
    }
    return { hoja: valor.hoja, revisar: (valor.revisar || []).slice() };
  }

  return { SUFIJO, camposAutomaticos, camposRevisar, nombreNuevaHoja, sinHojaNiDe, planoNuevaHoja,
    porRevisar, leerCopiado, sinJson };
});
