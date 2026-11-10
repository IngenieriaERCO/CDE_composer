/*
 * Editor de planos — VISTA PREVIA del rótulo (subfase 4.3f). Pura, sin pantalla: funciona en el
 * navegador (window.EditorVistaPrevia) y en Node (module.exports), para compararla con Python.
 *
 * Dice QUÉ dibujaría `componer` y DÓNDE (mm de papel, Y hacia arriba), sin dibujar nada:
 * - `piezasRotulo`: los textos del rótulo (campos, revisiones, firmas en texto, descripciones
 *   de convenciones y notas numeradas), los símbolos de convenciones en su casilla y la caja de
 *   cada firma en imagen. Recorre los campos en el MISMO orden que `rotulo.preparar_rotulo`
 *   (descripciones de convenciones, tablas, campos de texto y al final las notas) y maqueta
 *   con editor_maquetacion.js (la copia de maquetacion.py y notas.maquetar_notas).
 * - `etiquetasEscala`: las etiquetas «ESC: 1:N» (copia de `etiquetas_escala.colocar_etiquetas`,
 *   con sus mismos avisos cuando una no cabe).
 * - `colocarSimbolo` (simbolos.colocar_simbolo) y `cajaFirma` (firmas.caja_firma).
 *
 * Diferencia a propósito con `componer`: Python rechaza TODO el rótulo si un campo tiene un
 * problema; la vista previa sigue con los demás y devuelve el campo en `problemas` (con su
 * celda, para marcarla en rojo) SIN dibujarlo. Lo que el editor no puede medir (un carácter sin
 * ancho en la tabla, un .txt fuera del catálogo) va en `problemas` con nivel "aviso".
 *
 * Las firmas en imagen nunca llegan al editor: solo se devuelve su caja y el nombre de la persona.
 * El editor es una ayuda: `componer` vuelve a maquetar y a validar todo.
 */
(function (raiz, fabrica) {
  "use strict";
  const enNode = typeof module === "object" && module.exports;
  const api = enNode
    ? fabrica(require("./editor_maquetacion.js"), require("./editor_formularios.js"), require("./editor_notas.js"))
    : fabrica(raiz.EditorMaquetacion, raiz.EditorFormularios, raiz.EditorNotas);
  if (enNode) {
    module.exports = api;
  } else {
    raiz.EditorVistaPrevia = api;
  }
})(typeof self !== "undefined" ? self : this, function (M, F, N) {
  "use strict";

  const EPS_MM = 1e-6;
  // etiquetas_escala.py
  const ALTURA_ETIQUETA_MM = 2.5;
  const SEPARACION_ETIQUETA_MM = 3.0;
  const PREFIJO_ETIQUETA = "ESC: ";

  const esObjeto = (v) => v !== null && typeof v === "object" && !Array.isArray(v);
  const esEntero = (v) => typeof v === "number" && Number.isInteger(v);
  /** `f"{v:g}"` de Python para los números de los avisos (3.0 -> «3», 2.5 -> «2.5»). */
  const pyG = (v) => String(Number(v.toPrecision(6)));

  // ---------------------------------------------------------------------------------------
  // Símbolos y firmas (copias de simbolos.colocar_simbolo y firmas.caja_firma).
  // ---------------------------------------------------------------------------------------

  /**
   * El símbolo centrado en su casilla y, si no cabe en el espacio útil, reducido (nunca
   * agrandado). `tamano`: [ancho, alto] del dibujo en mm. Devuelve {posicion, casilla, escala,
   * pagina_mm (dibujo + margen: donde va su imagen), dibujo_mm}.
   */
  function colocarSimbolo(tamano, posicion, casilla, relleno, margen) {
    const [ancho, alto] = tamano;
    const utilX = casilla[2] - casilla[0] - 2 * relleno;
    const utilY = casilla[3] - casilla[1] - 2 * relleno;
    const f = Math.min(1.0, ancho > 0 ? utilX / ancho : 1.0, alto > 0 ? utilY / alto : 1.0);
    const cx = (casilla[0] + casilla[2]) / 2;
    const cy = (casilla[1] + casilla[3]) / 2;
    const dibujo = [cx - ancho * f / 2, cy - alto * f / 2, cx + ancho * f / 2, cy + alto * f / 2];
    const m = margen * f;
    const pagina = [dibujo[0] - m, dibujo[1] - m, dibujo[2] + m, dibujo[3] + m];
    return { posicion, casilla: casilla.slice(), escala: f, pagina_mm: pagina, dibujo_mm: dibujo };
  }

  /**
   * Dónde puede ir la firma (firmas.caja_firma): el ancho de la celda menos el relleno y, con
   * `altoMax`, un alto de max(altoMax, alto útil de su fila) centrado en la fila y corrido hacia
   * adentro del cuerpo de la tabla (`cuerpoY`: [abajo, arriba]) si se saldría.
   */
  function cajaFirma(rect, altoMax, cuerpoY, relleno) {
    const [x0, y0, x1, y1] = rect;
    const r = relleno;
    if (!(altoMax > 0) || !cuerpoY) return [x0 + r, y0 + r, x1 - r, y1 - r];
    const abajo = cuerpoY[0] + r;
    const arriba = cuerpoY[1] - r;
    const alto = Math.min(Math.max(altoMax, (y1 - y0) - 2 * r), arriba - abajo);
    const cy = (y0 + y1) / 2;
    let inferior = cy - alto / 2;
    let superior = cy + alto / 2;
    if (superior > arriba) {
      inferior = arriba - alto;
      superior = arriba;
    }
    if (inferior < abajo) {
      inferior = abajo;
      superior = abajo + alto;
    }
    return [x0 + r, inferior, x1 - r, superior];
  }

  // ---------------------------------------------------------------------------------------
  // Rótulo.
  // ---------------------------------------------------------------------------------------

  /** rotulo._contenido: {contenido} (texto o lista de líneas) o {error}. null = vacío. */
  function contenido(valor, sitio, lineasMax) {
    const errores = F.problemasContenido(valor, sitio, lineasMax);
    if (errores.length) return { error: errores[0] };
    if (valor === null || valor === undefined) return { contenido: "" };
    if (esEntero(valor)) return { contenido: String(valor) };
    return { contenido: Array.isArray(valor) ? valor.slice() : valor };
  }

  const union = (a, b) => [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[2], b[2]), Math.max(a[3], b[3])];

  function camposDeTipo(definicion, tipo) {
    return Object.entries(definicion.campos).filter(([, c]) => c.tipo === tipo).map(([nombre, c]) => Object.assign({ nombre }, c));
  }

  /** Celdas (fila, columna) de una tabla llena, en el orden del formato (rotulo._tabla). */
  function celdasDeTabla(definicion, tabla, valor) {
    const salida = []; // {celda, valor, sitio, columna}
    if (valor === undefined || valor === null) return salida;
    const filas = new Map();
    const claves = tabla.filas.map((f) => f.clave);
    if (tabla.columna_clave) {
      if (!Array.isArray(valor)) return salida;
      for (const item of valor) {
        if (!esObjeto(item)) continue;
        let letra = item[tabla.columna_clave];
        if (esEntero(letra)) letra = String(letra);
        if (!claves.includes(letra) || filas.has(letra)) continue;
        const i = valor.indexOf(item);
        filas.set(letra, { item: Object.assign({}, item, { [tabla.columna_clave]: letra }), sitio: "rotulo." + tabla.nombre + "[" + i + "]" });
      }
    } else {
      if (!esObjeto(valor)) return salida;
      for (const fila of claves) {
        if (!esObjeto(valor[fila])) continue;
        filas.set(fila, { item: valor[fila], sitio: "rotulo." + tabla.nombre + "." + fila });
      }
    }
    for (const fila of claves) {
      if (!filas.has(fila)) continue;
      const { item, sitio } = filas.get(fila);
      for (const col of tabla.columnas) {
        if (!(col.clave in item)) continue;
        salida.push({ celda: F.celdaTabla(definicion, tabla.nombre, fila, col.clave), valor: item[col.clave],
          sitio: sitio + "." + col.clave, columna: col });
      }
    }
    return salida;
  }

  /**
   * Todo lo que `componer` dibujaría en el rótulo con estos valores. Entrada:
   * {rotulo (el objeto "rotulo" del plano), definicion, fuente (tabla de anchos), simbolos (los
   * del editor: id, descripcion, tamano_dibujo_mm, margen_mm), catalogo (de notas), escalas}.
   * Devuelve {textos: [{ruta, lineas: [{texto, base_mm, ancho_mm}], altura_mm, celda_mm}],
   * simbolos: [{id, posicion, casilla, escala, pagina_mm, dibujo_mm}], firmas: [{ruta, persona,
   * imagen, caja_mm, celda_mm}], problemas: [{ruta, rect_mm, nivel: "error"|"aviso", mensaje}]}.
   */
  function piezasRotulo(entrada) {
    const definicion = entrada.definicion;
    const fuente = entrada.fuente;
    const valores = esObjeto(entrada.rotulo) ? entrada.rotulo : {};
    const relleno = definicion.relleno_mm;
    const interlineado = definicion.interlineado;
    const textos = [];
    const simbolos = [];
    const firmas = [];
    const problemas = [];
    const contenidos = []; // {celda, contenido}
    const problema = (ruta, rect, nivel, mensaje) => problemas.push({ ruta, rect_mm: rect ? rect.slice() : null, nivel, mensaje });

    // 1. Convenciones: símbolo en su casilla y la descripción como un texto más.
    for (const campo of camposDeTipo(definicion, "convenciones")) {
      const valor = valores[campo.nombre];
      if (!Array.isArray(valor) || !valor.length) continue;
      const porId = new Map((entrada.simbolos || []).map((s) => [s.id, s]));
      const vistos = new Set();
      valor.forEach((item, i) => {
        if (i >= campo.capacidad || !esObjeto(item)) return;
        const casilla = campo.simbolos[i];
        const d = campo.descripciones[i];
        const celda = { ruta: campo.nombre + "." + (i + 1) + ".descripcion", rect_mm: d.rect_mm.slice(), alinear: d.alinear,
          altura_mm: d.altura_mm, altura_min_mm: d.altura_min_mm, lineas_max: d.lineas_max };
        const s = porId.get(item.simbolo);
        if (!s || vistos.has(item.simbolo)) {
          problema(celda.ruta, union(casilla, d.rect_mm), "error",
            s ? "el símbolo '" + item.simbolo + "' está repetido" : "el símbolo " + F.tipo(item.simbolo) + " no está en la biblioteca");
          return;
        }
        vistos.add(item.simbolo);
        if ("descripcion" in item) {
          const c = contenido(item.descripcion, "rotulo." + campo.nombre + "[" + i + "].descripcion", d.lineas_max);
          if (c.error) problema(celda.ruta, celda.rect_mm, "error", c.error);
          else contenidos.push({ celda, contenido: c.contenido });
        } else {
          contenidos.push({ celda, contenido: s.descripcion });
        }
        simbolos.push(Object.assign({ id: s.id }, colocarSimbolo(s.tamano_dibujo_mm, i + 1, casilla, relleno, s.margen_mm)));
      });
    }

    // 2. Tablas (revisiones y firmas): cada celda llena; las firmas en imagen, su caja.
    let letras = [];
    for (const tabla of camposDeTipo(definicion, "tabla")) {
      const valor = valores[tabla.nombre];
      if (tabla.columna_clave) letras = letras.concat(F.letrasValidas(valor, tabla));
      for (const { celda, valor: v, sitio, columna } of celdasDeTabla(definicion, tabla, valor)) {
        if (esObjeto(v)) {
          if (!columna.acepta_imagen || typeof v.imagen !== "string") {
            problema(celda.ruta, celda.rect_mm, "error", sitio + ": esta celda no admite una imagen de firma");
            continue;
          }
          firmas.push({ ruta: celda.ruta, imagen: v.imagen, persona: v.imagen.split("/")[0], celda_mm: celda.rect_mm.slice(),
            caja_mm: cajaFirma(celda.rect_mm, columna.alto_max_mm, tabla.cuerpo_y, relleno) });
          continue;
        }
        const c = contenido(v, sitio, celda.lineas_max);
        if (c.error) problema(celda.ruta, celda.rect_mm, "error", c.error);
        else contenidos.push({ celda, contenido: c.contenido });
      }
    }

    // 3. Campos de texto: calculados (ESCALA, REV.), escritos o el valor por defecto.
    for (const campo of camposDeTipo(definicion, "texto")) {
      const celda = F.celdaTexto(campo.nombre, campo);
      let c;
      if (campo.calculado === "escala_comun") c = { contenido: F.escalaComun(entrada.escalas || []) };
      else if (campo.calculado) c = { contenido: F.ultimaRevision(letras, (definicion.campos.revisiones || { orden: [] }).orden) };
      else if (campo.nombre in valores) c = contenido(valores[campo.nombre], "rotulo." + campo.nombre, campo.lineas_max);
      else c = { contenido: campo.por_defecto || "" };
      if (c.error) problema(celda.ruta, celda.rect_mm, "error", c.error);
      else contenidos.push({ celda, contenido: c.contenido });
    }

    // Maquetar cada contenido como `componer` (caracteres de la fuente, luego medir).
    for (const { celda, contenido: cont } of contenidos) {
      const texto = Array.isArray(cont) ? cont.join(" ") : cont;
      const { faltan } = F.caracteresFaltantes(texto, fuente);
      if (faltan.length) {
        problema(celda.ruta, celda.rect_mm, "error", "campo '" + celda.ruta + "': la fuente " + fuente.nombre +
          " no tiene los caracteres " + faltan.map(F.pyRepr).join(" "));
        continue;
      }
      const m = M.maquetar(celda, cont, fuente, relleno, interlineado);
      if (m.problema) problema(celda.ruta, celda.rect_mm, "error", m.problema);
      else if (m.sin_medir) problema(celda.ruta, celda.rect_mm, "aviso", F.avisoSinMedir(celda.ruta, m.sin_medir));
      else if (m.lineas.length) textos.push(m);
    }

    // 4. Notas (al final, como en Python): las de los .txt del catálogo y luego las adicionales.
    for (const campo of camposDeTipo(definicion, "notas")) {
      const valor = valores[campo.nombre];
      if (valor === undefined) continue;
      const v = N.validarNotas(valor, fuente, entrada.catalogo || null, null);
      if (v.errores.length) {
        problema(campo.nombre, campo.rect_mm, "error", v.errores[0]);
        continue;
      }
      const archivos = esObjeto(valor) && Array.isArray(valor.archivos) ? valor.archivos : [];
      const lista = N.notasParaComponer(archivos, v.notas, entrada.catalogo || null);
      if (lista.sin_medir) {
        problema(campo.nombre, campo.rect_mm, "aviso", lista.sin_medir);
        continue;
      }
      const m = M.maquetarNotas(campo, lista.lista, fuente, relleno, interlineado);
      if (m.problema) problema(campo.nombre, campo.rect_mm, "error", m.problema);
      else if (m.sin_medir) problema(campo.nombre, campo.rect_mm, "aviso", "campo 'notas': el editor no puede medir los caracteres " +
        m.sin_medir.map(F.pyRepr).join(" ") + "; componer dirá si las notas caben");
      else textos.push(...m.textos);
    }
    return { textos, simbolos, firmas, problemas };
  }

  // ---------------------------------------------------------------------------------------
  // Etiquetas «ESC: 1:N» (copia de etiquetas_escala.colocar_etiquetas).
  // ---------------------------------------------------------------------------------------

  function cruzan(a, b) {
    return a[0] < b[2] - EPS_MM && b[0] < a[2] - EPS_MM && a[1] < b[3] - EPS_MM && b[1] < a[3] - EPS_MM;
  }

  function motivo(rect, propio, area, detalles, elementos, puestas) {
    if (rect[0] < area[0] - EPS_MM || rect[1] < area[1] - EPS_MM || rect[2] > area[2] + EPS_MM || rect[3] > area[3] + EPS_MM) {
      return "se sale del área de dibujo";
    }
    for (const otro of detalles) if (otro.id !== propio && cruzan(rect, otro.dibujo_mm)) return "se monta sobre el dibujo de '" + otro.id + "'";
    for (const [nombre, r] of elementos) if (cruzan(rect, r)) return "se monta sobre '" + nombre + "'";
    for (const [nombre, r] of puestas) if (cruzan(rect, r)) return "se monta sobre " + nombre;
    return null;
  }

  function textoEtiqueta(denominador) {
    return PREFIJO_ETIQUETA + "1:" + F.numeroConMiles(denominador);
  }

  /**
   * Entrada: {detalles: [{id, dibujo_mm, denominador, con_etiqueta}] (en orden de apilado),
   * area_mm, elementos: [[nombre, rect_mm]] (los visibles: la rosa en su sitio), fuente,
   * altura_mm?, separacion_mm?}. Devuelve {textos (como los del rótulo, con celda_mm = la caja
   * de la línea), avisos (los de componer)}.
   */
  function etiquetasEscala(entrada) {
    const fuente = entrada.fuente;
    const altura = entrada.altura_mm === undefined ? ALTURA_ETIQUETA_MM : entrada.altura_mm;
    const separacion = entrada.separacion_mm === undefined ? SEPARACION_ETIQUETA_MM : entrada.separacion_mm;
    const em = altura / fuente.altura_mayusculas; // tamaño de la fuente en mm
    const descenso = fuente.descenso_em * em;
    const ascenso = fuente.ascenso_em * em;
    const puestas = [];
    const textos = [];
    const avisos = [];
    for (const d of entrada.detalles) {
      if (d.con_etiqueta === false) continue;
      const texto = textoEtiqueta(d.denominador);
      const ancho = M.anchoMm(fuente, texto, altura);
      const cx = (d.dibujo_mm[0] + d.dibujo_mm[2]) / 2;
      const x0 = cx - ancho / 2;
      const sitios = [["debajo", d.dibujo_mm[1] - separacion - altura], ["encima", d.dibujo_mm[3] + separacion]];
      const motivos = {};
      let puesta = false;
      for (const [nombre, base] of sitios) {
        const rect = [x0, base - descenso, x0 + ancho, base + ascenso];
        const m = motivo(rect, d.id, entrada.area_mm, entrada.detalles, entrada.elementos || [], puestas);
        if (m === null) {
          puestas.push(["la etiqueta de '" + d.id + "'", rect]);
          textos.push({ ruta: "etiqueta_escala." + d.id, lineas: [{ texto, base_mm: [x0, base], ancho_mm: ancho }],
            altura_mm: altura, reducido_desde: null, celda_mm: rect });
          puesta = true;
          break;
        }
        motivos[nombre] = m;
      }
      if (!puesta) {
        avisos.push("Advertencia: no se dibujó la etiqueta «" + texto + "» del detalle '" + d.id + "': no cabe a " +
          pyG(separacion) + " mm de su dibujo (debajo: " + motivos.debajo + "; encima: " + motivos.encima +
          "). Mueva el detalle o ponga \"etiqueta_escala\": false.");
      }
    }
    return { textos, avisos };
  }

  return {
    ALTURA_ETIQUETA_MM, SEPARACION_ETIQUETA_MM,
    colocarSimbolo, cajaFirma, piezasRotulo, textoEtiqueta, etiquetasEscala,
  };
});
