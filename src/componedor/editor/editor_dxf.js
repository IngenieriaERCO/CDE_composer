/*
 * Editor de planos — textos de la carpeta del DXF (etapa 1). Lógica pura: funciona en el
 * navegador (window.EditorDxf) y en Node (module.exports), para probarla desde pytest.
 *
 * Los números llegan del servidor (bloques_dxf.py ya calculó tamaño, escala sugerida, página y
 * notas); aquí solo se escriben en español, con coma decimal.
 *
 * Bloques anónimos (*U ofrecidos por el trabajador): van aparte, en «Anónimos (opcionales)»,
 * con su etiqueta (capa + handle) como nombre y un filtro por texto (separarBloques,
 * filtrarBloques, textosAnonimos).
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
    draw: "Dibujando",
    paint: "Pintando la vista previa",
    extract: "Extrayendo el bloque",
    analyze: "Analizando (fidelidad e inventario)",
    pdf: "Escribiendo el PDF",
    checks: "Comprobando el paquete",
    publish: "Publicando el paquete",
    verificar: "Verificando el paquete (Componedor)",
  };
  const SIN_NOTICIAS_S = 30;
  const LIMITE_TARJETAS = 200; // anónimos que se muestran a la vez (el filtro encuentra el resto)

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

  /** El nombre que se muestra: la etiqueta (capa + handle en un anónimo) o el nombre. */
  function nombreBloque(b) {
    return (b && (b.etiqueta || b.nombre)) || "?";
  }

  /** "1 234" (miles con espacio fino, como en los planos). */
  function entero(n) {
    return String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, "\u202f");
  }

  /** Las líneas de la tarjeta de un bloque, en orden (sin las notas). */
  function lineasBloque(b) {
    const lineas = [];
    if (b.anonimo) {
      // La etiqueta ya dice capa y handle: aquí el *U (cambia al guardar en AutoCAD) y su tamaño.
      const visibles = typeof b.entidades_visibles === "number"
        ? " · " + entero(b.entidades_visibles) + " entidades visibles" : "";
      lineas.push("bloque anónimo " + b.nombre + visibles);
    } else {
      const ocurrencia = textoOcurrencia(b);
      const capa = b.capa ? "capa " + b.capa : "";
      if (ocurrencia || capa) lineas.push([ocurrencia, capa].filter(Boolean).join(" · "));
    }
    lineas.push(textoTamano(b) + " · " + textoUnidades(b.unidades));
    const escala = textoEscala(b);
    if (escala) lineas.push(escala);
    return lineas;
  }

  /** {nombrados, anonimos}: los bloques de la carpeta, en el orden del DXF. */
  function separarBloques(catalogo) {
    const bloques = (catalogo && catalogo.bloques) || [];
    return { nombrados: bloques.filter((b) => !b.anonimo), anonimos: bloques.filter((b) => b.anonimo) };
  }

  /** Minúsculas y sin tildes, para comparar. */
  const normal = (t) => String(t || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();

  /**
   * Los bloques que contienen TODAS las palabras del filtro en su etiqueta, nombre, capa o
   * handle (sin distinguir mayúsculas ni tildes). Sin filtro, todos.
   */
  function filtrarBloques(bloques, texto) {
    const palabras = normal(texto).split(/\s+/).filter(Boolean);
    if (!palabras.length) return bloques.slice();
    return bloques.filter((b) => {
      const donde = normal([b.etiqueta, b.nombre, b.capa, b.handle].join(" "));
      return palabras.every((p) => donde.includes(p));
    });
  }

  /**
   * Textos de la subsección de anónimos: {titulo, explicacion, pequenos, mostrando}.
   * `pequenos` (null si no hay) cuenta los que no se ofrecen; `mostrando` (null si se ven
   * todos) dice cuántos se muestran con el filtro o el límite.
   */
  function textosAnonimos(catalogo, encontrados, mostrados) {
    const { anonimos } = separarBloques(catalogo);
    const umbral = catalogo.anonimos_min_entidades;
    const desde = typeof umbral === "number" ? "con " + entero(umbral) + " entidades visibles o más" :
      "que el exportador ofrece";
    const omitidos = catalogo.anonimos_omitidos || { cantidad: 0 };
    let pequenos = null;
    if (omitidos.cantidad > 0) {
      pequenos = (omitidos.cantidad === 1 ? "Otro anónimo más pequeño no se ofrece" :
        "Otros " + entero(omitidos.cantidad) + " anónimos más pequeños no se ofrecen") +
        (typeof umbral === "number" ? " (menos de " + entero(umbral) + " entidades visibles)" : "") +
        ": etiquetas, cotas y piezas que AutoCAD o Civil 3D crean por montones.";
    }
    let mostrando = null;
    if (encontrados !== undefined && (encontrados < anonimos.length || mostrados < encontrados)) {
      mostrando = "Mostrando " + entero(mostrados) + " de " + entero(encontrados) +
        (encontrados < anonimos.length ? " que coinciden (" + entero(anonimos.length) + " en total)" : "") +
        (mostrados < encontrados ? ": escriba en el filtro para encontrar los demás." : ".");
    }
    return {
      titulo: "Anónimos (opcionales) (" + anonimos.length + ")",
      explicacion: "Bloques anónimos (*U) del Model Space " + desde + ", como las mesas de paneles de " +
        "PVcase o las tablas de Civil 3D. Se nombran por capa y handle, porque AutoCAD renumera los *U " +
        "al guardar. Se agregan, escalan y exportan como cualquier bloque.",
      pequenos, mostrando,
    };
  }

  /** "GUAMO.dxf · 65 bloques" (el nombre va aparte, en negrita); "· 3 anónimos" si hay. */
  function resumenDxf(catalogo) {
    const { nombrados, anonimos } = separarBloques(catalogo);
    const n = nombrados.length;
    return n + (n === 1 ? " bloque" : " bloques") +
      (anonimos.length ? " · " + anonimos.length + (anonimos.length === 1 ? " anónimo" : " anónimos") : "");
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

  /** El texto técnico de un error (para «Ver detalle») y dónde está el registro; null si no hay. */
  function textoDetalle(foto) {
    const e = (foto && foto.error) || {};
    if (!e.detalle) return null;
    return e.detalle + (e.registro ? "\n\nRegistro del trabajador: " + e.registro : "");
  }

  return { ETAPAS, SIN_NOTICIAS_S, LIMITE_TARJETAS, textoDetalle, tamanoArchivo, textoUnidades, textoTamano,
    textoOcurrencia, textoEscala, nombreBloque, lineasBloque, separarBloques, filtrarBloques, textosAnonimos,
    resumenDxf, detalleDxf, textoAvance, textoError };
});
