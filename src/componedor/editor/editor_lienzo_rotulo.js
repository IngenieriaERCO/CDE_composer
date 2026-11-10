/*
 * Editor de planos — dibujo de la VISTA PREVIA del rótulo en el lienzo (subfase 4.3f). Solo
 * pantalla: QUÉ y DÓNDE lo dice editor_vista_previa.js (EditorVistaPrevia, las mismas posiciones
 * que `componer`); aquí solo se pasa a SVG.
 *
 * Cada capa es un <g> con UNA transformación de mm de papel a píxeles del lienzo: escala X e Y
 * (las de L.escalaDeImagen) y la Y medida desde el borde superior de la hoja (la misma fórmula
 * que L.papelAPantalla). Dentro de la capa se trabaja en mm con Y hacia abajo: un texto va en
 * (x, alto de la hoja − y) de su línea base.
 *
 * Texto, como lo escribe PyMuPDF: Arial, tamaño = altura de las MAYÚSCULAS / altura_mayusculas
 * (en mm), sin kerning ni ligaduras, los espacios tal cual, y `textLength` = el ancho calculado
 * (así la línea mide en pantalla lo mismo que en el PDF aunque el navegador redondee).
 *
 * Capas (las crea editor_ui.js, en el orden de `componer`): símbolos (antes que los detalles),
 * textos y etiquetas «ESC» (encima de los detalles), firmas (cajas punteadas) y problemas
 * (celda en rojo: no se dibuja; ámbar: el editor no puede medir).
 */
(function (raiz) {
  "use strict";

  const CLASE_PROBLEMA = { error: "vp-problema", aviso: "vp-problema aviso" };
  const ALTURA_ROTULO_FIRMA_MM = 1.4; // texto «firma: <persona>» dentro de la caja
  const AUMENTO = 100; // los textos se escriben 100 veces más grandes y se reducen (ver `texto`)

  /**
   * opciones: {svg, capas: {simbolos, textos, etiquetas, firmas, problemas} (<g> vacíos ya en
   * el lienzo), escala (L.escalaDeImagen), fuente (tabla de anchos), simbolos (los del editor,
   * con imagen.data_url)}.
   */
  function crear(opciones) {
    const NS = opciones.svg.namespaceURI;
    const escala = opciones.escala;
    const alto = escala.altoMm;
    const fuente = opciones.fuente;
    const imagenes = new Map((opciones.simbolos || []).map((s) => [s.id, s.imagen && s.imagen.data_url]));
    const capas = opciones.capas;

    for (const g of Object.values(capas)) {
      g.setAttribute("transform", "matrix(" + escala.pxPorMmX + " 0 0 " + escala.pxPorMmY + " 0 0)");
    }

    function nodo(nombre, atributos, padre) {
      const n = document.createElementNS(NS, nombre);
      for (const [k, v] of Object.entries(atributos)) n.setAttribute(k, v);
      padre.appendChild(n);
      return n;
    }

    /** Rectángulo de papel [x0, y0, x1, y1] -> atributos SVG en mm con Y hacia abajo. */
    function rect(r) {
      return { x: r[0], y: alto - r[3], width: Math.max(0, r[2] - r[0]), height: Math.max(0, r[3] - r[1]) };
    }

    /**
     * Cada línea va en su base con `translate` y se escribe AUMENTADA (× AUMENTO, reducida con
     * `scale`): a ~3 unidades de tamaño el navegador redondea el avance de cada letra y la línea
     * mide hasta un 1 % distinto; a ~300 unidades mide como la tabla de anchos.
     */
    function texto(t, padre) {
      const em = t.altura_mm / fuente.altura_mayusculas;
      for (const linea of t.lineas) {
        if (!linea.texto) continue;
        const n = nodo("text", { class: "vp-texto", x: 0, y: 0, "font-size": em * AUMENTO, "data-ruta": t.ruta,
          transform: "translate(" + linea.base_mm[0] + " " + (alto - linea.base_mm[1]) + ") scale(" + 1 / AUMENTO + ")" }, padre);
        if (linea.ancho_mm > 0) {
          n.setAttribute("textLength", linea.ancho_mm * AUMENTO);
          n.setAttribute("lengthAdjust", "spacing");
        }
        n.textContent = linea.texto;
      }
    }

    function dibujarRotulo(piezas) {
      capas.simbolos.replaceChildren();
      capas.textos.replaceChildren();
      capas.firmas.replaceChildren();
      capas.problemas.replaceChildren();
      for (const s of piezas.simbolos) {
        const url = imagenes.get(s.id);
        if (!url) continue;
        const img = nodo("image", Object.assign(rect(s.pagina_mm), { preserveAspectRatio: "none", class: "vp-simbolo",
          "data-id": s.id }), capas.simbolos);
        img.setAttribute("href", url);
      }
      for (const t of piezas.textos) texto(t, capas.textos);
      for (const f of piezas.firmas) {
        const g = nodo("g", { class: "vp-firma", "data-ruta": f.ruta }, capas.firmas);
        nodo("rect", Object.assign(rect(f.caja_mm), { class: "vp-caja-firma" }), g);
        // Ayuda del editor (no sale en el PDF): se achica si no cabe a lo ancho de la caja.
        const leyenda = "firma: " + f.persona;
        let ems = 0;
        for (const c of leyenda) ems += c in fuente.anchos_em ? fuente.anchos_em[c] : 0.6;
        const ancho = f.caja_mm[2] - f.caja_mm[0] - 0.4;
        const altura = Math.min(ALTURA_ROTULO_FIRMA_MM, ancho * fuente.altura_mayusculas / Math.max(ems, 1e-9));
        const n = nodo("text", { class: "vp-rotulo-firma", x: (f.caja_mm[0] + f.caja_mm[2]) / 2,
          y: alto - (f.caja_mm[1] + f.caja_mm[3]) / 2 + altura / 2, "font-size": altura / fuente.altura_mayusculas }, g);
        n.textContent = leyenda;
        nodo("title", {}, g).textContent = "Firma en imagen de «" + f.persona + "»: el editor no la muestra; componer la pondrá en esta caja.";
      }
      for (const p of piezas.problemas) {
        if (!p.rect_mm) continue;
        const r = nodo("rect", Object.assign(rect(p.rect_mm), { class: CLASE_PROBLEMA[p.nivel] || CLASE_PROBLEMA.error,
          "data-ruta": p.ruta }), capas.problemas);
        nodo("title", {}, r).textContent = p.mensaje;
      }
    }

    function dibujarEtiquetas(textos) {
      capas.etiquetas.replaceChildren();
      for (const t of textos) texto(t, capas.etiquetas);
    }

    function limpiar() {
      for (const g of Object.values(capas)) g.replaceChildren();
    }

    return { dibujarRotulo, dibujarEtiquetas, limpiar };
  }

  /**
   * ¿La «Arial» del navegador mide como la tabla de anchos? Mide un texto de prueba con un
   * <canvas> (sin kerning) y lo compara con la suma de avances. Devuelve la diferencia relativa
   * (0,001 = 0,1 %) o null si no se puede medir.
   */
  function diferenciaDeFuente(fuente) {
    try {
      const muestra = "ABCDEFGHIJKLMNÑOPQRSTUVWXYZ 0123456789 áéíóú.,:-/";
      let suma = 0;
      for (const c of muestra) {
        if (!(c in fuente.anchos_em)) return null;
        suma += fuente.anchos_em[c];
      }
      const ctx = document.createElement("canvas").getContext("2d");
      ctx.font = "100px Arial";
      if ("fontKerning" in ctx) ctx.fontKerning = "none";
      return Math.abs(ctx.measureText(muestra).width / 100 - suma) / suma;
    } catch (e) {
      return null;
    }
  }

  raiz.EditorLienzoRotulo = { crear, diferenciaDeFuente };
})(typeof self !== "undefined" ? self : this);
