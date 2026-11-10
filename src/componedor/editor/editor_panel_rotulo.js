/*
 * Editor de planos — panel «Rótulo» con sus FORMULARIOS (subfase 4.3b). Solo pantalla: las
 * reglas están en editor_formularios.js (EditorFormularios) y el modelo en editor_rotulo.js
 * (EditorRotulo). Aquí: campos simples, ESCALA y REV. (solo lectura), revisiones y firmas.
 *
 * Al escribir, el valor va directo al modelo (sin volver a dibujar el panel, para no perder el
 * cursor) y se revalida todo. Agregar, quitar o cambiar la letra de una revisión, o el modo de
 * una firma, sí vuelve a dibujar el panel.
 */
(function (raiz) {
  "use strict";

  /**
   * opciones: {panel, datos (DATOS.rotulo), modelo() (modelo actual), escalas() (de los
   * detalles colocados), alCambiar() (hay cambios por guardar)}.
   */
  function crear(opciones) {
    const R = raiz.EditorRotulo;
    const F = raiz.EditorFormularios;
    const panel = opciones.panel;
    const DATOS = opciones.datos;
    const DEF = DATOS ? DATOS.definicion : null;
    const FUENTE = DATOS ? DATOS.fuente : null;
    const PERSONAS = DATOS ? DATOS.personas_firmas : null;
    const FORMATO_FECHA = DEF ? DEF.formato_fecha : "dd/mm/aa";
    let marcables = []; // [{nodo, claves}] para marcar en rojo los que tienen error
    let calculados = {}; // campo -> input de solo lectura
    let crecientes = []; // cajas que crecen con el texto (Título)
    let cajaProblemas = null;

    const modelo = () => opciones.modelo();
    const valor = (campo) => R.valor(modelo(), campo);

    function nodo(nombre, atributos, texto) {
      const n = document.createElement(nombre);
      for (const [clave, v] of Object.entries(atributos || {})) {
        if (clave === "class") n.className = v;
        else n.setAttribute(clave, v);
      }
      if (texto !== undefined) n.textContent = texto;
      return n;
    }

    function cambiar(campo, nuevo) {
      R.cambiar(modelo(), campo, nuevo);
      opciones.alCambiar();
      refrescar();
    }

    // -------------------------------------------------------------------------------------
    // Piezas: entrada de texto (una o varias líneas) y fecha con selector.
    // -------------------------------------------------------------------------------------

    /** Entrada para un valor de texto; `escribir(valorJson)` lo guarda. */
    function entradaTexto(actual, celda, claves, escribir, placeholder) {
      const varias = celda.lineas_max > 1;
      const entrada = nodo(varias ? "textarea" : "input", varias ? { rows: String(Math.min(celda.lineas_max, 3)) }
        : { type: "text" });
      entrada.value = F.textoDeValor(actual);
      if (placeholder) entrada.placeholder = placeholder;
      entrada.title = (varias ? "Hasta " + celda.lineas_max + " líneas (una por renglón). " : "Una sola línea. ") +
        "Celda «" + celda.ruta + "»";
      let anterior = actual;
      entrada.addEventListener("input", () => {
        const nuevo = F.valorDeTexto(entrada.value, anterior);
        escribir(nuevo);
        if (nuevo !== undefined) anterior = nuevo;
      });
      marcables.push({ nodo: entrada, claves });
      return entrada;
    }

    /** Fecha: texto libre + selector (calendario) que escribe en formato_fecha. */
    function entradaFecha(actual, celda, claves, escribir) {
      const caja = nodo("div", { class: "fecha" });
      // Una fecha siempre se escribe en un renglón (aunque la fila admita más líneas).
      const texto = entradaTexto(actual, Object.assign({}, celda, { lineas_max: 1 }), claves, (v) => {
        selector.value = F.fechaIso(typeof v === "string" ? v : "", FORMATO_FECHA);
        escribir(v);
      }, FORMATO_FECHA);
      const selector = nodo("input", { type: "date", title: "Elegir la fecha (se escribe como " + FORMATO_FECHA + ")" });
      selector.value = F.fechaIso(typeof actual === "string" ? actual : "", FORMATO_FECHA);
      selector.addEventListener("change", () => {
        const escrita = F.formatearFecha(selector.value, FORMATO_FECHA);
        if (!escrita) return;
        texto.value = escrita;
        texto.dispatchEvent(new Event("input"));
      });
      caja.append(texto, selector);
      return caja;
    }

    /** Alto de una caja de texto según su contenido, hasta `maxLineas` (después, barra). */
    function crecer(caja, maxLineas) {
      const estilo = getComputedStyle(caja);
      const bordes = parseFloat(estilo.borderTopWidth) + parseFloat(estilo.borderBottomWidth);
      const maximo = (parseFloat(estilo.lineHeight) || 17) * maxLineas + parseFloat(estilo.paddingTop) +
        parseFloat(estilo.paddingBottom) + bordes;
      caja.style.height = "auto";
      const alto = caja.scrollHeight + bordes;
      caja.style.height = Math.min(alto, maximo) + "px";
      caja.style.overflowY = alto > maximo + 1 ? "auto" : "hidden";
    }

    function fila(etiqueta, entrada) {
      const f = nodo("label", { class: "campo" });
      f.append(nodo("span", { class: "etiqueta" }, etiqueta), entrada);
      return f;
    }

    // -------------------------------------------------------------------------------------
    // Secciones.
    // -------------------------------------------------------------------------------------

    function seccion(titulo, abierta) {
      const d = nodo("details", { class: "seccion" });
      if (abierta) d.open = true;
      d.appendChild(nodo("summary", {}, titulo));
      return d;
    }

    function seccionDatos() {
      const s = seccion("Datos del plano", true);
      for (const c of F.camposSimples(DEF)) {
        const actual = valor(c.campo);
        if (!F.representable(actual)) {
          s.appendChild(fila(c.etiqueta, nodo("div", { class: "medida" }, "Valor que el formulario no sabe mostrar: se conserva sin editar.")));
          continue;
        }
        const placeholder = c.por_defecto ? c.por_defecto + " (por defecto)" : "";
        const entrada = entradaTexto(actual, c.celda, ["rotulo." + c.campo, "campo '" + c.campo + "'"],
          (v) => cambiar(c.campo, v), placeholder);
        if (c.campo === "titulo") {
          // El título crece con el texto, sin barra de desplazamiento, hasta ~6 renglones.
          entrada.classList.add("crece");
          entrada.addEventListener("input", () => crecer(entrada, 6));
          crecientes.push(entrada);
        }
        s.appendChild(fila(c.etiqueta, entrada));
      }
      for (const [nombre, campo] of Object.entries(DEF.campos)) {
        if (campo.tipo !== "texto" || !campo.calculado) continue;
        const entrada = nodo("input", { type: "text", readonly: "", class: "calculado",
          title: "Se calcula al componer; no se escribe en el plano" });
        calculados[nombre] = entrada;
        marcables.push({ nodo: entrada, claves: ["rotulo." + nombre] });
        s.appendChild(fila((F.ETIQUETAS[nombre] || nombre) + " (calculada)", entrada));
      }
      return s;
    }

    function seccionRevisiones() {
      const tabla = DEF.campos[F.TABLA_REVISIONES];
      if (!tabla) return null;
      const lista = valor(F.TABLA_REVISIONES);
      const s = seccion("Revisiones", true);
      if (!F.revisionesRepresentables(lista)) {
        s.appendChild(nodo("div", { class: "medida" }, "Las revisiones del plano tienen una forma que el formulario no sabe mostrar: se conservan sin editar."));
        return s;
      }
      const actual = lista || [];
      // Siempre la lista del modelo en ese momento (lo escrito después de dibujar ya está ahí).
      const fresca = () => R.valor(modelo(), F.TABLA_REVISIONES) || [];
      const guardar = (nueva) => cambiar(F.TABLA_REVISIONES, F.revisionesParaGuardar(nueva));
      // Se muestran en el orden del rótulo (de arriba abajo: 0, C, B, A), no en el de llenado;
      // `i` sigue siendo la posición en la lista del plano.
      for (const i of F.ordenRotulo(actual, tabla)) {
        const item = actual[i];
        const tarjeta = nodo("div", { class: "tarjeta-tabla" });
        const cabeza = nodo("div", { class: "cabeza" });
        const letra = F.letrasValidas([item], tabla)[0] || null;
        const select = nodo("select", { title: "Letra de la revisión (cada una va en su fila del rótulo)" });
        const opciones = F.letrasLibres(actual, tabla, i);
        if (!letra) select.appendChild(nodo("option", { value: "" }, "(no válida: " + F.pyRepr(item[tabla.columna_clave]) + ")"));
        for (const l of opciones) select.appendChild(nodo("option", { value: l }, l));
        select.value = letra && opciones.includes(letra) ? letra : "";
        select.addEventListener("change", () => {
          if (!select.value) return;
          guardar(F.cambiarCeldaRevision(fresca(), i, tabla.columna_clave, select.value));
          pintar();
        });
        marcables.push({ nodo: select, claves: ["rotulo.revisiones[" + i + "]." + tabla.columna_clave,
          "rotulo.revisiones[" + i + "]:"] });
        const quitar = nodo("button", { type: "button", title: "Quitar esta revisión" }, "Quitar");
        quitar.addEventListener("click", () => {
          guardar(F.quitarRevision(fresca(), i));
          pintar();
        });
        // Línea 1: VER. y Fecha (y Quitar); luego Descripción; las demás en cuadrícula 2 x 2.
        const ver = fila("VER.", select);
        ver.classList.add("ver");
        cabeza.appendChild(ver);
        tarjeta.appendChild(cabeza);
        const cuadricula = nodo("div", { class: "dos-columnas" });
        for (const col of tabla.columnas) {
          if (col.clave === tabla.columna_clave) continue;
          const celda = F.celdaTabla(DEF, F.TABLA_REVISIONES, letra || tabla.filas[0].clave, col.clave);
          const claves = ["rotulo.revisiones[" + i + "]." + col.clave];
          if (letra) claves.push("campo '" + celda.ruta + "'");
          const escribir = (v) => guardar(F.cambiarCeldaRevision(fresca(), i, col.clave, v));
          if (col.clave === F.COLUMNA_FECHA) {
            const f = fila(F.etiquetaColumna(col.clave), entradaFecha(item[col.clave], celda, claves, escribir));
            f.classList.add("crece-fila");
            cabeza.appendChild(f);
          } else if (col.clave === "descripcion") {
            tarjeta.appendChild(fila(F.etiquetaColumna(col.clave), entradaTexto(item[col.clave], celda, claves, escribir)));
          } else {
            cuadricula.appendChild(fila(F.etiquetaColumna(col.clave), entradaTexto(item[col.clave], celda, claves, escribir)));
          }
        }
        cabeza.appendChild(quitar);
        tarjeta.appendChild(cuadricula);
        s.appendChild(tarjeta);
      }
      const agregar = nodo("button", { type: "button" }, "Agregar revisión");
      agregar.disabled = !F.agregarRevision(actual, tabla);
      if (agregar.disabled) agregar.title = "Ya están todas las letras (" + tabla.orden.join(", ") + ")";
      agregar.addEventListener("click", () => {
        const nueva = F.agregarRevision(fresca(), tabla);
        if (nueva) guardar(nueva);
        pintar();
      });
      if (!actual.length) s.appendChild(nodo("div", { class: "vacio" }, "Sin revisiones: REV. queda vacía."));
      s.appendChild(nodo("div", { class: "botones" })).appendChild(agregar);
      return s;
    }

    function seccionFirmas() {
      const tabla = DEF.campos[F.TABLA_FIRMAS];
      if (!tabla) return null;
      const firmas = valor(F.TABLA_FIRMAS);
      const s = seccion("Firmas", true);
      if (!F.firmasRepresentables(firmas, DEF)) {
        s.appendChild(nodo("div", { class: "medida" }, "Las firmas del plano tienen una forma que el formulario no sabe mostrar: se conservan sin editar."));
        return s;
      }
      if (PERSONAS === null || PERSONAS === undefined) {
        s.appendChild(nodo("div", { class: "medida" }, "Sin lista de personas (use --firmas <carpeta> al generar el editor): la firma se puede escribir como texto."));
      }
      for (const f of tabla.filas) {
        const item = (firmas && firmas[f.clave]) || {};
        const tarjeta = nodo("div", { class: "tarjeta-tabla" });
        tarjeta.appendChild(nodo("div", { class: "cabeza" }, F.etiquetaFilaFirma(f.clave)));
        // De a dos por fila, en el orden del formato: Nombre | Matrícula, Firma | Fecha.
        const cuadricula = nodo("div", { class: "dos-columnas firmas" });
        tarjeta.appendChild(cuadricula);
        for (const col of tabla.columnas) {
          const celda = F.celdaTabla(DEF, F.TABLA_FIRMAS, f.clave, col.clave);
          const claves = ["rotulo.firmas." + f.clave + "." + col.clave, "campo '" + celda.ruta + "'",
            "rotulo.firmas." + f.clave + ":"];
          const escribir = (v) => cambiar(F.TABLA_FIRMAS, F.cambiarCeldaFirma(valor(F.TABLA_FIRMAS), f.clave, col.clave, v));
          let entrada;
          if (col.acepta_imagen) entrada = entradaFirma(item[col.clave], celda, claves, escribir);
          else if (col.clave === F.COLUMNA_FECHA) entrada = entradaFecha(item[col.clave], celda, claves, escribir);
          else entrada = entradaTexto(item[col.clave], celda, claves, escribir);
          cuadricula.appendChild(fila(F.etiquetaColumna(col.clave), entrada));
        }
        s.appendChild(tarjeta);
      }
      return s;
    }

    /** Firma: texto, o una persona de la lista de --firmas ({"imagen": "<persona>"}). */
    function entradaFirma(actual, celda, claves, escribir) {
      const caja = nodo("div", { class: "firma" });
      const modo = nodo("select", { title: "Firma como texto o con la imagen de una persona" });
      modo.append(nodo("option", { value: "texto" }, "Texto"), nodo("option", { value: "persona" }, "Persona"));
      const imagen = F.esFirmaImagen(actual);
      modo.value = imagen ? "persona" : "texto";
      if (!imagen && !(PERSONAS && PERSONAS.length)) modo.disabled = true;
      modo.addEventListener("change", () => {
        if (modo.value === "persona") escribir(PERSONAS && PERSONAS.length ? { imagen: PERSONAS[0] } : undefined);
        else escribir(undefined);
        pintar();
      });
      caja.appendChild(modo);
      if (!imagen) {
        caja.appendChild(entradaTexto(actual, celda, claves, escribir));
        return caja;
      }
      const lista = nodo("select", { title: "Persona: su carpeta en firmas/ (la imagen no está en el editor)" });
      const nombres = (PERSONAS || []).slice();
      if (!nombres.some((p) => p === actual.imagen)) nombres.unshift(actual.imagen);
      for (const p of nombres) {
        const enLista = (PERSONAS || []).includes(p);
        lista.appendChild(nodo("option", { value: p }, enLista ? p : p + " (no está en la lista)"));
      }
      lista.value = actual.imagen;
      lista.addEventListener("change", () => escribir({ imagen: lista.value }));
      marcables.push({ nodo: lista, claves });
      caja.appendChild(lista);
      return caja;
    }

    function seccionInformacion() {
      const s = seccion("Catálogos del editor", false);
      const c = R.resumenCatalogo(DATOS.notas);
      s.appendChild(nodo("div", { class: "medida" }, DATOS.notas
        ? "Notas típicas: " + c.notas + " nota(s) (" + c.vinetas + " viñeta(s)) en " + c.archivos +
          " archivo(s), " + c.grupos + " grupo(s)."
        : "Notas típicas: no se cargó ninguna carpeta (use --notas al generar el editor)."));
      s.appendChild(nodo("div", { class: "medida" }, "Símbolos de convenciones: " + DATOS.simbolos.length + "."));
      s.appendChild(nodo("div", { class: "medida" }, PERSONAS
        ? "Personas con firma: " + PERSONAS.length + " (solo el nombre; las imágenes no están en el editor)."
        : "Personas con firma: no se cargó ninguna carpeta (use --firmas)."));
      if (DATOS.proyecto) {
        s.appendChild(nodo("div", { class: "medida" }, "Proyecto" + (DATOS.proyecto.nombre ? " «" + DATOS.proyecto.nombre + "»" : "") +
          ": prellena los planos nuevos."));
      }
      if (c.problemas) s.appendChild(nodo("div", { class: "nota-detalle" }, c.problemas + " problema(s) al leer las notas típicas."));
      for (const aviso of DATOS.avisos) s.appendChild(nodo("div", { class: "nota-detalle" }, aviso));
      return s;
    }

    // -------------------------------------------------------------------------------------
    // Validación en vivo y calculados.
    // -------------------------------------------------------------------------------------

    function validacion() {
      return F.validarRotulo(R.serializar(modelo()), DEF, FUENTE, PERSONAS);
    }

    /** Calculados, marcas rojas y lista de problemas (sin volver a dibujar los formularios). */
    function refrescar() {
      if (!DEF) return;
      const tablaRev = DEF.campos[F.TABLA_REVISIONES];
      for (const [nombre, entrada] of Object.entries(calculados)) {
        const campo = DEF.campos[nombre];
        if (campo.calculado === "ultima_revision" && tablaRev) {
          entrada.value = F.ultimaRevision(F.letrasValidas(valor(F.TABLA_REVISIONES), tablaRev), tablaRev.orden);
        } else if (campo.calculado === "escala_comun") {
          entrada.value = F.escalaComun(opciones.escalas());
        }
        entrada.placeholder = "(vacía)";
      }
      const v = validacion();
      for (const m of marcables) {
        const mal = v.errores.some((e) => m.claves.some((k) => e.startsWith(k + ":") || e.startsWith(k + ".") ||
          (k.endsWith(":") && e.startsWith(k))));
        m.nodo.classList.toggle("invalido", mal);
      }
      if (!cajaProblemas) return;
      const filas = v.errores.map((e) => nodo("li", { class: "error" }, e))
        .concat(v.avisos.map((a) => nodo("li", { class: "aviso" }, a)));
      if (!filas.length) filas.push(nodo("li", { class: "ninguna" }, "Sin problemas en los campos del formulario."));
      cajaProblemas.replaceChildren(...filas);
    }

    function pintar() {
      marcables = [];
      calculados = {};
      crecientes = [];
      if (!DATOS || !DEF) {
        panel.replaceChildren(nodo("div", { class: "vacio" }, "El formato no tiene sección de rótulo."));
        cajaProblemas = null;
        return;
      }
      const partes = [seccionDatos(), seccionRevisiones(), seccionFirmas()].filter(Boolean);
      const conserva = R.noRepresentable(modelo());
      if (conserva.length) {
        const s = seccion("Se conserva sin editar", true);
        for (const t of conserva) s.appendChild(nodo("div", { class: "medida" }, t));
        partes.push(s);
      }
      partes.push(nodo("div", { class: "medida" }, "Las notas se editan en el panel «Notas» y las convenciones en el panel «Convenciones»."));
      const titulo = nodo("div", { class: "subtitulo" }, "Problemas del rótulo");
      cajaProblemas = nodo("ul", { class: "advertencias problemas-rotulo" });
      partes.push(titulo, cajaProblemas, seccionInformacion());
      panel.replaceChildren(...partes);
      for (const caja of crecientes) crecer(caja, 6);
      refrescar();
    }

    return { pintar, refrescar, validacion };
  }

  raiz.EditorPanelRotulo = { crear };
})(typeof self !== "undefined" ? self : this);
