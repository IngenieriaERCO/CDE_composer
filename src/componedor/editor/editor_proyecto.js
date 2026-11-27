/*
 * Proyecto de varias hojas en UN archivo (plano versión 8, subfase 8b): lógica sin pantalla,
 * la misma en el navegador y en las pruebas de Node. Igual que plano_proyecto.py:
 *
 *   {"version": 8, "formato", "plantilla", "dxf": [...], "ortofoto": {...},
 *    "hojas": [{"nombre", "detalles", "zonas": [{"dxf": id, ...}], "rosa_vientos", "rotulo",
 *               "copiado_de"}]}
 *
 * Cada hoja se lee y se escribe con lo de siempre (EditorLogica.leerPlano / objetoPlano) como si
 * fuera un plano versión 7; aquí solo se arma y se desarma el proyecto. Hoja, de y número de plano
 * salen de la posición de la hoja (como hojas_proyecto.automaticos_de_lista).
 */
(function (raiz, fabrica) {
  "use strict";
  const api = fabrica();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    raiz.EditorProyecto = api;
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const enNode = typeof module === "object" && module.exports;
  const L = enNode ? require("./editor_logica.js") : self.EditorLogica;
  const B = enNode ? require("./editor_bloques.js") : self.EditorBloques;

  const VERSION = 8;
  const clonar = (v) => (v === undefined ? undefined : JSON.parse(JSON.stringify(v)));
  const esObjeto = (v) => v !== null && typeof v === "object" && !Array.isArray(v);

  /** La hoja `h` de un proyecto como un plano versión 7 (lo del proyecto + lo suyo). */
  function planoDeHoja(proyecto, h) {
    const plano = { version: 7, formato: proyecto.formato };
    if ("plantilla" in proyecto) plano.plantilla = proyecto.plantilla;
    const zonas = Array.isArray(h.zonas) ? h.zonas : [];
    if (Array.isArray(proyecto.dxf)) {
      plano.dxf = proyecto.dxf.map((d) => {
        const e = clonar(d);
        if (!esObjeto(e)) return e;
        delete e.zonas;
        const propias = zonas.filter((z) => esObjeto(z) && z.dxf === e.id).map((z) => {
          const sin = clonar(z);
          delete sin.dxf;
          return sin;
        });
        if (propias.length) e.zonas = propias;
        return e;
      });
    }
    if (proyecto.ortofoto !== undefined) plano.ortofoto = clonar(proyecto.ortofoto);
    plano.detalles = clonar(Array.isArray(h.detalles) ? h.detalles : []);
    for (const clave of ["rosa_vientos", "rotulo", "copiado_de"]) if (h[clave] !== undefined) plano[clave] = clonar(h[clave]);
    return plano;
  }

  /**
   * Lee un plano.json para el editor: {version, hojas: [{nombre, resultado}], errores}. Un proyecto
   * versión 8 da una hoja por entrada de "hojas"; un plano de las versiones 1 a 7, una sola hoja
   * («Hoja 1»). `resultado` es lo de EditorLogica.leerPlano. Con errores no se abre nada.
   */
  function leerProyecto(texto, datos) {
    let proyecto;
    try {
      proyecto = JSON.parse(texto);
    } catch (e) {
      return { version: null, hojas: [], errores: ["El archivo no es un JSON válido: " + e.message] };
    }
    if (!esObjeto(proyecto) || proyecto.version !== VERSION) {
      const r = L.leerPlano(texto, datos);
      return { version: esObjeto(proyecto) ? proyecto.version : null, hojas: r.errores.length ? []
        : [{ nombre: "Hoja 1", resultado: r }], errores: r.errores };
    }
    const errores = [];
    const validas = ["version", "formato", "plantilla", "dxf", "ortofoto", "hojas"];
    for (const clave of Object.keys(proyecto)) {
      if (!validas.includes(clave)) errores.push(clave + ": campo no reconocido en un proyecto (lo de cada hoja va en «hojas»).");
    }
    if (!Array.isArray(proyecto.hojas) || !proyecto.hojas.length) {
      errores.push("hojas: se esperaba la lista de hojas del proyecto (al menos una).");
      return { version: VERSION, hojas: [], errores };
    }
    const nombres = new Set();
    const zonas = new Map();
    const hojas = [];
    proyecto.hojas.forEach((h, i) => {
      const nombre = esObjeto(h) && typeof h.nombre === "string" ? h.nombre.trim() : "";
      const donde = "Hoja " + (i + 1) + (nombre ? " («" + nombre + "»)" : "");
      if (!nombre) return errores.push(donde + ": falta su «nombre».");
      if (nombres.has(nombre.toLowerCase())) return errores.push(donde + ": el nombre está repetido.");
      nombres.add(nombre.toLowerCase());
      for (const z of Array.isArray(h.zonas) ? h.zonas : []) {
        if (!esObjeto(z) || typeof z.nombre !== "string") continue;
        if (zonas.has(z.nombre)) errores.push(donde + ": la zona «" + z.nombre + "» ya es de la hoja " + zonas.get(z.nombre) + " (cada zona da un paquete).");
        else zonas.set(z.nombre, i + 1);
      }
      const r = L.leerPlano(JSON.stringify(planoDeHoja(proyecto, h)), datos);
      for (const e of r.errores) errores.push(donde + ": " + e);
      hojas.push({ nombre, resultado: r });
    });
    return { version: VERSION, hojas: errores.length ? [] : hojas, errores };
  }

  /**
   * El objeto plano.json versión 8 del proyecto. `hojas`: [{nombre, colocaciones, extra}] con el
   * `extra` de EditorLogica.objetoPlano de cada hoja (rosa, rotulo, original, copiado); `comun`:
   * {ortofoto}. Los DXF reciben el mismo id en todas las hojas (mismo sha256 = mismo DXF).
   */
  function objetoProyecto(hojas, datos, comun) {
    comun = comun || {};
    const dxfs = [];
    for (const h of hojas) {
      for (const c of h.colocaciones) {
        if (c.bloque && c.bloque.dxf) dxfs.push(c.bloque.dxf);
        else if (c.zona && c.zona.dxf) dxfs.push(c.zona.dxf);
      }
    }
    B.asignarIdsDxf(dxfs);
    const salida = { version: VERSION };
    const lista = new Map();
    const hojasSalida = [];
    hojas.forEach((h, i) => {
      const o = L.objetoPlano(h.colocaciones, datos, Object.assign({}, h.extra || {}, { ortofoto: comun.ortofoto || null }));
      if (i === 0) {
        salida.formato = o.formato;
        if ("plantilla" in o) salida.plantilla = o.plantilla;
      }
      const hoja = { nombre: h.nombre, detalles: o.detalles };
      const zonas = [];
      for (const d of o.dxf || []) {
        const e = clonar(d);
        for (const z of e.zonas || []) zonas.push(Object.assign({ dxf: e.id }, z));
        delete e.zonas;
        if (!lista.has(e.id)) lista.set(e.id, e);
      }
      if (zonas.length) hoja.zonas = zonas;
      if (o.rosa_vientos !== undefined) hoja.rosa_vientos = o.rosa_vientos;
      if (o.rotulo !== undefined) hoja.rotulo = o.rotulo;
      if (o.copiado_de !== undefined) hoja.copiado_de = o.copiado_de;
      if (comun.ortofoto && o.ortofoto && salida.ortofoto === undefined) salida.ortofoto = o.ortofoto;
      hojasSalida.push(hoja);
    });
    if (lista.size) salida.dxf = [...lista.values()];
    salida.hojas = hojasSalida;
    return salida;
  }

  function serializarProyecto(hojas, datos, comun) {
    return JSON.stringify(objetoProyecto(hojas, datos, comun), null, 2).replace(/\r\n/g, "\n") + "\n";
  }

  /** «Hoja N» con el primer N (desde 2) que no está en `usados` (sin mayúsculas). */
  function nombreHojaNueva(usados) {
    const u = new Set((usados || []).map((n) => String(n).toLowerCase()));
    for (let n = 2; n < 10000; n++) if (!u.has(("Hoja " + n).toLowerCase())) return "Hoja " + n;
    return "Hoja";
  }

  /** El número con su último grupo de cifras sumado en 1 (como hojas_proyecto.siguiente_numero). */
  function siguienteNumero(numero) {
    if (typeof numero !== "string") return null;
    const m = /(\d+)(?!.*\d)/.exec(numero);
    if (!m) return null;
    return numero.slice(0, m.index) + String(Number(m[1]) + 1).padStart(m[1].length, "0") + numero.slice(m.index + m[1].length);
  }

  const escrito = (v) => (typeof v === "number" ? String(v) : typeof v === "string" && v.trim() ? v.trim() : null);

  /** {campo: valor} automáticos de la hoja `posicion` (lo escrito a mano manda). `rotulos`: los de
   *  todas las hojas en orden; `campos`: {campo: "hoja_actual" | "total_hojas" | "numero_siguiente"}. */
  function automaticosDeLista(rotulos, posicion, campos) {
    const actual = rotulos[posicion] || {};
    const salida = {};
    for (const [campo, tipo] of Object.entries(campos || {})) {
      if (escrito(actual[campo]) !== null) continue;
      if (tipo === "hoja_actual") salida[campo] = String(posicion + 1);
      else if (tipo === "total_hojas") salida[campo] = String(rotulos.length);
      else if (tipo === "numero_siguiente") {
        for (let i = posicion - 1, pasos = 1; i >= 0; i--, pasos++) {
          let n = escrito((rotulos[i] || {})[campo]);
          if (n === null) continue;
          for (let k = 0; k < pasos && n !== null; k++) n = siguienteNumero(n);
          if (n !== null) salida[campo] = n;
          break;
        }
      }
    }
    return salida;
  }

  /** Nombre sugerido al guardar: el del proyecto abierto; un plano viejo o un índice, otro
   *  nombre que no pisa el original («<nombre>_proyecto.json»). */
  function nombreParaGuardar(archivo, viejo) {
    if (!archivo) return "proyecto.json";
    const base = String(archivo).replace(/\.hojas\.json$/i, "").replace(/\.json$/i, "");
    return viejo ? base + "_proyecto.json" : base + ".json";
  }

  /** Al duplicar una hoja: los nombres de sus zonas (borradores y exportadas) cambian para no
   *  repetirse en el proyecto. `usados`: los nombres de zona de todas las hojas. */
  function nombreZonaLibre(nombre, usados) {
    return L.idUnico(nombre, usados);
  }

  return { VERSION, planoDeHoja, leerProyecto, objetoProyecto, serializarProyecto, nombreHojaNueva,
    siguienteNumero, automaticosDeLista, nombreParaGuardar, nombreZonaLibre };
});
