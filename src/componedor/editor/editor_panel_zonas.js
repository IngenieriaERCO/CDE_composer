/*
 * Editor de planos — diálogo «Zonas del modelo» (Fase 10d). Solo pantalla: la lógica está en
 * editor_zonas.js, la conexión en editor_servidor.js y los textos de tareas en editor_dxf.js.
 *
 * Se abre con el botón «Zonas del modelo…» de la carpeta del DXF (editor_panel_dxf.js), solo
 * con el editor abierto desde «Abrir editor.bat» y un DXF cargado.
 *
 * La vista se maneja como en AutoCAD:
 *   - rueda del ratón: acercar / alejar hacia donde apunta el cursor;
 *   - rueda apretada y arrastrar: mover la vista;
 *   - doble clic con la rueda: ver todo el Model Space;
 *   - clic izquierdo y arrastrar: dibujar la zona (a cualquier zoom);
 *   - clic izquierdo en un grupo (G1, G2…) o en sus botones: ir a ese grupo.
 * La «cámara» es la ventana CAD que se ve (z.camara). La imagen que hay se escala al instante
 * (el viewBox del SVG sale de la cámara y de la matriz de esa imagen); 450 ms después de parar,
 * se pide al Exportador una vista nítida de la ventana, si la imagen actual no la cubre o se
 * ve pixelada (las ya pedidas se toman de la caché del editor; el Exportador tiene la suya).
 * La zona, los grupos y el rectángulo se guardan y se dibujan en coordenadas del dibujo: son
 * exactos a cualquier zoom.
 *
 * Capas: todas marcadas al empezar (se exportan todas menos las desmarcadas); opción «Solo las
 * marcadas»; «Ver la imagen con el filtro de capas» pide las vistas con el filtro.
 * Escala (sugerida al dibujar la zona), tamaño en la hoja y aviso si no cabe en el A1. Nombre
 * opcional (vacío: Zona_01, Zona_02…, que da el servidor al agregarla) y «Agregar a la hoja»
 * (Fase 10e): la zona queda en el A1 como borrador, con su tamaño real a esa escala
 * (EditorUI.agregarZona); se mueve y cambia de escala allí y se exporta con «Exportar bloques y
 * zonas». «Editar zona…» del panel Selección abre este cuadro con esa zona: «Guardar cambios en
 * la hoja» le cambia el rectángulo, las capas o la escala (el centro y el nombre se quedan).
 *
 * Arriba, la línea de la vista previa preparada del exportador 1.2 (la del panel del DXF):
 * «Preparando… 61 % · lleva 32 s» o «lista: el zoom ya va rápido» o por qué falló.
 *
 * Lo largo (con PRGD, la primera vista de todo el Model Space pasa del minuto) muestra el
 * avance, el mensaje del trabajador, el tiempo transcurrido y «Cancelar». Nada bloquea: se
 * puede seguir acercando, moviendo y dibujando mientras llega la vista nítida.
 */
(function () {
  "use strict";

  const S = window.EditorServidor;
  const D = window.EditorDxf;
  const E = window.EditorZonas;
  const B = window.EditorBloques;
  const conexion = S.detectar(window.location);
  if (!conexion) return; // sin servidor no hay DXF: el botón ni siquiera aparece
  const cliente = S.crearCliente(conexion, window.fetch.bind(window));
  const UI = () => window.EditorUI || null;
  const panelDxf = () => window.EditorPanelDxf || null;
  // El namespace de SVG, del <svg> de la hoja (el HTML no lleva ninguna URL escrita).
  const NS = document.getElementById("hoja").namespaceURI;
  const EXPLICACION_PRIMERA = "La primera vista de una sesión calcula las cajas de todo el Model " +
    "Space (una sola vez): con un DXF grande puede tardar más de un minuto. Puede cerrar este " +
    "cuadro y seguir con el plano mientras tanto.";
  const ESPERA_NITIDA_MS = 450; // tras la última vuelta de rueda o el fin del arrastre
  const DOBLE_CLIC_MS = 400;
  const TOL_GRUPO_PANTALLA = 24; // px de pantalla alrededor de un grupo (o su etiqueta)

  const z = {
    sesion: null, // la sesión del DXF para la que vale lo de abajo
    vista: null, // {cuerpo, resultado, url}: la imagen que se ve
    todo: null, // {caja, grupos}: lo de la vista de todo el Model Space
    camara: null, // la ventana CAD que se ve [x0, y0, x1, y1]
    pidiendo: null, // {foto, inicio, clave, cuerpo, explicacion}
    cache: new Map(), // clave del pedido → {cuerpo, resultado, url}
    zona: null, modo: "excluir", desmarcadas: new Set(), capas: [], filas: [], verVacias: false,
    conFiltro: false, escala: "", nombre: "", agregando: false, agregada: null, editando: null, error: null,
    nitidas: 0, // cuántas veces se pidió (o tomó de la caché) una vista nítida (para verificar)
  };
  window.EditorPruebaZonas = z;
  let dialogo = null;
  let partes = null;
  let reloj = null;
  let temporizador = null;

  function nodo(nombre, atributos, texto) {
    const n = document.createElement(nombre);
    for (const [k, v] of Object.entries(atributos || {})) n.setAttribute(k, v);
    if (texto !== undefined) n.textContent = texto; // nunca HTML: los nombres vienen del DXF
    return n;
  }

  function svg(nombre, atributos) {
    const n = document.createElementNS(NS, nombre);
    for (const [k, v] of Object.entries(atributos || {})) n.setAttribute(k, String(v));
    return n;
  }

  const catalogo = () => (panelDxf() && panelDxf().catalogo()) || null;
  const estilo = () => (panelDxf() && panelDxf().estiloPedido ? panelDxf().estiloPedido() : null);
  const area = () => (UI() ? UI().zona() : null);

  // ---------------------------------------------------------------------------------------
  // Armar el diálogo (una vez)
  // ---------------------------------------------------------------------------------------

  function seccion(titulo) {
    const s = nodo("section", { class: "seccion-zona" });
    s.appendChild(nodo("h4", {}, titulo));
    return s;
  }

  function armar() {
    dialogo = nodo("dialog", { class: "dialogo-zonas", id: "dialogo-zonas" });
    const cabecera = nodo("div", { class: "cabecera-zonas" });
    const titulo = nodo("h3", {}, "Zonas del modelo");
    const cerrar = nodo("button", { type: "button", id: "cerrar-zonas" }, "Cerrar");
    cerrar.addEventListener("click", () => dialogo.close());
    cabecera.append(titulo, cerrar);

    const izq = nodo("div", { class: "izq-zonas" });
    const preparacion = nodo("div", { class: "preparacion-dxf", id: "preparacion-zonas", hidden: "" });
    const navegacion = nodo("div", { class: "navegacion-zonas" });
    const visor = nodo("div", { class: "visor-zonas" });
    const lamina = svg("svg", { class: "lamina-zonas", id: "lamina-zonas" });
    const ocupado = nodo("div", { class: "ocupado-zonas", hidden: "" });
    visor.append(lamina, ocupado);
    const ayuda = nodo("div", { class: "dato ayuda-zonas" }, "Rueda: acercar y alejar hacia el cursor · " +
      "rueda apretada y arrastrar: mover · doble clic con la rueda: ver todo · clic izquierdo y " +
      "arrastrar: dibujar la zona · clic en un grupo (G1, G2…): ir a él.");
    izq.append(preparacion, navegacion, visor, ayuda);

    const der = nodo("div", { class: "der-zonas" });
    // Zona
    const sZona = seccion("1. Zona");
    const textoZona = nodo("div", { class: "dato", id: "texto-zona" });
    const botonesZona = nodo("div", { class: "botones" });
    const borrar = nodo("button", { type: "button", id: "borrar-zona" }, "Borrar zona");
    borrar.addEventListener("click", () => { z.zona = null; z.agregada = null; pintar(); });
    botonesZona.append(borrar);
    sZona.append(textoZona, botonesZona);
    // Capas
    const sCapas = seccion("2. Capas");
    const modos = nodo("div", { class: "modos-capas" });
    for (const [valor, texto] of [["excluir", "Todas menos las desmarcadas"], ["solo", "Solo las marcadas"]]) {
      const l = nodo("label");
      const r = nodo("input", { type: "radio", name: "modo-capas", value: valor, id: "modo-" + valor });
      r.checked = z.modo === valor;
      r.addEventListener("change", () => { z.modo = valor; alCambiarCapas(); });
      l.append(r, " " + texto);
      modos.appendChild(l);
    }
    const botonesCapas = nodo("div", { class: "botones" });
    const todas = nodo("button", { type: "button", id: "marcar-todas" }, "Marcar todas");
    todas.addEventListener("click", () => { z.desmarcadas.clear(); alCambiarCapas(); });
    const ninguna = nodo("button", { type: "button", id: "desmarcar-todas" }, "Desmarcar todas");
    ninguna.addEventListener("click", () => { z.desmarcadas = new Set(z.capas); alCambiarCapas(); });
    botonesCapas.append(todas, ninguna);
    const conFiltro = nodo("label", { class: "dato" });
    const casillaFiltro = nodo("input", { type: "checkbox", id: "vista-con-filtro" });
    casillaFiltro.addEventListener("change", () => {
      z.conFiltro = casillaFiltro.checked;
      pedirNitida(true);
    });
    conFiltro.append(casillaFiltro, " Ver la imagen con el filtro de capas");
    const vacias = nodo("label", { class: "dato" });
    const casillaVacias = nodo("input", { type: "checkbox", id: "ver-capas-vacias" });
    casillaVacias.addEventListener("change", () => { z.verVacias = casillaVacias.checked; pintar(); });
    vacias.append(casillaVacias, " Mostrar también las capas sin nada en esta vista");
    const listaCapas = nodo("div", { class: "lista-capas", id: "lista-capas" });
    const resumenCapas = nodo("div", { class: "dato", id: "resumen-capas" });
    sCapas.append(modos, botonesCapas, conFiltro, vacias, listaCapas, resumenCapas);
    // Escala y tamaño
    const sEscala = seccion("3. Escala y tamaño en la hoja");
    const filaEscala = nodo("div", { class: "fila" });
    filaEscala.appendChild(nodo("label", { for: "escala-zona" }, "Escala 1:"));
    const escala = nodo("input", { id: "escala-zona", list: "escalas-zona", inputmode: "numeric",
      autocomplete: "off", size: "8", placeholder: "N" });
    escala.addEventListener("input", () => { z.escala = escala.value; pintarTamano(); pintarBotonExportar(); });
    const lista = nodo("datalist", { id: "escalas-zona" });
    for (const n of [5, 10, 20, 25, 50, 75, 100, 200, 250, 500, 750, 1000, 2000, 5000]) {
      lista.appendChild(nodo("option", { value: String(n) }));
    }
    filaEscala.append(escala, lista);
    const tamano = nodo("div", { class: "dato", id: "tamano-zona" });
    sEscala.append(filaEscala, tamano);
    // Nombre y agregar a la hoja (Fase 10e)
    const sNombre = seccion("4. Nombre y agregar a la hoja");
    const filaNombre = nodo("div", { class: "fila" });
    filaNombre.appendChild(nodo("label", { for: "nombre-zona" }, "Nombre"));
    const nombre = nodo("input", { id: "nombre-zona", autocomplete: "off",
      placeholder: "Vacío: Zona_01, Zona_02… (se pone al agregarla)", maxlength: "40" });
    nombre.addEventListener("input", () => { z.nombre = nombre.value; });
    filaNombre.appendChild(nombre);
    const agregar = nodo("button", { type: "button", class: "principal", id: "btn-agregar-zona" }, "Agregar a la hoja");
    agregar.addEventListener("click", agregarALaHoja);
    const dejar = nodo("button", { type: "button", id: "btn-dejar-editar", hidden: "" }, "Dejar de editar");
    dejar.addEventListener("click", () => { z.editando = null; z.agregada = null; pintar(); });
    const botonesAgregar = nodo("div", { class: "botones" });
    botonesAgregar.append(agregar, dejar);
    const estiloTexto = nodo("div", { class: "dato", id: "estilo-zona" });
    const resultado = nodo("div", { class: "resultado-zona", id: "resultado-zona" });
    sNombre.append(filaNombre, botonesAgregar, estiloTexto, resultado);
    const error = nodo("div", { class: "error-dxf", id: "error-zonas", hidden: "" });
    der.append(error, sZona, sCapas, sEscala, sNombre);

    const cuerpo = nodo("div", { class: "cuerpo-zonas" });
    cuerpo.append(izq, der);
    dialogo.append(cabecera, cuerpo);
    document.body.appendChild(dialogo);
    dialogo.addEventListener("close", () => {
      clearInterval(reloj);
      reloj = null;
    });
    partes = { titulo, preparacion, navegacion, lamina, ocupado, textoZona, borrar, listaCapas, resumenCapas,
      casillaFiltro, casillaVacias, escala, tamano, nombre, agregar, dejar, estiloTexto, resultado, error };
    prepararRaton(lamina);
  }

  // ---------------------------------------------------------------------------------------
  // Abrir
  // ---------------------------------------------------------------------------------------

  function abrir() {
    const c = catalogo();
    if (!c) return;
    if (!dialogo) armar();
    const sesion = c.dxf.sha256 + "|" + c.sesion;
    if (z.sesion !== sesion) reiniciar(sesion);
    partes.titulo.textContent = "Zonas del modelo — " + c.dxf.nombre;
    if (!dialogo.open) dialogo.showModal();
    reloj = reloj || setInterval(() => { pintarOcupado(); pintarPreparacion(); }, 1000); // el tiempo avanza solo
    if (!c.sesion_activa) {
      z.error = "El trabajador ya no tiene este DXF: ciérrelo y use «Volver a cargar».";
    } else if (!z.vista && !z.pidiendo) {
      pedirVista({}, EXPLICACION_PRIMERA);
    }
    pintar();
  }

  /**
   * «Editar zona…» de una zona borrador de la hoja: el cuadro con su rectángulo, capas y escala,
   * la vista sobre ella, y «Guardar cambios en la hoja» en lugar de «Agregar a la hoja».
   */
  function editar(c) {
    abrir();
    const b = c.bloque;
    const zb = b.zona;
    z.editando = c.id;
    z.agregada = null;
    z.zona = zb.rect.slice();
    z.modo = zb.modo || "excluir";
    z.desmarcadas = new Set(zb.desmarcadas || zb.excluir || []);
    z.escala = String(c.escala);
    z.nombre = b.nombre;
    partes.escala.value = z.escala;
    partes.nombre.value = b.nombre;
    for (const r of dialogo.querySelectorAll("input[name=modo-capas]")) r.checked = r.value === z.modo;
    z.camara = E.encuadrar(zb.rect, aspecto(), 0.3);
    if (z.vista) pedirNitida(false);
    pintar();
  }

  /** Otro DXF (u otra sesión): lo de antes no sirve. */
  function reiniciar(sesion) {
    if (z.pidiendo && z.pidiendo.foto) cliente.cancelar(z.pidiendo.foto.id).catch(() => {});
    for (const v of z.cache.values()) URL.revokeObjectURL(v.url);
    Object.assign(z, { sesion, vista: null, todo: null, camara: null, pidiendo: null, cache: new Map(),
      zona: null, modo: "excluir", desmarcadas: new Set(), capas: [], filas: [], conFiltro: false,
      escala: "", nombre: "", agregando: false, agregada: null, editando: null, error: null });
    if (partes) {
      partes.escala.value = "";
      partes.nombre.value = "";
      partes.casillaFiltro.checked = false;
      for (const r of dialogo.querySelectorAll("input[name=modo-capas]")) r.checked = r.value === "excluir";
    }
  }

  // ---------------------------------------------------------------------------------------
  // La cámara: lo que se ve
  // ---------------------------------------------------------------------------------------

  /** Proporción ancho/alto del visor en pantalla. */
  function aspecto() {
    const r = partes.lamina.getBoundingClientRect();
    return r.width > 0 && r.height > 0 ? r.width / r.height : 1.6;
  }

  /** Un punto de la ventana del navegador → px de la imagen que se ve. */
  function aImagen(cx, cy) {
    const pt = partes.lamina.createSVGPoint();
    pt.x = cx;
    pt.y = cy;
    const p = pt.matrixTransform(partes.lamina.getScreenCTM().inverse());
    return [p.x, p.y];
  }

  /** Un punto de la ventana del navegador → coordenadas del dibujo. */
  function aCad(cx, cy) {
    const p = aImagen(cx, cy);
    return E.pxACad(z.vista.resultado.cad_a_px, p[0], p[1]);
  }

  /** La ventana CAD que de verdad se ve en el visor (todo su rectángulo). */
  function ventanaVisible() {
    const r = partes.lamina.getBoundingClientRect();
    const a = aCad(r.left, r.bottom);
    const b = aCad(r.right, r.top);
    return [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[0], b[0]), Math.max(a[1], b[1])];
  }

  /** px de la imagen por px de pantalla (para grosores y letras que no cambian con el zoom). */
  function imagenPorPantalla() {
    const r = partes.lamina.getBoundingClientRect();
    const c = E.cajaAPx(z.vista.resultado.cad_a_px, z.camara);
    return r.width > 0 ? Math.max(c.ancho / r.width, c.alto / r.height) : 1;
  }

  function fijarCamara(camara) {
    z.camara = camara;
    pintarLamina();
  }

  /** Pide la vista nítida al dejar de mover la rueda (o de arrastrar) un momento. */
  function programarNitida() {
    clearTimeout(temporizador);
    temporizador = setTimeout(() => pedirNitida(false), ESPERA_NITIDA_MS);
  }

  /** La vista para lo que se ve, si la imagen actual no sirve (o `forzar`, p. ej. otro filtro). */
  function pedirNitida(forzar) {
    clearTimeout(temporizador);
    if (!z.vista || !z.camara) return;
    const r = z.vista.resultado;
    const ventana = ventanaVisible();
    const limite = z.todo ? z.todo.caja : null;
    const filtroActual = z.conFiltro ? filtro() : null;
    if (filtroActual && filtroActual.error) {
      z.error = filtroActual.error;
      pintar();
      return;
    }
    const mismoFiltro = E.clavePrevia(E.cuerpoPrevia({ filtro: filtroActual })) ===
      E.clavePrevia(E.cuerpoPrevia({ filtro: filtroDe(z.vista.cuerpo) }));
    const ancho = partes.lamina.getBoundingClientRect().width;
    if (!forzar && mismoFiltro && !E.necesitaVistaNitida(r.cad_a_px, r.px, ventana, ancho, limite)) return;
    // Todo el Model Space a la vista: la de todo (de la caché si ya está).
    z.nitidas++;
    if (limite && ventana[0] <= limite[0] && ventana[1] <= limite[1] && ventana[2] >= limite[2] &&
        ventana[3] >= limite[3] && !filtroActual) {
      pedirVista({});
      return;
    }
    const util = (limite && E.interseccion(ventana, limite)) || ventana;
    pedirVista({ vista: E.redondear(util), filtro: filtroActual });
  }

  /** El filtro con que se pidió una vista (para saber si hay que pedirla otra vez). */
  function filtroDe(cuerpo) {
    if (cuerpo.capas) return { capas: cuerpo.capas, excluir: null };
    if (cuerpo.excluir) return { excluir: cuerpo.excluir, capas: null };
    return null;
  }

  function verTodo() {
    if (!z.todo) {
      pedirVista({});
      return;
    }
    fijarCamara(E.encuadrar(z.todo.caja, aspecto()));
    pedirNitida(false);
  }

  function verGrupo(g) {
    if (!z.vista) return;
    fijarCamara(E.encuadrar(g.caja, aspecto()));
    pedirNitida(false);
  }

  // ---------------------------------------------------------------------------------------
  // Vistas previas
  // ---------------------------------------------------------------------------------------

  function filtro() {
    return E.filtroCapas(z.modo, z.capas, z.desmarcadas);
  }

  /** Pide (o toma de la caché) la vista `base` ({vista?, filtro?}). Sin vista: todo. */
  async function pedirVista(base, explicacion) {
    const cuerpo = E.cuerpoPrevia(Object.assign({}, base, { estilo: estilo() }));
    const clave = E.clavePrevia(cuerpo);
    z.error = null;
    if (z.cache.has(clave)) {
      if (z.pidiendo && z.pidiendo.foto) cliente.cancelar(z.pidiendo.foto.id).catch(() => {});
      z.pidiendo = null;
      mostrar(z.cache.get(clave));
      return;
    }
    if (z.pidiendo) {
      if (z.pidiendo.clave === clave) return;
      if (z.pidiendo.foto) cliente.cancelar(z.pidiendo.foto.id).catch(() => {});
    }
    const p = { foto: null, inicio: Date.now(), clave, cuerpo, explicacion: explicacion || null };
    z.pidiendo = p;
    pintarOcupado();
    try {
      const r = await cliente.previaZona(cuerpo);
      p.foto = r.tarea;
      const fin = await S.seguirTarea(cliente, r.tarea.id, (foto) => {
        p.foto = foto;
        if (z.pidiendo === p) pintarOcupado();
      });
      if (fin.estado === "terminada" && /^\/api\/previas\/t-\d+$/.test(fin.resultado.url)) {
        const v = { cuerpo, resultado: fin.resultado, url: URL.createObjectURL(await cliente.png(fin.resultado.url)) };
        z.cache.set(clave, v);
        if (!cuerpo.vista) recordarTodo(v);
        if (z.pidiendo !== p) return; // se pidió otra mientras tanto (queda en la caché)
        z.pidiendo = null;
        mostrar(v);
        return;
      }
      if (z.pidiendo !== p) return;
      z.pidiendo = null;
      if (fin.estado !== "cancelada") z.error = "Vista previa: " + D.textoError(fin);
    } catch (err) {
      if (z.pidiendo !== p) return;
      z.pidiendo = null;
      z.error = "Vista previa: " + err.message;
    }
    pintar();
  }

  /** La vista de todo el Model Space: su caja y sus grupos sirven a cualquier zoom. */
  function recordarTodo(v) {
    const r = v.resultado;
    z.todo = { caja: r.vista || E.cajaDeImagen(r.cad_a_px, r.px), grupos: r.grupos };
  }

  function mostrar(v) {
    z.vista = v;
    if (!z.camara) z.camara = E.encuadrar(z.todo ? z.todo.caja : E.cajaDeImagen(v.resultado.cad_a_px, v.resultado.px), aspecto());
    else programarNitida(); // p. ej. «Editar zona…» antes de tener la primera vista: la nítida de la zona
    // Todas las capas del DXF (layer_rows las trae todas, con lo que hay en esta vista).
    z.filas = v.resultado.filas_capas;
    z.capas = z.filas.map((f) => f.nombre);
    pintar();
  }

  function alCambiarCapas() {
    pintar();
    if (z.conFiltro) programarNitida();
  }

  // ---------------------------------------------------------------------------------------
  // El ratón: rueda, rueda apretada, doble clic con la rueda y clic izquierdo
  // ---------------------------------------------------------------------------------------

  function prepararRaton(lamina) {
    let dibujo = null; // {cad, pantalla, rect, ultimo}
    let mover = null; // {pantalla, camara, k}
    let ultimoMedio = { t: 0, x: 0, y: 0 };

    /** El punto del evento, limitado al visor: soltar pasado el borde deja la zona en el borde. */
    const enVisor = (ev) => {
      const r = lamina.getBoundingClientRect();
      return [Math.min(Math.max(ev.clientX, r.left), r.right), Math.min(Math.max(ev.clientY, r.top), r.bottom)];
    };

    // Sin esto, el botón de la rueda en Windows activa el «autodesplazamiento» del navegador.
    lamina.addEventListener("mousedown", (ev) => { if (ev.button === 1) ev.preventDefault(); });
    lamina.addEventListener("auxclick", (ev) => { if (ev.button === 1) ev.preventDefault(); });

    lamina.addEventListener("wheel", (ev) => {
      if (!z.vista || !z.camara) return;
      ev.preventDefault();
      const p = aCad(ev.clientX, ev.clientY);
      fijarCamara(E.zoomEnPunto(z.camara, p, E.factorRueda(ev.deltaY)));
      programarNitida();
    }, { passive: false });

    lamina.addEventListener("pointerdown", (ev) => {
      if (!z.vista || !z.camara) return;
      if (ev.button === 1) {
        ev.preventDefault();
        const ahora = Date.now();
        if (ahora - ultimoMedio.t < DOBLE_CLIC_MS && Math.hypot(ev.clientX - ultimoMedio.x, ev.clientY - ultimoMedio.y) < 8) {
          ultimoMedio = { t: 0, x: 0, y: 0 };
          verTodo(); // doble clic con la rueda
          return;
        }
        ultimoMedio = { t: ahora, x: ev.clientX, y: ev.clientY };
        const v = ventanaVisible();
        mover = { pantalla: [ev.clientX, ev.clientY], camara: z.camara,
          k: (v[2] - v[0]) / lamina.getBoundingClientRect().width };
        lamina.setPointerCapture(ev.pointerId);
        lamina.classList.add("moviendo");
        return;
      }
      if (ev.button !== 0) return;
      ev.preventDefault();
      dibujo = { cad: aCad(ev.clientX, ev.clientY), pantalla: [ev.clientX, ev.clientY], rect: null,
        ultimo: [ev.clientX, ev.clientY] };
      lamina.setPointerCapture(ev.pointerId);
    });

    lamina.addEventListener("pointermove", (ev) => {
      if (mover) {
        const dx = ev.clientX - mover.pantalla[0];
        const dy = ev.clientY - mover.pantalla[1];
        fijarCamara(E.desplazar(mover.camara, -dx * mover.k, dy * mover.k)); // pantalla Y abajo, CAD Y arriba
        return;
      }
      if (!dibujo) return;
      dibujo.ultimo = enVisor(ev);
      const c = aCad(dibujo.ultimo[0], dibujo.ultimo[1]);
      const caja = [Math.min(c[0], dibujo.cad[0]), Math.min(c[1], dibujo.cad[1]),
        Math.max(c[0], dibujo.cad[0]), Math.max(c[1], dibujo.cad[1])];
      const r = E.cajaAPx(z.vista.resultado.cad_a_px, caja);
      if (!dibujo.rect) {
        dibujo.rect = svg("rect", { class: "zona-temporal" });
        lamina.appendChild(dibujo.rect);
      }
      dibujo.rect.setAttribute("x", r.x);
      dibujo.rect.setAttribute("y", r.y);
      dibujo.rect.setAttribute("width", r.ancho);
      dibujo.rect.setAttribute("height", r.alto);
    });

    const soltar = (ev) => {
      if (mover) {
        mover = null;
        lamina.classList.remove("moviendo");
        programarNitida();
        return;
      }
      if (!dibujo) return;
      const d = dibujo;
      dibujo = null;
      if (d.rect) d.rect.remove();
      // Si se soltó fuera (sobre el fondo del diálogo, p. ej.), vale el último punto dentro.
      const fin = ev && typeof ev.clientX === "number" && ev.type === "pointerup" ? enVisor(ev) : d.ultimo;
      const zona = E.zonaDesdeArrastre(d.cad, aCad(fin[0], fin[1]), [d.pantalla, fin]);
      if (zona) {
        fijarZona(zona);
        return;
      }
      // Un clic: si está en un grupo (o cerca de su etiqueta), ir a él.
      if (z.todo && z.todo.grupos.length) {
        const p = aImagen(fin[0], fin[1]);
        const g = E.grupoEnPunto(z.vista.resultado.cad_a_px, z.todo.grupos, p,
          TOL_GRUPO_PANTALLA * imagenPorPantalla());
        if (g) verGrupo(g);
      }
    };
    lamina.addEventListener("pointerup", soltar);
    // El botón soltado fuera del visor (o fuera del diálogo) no siempre llega a la lámina:
    // se escucha también en la ventana, y si se pierde la captura se termina con el último punto.
    window.addEventListener("pointerup", (ev) => { if (dibujo || mover) soltar(ev); });
    lamina.addEventListener("lostpointercapture", () => { if (dibujo || mover) soltar(null); });
    lamina.addEventListener("pointercancel", () => {
      if (dibujo && dibujo.rect) dibujo.rect.remove();
      dibujo = null;
      mover = null;
      lamina.classList.remove("moviendo");
    });
  }

  function fijarZona(zona) {
    z.zona = zona;
    z.agregada = null;
    const c = catalogo();
    const mmU = c && c.unidades ? c.unidades.mm_por_unidad : null;
    if (mmU && area()) {
      const n = B.leerEscalaEscrita(z.escala);
      const cabe = !n.error && E.tamanoEnHoja(zona, mmU, n.n, c.margen_mm, area()).cabe;
      if (!cabe) { // sin escala o con una que ya no sirve: la sugerida
        const sugerida = E.escalaSugerida(zona, mmU, c.margen_mm, area());
        if (sugerida) {
          z.escala = String(sugerida);
          partes.escala.value = z.escala;
        }
      }
    }
    pintar();
  }

  // ---------------------------------------------------------------------------------------
  // Agregar a la hoja (Fase 10e)
  // ---------------------------------------------------------------------------------------

  /** Lo que va a la hoja ({rect, capas, excluir, modo, desmarcadas, escala, catalogo}) o {error}.
   *  Puede no caber: queda en rojo en la hoja, como un bloque (no se puede exportar así). */
  function datosAgregar() {
    const c = catalogo();
    if (!c || !c.unidades || !c.unidades.mm_por_unidad) {
      return { error: "El DXF no tiene unidades verificadas: no se sabe el tamaño en la hoja." };
    }
    if (!z.zona) return { error: "Dibuje la zona: con el clic izquierdo, arrastre un rectángulo sobre la vista." };
    const n = B.leerEscalaEscrita(z.escala);
    if (n.error) return { error: n.error };
    const f = filtro();
    if (f.error) return { error: f.error };
    return { rect: z.zona.slice(), capas: f.capas, excluir: f.excluir, modo: z.modo, desmarcadas: [...z.desmarcadas],
      escala: n.n, catalogo: c };
  }

  async function agregarALaHoja() {
    const datos = datosAgregar();
    const ui = UI();
    if (datos.error || !ui) {
      z.error = datos.error || "El editor no está listo.";
      pintar();
      return;
    }
    z.error = null;
    if (z.editando) {
      if (ui.actualizarZona(z.editando, datos)) {
        z.agregada = "Zona «" + z.editando + "» cambiada en la hoja (" + B.textoEscala(datos.escala) + "). " +
          "Cierre este cuadro para verla.";
      } else {
        z.error = "La zona «" + z.editando + "» ya no está en la hoja.";
      }
      z.editando = null;
      pintar();
      return;
    }
    z.agregando = true;
    pintar();
    try {
      let nombre;
      if ((z.nombre || "").trim()) {
        const r = E.limpiarNombre(z.nombre);
        if (r.error) throw new Error(r.error);
        if (ui.nombresEnUso().some((x) => x.toLowerCase() === r.nombre.toLowerCase())) {
          throw new Error("Ya hay un elemento «" + r.nombre + "» en el plano: elija otro nombre.");
        }
        nombre = r.nombre;
      } else {
        nombre = (await cliente.nombreZona(ui.nombresEnUso())).nombre; // Zona_01, Zona_02…
      }
      const id = ui.agregarZona(Object.assign({ nombre }, datos));
      z.agregada = "Agregada a la hoja como «" + id + "» (" + B.textoEscala(datos.escala) + "). Cierre este cuadro " +
        "para verla, moverla o cambiarle la escala; puede agregar más zonas (o la misma a otra escala).";
      z.nombre = "";
      partes.nombre.value = "";
    } catch (err) {
      z.error = err.message;
    }
    z.agregando = false;
    pintar();
  }

  // ---------------------------------------------------------------------------------------
  // Pintar
  // ---------------------------------------------------------------------------------------

  function pintar() {
    if (!dialogo) return;
    partes.error.hidden = !z.error;
    partes.error.textContent = z.error || "";
    pintarPreparacion();
    pintarNavegacion();
    pintarLamina();
    pintarOcupado();
    pintarZona();
    pintarCapas();
    pintarTamano();
    pintarBotonExportar();
    pintarResultado();
  }

  /** La línea de la vista previa preparada (la misma del panel del DXF; se consulta allí). */
  function pintarPreparacion() {
    const caja = partes.preparacion;
    const prep = D.textoPreparacion(panelDxf() && panelDxf().preparacion ? panelDxf().preparacion() : null);
    caja.hidden = !prep;
    if (!prep) {
      caja.replaceChildren();
      return;
    }
    caja.className = "preparacion-dxf " + prep.clase;
    const hijos = [];
    if (prep.clase === "preparando") {
      const barra = nodo("progress", { max: "100" });
      if (prep.porcentaje !== null) barra.value = prep.porcentaje;
      hijos.push(barra);
    }
    hijos.push(nodo("span", {}, prep.texto));
    caja.replaceChildren(...hijos);
  }

  function pintarNavegacion() {
    const hijos = [];
    const todo = nodo("button", { type: "button", id: "ver-todo" }, "Todo el Model Space");
    todo.title = "Ver todo (también: doble clic con la rueda)";
    todo.addEventListener("click", verTodo);
    hijos.push(todo);
    for (const g of (z.todo ? z.todo.grupos : [])) {
      const b = nodo("button", { type: "button", class: "grupo-zona", "data-grupo": String(g.numero) }, E.textoGrupo(g));
      b.addEventListener("click", () => verGrupo(g));
      hijos.push(b);
    }
    partes.navegacion.replaceChildren(...hijos);
  }

  /** La imagen escalada a la cámara, los grupos, la zona: todo desde coordenadas del dibujo. */
  function pintarLamina() {
    const l = partes.lamina;
    if (!z.vista || !z.camara) {
      l.replaceChildren();
      l.setAttribute("viewBox", "0 0 100 60");
      return;
    }
    const r = z.vista.resultado;
    const m = r.cad_a_px;
    const [w, h] = r.px;
    const vb = E.cajaAPx(m, z.camara);
    l.setAttribute("viewBox", vb.x + " " + vb.y + " " + vb.ancho + " " + vb.alto);
    const k = imagenPorPantalla(); // px de imagen por px de pantalla
    const hijos = [svg("rect", { class: "fondo-lamina", x: 0, y: 0, width: w, height: h }),
      svg("image", { href: z.vista.url, x: 0, y: 0, width: w, height: h, preserveAspectRatio: "none" })];
    for (const g of (z.todo ? z.todo.grupos : [])) {
      const c = E.cajaAPx(m, g.caja);
      const minimo = 3 * k; // un grupo muy lejano sigue viéndose (3 px de pantalla)
      hijos.push(svg("rect", { class: "grupo-lamina", x: c.x, y: c.y, width: Math.max(c.ancho, minimo),
        height: Math.max(c.alto, minimo) }));
      const t = svg("text", { class: "etiqueta-grupo", x: c.x, y: c.y - 4 * k, "font-size": 13 * k });
      t.textContent = "G" + g.numero;
      hijos.push(t);
    }
    if (z.zona) {
      const c = E.cajaAPx(m, z.zona);
      hijos.push(svg("rect", { class: "zona-lamina", x: c.x, y: c.y, width: Math.max(c.ancho, k),
        height: Math.max(c.alto, k) }));
    }
    l.replaceChildren(...hijos);
  }

  function pintarOcupado() {
    if (!dialogo) return;
    const caja = partes.ocupado;
    const p = z.pidiendo;
    caja.hidden = !p;
    if (!p) {
      caja.replaceChildren();
      return;
    }
    // La primera vista (sin nada que mirar todavía): cuadro grande. Las nítidas: una barra
    // arriba que no tapa el dibujo (se puede seguir acercando, moviendo y dibujando).
    caja.className = "ocupado-zonas " + (z.vista ? "chico" : "grande");
    const barra = nodo("progress", { max: "100" });
    const a = p.foto && p.foto.avance;
    if (a && typeof a.percent === "number") barra.value = a.percent;
    const texto = (z.vista ? "Pidiendo la vista nítida: " : "") +
      (p.foto ? D.textoAvance(p.foto) : "pidiendo la vista previa…") +
      " · lleva " + E.textoTranscurrido((Date.now() - p.inicio) / 1000);
    const cancelar = nodo("button", { type: "button", id: "cancelar-vista" }, "Cancelar");
    cancelar.addEventListener("click", cancelarVista);
    const hijos = z.vista ? [barra, nodo("span", { class: "dato" }, texto), cancelar]
      : [nodo("div", { class: "nombre" }, "Trabajando…"), barra, nodo("div", { class: "dato" }, texto)];
    if (!z.vista && p.explicacion) hijos.push(nodo("div", { class: "dato" }, p.explicacion));
    if (!z.vista) hijos.push(cancelar);
    caja.replaceChildren(...hijos);
  }

  function cancelarVista() {
    const p = z.pidiendo;
    if (!p) return;
    z.pidiendo = null;
    if (p.foto) cliente.cancelar(p.foto.id).catch(() => {});
    pintar();
  }

  function pintarZona() {
    const c = catalogo();
    const unidades = c && c.unidades ? c.unidades.nombre : null;
    partes.textoZona.textContent = z.zona ? E.textoZona(z.zona, unidades)
      : "Sin zona: con el clic izquierdo, arrastre un rectángulo sobre la vista.";
    partes.borrar.disabled = !z.zona;
  }

  function pintarCapas() {
    const filas = E.ordenarCapas(z.filas);
    const mostradas = filas.filter((f) => z.verVacias || f.entidades > 0 || z.desmarcadas.has(f.nombre));
    const hijos = [];
    for (const f of mostradas) {
      const l = nodo("label", { class: "capa-zona" + (f.estado_cad ? " oculta" : "") });
      const casilla = nodo("input", { type: "checkbox", "data-capa": f.nombre });
      casilla.checked = !z.desmarcadas.has(f.nombre);
      casilla.addEventListener("change", () => {
        if (casilla.checked) z.desmarcadas.delete(f.nombre);
        else z.desmarcadas.add(f.nombre);
        pintarResumenCapas();
        pintarBotonExportar();
        if (z.conFiltro) programarNitida();
      });
      l.append(casilla, " " + f.nombre + " (" + f.entidades + ")");
      const estadoCad = E.textoEstadoCad(f);
      if (estadoCad) l.title = estadoCad;
      hijos.push(l);
    }
    if (!filas.length) hijos.push(nodo("div", { class: "vacio" }, "Las capas aparecen con la vista previa."));
    else if (!mostradas.length) hijos.push(nodo("div", { class: "vacio" }, "Ninguna capa con algo en esta vista."));
    partes.listaCapas.replaceChildren(...hijos);
    partes.casillaVacias.checked = z.verVacias;
    partes.casillaFiltro.checked = z.conFiltro;
    pintarResumenCapas();
  }

  function pintarResumenCapas() {
    const f = filtro();
    partes.resumenCapas.textContent = z.capas.length
      ? "Se exportan: " + E.textoFiltro(f) + " (de " + z.capas.length + " del DXF). Las capas apagadas o " +
        "congeladas en el CAD no se dibujan. La cuenta de cada capa es de lo que se ve en la imagen."
      : "";
  }

  function pintarTamano() {
    const c = catalogo();
    const t = partes.tamano;
    t.classList.remove("no-cabe");
    if (!z.zona) {
      t.textContent = "Dibuje la zona para ver su tamaño en la hoja.";
      return;
    }
    if (!c || !c.unidades || !c.unidades.mm_por_unidad) {
      t.textContent = "El DXF no tiene unidades verificadas: no se sabe el tamaño en la hoja.";
      return;
    }
    const n = B.leerEscalaEscrita(z.escala);
    if (n.error) {
      t.textContent = n.error;
      return;
    }
    const r = E.tamanoEnHoja(z.zona, c.unidades.mm_por_unidad, n.n, c.margen_mm, area());
    t.textContent = "A " + B.textoEscala(n.n) + (n.aviso ? " (" + n.aviso + ")" : "") + ": " + r.texto +
      (r.cabe ? " Cabe en el área de dibujo del A1." : " " + r.aviso);
    if (!r.cabe) t.classList.add("no-cabe");
  }

  function pintarBotonExportar() {
    const datos = datosAgregar();
    const b = partes.agregar;
    b.textContent = z.editando ? "Guardar cambios en «" + z.editando + "»" : "Agregar a la hoja";
    b.disabled = !!datos.error || z.agregando;
    b.title = datos.error || (z.editando ? "Cambia el rectángulo, las capas o la escala de esa zona en la hoja"
      : "Pone la zona en el A1 como borrador, con su tamaño real a esa escala (se exporta desde la hoja)");
    partes.dejar.hidden = !z.editando;
    partes.nombre.disabled = !!z.editando;
    partes.nombre.title = z.editando ? "El nombre de una zona de la hoja se cambia en el panel Selección." : "";
    const e = panelDxf() && panelDxf().estilo ? panelDxf().estilo() : null;
    partes.estiloTexto.textContent = e ? "Vistas con el estilo: " + D.textoEstilo(e) + " (el del panel del DXF)." : "";
  }

  function pintarResultado() {
    const caja = partes.resultado;
    caja.replaceChildren(...(z.agregando ? [nodo("div", { class: "dato" }, "Agregando a la hoja…")]
      : z.agregada ? [nodo("div", { class: "ok-zona" }, z.agregada)] : []));
  }

  // Lo usa editor_panel_dxf.js (botón «Zonas del modelo…»).
  window.EditorPanelZonas = { abrir, editar };
})();
