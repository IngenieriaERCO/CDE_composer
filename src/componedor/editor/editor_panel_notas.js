/*
 * Editor de planos — panel «Notas» (subfase 4.3c). Solo pantalla: las reglas están en
 * editor_notas.js (EditorNotas) y el modelo del rótulo en editor_rotulo.js (EditorRotulo).
 *
 * - Catálogo de notas típicas (de --notas) por grupo: una casilla por nota. Marcarla la agrega
 *   al final de «Notas del plano»; desmarcarla la saca. Una nota elegida no se repite.
 * - «Notas del plano»: numeración en vivo (1…N; las viñetas no se numeran), subir, bajar,
 *   quitar, y texto y viñetas editables (la nota está COPIADA en el plano).
 * - Notas a mano, con viñetas (una por línea).
 * Lo elegido se guarda en rotulo.notas.adicionales; "archivos" se conserva intacto.
 */
(function (raiz) {
  "use strict";

  /** opciones: {panel, datos (DATOS.rotulo), modelo(), alCambiar()}. */
  function crear(opciones) {
    const R = raiz.EditorRotulo;
    const N = raiz.EditorNotas;
    const panel = opciones.panel;
    const DATOS = opciones.datos;
    const CATALOGO = DATOS ? DATOS.notas : null;
    const FUENTE = DATOS ? DATOS.fuente : null;
    const TIENE_CAMPO = !!(DATOS && DATOS.definicion && Object.values(DATOS.definicion.campos).some((c) => c.tipo === "notas"));
    let estado = { archivos: [], items: [], editable: true };
    let marcables = []; // [{nodo, indice}]
    let crecientes = [];
    let cajaProblemas = null;

    const modelo = () => opciones.modelo();

    function nodo(nombre, atributos, texto) {
      const n = document.createElement(nombre);
      for (const [clave, v] of Object.entries(atributos || {})) {
        if (clave === "class") n.className = v;
        else n.setAttribute(clave, v);
      }
      if (texto !== undefined) n.textContent = texto;
      return n;
    }

    /** Caja de texto que crece con su contenido hasta `maxLineas` (sin barra antes). */
    function crecer(caja, maxLineas) {
      const estilo = getComputedStyle(caja);
      const linea = parseFloat(estilo.lineHeight) || 17;
      const extra = parseFloat(estilo.paddingTop) + parseFloat(estilo.paddingBottom) +
        parseFloat(estilo.borderTopWidth) + parseFloat(estilo.borderBottomWidth);
      const maximo = linea * maxLineas + extra;
      caja.style.height = "auto";
      const alto = caja.scrollHeight + parseFloat(estilo.borderTopWidth) + parseFloat(estilo.borderBottomWidth);
      caja.style.height = Math.min(alto, maximo) + "px";
      caja.style.overflowY = alto > maximo + 1 ? "auto" : "hidden";
    }

    function cajaCreciente(valor, maxLineas, placeholder) {
      const caja = nodo("textarea", { rows: "1", class: "crece" });
      caja.value = valor;
      if (placeholder) caja.placeholder = placeholder;
      caja.addEventListener("input", () => crecer(caja, maxLineas));
      crecientes.push([caja, maxLineas]);
      return caja;
    }

    /** Vuelve a leer las notas del modelo (al empezar y al abrir otro plano). */
    function reiniciar() {
      estado = N.lista(R.valor(modelo(), "notas"), CATALOGO);
      pintar();
    }

    function guardar() {
      R.cambiar(modelo(), "notas", N.notasParaGuardar(R.valor(modelo(), "notas"), estado.items));
      opciones.alCambiar();
    }

    function cambiarLista(items) {
      estado.items = items;
      guardar();
      pintar();
    }

    // -------------------------------------------------------------------------------------
    // Catálogo.
    // -------------------------------------------------------------------------------------

    function seccionCatalogo() {
      const s = nodo("details", { class: "seccion" });
      s.open = true;
      s.appendChild(nodo("summary", {}, "Notas típicas"));
      if (!CATALOGO) {
        s.appendChild(nodo("div", { class: "medida" }, "No se cargó ningún catálogo (use --notas <carpeta> al generar el editor)."));
        return s;
      }
      for (const aviso of CATALOGO.avisos) s.appendChild(nodo("div", { class: "nota-detalle" }, aviso));
      const elegidas = new Set(estado.items.map((x) => x.clave).filter(Boolean));
      // .txt del catálogo que el plano ya trae en "archivos": sus notas no se pueden marcar.
      const incluidos = N.archivosIncluidos(estado.archivos, CATALOGO);
      CATALOGO.grupos.forEach((g, gi) => {
        const grupo = nodo("details", { class: "grupo-notas" });
        if (gi === 0) grupo.open = true;
        const total = g.archivos.reduce((s, a) => s + a.notas.length, 0);
        const marcadas = g.archivos.reduce((s, a) => s + a.notas.filter((n) => elegidas.has(N.claveNota(a.archivo, n))).length, 0);
        grupo.appendChild(nodo("summary", {}, g.titulo + " (" + (marcadas ? marcadas + " de " : "") + total + ")"));
        for (const a of g.archivos) {
          const ruta = incluidos.get(a.archivo);
          grupo.appendChild(nodo("div", { class: "archivo-notas" }, a.archivo +
            (ruta ? " — en «archivos» del plano como " + ruta : "")));
          for (const p of a.problemas) grupo.appendChild(nodo("div", { class: "nota-detalle" }, p));
          for (const n of a.notas) {
            grupo.appendChild(notaCatalogo(n, a, elegidas.has(N.claveNota(a.archivo, n)), ruta));
          }
          if (!a.notas.length && !a.problemas.length) grupo.appendChild(nodo("div", { class: "vacio" }, "Sin notas."));
        }
        s.appendChild(grupo);
      });
      if (!CATALOGO.grupos.length) s.appendChild(nodo("div", { class: "vacio" }, "El catálogo está vacío."));
      return s;
    }

    /** `incluida`: la ruta con que el plano ya trae ese .txt en "archivos" (o undefined). */
    function notaCatalogo(n, archivo, marcada, incluida) {
      const clave = N.claveNota(archivo.archivo, n);
      const fila = nodo("label", { class: "nota-catalogo" + (incluida ? " incluida" : ""), title: clave });
      const casilla = nodo("input", { type: "checkbox" });
      casilla.checked = marcada && !incluida;
      casilla.disabled = !estado.editable || !!incluida;
      casilla.title = incluida ? "Ya está en el plano: viene de «archivos» (" + incluida + ")"
        : marcada ? "Quitar del plano" : "Agregar al plano (al final de la lista)";
      casilla.addEventListener("change", () => cambiarLista(casilla.checked
        ? N.marcar(estado.items, clave, CATALOGO, estado.archivos) : N.desmarcar(estado.items, clave)));
      const texto = nodo("div", { class: "texto-nota" });
      texto.appendChild(nodo("div", {}, n.texto));
      if (incluida) texto.appendChild(nodo("div", { class: "etiqueta-incluida" }, "ya incluida desde archivos"));
      for (const v of n.vinetas) texto.appendChild(nodo("div", { class: "vineta" }, "• " + v));
      for (const aviso of N.avisosDeNota(archivo, n)) {
        texto.appendChild(nodo("div", { class: "aviso-nota" }, aviso));
      }
      fila.append(casilla, texto);
      return fila;
    }

    // -------------------------------------------------------------------------------------
    // Notas del plano.
    // -------------------------------------------------------------------------------------

    function seccionPlano() {
      const s = nodo("details", { class: "seccion" });
      s.open = true;
      s.appendChild(nodo("summary", {}, "Notas del plano (" + estado.items.length + ")"));
      if (estado.archivos.length) {
        const caja = nodo("div", { class: "de-archivos" });
        caja.appendChild(nodo("div", { class: "subtitulo" }, "Vienen de archivos (editar a mano):"));
        const conocidos = new Set(N.archivosIncluidos(estado.archivos, CATALOGO).values());
        for (const a of estado.archivos) {
          caja.appendChild(nodo("div", { class: "medida" }, a + (conocidos.has(a)
            ? " (en el catálogo: sus notas típicas quedan marcadas «ya incluida»)"
            : " (no está en el catálogo: el editor no ve sus notas)")));
        }
        caja.appendChild(nodo("div", { class: "medida" }, "En el PDF van primero; la numeración de abajo sigue después de ellas."));
        s.appendChild(caja);
      }
      if (!estado.editable) {
        s.appendChild(nodo("div", { class: "medida" }, "Las notas adicionales del plano tienen una forma que el editor no sabe mostrar: se conservan sin editar."));
        return s;
      }
      const indice = N.indiceCatalogo(CATALOGO);
      const numeros = N.numeros(estado.items);
      estado.items.forEach((item, i) => {
        const tarjeta = nodo("div", { class: "nota-plano" });
        const cabeza = nodo("div", { class: "cabeza" });
        cabeza.appendChild(nodo("strong", { class: "numero" }, (estado.archivos.length ? "+" : "") + numeros[i] + "."));
        const origen = item.clave && indice.get(item.clave);
        cabeza.appendChild(nodo("span", { class: "medida origen" }, origen ? "típica: " + item.clave : "a mano"));
        for (const [texto, titulo, accion, deshabilitado] of [
          ["↑", "Subir", () => cambiarLista(N.mover(estado.items, i, -1)), i === 0],
          ["↓", "Bajar", () => cambiarLista(N.mover(estado.items, i, 1)), i === estado.items.length - 1],
          ["✕", "Quitar del plano", () => cambiarLista(N.quitar(estado.items, i)), false],
        ]) {
          const b = nodo("button", { type: "button", title: titulo, class: texto === "✕" ? "mini quitar" : "mini" }, texto);
          b.disabled = deshabilitado;
          b.addEventListener("click", accion);
          cabeza.appendChild(b);
        }
        tarjeta.appendChild(cabeza);
        const texto = cajaCreciente(item.texto, 6, "Texto de la nota");
        texto.title = "Una sola línea (el componedor la parte en la celda)";
        texto.addEventListener("keydown", (ev) => { if (ev.key === "Enter") ev.preventDefault(); });
        texto.addEventListener("input", () => {
          if (texto.value.includes("\n")) texto.value = texto.value.replace(/\r?\n/g, " ");
          item.texto = texto.value;
          item.tocado = true;
          guardar();
          refrescar();
        });
        const vinetas = cajaCreciente(item.vinetas.join("\n"), 6, "Viñetas (una por línea; opcional)");
        vinetas.addEventListener("input", () => {
          item.vinetas = N.vinetasDeTexto(vinetas.value);
          item.tocado = true;
          guardar();
          refrescar();
        });
        const aviso = nodo("div", { class: "aviso-nota" });
        aviso.hidden = true;
        marcables.push({ nodo: texto, indice: i, aviso });
        tarjeta.append(texto, aviso, vinetas);
        s.appendChild(tarjeta);
      });
      if (!estado.items.length) {
        s.appendChild(nodo("div", { class: "vacio" }, "Ninguna: marque notas típicas o agregue una a mano."));
      }
      return s;
    }

    function seccionAMano() {
      const s = nodo("details", { class: "seccion" });
      s.open = true;
      s.appendChild(nodo("summary", {}, "Agregar nota a mano"));
      const texto = cajaCreciente("", 6, "Texto de la nota (una línea)");
      texto.addEventListener("keydown", (ev) => { if (ev.key === "Enter") ev.preventDefault(); });
      const vinetas = cajaCreciente("", 6, "Viñetas, una por línea (opcional)");
      const boton = nodo("button", { type: "button" }, "Agregar nota");
      boton.disabled = !estado.editable;
      boton.addEventListener("click", () => {
        const item = N.itemAMano(texto.value, vinetas.value);
        if (!item) {
          texto.classList.add("invalido");
          texto.focus();
          return;
        }
        cambiarLista(estado.items.concat([item]));
      });
      const botones = nodo("div", { class: "botones" });
      botones.appendChild(boton);
      s.append(texto, vinetas, botones);
      return s;
    }

    // -------------------------------------------------------------------------------------
    // Validación en vivo.
    // -------------------------------------------------------------------------------------

    function validacion() {
      return N.validarNotas(R.valor(modelo(), "notas"), FUENTE, CATALOGO);
    }

    function refrescar() {
      if (!cajaProblemas) return;
      const v = validacion();
      for (const m of marcables) {
        const marca = "adicionales[" + m.indice + "]";
        m.nodo.classList.toggle("invalido", v.errores.some((e) => e.includes(marca + ":") ||
          e.includes(marca + ".") || e.includes("(" + marca + ")")));
        // Repetida de un .txt de "archivos": en amarillo, con el aviso debajo de la nota.
        const repetida = v.avisos.find((a) => a.startsWith("rotulo.notas." + marca + ": esta nota ya viene en "));
        m.nodo.classList.toggle("repetida", !!repetida);
        m.aviso.textContent = repetida ? repetida.slice(repetida.indexOf("esta nota")) : "";
        m.aviso.hidden = !repetida;
      }
      const filas = v.errores.map((e) => nodo("li", { class: "error" }, e))
        .concat(v.avisos.map((a) => nodo("li", { class: "aviso" }, a)));
      if (!filas.length) filas.push(nodo("li", { class: "ninguna" }, "Sin problemas en las notas."));
      cajaProblemas.replaceChildren(...filas);
    }

    function pintar() {
      marcables = [];
      crecientes = [];
      if (!DATOS || !TIENE_CAMPO) {
        panel.replaceChildren(nodo("div", { class: "vacio" }, "El formato no tiene campo de notas."));
        cajaProblemas = null;
        return;
      }
      cajaProblemas = nodo("ul", { class: "advertencias problemas-rotulo" });
      panel.replaceChildren(seccionPlano(), seccionAMano(), seccionCatalogo(),
        nodo("div", { class: "subtitulo" }, "Problemas de las notas"), cajaProblemas,
        nodo("div", { class: "medida" }, "Si las notas caben en su celda lo dice componer (el editor todavía no lo calcula)."));
      for (const [caja, max] of crecientes) crecer(caja, max);
      refrescar();
    }

    return { reiniciar, pintar, refrescar, validacion, items: () => estado.items };
  }

  raiz.EditorPanelNotas = { crear };
})(typeof self !== "undefined" ? self : this);
