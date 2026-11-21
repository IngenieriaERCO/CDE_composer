/*
 * Editor de planos — lógica de los FORMULARIOS del rótulo (subfase 4.3b). Pura, sin pantalla:
 * funciona en el navegador (window.EditorFormularios) y en Node (module.exports).
 *
 * Validación: las MISMAS reglas y los MISMOS textos que `rotulo.py` (y `firmas.py` para el
 * nombre de una firma en imagen):
 *   - texto o entero; lista de líneas solo en celdas de varias líneas; sin salto de línea en
 *     una celda de una sola línea; caracteres que la fuente no tiene (`rangos_unicode`);
 *   - revisiones: letra válida y sin repetir, columnas conocidas;
 *   - firmas: filas y columnas conocidas; {"imagen": "<persona>[/<archivo>]"} solo en FIRMA.
 * Medir (4.3e): cada texto se maqueta con editor_maquetacion.js (copia de `maquetacion.py`):
 * si no cabe ni a la altura mínima, el error de `TextoNoCabe`; si se escribe más pequeño, la
 * advertencia de `rotulo.preparar_rotulo` («se escribió a X mm»), con los mismos textos. Sin
 * rectángulo de celda o sin tabla de anchos solo se revisa la cantidad de líneas a mano.
 *
 * Forma de los valores: el formulario respeta la que traía el plano (una lista de líneas sigue
 * siendo lista; un entero, entero si se escribe un entero). Un campo vacío se QUITA del plano
 * (vuelve su valor por defecto, p. ej. «DEFINIR»).
 *
 * REV. y ESCALA se calculan como en `rotulo.py` (solo lectura).
 */
(function (raiz, fabrica) {
  "use strict";
  const M = typeof module === "object" && module.exports ? require("./editor_maquetacion.js") : raiz.EditorMaquetacion;
  const api = fabrica(M);
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    raiz.EditorFormularios = api;
  }
})(typeof self !== "undefined" ? self : this, function (M) {
  "use strict";

  const esObjeto = (v) => v !== null && typeof v === "object" && !Array.isArray(v);
  const esEntero = (v) => typeof v === "number" && Number.isInteger(v);
  const clonar = (v) => (v === undefined ? undefined : JSON.parse(JSON.stringify(v)));
  const mm1 = (v) => v.toFixed(1);

  // Nombres para la pantalla; los demás campos se muestran con su clave.
  const ETIQUETAS = {
    titulo: "Título", no_plano: "No. PLANO", hoja: "HOJA", de: "DE",
    este: "Coordenada ESTE", norte: "Coordenada NORTE", localizacion_escala: "ESC. de localización",
    escala: "ESCALA", rev: "REV.",
  };
  const ETIQUETAS_COLUMNAS = {
    ver: "VER.", fecha: "Fecha", descripcion: "Descripción", dibujo: "Dibujó", diseno: "Diseñó",
    reviso: "Revisó", aprobo: "Aprobó", nombre: "Nombre", matricula: "Matrícula", firma: "Firma",
  };
  const ETIQUETAS_FILAS_FIRMAS = { dibujo: "DIBUJÓ", diseno: "DISEÑÓ", reviso: "REVISÓ", aprobo: "APROBÓ" };
  const TABLA_REVISIONES = "revisiones";
  const TABLA_FIRMAS = "firmas";
  const COLUMNA_FECHA = "fecha";
  const ESCALAS_DISTINTAS = "INDICADAS";
  // Como firmas.NOMBRE_VALIDO (\w de Python: letras con tildes y ñ, números, «_»).
  const NOMBRE_VALIDO = /^[\p{L}\p{M}\p{N}_-](?:[\p{L}\p{M}\p{N}_ -]*[\p{L}\p{M}\p{N}_-])?$/u;

  // ---------------------------------------------------------------------------------------
  // Textos como los de Python (repr y _tipo de rotulo.py).
  // ---------------------------------------------------------------------------------------

  function pyRepr(v) {
    if (v === null || v === undefined) return "None";
    if (v === true) return "True";
    if (v === false) return "False";
    if (typeof v === "string") {
      const comilla = v.includes("'") && !v.includes('"') ? '"' : "'";
      const escapado = v.replace(/\\/g, "\\\\").replace(/\n/g, "\\n").replace(/\r/g, "\\r")
        .replace(/\t/g, "\\t").split(comilla).join("\\" + comilla);
      return comilla + escapado + comilla;
    }
    if (typeof v === "number") return String(v);
    if (Array.isArray(v)) return "[" + v.map(pyRepr).join(", ") + "]";
    return "{" + Object.entries(v).map(([k, x]) => pyRepr(k) + ": " + pyRepr(x)).join(", ") + "}";
  }

  function tipo(v) {
    if (v === null || v === undefined) return "null";
    if (typeof v === "boolean") return "un booleano (" + v + ")";
    if (typeof v === "string") return "texto " + pyRepr(v);
    if (Array.isArray(v)) return "una lista";
    if (esObjeto(v)) return "un objeto";
    return (esEntero(v) ? "int " : "float ") + v;
  }

  // ---------------------------------------------------------------------------------------
  // Definición: qué campos tiene el formulario.
  // ---------------------------------------------------------------------------------------

  /**
   * Campos de texto que escribe el usuario (no calculados), en el orden del rótulo (ver
   * ordenarPorFilas). En A1 ERCO: ESC. de localización, ESTE, NORTE, Título, HOJA, DE, No. PLANO.
   */
  function camposSimples(definicion) {
    const campos = (definicion && definicion.campos) || {};
    const nombres = ordenarPorFilas(Object.keys(campos)
      .filter((n) => campos[n].tipo === "texto" && !campos[n].calculado), (n) => campos[n].rect_mm);
    return nombres.map((n) => ({ campo: n, etiqueta: ETIQUETAS[n] || n, celda: celdaTexto(n, campos[n]),
      por_defecto: campos[n].por_defecto || null }));
  }

  // Dos celdas están en la misma fila del rótulo si sus bordes superiores difieren en 1 mm o menos
  // (p. ej. FIRMAS y HOJA: 43,5 y 43,6 mm, medidas de la misma línea de la plantilla).
  const MISMA_FILA_MM = 1.0;

  /**
   * Orden del rótulo de ARRIBA hacia ABAJO: por el borde superior (Y mayor primero); los que están
   * en la misma fila (bordes superiores a ≤ 1 mm del primero de la fila), de izquierda a derecha.
   * `rectDe(item)` → [x0, y0, x1, y1] en mm de papel. Sale del formato: si una celda se mueve,
   * cambia el orden.
   */
  function ordenarPorFilas(items, rectDe) {
    const conRect = items.map((it) => ({ it, r: rectDe(it) }));
    conRect.sort((a, b) => b.r[3] - a.r[3] || a.r[0] - b.r[0]);
    const filas = [];
    for (const x of conRect) {
      const fila = filas[filas.length - 1];
      if (fila && fila[0].r[3] - x.r[3] <= MISMA_FILA_MM) fila.push(x);
      else filas.push([x]);
    }
    return filas.flatMap((fila) => fila.sort((a, b) => a.r[0] - b.r[0] || b.r[3] - a.r[3]).map((x) => x.it));
  }

  /** El recuadro [x0, y0, x1, y1] (mm) de un campo de la definición del rótulo, de cualquier tipo. */
  function cajaCampo(campo) {
    if (campo.rect_mm) return campo.rect_mm.slice();
    const rects = [];
    if (campo.filas && campo.columnas) { // tabla
      for (const f of campo.filas) for (const c of campo.columnas) rects.push([c.x_mm[0], f.y_mm[0], c.x_mm[1], f.y_mm[1]]);
    }
    for (const r of campo.simbolos || []) rects.push(r); // convenciones
    for (const d of campo.descripciones || []) rects.push(d.rect_mm);
    if (!rects.length) return null;
    return [Math.min(...rects.map((r) => r[0])), Math.min(...rects.map((r) => r[1])),
      Math.max(...rects.map((r) => r[2])), Math.max(...rects.map((r) => r[3]))];
  }

  /**
   * TODO el formulario del rótulo en el orden del rótulo, de arriba hacia abajo: cada campo de la
   * definición (texto, calculado o no; imagen; notas; convenciones; tablas) con su recuadro. En A1
   * ERCO: imagen de localización, ESC. de localización, ESTE, NORTE, notas, convenciones,
   * revisiones, título, firmas, HOJA, DE, ESCALA, No. PLANO, REV. [{campo, tipo, calculado, rect_mm}].
   */
  function bloquesRotulo(definicion) {
    const campos = (definicion && definicion.campos) || {};
    const lista = Object.keys(campos).map((n) => ({ campo: n, tipo: campos[n].tipo,
      calculado: !!campos[n].calculado, rect_mm: cajaCampo(campos[n]) })).filter((b) => b.rect_mm);
    return ordenarPorFilas(lista, (b) => b.rect_mm);
  }

  function celdaTexto(nombre, campo) {
    return { ruta: nombre, ancho_mm: campo.rect_mm[2] - campo.rect_mm[0], altura_mm: campo.altura_mm,
      altura_min_mm: campo.altura_min_mm, lineas_max: campo.lineas_max, rect_mm: campo.rect_mm.slice(),
      alinear: campo.alinear };
  }

  /** Celda (fila, columna) de una tabla de la definición. */
  function celdaTabla(definicion, tabla, fila, columna) {
    const t = definicion.campos[tabla];
    const f = t.filas.find((x) => x.clave === fila);
    const c = t.columnas.find((x) => x.clave === columna);
    return { ruta: tabla + "." + fila + "." + columna, ancho_mm: c.x_mm[1] - c.x_mm[0],
      altura_mm: t.altura_mm, altura_min_mm: t.altura_min_mm, lineas_max: f.lineas_max,
      acepta_imagen: !!c.acepta_imagen, rect_mm: [c.x_mm[0], f.y_mm[0], c.x_mm[1], f.y_mm[1]],
      alinear: c.alinear };
  }

  function etiquetaColumna(clave) {
    return ETIQUETAS_COLUMNAS[clave] || clave;
  }

  function etiquetaFilaFirma(clave) {
    return ETIQUETAS_FILAS_FIRMAS[clave] || clave;
  }

  // ---------------------------------------------------------------------------------------
  // Valor JSON <-> texto del formulario.
  // ---------------------------------------------------------------------------------------

  /** ¿El formulario sabe mostrar este valor de texto? (texto, entero, lista de textos o nada) */
  function representable(v) {
    return v === undefined || v === null || typeof v === "string" || esEntero(v) ||
      (Array.isArray(v) && v.every((x) => typeof x === "string" && !x.includes("\n")));
  }

  /** Lo que se muestra en el formulario: una lista de líneas va una por renglón. */
  function textoDeValor(v) {
    if (v === undefined || v === null) return "";
    if (Array.isArray(v)) return v.join("\n");
    return String(v);
  }

  /**
   * Valor para guardar a partir del texto del formulario. Vacío -> undefined (se quita).
   * Respeta la forma anterior: lista si era lista; entero si era entero y se escribe un entero.
   */
  function valorDeTexto(texto, anterior) {
    const limpio = String(texto).replace(/\r\n?/g, "\n");
    if (!limpio.trim()) return undefined;
    if (Array.isArray(anterior)) return limpio.split("\n");
    if (esEntero(anterior) && /^-?\d+$/.test(limpio.trim())) return Number(limpio.trim());
    return limpio;
  }

  // ---------------------------------------------------------------------------------------
  // Validación de un valor de texto (rotulo._contenido + caracteres de la fuente).
  // ---------------------------------------------------------------------------------------

  /** Problemas de forma (mismos textos que rotulo._contenido). `sitio`: "rotulo.titulo". */
  function problemasContenido(valor, sitio, lineasMax) {
    if (valor === null || valor === undefined || esEntero(valor)) return [];
    if (typeof valor === "string") {
      return valor.includes("\n") && lineasMax === 1
        ? [sitio + ": la celda es de una sola línea y el texto trae un salto de línea"] : [];
    }
    if (Array.isArray(valor) && lineasMax > 1) {
      if (valor.every((v) => typeof v === "string" && !v.includes("\n"))) return [];
      return [sitio + ": se esperaba una lista de líneas de texto; tiene " + pyRepr(valor)];
    }
    const permitido = lineasMax > 1 ? "un texto o una lista de líneas" : "un texto";
    return [sitio + ": se esperaba " + permitido + "; tiene " + tipo(valor)];
  }

  /** ¿La fuente tiene el carácter? (rangos_unicode: [[desde, hasta], ...], ordenados) */
  function fuenteTiene(fuente, c) {
    const cp = c.codePointAt(0);
    const rangos = fuente.rangos_unicode;
    let bajo = 0;
    let alto = rangos.length - 1;
    while (bajo <= alto) {
      const medio = (bajo + alto) >> 1;
      if (cp < rangos[medio][0]) alto = medio - 1;
      else if (cp > rangos[medio][1]) bajo = medio + 1;
      else return true;
    }
    return false;
  }

  /**
   * Caracteres de `texto` que la fuente no tiene (`faltan`, sin repetir, en orden), como
   * Fuente.caracteres_faltantes: los espacios no cuentan. Sin `rangos_unicode` (datos de un
   * editor anterior) no se puede saber: van en `desconocidos` los que no están en la tabla.
   */
  function caracteresFaltantes(texto, fuente) {
    const faltan = [];
    const desconocidos = [];
    if (!fuente) return { faltan, desconocidos };
    for (const c of String(texto)) {
      if (/\s/u.test(c)) continue;
      if (Array.isArray(fuente.rangos_unicode)) {
        if (!fuenteTiene(fuente, c) && !faltan.includes(c)) faltan.push(c);
      } else if (!Object.prototype.hasOwnProperty.call(fuente.anchos_em, c) && !desconocidos.includes(c)) {
        desconocidos.push(c);
      }
    }
    return { faltan, desconocidos };
  }

  /**
   * {errores, avisos} de un valor de texto en `celda`. `sitio`: dónde está en el plano
   * ("rotulo.revisiones[0].fecha"); la celda trae su `ruta` ("revisiones.A.fecha"), que es lo
   * que nombra Python en los problemas de fuente y de tamaño. `interlineado`: el de la
   * definición (para medir el alto de varias líneas).
   */
  function validarTexto(valor, celda, sitio, fuente, relleno, interlineado) {
    const errores = problemasContenido(valor, sitio, celda.lineas_max);
    const avisos = [];
    if (errores.length || valor === undefined || valor === null) return { errores, avisos };
    const texto = Array.isArray(valor) ? valor.join(" ") : String(valor);
    const { faltan, desconocidos } = caracteresFaltantes(texto, fuente);
    if (faltan.length) {
      errores.push("campo '" + celda.ruta + "': la fuente " + fuente.nombre + " no tiene los caracteres " +
        faltan.map(pyRepr).join(" "));
      return { errores, avisos };
    }
    if (desconocidos.length) {
      avisos.push("campo '" + celda.ruta + "': el editor no sabe si la fuente tiene los caracteres " +
        desconocidos.map(pyRepr).join(" ") + "; componer lo comprobará");
    }
    if (M && Array.isArray(celda.rect_mm) && fuente.anchos_em && typeof interlineado === "number") {
      const m = M.maquetar(celda, esEntero(valor) ? String(valor) : valor, fuente, relleno || 0, interlineado);
      if (m.problema) errores.push(m.problema);
      else if (m.sin_medir) avisos.push(avisoSinMedir(celda.ruta, m.sin_medir));
      else if (m.reducido_desde !== null) avisos.push(M.avisoReducido(m));
      return { errores, avisos };
    }
    // Sin medir: líneas explícitas de más no caben a ninguna altura (mismo texto que maquetacion.py).
    if (Array.isArray(valor) && valor.length > celda.lineas_max) {
      const util = celda.ancho_mm - 2 * (relleno || 0);
      const minima = celda.altura_min_mm < celda.altura_mm ? ", la mínima permitida" : "";
      errores.push("campo '" + celda.ruta + "': «" + valor.map((l) => l.trim()).join(" | ") + "» necesita " +
        valor.length + " líneas de hasta " + mm1(util) + " mm y la celda permite " + celda.lineas_max +
        " (altura " + mm1(celda.altura_min_mm) + " mm" + minima + ")");
    }
    return { errores, avisos };
  }

  /**
   * ¿El mensaje (error o aviso) es de uno de esos campos? (4.3e) `claves`: como las marca el
   * panel: "rotulo.titulo" (forma del valor), "campo 'titulo'" (fuente y tamaño: «campo
   * 'titulo': …», «campo 'titulo', línea 2: …» y la advertencia «… el campo 'titulo' se
   * escribió a …») o "rotulo.firmas.dibujo:" (terminada en «:», solo ese prefijo).
   */
  function mensajeDeCampo(mensaje, claves) {
    return claves.some((k) => (k.endsWith(":") ? mensaje.startsWith(k)
      : mensaje.startsWith(k + ":") || mensaje.startsWith(k + ".") || mensaje.startsWith(k + ",") ||
        mensaje.includes(" el " + k + " se escribió a ")));
  }

  /** {errores, avisos} de una validación que son de esos campos (mismo orden). */
  function mensajesDeCampo(validacion, claves) {
    return { errores: validacion.errores.filter((e) => mensajeDeCampo(e, claves)),
      avisos: validacion.avisos.filter((a) => mensajeDeCampo(a, claves)) };
  }

  /** Aviso propio del editor: un carácter que la tabla de anchos no trae no se puede medir. */
  function avisoSinMedir(ruta, caracteres) {
    return "campo '" + ruta + "': el editor no puede medir los caracteres " + caracteres.map(pyRepr).join(" ") +
      "; componer dirá si el texto cabe";
  }

  // ---------------------------------------------------------------------------------------
  // Fechas: el selector escribe en `formato_fecha` (p. ej. "dd/mm/aa").
  // ---------------------------------------------------------------------------------------

  const FORMATO_FECHA = /^(dd|mm|aa|aaaa)([/.-])(dd|mm|aa|aaaa)\2(dd|mm|aa|aaaa)$/;

  function partesFormato(formato) {
    const m = FORMATO_FECHA.exec(formato || "");
    return m ? { piezas: [m[1], m[3], m[4]], separador: m[2] } : null;
  }

  /** "2026-11-09" -> "09/11/26" con "dd/mm/aa". "" si la fecha no es válida. */
  function formatearFecha(iso, formato) {
    const p = partesFormato(formato);
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || "");
    if (!p || !m) return "";
    const valores = { dd: m[3], mm: m[2], aaaa: m[1], aa: m[1].slice(2) };
    return p.piezas.map((x) => valores[x]).join(p.separador);
  }

  /** "09/11/26" -> "2026-11-09" (para abrir el selector en esa fecha). "" si no se entiende. */
  function fechaIso(texto, formato) {
    const p = partesFormato(formato);
    if (!p || typeof texto !== "string") return "";
    const trozos = texto.trim().split(p.separador);
    if (trozos.length !== 3) return "";
    const v = {};
    for (let i = 0; i < 3; i++) {
      const largo = p.piezas[i] === "aaaa" ? 4 : 2;
      if (!new RegExp("^\\d{" + largo + "}$").test(trozos[i])) return "";
      v[p.piezas[i]] = trozos[i];
    }
    const anio = v.aaaa || "20" + v.aa;
    const fecha = new Date(Date.UTC(Number(anio), Number(v.mm) - 1, Number(v.dd)));
    if (fecha.getUTCFullYear() !== Number(anio) || fecha.getUTCMonth() !== Number(v.mm) - 1 ||
        fecha.getUTCDate() !== Number(v.dd)) return "";
    return anio + "-" + v.mm + "-" + v.dd;
  }

  /** Fecha de hoy en ISO (hora local), para el botón «Hoy». */
  function hoyIso(ahora) {
    const d = ahora || new Date();
    const dos = (n) => String(n).padStart(2, "0");
    return d.getFullYear() + "-" + dos(d.getMonth() + 1) + "-" + dos(d.getDate());
  }

  // ---------------------------------------------------------------------------------------
  // Calculados (solo lectura): REV. y ESCALA, como rotulo.py.
  // ---------------------------------------------------------------------------------------

  /** Letras válidas y no repetidas de la lista de revisiones (las que cuenta Python). */
  function letrasValidas(lista, tabla) {
    const filas = tabla.filas.map((f) => f.clave);
    const vistas = [];
    for (const item of Array.isArray(lista) ? lista : []) {
      if (!esObjeto(item)) continue;
      let letra = item[tabla.columna_clave];
      if (esEntero(letra)) letra = String(letra);
      if (filas.includes(letra) && !vistas.includes(letra)) vistas.push(letra);
    }
    return vistas;
  }

  /** REV.: la letra de mayor `orden` entre las llenas (A1 ERCO: 0 si existe; si no C, B, A). */
  function ultimaRevision(letras, orden) {
    const presentes = orden.filter((l) => letras.includes(l));
    return presentes.length ? presentes[presentes.length - 1] : "";
  }

  /** 1000 -> "1.000"; 12.5 -> "12,5" (texto_escala.numero_con_miles). */
  function numeroConMiles(n) {
    const miles = (e) => String(e).replace(/\B(?=(\d{3})+(?!\d))/g, ".");
    if (Math.abs(n - Math.round(n)) < 1e-9) return miles(Math.round(n));
    const [entero, decimales] = n.toFixed(4).replace(/0+$/, "").split(".");
    return miles(Number(entero)) + "," + decimales;
  }

  function escalaComun(escalas) {
    const distintas = Array.from(new Set(escalas)).sort((a, b) => a - b);
    if (!distintas.length) return "";
    return distintas.length === 1 ? "1:" + numeroConMiles(distintas[0]) : ESCALAS_DISTINTAS;
  }

  // ---------------------------------------------------------------------------------------
  // Revisiones: lista de {ver, fecha, ...}; cada una va en la fila de SU letra.
  // ---------------------------------------------------------------------------------------

  /** ¿El formulario sabe mostrar esta lista? (lista de objetos con textos representables) */
  function revisionesRepresentables(lista) {
    if (lista === undefined) return true;
    return Array.isArray(lista) && lista.every((item) => esObjeto(item) &&
      Object.values(item).every(representable));
  }

  /** Letras que puede tomar la revisión `i` (las de la tabla, sin las usadas por otras). */
  function letrasLibres(lista, tabla, i) {
    const usadas = (lista || []).filter((x, k) => k !== i && esObjeto(x))
      .map((x) => (esEntero(x[tabla.columna_clave]) ? String(x[tabla.columna_clave]) : x[tabla.columna_clave]));
    return tabla.orden.filter((l) => !usadas.includes(l));
  }

  /**
   * Posiciones de la lista en el orden en que se ven en el rótulo: de arriba abajo, el `orden`
   * al revés (A1 ERCO: 0, C, B, A). Las revisiones con letra no válida o repetida, al final, en
   * su orden de llegada. Solo para mostrar: la lista del plano no se reordena.
   */
  function ordenRotulo(lista, tabla) {
    const arriba = tabla.orden.slice().reverse();
    const vistas = new Set();
    const clave = (i) => {
      const item = lista[i];
      let letra = esObjeto(item) ? item[tabla.columna_clave] : undefined;
      if (esEntero(letra)) letra = String(letra);
      const k = arriba.indexOf(letra);
      if (k < 0 || vistas.has(letra)) return arriba.length + i;
      vistas.add(letra);
      return k;
    };
    const claves = (lista || []).map((x, i) => clave(i));
    return claves.map((k, i) => i).sort((a, b) => claves[a] - claves[b] || a - b);
  }

  /** Lista con una revisión nueva (la primera letra libre según el orden). null si no hay letra. */
  function agregarRevision(lista, tabla) {
    const libres = letrasLibres(lista, tabla, -1);
    if (!libres.length) return null;
    const nueva = {};
    nueva[tabla.columna_clave] = libres[0];
    return (lista || []).map(clonar).concat([nueva]);
  }

  /** Lista con la celda cambiada (undefined la quita); las demás claves, en su orden. */
  function cambiarCeldaRevision(lista, i, columna, valor) {
    const nueva = lista.map(clonar);
    const item = Object.assign({}, nueva[i]);
    if (valor === undefined) delete item[columna];
    else item[columna] = clonar(valor);
    nueva[i] = item;
    return nueva;
  }

  function quitarRevision(lista, i) {
    return lista.filter((x, k) => k !== i).map(clonar);
  }

  /** Para guardar: lista vacía -> undefined (se quita "revisiones"). */
  function revisionesParaGuardar(lista) {
    return Array.isArray(lista) && lista.length ? lista : undefined;
  }

  /** {errores, avisos} de "revisiones" (mismos textos que rotulo._tabla). */
  function validarRevisiones(valor, definicion, fuente) {
    const errores = [];
    const avisos = [];
    const tabla = definicion.campos[TABLA_REVISIONES];
    if (valor === undefined || valor === null || !tabla) return { errores, avisos };
    const donde = "rotulo." + TABLA_REVISIONES;
    const clave = tabla.columna_clave;
    if (!Array.isArray(valor)) {
      errores.push(donde + ": se esperaba una lista de objetos {\"" + clave + "\": ..., ...}; tiene " + tipo(valor));
      return { errores, avisos };
    }
    const filas = tabla.filas.map((f) => f.clave);
    const columnas = tabla.columnas.map((c) => c.clave);
    const vistas = {};
    valor.forEach((item, i) => {
      const sitio = donde + "[" + i + "]";
      if (!esObjeto(item)) {
        errores.push(sitio + ": se esperaba un objeto {...}; tiene " + tipo(item));
        return;
      }
      let letra = item[clave];
      if (esEntero(letra)) letra = String(letra);
      if (!filas.includes(letra)) {
        errores.push(sitio + "." + clave + ": se esperaba una de " + tabla.orden.join(", ") + "; tiene " + tipo(letra));
        return;
      }
      if (letra in vistas) {
        errores.push(sitio + "." + clave + ": la revisión '" + letra + "' está repetida (ya está en " +
          donde + "[" + vistas[letra] + "])");
        return;
      }
      vistas[letra] = i;
      for (const k of Object.keys(item).filter((k) => !columnas.includes(k)).sort()) {
        errores.push(sitio + "." + k + ": campo no reconocido (campos válidos: " + columnas.join(", ") + ")");
      }
      for (const col of columnas) {
        if (!(col in item)) continue;
        const v = col === clave ? letra : item[col];
        const r = validarTexto(v, celdaTabla(definicion, TABLA_REVISIONES, letra, col), sitio + "." + col,
          fuente, definicion.relleno_mm, definicion.interlineado);
        errores.push(...r.errores);
        avisos.push(...r.avisos);
      }
    });
    return { errores, avisos };
  }

  // ---------------------------------------------------------------------------------------
  // Firmas: {"<fila>": {"nombre", "matricula", "firma", "fecha"}}; la firma es texto o
  // {"imagen": "<persona>"} (de la lista de --firmas).
  // ---------------------------------------------------------------------------------------

  function esFirmaImagen(v) {
    return esObjeto(v) && typeof v.imagen === "string";
  }

  /** ¿El formulario sabe mostrar "firmas"? (objeto de filas con objetos de valores) */
  function firmasRepresentables(valor, definicion) {
    if (valor === undefined) return true;
    if (!esObjeto(valor)) return false;
    const tabla = definicion.campos[TABLA_FIRMAS];
    const imagen = new Set(tabla.columnas.filter((c) => c.acepta_imagen).map((c) => c.clave));
    return Object.values(valor).every((item) => item === null || item === undefined || (esObjeto(item) &&
      Object.entries(item).every(([col, v]) => representable(v) ||
        (imagen.has(col) && esFirmaImagen(v) && Object.keys(v).length === 1))));
  }

  /** "firmas" con la celda cambiada (undefined la quita; fila vacía y tabla vacía también). */
  function cambiarCeldaFirma(firmas, fila, columna, valor) {
    const nuevo = esObjeto(firmas) ? clonar(firmas) : {};
    const item = esObjeto(nuevo[fila]) ? nuevo[fila] : {};
    if (valor === undefined) delete item[columna];
    else item[columna] = clonar(valor);
    if (Object.keys(item).length) nuevo[fila] = item;
    else delete nuevo[fila];
    return Object.keys(nuevo).length ? nuevo : undefined;
  }

  /** {errores, avisos} de "firmas" (mismos textos que rotulo._tabla y firmas.pedir_firma). */
  function validarFirmas(valor, definicion, fuente, personas) {
    const errores = [];
    const avisos = [];
    const tabla = definicion.campos[TABLA_FIRMAS];
    if (valor === undefined || valor === null || !tabla) return { errores, avisos };
    const donde = "rotulo." + TABLA_FIRMAS;
    const filas = tabla.filas.map((f) => f.clave);
    const columnas = tabla.columnas.map((c) => c.clave);
    if (!esObjeto(valor)) {
      errores.push(donde + ": se esperaba un objeto con las filas (" + filas.join(", ") + "); tiene " + tipo(valor));
      return { errores, avisos };
    }
    for (const f of Object.keys(valor).filter((f) => !filas.includes(f)).sort()) {
      errores.push(donde + "." + f + ": fila no reconocida (filas válidas: " + filas.join(", ") + ")");
    }
    for (const fila of filas) {
      const item = valor[fila];
      if (item === undefined || item === null) continue;
      const sitio = donde + "." + fila;
      if (!esObjeto(item)) {
        errores.push(sitio + ": se esperaba un objeto con las columnas (" + columnas.join(", ") + "); tiene " + tipo(item));
        continue;
      }
      for (const k of Object.keys(item).filter((k) => !columnas.includes(k)).sort()) {
        errores.push(sitio + "." + k + ": campo no reconocido (campos válidos: " + columnas.join(", ") + ")");
      }
      for (const col of columnas) {
        if (!(col in item)) continue;
        const celda = celdaTabla(definicion, TABLA_FIRMAS, fila, col);
        if (esObjeto(item[col])) {
          const r = validarFirmaImagen(item[col], celda, sitio + "." + col, personas);
          errores.push(...r.errores);
          avisos.push(...r.avisos);
          continue;
        }
        const r = validarTexto(item[col], celda, sitio + "." + col, fuente, definicion.relleno_mm,
          definicion.interlineado);
        errores.push(...r.errores);
        avisos.push(...r.avisos);
      }
    }
    return { errores, avisos };
  }

  function validarFirmaImagen(valor, celda, donde, personas) {
    const errores = [];
    const avisos = [];
    if (!celda.acepta_imagen) {
      errores.push(donde + ": la celda '" + celda.ruta + "' no acepta imagen (solo texto); las firmas en " +
        "imagen van en la columna FIRMA");
      return { errores, avisos };
    }
    for (const k of Object.keys(valor).filter((k) => k !== "imagen").sort()) {
      errores.push(donde + "." + k + ": campo no reconocido (campos válidos: imagen)");
    }
    const ident = valor.imagen;
    const partes = typeof ident === "string" && ident && ident === ident.trim() && !/[\\:]/.test(ident) &&
      !ident.startsWith("/") ? ident.split("/") : null;
    if (!partes || partes.length > 2 || !partes.every((p) => NOMBRE_VALIDO.test(p.normalize("NFC")))) {
      errores.push(donde + ".imagen: se esperaba \"<persona>\" o \"<persona>/<archivo>\" (letras con tildes y ñ, " +
        "números, espacio, _ o -; sin «..», sin ruta absoluta y sin otros separadores; el archivo va sin .png); " +
        "tiene " + pyRepr(ident === undefined ? null : ident));
      return { errores, avisos };
    }
    if (Array.isArray(personas) && !personas.some((p) => mismaPersona(p, partes[0]))) {
      avisos.push(donde + ".imagen: '" + partes[0] + "' no está en la lista de firmas del editor; componer la " +
        "buscará en las carpetas de firmas del formato");
    }
    return { errores, avisos };
  }

  /** Como firmas._clave: tildes normalizadas y sin distinguir mayúsculas (Windows). */
  function mismaPersona(a, b) {
    return a.normalize("NFC").toLocaleLowerCase("es") === b.normalize("NFC").toLocaleLowerCase("es");
  }

  // ---------------------------------------------------------------------------------------
  // Todo el rótulo del formulario y el prellenado desde proyecto.json.
  // ---------------------------------------------------------------------------------------

  const EXPLICACIONES = {
    escala_comun: "la escala de los detalles, o INDICADAS si son distintas",
    ultima_revision: "0 si hay emisión final; si no, la mayor letra llena entre C, B y A",
  };

  /**
   * {errores, avisos} de lo que editan los formularios de la 4.3b: campos desconocidos,
   * campos simples, calculados escritos a mano, revisiones y firmas. `rotulo`: el objeto
   * "rotulo" que se guardaría (o undefined).
   */
  function validarRotulo(rotulo, definicion, fuente, personas) {
    const errores = [];
    const avisos = [];
    const valores = esObjeto(rotulo) ? rotulo : {};
    const valorDe = (campo) => valores[campo];
    const nombres = Object.keys(definicion.campos);
    // Campos que el rótulo ya no tiene (p. ej. disenador y revisor): no son error; un solo aviso,
    // con el mismo texto que componer (rotulo_formato.AVISO_CAMPOS_RETIRADOS).
    const retirados = definicion.campos_retirados || [];
    for (const clave of Object.keys(valores).filter((k) => !nombres.includes(k) && !retirados.includes(k)).sort()) {
      errores.push("rotulo." + clave + ": campo no reconocido (campos válidos: " + nombres.join(", ") + ")");
    }
    const aviso = avisoCamposRetirados(valores, definicion, "rotulo");
    if (aviso) avisos.push(aviso);
    for (const [nombre, campo] of Object.entries(definicion.campos)) {
      if (campo.tipo !== "texto") continue;
      const v = valorDe(nombre);
      if (campo.calculado) {
        if (v !== undefined) {
          errores.push("rotulo." + nombre + ": se calcula automáticamente (" +
            (EXPLICACIONES[campo.calculado] || campo.calculado) + "); no se escribe en el plano");
        }
        continue;
      }
      // Sin valor va el por defecto («DEFINIR»): Python también lo maqueta.
      const r = validarTexto(v === undefined && campo.por_defecto ? campo.por_defecto : v, celdaTexto(nombre, campo),
        "rotulo." + nombre, fuente, definicion.relleno_mm, definicion.interlineado);
      errores.push(...r.errores);
      avisos.push(...r.avisos);
    }
    for (const r of [validarRevisiones(valorDe(TABLA_REVISIONES), definicion, fuente),
      validarFirmas(valorDe(TABLA_FIRMAS), definicion, fuente, personas)]) {
      errores.push(...r.errores);
      avisos.push(...r.avisos);
    }
    return { errores, avisos };
  }

  /** El aviso de campos retirados presentes en `valores` (uno para todos), o null. */
  function avisoCamposRetirados(valores, definicion, prefijo) {
    if (!esObjeto(valores) || !definicion || !definicion.aviso_campos_retirados) return null;
    const presentes = (definicion.campos_retirados || []).filter((c) => Object.prototype.hasOwnProperty.call(valores, c));
    if (!presentes.length) return null;
    return definicion.aviso_campos_retirados.replace("{campos}", presentes.map((c) => prefijo + "." + c).join(", "));
  }

  /**
   * Valores que pone proyecto.json en un plano NUEVO: campo -> valor (diseñador, revisor,
   * No. PLANO = el prefijo, firmas con nombre y matrícula). Copias: el plano no depende del
   * proyecto.
   */
  function valoresProyecto(proyecto, definicion) {
    const valores = {};
    if (!esObjeto(proyecto) || !definicion) return valores;
    for (const campo of ["disenador", "revisor"]) {
      if (proyecto[campo] !== undefined && definicion.campos[campo]) valores[campo] = clonar(proyecto[campo]);
    }
    if (typeof proyecto.prefijo_no_plano === "string" && proyecto.prefijo_no_plano && definicion.campos.no_plano) {
      valores.no_plano = proyecto.prefijo_no_plano;
    }
    if (esObjeto(proyecto.firmas) && definicion.campos[TABLA_FIRMAS]) {
      const firmas = {};
      for (const fila of definicion.campos[TABLA_FIRMAS].filas.map((f) => f.clave)) {
        const item = proyecto.firmas[fila];
        if (!esObjeto(item)) continue;
        const copia = {};
        for (const col of ["nombre", "matricula"]) if (item[col] !== undefined) copia[col] = clonar(item[col]);
        if (Object.keys(copia).length) firmas[fila] = copia;
      }
      if (Object.keys(firmas).length) valores[TABLA_FIRMAS] = firmas;
    }
    return valores;
  }

  return {
    ETIQUETAS,
    TABLA_REVISIONES,
    TABLA_FIRMAS,
    COLUMNA_FECHA,
    pyRepr,
    tipo,
    camposSimples,
    ordenarPorFilas,
    cajaCampo,
    bloquesRotulo,
    celdaTexto,
    celdaTabla,
    etiquetaColumna,
    etiquetaFilaFirma,
    representable,
    textoDeValor,
    valorDeTexto,
    problemasContenido,
    fuenteTiene,
    caracteresFaltantes,
    validarTexto,
    avisoSinMedir,
    mensajeDeCampo,
    mensajesDeCampo,
    partesFormato,
    formatearFecha,
    fechaIso,
    hoyIso,
    letrasValidas,
    ultimaRevision,
    numeroConMiles,
    escalaComun,
    revisionesRepresentables,
    letrasLibres,
    ordenRotulo,
    agregarRevision,
    cambiarCeldaRevision,
    quitarRevision,
    revisionesParaGuardar,
    validarRevisiones,
    esFirmaImagen,
    firmasRepresentables,
    cambiarCeldaFirma,
    validarFirmas,
    validarFirmaImagen,
    mismaPersona,
    validarRotulo,
    avisoCamposRetirados,
    valoresProyecto,
  };
});
