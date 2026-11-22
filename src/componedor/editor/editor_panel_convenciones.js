/*
 * Editor de planos — panel «Convenciones» (subfase 4.3d). Solo pantalla: las reglas están en
 * editor_convenciones.js (EditorConvenciones) y el modelo en editor_rotulo.js (EditorRotulo).
 *
 * - Símbolos del índice (miniaturas PNG incrustadas, con su opacidad) con una casilla: marcar =
 *   al final de «Convenciones del plano»; desmarcar = sale. Sin repetir; tope = capacidad.
 * - «Convenciones del plano»: casilla de la leyenda en vivo (columna y fila), ↑ ↓ ✕ y la
 *   descripción editable (vacía = la de por defecto).
 * - Subfase 9a: «+ Línea» y «+ Relleno» agregan una MUESTRA dibujada como vector (color, grosor
 *   y trazo, u opacidad); su descripción es obligatoria. Reglas en editor_muestras.js.
 * Se guarda en rotulo.convenciones.
 */
(function (raiz) {
  "use strict";

  /** opciones: {panel, datos (DATOS.rotulo), modelo(), alCambiar()}. */
  function crear(opciones) {
    const R = raiz.EditorRotulo;
    const C = raiz.EditorConvenciones;
    const MU = raiz.EditorMuestras;
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

    /** Muestra de línea o relleno en pequeño (SVG), como saldrá en el PDF. */
    function miniaturaMuestra(item) {
      const caja = nodo("div", { class: "miniatura-simbolo miniatura-muestra" });
      // El HTML no lleva URLs: el <svg> sale del analizador HTML (que ya le pone su espacio de
      // nombres) y la forma se crea con el espacio de nombres de ese <svg>.
      caja.innerHTML = '<svg viewBox="0 0 15 7" width="60" height="28"></svg>';
      const svg = caja.firstChild;
      const forma = document.createElementNS(svg.namespaceURI, item.tipo === "linea" ? "line" : "rect");
      const atributos = item.tipo === "linea"
        ? { x1: 1, y1: 3.5, x2: 14, y2: 3.5, stroke: item.color, "stroke-width": Math.max(item.grosor_mm, 0.1),
          "stroke-dasharray": item.trazo === "discontinua" ? "2 1" : "none" }
        : { x: 1, y: 0.5, width: 13, height: 6, fill: item.color, "fill-opacity": item.opacidad };
      for (const [k, v] of Object.entries(atributos)) forma.setAttribute(k, v);
      svg.appendChild(forma);
      return caja;
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
        const esMuestra = MU.esMuestra(item.tipo);
        const tarjeta = nodo("div", { class: "convencion-plano" + (item.conocido ? "" : " desconocida") });
        const cabeza = nodo("div", { class: "cabeza" });
        cabeza.appendChild(nodo("strong", { class: "numero", title: "Casilla " + pos.numero + " de la leyenda" }, pos.numero + "."));
        let mini = esMuestra ? miniaturaMuestra(item) : miniatura(item.simbolo);
        cabeza.appendChild(mini);
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
        if (esMuestra) {
          tarjeta.appendChild(nodo("div", { class: "id-simbolo" }, item.tipo === "linea"
            ? "Línea (dibujada como vector)" : "Relleno (dibujado como vector)"));
          const cambiar = (cambios) => {
            estado.items[i] = C.cambiarMuestra(estado.items[i], cambios);
            guardar();
            const nueva = miniaturaMuestra(estado.items[i]);
            mini.replaceWith(nueva);
            mini = nueva;
            refrescar();
          };
          tarjeta.appendChild(controlesMuestra(item, cambiar));
        } else {
          tarjeta.appendChild(nodo("div", { class: "id-simbolo" }, item.simbolo +
            (item.conocido ? "" : " — símbolo desconocido (no está en el índice; se conserva)")));
        }
        const s0 = esMuestra ? null : SIMBOLOS.find((x) => x.id === item.simbolo);
        const entrada = nodo("textarea", { rows: "2", title: esMuestra
          ? "Descripción (hasta 2 líneas). Obligatoria: una línea o un relleno no tiene descripción por defecto."
          : "Descripción (hasta 2 líneas). Vacía = la de por defecto." });
        entrada.value = F.textoDeValor(item.descripcion);
        if (s0) entrada.placeholder = s0.descripcion + " (por defecto)";
        if (esMuestra) entrada.placeholder = "Escriba la descripción (obligatoria)";
        entrada.addEventListener("input", () => {
          estado.items[i] = C.cambiarDescripcion(estado.items[i], entrada.value, SIMBOLOS);
          guardar();
          refrescar();
        });
        const junto = nodo("ul", { class: "advertencias problemas-rotulo junto-campo" });
        junto.hidden = true;
        marcables.push({ nodo: entrada, indice: i, junto });
        tarjeta.append(entrada, junto);
        s.appendChild(tarjeta);
      });
      if (!estado.items.length) s.appendChild(nodo("div", { class: "vacio" }, "Ninguna: marque símbolos abajo o agregue una línea o un relleno."));
      const botones = nodo("div", { class: "agregar-muestra" });
      const llena = estado.items.length >= CAMPO.capacidad;
      for (const [tipo, texto] of [["linea", "+ Línea"], ["relleno", "+ Relleno"]]) {
        const b = nodo("button", { type: "button", "data-tipo": tipo,
          title: llena ? "La tabla está llena (" + CAMPO.capacidad + ")" : "Agregar una muestra de " + (tipo === "linea" ? "línea" : "relleno") + " (vector)" }, texto);
        b.disabled = llena;
        b.addEventListener("click", () => {
          const r = C.agregarMuestra(estado.items, tipo, CAMPO.capacidad);
          ultimoAviso = r.aviso;
          cambiarLista(r.items);
        });
        botones.appendChild(b);
      }
      s.appendChild(botones);
      return s;
    }

    /** Color y grosor + trazo (línea) u opacidad (relleno). `cambiar(cambios)` guarda. */
    function controlesMuestra(item, cambiar) {
      const fila = nodo("div", { class: "controles-muestra" });
      const color = nodo("input", { type: "color", title: "Color de la muestra" });
      color.value = item.color.toLowerCase();
      color.addEventListener("input", () => cambiar({ color: color.value.toUpperCase() }));
      fila.appendChild(nodo("label", {}, "Color ")).appendChild(color);
      if (item.tipo === "linea") {
        const grosor = nodo("input", { type: "number", min: String(MU.GROSOR_MIN_MM), max: String(MU.GROSOR_MAX_MM),
          step: "0.05", title: "Grosor de la línea en mm (" + MU.GROSOR_MIN_MM + " a " + MU.GROSOR_MAX_MM + ")" });
        grosor.value = String(item.grosor_mm);
        grosor.addEventListener("change", () => {
          const v = Number(grosor.value);
          if (grosor.value !== "" && Number.isFinite(v)) cambiar({ grosor_mm: v });
        });
        fila.appendChild(nodo("label", {}, "Grosor (mm) ")).appendChild(grosor);
        const trazo = nodo("select", { title: "Trazo de la línea" });
        for (const t of MU.TRAZOS) {
          const o = nodo("option", { value: t }, t === "continua" ? "Continua" : "Discontinua");
          if (t === item.trazo) o.selected = true;
          trazo.appendChild(o);
        }
        trazo.addEventListener("change", () => cambiar({ trazo: trazo.value }));
        fila.appendChild(nodo("label", {}, "Trazo ")).appendChild(trazo);
      } else {
        const opacidad = nodo("input", { type: "number", min: "0.05", max: "1", step: "0.05",
          title: "Opacidad del relleno (1 = opaco)" });
        opacidad.value = String(item.opacidad);
        opacidad.addEventListener("change", () => {
          const v = Number(opacidad.value);
          if (opacidad.value !== "" && Number.isFinite(v)) cambiar({ opacidad: v });
        });
        fila.appendChild(nodo("label", {}, "Opacidad ")).appendChild(opacidad);
      }
      return fila;
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
        // 4.3e: «no cabe» (rojo) y «se escribió a X mm» (ámbar) de esta descripción, debajo de ella.
        const propios = F.mensajesDeCampo(v, [ruta]);
        m.nodo.classList.toggle("reducido", !m.nodo.classList.contains("invalido") && propios.avisos.length > 0);
        m.junto.replaceChildren(...propios.errores.map((e) => nodo("li", { class: "error" }, e)),
          ...propios.avisos.map((a) => nodo("li", { class: "aviso" }, a)));
        m.junto.hidden = !m.junto.children.length;
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
        nodo("div", { class: "medida" }, "El editor mide cada descripción con la fuente del rótulo (como componer); componer lo vuelve a comprobar."));
      refrescar();
    }

    return { reiniciar, pintar, refrescar, validacion, items: () => estado.items };
  }

  raiz.EditorPanelConvenciones = { crear };
})(typeof self !== "undefined" ? self : this);
