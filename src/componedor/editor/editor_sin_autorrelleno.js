/*
 * Editor de planos — que el navegador no rellene solo los cuadros de texto.
 *
 * Los navegadores guardan lo escrito en los cuadros de una página y lo vuelven a poner, POR
 * ORDEN, al volver a ella (atrás en el historial, restaurar la pestaña) o lo sugieren como
 * autocompletado. El editor arma sus cuadros con JavaScript y cuáles hay depende de lo
 * seleccionado: al volver, los valores de «Centro X / Centro Y» de un bloque caían en «No. PLANO»
 * y «HOJA» del rótulo, sin que el editor se enterara (se veían, pero no estaban en el modelo).
 *
 * Por eso TODO cuadro del editor lleva autocomplete="off": el navegador no lo guarda ni lo
 * rellena. Este módulo se carga antes que los demás y vigila los que se crean después.
 * Funciona en el navegador (window.EditorSinAutorrelleno) y en Node (module.exports).
 */
(function (raiz, fabrica) {
  "use strict";
  const api = fabrica();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    raiz.EditorSinAutorrelleno = api;
    if (raiz.document) api.vigilar(raiz.document, raiz.MutationObserver);
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const SELECTOR = "input, textarea, select";

  /** autocomplete="off" en el nodo (si es un cuadro) y en los cuadros que tenga dentro. */
  function apagar(nodo) {
    if (!nodo || nodo.nodeType !== 1) return 0;
    let n = 0;
    const cuadros = nodo.matches && nodo.matches(SELECTOR) ? [nodo] : [];
    if (nodo.querySelectorAll) cuadros.push(...nodo.querySelectorAll(SELECTOR));
    for (const c of cuadros) {
      if (c.getAttribute("autocomplete") !== "off") {
        c.setAttribute("autocomplete", "off");
        n++;
      }
    }
    return n;
  }

  /** Apaga los cuadros que ya hay y los que se agreguen después en `documento`. */
  function vigilar(documento, Observador) {
    apagar(documento.documentElement);
    if (!Observador) return null;
    const observador = new Observador((cambios) => {
      for (const cambio of cambios) for (const nodo of cambio.addedNodes) apagar(nodo);
    });
    observador.observe(documento.documentElement, { childList: true, subtree: true });
    return observador;
  }

  return { SELECTOR, apagar, vigilar };
});
