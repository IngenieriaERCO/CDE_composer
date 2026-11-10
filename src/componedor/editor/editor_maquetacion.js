/*
 * Editor de planos — MAQUETACIÓN de textos del rótulo (subfase 4.3e). Pura, sin pantalla:
 * funciona en el navegador (window.EditorMaquetacion) y en Node (module.exports).
 *
 * Es la copia en JavaScript de `maquetacion.py` (celdas: título, revisiones, firmas,
 * descripciones de convenciones) y de `notas.maquetar_notas` (notas numeradas con sangría
 * francesa y viñetas): las mismas líneas, las mismas alturas y los MISMOS textos de «no cabe»
 * y «se escribió a X mm» que `componer`. Las pruebas comparan las dos versiones.
 *
 * - Medir: ancho = suma de avances (tabla `anchos_em` de la fuente del editor) × tamaño en pt,
 *   igual que `Fuente.ancho_mm` (PyMuPDF no aplica kerning). La altura es la de las MAYÚSCULAS.
 *   Un carácter sin ancho en la tabla no se puede medir: `sinAncho` lo dice y el llamador avisa
 *   («componer lo comprobará»).
 * - Celda: {ruta, rect_mm: [x0, y0, x1, y1], alinear, altura_mm, altura_min_mm, lineas_max}
 *   (mm de papel, Y hacia arriba).
 * - Si no cabe se baja de 0,1 en 0,1 mm hasta `altura_min_mm`; si ni así: {problema: "..."}.
 * - Los números de los mensajes se escriben como en Python (`f"{v:.1f}"`: redondeo al par en
 *   los empates; `toFixed` de JavaScript los sube), y los espacios son los de `str.split()`.
 *
 * El editor es una ayuda: `componer` vuelve a maquetar y a validar todo.
 */
(function (raiz, fabrica) {
  "use strict";
  const api = fabrica();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    raiz.EditorMaquetacion = api;
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const PASO_REDUCCION_MM = 0.1;
  const EPS_MM = 1e-6;
  const PT_POR_MM = 72 / 25.4;
  const SIGNO_VINETA = "•";

  // ---------------------------------------------------------------------------------------
  // Como Python: números con decimales, espacios y recortes.
  // ---------------------------------------------------------------------------------------

  /**
   * `f"{v:.{d}f}"` de Python. Las dos versiones redondean el valor exacto del número; solo
   * difieren en el empate exacto (p. ej. 0,25 con un decimal): Python va al dígito par («0.2»)
   * y `toFixed` al mayor («0.3»). Hay empate solo si v × 2^(d+1) es un entero impar.
   */
  function fmt(v, decimales) {
    const d = decimales === undefined ? 1 : decimales;
    const a = Math.abs(v);
    const t = a * Math.pow(2, d + 1);
    if (Number.isFinite(v) && Number.isInteger(t) && t % 2 === 1) {
      let n = Math.floor(a * Math.pow(10, d));
      if (n % 2 === 1) n += 1;
      return (v < 0 ? "-" : "") + (n / Math.pow(10, d)).toFixed(d);
    }
    return v.toFixed(d);
  }

  /** `round(v, d)` de Python (número). */
  function redondear(v, decimales) {
    return Number(fmt(v, decimales));
  }

  /** `int(round(v))` de Python: al entero más cercano; el empate, al par. */
  function redondearEntero(v) {
    const piso = Math.floor(v);
    const resto = v - piso;
    if (resto === 0.5) return piso % 2 === 0 ? piso : piso + 1;
    return resto < 0.5 ? piso : piso + 1;
  }

  // Los caracteres que Python trata como espacio (str.isspace): no son los mismos que \s.
  const ESPACIOS = "\\t\\n\\x0b\\x0c\\r\\x1c-\\x1f \\x85\\xa0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000";
  const RE_SEPARAR = new RegExp("[" + ESPACIOS + "]+");
  const RE_RECORTAR = new RegExp("^[" + ESPACIOS + "]+|[" + ESPACIOS + "]+$", "g");

  /** `str.strip()` de Python. */
  function recortar(texto) {
    return String(texto).replace(RE_RECORTAR, "");
  }

  /** `str.split()` de Python: palabras separadas por cualquier espacio, sin vacías. */
  function palabras(texto) {
    const limpio = recortar(texto);
    return limpio === "" ? [] : limpio.split(RE_SEPARAR);
  }

  // ---------------------------------------------------------------------------------------
  // Medir con la tabla de anchos (como fuente.Fuente).
  // ---------------------------------------------------------------------------------------

  /** Tamaño de fuente (pt) para que las MAYÚSCULAS midan `altura` mm. */
  function tamanoPt(fuente, altura) {
    return (altura * PT_POR_MM) / fuente.altura_mayusculas;
  }

  /** Ancho del texto (mm) con mayúsculas de `altura` mm. NaN si algún carácter no tiene ancho. */
  function anchoMm(fuente, texto, altura) {
    const anchos = fuente.anchos_em;
    let suma = 0;
    for (const c of String(texto)) {
      if (!Object.prototype.hasOwnProperty.call(anchos, c)) return NaN;
      suma += anchos[c];
    }
    return (suma * tamanoPt(fuente, altura)) / PT_POR_MM;
  }

  /** Caracteres de `texto` que la tabla de anchos no trae (sin repetir, en orden). */
  function sinAncho(fuente, texto) {
    const faltan = [];
    for (const c of String(texto)) {
      if (!Object.prototype.hasOwnProperty.call(fuente.anchos_em, c) && !faltan.includes(c)) faltan.push(c);
    }
    return faltan;
  }

  // ---------------------------------------------------------------------------------------
  // Una celda (maquetacion.py).
  // ---------------------------------------------------------------------------------------

  /** altura, altura − 0,1, …, altura_min (redondeadas a 0,01 mm). */
  function alturasAProbar(celda) {
    const pasos = redondearEntero((celda.altura_mm - celda.altura_min_mm) / PASO_REDUCCION_MM);
    const alturas = [];
    for (let i = 0; i <= pasos; i++) alturas.push(redondear(celda.altura_mm - i * PASO_REDUCCION_MM, 2));
    if (alturas.length) alturas[alturas.length - 1] = celda.altura_min_mm;
    return alturas;
  }

  /**
   * Corta cada párrafo por palabras para que cada línea mida a lo sumo `ancho`. Una palabra más
   * ancha que la celda queda sola en su línea (y luego se informa).
   */
  function partirEnLineas(parrafos, ancho, altura, fuente) {
    const lineas = [];
    for (const parrafo of parrafos) {
      let actual = "";
      for (const palabra of palabras(parrafo)) {
        const candidata = actual ? actual + " " + palabra : palabra;
        if (actual && anchoMm(fuente, candidata, altura) > ancho + EPS_MM) {
          lineas.push(actual);
          actual = palabra;
        } else {
          actual = candidata;
        }
      }
      lineas.push(actual);
    }
    return lineas;
  }

  /** Párrafos de un contenido: una lista son líneas explícitas; un texto se parte por «\n». */
  function parrafosDe(contenido) {
    const partes = Array.isArray(contenido) ? contenido : String(contenido).split("\n");
    return partes.map(recortar);
  }

  /** Por qué no cabe a esta altura ("" si cabe). */
  function problemaCelda(celda, contenido, lineas, altura, anchoUtil, altoUtil, fuente, interlineado) {
    const campo = "campo '" + celda.ruta + "'";
    const medida = "altura " + fmt(altura) + " mm" + (celda.altura_min_mm < celda.altura_mm ? ", la mínima permitida" : "");
    if (lineas.length > celda.lineas_max) {
      const texto = lineas.join(Array.isArray(contenido) ? " | " : " ");
      return campo + ": «" + texto + "» necesita " + lineas.length + " líneas de hasta " + fmt(anchoUtil) +
        " mm y la celda permite " + celda.lineas_max + " (" + medida + ")";
    }
    for (let i = 0; i < lineas.length; i++) {
      const ancho = anchoMm(fuente, lineas[i], altura);
      if (ancho > anchoUtil + EPS_MM) {
        const donde = lineas.length > 1 ? ", línea " + (i + 1) : "";
        return campo + donde + ": «" + lineas[i] + "» mide " + fmt(ancho) + " mm y la celda permite " +
          fmt(anchoUtil) + " mm (" + medida + ")";
      }
    }
    const bloque = altura + (lineas.length - 1) * interlineado * altura;
    if (bloque > altoUtil + EPS_MM) {
      return campo + ": " + lineas.length + " líneas ocupan " + fmt(bloque) + " mm de alto y la celda permite " +
        fmt(altoUtil) + " mm (" + medida + ")";
    }
    return "";
  }

  /** Base (inicio de la línea base, mm de papel) y ancho de cada línea: bloque centrado en alto. */
  function colocar(celda, lineas, altura, fuente, relleno, interlineado) {
    const [x0, y0, x1, y1] = celda.rect_mm;
    const paso = interlineado * altura;
    const bloque = altura + (lineas.length - 1) * paso;
    const arriba = (y0 + y1) / 2 + bloque / 2;
    return lineas.map((texto, i) => {
      const ancho = anchoMm(fuente, texto, altura);
      let x;
      if (celda.alinear === "izq") x = x0 + relleno;
      else if (celda.alinear === "der") x = x1 - relleno - ancho;
      else x = (x0 + x1) / 2 - ancho / 2;
      return { texto, base_mm: [x, arriba - altura - i * paso], ancho_mm: ancho };
    });
  }

  /**
   * Acomoda `contenido` (texto, o lista de líneas explícitas) en `celda`. Devuelve
   * {ruta, lineas, altura_mm, reducido_desde, celda_mm}; si no cabe ni a la altura mínima,
   * {problema} (el texto de `TextoNoCabe`); si hay caracteres sin ancho, {sin_medir: [...]}.
   */
  function maquetar(celda, contenido, fuente, relleno, interlineado) {
    const explicitas = Array.isArray(contenido);
    const parrafos = parrafosDe(contenido);
    const rect = celda.rect_mm.slice();
    if (!parrafos.some((p) => p)) {
      return { ruta: celda.ruta, lineas: [], altura_mm: celda.altura_mm, reducido_desde: null, celda_mm: rect };
    }
    const partir = !explicitas && celda.lineas_max > 1;
    // Al partir por palabras, los espacios raros (tabulador...) se vuelven un espacio: no se miden.
    const faltan = sinAncho(fuente, (partir ? parrafos.map((p) => palabras(p).join(" ")) : parrafos).join(" "));
    if (faltan.length) return { sin_medir: faltan };
    const anchoUtil = rect[2] - rect[0] - 2 * relleno;
    const altoUtil = rect[3] - rect[1] - 2 * relleno;
    let problema = "";
    for (const altura of alturasAProbar(celda)) {
      const lineas = partir ? partirEnLineas(parrafos, anchoUtil, altura, fuente) : parrafos;
      problema = problemaCelda(celda, contenido, lineas, altura, anchoUtil, altoUtil, fuente, interlineado);
      if (!problema) {
        return {
          ruta: celda.ruta, lineas: colocar(celda, lineas, altura, fuente, relleno, interlineado),
          altura_mm: altura, reducido_desde: altura < celda.altura_mm - EPS_MM ? celda.altura_mm : null,
          celda_mm: rect,
        };
      }
    }
    return { problema };
  }

  /** La advertencia de `rotulo.preparar_rotulo` cuando una celda se escribe más pequeña. */
  function avisoReducido(maquetado) {
    return "Advertencia: en el rótulo, el campo '" + maquetado.ruta + "' se escribió a " + fmt(maquetado.altura_mm) +
      " mm de altura (pedida " + fmt(maquetado.reducido_desde) + " mm) para que quepa en su celda.";
  }

  // ---------------------------------------------------------------------------------------
  // Notas (notas.maquetar_notas): numeradas, sangría francesa, viñetas, pegadas arriba.
  // ---------------------------------------------------------------------------------------

  /** [{tipo: "nota" | "vineta", j, lineas}] de una nota a esa altura. */
  function partesNota(nota, fuente, altura, anchoTexto, anchoVineta) {
    const partes = [{ tipo: "nota", j: 0, lineas: partirEnLineas([nota.texto], anchoTexto, altura, fuente) }];
    (nota.vinetas || []).forEach((vineta, i) => {
      partes.push({ tipo: "vineta", j: i + 1, lineas: partirEnLineas([vineta], anchoTexto - anchoVineta, altura, fuente) });
    });
    return partes;
  }

  /** Las notas a una altura dada: {textos, lineas} o {problema}. */
  function notasAAltura(campo, notas, fuente, relleno, interlineado, altura) {
    const [x0, y0, x1, y1] = campo.rect_mm;
    const minima = campo.altura_min_mm < campo.altura_mm ? " (la mínima permitida)" : "";
    const sangria = anchoMm(fuente, notas.length + ". ", altura);
    const anchoTexto = (x1 - x0) - 2 * relleno - sangria;
    const anchoVineta = anchoMm(fuente, SIGNO_VINETA + " ", altura);
    const xTexto = x0 + relleno + sangria;
    const paso = interlineado * altura;
    const tope = y1 - relleno - altura;
    const piso = y0 + relleno;
    const todas = notas.map((n) => partesNota(n, fuente, altura, anchoTexto, anchoVineta));
    let total = 0;
    for (const partes of todas) for (const p of partes) total += p.lineas.length;

    let base = tope;
    const textos = [];
    for (let k = 1; k <= notas.length; k++) {
      const nota = notas[k - 1];
      const colocadas = [{ texto: k + ".", base_mm: [x0 + relleno, base], ancho_mm: anchoMm(fuente, k + ".", altura) }];
      for (const { tipo, j, lineas } of todas[k - 1]) {
        const x = tipo === "nota" ? xTexto : xTexto + anchoVineta;
        const disponible = tipo === "nota" ? anchoTexto : anchoTexto - anchoVineta;
        for (const linea of lineas) {
          const ancho = anchoMm(fuente, linea, altura);
          if (ancho > disponible + EPS_MM) {
            const que = "nota " + k + (tipo === "vineta" ? ", viñeta " + j : "");
            const de = tipo === "nota" ? "de las notas" : "de las viñetas";
            return { problema: "campo 'notas', " + que + " (" + nota.origen + "): «" + linea + "» mide " + fmt(ancho) +
              " mm y el ancho para el texto " + de + " es " + fmt(disponible) + " mm (altura " + fmt(altura) + " mm" + minima + ")" };
          }
        }
        if (base - (lineas.length - 1) * paso < piso - EPS_MM) {
          const ocupado = (y1 - relleno) - (tope - (total - 1) * paso - (notas.length - 1) * campo.separacion_notas * paso);
          return { problema: "campo 'notas': " + notas.length + " notas (" + total + " líneas a " + fmt(altura) + " mm" +
            minima + ") ocupan " + fmt(ocupado) + " mm de alto y la celda permite " + fmt((y1 - y0) - 2 * relleno) +
            " mm; no caben desde la nota " + k + " (" + nota.origen + "): «" + nota.texto + "»" };
        }
        if (tipo === "vineta") {
          colocadas.push({ texto: SIGNO_VINETA, base_mm: [xTexto, base], ancho_mm: anchoMm(fuente, SIGNO_VINETA, altura) });
        }
        lineas.forEach((linea, i) => {
          colocadas.push({ texto: linea, base_mm: [x, base - i * paso], ancho_mm: anchoMm(fuente, linea, altura) });
        });
        base -= lineas.length * paso;
      }
      textos.push({ ruta: "notas." + k, lineas: colocadas, altura_mm: altura, reducido_desde: null, celda_mm: campo.rect_mm.slice() });
      base -= campo.separacion_notas * paso;
    }
    return { textos, lineas: total };
  }

  /**
   * Numera y acomoda las notas ({texto, vinetas, origen}) arriba de la celda de notas
   * (`campo`: el de la definición, con rect_mm, alturas y separacion_notas). Devuelve
   * {textos, altura_mm, reducido_desde, celda_mm, lineas}, {problema} o {sin_medir: [...]}.
   */
  function maquetarNotas(campo, notas, fuente, relleno, interlineado) {
    const rect = campo.rect_mm.slice();
    if (!notas.length) return { textos: [], altura_mm: campo.altura_mm, reducido_desde: null, celda_mm: rect, lineas: 0 };
    const todo = notas.map((n) => [n.texto].concat(n.vinetas || []).join(" ")).join(" ") + " " + SIGNO_VINETA + " 0123456789.";
    const faltan = sinAncho(fuente, todo.replace(new RegExp("[" + ESPACIOS + "]", "g"), " "));
    if (faltan.length) return { sin_medir: faltan };
    let problema = "";
    for (const altura of alturasAProbar(campo)) {
      const r = notasAAltura(campo, notas, fuente, relleno, interlineado, altura);
      if (!r.problema) {
        return { textos: r.textos, altura_mm: altura, reducido_desde: altura < campo.altura_mm - EPS_MM ? campo.altura_mm : null,
          celda_mm: rect, lineas: r.lineas };
      }
      problema = r.problema;
    }
    return { problema };
  }

  /** La advertencia de `rotulo._notas` cuando las notas se escriben más pequeñas. */
  function avisoNotasReducidas(maquetadas) {
    return "Advertencia: en el rótulo, las notas se escribieron a " + fmt(maquetadas.altura_mm) + " mm de altura (pedida " +
      fmt(maquetadas.reducido_desde) + " mm) para que quepan en su celda.";
  }

  return {
    PASO_REDUCCION_MM, EPS_MM, SIGNO_VINETA,
    fmt, redondear, redondearEntero, recortar, palabras,
    tamanoPt, anchoMm, sinAncho,
    alturasAProbar, partirEnLineas, maquetar, avisoReducido,
    maquetarNotas, avisoNotasReducidas,
  };
});
