/*
 * Editor de planos — procesar una FIRMA en imagen (subfase 4.3b2). Lógica pura, sin pantalla:
 * funciona en el navegador (window.EditorFirma) y en Node (module.exports), para probarla desde
 * pytest con imágenes sintéticas.
 *
 * Una imagen es {ancho, alto, datos}: datos = RGBA, 4 bytes por píxel (como ImageData).
 *   1. recortar(img, rect): lo que la persona marcó con el mouse.
 *   1b. compensarFondo(img) (opción «Compensar sombras e iluminación despareja», por defecto
 *      sí): divide cada píxel por el fondo LOCAL estimado (máximo por bloques + vecinos +
 *      suavizado), así un papel con degradado o sombra queda blanco antes del umbral.
 *      umbralAutomatico(img, ...) = Otsu sobre esa imagen (el umbral inicial del diálogo).
 *   2. limpiar(img, umbral, tinta): el fondo claro pasa a transparente con un umbral SUAVE por
 *      luminosidad (Y = 0,299 R + 0,587 G + 0,114 B): Y <= umbral - SUAVIDAD/2 -> opaco; Y >=
 *      umbral + SUAVIDAD/2 -> transparente; entre los dos, gradual. Tinta "original" (el color
 *      se «despega» del blanco) o "negro".
 *   3. recorteAlTrazo(img, 2): la caja de los píxeles con trazo (alfa >= 16) y 2 px de margen.
 *   4. reducir(img, 600, 200): proporcional, promediando (con alfa premultiplicado: sin halos).
 *   5. codificarPng(img, deflate): PNG RGBA de 8 bits (tipo de color 6, con canal alfa). La
 *      compresión `deflate` (formato zlib) la pone quien llama: CompressionStream("deflate") en
 *      el navegador, zlib.deflateSync en Node.
 *   6. generar(...): todo lo anterior y, si pasa de 100 KB, reduce un 15 % y vuelve a probar.
 *   7. revisarPng(bytes, archivo, donde): las MISMAS reglas y textos que firmas.revisar_png
 *      (PNG, hasta 100 KB, hasta 600 x 200 px) y el aviso sin alfa de firmas.aviso_sin_alfa.
 *
 * Privacidad: nada de esto guarda la imagen; el diálogo la descarta al cerrarse.
 */
(function (raiz, fabrica) {
  "use strict";
  const api = fabrica();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    raiz.EditorFirma = api;
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const MAX_ANCHO_PX = 600;
  const MAX_ALTO_PX = 200;
  const MAX_BYTES = 100 * 1024;
  const SUAVIDAD = 40; // ancho (en niveles de luminosidad) de la transición opaco -> transparente
  const ALFA_TRAZO = 16; // desde este alfa un píxel cuenta como trazo para el recorte automático
  const MARGEN_PX = 2;
  const FIRMA_PNG = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];
  // Como firmas.NOMBRE_VALIDO: letras (con tildes y ñ), números, espacio, «_» y «-»; sin
  // espacios al principio ni al final; sin puntos ni separadores.
  const NOMBRE_VALIDO = /^[\p{L}\p{M}\p{N}_-](?:[\p{L}\p{M}\p{N}_ -]*[\p{L}\p{M}\p{N}_-])?$/u;

  function imagen(ancho, alto, datos) {
    return { ancho, alto, datos: datos || new Uint8ClampedArray(ancho * alto * 4) };
  }

  const luminosidad = (r, g, b) => 0.299 * r + 0.587 * g + 0.114 * b;

  // ---------------------------------------------------------------------------------------
  // Procesamiento.
  // ---------------------------------------------------------------------------------------

  /** Recorte a un rectángulo {x, y, ancho, alto} (px de la imagen; se ajusta a sus bordes). */
  function recortar(img, rect) {
    if (!rect) return imagen(img.ancho, img.alto, new Uint8ClampedArray(img.datos));
    const x0 = Math.max(0, Math.min(img.ancho, Math.round(rect.x)));
    const y0 = Math.max(0, Math.min(img.alto, Math.round(rect.y)));
    const x1 = Math.max(x0, Math.min(img.ancho, Math.round(rect.x + rect.ancho)));
    const y1 = Math.max(y0, Math.min(img.alto, Math.round(rect.y + rect.alto)));
    const salida = imagen(x1 - x0, y1 - y0);
    for (let y = y0; y < y1; y++) {
      salida.datos.set(img.datos.subarray((y * img.ancho + x0) * 4, (y * img.ancho + x1) * 4), (y - y0) * salida.ancho * 4);
    }
    return salida;
  }

  // ---------------------------------------------------------------------------------------
  // Sombras e iluminación despareja (4.3b2, mejora): fondo local y umbral automático.
  // ---------------------------------------------------------------------------------------

  /** Luminosidad de cada píxel, compuesto sobre blanco si trae alfa. */
  function luminosidades(img) {
    const y = new Float32Array(img.ancho * img.alto);
    const d = img.datos;
    for (let i = 0, k = 0; k < y.length; i += 4, k++) {
      const a = d[i + 3] / 255;
      y[k] = luminosidad(d[i] * a + 255 * (1 - a), d[i + 1] * a + 255 * (1 - a), d[i + 2] * a + 255 * (1 - a));
    }
    return y;
  }

  /** Lado del bloque para estimar el fondo: ~1/40 del lado mayor, al menos 8 px. */
  function bloqueFondo(img) {
    return Math.max(8, Math.round(Math.max(img.ancho, img.alto) / 40));
  }

  /**
   * Fondo local (luminosidad del «papel» en cada píxel): máximo por bloques, cierre entre
   * bloques vecinos (así un trazo grueso no pasa por fondo y el borde de una sombra no se corre),
   * promedio 3 x 3 e interpolación bilineal.
   */
  function estimarFondo(img, bloque) {
    const B = bloque || bloqueFondo(img);
    const y = luminosidades(img);
    const gw = Math.ceil(img.ancho / B);
    const gh = Math.ceil(img.alto / B);
    const maximo = new Float32Array(gw * gh);
    for (let py = 0; py < img.alto; py++) {
      for (let px = 0; px < img.ancho; px++) {
        const g = Math.floor(py / B) * gw + Math.floor(px / B);
        const v = y[py * img.ancho + px];
        if (v > maximo[g]) maximo[g] = v;
      }
    }
    const vecinos = (fuente, combinar) => {
      const salida = new Float32Array(gw * gh);
      for (let gy = 0; gy < gh; gy++) {
        for (let gx = 0; gx < gw; gx++) {
          const valores = [];
          for (let dy = -1; dy <= 1; dy++) {
            for (let dx = -1; dx <= 1; dx++) {
              const x = gx + dx;
              const yy = gy + dy;
              if (x >= 0 && yy >= 0 && x < gw && yy < gh) valores.push(fuente[yy * gw + x]);
            }
          }
          salida[gy * gw + gx] = combinar(valores);
        }
      }
      return salida;
    };
    // Cierre morfológico (máximo y luego mínimo entre vecinos): borra los bloques llenos de
    // tinta sin correr el borde de una sombra; después, un promedio 3 x 3.
    const dilatado = vecinos(maximo, (v) => Math.max(...v));
    const cerrado = vecinos(dilatado, (v) => Math.min(...v));
    const suave = vecinos(cerrado, (v) => v.reduce((s, x) => s + x, 0) / v.length);
    const fondo = new Float32Array(img.ancho * img.alto);
    for (let py = 0; py < img.alto; py++) {
      const fy = Math.min(Math.max((py + 0.5) / B - 0.5, 0), gh - 1);
      const y0 = Math.floor(fy);
      const y1 = Math.min(y0 + 1, gh - 1);
      const ty = fy - y0;
      for (let px = 0; px < img.ancho; px++) {
        const fx = Math.min(Math.max((px + 0.5) / B - 0.5, 0), gw - 1);
        const x0 = Math.floor(fx);
        const x1 = Math.min(x0 + 1, gw - 1);
        const tx = fx - x0;
        const arriba = suave[y0 * gw + x0] * (1 - tx) + suave[y0 * gw + x1] * tx;
        const abajo = suave[y1 * gw + x0] * (1 - tx) + suave[y1 * gw + x1] * tx;
        fondo[py * img.ancho + px] = Math.max(1, arriba * (1 - ty) + abajo * ty);
      }
    }
    return fondo;
  }

  /**
   * Imagen «aplanada»: cada píxel dividido por su fondo local (el papel queda blanco aunque
   * tenga sombra o degradado; el trazo conserva su contraste). Opaca, compuesta sobre blanco.
   */
  function compensarFondo(img, bloque) {
    const fondo = estimarFondo(img, bloque);
    const salida = imagen(img.ancho, img.alto);
    const d = img.datos;
    const s = salida.datos;
    for (let i = 0, k = 0; k < fondo.length; i += 4, k++) {
      const a = d[i + 3] / 255;
      const f = 255 / fondo[k];
      s[i] = (d[i] * a + 255 * (1 - a)) * f;
      s[i + 1] = (d[i + 1] * a + 255 * (1 - a)) * f;
      s[i + 2] = (d[i + 2] * a + 255 * (1 - a)) * f;
      s[i + 3] = 255;
    }
    return salida;
  }

  /** Umbral de Otsu sobre la luminosidad (0…255): el que mejor separa tinta y papel. */
  function umbralOtsu(img) {
    const hist = new Float64Array(256);
    const y = luminosidades(img);
    for (let k = 0; k < y.length; k++) hist[Math.min(255, Math.max(0, Math.round(y[k])))]++;
    let total = 0;
    let suma = 0;
    for (let t = 0; t < 256; t++) {
      total += hist[t];
      suma += t * hist[t];
    }
    let peso0 = 0;
    let suma0 = 0;
    let mejor = 0;
    let ultimo = 0; // si varios t empatan (un hueco sin píxeles entre tinta y papel), el centro
    let varianza = -1;
    for (let t = 0; t < 256; t++) {
      peso0 += hist[t];
      if (!peso0) continue;
      const peso1 = total - peso0;
      if (!peso1) break;
      suma0 += t * hist[t];
      const m0 = suma0 / peso0;
      const m1 = (suma - suma0) / peso1;
      const v = peso0 * peso1 * (m0 - m1) * (m0 - m1);
      if (v > varianza) {
        varianza = v;
        mejor = ultimo = t;
      } else if (v === varianza) {
        ultimo = t;
      }
    }
    return Math.round((mejor + ultimo) / 2);
  }

  const UMBRAL_MIN = 40;
  const UMBRAL_MAX = 250;

  /** Umbral automático para la imagen tal como se va a limpiar (recorte y compensación). */
  function umbralAutomatico(img, opciones) {
    let base = recortar(img, (opciones && opciones.recorte) || null);
    if (!opciones || opciones.compensar !== false) base = compensarFondo(base);
    return Math.min(UMBRAL_MAX, Math.max(UMBRAL_MIN, umbralOtsu(base)));
  }

  const LIMITE_OPACOS = 0.25;

  /** Fracción de píxeles opacos (alfa >= 128) de la imagen. */
  function fraccionOpaca(img) {
    let n = 0;
    for (let i = 3; i < img.datos.length; i += 4) if (img.datos[i] >= 128) n++;
    return n / Math.max(1, img.ancho * img.alto);
  }

  /** Aviso si más del 25 % de los píxeles de la firma quedan opacos ("" si no). */
  function avisoFondo(fraccion) {
    if (fraccion <= LIMITE_OPACOS) return "";
    return "Parece que queda fondo: el " + Math.round(fraccion * 100) + " % de los píxeles de la firma quedó opaco " +
      "(una firma limpia rara vez pasa del 25 %). Revise el umbral o repita la foto con más luz.";
  }

  /** Alfa (0…1) de un píxel de luminosidad `y` con este umbral (suave). */
  function alfaPorLuminosidad(y, umbral) {
    const t = (umbral + SUAVIDAD / 2 - y) / SUAVIDAD;
    return t <= 0 ? 0 : t >= 1 ? 1 : t;
  }

  /**
   * Fondo claro -> transparente. `tinta`: "original" (color del trazo, despegado del blanco) o
   * "negro". Un píxel ya transparente sigue transparente.
   */
  function limpiar(img, umbral, tinta) {
    const salida = imagen(img.ancho, img.alto);
    const s = salida.datos;
    const d = img.datos;
    for (let i = 0; i < d.length; i += 4) {
      // Si la imagen ya traía alfa, se compone sobre blanco antes de medir.
      const a0 = d[i + 3] / 255;
      const r = d[i] * a0 + 255 * (1 - a0);
      const g = d[i + 1] * a0 + 255 * (1 - a0);
      const b = d[i + 2] * a0 + 255 * (1 - a0);
      const a = alfaPorLuminosidad(luminosidad(r, g, b), umbral);
      if (a <= 0) continue; // transparente (s ya es 0)
      if (tinta === "negro") {
        s[i] = s[i + 1] = s[i + 2] = 0;
      } else {
        // Color «despegado» del blanco: c = (observado - 255 (1 - a)) / a.
        const k = Math.max(a, 0.05);
        s[i] = (r - 255 * (1 - k)) / k;
        s[i + 1] = (g - 255 * (1 - k)) / k;
        s[i + 2] = (b - 255 * (1 - k)) / k;
      }
      s[i + 3] = Math.round(a * 255);
    }
    return salida;
  }

  /** Caja del trazo (alfa >= ALFA_TRAZO) con `margen` px; null si no queda ningún trazo. */
  function cajaDelTrazo(img, margen) {
    let x0 = Infinity;
    let y0 = Infinity;
    let x1 = -1;
    let y1 = -1;
    for (let y = 0; y < img.alto; y++) {
      for (let x = 0; x < img.ancho; x++) {
        if (img.datos[(y * img.ancho + x) * 4 + 3] >= ALFA_TRAZO) {
          if (x < x0) x0 = x;
          if (x > x1) x1 = x;
          if (y < y0) y0 = y;
          if (y > y1) y1 = y;
        }
      }
    }
    if (x1 < 0) return null;
    const m = margen === undefined ? MARGEN_PX : margen;
    x0 = Math.max(0, x0 - m);
    y0 = Math.max(0, y0 - m);
    x1 = Math.min(img.ancho - 1, x1 + m);
    y1 = Math.min(img.alto - 1, y1 + m);
    return { x: x0, y: y0, ancho: x1 - x0 + 1, alto: y1 - y0 + 1 };
  }

  function recorteAlTrazo(img, margen) {
    const caja = cajaDelTrazo(img, margen);
    return caja ? recortar(img, caja) : null;
  }

  /** Tamaño final: proporcional, dentro de max_ancho x max_alto (nunca se agranda). */
  function tamanoReducido(ancho, alto, maxAncho, maxAlto, factor) {
    const f = Math.min(1, maxAncho / ancho, maxAlto / alto) * (factor || 1);
    return { ancho: Math.max(1, Math.round(ancho * f)), alto: Math.max(1, Math.round(alto * f)) };
  }

  /** Reducción por promedio de área (alfa premultiplicado). */
  function reducir(img, maxAncho, maxAlto, factor) {
    const t = tamanoReducido(img.ancho, img.alto, maxAncho || MAX_ANCHO_PX, maxAlto || MAX_ALTO_PX, factor);
    if (t.ancho === img.ancho && t.alto === img.alto) return imagen(img.ancho, img.alto, new Uint8ClampedArray(img.datos));
    const salida = imagen(t.ancho, t.alto);
    const fx = img.ancho / t.ancho;
    const fy = img.alto / t.alto;
    for (let y = 0; y < t.alto; y++) {
      const sy0 = y * fy;
      const sy1 = (y + 1) * fy;
      for (let x = 0; x < t.ancho; x++) {
        const sx0 = x * fx;
        const sx1 = (x + 1) * fx;
        let r = 0, g = 0, b = 0, a = 0, peso = 0;
        for (let sy = Math.floor(sy0); sy < Math.ceil(sy1); sy++) {
          const wy = Math.min(sy + 1, sy1) - Math.max(sy, sy0);
          for (let sx = Math.floor(sx0); sx < Math.ceil(sx1); sx++) {
            const w = wy * (Math.min(sx + 1, sx1) - Math.max(sx, sx0));
            const i = (sy * img.ancho + sx) * 4;
            const al = img.datos[i + 3] / 255;
            r += img.datos[i] * al * w;
            g += img.datos[i + 1] * al * w;
            b += img.datos[i + 2] * al * w;
            a += al * w;
            peso += w;
          }
        }
        const o = (y * t.ancho + x) * 4;
        if (a > 0) {
          salida.datos[o] = r / a;
          salida.datos[o + 1] = g / a;
          salida.datos[o + 2] = b / a;
        }
        salida.datos[o + 3] = Math.round((a / peso) * 255);
      }
    }
    return salida;
  }

  // ---------------------------------------------------------------------------------------
  // PNG (RGBA 8 bits).
  // ---------------------------------------------------------------------------------------

  const TABLA_CRC = (() => {
    const t = new Uint32Array(256);
    for (let n = 0; n < 256; n++) {
      let c = n;
      for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
      t[n] = c >>> 0;
    }
    return t;
  })();

  function crc32(bytes) {
    let c = 0xffffffff;
    for (let i = 0; i < bytes.length; i++) c = TABLA_CRC[(c ^ bytes[i]) & 0xff] ^ (c >>> 8);
    return (c ^ 0xffffffff) >>> 0;
  }

  function trozo(tipo, contenido) {
    const salida = new Uint8Array(12 + contenido.length);
    const vista = new DataView(salida.buffer);
    vista.setUint32(0, contenido.length);
    for (let i = 0; i < 4; i++) salida[4 + i] = tipo.charCodeAt(i);
    salida.set(contenido, 8);
    vista.setUint32(8 + contenido.length, crc32(salida.subarray(4, 8 + contenido.length)));
    return salida;
  }

  /** Filas con su filtro (el de menor suma absoluta entre None, Sub, Up y Paeth). */
  function filtrar(img) {
    const linea = img.ancho * 4;
    const salida = new Uint8Array((linea + 1) * img.alto);
    const d = img.datos;
    const candidatos = [new Uint8Array(linea), new Uint8Array(linea), new Uint8Array(linea), new Uint8Array(linea)];
    for (let y = 0; y < img.alto; y++) {
      const fila = y * linea;
      const previa = (y - 1) * linea;
      for (let i = 0; i < linea; i++) {
        const x = d[fila + i];
        const a = i >= 4 ? d[fila + i - 4] : 0;
        const b = y > 0 ? d[previa + i] : 0;
        const c = y > 0 && i >= 4 ? d[previa + i - 4] : 0;
        const p = a + b - c;
        const pa = Math.abs(p - a);
        const pb = Math.abs(p - b);
        const pc = Math.abs(p - c);
        const paeth = pa <= pb && pa <= pc ? a : pb <= pc ? b : c;
        candidatos[0][i] = x;
        candidatos[1][i] = (x - a) & 0xff;
        candidatos[2][i] = (x - b) & 0xff;
        candidatos[3][i] = (x - paeth) & 0xff;
      }
      let mejor = 0;
      let menor = Infinity;
      candidatos.forEach((cand, k) => {
        let suma = 0;
        for (let i = 0; i < linea; i++) suma += cand[i] < 128 ? cand[i] : 256 - cand[i];
        if (suma < menor) {
          menor = suma;
          mejor = k === 3 ? 4 : k; // tipos de filtro PNG: 0 None, 1 Sub, 2 Up, 4 Paeth
        }
      });
      salida[y * (linea + 1)] = mejor;
      salida.set(candidatos[mejor === 4 ? 3 : mejor], y * (linea + 1) + 1);
    }
    return salida;
  }

  /** PNG RGBA. `deflate(bytes)` -> bytes en formato zlib (o una promesa de ellos). */
  async function codificarPng(img, deflate) {
    const cabecera = new Uint8Array(13);
    const vista = new DataView(cabecera.buffer);
    vista.setUint32(0, img.ancho);
    vista.setUint32(4, img.alto);
    cabecera.set([8, 6, 0, 0, 0], 8); // 8 bits, RGBA, deflate, filtro adaptativo, sin entrelazado
    const comprimido = new Uint8Array(await deflate(filtrar(img)));
    const partes = [Uint8Array.from(FIRMA_PNG), trozo("IHDR", cabecera), trozo("IDAT", comprimido), trozo("IEND", new Uint8Array(0))];
    const salida = new Uint8Array(partes.reduce((s, p) => s + p.length, 0));
    let pos = 0;
    for (const p of partes) {
      salida.set(p, pos);
      pos += p.length;
    }
    return salida;
  }

  // ---------------------------------------------------------------------------------------
  // Revisión (firmas.revisar_png) y nombre de persona.
  // ---------------------------------------------------------------------------------------

  /** {ancho, alto, alfa} de la cabecera de un PNG (alfa: tipo de color 4 o 6, o trozo tRNS). */
  function leerCabeceraPng(bytes) {
    const vista = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    const ancho = vista.getUint32(16);
    const alto = vista.getUint32(20);
    let alfa = bytes[25] === 4 || bytes[25] === 6;
    for (let pos = 8; pos + 8 <= bytes.length;) {
      const largo = vista.getUint32(pos);
      const tipo = String.fromCharCode(bytes[pos + 4], bytes[pos + 5], bytes[pos + 6], bytes[pos + 7]);
      if (tipo === "tRNS") alfa = true;
      if (tipo === "IEND") break;
      pos += 12 + largo;
    }
    return { ancho, alto, alfa };
  }

  /** {problemas, ancho, alto, alfa}: mismos textos que firmas.revisar_png. */
  function revisarPng(bytes, archivo, donde) {
    const esPng = bytes.length >= 8 && FIRMA_PNG.every((b, i) => bytes[i] === b);
    if (!esPng) return { problemas: [donde + ": '" + archivo + "' no es un PNG"], ancho: 0, alto: 0, alfa: false };
    const problemas = [];
    if (bytes.length > MAX_BYTES) {
      problemas.push(donde + ": '" + archivo + "' pesa " + (bytes.length / 1024).toFixed(1) + " KB y el máximo es " +
        Math.floor(MAX_BYTES / 1024) + " KB");
    }
    let cab;
    try {
      cab = leerCabeceraPng(bytes);
    } catch (e) {
      problemas.push(donde + ": '" + archivo + "' no se pudo leer como imagen: " + e.message);
      return { problemas, ancho: 0, alto: 0, alfa: false };
    }
    if (cab.ancho > MAX_ANCHO_PX || cab.alto > MAX_ALTO_PX) {
      problemas.push(donde + ": '" + archivo + "' mide " + cab.ancho + " x " + cab.alto + " px y el máximo es " +
        MAX_ANCHO_PX + " x " + MAX_ALTO_PX + " px");
    }
    return { problemas, ancho: cab.ancho, alto: cab.alto, alfa: cab.alfa };
  }

  /** firmas.aviso_sin_alfa. */
  function avisoSinAlfa(persona, nombreArchivo, rutaCelda) {
    return "Advertencia: la firma de '" + persona + "' (" + nombreArchivo + ") no tiene canal alfa " +
      "(transparencia): su fondo tapará las líneas de la celda '" + rutaCelda + "'. Límpiela antes de emitir el plano.";
  }

  /** "" si el nombre sirve como carpeta de persona; si no, por qué. */
  function problemaNombre(nombre) {
    const n = String(nombre || "");
    if (!n.trim()) return "Escriba el nombre de la persona (será el nombre de su carpeta en firmas/).";
    if (n !== n.trim()) return "El nombre no puede empezar ni terminar con espacios.";
    if (!NOMBRE_VALIDO.test(n.normalize("NFC"))) {
      return "El nombre solo admite letras (con tildes y ñ), números, espacio, «_» y «-»: sin puntos, «/», «\\» ni «:».";
    }
    return "";
  }

  // ---------------------------------------------------------------------------------------
  // Todo junto.
  // ---------------------------------------------------------------------------------------

  /**
   * opciones: {recorte (rect o null), umbral, tinta, compensar (fondo local; por defecto sí)}.
   * Devuelve {png, ancho, alto, reducciones, revision, limpia (la imagen final, para la vista
   * previa), opacos (fracción), avisoFondo} o {error} si no queda trazo.
   */
  async function generar(img, opciones, deflate, archivo, donde) {
    let recortada = recortar(img, opciones.recorte || null);
    if (opciones.compensar !== false) recortada = compensarFondo(recortada);
    const limpia = recorteAlTrazo(limpiar(recortada, opciones.umbral, opciones.tinta), MARGEN_PX);
    if (!limpia) return { error: "No quedó ningún trazo: suba el umbral o revise el recorte." };
    let factor = 1;
    let reducciones = 0;
    for (;;) {
      const final = reducir(limpia, MAX_ANCHO_PX, MAX_ALTO_PX, factor);
      const png = await codificarPng(final, deflate);
      if (png.length <= MAX_BYTES || reducciones >= 12 || (final.ancho <= 16 && final.alto <= 16)) {
        const opacos = fraccionOpaca(limpia);
        return { png, ancho: final.ancho, alto: final.alto, reducciones, limpia: final, opacos,
          avisoFondo: avisoFondo(opacos), revision: revisarPng(png, archivo || "firma.png", donde || "firma") };
      }
      factor *= 0.85;
      reducciones++;
    }
  }

  return {
    MAX_ANCHO_PX,
    MAX_ALTO_PX,
    MAX_BYTES,
    SUAVIDAD,
    MARGEN_PX,
    UMBRAL_MIN,
    UMBRAL_MAX,
    LIMITE_OPACOS,
    imagen,
    luminosidad,
    luminosidades,
    bloqueFondo,
    estimarFondo,
    compensarFondo,
    umbralOtsu,
    umbralAutomatico,
    fraccionOpaca,
    avisoFondo,
    recortar,
    alfaPorLuminosidad,
    limpiar,
    cajaDelTrazo,
    recorteAlTrazo,
    tamanoReducido,
    reducir,
    crc32,
    codificarPng,
    leerCabeceraPng,
    revisarPng,
    avisoSinAlfa,
    problemaNombre,
    generar,
  };
});
