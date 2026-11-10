/*
 * Editor de planos — panel «Convenciones» (subfase 4.3d). Solo pantalla: las reglas están en
 * editor_convenciones.js (EditorConvenciones) y el modelo en editor_rotulo.js (EditorRotulo).
 *
 * - Símbolos del índice (miniaturas PNG incrustadas, con su opacidad) con una casilla: marcar =
 *   al final de «Convenciones del plano»; desmarcar = sale. Sin repetir; tope = capacidad.
 * - «Convenciones del plano»: casilla de la leyenda en vivo (columna y fila), ↑ ↓ ✕ y la
 *   descripción editable (vacía = la de por defecto).
 * Se guarda en rotulo.convenciones.
 */
(function (raiz) {
  "use strict";

  /** opciones: {panel, datos (DATOS.rotulo), modelo(), alCambiar()}. */
  function crear(opciones) {
    const R = raiz.EditorRotulo;
    const C = raiz.EditorConvenciones;
    const F = raiz.EditorFormularios;
    const panel = opciones.panel;
    const DATOS = opciones.datos;
    const DEF = DATOS ? DATOS.definicion : null;
    const CAMPO = C.campo(DEF);
    const SIMBOLOS = DATOS ? DATOS.simbolos : [];
    const FUENTE = DATOS ? DATOS.fuente : null;
    let estado = { items: [], editable: true };
    let marcables = [];
    let cajaProblemas = null;
    let ultimoAviso = "";

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

    function miniatura(id) {
      const s = SIMBOLOS.find((x) => x.id === id);
      const caja = nodo("div", { class: "miniatura-simbolo" });
      if (s && s.imagen && s.imagen.data_url) {
        const img = nodo("img", { alt: id, title: id + (s.opacidad < 1 ? " (opacidad " + s.opacidad + ")" : "") });
        img.src = s.imagen.data_url;
        caja.appendChild(img);
      } else {
        caja.appendChild(nodo("span", { class: "medida" }, "?"));
      }
      return caja;
    }

    function reiniciar() {
      estado = C.lista(CAMPO ? R.valor(modelo(), CAMPO.nombre) : undefined, SIMBOLOS);
      ultimoAviso = "";
      pintar();
    }

    function guardar() {
      R.cambiar(modelo(), CAMPO.nombre, C.convencionesParaGuardar(estado.items, SIMBOLOS));
      opciones.alCambiar();
    }

    function cambiarLista(items) {
      estado.items = items;
      guardar();
      pintar();
    }

    // -------------------------------------------------------------------------------------

    function seccionPlano() {
      const s = nodo("details", { class: "seccion" });
      s.open = true;
      s.appendChild(nodo("summary", {}, "Convenciones del plano (" + estado.items.length + " de " + CAMPO.capacidad + ")"));
      if (!estado.editable) {
        s.appendChild(nodo("div", { class: "medida" }, "Las convenciones del plano tienen una forma que el editor no sabe mostrar: se conservan sin editar."));
        return s;
      }
      if (ultimoAviso) s.appendChild(nodo("div", { class: "nota-detalle" }, ultimoAviso));
      estado.items.forEach((item, i) => {
        const pos = C.casilla(i, CAMPO.capacidad);
        const tarjeta = nodo("div", { class: "convencion-plano" + (item.conocido ? "" : " desconocida") });
        const cabeza = nodo("div", { class: "cabeza" });
        cabeza.appendChild(nodo("strong", { class: "numero", title: "Casilla " + pos.numero + " de la leyenda" }, pos.numero + "."));
        cabeza.appendChild(miniatura(item.simbolo));
        cabeza.appendChild(nodo("span", { class: "medida origen" }, pos.dentro
          ? "columna " + pos.columna + ", fila " + pos.fila : "no cabe (más de " + CAMPO.capacidad + ")"));
        for (const [texto, titulo, accion, deshabilitado] of [
          ["↑", "Subir", () => cambiarLista(C.mover(estado.items, i, -1)), i === 0],
          ["↓", "Bajar", () => cambiarLista(C.mover(estado.items, i, 1)), i === estado.items.length - 1],
          ["✕", "Quitar del plano", () => cambiarLista(C.quitar(estado.items, i)), false],
        ]) {
          const b = nodo("button", { type: "button", title: titulo, class: texto === "✕" ? "mini quitar" : "mini" }, texto);
          b.disabled = deshabilitado;
          b.addEventListener("click", accion);
          cabeza.appendChild(b);
        }
        tarjeta.appendChild(cabeza);
        tarjeta.appendChild(nodo("div", { class: "id-simbolo" }, item.simbolo +
          (item.conocido ? "" : " — símbolo desconocido (no está en el índice; se conserva)")));
        const s0 = SIMBOLOS.find((x) => x.id === item.simbolo);
        const entrada = nodo("textarea", { rows: "2", title: "Descripción (hasta 2 líneas). Vacía = la de por defecto." });
        entrada.value = F.textoDeValor(item.descripcion);
        if (s0) entrada.placeholder = s0.descripcion + " (por defecto)";
        entrada.addEventListener("input", () => {
          estado.items[i] = C.cambiarDescripcion(estado.items[i], entrada.value, SIMBOLOS);
          guardar();
          refrescar();
        });
        marcables.push({ nodo: entrada, indice: i });
        tarjeta.appendChild(entrada);
        s.appendChild(tarjeta);
      });
      if (!estado.items.length) s.appendChild(nodo("div", { class: "vacio" }, "Ninguna: marque símbolos abajo."));
      return s;
    }

    function seccionSimbolos() {
      const s = nodo("details", { class: "seccion" });
      s.open = true;
      s.appendChild(nodo("summary", {}, "Símbolos disponibles (" + SIMBOLOS.length + ")"));
      for (const aviso of DATOS.avisos.filter((a) => a.startsWith("convenciones"))) {
        s.appendChild(nodo("div", { class: "nota-detalle" }, aviso));
      }
      const elegidos = new Set(estado.items.map((x) => x.simbolo));
      const llena = estado.items.length >= CAMPO.capacidad;
      for (const sim of SIMBOLOS) {
        const fila = nodo("label", { class: "simbolo-catalogo" });
        const casilla = nodo("input", { type: "checkbox" });
        casilla.checked = elegidos.has(sim.id);
        casilla.disabled = !estado.editable;
        casilla.title = casilla.checked ? "Quitar del plano" : (llena ? "La tabla está llena (" + CAMPO.capacidad + ")" : "Agregar al plano");
        casilla.addEventListener("change", () => {
          if (casilla.checked) {
            const r = C.marcar(estado.items, sim.id, SIMBOLOS, CAMPO.capacidad);
            ultimoAviso = r.aviso;
            cambiarLista(r.items);
          } else {
            ultimoAviso = "";
            cambiarLista(C.desmarcar(estado.items, sim.id));
          }
        });
        const texto = nodo("div", { class: "texto-nota" });
        texto.appendChild(nodo("div", {}, sim.descripcion));
        texto.appendChild(nodo("div", { class: "id-simbolo" }, sim.id + (sim.opacidad < 1 ? " · opacidad " + sim.opacidad : "")));
        fila.append(casilla, miniatura(sim.id), texto);
        s.appendChild(fila);
      }
      if (!SIMBOLOS.length) s.appendChild(nodo("div", { class: "vacio" }, "El editor no trae símbolos (falta la biblioteca)."));
      return s;
    }

    function validacion() {
      return C.validarConvenciones(R.valor(modelo(), CAMPO.nombre), DEF, FUENTE, SIMBOLOS);
    }

    function refrescar() {
      if (!cajaProblemas) return;
      const v = validacion();
      for (const m of marcables) {
        const marca = "convenciones[" + m.indice + "]";
        const ruta = "campo 'convenciones." + (m.indice + 1) + ".descripcion'";
        m.nodo.classList.toggle("invalido", v.errores.some((e) => e.includes(marca + ".") || e.includes(marca + ":") || e.startsWith(ruta)));
      }
      const filas = v.errores.map((e) => nodo("li", { class: "error" }, e))
        .concat(v.avisos.map((a) => nodo("li", { class: "aviso" }, a)));
      if (!filas.length) filas.push(nodo("li", { class: "ninguna" }, "Sin problemas en las convenciones."));
      cajaProblemas.replaceChildren(...filas);
    }

    function pintar() {
      marcables = [];
      if (!DATOS || !CAMPO) {
        panel.replaceChildren(nodo("div", { class: "vacio" }, "El formato no tiene campo de convenciones."));
        cajaProblemas = null;
        return;
      }
      cajaProblemas = nodo("ul", { class: "advertencias problemas-rotulo" });
      panel.replaceChildren(seccionPlano(), seccionSimbolos(),
        nodo("div", { class: "subtitulo" }, "Problemas de las convenciones"), cajaProblemas,
        nodo("div", { class: "medida" }, "Si cada descripción cabe en su casilla lo dice componer (el editor todavía no lo calcula)."));
      refrescar();
    }

    return { reiniciar, pintar, refrescar, validacion, items: () => estado.items };
  }

  raiz.EditorPanelConvenciones = { crear };
})(typeof self !== "undefined" ? self : this);
