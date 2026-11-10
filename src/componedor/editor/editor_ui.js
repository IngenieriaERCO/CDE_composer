/*
 * Editor de planos — interfaz (SVG + DOM). Toda la geometría y las reglas están en
 * editor_logica.js (EditorLogica); aquí solo se dibuja y se responde al usuario.
 *
 * El lienzo SVG usa como unidades los píxeles de plantilla.png (Y hacia abajo); los mm de
 * papel (Y hacia arriba) se convierten SOLO con EditorLogica.papelAPantalla/pantallaAPapel.
 */
(function () {
  "use strict";

  const L = window.EditorLogica;
  const DATOS = JSON.parse(document.getElementById("datos-editor").textContent);
  const svg = document.getElementById("hoja");
  const NS = svg.namespaceURI; // namespace del SVG en línea (sin escribir ninguna URL)
  const ESCALA = L.escalaDeImagen(DATOS.hoja, DATOS.imagen_plantilla);
  const ZONA = L.zonaEditable(DATOS);
  const ANCHO_PX = DATOS.imagen_plantilla.ancho_px;
  const ALTO_PX = DATOS.imagen_plantilla.alto_px;
  const CATALOGO = DATOS.detalles;
  // Rosa de los vientos (subfase 4.1): null si el formato no la declara (datos anteriores).
  const ROSA = DATOS.rosa_vientos || null;
  const ROSA_ORIGEN = ROSA ? [ROSA.rect_mm[0], ROSA.rect_mm[1]] : null;
  // Rótulo (subfase 4.3a): definición, catálogo de notas, símbolos y anchos de la fuente.
  // null con datos anteriores o con un formato sin sección "rotulo".
  const R = window.EditorRotulo;
  const F = window.EditorFormularios; // formularios del rótulo (4.3b)
  const DATOS_ROTULO = DATOS.rotulo || null;
  const DEFINICION_ROTULO = DATOS_ROTULO ? DATOS_ROTULO.definicion : null;
  // proyecto.json (editor --proyecto): valores que prellenan un plano NUEVO.
  const PRELLENADO = DATOS_ROTULO ? F.valoresProyecto(DATOS_ROTULO.proyecto, DEFINICION_ROTULO) : {};

  const estado = {
    colocaciones: [], // [{id, detalle, pos: [x, y]}], en orden de apilado
    seleccion: null, // id
    rosa: ROSA ? { visible: true, pos: ROSA_ORIGEN.slice() } : null,
    rosaSeleccionada: false,
    // Rótulo (4.3a): modelo que conserva intacto lo que no se toca; plano abierto, para
    // guardarlo idéntico si no se cambia nada.
    rotulo: R.crearModelo(null, DEFINICION_ROTULO),
    original: null,
    paso: 1,
    cambios: false,
    vista: { x: 0, y: 0, ancho: ANCHO_PX, alto: ALTO_PX },
  };
  R.prellenar(estado.rotulo, PRELLENADO); // plano nuevo: los datos del proyecto quedan copiados
  let arrastre = null; // {c, dx, dy} en mm (c: detalle) o {rosa: true, dx, dy}
  let paneo = null; // {x, y, vista} en px de pantalla
  let ultimasAdvertencias = [];

  // ---------------------------------------------------------------------------------------
  // Utilidades
  // ---------------------------------------------------------------------------------------

  function nodoSvg(nombre, atributos, padre) {
    const nodo = document.createElementNS(NS, nombre);
    for (const [clave, valor] of Object.entries(atributos || {})) nodo.setAttribute(clave, valor);
    if (padre) padre.appendChild(nodo);
    return nodo;
  }

  function nodo(nombre, atributos, texto) {
    const n = document.createElement(nombre);
    for (const [clave, valor] of Object.entries(atributos || {})) {
      if (clave === "class") n.className = valor;
      else n.setAttribute(clave, valor);
    }
    if (texto !== undefined) n.textContent = texto;
    return n;
  }

  const mm = (v) => v.toFixed(2).replace(".", ",");
  const mm1 = (v) => v.toFixed(1).replace(".", ",");

  function rectSvg(nodoRect, rectPapel) {
    const r = L.rectPapelAPantalla(rectPapel, ESCALA);
    nodoRect.setAttribute("x", r.x);
    nodoRect.setAttribute("y", r.y);
    nodoRect.setAttribute("width", r.ancho);
    nodoRect.setAttribute("height", r.alto);
    return r;
  }

  let temporizadorMensaje = null;
  function mensaje(texto, tipo) {
    const caja = document.getElementById("mensaje");
    caja.textContent = texto;
    caja.className = "mensaje " + (tipo || "");
    caja.hidden = false;
    clearTimeout(temporizadorMensaje);
    if (tipo !== "error") temporizadorMensaje = setTimeout(() => (caja.hidden = true), 6000);
  }
  document.getElementById("mensaje").addEventListener("click", (e) => (e.currentTarget.hidden = true));

  function marcarCambios() {
    estado.cambios = true;
  }

  // ---------------------------------------------------------------------------------------
  // Capas fijas del lienzo: plantilla, zonas bloqueadas, área de dibujo, elementos fijos.
  // ---------------------------------------------------------------------------------------

  const defs = nodoSvg("defs", {}, svg);
  const rayado = nodoSvg("pattern", { id: "rayado", width: 8, height: 8, patternUnits: "userSpaceOnUse",
    patternTransform: "rotate(45)" }, defs);
  nodoSvg("rect", { width: 8, height: 8, fill: "rgba(107,114,128,0.18)" }, rayado);
  nodoSvg("line", { x1: 0, y1: 0, x2: 0, y2: 8, stroke: "rgba(75,85,99,0.35)", "stroke-width": 3 }, rayado);

  nodoSvg("rect", { x: 0, y: 0, width: ANCHO_PX, height: ALTO_PX, fill: "#fff" }, svg);
  const fondo = nodoSvg("image", { x: 0, y: 0, width: ANCHO_PX, height: ALTO_PX,
    preserveAspectRatio: "none" }, svg);
  fondo.setAttribute("href", DATOS.imagen_plantilla.data_url);

  const capaBloqueos = nodoSvg("g", {}, svg);
  // Solo los datos `zonas` deciden qué está bloqueado: el editor no deduce nada del dibujo.
  for (const zona of DATOS.zonas) {
    if (zona.editable) continue;
    const bloqueo = nodoSvg("rect", { class: "zona-bloqueada" }, capaBloqueos);
    rectSvg(bloqueo, zona.rect_mm);
    nodoSvg("title", {}, bloqueo).textContent = zona.nombre + " (bloqueada)";
  }
  if (ZONA) rectSvg(nodoSvg("rect", { class: "zona-activa" }, svg), ZONA);

  // La rosa va debajo de los detalles, como en el PDF (es parte de la hoja base). plantilla.png
  // ya viene SIN la rosa: se dibuja solo aquí, en su posición actual.
  const capaRosa = nodoSvg("g", {}, svg);

  const capaElementos = nodoSvg("g", {}, svg);
  const nodosElementos = new Map();
  for (const el of DATOS.elementos_plantilla) {
    if (ROSA && el.nombre === L.ROSA) continue; // la rosa se dibuja en capaRosa
    const marco = nodoSvg("rect", { class: "elemento-fijo" }, capaElementos);
    const rect = rectSvg(marco, el.rect_mm);
    const etiqueta = nodoSvg("text", { class: "etiqueta-fijo", x: rect.x, y: rect.y - 3 }, capaElementos);
    etiqueta.textContent = el.nombre + " (fijo)";
    nodosElementos.set(el.nombre, marco);
  }

  const capaDetalles = nodoSvg("g", {}, svg);

  // ---------------------------------------------------------------------------------------
  // Vista: zoom y desplazamiento (viewBox en píxeles de la plantilla).
  // ---------------------------------------------------------------------------------------

  function aplicarVista() {
    const v = estado.vista;
    svg.setAttribute("viewBox", [v.x, v.y, v.ancho, v.alto].join(" "));
  }

  function ajustarVista() {
    const margen = 0.03;
    const caja = svg.getBoundingClientRect();
    const proporcion = caja.width && caja.height ? caja.width / caja.height : ANCHO_PX / ALTO_PX;
    let ancho = ANCHO_PX * (1 + 2 * margen);
    let alto = ALTO_PX * (1 + 2 * margen);
    if (ancho / alto > proporcion) alto = ancho / proporcion;
    else ancho = alto * proporcion;
    estado.vista = { x: (ANCHO_PX - ancho) / 2, y: (ALTO_PX - alto) / 2, ancho, alto };
    aplicarVista();
  }

  function zoom(factor, centro) {
    const v = estado.vista;
    const c = centro || { x: v.x + v.ancho / 2, y: v.y + v.alto / 2 };
    const ancho = Math.min(Math.max(v.ancho / factor, ANCHO_PX * 0.02), ANCHO_PX * 4);
    const real = v.ancho / ancho;
    estado.vista = {
      x: c.x - (c.x - v.x) / real,
      y: c.y - (c.y - v.y) / real,
      ancho: ancho,
      alto: v.alto / real,
    };
    aplicarVista();
  }

  /** Punto del evento en píxeles de la plantilla (unidades del SVG). */
  function puntoSvg(ev) {
    const p = svg.createSVGPoint();
    p.x = ev.clientX;
    p.y = ev.clientY;
    return p.matrixTransform(svg.getScreenCTM().inverse());
  }

  function puntoPapel(ev) {
    const p = puntoSvg(ev);
    return L.pantallaAPapel(p.x, p.y, ESCALA);
  }

  // ---------------------------------------------------------------------------------------
  // Detalles en el lienzo.
  // ---------------------------------------------------------------------------------------

  function colocadosParaAdvertencias() {
    return estado.colocaciones.map((c) => ({
      id: c.id,
      pagina: L.paginaEnPapel(c.detalle, c.pos),
      dibujo: L.dibujoEnPapel(c.detalle, c.pos),
      tiene_fondo: c.detalle.tiene_fondo,
    }));
  }

  /** Estado de la rosa para la lógica: {visible, rect} o null (el formato no tiene rosa). */
  function rosaParaLogica() {
    if (!estado.rosa) return null;
    return { visible: estado.rosa.visible, rect: L.rectRosa(ROSA.rect_mm, estado.rosa.pos) };
  }

  function dibujarRosa(tapada) {
    capaRosa.replaceChildren();
    if (!estado.rosa || !estado.rosa.visible) return; // oculta: desaparece y la zona queda libre
    const rect = L.rectRosa(ROSA.rect_mm, estado.rosa.pos);
    const clases = ["rosa"];
    if (estado.rosaSeleccionada) clases.push("sel");
    const g = nodoSvg("g", { class: clases.join(" ") }, capaRosa);
    const r = L.rectPapelAPantalla(rect, ESCALA);
    if (ROSA.imagen && ROSA.imagen.data_url) {
      const imagen = nodoSvg("image", { x: r.x, y: r.y, width: r.ancho, height: r.alto,
        preserveAspectRatio: "none" }, g);
      imagen.setAttribute("href", ROSA.imagen.data_url);
    }
    const marco = nodoSvg("rect", { class: "elemento-fijo rosa-marco" + (tapada ? " tapado" : "") }, g);
    rectSvg(marco, rect);
    const etiqueta = nodoSvg("text", { class: "etiqueta-fijo", x: r.x, y: r.y - 3 }, g);
    etiqueta.textContent = L.ROSA + " (movible)";
    g.addEventListener("pointerdown", empezarArrastreRosa);
  }

  const ORDEN_NIVEL = { aviso: 1, fuerte: 2, muy_fuerte: 3 };

  function dibujarDetalles(niveles) {
    capaDetalles.replaceChildren();
    for (const c of estado.colocaciones) {
      const clases = ["detalle"];
      if (niveles.has(c.id)) clases.push(niveles.get(c.id));
      if (c.id === estado.seleccion) clases.push("sel");
      const g = nodoSvg("g", { class: clases.join(" "), "data-id": c.id }, capaDetalles);
      const pagina = L.paginaEnPapel(c.detalle, c.pos);
      const r = L.rectPapelAPantalla(pagina, ESCALA);
      const imagen = nodoSvg("image", { x: r.x, y: r.y, width: r.ancho, height: r.alto,
        preserveAspectRatio: "none" }, g);
      imagen.setAttribute("href", c.detalle.miniatura.data_url);
      rectSvg(nodoSvg("rect", { class: "pagina" }, g), pagina);
      rectSvg(nodoSvg("rect", { class: "dibujo" }, g), L.dibujoEnPapel(c.detalle, c.pos));
      const etiqueta = nodoSvg("text", { class: "etiqueta", x: r.x + 3, y: r.y + 11 }, g);
      etiqueta.textContent = c.id;
      g.addEventListener("pointerdown", (ev) => empezarArrastre(ev, c));
    }
  }

  function actualizar() {
    // Mismos elementos que usa componer: la rosa en su posición actual (oculta: no cuenta).
    const elementos = L.elementosVisibles(DATOS.elementos_plantilla, rosaParaLogica());
    const lista = L.advertencias(colocadosParaAdvertencias(), elementos, DATOS.advertencias);
    ultimasAdvertencias = lista;
    const niveles = new Map();
    const tapados = new Set();
    for (const a of lista) {
      for (const id of a.ids) {
        const actual = niveles.get(id);
        if (!actual || ORDEN_NIVEL[a.nivel] > ORDEN_NIVEL[actual]) niveles.set(id, a.nivel);
      }
      if (a.elemento) tapados.add(a.elemento);
    }
    for (const [nombre, rect] of nodosElementos) rect.classList.toggle("tapado", tapados.has(nombre));
    dibujarRosa(tapados.has(L.ROSA));
    dibujarDetalles(niveles);
    pintarRosa();
    pintarPropiedades();
    pintarListaPlano();
    pintarAdvertencias(lista);
    panelRotulo.refrescar(); // ESCALA depende de los detalles colocados
  }

  // ---------------------------------------------------------------------------------------
  // Paneles: catálogo, propiedades, lista del plano, advertencias.
  // ---------------------------------------------------------------------------------------

  function tarjeta(detalle, habilitada) {
    const t = nodo("div", { class: "tarjeta" + (habilitada ? "" : " deshabilitada") });
    const img = nodo("img", { alt: detalle.id });
    img.src = detalle.miniatura.data_url;
    t.appendChild(img);
    const info = nodo("div");
    info.appendChild(nodo("div", { class: "nombre" }, detalle.id));
    info.appendChild(nodo("div", { class: "dato" },
      "1:" + detalle.escala + " · página " + mm(detalle.tamano_pagina_mm[0]) + " × " +
      mm(detalle.tamano_pagina_mm[1]) + " mm"));
    info.appendChild(nodo("div", { class: "dato" }, detalle.cabe ? "Cabe en el área de dibujo" : "NO cabe"));
    const boton = nodo("button", { type: "button" }, "Agregar al plano");
    boton.disabled = !habilitada;
    boton.addEventListener("click", () => agregar(detalle));
    info.appendChild(boton);
    t.appendChild(info);
    if (!habilitada) {
      for (const nota of detalle.notas) t.appendChild(nodo("div", { class: "nota-detalle" }, nota));
    }
    return t;
  }

  function pintarCatalogo() {
    const disponibles = document.getElementById("catalogo");
    const noCaben = document.getElementById("no-caben");
    const rechazados = document.getElementById("rechazados");
    const caben = CATALOGO.filter((d) => d.cabe);
    const fuera = CATALOGO.filter((d) => !d.cabe);
    disponibles.replaceChildren(...caben.map((d) => tarjeta(d, true)));
    noCaben.replaceChildren(...fuera.map((d) => tarjeta(d, false)));
    rechazados.replaceChildren(...DATOS.rechazados.map((r) => {
      const caja = nodo("div", { class: "rechazado" });
      caja.appendChild(nodo("div", { class: "nombre" }, r.prefijo));
      const ul = nodo("ul");
      for (const m of r.motivos) ul.appendChild(nodo("li", {}, m));
      caja.appendChild(ul);
      return caja;
    }));
    if (!caben.length) disponibles.appendChild(nodo("div", { class: "vacio" }, "Ninguno."));
    if (!fuera.length) noCaben.appendChild(nodo("div", { class: "vacio" }, "Ninguno."));
    if (!DATOS.rechazados.length) rechazados.appendChild(nodo("div", { class: "vacio" }, "Ninguno."));
  }

  function seleccionada() {
    return estado.colocaciones.find((c) => c.id === estado.seleccion) || null;
  }

  function pintarPropiedades() {
    const panel = document.getElementById("propiedades");
    const c = seleccionada();
    if (!c) {
      panel.replaceChildren(nodo("div", { class: "vacio" }, estado.rosaSeleccionada
        ? "Rosa de los vientos seleccionada: arrástrela o muévala con las flechas; su posición exacta está en el panel «Rosa de los vientos»."
        : "Haga clic en un detalle del plano para moverlo o editar su posición."));
      return;
    }
    const pagina = L.paginaEnPapel(c.detalle, c.pos);
    const dibujo = L.dibujoEnPapel(c.detalle, c.pos);
    // Se muestra exactamente lo que se guardará (0,01 mm, redondeado hacia dentro del área).
    const guardada = L.redondearDentro(c.pos, c.detalle.tamano_pagina_mm, ZONA);
    const filas = [
      nodo("div", { class: "fila" }, ""),
      campo("X (mm)", guardada[0], 0),
      campo("Y (mm)", guardada[1], 1),
      nodo("div", { class: "medida" }, "Esquina inferior izquierda de la PÁGINA (posicion_mm)."),
      nodo("div", { class: "medida" }, "Página: X " + mm(pagina[0]) + " a " + mm(pagina[2]) +
        ", Y " + mm(pagina[1]) + " a " + mm(pagina[3]) + " mm"),
      nodo("div", { class: "medida" }, "Dibujo: X " + mm(dibujo[0]) + " a " + mm(dibujo[2]) +
        ", Y " + mm(dibujo[1]) + " a " + mm(dibujo[3]) + " mm"),
    ];
    filas[0].appendChild(nodo("strong", {}, c.id));
    filas[0].appendChild(nodo("span", { class: "medida" }, " · " + c.detalle.id + " · 1:" + c.detalle.escala));
    const botones = nodo("div", { class: "botones" });
    const acciones = [
      ["Centrar", () => mover(c, L.posicionCentrada(c.detalle.tamano_pagina_mm, ZONA))],
      ["Traer al frente", () => reordenar(c, +Infinity)],
      ["Enviar atrás", () => reordenar(c, -Infinity)],
      ["Quitar", () => quitar(c)],
    ];
    for (const [texto, accion] of acciones) {
      const b = nodo("button", { type: "button" }, texto);
      b.addEventListener("click", accion);
      botones.appendChild(b);
    }
    panel.replaceChildren(...filas, botones);
  }

  function campo(etiqueta, valor, indice) {
    const fila = nodo("div", { class: "fila" });
    fila.appendChild(nodo("label", {}, etiqueta));
    const input = nodo("input", { type: "text", inputmode: "decimal" });
    input.value = mm(valor);
    input.addEventListener("change", () => {
      const numero = parseFloat(input.value.replace(",", "."));
      const c = seleccionada();
      if (!c || !isFinite(numero)) {
        pintarPropiedades();
        return;
      }
      const pos = c.pos.slice();
      pos[indice] = numero;
      mover(c, pos);
    });
    fila.appendChild(input);
    return fila;
  }

  function pintarListaPlano() {
    const lista = document.getElementById("lista-plano");
    lista.replaceChildren(...estado.colocaciones.map((c) => {
      const li = nodo("li", { class: c.id === estado.seleccion ? "sel" : "" },
        c.id + " (" + mm1(c.pos[0]) + "; " + mm1(c.pos[1]) + ")");
      li.addEventListener("click", () => seleccionar(c.id));
      return li;
    }));
    if (!estado.colocaciones.length) {
      lista.appendChild(nodo("li", { class: "vacio" }, "Vacío: agregue detalles desde el panel izquierdo."));
    }
  }

  function pintarAdvertencias(lista) {
    const ul = document.getElementById("advertencias");
    if (!lista.length) {
      ul.replaceChildren(nodo("li", { class: "ninguna" }, "Sin advertencias."));
      return;
    }
    ul.replaceChildren(...lista.map((a) => nodo("li", { class: a.nivel }, a.texto)));
  }

  /**
   * Panel «Rótulo» (4.3b): formularios de los campos simples, revisiones y firmas
   * (editor_panel_rotulo.js). Lo que no se toca se guarda tal como vino.
   */
  const panelRotulo = window.EditorPanelRotulo.crear({
    panel: document.getElementById("panel-rotulo"),
    datos: DATOS_ROTULO,
    modelo: () => estado.rotulo,
    escalas: () => estado.colocaciones.map((c) => c.detalle.escala),
    alCambiar: marcarCambios,
  });

  /** Panel «Notas» (4.3c): catálogo con casillas y notas del plano (editor_panel_notas.js). */
  const panelNotas = window.EditorPanelNotas.crear({
    panel: document.getElementById("panel-notas"),
    datos: DATOS_ROTULO,
    modelo: () => estado.rotulo,
    alCambiar: marcarCambios,
  });

  /** Panel «Convenciones» (4.3d): símbolos con casillas y su lista (editor_panel_convenciones.js). */
  const panelConvenciones = window.EditorPanelConvenciones.crear({
    panel: document.getElementById("panel-convenciones"),
    datos: DATOS_ROTULO,
    modelo: () => estado.rotulo,
    alCambiar: marcarCambios,
  });

  function pintarRotulo() {
    panelRotulo.pintar();
    panelNotas.reiniciar(); // vuelve a leer las notas del rótulo actual
    panelConvenciones.reiniciar(); // y las convenciones
  }

  /** Panel «Rosa de los vientos»: mostrar/ocultar, X / Y y restaurar posición. */
  function pintarRosa() {
    const panel = document.getElementById("panel-rosa");
    if (!estado.rosa) {
      panel.replaceChildren(nodo("div", { class: "vacio" }, "El formato no tiene rosa de los vientos."));
      return;
    }
    const casilla = nodo("input", { type: "checkbox", id: "mostrar-rosa" });
    casilla.checked = estado.rosa.visible;
    casilla.addEventListener("change", () => mostrarRosa(casilla.checked));
    const etiqueta = nodo("label", { class: "casilla", for: "mostrar-rosa" });
    etiqueta.append(casilla, " Mostrar rosa de los vientos");
    const filas = [etiqueta];
    if (estado.rosa.visible) {
      const tamano = L.tamanoRosa(ROSA.rect_mm);
      const guardada = L.redondearDentro(estado.rosa.pos, tamano, ZONA);
      filas.push(campoRosa("X (mm)", guardada[0], 0), campoRosa("Y (mm)", guardada[1], 1),
        nodo("div", { class: "medida" }, "Esquina inferior izquierda del rectángulo de la rosa (" +
          mm(tamano[0]) + " × " + mm(tamano[1]) + " mm)."));
    } else {
      filas.push(nodo("div", { class: "medida" }, "Oculta: no sale en el plano y no genera advertencias."));
    }
    const restaurar = nodo("button", { type: "button" }, "Restaurar posición");
    restaurar.title = "Volver a su lugar original (" + mm(ROSA_ORIGEN[0]) + "; " + mm(ROSA_ORIGEN[1]) + ") mm";
    restaurar.addEventListener("click", restaurarRosa);
    const botones = nodo("div", { class: "botones" });
    botones.appendChild(restaurar);
    filas.push(botones);
    panel.replaceChildren(...filas);
  }

  function campoRosa(etiqueta, valor, indice) {
    const fila = nodo("div", { class: "fila" });
    fila.appendChild(nodo("label", {}, etiqueta));
    const input = nodo("input", { type: "text", inputmode: "decimal" });
    input.value = mm(valor);
    input.addEventListener("change", () => {
      const numero = parseFloat(input.value.replace(",", "."));
      if (!isFinite(numero)) {
        pintarRosa();
        return;
      }
      const pos = estado.rosa.pos.slice();
      pos[indice] = numero;
      moverRosa(pos);
    });
    fila.appendChild(input);
    return fila;
  }

  // ---------------------------------------------------------------------------------------
  // Acciones.
  // ---------------------------------------------------------------------------------------

  function seleccionar(id) {
    estado.seleccion = id;
    if (id) estado.rosaSeleccionada = false;
    actualizar();
  }

  function seleccionarRosa() {
    estado.seleccion = null;
    estado.rosaSeleccionada = true;
    actualizar();
  }

  /** Mueve la rosa: igual que un detalle, siempre COMPLETA dentro del área de dibujo. */
  function moverRosa(pos) {
    if (!estado.rosa) return;
    const limitada = L.clampAZona(pos, L.tamanoRosa(ROSA.rect_mm), ZONA);
    if (!limitada) return;
    if (limitada[0] !== estado.rosa.pos[0] || limitada[1] !== estado.rosa.pos[1]) {
      estado.rosa.pos = limitada;
      marcarCambios();
    }
    actualizar();
  }

  function mostrarRosa(visible) {
    if (!estado.rosa || estado.rosa.visible === visible) return;
    estado.rosa.visible = visible;
    if (!visible) estado.rosaSeleccionada = false;
    marcarCambios();
    actualizar();
  }

  function restaurarRosa() {
    if (!estado.rosa) return;
    if (!estado.rosa.visible) {
      estado.rosa.visible = true;
      marcarCambios();
    }
    moverRosa(ROSA_ORIGEN.slice()); // vuelve a su sitio y vuelve a dibujar
  }

  function agregar(detalle) {
    const ids = new Set(estado.colocaciones.map((c) => c.id));
    const id = L.idUnico(detalle.id, ids);
    let pos = L.clampAZona(L.posicionCentrada(detalle.tamano_pagina_mm, ZONA),
      detalle.tamano_pagina_mm, ZONA);
    if (!pos) {
      mensaje("'" + detalle.id + "' no cabe en el área de dibujo.", "error");
      return;
    }
    // Si ya hay un detalle exactamente ahí (p. ej. otra copia), se corre 10 mm para que se vea.
    const ocupada = (p) => estado.colocaciones.some((c) => c.pos[0] === p[0] && c.pos[1] === p[1]);
    for (let i = 0; i < 20 && ocupada(pos); i++) {
      pos = L.clampAZona([pos[0] + 10, pos[1] - 10], detalle.tamano_pagina_mm, ZONA);
    }
    estado.colocaciones.push({ id, detalle, pos });
    estado.seleccion = id;
    marcarCambios();
    actualizar();
  }

  /** Mueve con la regla de componer: la PÁGINA siempre queda dentro del área de dibujo. */
  function mover(c, pos) {
    const limitada = L.clampAZona(pos, c.detalle.tamano_pagina_mm, ZONA);
    if (!limitada) return;
    if (limitada[0] !== c.pos[0] || limitada[1] !== c.pos[1]) {
      c.pos = limitada;
      marcarCambios();
    }
    actualizar();
  }

  function reordenar(c, destino) {
    const i = estado.colocaciones.indexOf(c);
    estado.colocaciones.splice(i, 1);
    if (destino > 0) estado.colocaciones.push(c);
    else estado.colocaciones.unshift(c);
    marcarCambios();
    actualizar();
  }

  function quitar(c) {
    estado.colocaciones = estado.colocaciones.filter((x) => x !== c);
    estado.seleccion = null;
    marcarCambios();
    actualizar();
  }

  // ---------------------------------------------------------------------------------------
  // Mouse: arrastrar detalles, desplazar la hoja, zoom con la rueda.
  // ---------------------------------------------------------------------------------------

  /** Detalles cuya página contiene el punto (mm de papel), del de ENCIMA al de abajo. */
  function detallesEnPunto(p) {
    return estado.colocaciones.filter((c) => {
      const r = L.paginaEnPapel(c.detalle, c.pos);
      return p.x >= r[0] && p.x <= r[2] && p.y >= r[1] && p.y <= r[3];
    }).reverse();
  }

  function empezarArrastre(ev, c) {
    if (ev.button !== 0) return;
    ev.stopPropagation();
    const p = puntoPapel(ev);
    if (ev.altKey) {
      // Alt + clic: el de debajo del seleccionado en ese punto (en ciclo). Sin Alt, el clic
      // toma el de encima, como en el PDF.
      ev.preventDefault();
      const pila = detallesEnPunto(p);
      const actual = pila.findIndex((x) => x.id === estado.seleccion);
      c = pila[(actual + 1) % pila.length] || c;
    }
    if (estado.seleccion !== c.id) seleccionar(c.id);
    arrastre = { c, dx: p.x - c.pos[0], dy: p.y - c.pos[1] };
    svg.setPointerCapture(ev.pointerId);
  }

  /** La rosa se arrastra como un detalle (mismo paso de ajuste). Está debajo de los
   * detalles: donde un detalle la tapa, el clic toma el detalle. */
  function empezarArrastreRosa(ev) {
    if (ev.button !== 0) return;
    ev.stopPropagation();
    const p = puntoPapel(ev);
    if (!estado.rosaSeleccionada) seleccionarRosa();
    arrastre = { rosa: true, dx: p.x - estado.rosa.pos[0], dy: p.y - estado.rosa.pos[1] };
    svg.setPointerCapture(ev.pointerId);
  }

  svg.addEventListener("pointerdown", (ev) => {
    if (ev.button !== 0 || arrastre) return;
    paneo = { x: ev.clientX, y: ev.clientY, vista: Object.assign({}, estado.vista) };
    svg.classList.add("paneando");
    svg.setPointerCapture(ev.pointerId);
  });

  svg.addEventListener("pointermove", (ev) => {
    const p = puntoPapel(ev);
    document.getElementById("cursor").textContent = "Cursor: X " + mm(p.x) + "  Y " + mm(p.y) + " mm";
    if (arrastre) {
      const pos = [L.ajustarAPaso(p.x - arrastre.dx, estado.paso),
        L.ajustarAPaso(p.y - arrastre.dy, estado.paso)];
      if (arrastre.rosa) moverRosa(pos);
      else mover(arrastre.c, pos);
    } else if (paneo) {
      const caja = svg.getBoundingClientRect();
      const factor = paneo.vista.ancho / caja.width;
      estado.vista.x = paneo.vista.x - (ev.clientX - paneo.x) * factor;
      estado.vista.y = paneo.vista.y - (ev.clientY - paneo.y) * factor;
      aplicarVista();
    }
  });

  function terminar(ev) {
    if ((arrastre || paneo) && svg.hasPointerCapture(ev.pointerId)) svg.releasePointerCapture(ev.pointerId);
    if (paneo && Math.abs(ev.clientX - paneo.x) + Math.abs(ev.clientY - paneo.y) < 3 && !arrastre) {
      if (estado.seleccion || estado.rosaSeleccionada) { // clic en el fondo: quita la selección
        estado.rosaSeleccionada = false;
        seleccionar(null);
      }
    }
    arrastre = null;
    paneo = null;
    svg.classList.remove("paneando");
  }
  svg.addEventListener("pointerup", terminar);
  svg.addEventListener("pointercancel", terminar);
  svg.addEventListener("pointerleave", () => (document.getElementById("cursor").textContent = "Cursor: —"));

  svg.addEventListener("wheel", (ev) => {
    ev.preventDefault();
    zoom(ev.deltaY < 0 ? 1.15 : 1 / 1.15, puntoSvg(ev));
  }, { passive: false });

  // ---------------------------------------------------------------------------------------
  // Teclado: flechas (paso; Shift = 10 pasos), Supr = quitar, Ctrl+S = guardar.
  // ---------------------------------------------------------------------------------------

  // Vista limpia: el botón la deja fija; la tecla V la muestra mientras se mantiene.
  let vistaLimpiaFija = false;
  let teclaV = false;
  const botonVistaLimpia = document.getElementById("btn-vista-limpia");
  function aplicarVistaLimpia() {
    svg.classList.toggle("vista-limpia", vistaLimpiaFija || teclaV);
    botonVistaLimpia.setAttribute("aria-pressed", String(vistaLimpiaFija));
  }
  botonVistaLimpia.addEventListener("click", () => {
    vistaLimpiaFija = !vistaLimpiaFija;
    aplicarVistaLimpia();
  });
  document.addEventListener("keyup", (ev) => {
    if (ev.key === "v" || ev.key === "V") {
      teclaV = false;
      aplicarVistaLimpia();
    }
  });
  window.addEventListener("blur", () => {
    teclaV = false; // si se suelta la V fuera de la ventana
    aplicarVistaLimpia();
  });

  document.addEventListener("keydown", (ev) => {
    if (ev.ctrlKey && (ev.key === "s" || ev.key === "S")) {
      ev.preventDefault();
      guardar();
      return;
    }
    const etiqueta = ev.target.tagName;
    if (etiqueta === "INPUT" || etiqueta === "SELECT" || etiqueta === "TEXTAREA") return;
    if ((ev.key === "v" || ev.key === "V") && !ev.ctrlKey && !ev.altKey && !ev.metaKey) {
      teclaV = true;
      aplicarVistaLimpia();
      return;
    }
    const paso = estado.paso * (ev.shiftKey ? 10 : 1);
    const movimientos = { ArrowLeft: [-paso, 0], ArrowRight: [paso, 0], ArrowUp: [0, paso], ArrowDown: [0, -paso] };
    if (estado.rosaSeleccionada && estado.rosa && estado.rosa.visible) {
      if (movimientos[ev.key]) {
        ev.preventDefault();
        const [dx, dy] = movimientos[ev.key];
        moverRosa([estado.rosa.pos[0] + dx, estado.rosa.pos[1] + dy]);
      }
      return; // Supr no quita la rosa: se oculta con la casilla
    }
    const c = seleccionada();
    if (!c) return;
    if (movimientos[ev.key]) {
      ev.preventDefault();
      const [dx, dy] = movimientos[ev.key]; // en papel, Y hacia arriba: flecha arriba = +Y
      mover(c, [c.pos[0] + dx, c.pos[1] + dy]);
    } else if (ev.key === "Delete") {
      quitar(c);
    }
  });

  // ---------------------------------------------------------------------------------------
  // Guardar y abrir plano.json.
  // ---------------------------------------------------------------------------------------

  const SEPARADOR = DATOS.carpeta_editor.includes("\\") ? "\\" : "/";

  function pintarDondeGuardar() {
    const caja = document.getElementById("donde-guardar");
    caja.replaceChildren(
      nodo("strong", {}, "Guarde el plano.json en la MISMA carpeta que este editor.html "),
      nodo("span", {}, "(las rutas del plano son relativas a esa carpeta). Al generar el editor, " +
        "esa carpeta era: "),
      nodo("code", {}, DATOS.carpeta_editor),
      nodo("span", {}, " (dato informativo: si movió el editor, use la carpeta donde está ahora).")
    );
  }

  function mostrarComando(nombre) {
    const base = nombre.replace(/\.json$/i, "");
    const ruta = DATOS.carpeta_editor + SEPARADOR;
    const comando = 'python -m componedor.cli componer "' + ruta + nombre + '" --salida "' +
      ruta + base + '.pdf"';
    document.getElementById("texto-comando").textContent = comando;
    document.getElementById("comando").hidden = false;
  }

  function descargar(texto, nombre) {
    const blob = new Blob([texto], { type: "application/json" });
    const enlace = nodo("a", { download: nombre });
    enlace.href = URL.createObjectURL(blob);
    document.body.appendChild(enlace);
    enlace.click();
    enlace.remove();
    setTimeout(() => URL.revokeObjectURL(enlace.href), 1000);
  }

  async function guardar() {
    if (!estado.colocaciones.length) {
      mensaje("El plano está vacío: agregue al menos un detalle antes de guardar.", "error");
      return;
    }
    const texto = textoPlano();
    if (window.showSaveFilePicker) {
      try {
        const archivo = await window.showSaveFilePicker({
          suggestedName: "plano.json",
          types: [{ description: "Plano (JSON)", accept: { "application/json": [".json"] } }],
        });
        const escritor = await archivo.createWritable();
        await escritor.write(new Blob([texto], { type: "application/json" }));
        await escritor.close();
        guardado(archivo.name, false);
        return;
      } catch (error) {
        if (error && error.name === "AbortError") return; // el usuario canceló: nada que hacer
        // Otro error (permisos, página abierta desde file://…): se usa la descarga normal.
      }
    }
    descargar(texto, "plano.json");
    guardado("plano.json", true);
  }

  /** plano.json con los detalles, la rosa y (si se abrió un plano que lo traía) el rótulo. */
  function textoPlano() {
    return L.serializarPlano(estado.colocaciones, DATOS, {
      rosa: estado.rosa, rotulo: R.serializar(estado.rotulo), original: estado.original });
  }

  function guardado(nombre, descargado) {
    estado.cambios = false;
    mostrarComando(nombre);
    if (descargado) {
      mensaje("Se descargó '" + nombre + "' en la carpeta de descargas del navegador.\n" +
        "Muévalo a la carpeta de este editor.html antes de componer.", "ok");
    } else {
      mensaje("Plano guardado como '" + nombre + "'. Verifique que quedó en la carpeta de este editor.html.", "ok");
    }
  }

  function abrir(texto) {
    const resultado = L.leerPlano(texto, DATOS);
    if (resultado.errores.length) {
      mensaje("No se pudo abrir el plano:\n- " + resultado.errores.join("\n- "), "error");
      return;
    }
    estado.colocaciones = resultado.colocaciones;
    estado.seleccion = null;
    estado.rosaSeleccionada = false;
    // Sin "rosa_vientos" en el plano: visible y en su sitio (lo mismo que hace componer).
    if (ROSA) estado.rosa = resultado.rosa || { visible: true, pos: ROSA_ORIGEN.slice() };
    estado.rotulo = R.crearModelo(resultado.rotulo, DEFINICION_ROTULO); // se conserva al guardar
    estado.original = resultado.original;
    pintarRotulo();
    estado.cambios = resultado.avisos.length > 0; // si se ajustó algo, hay cambios por guardar
    actualizar();
    const resumen = "Plano abierto: " + resultado.colocaciones.length + " detalle(s).";
    if (resultado.avisos.length) mensaje(resumen + "\n- " + resultado.avisos.join("\n- "), "");
    else mensaje(resumen, "ok");
  }

  document.getElementById("btn-guardar").addEventListener("click", guardar);
  document.getElementById("btn-abrir").addEventListener("click", () => {
    if (estado.cambios && !confirm("Hay cambios sin guardar. ¿Abrir otro plano de todos modos?")) return;
    document.getElementById("archivo-plano").click();
  });
  document.getElementById("archivo-plano").addEventListener("change", (ev) => {
    const archivo = ev.target.files[0];
    ev.target.value = "";
    if (!archivo) return;
    archivo.text().then(abrir, (e) => mensaje("No se pudo leer el archivo: " + e.message, "error"));
  });
  document.getElementById("btn-copiar").addEventListener("click", () => {
    const texto = document.getElementById("texto-comando").textContent;
    const copiado = () => mensaje("Comando copiado.", "ok");
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(texto).then(copiado, () => seleccionarTexto());
    } else {
      seleccionarTexto();
    }
  });
  function seleccionarTexto() {
    const rango = document.createRange();
    rango.selectNodeContents(document.getElementById("texto-comando"));
    const sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(rango);
    mensaje("Seleccioné el comando: cópielo con Ctrl+C.", "");
  }

  window.addEventListener("beforeunload", (ev) => {
    if (!estado.cambios) return;
    ev.preventDefault();
    ev.returnValue = "";
  });

  // ---------------------------------------------------------------------------------------
  // Barra superior e inicio.
  // ---------------------------------------------------------------------------------------

  document.getElementById("btn-acercar").addEventListener("click", () => zoom(1.25));
  document.getElementById("btn-alejar").addEventListener("click", () => zoom(1 / 1.25));
  document.getElementById("btn-ajustar").addEventListener("click", ajustarVista);
  document.getElementById("paso").addEventListener("change", (ev) => {
    estado.paso = parseFloat(ev.target.value);
  });
  window.addEventListener("resize", ajustarVista);

  // Para la verificación automática del reporte (no la usa la interfaz).
  window.EditorPrueba = { estado, agregar: (id) => agregar(CATALOGO.find((d) => d.id === id)),
    mover: (id, pos) => mover(estado.colocaciones.find((c) => c.id === id), pos),
    texto: textoPlano, advertencias: () => ultimasAdvertencias,
    moverRosa, mostrarRosa, restaurarRosa, abrir,
    rotulo: () => R.serializar(estado.rotulo), validacionRotulo: () => panelRotulo.validacion(),
    validacionNotas: () => panelNotas.validacion(), validacionConvenciones: () => panelConvenciones.validacion() };

  pintarCatalogo();
  pintarRotulo();
  pintarDondeGuardar();
  ajustarVista();
  actualizar();
})();
