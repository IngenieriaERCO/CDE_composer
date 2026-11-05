/*
 * Editor de planos — lógica pura (sin pantalla).
 *
 * Funciones que no tocan el DOM: conversión de coordenadas, límite al área de dibujo,
 * centrado, traslapes y su clasificación, y lectura/escritura de plano.json. Funcionan
 * igual en el navegador (window.EditorLogica) y en Node (module.exports), para probarlas
 * desde pytest.
 *
 * Coordenadas del PAPEL: mm, origen en la esquina inferior izquierda de la hoja, Y hacia
 * arriba (como el Layout de AutoCAD y como plano.json). Las de la PANTALLA (imagen/SVG):
 * píxeles, origen arriba a la izquierda, Y hacia abajo. La inversión de Y está SOLO en
 * papelAPantalla / pantallaAPapel.
 *
 * Las reglas son las mismas que en Python (componer.py, colocar.py), pero el editor NO es
 * la fuente de la verdad: `componer` revalida todo.
 */
(function (raiz, fabrica) {
  "use strict";
  const api = fabrica();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    raiz.EditorLogica = api;
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const EPS_MM = 1e-6; // igual que formato.EPS_MM: solo ruido numérico
  const ZONA_EDITABLE = "area_dibujo";

  // ---------------------------------------------------------------------------------------
  // Coordenadas: papel (mm, Y arriba) <-> pantalla (px de la imagen de la hoja, Y abajo).
  // ---------------------------------------------------------------------------------------

  /**
   * Escala de una imagen de la hoja: píxeles por mm en X y en Y POR SEPARADO (los píxeles
   * se redondean al generar la imagen, así que las dos escalas difieren un poco).
   */
  function escalaDeImagen(hoja, imagen) {
    return {
      pxPorMmX: imagen.ancho_px / hoja.ancho_mm,
      pxPorMmY: imagen.alto_px / hoja.alto_mm,
      altoMm: hoja.alto_mm,
    };
  }

  /**
   * ÚNICA conversión papel -> pantalla. Un punto (x, y) en mm de papel (Y hacia arriba) pasa
   * a píxeles de la imagen (Y hacia abajo): la Y se mide desde el borde superior de la hoja.
   */
  function papelAPantalla(x, y, escala) {
    return { x: x * escala.pxPorMmX, y: (escala.altoMm - y) * escala.pxPorMmY };
  }

  /** Inversa de papelAPantalla (misma fórmula despejada; no es otra convención). */
  function pantallaAPapel(px, py, escala) {
    return { x: px / escala.pxPorMmX, y: escala.altoMm - py / escala.pxPorMmY };
  }

  /** Rectángulo de papel [x0, y0, x1, y1] -> {x, y, ancho, alto} en píxeles (para SVG). */
  function rectPapelAPantalla(rect, escala) {
    const arribaIzq = papelAPantalla(rect[0], rect[3], escala);
    const abajoDer = papelAPantalla(rect[2], rect[1], escala);
    return {
      x: arribaIzq.x,
      y: arribaIzq.y,
      ancho: abajoDer.x - arribaIzq.x,
      alto: abajoDer.y - arribaIzq.y,
    };
  }

  // ---------------------------------------------------------------------------------------
  // Geometría de un detalle en la hoja.
  // ---------------------------------------------------------------------------------------

  /** Página del detalle en papel con su esquina inferior izquierda en pos = [x, y]. */
  function paginaEnPapel(detalle, pos) {
    const [ancho, alto] = detalle.tamano_pagina_mm;
    return [pos[0], pos[1], pos[0] + ancho, pos[1] + alto];
  }

  /** Dibujo real (limites_dibujo_mm, relativo a la página) en papel. */
  function dibujoEnPapel(detalle, pos) {
    const l = detalle.limites_dibujo_mm;
    return [pos[0] + l[0], pos[1] + l[1], pos[0] + l[2], pos[1] + l[3]];
  }

  /** Igual que colocar.posicion_centrada (mismas operaciones, mismo resultado). */
  function posicionCentrada(tamano, zona) {
    const [ancho, alto] = tamano;
    return [(zona[0] + zona[2]) / 2 - ancho / 2, (zona[1] + zona[3]) / 2 - alto / 2];
  }

  /**
   * Limita la posición para que la PÁGINA completa quede dentro de la zona (la regla
   * estricta de componer). Si la página no cabe por tamaño, devuelve null.
   */
  function clampAZona(pos, tamano, zona) {
    const [ancho, alto] = tamano;
    if (ancho > zona[2] - zona[0] + EPS_MM || alto > zona[3] - zona[1] + EPS_MM) {
      return null;
    }
    const x = Math.min(Math.max(pos[0], zona[0]), zona[2] - ancho);
    const y = Math.min(Math.max(pos[1], zona[1]), zona[3] - alto);
    return [x, y];
  }

  /** Lleva un valor al múltiplo más cercano del paso (mm). */
  function ajustarAPaso(valor, paso) {
    return Math.round(valor / paso) * paso;
  }

  /**
   * Redondea a 0,01 mm para guardar, pero SIEMPRE hacia dentro de la zona: si el detalle
   * está pegado a un borde, redondear al más cercano podría sacarlo unas milésimas y
   * componer lo rechazaría.
   */
  function redondearDentro(pos, tamano, zona) {
    const [ancho, alto] = tamano;
    const r = (v) => Math.round(v * 100) / 100;
    const ajustar = (v, minimo, maximo) => {
      let resultado = r(v);
      if (resultado < minimo - EPS_MM) resultado = Math.ceil(minimo * 100 - 1e-6) / 100;
      if (resultado > maximo + EPS_MM) resultado = Math.floor(maximo * 100 + 1e-6) / 100;
      return resultado;
    };
    return [
      ajustar(pos[0], zona[0], zona[2] - ancho),
      ajustar(pos[1], zona[1], zona[3] - alto),
    ];
  }

  /** Igual que colocar.motivo_fuera_de_zona en lo esencial: ¿la página queda dentro? */
  function dentroDeZona(rect, zona) {
    return (
      zona[0] - rect[0] <= EPS_MM &&
      zona[1] - rect[1] <= EPS_MM &&
      rect[2] - zona[2] <= EPS_MM &&
      rect[3] - zona[3] <= EPS_MM
    );
  }

  /** [ancho, alto] del traslape, o null si solo se tocan o no se cruzan (como componer). */
  function interseccion(a, b) {
    const ancho = Math.min(a[2], b[2]) - Math.max(a[0], b[0]);
    const alto = Math.min(a[3], b[3]) - Math.max(a[1], b[1]);
    return ancho > EPS_MM && alto > EPS_MM ? [ancho, alto] : null;
  }

  // ---------------------------------------------------------------------------------------
  // Advertencias: mismos criterios, orden y textos que componer.py (las plantillas de texto
  // vienen de advertencias.py, incrustadas en los datos).
  // ---------------------------------------------------------------------------------------

  /** Rellena una plantilla de advertencias.py ({a}, {b}, {elemento}, {ancho}, {alto}). */
  function textoAdvertencia(plantillas, clave, medidas, nombres) {
    const valores = Object.assign(
      { ancho: medidas[0].toFixed(1), alto: medidas[1].toFixed(1) },
      nombres
    );
    return plantillas[clave].texto.replace(/\{(\w+)\}/g, (_, nombre) => valores[nombre]);
  }

  /**
   * Qué advertencia corresponde a dos detalles (null: ninguna). Lo que tapa es solo el de
   * ENCIMA: si no tiene fondo, un traslape solo de páginas no avisa. Igual que
   * advertencias.clave_traslape_detalles en Python.
   */
  function claveTraslapeDetalles(dibujos, paginas, encimaTieneFondo) {
    if (dibujos) return encimaTieneFondo ? "dibujos" : "dibujos_sin_fondo";
    if (paginas && encimaTieneFondo) return "paginas";
    return null;
  }

  /** Igual que advertencias.clave_sobre_elemento en Python. */
  function claveSobreElemento(dibujo, pagina, tieneFondo) {
    if (dibujo) return tieneFondo ? "dibujo_sobre_elemento" : "dibujo_sobre_elemento_sin_fondo";
    if (pagina && tieneFondo) return "pagina_sobre_elemento";
    return null;
  }

  /** Si el dato falta (datos de antes de la 3.4), se supone que tiene fondo. */
  const conFondo = (c) => c.tiene_fondo !== false;

  /**
   * colocados: [{id, pagina: [x0,y0,x1,y1], dibujo: [...], tiene_fondo}] en orden de
   * apilado. Devuelve [{clave, nivel, texto, ids, elemento}] en el mismo orden que componer:
   * primero los pares de detalles, luego cada detalle contra cada elemento fijo.
   */
  function advertencias(colocados, elementos, plantillas) {
    const lista = [];
    const agregar = (clave, medidas, nombres, ids, elemento) =>
      lista.push({
        clave: clave,
        nivel: plantillas[clave].nivel,
        texto: textoAdvertencia(plantillas, clave, medidas, nombres),
        ids: ids,
        elemento: elemento || null,
      });
    for (let i = 0; i < colocados.length; i++) {
      for (let j = i + 1; j < colocados.length; j++) {
        const a = colocados[i];
        const b = colocados[j];
        const dibujos = interseccion(a.dibujo, b.dibujo);
        const paginas = interseccion(a.pagina, b.pagina);
        const clave = claveTraslapeDetalles(!!dibujos, !!paginas, conFondo(b));
        if (clave) agregar(clave, dibujos || paginas, { a: a.id, b: b.id }, [a.id, b.id]);
      }
    }
    for (const c of colocados) {
      for (const el of elementos) {
        const dibujo = interseccion(c.dibujo, el.rect_mm);
        const pagina = interseccion(c.pagina, el.rect_mm);
        const clave = claveSobreElemento(!!dibujo, !!pagina, conFondo(c));
        if (clave) agregar(clave, dibujo || pagina, { a: c.id, elemento: el.nombre }, [c.id], el.nombre);
      }
    }
    return lista;
  }

  // ---------------------------------------------------------------------------------------
  // plano.json (versión 1, docs/formato_plano.md).
  // ---------------------------------------------------------------------------------------

  /** id, id_2, id_3… el primero que no esté en `usados`. */
  function idUnico(base, usados) {
    if (!usados.has(base)) return base;
    let n = 2;
    while (usados.has(base + "_" + n)) n++;
    return base + "_" + n;
  }

  function zonaEditable(datos) {
    const zona = datos.zonas.find((z) => z.nombre === ZONA_EDITABLE);
    return zona ? zona.rect_mm : null;
  }

  /**
   * Texto de plano.json (saltos de línea LF) para las colocaciones en orden de apilado:
   * [{id, detalle (entrada del catálogo), pos: [x, y]}]. Siempre posicion_mm, redondeada a
   * 0,01 mm hacia dentro del área de dibujo.
   */
  function serializarPlano(colocaciones, datos) {
    const zona = zonaEditable(datos);
    const plano = {
      version: 1,
      formato: datos.formato,
      plantilla: null,
      detalles: colocaciones.map((c) => ({
        id: c.id,
        manifiesto: c.detalle.manifiesto,
        posicion_mm: redondearDentro(c.pos, c.detalle.tamano_pagina_mm, zona),
      })),
    };
    return JSON.stringify(plano, null, 2).replace(/\r\n/g, "\n") + "\n";
  }

  function normalizarRuta(ruta) {
    return String(ruta).replace(/\\/g, "/").replace(/^(\.\/)+/, "");
  }

  /**
   * Lee un plano.json contra el catálogo del editor. Devuelve
   * {colocaciones, errores, avisos}: con errores no se carga nada; los avisos (p. ej. un
   * detalle fuera del área que se ajustó) se cargan igual.
   */
  function leerPlano(texto, datos) {
    const errores = [];
    const avisos = [];
    let plano;
    try {
      plano = JSON.parse(texto);
    } catch (e) {
      return { colocaciones: [], errores: ["El archivo no es un JSON válido: " + e.message], avisos };
    }
    if (plano === null || typeof plano !== "object" || Array.isArray(plano)) {
      return { colocaciones: [], errores: ["El plano debe ser un objeto JSON {...}."], avisos };
    }
    if (plano.version !== 1) {
      errores.push("version: versión " + JSON.stringify(plano.version) +
        " no soportada; el editor entiende la versión 1.");
    }
    if (plano.formato !== undefined && normalizarRuta(plano.formato) !== normalizarRuta(datos.formato)) {
      avisos.push("El plano usa el formato '" + plano.formato + "' y el editor '" +
        datos.formato + "': se usará el del editor.");
    }
    if (!Array.isArray(plano.detalles) || plano.detalles.length === 0) {
      errores.push("detalles: se esperaba una lista con al menos un detalle.");
      return { colocaciones: [], errores, avisos };
    }
    const catalogo = new Map(datos.detalles.map((d) => [normalizarRuta(d.manifiesto), d]));
    const rechazados = new Map(datos.rechazados.map((r) => [normalizarRuta(r.manifiesto), r]));
    const zona = zonaEditable(datos);
    const ids = new Set();
    const colocaciones = [];
    plano.detalles.forEach((item, i) => {
      const donde = "detalles[" + i + "]";
      if (item === null || typeof item !== "object") {
        errores.push(donde + ": se esperaba un objeto {...}.");
        return;
      }
      if (typeof item.id !== "string" || !item.id.trim()) {
        errores.push(donde + ".id: se esperaba un texto no vacío.");
        return;
      }
      if (ids.has(item.id)) {
        errores.push(donde + ".id: '" + item.id + "' está repetido.");
        return;
      }
      ids.add(item.id);
      const ruta = normalizarRuta(item.manifiesto || "");
      const detalle = catalogo.get(ruta);
      if (!detalle) {
        const rechazado = rechazados.get(ruta);
        errores.push(donde + " ('" + item.id + "'): " + (rechazado
          ? "el paquete '" + rechazado.prefijo + "' está rechazado y no se puede colocar."
          : "el manifiesto '" + item.manifiesto + "' no está en el catálogo del editor."));
        return;
      }
      if (!detalle.cabe) {
        errores.push(donde + " ('" + item.id + "'): el detalle '" + detalle.id +
          "' no cabe en el área de dibujo.");
        return;
      }
      let pos;
      const tienePos = Array.isArray(item.posicion_mm) && item.posicion_mm.length === 2 &&
        item.posicion_mm.every((v) => typeof v === "number" && isFinite(v));
      if (item.centrar === true && item.posicion_mm === undefined) {
        pos = posicionCentrada(detalle.tamano_pagina_mm, zona);
      } else if (tienePos && item.centrar !== true) {
        pos = item.posicion_mm.slice();
      } else {
        errores.push(donde + " ('" + item.id + "'): lleva posicion_mm [x, y] o centrar: true (uno de los dos).");
        return;
      }
      const ajustada = clampAZona(pos, detalle.tamano_pagina_mm, zona);
      if (ajustada[0] !== pos[0] || ajustada[1] !== pos[1]) {
        avisos.push("'" + item.id + "' se salía del área de dibujo: se movió a (" +
          ajustada[0].toFixed(2) + ", " + ajustada[1].toFixed(2) + ") mm.");
      }
      colocaciones.push({ id: item.id, detalle: detalle, pos: ajustada });
    });
    return { colocaciones: errores.length ? [] : colocaciones, errores, avisos };
  }

  return {
    EPS_MM,
    ZONA_EDITABLE,
    escalaDeImagen,
    papelAPantalla,
    pantallaAPapel,
    rectPapelAPantalla,
    paginaEnPapel,
    dibujoEnPapel,
    posicionCentrada,
    clampAZona,
    ajustarAPaso,
    redondearDentro,
    dentroDeZona,
    interseccion,
    textoAdvertencia,
    claveTraslapeDetalles,
    claveSobreElemento,
    advertencias,
    idUnico,
    zonaEditable,
    serializarPlano,
    leerPlano,
  };
});
