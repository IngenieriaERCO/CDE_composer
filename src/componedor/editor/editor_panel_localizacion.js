/*
 * Editor de planos — «Cargar imagen de localización» (panel debajo del Rótulo). Solo pantalla: la
 * lógica está en editor_localizacion.js y la conexión en editor_servidor.js; la imagen en la hoja
 * la dibuja editor_ui.js.
 *
 * - La imagen (PNG o JPG de QGIS) la elige el cuadro nativo del servidor; si el plano ya tiene
 *   una, el cuadro se abre en su carpeta. El plano guarda {archivo, bytes, modificado} en el
 *   campo de tipo "imagen" del rótulo; la imagen nunca va dentro del plano.json.
 * - Si lo elegido no coincide con lo del plano (nombre, tamaño o fecha), el plano no cambia: se
 *   avisa y se ofrece «Usar la cargada en el plano».
 * - Con imagen y la escala de localización vacía: aviso amarillo (en el PDF sale «DEFINIR»).
 * - Sin servidor: se ve qué imagen usa el plano y se conserva al guardar, pero no se dibuja.
 *
 * window.EditorPanelLocalizacion (lo usa editor_ui.js):
 *   imagen() → {url, px} si la cargada es la del plano; null si no.
 *   repintar(), alCambiarRotulo().
 */
(function () {
  "use strict";

  const S = window.EditorServidor;
  const LO = window.EditorLocalizacion;
  const panel = document.getElementById("panel-localizacion");
  if (!panel) return;
  const UI = () => window.EditorUI || null;
  const DATOS = JSON.parse(document.getElementById("datos-editor").textContent);
  const CAMPO = LO.campoImagen(DATOS.rotulo && DATOS.rotulo.definicion);
  const conexion = S.detectar(window.location);
  const cliente = conexion ? S.crearCliente(conexion, window.fetch.bind(window)) : null;
  const vista = { ficha: null, url: null, error: null, ocupado: false };
  window.EditorPruebaLocalizacion = { vista };

  function nodo(nombre, atributos, texto) {
    const n = document.createElement(nombre);
    for (const [k, v] of Object.entries(atributos || {})) n.setAttribute(k, v);
    if (texto !== undefined) n.textContent = texto;
    return n;
  }

  const valorPlano = () => (UI() && CAMPO ? UI().rotuloValor(CAMPO.nombre) : undefined);
  const escala = () => (UI() && CAMPO && CAMPO.campo_escala ? UI().rotuloValor(CAMPO.campo_escala) : undefined);
  const esLaDelPlano = () => {
    const v = valorPlano();
    return !!(v && vista.ficha && !vista.ficha.cambio && LO.diferencias(v, vista.ficha).length === 0);
  };

  function imagen() {
    return esLaDelPlano() && vista.url ? { url: vista.url, px: vista.ficha.px } : null;
  }

  async function bajarImagen() {
    if (vista.url) URL.revokeObjectURL(vista.url);
    vista.url = null;
    if (!vista.ficha || vista.ficha.cambio) return;
    try {
      vista.url = URL.createObjectURL(await cliente.imagenLocalizacion());
    } catch (err) {
      vista.error = err.message;
    }
  }

  function fijar(valor) {
    UI().cambiarRotulo(CAMPO.nombre, valor);
    pintar();
  }

  function pintar() {
    if (!CAMPO) {
      panel.replaceChildren(nodo("p", { class: "ayuda" }, "El formato no tiene recuadro de imagen de localización."));
      return;
    }
    const v = valorPlano();
    const hijos = [];
    if (vista.error) hijos.push(nodo("div", { class: "aviso-ortofoto error" }, vista.error));
    if (!conexion) {
      hijos.push(nodo("p", { class: "ayuda" }, (v ? "El plano usa la imagen «" + v.archivo + "». " : "Sin imagen. ") +
        "Para cargar una, abra el editor con «Abrir editor.bat»; con doble clic se conserva al guardar, pero no se dibuja."));
      panel.replaceChildren(...hijos);
      return;
    }
    const boton = nodo("button", { type: "button", id: "btn-cargar-localizacion" },
      vista.ocupado ? "Eligiendo imagen…" : "Cargar imagen de localización");
    if (vista.ocupado) boton.disabled = true;
    boton.title = "Un PNG o JPG exportado de QGIS: va entero en el recuadro de Localización, centrado, a ~" + CAMPO.ppp + " ppp";
    boton.addEventListener("click", cargar);
    hijos.push(boton);
    if (vista.ficha) {
      const ficha = nodo("div", { class: "ficha-ortofoto" });
      for (const l of LO.lineasFicha(CAMPO, vista.ficha)) ficha.appendChild(nodo("div", {}, l));
      hijos.push(ficha);
      if (vista.ficha.cambio) hijos.push(nodo("div", { class: "aviso-ortofoto error" }, "La imagen cambió en el disco desde que se cargó: vuelva a cargarla."));
    }
    if (v && vista.ficha && !esLaDelPlano() && !vista.ficha.cambio) {
      const aviso = nodo("div", { class: "aviso-ortofoto elegir" }, "La imagen elegida no coincide con la del plano («" + v.archivo + "»):");
      const lista = nodo("ul");
      for (const d of LO.diferencias(v, vista.ficha)) lista.appendChild(nodo("li", {}, d));
      aviso.appendChild(lista);
      const usar = nodo("button", { type: "button", id: "btn-usar-localizacion" }, "Usar la cargada en el plano");
      usar.addEventListener("click", () => fijar(LO.valorParaPlano(vista.ficha)));
      aviso.appendChild(usar);
      hijos.push(aviso);
    } else if (v && !vista.ficha) {
      hijos.push(nodo("p", { class: "ayuda" }, "El plano usa la imagen «" + v.archivo + "»: cárguela con el botón para verla."));
    } else if (!v && vista.ficha) {
      const usar = nodo("button", { type: "button", id: "btn-usar-localizacion" }, "Usar en este plano");
      usar.addEventListener("click", () => fijar(LO.valorParaPlano(vista.ficha)));
      hijos.push(nodo("div", { class: "aviso-ortofoto info" }, "Esta imagen no está en el plano."), usar);
    }
    if (v && LO.escalaVacia(escala())) hijos.push(nodo("div", { class: "aviso-ortofoto elegir", id: "aviso-escala-localizacion" }, LO.AVISO_ESCALA));
    if (v) {
      const quitar = nodo("button", { type: "button", id: "btn-quitar-localizacion" }, "Quitar imagen de localización");
      quitar.addEventListener("click", () => {
        if (!window.confirm("¿Quitar la imagen de localización del plano? (El archivo no se toca.)")) return;
        fijar(undefined);
      });
      hijos.push(quitar);
    }
    panel.replaceChildren(...hijos);
  }

  async function cargar() {
    if (vista.ocupado) return;
    vista.ocupado = true;
    pintar();
    try {
      const anterior = valorPlano();
      const r = await cliente.elegirLocalizacion(anterior ? anterior.archivo : null);
      if (r.elegida) {
        vista.ficha = r.localizacion;
        vista.error = null;
        await bajarImagen();
        // Si el plano ya tenía otra (no coincide), no se cambia: pintar() lo avisa.
        if (!anterior || LO.diferencias(anterior, vista.ficha).length === 0) {
          UI().cambiarRotulo(CAMPO.nombre, LO.valorParaPlano(vista.ficha));
        }
      }
    } catch (err) {
      vista.error = err.message;
    } finally {
      vista.ocupado = false;
      pintar();
      if (UI()) UI().refrescar();
    }
  }

  window.EditorPanelLocalizacion = { imagen, repintar: pintar, alCambiarRotulo: pintar };

  async function inicio() {
    if (cliente) {
      try {
        const r = await cliente.localizacion();
        vista.ficha = r.localizacion;
        await bajarImagen();
      } catch (err) {
        vista.error = err.message;
      }
    }
    pintar();
    if (UI()) UI().refrescar();
  }
  inicio();
})();
