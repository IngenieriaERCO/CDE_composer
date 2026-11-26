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
 *
 * Etapa 2 (bloques de un DXF sin exportar, plano versión 3): la geometría de esos bloques está
 * en editor_bloques.js (EditorBloques); aquí solo se leen y escriben en plano.json.
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

  // editor_bloques.js: en el navegador ya está cargado (va antes en editor.html).
  const B = typeof module === "object" && module.exports
    ? require("./editor_bloques.js") : self.EditorBloques;
  // editor_ortofoto.js (plano versión 4), igual.
  const O = typeof module === "object" && module.exports
    ? require("./editor_ortofoto.js") : self.EditorOrtofoto;

  const EPS_MM = 1e-6; // igual que formato.EPS_MM: solo ruido numérico
  const ZONA_EDITABLE = "area_dibujo";
  const ROSA = "rosa_vientos"; // igual que rosa.NOMBRE

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

  // ---------------------------------------------------------------------------------------
  // Recorte (Fase 11, igual que recorte_detalle.py): en la hoja se ve el dibujo más un margen,
  // no la página entera del paquete. c.pos sigue siendo la esquina de la PÁGINA (posicion_mm):
  // el dibujo no se mueve al cambiar el margen. Lo visible es lo que debe caber en el área.
  // ---------------------------------------------------------------------------------------

  const MARGEN_POR_DEFECTO_MM = 1;
  const MARGEN_MAXIMO_MM = 50;

  /** El margen de una colocación: el suyo (c.margen) o el de componedor.json (datos). */
  function margenDe(c, datos) {
    if (c && typeof c.margen === "number") return c.margen;
    return datos && typeof datos.margen_detalle_mm === "number" ? datos.margen_detalle_mm : MARGEN_POR_DEFECTO_MM;
  }

  /** Lo visible relativo a la esquina de la página (papel, Y arriba): el dibujo agrandado
   *  `margen` por lado, sin salirse de la página. margen null: la página entera. */
  function recorteDetalle(detalle, margen) {
    const [ancho, alto] = detalle.tamano_pagina_mm;
    if (margen === null || margen === undefined || !detalle.limites_dibujo_mm) return [0, 0, ancho, alto];
    const l = detalle.limites_dibujo_mm;
    return [Math.max(0, l[0] - margen), Math.max(0, l[1] - margen),
      Math.min(ancho, l[2] + margen), Math.min(alto, l[3] + margen)];
  }

  /** Lo que se ve del detalle en papel con la página en pos. */
  function visibleEnPapel(detalle, pos, margen) {
    const r = recorteDetalle(detalle, margen);
    return [pos[0] + r[0], pos[1] + r[1], pos[0] + r[2], pos[1] + r[3]];
  }

  /** [tamaño visible, zona corrida]: con ellos clampAZona, posicionCentrada y redondearDentro
   *  dan la esquina de la PÁGINA que deja lo visible dentro (o centrado) de la zona. */
  function geometriaVisible(detalle, margen, zona) {
    const r = recorteDetalle(detalle, margen);
    return [[r[2] - r[0], r[3] - r[1]], [zona[0] - r[0], zona[1] - r[1], zona[2] - r[0], zona[3] - r[1]]];
  }
  const clampDetalle = (pos, detalle, margen, zona) => clampAZona(pos, ...geometriaVisible(detalle, margen, zona));
  const centrarDetalle = (detalle, margen, zona) => posicionCentrada(...geometriaVisible(detalle, margen, zona));
  const redondearDetalle = (pos, detalle, margen, zona) => redondearDentro(pos, ...geometriaVisible(detalle, margen, zona));
  /** ¿Cabe lo que se ve (dibujo + margen) en la zona? */
  function cabeDetalle(detalle, margen, zona) {
    const [t] = geometriaVisible(detalle, margen, zona);
    return t[0] <= zona[2] - zona[0] + EPS_MM && t[1] <= zona[3] - zona[1] + EPS_MM;
  }
  const margenValido = (v) => typeof v === "number" && isFinite(v) && v >= 0 && v <= MARGEN_MAXIMO_MM;

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

  // ---------------------------------------------------------------------------------------
  // Rosa de los vientos (subfase 4.1): se puede mover u ocultar. Mismas reglas que rosa.py.
  // ---------------------------------------------------------------------------------------

  /** [ancho, alto] de la rosa (su rectángulo original en la plantilla). */
  function tamanoRosa(original) {
    return [original[2] - original[0], original[3] - original[1]];
  }

  /** Rectángulo de la rosa con su esquina inferior izquierda en pos. Igual que rosa.rect_destino. */
  function rectRosa(original, pos) {
    const [ancho, alto] = tamanoRosa(original);
    return [pos[0], pos[1], pos[0] + ancho, pos[1] + alto];
  }

  /**
   * Los elementos fijos tal como quedan en la hoja (igual que rosa.elementos_visibles): la
   * rosa en su rectángulo actual, o fuera de la lista si está oculta; los demás sin cambios y
   * en el mismo orden. rosa: {visible, rect} o null (el formato no tiene rosa).
   */
  function elementosVisibles(elementos, rosa) {
    if (!rosa) return elementos.slice();
    const lista = [];
    for (const el of elementos) {
      if (el.nombre !== ROSA) lista.push(el);
      else if (rosa.visible) lista.push({ nombre: ROSA, rect_mm: rosa.rect });
    }
    return lista;
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
  // plano.json (versiones 1 a 5, docs/formato_plano.md).
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
   * [{id, detalle (entrada del catálogo), pos: [x, y], etiqueta_escala}]. Siempre
   * posicion_mm, redondeada a 0,01 mm hacia dentro del área de dibujo.
   *
   * extra (opcional): {rosa: {visible, pos}, rotulo: {...}}. Si el formato tiene rosa, se
   * guarda siempre su estado ("rosa_vientos"); el rótulo de un plano abierto se conserva tal
   * cual (el editor no lo edita). Con alguna de esas claves, o con "etiqueta_escala": false
   * en un detalle, el plano es versión 2; si no, versión 1. Con bloques de un DXF sin
   * exportar ({id, bloque, escala, centro}), versión 3: la lista "dxf" y cada bloque con
   * "origen" y "centro_mm" (sin manifiesto). Con extra.ortofoto ({archivo, bytes, crs,
   * crs_dibujo, opacidad}), versión 5: la sección "ortofoto" y, en cada detalle que la usa
   * (c.ortofoto === true), "ortofoto": true.
   */
  function serializarPlano(colocaciones, datos, extra) {
    return JSON.stringify(objetoPlano(colocaciones, datos, extra), null, 2)
      .replace(/\r\n/g, "\n") + "\n";
  }

  const mismaPos = (a, b) => !!a && !!b && a[0] === b[0] && a[1] === b[1];

  /**
   * El objeto plano.json. Con extra.original (el plano que se abrió, subfase 4.3a) se conserva
   * TODO lo que el usuario no tocó: cada detalle que no se movió sale tal como vino (incluso
   * con "centrar"), el formato y la plantilla originales, la rosa si su estado no cambió, y el
   * rótulo tal cual (o el que devuelve el modelo del rótulo). Abrir y guardar sin tocar nada
   * da un JSON idéntico. La rosa solo se escribe si el plano ya la traía o si dejó de estar
   * visible y en su lugar.
   */
  function objetoPlano(colocaciones, datos, extra) {
    extra = extra || {};
    const original = esObjeto(extra.original) ? extra.original : null;
    const zona = zonaEditable(datos);
    let v2 = false;
    // Versión 6: las zonas (borradores y exportadas) van en la lista "dxf"; los borradores no
    // son detalles todavía.
    const conZona = colocaciones.filter((c) => (c.bloque && c.bloque.zona) || (c.zona && c.detalle));
    const pendientes = colocaciones.filter((c) => c.bloque && !c.bloque.zona);
    const dxfsZonas = conZona.map((c) => (c.bloque ? c.bloque.dxf : c.zona.dxf));
    B.asignarIdsDxf(pendientes.map((c) => c.bloque.dxf).concat(dxfsZonas));
    colocaciones = colocaciones.filter((c) => !(c.bloque && c.bloque.zona));
    const conOrtofoto = !!extra.ortofoto;
    // "ortofoto" del detalle tal como se escribirá (solo con la sección "ortofoto").
    const usaOrtofoto = (c) => conOrtofoto && c.ortofoto === true;
    const igualOrtofoto = (c) => usaOrtofoto(c) === (c.original.ortofoto === true);
    const detalles = colocaciones.map((c) => {
      const etiqueta = c.etiqueta_escala === false ? false : undefined;
      const etiquetaOriginal = c.original && c.original.etiqueta_escala === false ? false : undefined;
      if (c.bloque) { // sin exportar: centro y escala (no se movió ni cambió: tal como vino)
        if (c.original && mismaPos(c.centro, c.centroOriginal) && c.escala === c.escalaOriginal &&
            etiqueta === etiquetaOriginal && igualOrtofoto(c)) {
          return JSON.parse(JSON.stringify(c.original));
        }
        return B.pendienteParaGuardar(c, conOrtofoto);
      }
      const margen = typeof c.margen === "number" ? c.margen : undefined;
      if (c.original && mismaPos(c.pos, c.posOriginal) && etiqueta === etiquetaOriginal &&
          igualOrtofoto(c) && margen === c.original.margen_mm) {
        if (etiqueta === false || margen !== undefined) v2 = true;
        return JSON.parse(JSON.stringify(c.original));
      }
      const d = {
        id: c.id,
        manifiesto: c.detalle.manifiesto,
        posicion_mm: redondearDetalle(c.pos, c.detalle, margenDe(c, datos), zona),
      };
      if (etiqueta === false) {
        d.etiqueta_escala = false;
        v2 = true;
      }
      if (margen !== undefined) { // versión 2: el margen propio de este detalle (Fase 11)
        d.margen_mm = margen;
        v2 = true;
      }
      if (usaOrtofoto(c)) d.ortofoto = true;
      if (c.zona) d.origen = { zona: c.zona.nombre }; // versión 6: exportado desde esa zona
      return d;
    });
    const nuevo = {
      version: 1,
      formato: original && original.formato !== undefined &&
        normalizarRuta(original.formato) === normalizarRuta(datos.formato) ? original.formato : datos.formato,
      plantilla: original && "plantilla" in original ? original.plantilla : null,
    };
    if (pendientes.length || conZona.length) {
      nuevo.dxf = dxfParaGuardar(pendientes.map((c) => c.bloque.dxf).concat(dxfsZonas), original);
      const zonas = zonasParaGuardar(conZona);
      for (const d of nuevo.dxf) {
        if (zonas.has(d.id)) d.zonas = zonas.get(d.id);
        else delete d.zonas;
      }
    }
    nuevo.detalles = detalles;
    if (extra.ortofoto) {
      const o = O.ortofotoParaGuardar(extra.ortofoto);
      const previa = original && esObjeto(original.ortofoto) ? original.ortofoto : null;
      // Sin cambios: tal como vino (abrir y guardar da el mismo JSON).
      nuevo.ortofoto = previa && JSON.stringify(O.ortofotoParaGuardar(
        O.leerOrtofoto(previa, []) || {})) === JSON.stringify(o) ? JSON.parse(JSON.stringify(previa)) : o;
    }
    const rosa = rosaParaGuardar(extra.rosa, datos, zona, original);
    if (rosa !== undefined) {
      nuevo.rosa_vientos = rosa;
      v2 = true;
    }
    if (extra.rotulo) {
      nuevo.rotulo = extra.rotulo;
      v2 = true;
    }
    if (v2) nuevo.version = 2;
    if (pendientes.length) nuevo.version = 3;
    if (extra.ortofoto) nuevo.version = 5; // la 4 (ortofoto en todos) se migra a la 5 al guardar
    if (conZona.length) nuevo.version = 6; // zonas del Model Space
    // No se baja de versión (un plano 3 sin bloques pendientes sigue siendo válido).
    if (original && [2, 3, 4, 5, 6].includes(original.version) &&
        original.version > nuevo.version) nuevo.version = original.version;
    if (!original) return nuevo;
    // Mismo orden de claves que el original; lo que no estaba, al final.
    const salida = {};
    for (const clave of Object.keys(original)) {
      if (clave in nuevo) salida[clave] = nuevo[clave];
      else if (!["rosa_vientos", "rotulo", "dxf", "ortofoto"].includes(clave)) salida[clave] = original[clave];
    }
    for (const clave of Object.keys(nuevo)) {
      // "plantilla": null es lo mismo que no tenerla: si el original no la traía, no se agrega.
      if (!(clave in salida) && clave !== "plantilla") salida[clave] = nuevo[clave];
    }
    return salida;
  }

  /** La lista "dxf": las entradas del plano abierto que no cambiaron salen tal como vinieron. */
  function dxfParaGuardar(entradas, original) {
    const previas = original && Array.isArray(original.dxf) ? original.dxf : [];
    return B.listaDxf(entradas).map((d) => {
      const previa = previas.find((x) => esObjeto(x) && x.id === d.id && x.sha256 === d.sha256);
      return previa ? JSON.parse(JSON.stringify(previa)) : d;
    });
  }

  /** "rosa_vientos" para guardar, o undefined si no hace falta escribirla. */
  function rosaParaGuardar(estado, datos, zona, original) {
    if (!datos.rosa_vientos || !estado) return undefined;
    const r = datos.rosa_vientos.rect_mm;
    const enSuSitio = estado.visible !== false && estado.pos[0] === r[0] && estado.pos[1] === r[1];
    const previa = original && esObjeto(original.rosa_vientos) ? original.rosa_vientos : null;
    if (previa) {
      const visiblePrevia = previa.visible !== false;
      const posPrevia = Array.isArray(previa.posicion_mm) ? previa.posicion_mm : [r[0], r[1]];
      const posActual = redondearDentro(estado.pos, tamanoRosa(r), zona);
      if (visiblePrevia === (estado.visible !== false) &&
          (mismaPos(estado.pos, posPrevia) || mismaPos(posActual, posPrevia))) {
        return JSON.parse(JSON.stringify(previa)); // no cambió: tal como vino
      }
    } else if (enSuSitio) {
      return undefined; // visible y en su lugar: es lo mismo que no escribirla
    }
    return {
      visible: estado.visible !== false,
      posicion_mm: redondearDentro(estado.pos, tamanoRosa(r), zona),
    };
  }

  const esObjeto = (v) => v !== null && typeof v === "object" && !Array.isArray(v);

  /**
   * "rosa_vientos" de un plano versión 2 -> {visible, pos} (pos dentro del área de dibujo;
   * si se salía, se acomoda y se avisa). Sin la clave: null (el editor la deja en su sitio).
   */
  function leerRosa(valor, datos, errores, avisos) {
    if (valor === undefined) return null;
    if (!datos.rosa_vientos) {
      errores.push("rosa_vientos: el formato del editor no tiene rosa de los vientos.");
      return null;
    }
    if (!esObjeto(valor)) {
      errores.push("rosa_vientos: se esperaba un objeto {\"visible\": ..., \"posicion_mm\": [x, y]}.");
      return null;
    }
    const desconocidas = Object.keys(valor).filter((k) => k !== "visible" && k !== "posicion_mm");
    if (desconocidas.length) {
      errores.push("rosa_vientos." + desconocidas[0] + ": campo no reconocido (campos válidos: posicion_mm, visible).");
      return null;
    }
    if (valor.visible !== undefined && typeof valor.visible !== "boolean") {
      errores.push("rosa_vientos.visible: se esperaba true o false.");
      return null;
    }
    const original = datos.rosa_vientos.rect_mm;
    let pos = [original[0], original[1]];
    if (valor.posicion_mm !== undefined) {
      const p = valor.posicion_mm;
      if (!Array.isArray(p) || p.length !== 2 || !p.every((v) => typeof v === "number" && isFinite(v))) {
        errores.push("rosa_vientos.posicion_mm: se esperaba [x, y] con 2 números en mm.");
        return null;
      }
      pos = p.slice();
    }
    const ajustada = clampAZona(pos, tamanoRosa(original), zonaEditable(datos));
    if (ajustada[0] !== pos[0] || ajustada[1] !== pos[1]) {
      avisos.push("La rosa de los vientos se salía del área de dibujo: se movió a (" +
        ajustada[0].toFixed(2) + ", " + ajustada[1].toFixed(2) + ") mm.");
    }
    return { visible: valor.visible !== false, pos: ajustada };
  }

  function normalizarRuta(ruta) {
    return String(ruta).replace(/\\/g, "/").replace(/^(\.\/)+/, "");
  }

  /**
   * Lee un plano.json contra el catálogo del editor. Devuelve
   * {colocaciones, errores, avisos, rosa, rotulo}: con errores no se carga nada; los avisos
   * (p. ej. un detalle fuera del área que se ajustó) se cargan igual. rosa: {visible, pos} o
   * null (sin "rosa_vientos"); rotulo: el objeto "rotulo" tal cual, o null; ortofoto: la
   * sección "ortofoto" de un plano versión 4 ({archivo, bytes, crs, crs_dibujo, opacidad}) o null.
   */
  function leerPlano(texto, datos) {
    const errores = [];
    const avisos = [];
    let plano;
    const vacio = (lista) => ({ colocaciones: [], errores: lista, avisos, rosa: null, rotulo: null, ortofoto: null });
    try {
      plano = JSON.parse(texto);
    } catch (e) {
      return vacio(["El archivo no es un JSON válido: " + e.message]);
    }
    if (!esObjeto(plano)) {
      return vacio(["El plano debe ser un objeto JSON {...}."]);
    }
    if (![1, 2, 3, 4, 5, 6].includes(plano.version)) {
      errores.push("version: versión " + JSON.stringify(plano.version) +
        " no soportada; el editor entiende las versiones 1 a 6.");
    }
    const v6 = plano.version === 6; // zonas del Model Space (Fase 10e3)
    const v5 = plano.version === 5 || v6;
    const v4 = plano.version === 4 || v5;
    const v3 = plano.version === 3 || v4; // cada versión incluye todo lo de la anterior
    const v2 = plano.version === 2 || v3;
    if (!v4 && plano.ortofoto !== undefined) {
      errores.push("ortofoto: solo existe en la versión 4 del plano (use \"version\": 4).");
    }
    const ortofoto = v4 && plano.ortofoto !== undefined ? O.leerOrtofoto(plano.ortofoto, errores) : null;
    if (!v3 && plano.dxf !== undefined) {
      errores.push("dxf: solo existe en la versión 3 del plano (use \"version\": 3).");
    }
    const dxfs = v3 && plano.dxf !== undefined ? B.leerListaDxf(plano.dxf, errores, { v6 }) : new Map();
    const zonas = v6 ? B.leerZonas(plano.dxf, dxfs, errores) : [];
    for (const clave of ["rotulo", "rosa_vientos"]) {
      if (!v2 && plano[clave] !== undefined) {
        errores.push(clave + ": solo existe en la versión 2 del plano (use \"version\": 2).");
      }
    }
    const rosa = v2 ? leerRosa(plano.rosa_vientos, datos, errores, avisos) : null;
    let rotulo = null;
    if (v2 && plano.rotulo !== undefined) {
      if (esObjeto(plano.rotulo)) rotulo = plano.rotulo;
      else errores.push("rotulo: se esperaba un objeto {...} con los valores del rótulo.");
    }
    if (plano.formato !== undefined && normalizarRuta(plano.formato) !== normalizarRuta(datos.formato)) {
      avisos.push("El plano usa el formato '" + plano.formato + "' y el editor '" +
        datos.formato + "': se usará el del editor.");
    }
    // Versión 6: un plano solo con zonas borrador no tiene detalles todavía.
    if (!Array.isArray(plano.detalles) || (plano.detalles.length === 0 && !zonas.length)) {
      errores.push("detalles: se esperaba una lista con al menos un detalle.");
      return vacio(errores);
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
      if (v3 && "origen" in item && !(v6 && "manifiesto" in item)) { // bloque de un DXF sin exportar
        const b = B.leerPendiente(item, donde + " ('" + item.id + "')", dxfs, errores);
        if (!b) return;
        const pagina = B.paginaMm(b.bloque.tamano_m, b.escala, margenDe(null, datos));
        const centro = B.centroLimitado(b.centro, pagina, zona);
        const igual = centro[0] === b.centro[0] && centro[1] === b.centro[1];
        if (!igual) {
          avisos.push("'" + item.id + "' se salía del área de dibujo: su centro se movió a (" +
            centro[0].toFixed(2) + ", " + centro[1].toFixed(2) + ") mm.");
        }
        const colocacion = { id: item.id, bloque: b.bloque, escala: b.escala, centro, original: item,
          centroOriginal: igual ? centro.slice() : null, escalaOriginal: b.escala };
        if (b.etiqueta_escala === false) colocacion.etiqueta_escala = false;
        colocaciones.push(colocacion);
        return;
      }
      const ruta = normalizarRuta(item.manifiesto || "");
      const detalle = catalogo.get(ruta);
      if (!detalle) {
        const rechazado = rechazados.get(ruta);
        errores.push(donde + " ('" + item.id + "'): " + (rechazado
          ? "el paquete '" + rechazado.prefijo + "' está rechazado y no se puede colocar."
          : "el manifiesto '" + item.manifiesto + "' no está en el catálogo del editor."));
        return;
      }
      if (item.margen_mm !== undefined && (!v2 || !margenValido(item.margen_mm))) {
        errores.push(donde + ".margen_mm: " + (v2 ? "se esperaba un número de 0 a " + MARGEN_MAXIMO_MM + " mm."
          : "solo existe en la versión 2 del plano (use \"version\": 2)."));
        return;
      }
      const margen = item.margen_mm !== undefined ? item.margen_mm : margenDe(null, datos);
      if (!cabeDetalle(detalle, margen, zona)) {
        errores.push(donde + " ('" + item.id + "'): el detalle '" + detalle.id +
          "' no cabe en el área de dibujo (su dibujo y " + margen + " mm de margen).");
        return;
      }
      let pos;
      const tienePos = Array.isArray(item.posicion_mm) && item.posicion_mm.length === 2 &&
        item.posicion_mm.every((v) => typeof v === "number" && isFinite(v));
      if (item.centrar === true && item.posicion_mm === undefined) {
        pos = centrarDetalle(detalle, margen, zona);
      } else if (tienePos && item.centrar !== true) {
        pos = item.posicion_mm.slice();
      } else {
        errores.push(donde + " ('" + item.id + "'): lleva posicion_mm [x, y] o centrar: true (uno de los dos).");
        return;
      }
      if (item.etiqueta_escala !== undefined &&
          (!v2 || typeof item.etiqueta_escala !== "boolean")) {
        errores.push(donde + ".etiqueta_escala: " + (v2 ? "se esperaba true o false."
          : "solo existe en la versión 2 del plano (use \"version\": 2)."));
        return;
      }
      const ajustada = clampDetalle(pos, detalle, margen, zona);
      if (ajustada[0] !== pos[0] || ajustada[1] !== pos[1]) {
        avisos.push("'" + item.id + "' se salía del área de dibujo: se movió a (" +
          ajustada[0].toFixed(2) + ", " + ajustada[1].toFixed(2) + ") mm.");
      }
      // original / posOriginal: para guardar el detalle tal como vino si no se mueve (4.3a).
      const colocacion = { id: item.id, detalle: detalle, pos: ajustada, original: item,
        posOriginal: ajustada[0] === pos[0] && ajustada[1] === pos[1] ? ajustada.slice() : null };
      if (item.origen !== undefined) { // versión 6: exportado desde una zona del Model Space
        const z = v6 && esObjeto(item.origen) ? zonas.find((x) => x.nombre === item.origen.zona) : null;
        if (!z) {
          errores.push(donde + ".origen: se esperaba {\"zona\": <nombre de una zona de la lista \"dxf\">}.");
          return;
        }
        colocacion.zona = zonaDeColocacion(z);
      }
      if (item.etiqueta_escala === false) colocacion.etiqueta_escala = false;
      if (item.margen_mm !== undefined) colocacion.margen = item.margen_mm;
      colocaciones.push(colocacion);
    });
    if (errores.length) return vacio(errores);
    // Ortofoto por detalle (versión 5). Una versión 4 con ortofoto la llevaba detrás de TODOS:
    // se migra marcándolos a todos (y al guardar pasa a la 5).
    for (const [i, c] of colocaciones.entries()) {
      const item = plano.detalles[i];
      if (!v5 && item.ortofoto !== undefined) {
        errores.push("detalles[" + i + "].ortofoto: solo existe en la versión 5 del plano (use \"version\": 5).");
      } else if (item.ortofoto !== undefined && typeof item.ortofoto !== "boolean") {
        errores.push("detalles[" + i + "].ortofoto: se esperaba true o false.");
      }
      c.ortofoto = v5 ? item.ortofoto === true : !!ortofoto;
      if (c.ortofoto && !ortofoto) {
        errores.push("detalles[" + i + "] ('" + c.id + "'): lleva \"ortofoto\": true, pero el plano no tiene la sección \"ortofoto\".");
      }
    }
    if (errores.length) return vacio(errores);
    // Versión 6: las zonas que ningún detalle nombra son borradores (vuelven a la hoja).
    const exportadas = new Set(colocaciones.filter((c) => c.zona).map((c) => c.zona.nombre));
    for (const z of zonas) {
      if (exportadas.has(z.nombre)) continue;
      if (colocaciones.some((c) => c.id === z.nombre)) {
        errores.push("zonas: '" + z.nombre + "' tiene el mismo nombre que un detalle del plano.");
        continue;
      }
      const pagina = B.paginaMm(z.tamano_m, z.escala, margenDe(null, datos));
      const centro = B.centroLimitado(z.centro, pagina, zona);
      colocaciones.push({ id: z.nombre, escala: z.escala, centro, bloque: Object.assign(zonaDeColocacion(z).bloque,
        { sugerida: B.escalaSugerida(z.tamano_m, margenDe(null, datos), zona) }) });
    }
    if (errores.length) return vacio(errores);
    if (ortofoto && plano.version === 4) {
      avisos.push("Plano versión 4: la ortofoto iba detrás de todos los detalles. Ahora se elige por " +
        "detalle («Usar ortofoto»): quedan todos marcados. Se guardará en versión 5.");
    }
    return { colocaciones, errores, avisos, rosa, rotulo, ortofoto, original: plano };
  }

  /**
   * Lo que guarda una colocación de una zona leída del plano: {nombre, rect, capas, excluir,
   * modo, desmarcadas, tamano_m, dxf} y, para un borrador, `bloque` (como agregarZona del editor).
   */
  function zonaDeColocacion(z) {
    const datosZona = { rect: z.rect.slice(), capas: z.capas, excluir: z.excluir,
      modo: z.capas ? "solo" : "excluir", desmarcadas: (z.excluir || []).slice(), escala_dibujo: z.escala_dibujo || null };
    return Object.assign({ nombre: z.nombre, tamano_m: z.tamano_m.slice(), dxf: z.dxf }, datosZona, {
      bloque: { dxf: z.dxf, nombre: z.nombre, etiqueta: z.nombre, handle: null, ocurrencia: 1, total_ocurrencias: 1,
        tamano_m: z.tamano_m.slice(), caja_exacta: true, sugerida: null, escalas: B.ESCALAS, zona: datosZona } });
  }

  /** Las zonas del plano para guardar: por id de DXF, la lista "zonas" (versión 6). */
  function zonasParaGuardar(colocaciones) {
    const porDxf = new Map();
    for (const c of colocaciones) {
      let z;
      if (c.bloque && c.bloque.zona) { // borrador: su escala y su centro
        z = { dxf: c.bloque.dxf, guardar: B.zonaParaGuardar(Object.assign({ nombre: c.bloque.nombre,
          tamano_m: c.bloque.tamano_m }, c.bloque.zona), c.escala, c.centro) };
      } else if (c.zona && c.detalle) { // exportada: la escala y el centro del detalle de hoy
        const t = c.detalle.tamano_pagina_mm;
        z = { dxf: c.zona.dxf, guardar: B.zonaParaGuardar(c.zona, c.detalle.escala,
          [c.pos[0] + t[0] / 2, c.pos[1] + t[1] / 2]) };
      } else {
        continue;
      }
      if (!porDxf.has(z.dxf.id)) porDxf.set(z.dxf.id, []);
      porDxf.get(z.dxf.id).push(z.guardar);
    }
    return porDxf;
  }

  return {
    EPS_MM,
    ZONA_EDITABLE,
    ROSA,
    tamanoRosa,
    rectRosa,
    elementosVisibles,
    escalaDeImagen,
    papelAPantalla,
    pantallaAPapel,
    rectPapelAPantalla,
    paginaEnPapel,
    dibujoEnPapel,
    MARGEN_POR_DEFECTO_MM,
    MARGEN_MAXIMO_MM,
    margenDe,
    margenValido,
    recorteDetalle,
    visibleEnPapel,
    clampDetalle,
    centrarDetalle,
    redondearDetalle,
    cabeDetalle,
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
    objetoPlano,
    leerPlano,
  };
});
