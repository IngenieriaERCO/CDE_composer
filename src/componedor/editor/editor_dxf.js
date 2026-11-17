/*
 * Editor de planos — textos de la carpeta del DXF (etapa 1). Lógica pura: funciona en el
 * navegador (window.EditorDxf) y en Node (module.exports), para probarla desde pytest.
 *
 * Los números llegan del servidor (bloques_dxf.py ya calculó tamaño, escala sugerida, página y
 * notas); aquí solo se escriben en español, con coma decimal.
 */
(function (raiz, fabrica) {
  "use strict";
  const api = fabrica();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    raiz.EditorDxf = api;
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const ETAPAS = {
    start: "Arrancando el trabajador del exportador",
    read: "Leyendo el DXF",
    hash: "Calculando la huella y el hash del DXF",
    blocks: "Listando los bloques",
    layers: "Leyendo las capas",
  };
  const SIN_NOTICIAS_S = 30;

  const numero = (v, decimales) => v.toFixed(decimales).replace(".", ",");

  /** "6,8 MB" (o KB / bytes). */
  function tamanoArchivo(bytes) {
    if (typeof bytes !== "number") return "tamaño desconocido";
    if (bytes >= 1024 * 1024 * 1024) return numero(bytes / (1024 * 1024 * 1024), 2) + " GB";
    if (bytes >= 1024 * 1024) return numero(bytes / (1024 * 1024), 1) + " MB";
    if (bytes >= 1024) return numero(bytes / 1024, 0) + " KB";
    return bytes + " bytes";
  }

  /** "m (verificadas)", "m, sin verificar" o "desconocidas". */
  function textoUnidades(u) {
    if (!u || !u.nombre) return "unidades desconocidas";
    return "unidades: " + u.nombre + (u.verificadas ? " (verificadas)" : ", sin verificar");
  }

  function textoTamano(b) {
    if (!b.tamano_m) return "tamaño real desconocido";
    return numero(b.tamano_m[0], 3) + " × " + numero(b.tamano_m[1], 3) + " m";
  }

  function textoOcurrencia(b) {
    return b.total_ocurrencias > 1 ? "ocurrencia " + b.ocurrencia + " de " + b.total_ocurrencias : "";
  }

  /** "Escala sugerida 1:50 · página 17,96 × 25,36 mm" o null si no hay. */
  function textoEscala(b) {
    if (!b.escala_sugerida) return null;
    const p = b.pagina_sugerida_mm;
    return "Escala sugerida 1:" + b.escala_sugerida + " · página " + (b.caja_exacta ? "" : "≤ ") +
      numero(p[0], 1) + " × " + numero(p[1], 1) + " mm";
  }

  /** Las líneas de la tarjeta de un bloque, en orden (sin las notas). */
  function lineasBloque(b) {
    const lineas = [];
    const ocurrencia = textoOcurrencia(b);
    const capa = b.capa ? "capa " + b.capa : "";
    if (ocurrencia || capa) lineas.push([ocurrencia, capa].filter(Boolean).join(" · "));
    lineas.push(textoTamano(b) + " · " + textoUnidades(b.unidades));
    const escala = textoEscala(b);
    if (escala) lineas.push(escala);
    return lineas;
  }

  /** "GUAMO.dxf · 65 bloques" (el nombre va aparte, en negrita). */
  function resumenDxf(catalogo) {
    const n = catalogo.bloques.length;
    return n + (n === 1 ? " bloque" : " bloques");
  }

  function detalleDxf(catalogo) {
    const partes = [tamanoArchivo(catalogo.dxf.bytes), textoUnidades(catalogo.unidades),
      "margen " + numero(catalogo.margen_mm, 1).replace(/,0$/, "") + " mm"];
    if (catalogo.dxf.segundos_lectura) partes.push("leído en " + numero(catalogo.dxf.segundos_lectura, 1) + " s");
    return partes.join(" · ");
  }

  /** Texto del avance de una tarea en curso. */
  function textoAvance(foto) {
    const a = foto.avance || {};
    let t = a.message || ETAPAS[a.stage] || (foto.estado === "en_cola" ? "En espera" : "Trabajando");
    if (typeof a.percent === "number") t += " — " + numero(a.percent, 0) + " %";
    if (foto.cancelando) t += " (cancelando…)";
    if (foto.estado === "en_curso" && foto.sin_noticias_s >= SIN_NOTICIAS_S) {
      t += " · sin noticias del trabajador hace " + numero(foto.sin_noticias_s, 0) + " s (un paso largo, " +
        "como leer un DXF grande, no informa avance)";
    }
    return t;
  }

  /** Texto de una tarea que no terminó bien: mensaje y consejo. */
  function textoError(foto) {
    const e = foto.error || {};
    return [e.mensaje || "La tarea no terminó.", e.consejo].filter(Boolean).join(" ");
  }

  return { ETAPAS, SIN_NOTICIAS_S, tamanoArchivo, textoUnidades, textoTamano, textoOcurrencia,
    textoEscala, lineasBloque, resumenDxf, detalleDxf, textoAvance, textoError };
});
