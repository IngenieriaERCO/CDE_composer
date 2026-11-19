/*
 * Editor de planos — imagen de localización del rótulo (lógica pura, sin pantalla). Funciona en
 * el navegador (window.EditorLocalizacion) y en Node (module.exports), para probarla desde pytest.
 *
 * Es un campo del rótulo de tipo "imagen" (rotulo_formato.CampoImagen): el recuadro libre de
 * Localización. El plano guarda en rotulo.<campo> {archivo, bytes, modificado}; la imagen nunca
 * va dentro del plano.json ni de editor.html. componer la ajusta igual que `contener` (entera,
 * centrada, sin deformar), a ~300 ppp: un PNG con más se reduce; un JPG va tal cual.
 */
(function (raiz, fabrica) {
  "use strict";
  const api = fabrica();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    raiz.EditorLocalizacion = api;
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const MARGEN_PPP = 1.02; // igual que localizacion.MARGEN_PPP

  /** El campo de tipo "imagen" de la definición del rótulo: {nombre, rect_mm, ppp, campo_escala} o null. */
  function campoImagen(definicion) {
    if (!definicion || !definicion.campos) return null;
    for (const [nombre, c] of Object.entries(definicion.campos)) {
      if (c.tipo === "imagen") return Object.assign({ nombre }, c);
    }
    return null;
  }

  /** La imagen entera dentro del recuadro, centrada y sin deformar (localizacion.contener). */
  function contener(rect, anchoPx, altoPx) {
    const ancho = rect[2] - rect[0];
    const alto = rect[3] - rect[1];
    const escala = Math.min(ancho / anchoPx, alto / altoPx);
    const w = anchoPx * escala;
    const h = altoPx * escala;
    const x0 = rect[0] + (ancho - w) / 2;
    const y0 = rect[1] + (alto - h) / 2;
    return [x0, y0, x0 + w, y0 + h];
  }

  /** Cómo quedará en el PDF: {destino, ppp (de la imagen), reducida, pppFinal}. */
  function enElPdf(campo, px, formato) {
    const destino = contener(campo.rect_mm, px[0], px[1]);
    const pulgadas = (destino[2] - destino[0]) / 25.4;
    const ppp = px[0] / pulgadas;
    const reducida = formato === "png" && ppp > campo.ppp * MARGEN_PPP;
    return { destino, ppp, reducida, pppFinal: reducida ? Math.round(pulgadas * campo.ppp) / pulgadas : ppp };
  }

  const nombreDe = (r) => String(r).replace(/\\/g, "/").split("/").pop();

  /** Qué no coincide entre la del plano ({archivo, bytes, modificado}) y la cargada (ficha). */
  function diferencias(plano, ficha) {
    const lista = [];
    if (nombreDe(plano.archivo).toLowerCase() !== nombreDe(ficha.archivo_plano).toLowerCase()) {
      lista.push("nombre: el plano usa «" + nombreDe(plano.archivo) + "» y la elegida es «" + ficha.nombre + "»");
    }
    if (plano.bytes !== undefined && plano.bytes !== null && plano.bytes !== ficha.bytes) {
      lista.push("tamaño: el plano dice " + plano.bytes + " bytes y la elegida tiene " + ficha.bytes);
    }
    if (plano.modificado && plano.modificado !== ficha.modificado) {
      lista.push("fecha: el plano dice " + plano.modificado + " y la elegida es del " + ficha.modificado);
    }
    return lista;
  }

  /** El valor para el plano a partir de la ficha del servidor. */
  const valorParaPlano = (ficha) => ({ archivo: ficha.archivo_plano, bytes: ficha.bytes, modificado: ficha.modificado });

  /** ¿La escala de localización está vacía? (entonces sale «DEFINIR» y se avisa). */
  const escalaVacia = (valor) => valor === undefined || valor === null || (typeof valor === "string" && !valor.trim());

  const AVISO_ESCALA = "La imagen de localización no tiene escala: en el PDF sale «ESC: DEFINIR». " +
    "Escríbala a mano en Rótulo (escala de localización).";

  /** Las líneas de la ficha. */
  function lineasFicha(campo, ficha) {
    const p = enElPdf(campo, ficha.px, ficha.formato);
    const lineas = [ficha.nombre + " · " + ficha.formato.toUpperCase() + " · " + ficha.px[0] + " × " + ficha.px[1] + " px"];
    lineas.push("En el recuadro: " + (p.destino[2] - p.destino[0]).toFixed(1).replace(".", ",") + " × " +
      (p.destino[3] - p.destino[1]).toFixed(1).replace(".", ",") + " mm, " + Math.round(p.ppp) + " ppp" +
      (p.reducida ? " (se reduce a " + campo.ppp + " ppp, sin pérdida)"
        : ficha.formato === "jpeg" ? " (va tal cual, sin recomprimir)"
          : p.ppp < campo.ppp ? " (menos de " + campo.ppp + ": no se agranda)" : ""));
    return lineas;
  }

  return { MARGEN_PPP, campoImagen, contener, enElPdf, diferencias, valorParaPlano, escalaVacia, AVISO_ESCALA,
    lineasFicha };
});
