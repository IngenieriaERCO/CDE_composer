/*
 * Editor de planos — «Cargar ortofoto» (etapa 1): botón, ficha con avisos, sistemas de
 * coordenadas, opacidad y vistas previas detrás de cada detalle. Solo pantalla: la lógica está
 * en editor_ortofoto.js, la conexión en editor_servidor.js y la capa en la hoja en editor_ui.js.
 *
 * - El GeoTIFF lo elige el cuadro nativo del servidor (el editor nunca manda rutas). El servidor
 *   lee solo la cabecera y devuelve la ficha.
 * - El plano guarda la ortofoto en "ortofoto" (versión 4). Sin servidor (doble clic en
 *   editor.html) se ve qué ortofoto usa el plano y se guarda igual, pero no se dibuja.
 * - Sistemas: el del dibujo SIEMPRE lo elige el usuario (el DXF no lo informa todavía); el de la
 *   ortofoto, solo si el archivo no trae el suyo. Nunca se supone ninguno.
 * - «Cargar ortofoto» abre el cuadro en la carpeta de la ortofoto del plano (el servidor recibe
 *   esa ruta solo para eso). Si lo elegido no coincide con el plano (nombre, tamaño o fecha), no
 *   se cambia el plano: se avisa qué difiere y se ofrece «Usar la cargada en el plano».
 * - Si el DXF cargado trae su sistema (dxf.crs del Exportador) sacado de un Alias del GEODATA,
 *   «Sistema del dibujo» sale prellenado con él (una vez por DXF y ortofoto; siempre editable).
 *   Si no lo trae, o si el código salió del texto de la autoridad (epsg_from "authority"),
 *   queda vacío; el aviso amarillo y «Usar EPSG:… para el dibujo» se muestran igual.
 * - Vistas previas: una por caja CAD (la página de cada detalle), pedidas 250 ms después del
 *   último cambio (al arrastrar el tirador de escala no se pide una por cada paso).
 *
 * window.EditorPanelOrtofoto (lo usa editor_ui.js):
 *   previa(caja, mmPorUnidad, id) → {estado: "lista"|"pidiendo"|"error"|"no", url, cobertura, mensaje}
 *   alCambiarPlano() → repinta el estado por detalle.
 */
(function () {
  "use strict";

  const S = window.EditorServidor;
  const O = window.EditorOrtofoto;
  const boton = document.getElementById("btn-cargar-ortofoto");
  const panel = document.getElementById("panel-ortofoto");
  const conexion = S.detectar(window.location);
  const UI = () => window.EditorUI || null;
  const ESPERA_MS = 250;
  const SIN_SERVIDOR = "Para cargar una ortofoto, abra el editor con «Abrir editor.bat» (servidor local). " +
    "Con doble clic en editor.html, la ortofoto del plano se conserva al guardar, pero no se dibuja.";

  const vista = { estado: null, ocupado: false, error: null }; // estado: el del servidor (ficha…)
  const previas = new Map(); // clave → {estado, url, cobertura, mensaje}
  const esperando = new Map(); // id del detalle → {clave, temporizador}
  const porDetalle = new Map(); // id del detalle → última clave pedida
  window.EditorPruebaOrtofoto = { vista, previas, conexion };

  function nodo(nombre, atributos, texto) {
    const n = document.createElement(nombre);
    for (const [k, v] of Object.entries(atributos || {})) n.setAttribute(k, v);
    if (texto !== undefined) n.textContent = texto; // nunca HTML: los nombres vienen del archivo
    return n;
  }

  const planoOrtofoto = () => (UI() ? UI().ortofoto() : null);
  /** El sistema del DXF cargado ({codigo, nombre}) o null. */
  function crsDxf() {
    const panelDxf = window.EditorPanelDxf;
    const c = panelDxf && panelDxf.catalogo ? panelDxf.catalogo() : null;
    return (c && c.dxf && c.dxf.crs) || null;
  }
  const prellenados = new Set(); // "sha256 del DXF|archivo de la ortofoto" ya prellenados

  /** Si el plano no tiene sistema del dibujo y el DXF trae el suyo, se pone (una sola vez). */
  function prellenar() {
    const o = planoOrtofoto();
    const crs = crsDxf();
    const panelDxf = window.EditorPanelDxf;
    const c = panelDxf && panelDxf.catalogo ? panelDxf.catalogo() : null;
    // Solo un código que sirve y que salió de un Alias del GEODATA (no del texto de la autoridad).
    if (!o || o.crs_dibujo || !crs || !crs.oficial || crs.prellenar === false || !c) return false;
    const clave = c.dxf.sha256 + "|" + o.archivo;
    if (prellenados.has(clave)) return false;
    prellenados.add(clave);
    cambiarPlano({ crs_dibujo: crs.codigo });
    return true;
  }
  const cliente = conexion ? S.crearCliente(conexion, window.fetch.bind(window)) : null;

  // ---------------------------------------------------------------------------------------
  // Vistas previas.
  // ---------------------------------------------------------------------------------------

  function olvidarPrevias() {
    for (const p of previas.values()) if (p.url) URL.revokeObjectURL(p.url);
    previas.clear();
    for (const e of esperando.values()) clearTimeout(e.temporizador);
    esperando.clear();
    porDetalle.clear();
  }

  /** ¿Se pueden pedir? La ortofoto cargada es la del plano y los sistemas están elegidos. */
  function lista() {
    const o = planoOrtofoto();
    return !!(vista.estado && o && O.esLaDelPlano(o, vista.estado) &&
      O.listaParaPrevias(vista.estado.ficha, o, vista.estado.cambio));
  }

  function previa(caja, mmPorUnidad, id) {
    if (!cliente || !lista()) return { estado: "no" };
    const o = planoOrtofoto();
    const propio = !!vista.estado.ficha.sistema;
    const k = O.clavePrevia(caja, mmPorUnidad, o.crs_dibujo, propio ? null : o.crs);
    if (id !== undefined) porDetalle.set(id, k);
    if (previas.has(k)) return previas.get(k);
    const clave = id === undefined ? k : id;
    const antes = esperando.get(clave);
    if (!antes || antes.clave !== k) {
      if (antes) clearTimeout(antes.temporizador);
      const cuerpo = { caja_cad: caja, mm_por_unidad: mmPorUnidad, crs_dibujo: o.crs_dibujo,
        crs_ortofoto: propio ? null : o.crs, px: O.LADO_PX };
      esperando.set(clave, { clave: k, temporizador: setTimeout(() => {
        esperando.delete(clave);
        pedir(k, cuerpo);
      }, ESPERA_MS) });
    }
    return { estado: "pidiendo" };
  }

  async function pedir(k, cuerpo) {
    if (previas.has(k)) return;
    const e = { estado: "pidiendo", url: null, cobertura: null, mensaje: null, caja: cuerpo.caja_cad };
    previas.set(k, e);
    try {
      const r = await cliente.previaOrtofoto(cuerpo);
      if (!/^\/api\/ortofoto\/previas\/o-\d+$/.test(r.url)) throw new Error("respuesta inesperada del servidor");
      const blob = await cliente.png(r.url);
      if (previas.get(k) !== e) return; // se olvidó mientras tanto
      e.url = URL.createObjectURL(blob);
      e.cobertura = r.cobertura;
      e.estado = "lista";
    } catch (err) {
      if (previas.get(k) !== e) return;
      e.estado = "error";
      e.mensaje = err.message;
      if (err.estadoHttp === 409) await refrescarEstado(); // cambió en el disco, etc.
    }
    if (UI()) UI().refrescar();
  }

  // ---------------------------------------------------------------------------------------
  // Panel.
  // ---------------------------------------------------------------------------------------

  /** El selector de un sistema: los comunes + «Otro (EPSG)…» con un cuadro de texto. */
  function selectorSistema(etiqueta, valor, alCambiar, idBase) {
    const caja = nodo("div", { class: "campo-sistema" });
    caja.appendChild(nodo("label", { for: idBase }, etiqueta));
    const sel = nodo("select", { id: idBase });
    sel.appendChild(nodo("option", { value: "" }, "— elija el sistema —"));
    const comunes = (vista.estado && vista.estado.sistemas) || [];
    for (const s of comunes) sel.appendChild(nodo("option", { value: s.codigo }, s.codigo + " · " + s.nombre));
    sel.appendChild(nodo("option", { value: "otro" }, "Otro (código EPSG)…"));
    const otro = nodo("input", { type: "text", id: idBase + "-otro", placeholder: "p. ej. EPSG:6247", hidden: "" });
    const esComun = comunes.some((s) => s.codigo === valor);
    sel.value = !valor ? "" : esComun ? valor : "otro";
    if (valor && !esComun) {
      otro.hidden = false;
      otro.value = valor;
    }
    sel.addEventListener("change", () => {
      if (sel.value === "otro") {
        otro.hidden = false;
        otro.focus();
        return;
      }
      otro.hidden = true;
      alCambiar(sel.value || null);
    });
    otro.addEventListener("change", () => {
      const codigo = O.leerSistema(otro.value);
      if (!codigo && otro.value.trim()) {
        otro.setCustomValidity("Escriba un código EPSG, p. ej. EPSG:6247.");
        otro.reportValidity();
        return;
      }
      otro.setCustomValidity("");
      if (codigo) otro.value = codigo;
      alCambiar(codigo);
    });
    caja.append(sel, otro);
    return caja;
  }

  function cambiarPlano(cambios) {
    const o = Object.assign({}, planoOrtofoto(), cambios);
    olvidarPrevias();
    UI().fijarOrtofoto(o);
    pintar();
  }

  const estadoDetalles = nodo("ul", { class: "ortofoto-detalles" });

  function pintarDetalles() {
    estadoDetalles.replaceChildren();
    if (!UI() || !lista()) return;
    for (const r of UI().cajasOrtofoto()) {
      let texto;
      if (!r.caja) {
        texto = r.motivo;
      } else {
        const k = porDetalle.get(r.id);
        const p = k ? previas.get(k) : null;
        texto = !p ? "pidiendo la ortofoto…" : p.estado === "lista" ? O.textoCobertura(p.cobertura)
          : p.estado === "error" ? "error: " + p.mensaje : "pidiendo la ortofoto…";
      }
      estadoDetalles.appendChild(nodo("li", {}, r.id + ": " + texto));
    }
  }

  function pintar() {
    const o = planoOrtofoto();
    const hijos = [];
    if (vista.error) hijos.push(nodo("div", { class: "aviso-ortofoto error" }, vista.error));
    if (!conexion) {
      hijos.push(nodo("p", { class: "ayuda" }, o
        ? "El plano usa la ortofoto «" + o.archivo + "» (opacidad " + Math.round(o.opacidad * 100) +
          " %). " + SIN_SERVIDOR
        : SIN_SERVIDOR));
      panel.replaceChildren(...hijos);
      return;
    }
    const e = vista.estado;
    if (!e) {
      hijos.push(nodo("p", { class: "ayuda" }, o
        ? "El plano usa la ortofoto «" + o.archivo + "»: cárguela con «Cargar ortofoto» para verla."
        : "Sin ortofoto. «Cargar ortofoto» elige un GeoTIFF: va detrás de los detalles, recortada a cada uno."));
      if (o) hijos.push(botonQuitar("Quitar la ortofoto del plano"));
      panel.replaceChildren(...hijos);
      return;
    }
    const ficha = nodo("div", { class: "ficha-ortofoto" });
    for (const linea of O.lineasFicha(e.ficha)) ficha.appendChild(nodo("div", {}, linea));
    hijos.push(ficha);
    if (!o) { // cargada en el servidor (p. ej. tras recargar la página), pero no en este plano
      const aviso = nodo("div", { class: "aviso-ortofoto info" }, "Esta ortofoto no está en el plano.");
      const usar = nodo("button", { type: "button", id: "btn-usar-ortofoto" }, "Usar en este plano");
      usar.addEventListener("click", () => cambiarPlano(nuevaParaPlano(null)));
      aviso.appendChild(usar);
      hijos.push(aviso);
      panel.replaceChildren(...hijos);
      return;
    }
    if (!O.esLaDelPlano(o, e)) {
      const aviso = nodo("div", { class: "aviso-ortofoto elegir" }, "La ortofoto elegida no coincide con la del " +
        "plano («" + o.archivo + "»):");
      const lista = nodo("ul");
      for (const d of O.diferencias(o, e)) lista.appendChild(nodo("li", {}, d));
      aviso.appendChild(lista);
      aviso.appendChild(nodo("div", {}, "El plano sigue con la suya. Elija otra con «Cargar ortofoto» o:"));
      const usar = nodo("button", { type: "button" }, "Usar la cargada en el plano");
      usar.addEventListener("click", () => cambiarPlano(nuevaParaPlano(o)));
      aviso.appendChild(usar);
      hijos.push(aviso);
      panel.replaceChildren(...hijos);
      return;
    }
    for (const a of O.avisos(e.ficha, o, e.cambio, crsDxf())) {
      hijos.push(nodo("div", { class: "aviso-ortofoto " + a.nivel }, a.texto));
    }
    const dxf = crsDxf();
    if (dxf && dxf.sugerido && o.crs_dibujo !== dxf.sugerido) {
      const usar = nodo("button", { type: "button", id: "btn-usar-sugerido" }, "Usar " + dxf.sugerido + " para el dibujo");
      usar.addEventListener("click", () => cambiarPlano({ crs_dibujo: dxf.sugerido }));
      hijos.push(usar);
    }
    if (!e.ficha.sistema) {
      hijos.push(selectorSistema("Sistema de la ortofoto", o.crs, (v) => cambiarPlano({ crs: v }), "crs-ortofoto"));
    }
    hijos.push(selectorSistema("Sistema del dibujo (DXF)", o.crs_dibujo, (v) => cambiarPlano({ crs_dibujo: v }),
      "crs-dibujo"));
    const opacidad = nodo("label", { class: "campo-opacidad" }, "Opacidad ");
    const deslizador = nodo("input", { type: "range", min: "0", max: "100", step: "5", id: "opacidad-ortofoto",
      value: String(Math.round(o.opacidad * 100)) });
    const valor = nodo("span", {}, Math.round(o.opacidad * 100) + " %");
    deslizador.addEventListener("input", () => {
      valor.textContent = deslizador.value + " %";
      UI().fijarOrtofoto(Object.assign({}, planoOrtofoto(), { opacidad: Number(deslizador.value) / 100 }));
    });
    opacidad.append(deslizador, valor);
    hijos.push(opacidad);
    hijos.push(estadoDetalles);
    hijos.push(botonQuitar("Quitar ortofoto"));
    panel.replaceChildren(...hijos);
    pintarDetalles();
  }

  function botonQuitar(texto) {
    const b = nodo("button", { type: "button", id: "btn-quitar-ortofoto" }, texto);
    b.addEventListener("click", quitar);
    return b;
  }

  /** La sección del plano para la ortofoto cargada: se conservan el sistema del dibujo y la
   *  opacidad; el de la ortofoto, solo si es la misma y no trae el suyo. */
  function nuevaParaPlano(anterior) {
    const e = vista.estado;
    const misma = anterior && O.esLaDelPlano(anterior, e);
    return { archivo: e.archivo_plano, bytes: e.ficha.bytes, modificado: e.ficha.modificado,
      crs: !e.ficha.sistema && misma ? anterior.crs : null,
      crs_dibujo: anterior ? anterior.crs_dibujo : null,
      opacidad: anterior ? anterior.opacidad : 1 };
  }

  async function quitar() {
    if (!window.confirm("¿Quitar la ortofoto del plano? (El archivo no se toca.)")) return;
    olvidarPrevias();
    if (cliente && vista.estado) {
      try {
        await cliente.quitarOrtofoto();
      } catch (err) {
        vista.error = err.message;
      }
    }
    vista.estado = null;
    UI().fijarOrtofoto(null);
    pintar();
  }

  async function refrescarEstado() {
    try {
      const r = await cliente.ortofoto();
      vista.estado = r.ortofoto;
      vista.error = null;
    } catch (err) {
      vista.error = err.message;
    }
    pintar();
  }

  async function cargar() {
    if (vista.ocupado) return;
    vista.ocupado = true;
    boton.disabled = true;
    boton.textContent = "Eligiendo ortofoto…";
    try {
      const anterior = planoOrtofoto();
      const r = await cliente.elegirOrtofoto(anterior ? anterior.archivo : null);
      if (r.elegida) {
        olvidarPrevias();
        vista.estado = r.ortofoto;
        vista.error = null;
        // Si el plano ya tenía otra (no coincide), el plano no cambia: pintar() lo avisa.
        if (!anterior || O.esLaDelPlano(anterior, vista.estado)) {
          UI().fijarOrtofoto(nuevaParaPlano(anterior));
        }
        prellenar();
      }
    } catch (err) {
      vista.error = err.message;
    } finally {
      vista.ocupado = false;
      boton.disabled = false;
      boton.textContent = "Cargar ortofoto";
      pintar();
    }
  }

  window.EditorPanelOrtofoto = { previa, repintar: pintar,
    alCambiarPlano: () => { if (!prellenar()) pintarDetalles(); } };

  if (!conexion) {
    boton.disabled = true;
    boton.title = SIN_SERVIDOR;
  } else {
    boton.disabled = false;
    boton.title = "Elegir un GeoTIFF para el fondo del plano (detrás de los detalles)";
    boton.addEventListener("click", cargar);
    refrescarEstado();
  }
  pintar();
})();
