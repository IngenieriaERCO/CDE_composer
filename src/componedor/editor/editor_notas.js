/*
 * Editor de planos — lógica de las NOTAS del rótulo (subfase 4.3c). Pura, sin pantalla: funciona
 * en el navegador (window.EditorNotas) y en Node (module.exports).
 *
 * - Lista editable: el valor "notas" del plano -> elementos {texto, vinetas, original, tocado,
 *   clave}. Al guardar, lo que no se tocó sale tal como vino (`original`); lo tocado o nuevo,
 *   como texto, o {"texto", "vinetas"} si tiene viñetas. "archivos" y cualquier otra clave de
 *   "notas" se conservan intactos.
 * - Catálogo (notas típicas de --notas): cada nota se identifica por su archivo y línea
 *   («vias/pavimentos.txt, línea 4», `claveNota`). Una nota del plano igual a una del catálogo queda enlazada
 *   a ella (casilla marcada); una nota elegida no se puede elegir dos veces.
 * - Validación: los MISMOS textos que notas.leer_notas / notas._adicional / notas._nota y la
 *   revisión de caracteres de rotulo._notas. Los archivos .txt referidos no se pueden leer
 *   desde el navegador: solo se revisa que "archivos" sea una lista de textos; y como sus notas
 *   van antes, con "archivos" el número «la nota k» de los mensajes de caracteres cuenta solo
 *   las adicionales. Si las notas CABEN en la celda lo dice `componer` (4.3e).
 * - Aviso propio del editor (Python lo omite sin decir nada): una nota adicional vacía.
 * - Notas que ya entran por "archivos" (4.3c): si una ruta de "archivos" es un .txt del
 *   catálogo (misma ruta, vista desde la carpeta del plano.json), sus notas típicas no se
 *   pueden marcar, y una adicional con el mismo texto que una de ellas da un aviso («esta nota
 *   ya viene en …»). Un .txt de "archivos" que no está en el catálogo no se puede leer aquí.
 */
(function (raiz, fabrica) {
  "use strict";
  const F = typeof module === "object" && module.exports ? require("./editor_formularios.js") : raiz.EditorFormularios;
  const api = fabrica(F);
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    raiz.EditorNotas = api;
  }
})(typeof self !== "undefined" ? self : this, function (F) {
  "use strict";

  const esObjeto = (v) => v !== null && typeof v === "object" && !Array.isArray(v);
  const clonar = (v) => (v === undefined ? undefined : JSON.parse(JSON.stringify(v)));
  const NUMERO_PROPIO = /^(\d+)\s*[.)]\s+/u; // como notas.NUMERO_PROPIO
  const SIGNO_VINETA = "•";
  const CLAVES = ["archivos", "adicionales"];
  const CLAVES_ADICIONAL = ["texto", "vinetas"];

  /** " ".join(texto.split()) de Python. */
  function normalizar(texto) {
    return String(texto).split(/\s+/u).filter(Boolean).join(" ");
  }

  /** notas._tipo (distinto del de rotulo.py en listas y booleanos). */
  function tipo(v) {
    if (v === null || v === undefined) return "null";
    if (typeof v === "string") return "texto " + F.pyRepr(v);
    if (Array.isArray(v)) return "una lista con elementos que no son texto";
    if (esObjeto(v)) return "un objeto";
    if (typeof v === "boolean") return "bool " + (v ? "True" : "False");
    return (Number.isInteger(v) ? "int " : "float ") + v;
  }

  // ---------------------------------------------------------------------------------------
  // Validación (mismos textos que Python).
  // ---------------------------------------------------------------------------------------

  /** notas._nota: {nota: {texto, origen} | null, aviso}. */
  function leerNota(texto, origen) {
    let limpio = normalizar(texto);
    if (!limpio) return { nota: null, aviso: "" };
    const numero = NUMERO_PROPIO.exec(limpio);
    if (numero) {
      limpio = limpio.slice(numero[0].length);
      return { nota: { texto: limpio, origen, vinetas: [] }, aviso: "Advertencia: la nota de " + origen +
        " traía su propio número «" + numero[0].trim() + "»; se quitó: el componedor numera las notas solo." };
    }
    return { nota: { texto: limpio, origen, vinetas: [] }, aviso: "" };
  }

  /** notas._adicional. */
  function leerAdicional(item, i, problemas, avisosEditor) {
    const donde = "rotulo.notas.adicionales[" + i + "]";
    const origen = "adicionales[" + i + "]";
    if (typeof item === "string") {
      if (item.includes("\n")) {
        problemas.push(donde + ": una nota adicional va en una sola línea (trae un salto de línea); " +
          "para varias notas use varios textos en la lista");
        return { nota: null, aviso: "" };
      }
      const r = leerNota(item, origen);
      if (!r.nota) avisosEditor.push(donde + ": la nota está vacía; componer la omite (no se numera)");
      return r;
    }
    if (!esObjeto(item)) {
      problemas.push(donde + ": se esperaba un texto o {\"texto\": ..., \"vinetas\": [...]}; tiene " + tipo(item));
      return { nota: null, aviso: "" };
    }
    const n = problemas.length;
    for (const k of Object.keys(item).filter((k) => !CLAVES_ADICIONAL.includes(k)).sort()) {
      problemas.push(donde + "." + k + ": campo no reconocido (campos válidos: texto, vinetas)");
    }
    const texto = item.texto;
    if (typeof texto !== "string" || !texto.trim() || texto.includes("\n")) {
      problemas.push(donde + ".texto: se esperaba el texto de la nota (una línea, no vacío); tiene " + tipo(texto));
    }
    const vinetas = "vinetas" in item ? item.vinetas : [];
    if (!Array.isArray(vinetas) || !vinetas.every((v) => typeof v === "string" && !v.includes("\n"))) {
      problemas.push(donde + ".vinetas: se esperaba una lista de textos de una línea; tiene " + tipo(vinetas));
    }
    if (problemas.length > n) return { nota: null, aviso: "" };
    const r = leerNota(texto, origen);
    if (r.nota) r.nota.vinetas = vinetas.filter((v) => v.trim()).map(normalizar);
    return r;
  }

  /**
   * {errores, avisos, notas} del valor "notas" del plano. `avisos`: los de Python (número
   * propio) y, al final, los propios del editor (nota vacía; con `catalogo`, nota repetida de
   * un .txt de `archivos`).
   */
  function validarNotas(valor, fuente, catalogo) {
    const errores = [];
    const avisos = [];
    const avisosEditor = [];
    if (valor === undefined) return { errores, avisos, notas: [] };
    if (!esObjeto(valor)) {
      errores.push("rotulo.notas: se esperaba {\"archivos\": [...], \"adicionales\": [...]}; tiene " + tipo(valor));
      return { errores, avisos, notas: [] };
    }
    for (const k of Object.keys(valor).filter((k) => !CLAVES.includes(k)).sort()) {
      errores.push("rotulo.notas." + k + ": campo no reconocido (campos válidos: adicionales, archivos)");
    }
    const archivos = "archivos" in valor ? valor.archivos : [];
    if (!Array.isArray(archivos) || !archivos.every((v) => typeof v === "string")) {
      errores.push("rotulo.notas.archivos: se esperaba una lista de textos; tiene " + tipo(archivos));
    }
    let adicionales = "adicionales" in valor ? valor.adicionales : [];
    if (!Array.isArray(adicionales)) {
      errores.push("rotulo.notas.adicionales: se esperaba una lista de textos u objetos {\"texto\", \"vinetas\"}; " +
        "tiene " + tipo(adicionales));
      adicionales = [];
    }
    const notas = [];
    adicionales.forEach((item, i) => {
      const r = leerAdicional(item, i, errores, avisosEditor);
      if (r.nota) notas.push(r.nota);
      if (r.aviso) avisos.push(r.aviso);
    });
    // rotulo._notas: caracteres que la fuente no tiene (texto + viñetas + el signo de viñeta).
    notas.forEach((nota, k) => {
      const texto = [nota.texto].concat(nota.vinetas).join(" ") + (nota.vinetas.length ? " " + SIGNO_VINETA : "");
      const faltan = F.caracteresFaltantes(texto, fuente).faltan;
      if (faltan.length) {
        errores.push("rotulo.notas: la nota " + (k + 1) + " (" + nota.origen + ") tiene caracteres que la fuente " +
          fuente.nombre + " no tiene: " + faltan.map(F.pyRepr).join(" "));
      }
    });
    return { errores, avisos: avisos.concat(avisosEditor, avisosRepetidas(valor, catalogo)), notas };
  }

  // ---------------------------------------------------------------------------------------
  // Notas que ya entran por "archivos" (4.3c): mismo .txt que uno del catálogo.
  // ---------------------------------------------------------------------------------------

  const esAbsoluta = (r) => /^[A-Za-z]:\//.test(r) || r.startsWith("/");

  /**
   * Una ruta para comparar: «\» -> «/», sin «.», «x/..» resuelto, tildes normalizadas (NFC) y
   * sin distinguir mayúsculas (Windows, como `componer`).
   */
  function normalizarRutaArchivo(ruta) {
    const partes = [];
    for (const p of String(ruta).replace(/\\/g, "/").split("/")) {
      if (p === "." || (p === "" && partes.length)) continue;
      if (p === ".." && partes.length && partes[partes.length - 1] !== ".." && partes[partes.length - 1] !== "") {
        partes.pop();
      } else {
        partes.push(p);
      }
    }
    return partes.join("/").normalize("NFC").toLowerCase();
  }

  /**
   * .txt del catálogo que el plano ya incluye en `archivos`: Map archivo del catálogo -> la ruta
   * tal como la escribe el plano. Se comparan "ruta_plano" (relativa a la carpeta del editor,
   * donde va el plano.json) o "absoluta" con cada ruta de `archivos`.
   */
  function archivosIncluidos(archivosPlan, catalogo) {
    const incluidos = new Map();
    if (!Array.isArray(archivosPlan) || !catalogo) return incluidos;
    for (const ruta of archivosPlan) {
      if (typeof ruta !== "string") continue;
      const buscada = normalizarRutaArchivo(ruta);
      for (const g of catalogo.grupos) {
        for (const a of g.archivos) {
          const suya = esAbsoluta(ruta.replace(/\\/g, "/")) ? a.absoluta : a.ruta_plano;
          if (suya && normalizarRutaArchivo(suya) === buscada && !incluidos.has(a.archivo)) incluidos.set(a.archivo, ruta);
        }
      }
    }
    return incluidos;
  }

  /** Línea de una nota del catálogo («generales.txt, línea 4» -> 4). */
  function lineaDe(nota) {
    const m = /línea (\d+)$/.exec(nota.origen);
    return m ? Number(m[1]) : null;
  }

  /**
   * Notas que entran por `archivos` y que el editor conoce (las de los .txt del catálogo):
   * [{clave, texto, ruta (como la escribe el plano), linea}], en el orden de `archivos`.
   */
  function notasDeArchivos(archivosPlan, catalogo) {
    const incluidos = archivosIncluidos(archivosPlan, catalogo);
    const lista = [];
    for (const g of (catalogo && catalogo.grupos) || []) {
      for (const a of g.archivos) {
        if (!incluidos.has(a.archivo)) continue;
        for (const n of a.notas) {
          lista.push({ clave: claveNota(a.archivo, n), texto: n.texto, ruta: incluidos.get(a.archivo), linea: lineaDe(n) });
        }
      }
    }
    const orden = (archivosPlan || []).map(normalizarRutaArchivo);
    return lista.sort((x, y) => orden.indexOf(normalizarRutaArchivo(x.ruta)) - orden.indexOf(normalizarRutaArchivo(y.ruta)));
  }

  /** Claves de las notas típicas que ya entran por `archivos` (no se pueden marcar). */
  function clavesIncluidas(archivosPlan, catalogo) {
    return new Set(notasDeArchivos(archivosPlan, catalogo).map((n) => n.clave));
  }

  /**
   * Avisos del editor: una nota adicional con el MISMO texto (normalizado como Python, sin el
   * número propio) que una que ya entra por `archivos` saldría dos veces en el plano.
   */
  function avisosRepetidas(valor, catalogo) {
    if (!esObjeto(valor) || !Array.isArray(valor.adicionales)) return [];
    const deArchivos = notasDeArchivos(valor.archivos, catalogo);
    if (!deArchivos.length) return [];
    const avisos = [];
    valor.adicionales.forEach((item, i) => {
      const texto = typeof item === "string" ? item : esObjeto(item) && typeof item.texto === "string" ? item.texto : null;
      if (texto === null || texto.includes("\n")) return;
      const r = leerNota(texto, "adicionales[" + i + "]");
      const igual = r.nota && deArchivos.find((n) => n.texto === r.nota.texto);
      if (igual) {
        avisos.push("rotulo.notas.adicionales[" + i + "]: esta nota ya viene en " + igual.ruta +
          (igual.linea ? " (línea " + igual.linea + ")" : "") + "; saldría dos veces en el plano");
      }
    });
    return avisos;
  }

  // ---------------------------------------------------------------------------------------
  // Lista editable.
  // ---------------------------------------------------------------------------------------

  /** ¿Una nota adicional que la lista sabe mostrar? (texto de una línea, o {texto, vinetas}) */
  function adicionalRepresentable(item) {
    if (typeof item === "string") return !item.includes("\n");
    return esObjeto(item) && Object.keys(item).every((k) => CLAVES_ADICIONAL.includes(k)) &&
      typeof item.texto === "string" && !item.texto.includes("\n") &&
      (item.vinetas === undefined || (Array.isArray(item.vinetas) &&
        item.vinetas.every((v) => typeof v === "string" && !v.includes("\n"))));
  }

  /**
   * Clave de una nota del catálogo: la ruta relativa del .txt y su línea
   * («vias/pavimentos.txt, línea 4»). El `origen` de Python solo trae el NOMBRE del archivo,
   * que puede repetirse en dos grupos.
   */
  function claveNota(archivo, nota) {
    const coma = nota.origen.lastIndexOf(",");
    return archivo + (coma >= 0 ? nota.origen.slice(coma) : ", " + nota.origen);
  }

  /** El aviso de número propio de ESA nota (lo dejó Python al leer el .txt). */
  function avisosDeNota(archivo, nota) {
    return archivo.avisos.filter((x) => x.includes("la nota de " + nota.origen + " traía"));
  }

  /** Índice del catálogo: clave -> {texto, vinetas, archivo, grupo, avisos}. */
  function indiceCatalogo(catalogo) {
    const indice = new Map();
    for (const g of (catalogo && catalogo.grupos) || []) {
      for (const a of g.archivos) {
        for (const n of a.notas) {
          indice.set(claveNota(a.archivo, n), { texto: n.texto, vinetas: n.vinetas.slice(), archivo: a.archivo,
            grupo: g.titulo, avisos: avisosDeNota(a, n) });
        }
      }
    }
    return indice;
  }

  const mismaNota = (a, b) => normalizar(a.texto) === normalizar(b.texto) &&
    a.vinetas.length === b.vinetas.length && a.vinetas.every((v, i) => normalizar(v) === normalizar(b.vinetas[i]));

  /**
   * {archivos, otras (claves extra de "notas"), items, editable}. Cada item: {texto, vinetas,
   * original, tocado: false, clave (origen en el catálogo o null)}.
   */
  function lista(valor, catalogo) {
    const v = esObjeto(valor) ? valor : {};
    const adicionales = Array.isArray(v.adicionales) ? v.adicionales : [];
    const editable = (valor === undefined || esObjeto(valor)) &&
      (v.adicionales === undefined || Array.isArray(v.adicionales)) && adicionales.every(adicionalRepresentable);
    const indice = indiceCatalogo(catalogo);
    // Las típicas que ya entran por "archivos" no se enlazan: esa nota queda «a mano» y avisa.
    const usadas = clavesIncluidas(v.archivos, catalogo);
    const items = editable ? adicionales.map((item) => {
      const texto = typeof item === "string" ? item : item.texto;
      const vinetas = typeof item === "string" ? [] : (item.vinetas || []).slice();
      let clave = null;
      for (const [origen, n] of indice) {
        if (!usadas.has(origen) && mismaNota({ texto, vinetas: vinetas.filter((x) => x.trim()) }, n)) {
          clave = origen;
          usadas.add(origen);
          break;
        }
      }
      return { texto, vinetas, original: clonar(item), tocado: false, clave };
    }) : [];
    return { archivos: Array.isArray(v.archivos) ? v.archivos.slice() : [], items, editable };
  }

  /** Item nuevo desde el catálogo (ya sin número propio: lo quitó Python). */
  function itemDeCatalogo(origen, catalogo) {
    const n = indiceCatalogo(catalogo).get(origen);
    return n ? { texto: n.texto, vinetas: n.vinetas.slice(), original: undefined, tocado: true, clave: origen } : null;
  }

  /** Item nuevo a mano: viñetas = una por línea (las vacías no cuentan). null si no hay texto. */
  function itemAMano(texto, vinetasTexto) {
    const t = String(texto || "").replace(/\r?\n/g, " ");
    if (!t.trim()) return null;
    const vinetas = String(vinetasTexto || "").split(/\r?\n/).map((x) => x.trim()).filter(Boolean);
    return { texto: t.trim(), vinetas, original: undefined, tocado: true, clave: null };
  }

  /** Viñetas desde la caja de texto (una por línea). */
  function vinetasDeTexto(texto) {
    return String(texto || "").split(/\r?\n/).map((x) => x.trim()).filter(Boolean);
  }

  /** Cómo se guarda un item: el original si no se tocó; si no, texto u objeto con viñetas. */
  function itemParaGuardar(item) {
    if (!item.tocado && item.original !== undefined) return clonar(item.original);
    const vinetas = item.vinetas.filter((v) => String(v).trim());
    return vinetas.length ? { texto: item.texto, vinetas } : item.texto;
  }

  /**
   * El valor "notas" para guardar: el actual con "adicionales" = la lista (en su orden); sin
   * notas en la lista se quita "adicionales"; si "notas" queda vacío, undefined.
   */
  function notasParaGuardar(valorActual, items) {
    const nuevo = esObjeto(valorActual) ? clonar(valorActual) : {};
    if (items.length) nuevo.adicionales = items.map(itemParaGuardar);
    else delete nuevo.adicionales;
    return Object.keys(nuevo).length ? nuevo : undefined;
  }

  function mover(items, i, paso) {
    const j = i + paso;
    if (j < 0 || j >= items.length) return items.slice();
    const copia = items.slice();
    [copia[i], copia[j]] = [copia[j], copia[i]];
    return copia;
  }

  function quitar(items, i) {
    return items.filter((x, k) => k !== i);
  }

  /**
   * Marcar una nota del catálogo: se agrega al final. No se repite, y no se agrega si ya entra
   * por `archivosPlan` (el .txt está en "archivos").
   */
  function marcar(items, origen, catalogo, archivosPlan) {
    if (items.some((x) => x.clave === origen) || clavesIncluidas(archivosPlan, catalogo).has(origen)) return items.slice();
    const item = itemDeCatalogo(origen, catalogo);
    return item ? items.concat([item]) : items.slice();
  }

  /** Desmarcar: sale de la lista la nota enlazada a ese origen. */
  function desmarcar(items, origen) {
    return items.filter((x) => x.clave !== origen);
  }

  /** Número de cada nota de la lista (1…N; las viñetas no se numeran). */
  function numeros(items) {
    return items.map((x, i) => i + 1);
  }

  return {
    NUMERO_PROPIO,
    normalizar,
    tipo,
    leerNota,
    validarNotas,
    adicionalRepresentable,
    claveNota,
    avisosDeNota,
    normalizarRutaArchivo,
    archivosIncluidos,
    notasDeArchivos,
    clavesIncluidas,
    avisosRepetidas,
    indiceCatalogo,
    lista,
    itemDeCatalogo,
    itemAMano,
    vinetasDeTexto,
    itemParaGuardar,
    notasParaGuardar,
    mover,
    quitar,
    marcar,
    desmarcar,
    numeros,
  };
});
