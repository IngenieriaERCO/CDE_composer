/*
 * Editor de planos — ortofoto de fondo (lógica pura, sin pantalla). Funciona en el navegador
 * (window.EditorOrtofoto) y en Node (module.exports), para probarla desde pytest.
 *
 * Una ortofoto por plano, DETRÁS de todos los detalles y recortada a la caja (página) de cada
 * uno; fuera de los detalles, nada. Para cada detalle el editor pide al servidor la ortofoto de
 * la caja CAD que cubre su página en la hoja:
 *
 * - detalle exportado: con su matriz cad_to_page [a, b, c, d, e, f] (página en mm, origen
 *   arriba-izquierda, Y abajo): un punto de la hoja (sx, sy) es el punto de página
 *   (sx − x0, alto − (sy − y0)), y de ahí a CAD con la inversa de la matriz.
 * - bloque sin exportar: papel = P + k·(X − C), k = mm por unidad ÷ N (editor_bloques.js),
 *   así que X = C + (papel − P) ÷ k.
 *
 * La imagen que vuelve cubre EXACTAMENTE esa caja: se dibuja sobre la página del detalle.
 *
 * plano.json versión 4 (plano_ortofoto.py en Python): "ortofoto": {archivo, bytes, modificado,
 * crs, crs_dibujo, opacidad}. bytes y modificado (fecha, UTC, al segundo) dicen qué archivo se
 * eligió: «Cargar ortofoto» avisa si el que se elige no coincide, y componer usa el original
 * solo si coincide (si no, la copia reducida).
 */
(function (raiz, fabrica) {
  "use strict";
  const api = fabrica();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    raiz.EditorOrtofoto = api;
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const LADO_PX = 1500; // igual que previa_ortofoto.LADO_PX
  const RE_EPSG = /^EPSG:\d{4,6}$/;
  const CLAVES = ["archivo", "bytes", "modificado", "crs", "crs_dibujo", "opacidad", "extender", "cuadricula"];
  const RE_FECHA = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/;
  const esNumero = (v) => typeof v === "number" && isFinite(v);
  const esObjeto = (v) => v !== null && typeof v === "object" && !Array.isArray(v);

  /** "epsg:9377", " 9377 " o "EPSG:9377" → "EPSG:9377"; null si no es un código. */
  function leerSistema(texto) {
    if (typeof texto !== "string") return null;
    const t = texto.trim().toUpperCase().replace(/^EPSG\s*:\s*/, "");
    return /^\d{4,6}$/.test(t) ? "EPSG:" + t : null;
  }

  /** Caja [x0, y0, x1, y1] de los 4 puntos. */
  function cajaDe(puntos) {
    const xs = puntos.map((p) => p[0]);
    const ys = puntos.map((p) => p[1]);
    return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
  }

  const esquinas = (r) => [[r[0], r[1]], [r[0], r[3]], [r[2], r[1]], [r[2], r[3]]];

  /**
   * Caja CAD de `rect` (por defecto, la página) con el mapeo de un detalle exportado. pagina:
   * [x0, y0, x1, y1] de su página en la hoja (mm, Y arriba); m: cad_to_page. En modo extendido
   * rect es el área de dibujo (el mapeo sigue siendo el de la página). null si la matriz está
   * girada (b o c ≠ 0: la imagen no se puede poner derecha) o no se puede invertir.
   */
  function cajaCadDetalle(pagina, m, rect) {
    rect = rect || pagina;
    if (!Array.isArray(m) || m.length !== 6 || !m.every(esNumero)) return null;
    const [a, b, c, d, e, f] = m;
    if (b !== 0 || c !== 0) return null;
    const det = a * d - b * c;
    if (!det) return null;
    const alto = pagina[3] - pagina[1];
    const aCad = ([sx, sy]) => {
      const px = sx - pagina[0] - e;
      const py = alto - (sy - pagina[1]) - f;
      return [(d * px - c * py) / det, (-b * px + a * py) / det];
    };
    return cajaDe(esquinas(rect).map(aCad));
  }

  /** Caja CAD de la página de un bloque sin exportar (centro en la hoja y centro CAD, k mm/unidad). */
  function cajaCadBloque(pagina, centro, centroCad, k) {
    if (!(k > 0)) return null;
    const aCad = ([sx, sy]) => [centroCad[0] + (sx - centro[0]) / k, centroCad[1] + (sy - centro[1]) / k];
    return cajaDe(esquinas(pagina).map(aCad));
  }

  /** Clave de una vista previa (la caja redondeada a 1 mm de CAD en m, más los sistemas). */
  function clavePrevia(caja, mmPorUnidad, crsDibujo, crsOrtofoto) {
    const r = (v) => Math.round(v * 1000) / 1000;
    return JSON.stringify([caja.map(r), mmPorUnidad, crsDibujo, crsOrtofoto || null]);
  }

  // ---------------------------------------------------------------------------------------
  // Ficha (lo que el servidor leyó de la cabecera) y avisos.
  // ---------------------------------------------------------------------------------------

  const coma = (v, d) => v.toFixed(d).replace(".", ",");
  const miles = (n) => String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, " ");

  function textoBytes(n) {
    if (n >= 1024 ** 3) return coma(n / 1024 ** 3, 2) + " GB";
    if (n >= 1024 ** 2) return coma(n / 1024 ** 2, 1) + " MB";
    return coma(n / 1024, 0) + " kB";
  }

  /** Las líneas de la ficha de la ortofoto. */
  function lineasFicha(ficha) {
    const lineas = [];
    lineas.push(ficha.nombre + " · " + textoBytes(ficha.bytes) + (ficha.bigtiff ? " · BigTIFF" : ""));
    lineas.push(miles(ficha.px[0]) + " × " + miles(ficha.px[1]) + " px · " + ficha.color + " · " + ficha.tipo +
      (ficha.bandas > 1 ? " (" + ficha.bandas + " bandas)" : ""));
    lineas.push("Sistema: " + (ficha.sistema
      ? (ficha.sistema.codigo || "sin código EPSG") + " · " + ficha.sistema.nombre
      : "el archivo no lo dice"));
    const res = ficha.resolucion;
    const igual = Math.abs(res[0] - res[1]) < 1e-6 * Math.max(res[0], res[1]);
    lineas.push("Píxel: " + (igual ? coma(res[0], 3) : coma(res[0], 3) + " × " + coma(res[1], 3)) +
      (ficha.sistema ? " m" : " unidades") + (ficha.girada ? " · girada" : ""));
    const l = ficha.limites;
    lineas.push("Cubre: " + miles(l[2] - l[0]) + " × " + miles(l[3] - l[1]) + (ficha.sistema ? " m" : " unidades"));
    lineas.push("Pirámides: " + (ficha.piramides.length ? ficha.piramides.join(", ") : "no") + " · " +
      (ficha.mosaicos ? "mosaicos " + ficha.bloque_px[1] + " × " + ficha.bloque_px[0] : "franjas") + " · " +
      (ficha.compresion ? "compresión " + ficha.compresion : "sin compresión"));
    lineas.push("Fondo transparente: " + ({ alfa: "banda alfa", nodata: "valor nodata " + ficha.nodata,
      mascara: "máscara" }[ficha.fondo] || "no"));
    return lineas;
  }

  /**
   * Avisos de la ficha y del plano: [{nivel: "error"|"elegir"|"aviso"|"info", texto}].
   * plano: {crs, crs_dibujo} (lo elegido en el selector). crsDxf: el sistema que dio el DXF
   * cargado ({codigo, nombre, oficial, aviso, sugerido}, de sistema_dxf.py) o null.
   */
  function avisos(ficha, plano, cambio, crsDxf) {
    const lista = (ficha.avisos || []).filter((a) => !(a.nivel === "elegir" && plano.crs));
    if (cambio) lista.unshift({ nivel: "error", texto: "La ortofoto cambió en el disco desde que se cargó: vuelva a cargarla." });
    if (!plano.crs_dibujo) {
      lista.push({ nivel: "elegir", texto: "Elija el sistema de coordenadas del dibujo (el DXF no lo informa todavía): " +
        "sin él no se sabe dónde cae la ortofoto." });
    }
    if (crsDxf && crsDxf.aviso) lista.push({ nivel: "aviso", texto: crsDxf.aviso });
    // Solo si el código del DXF se usa para prellenar (salió de un Alias, no de la autoridad).
    if (crsDxf && crsDxf.oficial && crsDxf.prellenar !== false && plano.crs_dibujo) {
      lista.push(plano.crs_dibujo === crsDxf.codigo
        ? { nivel: "info", texto: "Sistema del dibujo tomado del DXF (" + crsDxf.codigo + "): se puede cambiar." }
        : { nivel: "aviso", texto: "El DXF dice " + crsDxf.codigo + ", pero el plano usa " + plano.crs_dibujo +
            " para el dibujo: revise cuál es el correcto." });
    }
    const propio = ficha.sistema && ficha.sistema.codigo;
    const deOrtofoto = propio || plano.crs;
    if (deOrtofoto && plano.crs_dibujo && deOrtofoto !== plano.crs_dibujo) {
      lista.push({ nivel: "info", texto: "La ortofoto está en " + deOrtofoto + " y el dibujo en " + plano.crs_dibujo +
        ": se reproyecta." });
    }
    return lista;
  }

  /** ¿Se pueden pedir vistas previas? (sistema del dibujo y, si hace falta, el de la ortofoto). */
  const listaParaPrevias = (ficha, plano, cambio) =>
    !cambio && !!plano.crs_dibujo && (!!ficha.sistema || !!plano.crs);

  /** Texto de lo que cubre la ortofoto en un detalle. */
  function textoCobertura(cobertura) {
    if (cobertura <= 0) return "la ortofoto no cubre este detalle";
    if (cobertura >= 0.9995) return "la ortofoto cubre todo el detalle";
    return "la ortofoto cubre el " + Math.max(1, Math.round(cobertura * 100)) + " % del detalle";
  }

  const RUMBOS = ["al este", "al noreste", "al norte", "al noroeste", "al oeste", "al suroeste", "al sur", "al sureste"];

  /**
   * El aviso de cobertura de un detalle con «Usar ortofoto», o null si la foto lo cubre entero.
   * {nivel: "fuerte" (no lo cubre) | "aviso" (en parte), corto, largo}. cajaDetalle y foto:
   * [x0, y0, x1, y1] en el sistema del dibujo (foto: `foto_en_dibujo` de la vista previa, o
   * null); mmPorUnidad: para dar la distancia en m o km (1000 en un dibujo en metros).
   */
  function avisoCobertura(cobertura, cajaDetalle, foto, mmPorUnidad) {
    if (!(cobertura >= 0) || cobertura >= 0.9995) return null;
    if (cobertura > 0) {
      const n = Math.min(99, Math.max(1, Math.round(cobertura * 100)));
      const corto = "La ortofoto cubre solo el " + n + " % de este detalle";
      return { nivel: "aviso", corto, largo: corto + ": el resto queda sin foto (en blanco)." };
    }
    const corto = "La ortofoto no cubre este detalle";
    let donde = "";
    if (foto && cajaDetalle) {
      const cx = (foto[0] + foto[2]) / 2 - (cajaDetalle[0] + cajaDetalle[2]) / 2;
      const cy = (foto[1] + foto[3]) / 2 - (cajaDetalle[1] + cajaDetalle[3]) / 2;
      const metros = Math.hypot(cx, cy) * (mmPorUnidad || 1000) / 1000;
      const sector = ((Math.round(Math.atan2(cy, cx) / (Math.PI / 4)) % 8) + 8) % 8;
      const distancia = metros >= 1000 ? (metros / 1000).toFixed(1).replace(".", ",") + " km" : miles(metros) + " m";
      donde = ": la foto queda a " + distancia + " " + RUMBOS[sector] + " (su centro, en el sistema del dibujo: X " +
        miles((foto[0] + foto[2]) / 2) + ", Y " + miles((foto[1] + foto[3]) / 2) + "). Revise que sea la foto de " +
        "esta obra y que el sistema del dibujo sea el correcto";
    }
    return { nivel: "fuerte", corto, largo: corto + donde + "." };
  }

  const nombreDe = (r) => String(r).replace(/\\/g, "/").split("/").pop();
  const fechaTexto = (f) => f.replace("T", " ").replace("Z", " UTC");

  /**
   * Qué no coincide entre la ortofoto del plano y la cargada (estado del servidor): nombre,
   * tamaño y fecha (solo lo que el plano guardó). [] si es la misma.
   */
  function diferencias(plano, estado) {
    const lista = [];
    const a = nombreDe(plano.archivo);
    const b = nombreDe(estado.archivo_plano);
    if (a.toLowerCase() !== b.toLowerCase()) lista.push("nombre: el plano usa «" + a + "» y la elegida es «" + b + "»");
    const bytes = estado.ficha.bytes;
    if (plano.bytes !== null && plano.bytes !== undefined && plano.bytes !== bytes) {
      lista.push("tamaño: el plano dice " + miles(plano.bytes) + " bytes y la elegida tiene " + miles(bytes));
    }
    const fecha = estado.ficha.modificado;
    if (plano.modificado && plano.modificado !== fecha) {
      lista.push("fecha: el plano dice " + fechaTexto(plano.modificado) + " y la elegida es del " + fechaTexto(fecha));
    }
    return lista;
  }

  /** ¿La ortofoto cargada es la del plano? (mismo nombre y, si los guardó, tamaño y fecha). */
  function esLaDelPlano(plano, estado) {
    if (!plano || !estado) return false;
    return diferencias(plano, estado).length === 0;
  }

  // ---------------------------------------------------------------------------------------
  // plano.json versión 4.
  // ---------------------------------------------------------------------------------------

  /** La sección "ortofoto" → {archivo, bytes, crs, crs_dibujo, opacidad}, o null con errores. */
  function leerOrtofoto(valor, errores) {
    if (!esObjeto(valor)) {
      errores.push("ortofoto: se esperaba un objeto {\"archivo\": ...}.");
      return null;
    }
    const n = errores.length;
    for (const k of Object.keys(valor)) {
      if (!CLAVES.includes(k)) errores.push("ortofoto." + k + ": campo no reconocido (campos válidos: " + CLAVES.join(", ") + ").");
    }
    if (typeof valor.archivo !== "string" || !valor.archivo.trim()) {
      errores.push("ortofoto.archivo: se esperaba la ruta del GeoTIFF (texto no vacío).");
    } else if (!/\.tiff?$/i.test(valor.archivo)) {
      errores.push("ortofoto.archivo: '" + valor.archivo + "' no es un .tif ni un .tiff.");
    }
    const b = valor.bytes;
    if (b !== undefined && b !== null && !(Number.isInteger(b) && b >= 0)) {
      errores.push("ortofoto.bytes: se esperaba un entero ≥ 0.");
    }
    const m = valor.modificado;
    if (m !== undefined && m !== null && !(typeof m === "string" && RE_FECHA.test(m))) {
      errores.push("ortofoto.modificado: se esperaba la fecha «AAAA-MM-DDTHH:MM:SSZ» o null.");
    }
    for (const k of ["crs", "crs_dibujo"]) {
      const v = valor[k];
      if (v !== undefined && v !== null && !(typeof v === "string" && RE_EPSG.test(v))) {
        errores.push("ortofoto." + k + ": se esperaba «EPSG:<código>» (p. ej. EPSG:9377) o null.");
      }
    }
    const o = valor.opacidad === undefined ? 1 : valor.opacidad;
    if (!esNumero(o) || o < 0 || o > 1) errores.push("ortofoto.opacidad: se esperaba un número de 0 a 1.");
    if (valor.extender !== undefined && typeof valor.extender !== "boolean") {
      errores.push("ortofoto.extender: se esperaba true o false.");
    }
    const c = valor.cuadricula;
    if (c !== undefined) {
      if (!esObjeto(c)) errores.push("ortofoto.cuadricula: se esperaba un objeto {\"visible\", \"intervalo_m\"}.");
      else {
        for (const k of Object.keys(c)) {
          if (k !== "visible" && k !== "intervalo_m") errores.push("ortofoto.cuadricula." + k + ": campo no reconocido (campos válidos: intervalo_m, visible).");
        }
        if (c.visible !== undefined && typeof c.visible !== "boolean") errores.push("ortofoto.cuadricula.visible: se esperaba true o false.");
        if (c.intervalo_m !== undefined && c.intervalo_m !== null && !(esNumero(c.intervalo_m) && c.intervalo_m > 0 && c.intervalo_m <= 100000)) {
          errores.push("ortofoto.cuadricula.intervalo_m: se esperaba un número de m > 0.");
        }
      }
    }
    if (errores.length !== n) return null;
    return { archivo: valor.archivo, bytes: b === undefined ? null : b, modificado: m || null,
      crs: valor.crs || null, crs_dibujo: valor.crs_dibujo || null, opacidad: o,
      extender: valor.extender === true, cuadricula: !!(c && c.visible === true),
      intervalo_m: c && esNumero(c.intervalo_m) ? c.intervalo_m : null };
  }

  /** La sección "ortofoto" para guardar (las mismas claves, en el mismo orden; "extender" y
   *  "cuadricula" solo si se usan, así un plano que no los tiene sale igual). */
  function ortofotoParaGuardar(o) {
    const s = { archivo: o.archivo, bytes: o.bytes === undefined ? null : o.bytes, modificado: o.modificado || null,
      crs: o.crs || null, crs_dibujo: o.crs_dibujo || null, opacidad: Math.round(o.opacidad * 100) / 100 };
    if (o.extender === true) s.extender = true;
    if (o.cuadricula === true || esNumero(o.intervalo_m)) {
      s.cuadricula = { visible: o.cuadricula === true };
      if (esNumero(o.intervalo_m)) s.cuadricula.intervalo_m = o.intervalo_m;
    }
    return s;
  }

  // ---------------------------------------------------------------------------------------
  // Cuadrícula de coordenadas (cuadricula.py en Python: la misma regla; las pruebas lo comparan).
  // Líneas en la región (la página del detalle o, extendida, el área de dibujo); etiquetas en
  // una franja de 10 mm FUERA de ella, como en el plano de AutoCAD de PRGD.
  // ---------------------------------------------------------------------------------------

  // Como en PRGD: Arial de 10 pt (em de 3,528 mm), líneas negras de 0,085 mm, franja de 10 mm.
  const CUADRICULA = { color: "#000000", grosor_mm: 0.085, tamano_pt: 10, em_mm: 10 * 25.4 / 72, banda_mm: 10,
    max_lineas: 400, espacio_min_mm: 15 };
  /** Altura de las cifras a 10 pt (con la fuente del rótulo o Helvetica, 0,718 em). */
  const alturaCuadricula = (fuente) => CUADRICULA.em_mm * (fuente && fuente.altura_mayusculas ? fuente.altura_mayusculas : 0.718);
  const textoCoordenada = (v) => v.toFixed(3);

  /** Múltiplos de `intervalo` estrictamente dentro de (minimo, maximo) (cuadricula.valores). */
  function valoresCuadricula(minimo, maximo, intervalo) {
    const eps = intervalo * 1e-9;
    const salida = [];
    for (let k = Math.floor(minimo / intervalo) + 1; k <= Math.ceil(maximo / intervalo) - 1; k++) {
      const v = k * intervalo;
      if (minimo + eps < v && v < maximo - eps) salida.push(v);
    }
    return salida;
  }

  const cruza = (a, b) => a[0] < b[2] && b[0] < a[2] && a[1] < b[3] && b[1] < a[3];
  const dentro = (a, b) => a[0] >= b[0] - 1e-9 && a[1] >= b[1] - 1e-9 && a[2] <= b[2] + 1e-9 && a[3] <= b[3] + 1e-9;

  /**
   * La cuadrícula de una región. region: [x0, y0, x1, y1] en la hoja (mm); cajaM: la caja CAD
   * de esa región en m (sin giro: el mapeo es lineal); medir(texto) → ancho en mm a 2,5 mm.
   * {este, norte, lineas: [[x0, y0, x1, y1]], etiquetas: [{eje, texto, rect, base, giro}], omitidas, paso_mm}.
   */
  function cuadricula(region, cajaM, intervalo, obstaculos, limite, medir, altura) {
    const r = { este: valoresCuadricula(cajaM[0], cajaM[2], intervalo),
      norte: valoresCuadricula(cajaM[1], cajaM[3], intervalo), lineas: [], etiquetas: [], omitidas: 0, paso_mm: 0 };
    if (r.este.length + r.norte.length > CUADRICULA.max_lineas) {
      r.demasiadas = r.este.length + r.norte.length;
      r.este = [];
      r.norte = [];
      return r;
    }
    const [x0, y0, x1, y1] = region;
    const kx = (x1 - x0) / (cajaM[2] - cajaM[0]);
    const ky = (y1 - y0) / (cajaM[3] - cajaM[1]);
    r.paso_mm = intervalo * kx;
    const xs = r.este.map((e) => x0 + (e - cajaM[0]) * kx);
    const ys = r.norte.map((n) => y0 + (n - cajaM[1]) * ky);
    r.lineas = xs.map((x) => [x, y0, x, y1]).concat(ys.map((y) => [x0, y, x1, y]));
    const h = altura || alturaCuadricula(null);
    const mitad = CUADRICULA.banda_mm / 2;
    const candidatas = [];
    r.este.forEach((e, i) => {
      const t = textoCoordenada(e);
      const w = medir(t);
      for (const yb of [y0 - mitad - h / 2, y1 + mitad - h / 2]) {
        candidatas.push({ eje: "E", texto: t, rect: [xs[i] - w / 2, yb, xs[i] + w / 2, yb + h], base: [xs[i] - w / 2, yb], giro: 0 });
      }
    });
    r.norte.forEach((n, i) => {
      const t = textoCoordenada(n);
      const w = medir(t);
      for (const xb of [x0 - mitad + h / 2, x1 + mitad + h / 2]) {
        candidatas.push({ eje: "N", texto: t, rect: [xb - h, ys[i] - w / 2, xb, ys[i] + w / 2], base: [xb, ys[i] - w / 2], giro: 90 });
      }
    });
    const puestas = [];
    for (const et of candidatas) {
      if ((limite && !dentro(et.rect, limite)) || obstaculos.some((o) => cruza(et.rect, o)) ||
          puestas.some((p) => cruza(et.rect, p))) {
        r.omitidas++;
        continue;
      }
      r.etiquetas.push(et);
      puestas.push(et.rect);
    }
    return r;
  }

  /** Ancho de avance (mm) de un texto a 10 pt con la fuente del rótulo ({anchos_em}) o, sin
   *  ella, Helvetica (como cuadricula.ancho_texto_mm). */
  function medidorCuadricula(fuente) {
    const em = CUADRICULA.em_mm;
    if (fuente && fuente.anchos_em) {
      return (t) => [...t].reduce((s, c) => s + (c in fuente.anchos_em ? fuente.anchos_em[c] : 0.556), 0) * em;
    }
    const helv = (c) => (c === "." ? 0.278 : c === "-" ? 0.333 : 0.556);
    return (t) => [...t].reduce((s, c) => s + helv(c), 0) * em;
  }

  return { LADO_PX, avisoCobertura, leerSistema, cajaCadDetalle, cajaCadBloque, clavePrevia, textoBytes, lineasFicha,
    avisos, listaParaPrevias, textoCobertura, diferencias, esLaDelPlano, leerOrtofoto, ortofotoParaGuardar,
    CUADRICULA, textoCoordenada, valoresCuadricula, cuadricula, medidorCuadricula, alturaCuadricula };
});
