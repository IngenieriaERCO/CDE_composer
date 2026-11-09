/*
 * Editor de planos — modelo del RÓTULO (subfase 4.3a; prellenado, 4.3b). Lógica pura, sin pantalla: funciona en
 * el navegador (window.EditorRotulo) y en Node (module.exports), para probarla desde pytest.
 *
 * Regla de oro: abrir un plano.json y guardarlo SIN tocar nada debe dejar el JSON idéntico.
 * Por eso el modelo guarda el objeto "rotulo" tal como vino y solo reemplaza los campos que el
 * usuario cambia (`cambiar`). Lo que los formularios no sepan representar (p. ej. notas desde
 * archivos .txt, un título dado como lista de líneas) se conserva intacto.
 *
 * Notas: el editor guarda las notas elegidas COPIADAS en "adicionales" (texto, o
 * {"texto", "vinetas"} si tiene viñetas). Las firmas en imagen nunca están en el editor: solo
 * el nombre de la persona ({"imagen": "<persona>"}).
 */
(function (raiz, fabrica) {
  "use strict";
  const api = fabrica();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    raiz.EditorRotulo = api;
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const clonar = (v) => (v === undefined ? undefined : JSON.parse(JSON.stringify(v)));
  const esObjeto = (v) => v !== null && typeof v === "object" && !Array.isArray(v);

  /** Igualdad profunda de valores JSON (el orden de las claves no importa). */
  function igualProfundo(a, b) {
    if (a === b) return true;
    if (Array.isArray(a)) {
      return Array.isArray(b) && a.length === b.length && a.every((x, i) => igualProfundo(x, b[i]));
    }
    if (esObjeto(a) && esObjeto(b)) {
      const ka = Object.keys(a);
      const kb = Object.keys(b);
      return ka.length === kb.length && ka.every((k) => Object.prototype.hasOwnProperty.call(b, k) &&
        igualProfundo(a[k], b[k]));
    }
    return false;
  }

  /**
   * Modelo a partir del "rotulo" de un plano (o null/undefined si no tenía) y la definición
   * del formato (datos del editor). `cambios` guarda solo lo que el usuario tocó: campo ->
   * valor JSON nuevo (undefined = quitar el campo).
   */
  function crearModelo(rotulo, definicion) {
    return {
      original: esObjeto(rotulo) ? clonar(rotulo) : null,
      cambios: {},
      definicion: definicion || null,
    };
  }

  /** Valor actual (JSON) de un campo del rótulo. */
  function valor(modelo, campo) {
    if (Object.prototype.hasOwnProperty.call(modelo.cambios, campo)) return clonar(modelo.cambios[campo]);
    return modelo.original ? clonar(modelo.original[campo]) : undefined;
  }

  /** Cambia un campo completo (undefined lo quita). Si queda igual al original, deja de ser un cambio. */
  function cambiar(modelo, campo, nuevo) {
    const original = modelo.original ? modelo.original[campo] : undefined;
    if (igualProfundo(nuevo, original)) delete modelo.cambios[campo];
    else modelo.cambios[campo] = clonar(nuevo);
  }

  function hayCambios(modelo) {
    return Object.keys(modelo.cambios).length > 0;
  }

  /**
   * El "rotulo" para guardar: el original con los campos cambiados reemplazados (mismo orden
   * de claves; los nuevos al final). Sin cambios, el original tal cual. undefined si no hay
   * rótulo.
   */
  function serializar(modelo) {
    if (!hayCambios(modelo)) return modelo.original ? clonar(modelo.original) : undefined;
    const salida = {};
    const base = modelo.original || {};
    for (const clave of Object.keys(base)) {
      if (Object.prototype.hasOwnProperty.call(modelo.cambios, clave)) {
        if (modelo.cambios[clave] !== undefined) salida[clave] = clonar(modelo.cambios[clave]);
      } else {
        salida[clave] = clonar(base[clave]);
      }
    }
    for (const [clave, v] of Object.entries(modelo.cambios)) {
      if (!(clave in base) && v !== undefined) salida[clave] = clonar(v);
    }
    return Object.keys(salida).length ? salida : undefined;
  }

  // ---------------------------------------------------------------------------------------
  // Notas: vista normalizada y escritura en "adicionales".
  // ---------------------------------------------------------------------------------------

  /** Una nota adicional del plano -> {texto, vinetas}. */
  function normalizarNota(item) {
    if (typeof item === "string") return { texto: item, vinetas: [] };
    if (esObjeto(item)) return { texto: String(item.texto || ""), vinetas: (item.vinetas || []).slice() };
    return { texto: String(item), vinetas: [] };
  }

  /** {texto, vinetas} -> como se guarda: texto solo, o objeto si tiene viñetas. */
  function notaParaGuardar(nota) {
    const vinetas = (nota.vinetas || []).filter((v) => String(v).trim());
    return vinetas.length ? { texto: nota.texto, vinetas: vinetas } : nota.texto;
  }

  /** {archivos, adicionales: [{texto, vinetas}]} de lo que tiene el plano. */
  function notas(modelo) {
    const v = valor(modelo, "notas") || {};
    return {
      archivos: Array.isArray(v.archivos) ? v.archivos.slice() : [],
      adicionales: Array.isArray(v.adicionales) ? v.adicionales.map(normalizarNota) : [],
    };
  }

  /**
   * Reemplaza las notas adicionales (en el orden dado), conservando "archivos" y cualquier
   * otra clave que traiga "notas". Lista vacía y nada más: quita "notas".
   */
  function cambiarNotasAdicionales(modelo, lista) {
    const actual = esObjeto(valor(modelo, "notas")) ? valor(modelo, "notas") : {};
    const nuevo = Object.assign({}, actual);
    if (lista.length) nuevo.adicionales = lista.map(notaParaGuardar);
    else delete nuevo.adicionales;
    cambiar(modelo, "notas", Object.keys(nuevo).length ? nuevo : undefined);
  }

  /**
   * Plano NUEVO (sin rótulo de origen): pone `valores` (campo -> valor, p. ej. los de
   * proyecto.json) como cambios, así quedan COPIADOS en el plano al guardar. En un plano
   * abierto no hace nada: lo que trae el plano manda. Devuelve los campos que puso.
   */
  function prellenar(modelo, valores) {
    if (modelo.original !== null || !esObjeto(valores)) return [];
    const puestos = [];
    for (const [campo, v] of Object.entries(valores)) {
      if (v === undefined) continue;
      cambiar(modelo, campo, v);
      puestos.push(campo);
    }
    return puestos;
  }

  // ---------------------------------------------------------------------------------------
  // Lo que los formularios no saben representar: se conserva y se avisa. Desde la 4.3b las
  // listas de líneas sí se editan (una línea por renglón); lo que sigue aquí no.
  // ---------------------------------------------------------------------------------------

  const textoRepresentable = (v) => v === null || typeof v === "string" ||
    (typeof v === "number" && Number.isInteger(v)) ||
    (Array.isArray(v) && v.every((x) => typeof x === "string" && !x.includes("\n")));

  /** Lista de textos con lo que el editor conserva sin poder editarlo. */
  function noRepresentable(modelo) {
    const r = serializar(modelo);
    if (!r) return [];
    const lista = [];
    const campos = (modelo.definicion && modelo.definicion.campos) || null;
    for (const [clave, v] of Object.entries(r)) {
      if (campos && !campos[clave]) lista.push("rotulo." + clave + " (el formato no tiene ese campo)");
      else if (clave === "notas" && esObjeto(v) && Array.isArray(v.archivos) && v.archivos.length) {
        lista.push("notas.archivos (" + v.archivos.length + " archivo(s) .txt referidos)");
      } else if (campos && campos[clave] && campos[clave].tipo === "texto" && !campos[clave].calculado &&
                 !textoRepresentable(v)) {
        lista.push("rotulo." + clave + " (valor que el formulario no sabe mostrar)");
      }
    }
    return lista;
  }

  /** Resumen del catálogo de notas incrustado: grupos, archivos y notas. */
  function resumenCatalogo(catalogo) {
    if (!catalogo) return { grupos: 0, archivos: 0, notas: 0, vinetas: 0, problemas: 0 };
    let archivos = 0;
    let total = 0;
    let vinetas = 0;
    let problemas = 0;
    for (const g of catalogo.grupos) {
      for (const a of g.archivos) {
        archivos++;
        total += a.notas.length;
        vinetas += a.notas.reduce((s, n) => s + n.vinetas.length, 0);
        problemas += a.problemas.length;
      }
    }
    return { grupos: catalogo.grupos.length, archivos, notas: total, vinetas, problemas };
  }

  return {
    igualProfundo,
    crearModelo,
    valor,
    cambiar,
    hayCambios,
    serializar,
    normalizarNota,
    notaParaGuardar,
    notas,
    cambiarNotasAdicionales,
    prellenar,
    noRepresentable,
    resumenCatalogo,
  };
});
