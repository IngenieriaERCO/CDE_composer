/*
 * Editor de planos — panel «Rótulo» con sus FORMULARIOS (subfase 4.3b). Solo pantalla: las
 * reglas están en editor_formularios.js (EditorFormularios) y el modelo en editor_rotulo.js
 * (EditorRotulo). Aquí: campos simples, ESCALA y REV. (solo lectura), revisiones y firmas.
 *
 * Al escribir, el valor va directo al modelo (sin volver a dibujar el panel, para no perder el
 * cursor) y se revalida todo. Desde la 4.3e cada texto se MIDE: «no cabe» (rojo) y «se
 * escribió a X mm» (ámbar) se muestran debajo del campo (en revisiones y firmas, al pie de su
 * tarjeta) y en «Problemas del rótulo», con los textos de `componer`. Agregar, quitar o cambiar la letra de una revisión, o el modo de
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
    // Lista de personas de esta sesión: las de --firmas más las nuevas (escritas o cargadas).
    const sesion = (PERSONAS || []).slice();
    const nuevas = new Set(); // filas de firmas con «Persona nueva…» abierta
    const NUEVA = "\u0000nueva"; // valor de la opción «Persona nueva…» (no es un nombre válido)
    const FORMATO_FECHA = DEF ? DEF.formato_fecha : "dd/mm/aa";
    let marcables = []; // [{nodo, claves}]: rojo si tiene error, ámbar si se reduce
    let calculados = {}; // campo -> input de solo lectura
    let crecientes = []; // cajas que crecen con el texto (Título)
    let cajaProblemas = null;
    let cajasJunto = new Map(); // contenedor -> <ul> de mensajes junto al campo

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

    /** Un campo de texto que se escribe a mano (c: de F.camposSimples). */
    function campoSimple(c) {
      const actual = valor(c.campo);
      if (!F.representable(actual)) {
        return fila(c.etiqueta, nodo("div", { class: "medida" }, "Valor que el formulario no sabe mostrar: se conserva sin editar."));
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
      return fila(c.etiqueta, entrada);
    }

    /** Un campo calculado (ESCALA, REV.): de solo lectura; refrescar() pone su valor. */
    function campoCalculado(nombre) {
      const entrada = nodo("input", { type: "text", readonly: "", class: "calculado",
        title: "Se calcula al componer; no se escribe en el plano" });
      calculados[nombre] = entrada;
      marcables.push({ nodo: entrada, claves: ["rotulo." + nombre] });
      return fila((F.ETIQUETAS[nombre] || nombre) + " (calculada)", entrada);
    }

    // Los paneles propios (imagen de localización, notas, convenciones) viven en editor.html como
    // secciones «bloque-…»; aquí solo se colocan en su lugar del rótulo (no cambia cómo funcionan).
    const BLOQUES_PANEL = { imagen: "bloque-localizacion", notas: "bloque-notas", convenciones: "bloque-convenciones" };

    /**
     * Todo el formulario en el orden del rótulo, de arriba hacia abajo (F.bloquesRotulo): los
     * campos sueltos seguidos van juntos en un grupo; las tablas y los paneles, en su sección.
     */
    function bloquesEnOrden() {
      const simples = new Map(F.camposSimples(DEF).map((c) => [c.campo, c]));
      const partes = [];
      let grupo = null;
      for (const b of F.bloquesRotulo(DEF)) {
        let n = null;
        let suelto = false;
        if (b.tipo === "texto") {
          n = b.calculado ? campoCalculado(b.campo) : simples.has(b.campo) ? campoSimple(simples.get(b.campo)) : null;
          suelto = true;
        } else if (b.campo === F.TABLA_REVISIONES) {
          n = seccionRevisiones();
        } else if (b.campo === F.TABLA_FIRMAS) {
          n = seccionFirmas();
        } else if (BLOQUES_PANEL[b.tipo]) {
          n = document.getElementById(BLOQUES_PANEL[b.tipo]);
        }
        if (!n) continue;
        if (suelto) {
          if (!grupo) {
            grupo = nodo("div", { class: "grupo-campos" });
            partes.push(grupo);
          }
          grupo.appendChild(n);
        } else {
          grupo = null;
          partes.push(n);
        }
      }
      return partes;
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
        const quitar = nodo("button", { type: "button", title: "Quitar esta revisión", class: "quitar" }, "✕");
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
        s.appendChild(nodo("div", { class: "medida" }, "Sin lista de personas (use --firmas <carpeta> al generar el editor): la firma va como texto, como «Persona nueva…» o con «Cargar firma…»."));
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
          if (col.acepta_imagen) entrada = entradaFirma(item[col.clave], celda, claves, escribir, f.clave);
          else if (col.clave === F.COLUMNA_FECHA) entrada = entradaFecha(item[col.clave], celda, claves, escribir);
          else entrada = entradaTexto(item[col.clave], celda, claves, escribir);
          cuadricula.appendChild(fila(F.etiquetaColumna(col.clave), entrada));
        }
        s.appendChild(tarjeta);
      }
      return s;
    }

    /** Firma: texto, o una persona de la lista de --firmas ({"imagen": "<persona>"}). */
    /**
     * Firma: texto, o una persona ({"imagen": "<persona>"}): de la lista de --firmas, una
     * «Persona nueva…» escrita a mano, o la que se guarde con «Cargar firma…» (4.3b2). La lista
     * de la sesión suma las personas nuevas; las imágenes nunca pasan por aquí.
     */
    function entradaFirma(actual, celda, claves, escribir, fila) {
      const caja = nodo("div", { class: "firma" });
      const modo = nodo("select", { title: "Firma como texto o con la imagen de una persona" });
      modo.append(nodo("option", { value: "texto" }, "Texto"), nodo("option", { value: "persona" }, "Persona"));
      const imagen = F.esFirmaImagen(actual);
      modo.value = imagen || nuevas.has(fila) ? "persona" : "texto";
      modo.addEventListener("change", () => {
        nuevas.delete(fila);
        if (modo.value === "persona" && sesion.length) escribir({ imagen: sesion[0] });
        else if (modo.value === "persona") nuevas.add(fila); // sin lista: se escribe el nombre
        else escribir(undefined);
        pintar();
      });
      caja.appendChild(modo);
      if (modo.value === "texto") {
        caja.appendChild(entradaTexto(actual, celda, claves, escribir));
      } else if (nuevas.has(fila)) {
        caja.appendChild(entradaPersonaNueva(fila, claves, escribir));
      } else {
        const lista = nodo("select", { title: "Persona: su carpeta en firmas/ (la imagen no está en el editor)" });
        const nombres = sesion.slice();
        if (!nombres.includes(actual.imagen)) nombres.unshift(actual.imagen);
        for (const p of nombres) {
          lista.appendChild(nodo("option", { value: p }, sesion.includes(p) ? p : p + " (no está en la lista)"));
        }
        lista.appendChild(nodo("option", { value: NUEVA }, "Persona nueva…"));
        lista.value = actual.imagen;
        lista.addEventListener("change", () => {
          if (lista.value === NUEVA) {
            nuevas.add(fila);
            pintar();
          } else {
            escribir({ imagen: lista.value });
          }
        });
        marcables.push({ nodo: lista, claves });
        caja.appendChild(lista);
      }
      const cargar = nodo("button", { type: "button", class: "cargar-firma", title:
        "Recortar y limpiar una imagen de la firma (se procesa solo en este navegador)" }, "Cargar firma…");
      cargar.addEventListener("click", () => raiz.EditorDialogoFirma.abrir({
        fila: F.etiquetaFilaFirma(fila),
        persona: imagen ? actual.imagen.split("/")[0] : "",
        alUsar: (persona) => {
          if (!sesion.includes(persona)) sesion.push(persona);
          nuevas.delete(fila);
          escribir({ imagen: persona });
          pintar();
        },
      }));
      caja.appendChild(cargar);
      return caja;
    }

    /** «Persona nueva…»: el nombre de su carpeta en firmas/ (mismas reglas que firmas.py). */
    function entradaPersonaNueva(fila, claves, escribir) {
      const entrada = nodo("input", { type: "text", placeholder: "Nombre de la persona",
        title: "Letras (con tildes y ñ), números, espacio, «_» y «-». Es el nombre de su carpeta en firmas/." });
      entrada.addEventListener("change", () => {
        const problema = raiz.EditorFirma.problemaNombre(entrada.value);
        entrada.classList.toggle("invalido", !!problema);
        entrada.title = problema || "Persona nueva: componer buscará firmas/" + entrada.value + "/firma.png";
        if (problema) return;
        if (!sesion.includes(entrada.value)) sesion.push(entrada.value);
        nuevas.delete(fila);
        escribir({ imagen: entrada.value });
        pintar();
      });
      marcables.push({ nodo: entrada, claves });
      return entrada;
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
      // Mensajes junto al campo: debajo de la fila, o al pie de la tarjeta (revisiones, firmas).
      const junto = new Map(); // contenedor -> {errores, avisos} sin repetir
      for (const m of marcables) {
        const propios = F.mensajesDeCampo(v, m.claves);
        m.nodo.classList.toggle("invalido", propios.errores.length > 0);
        m.nodo.classList.toggle("reducido", !propios.errores.length && propios.avisos.length > 0);
        const contenedor = m.nodo.closest(".tarjeta-tabla") || m.nodo.closest(".campo");
        if (!contenedor) continue;
        if (!junto.has(contenedor)) junto.set(contenedor, { errores: new Set(), avisos: new Set() });
        propios.errores.forEach((e) => junto.get(contenedor).errores.add(e));
        propios.avisos.forEach((a) => junto.get(contenedor).avisos.add(a));
      }
      for (const [contenedor, mensajes] of junto) mostrarJunto(contenedor, mensajes);
      if (!cajaProblemas) return;
      const filas = v.errores.map((e) => nodo("li", { class: "error" }, e))
        .concat(v.avisos.map((a) => nodo("li", { class: "aviso" }, a)));
      if (!filas.length) filas.push(nodo("li", { class: "ninguna" }, "Sin problemas en los campos del formulario."));
      cajaProblemas.replaceChildren(...filas);
    }

    /** Lista de mensajes junto a un campo (al pie de la tarjeta, o debajo de la fila). */
    function mostrarJunto(contenedor, mensajes) {
      let lista = cajasJunto.get(contenedor);
      if (!lista) {
        lista = nodo("ul", { class: "advertencias problemas-rotulo junto-campo" });
        if (contenedor.classList.contains("tarjeta-tabla")) contenedor.appendChild(lista);
        else contenedor.after(lista);
        cajasJunto.set(contenedor, lista);
      }
      lista.replaceChildren(...[...mensajes.errores].map((e) => nodo("li", { class: "error" }, e)),
        ...[...mensajes.avisos].map((a) => nodo("li", { class: "aviso" }, a)));
      lista.hidden = !lista.children.length;
    }

    function pintar() {
      marcables = [];
      cajasJunto = new Map();
      calculados = {};
      crecientes = [];
      if (!DATOS || !DEF) {
        panel.replaceChildren(nodo("div", { class: "vacio" }, "El formato no tiene sección de rótulo."));
        cajaProblemas = null;
        return;
      }
      const partes = bloquesEnOrden();
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
