/*
 * Editor de planos — botón «Cargar DXF» y carpeta de bloques (etapa 1), «Agregar al plano» y
 * vistas previas PNG (etapa 2). Solo pantalla: la conexión está en editor_servidor.js, los
 * textos en editor_dxf.js y los bloques en la hoja en editor_ui.js (window.EditorUI).
 *
 * Sin servidor (editor abierto con doble clic) el botón queda desactivado con una explicación
 * y el panel no se muestra: el editor es el de siempre (un plano versión 3 se abre igual, con
 * las cajas sin vista previa).
 *
 * Etapa 3, «Exportar bloques del plano»: un pedido por bloque (el servidor los pone en cola,
 * uno a la vez), cada uno con su barra de avance y «Cancelar»; «Cancelar todo» y «Detener a la
 * fuerza» (cierra el trabajador sin esperar: hay que volver a cargar el DXF). Cada bloque
 * exportado (o que ya estaba publicado) pasa a ser un detalle normal en la hoja
 * (window.EditorUI.aplicarExportado).
 *
 * window.EditorPanelDxf (lo usa editor_ui.js):
 *   previa(bloque)  → {estado: "pidiendo"|"lista"|"error"|"sin_dxf"|"recargar"|"sin_servidor",
 *                      url, datos: {px, cad_a_px, ...}, caja_cad, mm_por_unidad, mensaje}
 *                     La primera vez que se pregunta por un bloque del DXF cargado, la pide.
 *   soltar(bloque)  → ya no hace falta (se quitó del plano): cancela la que esperaba turno.
 *   reintentar(bloque) → olvida un error para volver a pedirla.
 * Una vista previa es la de un DXF (sha256) y un handle: sirve a cualquier escala.
 *
 * Vista previa preparada (exportador 1.2): «Cargar DXF» manda el estilo elegido para que la
 * preparación empiece con la carga; una línea en la carpeta dice «Preparando la vista previa…
 * 61 % · lleva 32 s», «Vista previa lista» o por qué falló. Mientras se prepara, el estado se
 * consulta cada segundo. Con un exportador 1.0/1.1 no hay línea.
 *
 * «Zonas del modelo…» (Fase 10d): botón de la carpeta que abre el diálogo de
 * editor_panel_zonas.js (window.EditorPanelZonas). La carga del DXF muestra cuánto lleva.
 *
 * Bloques anónimos (*U que ofrece el trabajador): subsección «Anónimos (opcionales) (N)»,
 * cerrada por defecto, con un filtro por texto y las mismas tarjetas (nombre = etiqueta, capa +
 * handle). Cada tarjeta tiene «Ver vista previa»: la misma vista previa del bloque (la que
 * después usa la caja en la hoja), en pequeño dentro de la tarjeta, para reconocerlo antes de
 * agregarlo.
 */
(function () {
  "use strict";

  const S = window.EditorServidor;
  const D = window.EditorDxf;
  const boton = document.getElementById("btn-cargar-dxf");
  const panel = document.getElementById("panel-dxf");
  const conexion = S.detectar(window.location);
  const SIN_SERVIDOR = "Para cargar un DXF, abra el editor con «Abrir editor.bat» (servidor local con " +
    "el exportador). Con doble clic en editor.html el editor funciona igual, sin esta opción.";
  const LATIDO_MS = 60000;

  const vista = { estado: null, tarea: null, error: null, ocupado: false, recargar: null,
    exportacion: { trabajos: [], omitidos: [], pidiendo: false },
    anonimos: { abierto: false, filtro: "" }, // la subsección se recuerda entre repintados
    miniaturas: new Set(), // "sha256|handle" de las tarjetas con «Ver vista previa» abierta
    // Estilo de impresión: la lista del servidor (/api/estilos) y el elegido {ctb, transparencia}.
    // No se guarda en el plano: al abrir el editor, el de componedor.json.
    estilos: null, estilo: null };
  const previas = new Map(); // "sha256|handle|estilo" → estado de su vista previa
  window.EditorPruebaDxf = { vista, conexion, previas };
  const UI = () => window.EditorUI || null;

  if (!conexion) {
    boton.disabled = true;
    boton.title = SIN_SERVIDOR;
    panel.hidden = true;
    window.EditorPanelDxf = {
      previa: () => ({ estado: "sin_servidor", mensaje: "Sin vista previa: el editor se abrió sin servidor " +
        "(use «Abrir editor.bat» y cargue el DXF)." }),
      soltar: () => {}, reintentar: () => {},
    };
    return;
  }

  const cliente = S.crearCliente(conexion, window.fetch.bind(window));

  function nodo(nombre, atributos, texto) {
    const n = document.createElement(nombre);
    for (const [k, v] of Object.entries(atributos || {})) n.setAttribute(k, v);
    if (texto !== undefined) n.textContent = texto; // nunca HTML: los nombres vienen del DXF
    return n;
  }

  /** Caja de error: el mensaje claro y, si hay, «Ver detalle» con el texto técnico. */
  function cajaError(foto, clase) {
    const caja = nodo("div", { class: clase }, D.textoError(foto));
    const detalle = D.textoDetalle(foto);
    if (detalle) {
      const ver = nodo("details", { class: "detalle-error" });
      ver.appendChild(nodo("summary", {}, "Ver detalle"));
      ver.appendChild(nodo("pre", {}, detalle));
      caja.appendChild(ver);
    }
    return caja;
  }

  function lista(textos, clase) {
    const ul = nodo("ul", { class: clase });
    for (const t of textos) ul.appendChild(nodo("li", {}, t));
    return ul;
  }

  function tarjetaBloque(b, catalogo) {
    const t = nodo("div", { class: "bloque-dxf" + (b.anonimo ? " anonimo" : ""), "data-ref": b.ref });
    t.appendChild(nodo("div", { class: "nombre" }, D.nombreBloque(b)));
    for (const linea of D.lineasBloque(b)) t.appendChild(nodo("div", { class: "dato" }, linea));
    if (b.notas.length) t.appendChild(lista(b.notas, "notas-bloque"));
    const agregar = nodo("button", { type: "button" }, "Agregar al plano");
    const usable = !!(b.tamano_m && b.unidades && b.unidades.verificadas);
    agregar.disabled = !usable || !UI();
    agregar.title = usable ? "Caja exacta a la escala sugerida, en el centro del área de dibujo"
      : "Sin unidades verificadas no se sabe su tamaño en papel.";
    agregar.addEventListener("click", () => UI() && UI().agregarBloque(b, catalogo));
    const botones = nodo("div", { class: "botones" });
    botones.appendChild(agregar);
    const k = catalogo.dxf.sha256 + "|" + b.handle;
    const ver = nodo("button", { type: "button", class: "ver-previa" },
      vista.miniaturas.has(k) ? "Ocultar vista previa" : "Ver vista previa");
    ver.title = "La vista previa del bloque (solo capas visibles), para reconocerlo antes de agregarlo";
    ver.addEventListener("click", () => {
      if (vista.miniaturas.has(k)) vista.miniaturas.delete(k);
      else {
        vista.miniaturas.add(k);
        reintentar({ dxf: catalogo.dxf, handle: b.handle }); // si había fallado, se vuelve a pedir
      }
      pintar();
    });
    botones.appendChild(ver);
    t.appendChild(botones);
    if (vista.miniaturas.has(k)) {
      const m = nodo("div", { class: "miniatura-dxf", "data-previa": k });
      pintarMiniatura(m, { dxf: catalogo.dxf, handle: b.handle });
      t.appendChild(m);
    }
    return t;
  }

  /** La vista previa dentro de la tarjeta: la imagen, o en qué va / por qué no hay. */
  function pintarMiniatura(caja, b) {
    const e = previa(b);
    if (e.estado === "lista" && e.url) {
      const img = nodo("img", { src: e.url, alt: "Vista previa (solo capas visibles)" });
      caja.replaceChildren(img);
    } else {
      caja.replaceChildren(nodo("div", { class: "dato" },
        e.estado === "pidiendo" ? "Pidiendo vista previa…" : e.mensaje || "Sin vista previa."));
    }
  }

  /** Las miniaturas abiertas, después de que llega (o falla) una vista previa. */
  function pintarMiniaturas() {
    const catalogo = vista.estado && vista.estado.dxf;
    if (!catalogo) return;
    for (const caja of panel.querySelectorAll(".miniatura-dxf")) {
      const handle = caja.getAttribute("data-previa").split("|")[1];
      pintarMiniatura(caja, { dxf: catalogo.dxf, handle });
    }
  }

  /** Las tarjetas de los anónimos que pasan el filtro (hasta D.LIMITE_TARJETAS). */
  function pintarAnonimos(contenedor, catalogo) {
    const { anonimos } = D.separarBloques(catalogo);
    const encontrados = D.filtrarBloques(anonimos, vista.anonimos.filtro);
    const mostrados = encontrados.slice(0, D.LIMITE_TARJETAS);
    const textos = D.textosAnonimos(catalogo, encontrados.length, mostrados.length);
    const hijos = [];
    if (textos.mostrando) hijos.push(nodo("div", { class: "dato mostrando" }, textos.mostrando));
    for (const b of mostrados) hijos.push(tarjetaBloque(b, catalogo));
    if (!encontrados.length && anonimos.length) {
      hijos.push(nodo("div", { class: "vacio" }, "Ningún anónimo coincide con el filtro."));
    }
    contenedor.replaceChildren(...hijos);
  }

  /** «Anónimos (opcionales) (N)»: cerrada por defecto; null si no hay ninguno ni pequeños. */
  function seccionAnonimos(catalogo) {
    const { anonimos } = D.separarBloques(catalogo);
    const textos = D.textosAnonimos(catalogo);
    if (!anonimos.length && !textos.pequenos) return null;
    const s = nodo("details", { class: "anonimos-dxf" });
    if (vista.anonimos.abierto) s.open = true;
    s.addEventListener("toggle", () => { vista.anonimos.abierto = s.open; });
    s.appendChild(nodo("summary", {}, textos.titulo));
    s.appendChild(nodo("div", { class: "dato" }, textos.explicacion));
    if (textos.pequenos) s.appendChild(nodo("div", { class: "dato" }, textos.pequenos));
    if (anonimos.length) {
      const filtro = nodo("input", { type: "search", id: "filtro-anonimos", autocomplete: "off",
        placeholder: "Filtrar por capa o handle", "aria-label": "Filtrar los bloques anónimos" });
      filtro.value = vista.anonimos.filtro;
      const tarjetas = nodo("div", { class: "bloques-dxf" });
      filtro.addEventListener("input", () => {
        vista.anonimos.filtro = filtro.value;
        pintarAnonimos(tarjetas, catalogo); // solo las tarjetas: el cuadro conserva el foco
      });
      s.appendChild(filtro);
      pintarAnonimos(tarjetas, catalogo);
      s.appendChild(tarjetas);
    }
    return s;
  }

  function carpeta(catalogo) {
    const c = nodo("details", { class: "carpeta-dxf", open: "" });
    const resumen = nodo("summary");
    resumen.appendChild(nodo("span", { class: "nombre" }, catalogo.dxf.nombre));
    resumen.appendChild(nodo("span", { class: "dato" }, " · " + D.resumenDxf(catalogo)));
    c.appendChild(resumen);
    c.appendChild(nodo("div", { class: "dato" }, D.detalleDxf(catalogo)));
    const prep = D.textoPreparacion(catalogo.preparacion);
    if (prep) {
      const linea = nodo("div", { class: "preparacion-dxf " + prep.clase, id: "preparacion-dxf" });
      if (prep.clase === "preparando") {
        const barra = nodo("progress", { max: "100" });
        if (prep.porcentaje !== null) barra.value = prep.porcentaje;
        linea.appendChild(barra);
      }
      linea.appendChild(nodo("span", {}, prep.texto));
      c.appendChild(linea);
    }
    if (window.EditorPanelZonas) {
      const zonas = nodo("button", { type: "button", id: "btn-zonas-modelo" }, "Zonas del modelo…");
      zonas.disabled = !catalogo.sesion_activa || !!vista.recargar;
      zonas.title = zonas.disabled ? "Vuelva a cargar el DXF para usar las zonas del modelo."
        : "Ver el Model Space, dibujar una zona y exportarla como un detalle más";
      zonas.addEventListener("click", () => window.EditorPanelZonas.abrir());
      c.appendChild(zonas);
    }
    if (!catalogo.sesion_activa || vista.recargar) {
      const aviso = nodo("div", { class: "aviso-dxf" }, vista.recargar ||
        "El trabajador del exportador se reinició desde que se cargó este DXF: la lista sigue " +
        "sirviendo para mirar, pero vuelva a cargarlo para ver vistas previas y antes de exportar.");
      const volver = nodo("button", { type: "button" }, "Volver a cargar");
      volver.disabled = !!(vista.tarea && !S.FINALES.includes(vista.tarea.estado));
      volver.addEventListener("click", recargar);
      aviso.appendChild(volver);
      c.appendChild(aviso);
    }
    if (catalogo.avisos.length) c.appendChild(lista(catalogo.avisos, "avisos-dxf"));
    if (catalogo.problemas.length) c.appendChild(lista(catalogo.problemas, "problemas-dxf"));
    const bloques = nodo("div", { class: "bloques-dxf" });
    const { nombrados, anonimos } = D.separarBloques(catalogo);
    for (const b of nombrados) bloques.appendChild(tarjetaBloque(b, catalogo));
    if (!nombrados.length) {
      bloques.appendChild(nodo("div", { class: "vacio" }, anonimos.length
        ? "Ningún bloque con nombre: vea «Anónimos (opcionales)»." : "Ningún bloque exportable."));
    }
    c.appendChild(bloques);
    const seccion = seccionAnonimos(catalogo);
    if (seccion) c.appendChild(seccion);
    if (catalogo.omitidos.length) {
      const o = nodo("details", { class: "omitidos-dxf" });
      o.appendChild(nodo("summary", {}, "No exportables (" + catalogo.omitidos.length + ")"));
      o.appendChild(lista(catalogo.omitidos.map((x) => x.nombre +
        (x.total_ocurrencias > 1 ? " (ocurrencia " + x.ocurrencia + " de " + x.total_ocurrencias + ")" : "") +
        ": " + x.motivo), "omitidos"));
      c.appendChild(o);
    }
    return c;
  }

  function pintar() {
    const hijos = [];
    const e = vista.estado;
    const exportador = e ? e.exportador : null;
    const disponible = !!(exportador && exportador.disponible);
    const enCurso = vista.tarea && !S.FINALES.includes(vista.tarea.estado);
    boton.disabled = !disponible || enCurso || vista.ocupado;
    boton.title = disponible ? "Elegir un DXF y ver la lista de sus bloques"
      : (exportador ? exportador.mensaje : "Conectando con el servidor local…");
    if (vista.error) hijos.push(nodo("div", { class: "error-dxf" }, vista.error));
    if (exportador && !disponible) hijos.push(nodo("div", { class: "aviso-dxf" }, exportador.mensaje));
    const trabajador = exportador && exportador.trabajador;
    if (trabajador && trabajador.estado === "detenido") {
      const caja = nodo("div", { class: "error-dxf" }, trabajador.mensaje || "El trabajador está detenido.");
      const reiniciar = nodo("button", { type: "button" }, "Reiniciar trabajador");
      reiniciar.addEventListener("click", () => accion(() => cliente.reiniciar()));
      caja.appendChild(reiniciar);
      hijos.push(caja);
    }
    if (enCurso) {
      const caja = nodo("div", { class: "progreso-dxf" });
      const barra = nodo("progress", { max: "100" });
      if (typeof vista.tarea.avance.percent === "number") barra.value = vista.tarea.avance.percent;
      caja.appendChild(barra);
      let texto = D.textoAvance(vista.tarea);
      if (vista.inicioTarea && window.EditorZonas) {
        texto += " · lleva " + window.EditorZonas.textoTranscurrido((Date.now() - vista.inicioTarea) / 1000);
      }
      caja.appendChild(nodo("div", { class: "dato" }, texto));
      const cancelar = nodo("button", { type: "button" }, "Cancelar");
      cancelar.disabled = !!vista.tarea.cancelando;
      cancelar.addEventListener("click", () => accion(() => cliente.cancelar(vista.tarea.id)));
      caja.appendChild(cancelar);
      hijos.push(caja);
    } else if (vista.tarea && vista.tarea.estado !== "terminada") {
      hijos.push(cajaError(vista.tarea, vista.tarea.estado === "cancelada" ? "aviso-dxf" : "error-dxf"));
    }
    if (e && e.dxf) hijos.push(carpeta(e.dxf));
    // Repintar no debe quitarle el foco al filtro de anónimos mientras se escribe.
    const activo = document.activeElement;
    const enFiltro = activo && activo.id === "filtro-anonimos" ? [activo.selectionStart, activo.selectionEnd] : null;
    panel.replaceChildren(...hijos);
    if (enFiltro) {
      const nuevo = document.getElementById("filtro-anonimos");
      if (nuevo) {
        nuevo.focus();
        nuevo.setSelectionRange(enFiltro[0], enFiltro[1]);
      }
    }
    pintarExportar();
    pintarEstilo();
    panel.hidden = !hijos.length;
  }

  async function refrescar() {
    const antes = vista.estado && vista.estado.dxf;
    try {
      vista.estado = await cliente.estado();
      vista.error = null;
    } catch (err) {
      vista.error = err.message;
    }
    const ahora = vista.estado && vista.estado.dxf;
    if (ahora && (!antes || antes.sesion !== ahora.sesion || antes.sesion_activa !== ahora.sesion_activa)) {
      alCambiarCarpeta(ahora);
    }
    pintar();
    seguirPreparacion();
  }

  // Mientras el exportador prepara la vista previa, preguntar cada segundo (avance y «lista»).
  let preguntaPreparacion = null;
  function seguirPreparacion() {
    const p = vista.estado && vista.estado.dxf && vista.estado.dxf.preparacion;
    if (!p || p.estado !== "preparando" || preguntaPreparacion) return;
    preguntaPreparacion = setTimeout(async () => {
      preguntaPreparacion = null;
      const activo = document.activeElement; // no repintar debajo de un cuadro que se edita
      if (activo && activo.id === "filtro-anonimos") {
        seguirPreparacion();
        return;
      }
      await refrescar();
    }, 1000);
  }

  /** Carpeta nueva (o la misma con otra sesión): las vistas previas que fallaron o esperaban
   *  se vuelven a pedir; las listas siguen sirviendo si el DXF (sha256) es el mismo. */
  function alCambiarCarpeta(catalogo) {
    if (catalogo.sesion_activa) vista.recargar = null;
    for (const [k, e] of previas) {
      if (e.estado !== "lista" || !k.startsWith(catalogo.dxf.sha256 + "|")) previas.delete(k);
    }
    if (UI()) UI().catalogoCambiado(catalogo);
  }

  // ---------------------------------------------------------------------------------------
  // Vistas previas (etapa 2).
  // ---------------------------------------------------------------------------------------

  const clave = (b) => b.dxf.sha256 + "|" + b.handle + "|" + D.claveEstilo(vista.estilo);
  const avisarUI = () => {
    pintarMiniaturas();
    if (UI()) UI().refrescar();
  };

  function previa(b) {
    const k = clave(b);
    if (previas.has(k)) return previas.get(k);
    const catalogo = vista.estado && vista.estado.dxf;
    if (!catalogo || catalogo.dxf.sha256 !== b.dxf.sha256) {
      return { estado: "sin_dxf", mensaje: "Sin vista previa: cargue «" + b.dxf.nombre + "» con «Cargar DXF»." };
    }
    if (!catalogo.sesion_activa || vista.recargar) {
      return { estado: "recargar", mensaje: "Sin vista previa: vuelva a cargar el DXF («Volver a cargar»)." };
    }
    const bc = catalogo.bloques.find((x) => x.handle === b.handle);
    if (!bc) return { estado: "error", mensaje: "El bloque ya no está en el DXF cargado." };
    const e = { estado: "pidiendo", ref: bc.ref, caja_cad: bc.caja_cad, estilo: vista.estilo,
      mm_por_unidad: bc.unidades ? bc.unidades.mm_por_unidad : null, url: null, datos: null, tarea: null };
    if (!e.caja_cad || !e.mm_por_unidad) {
      return { estado: "error", mensaje: "El trabajador no dio la caja o las unidades del bloque: sin vista previa." };
    }
    previas.set(k, e);
    pedirPrevia(k, e);
    return e;
  }

  async function pedirPrevia(k, e) {
    try {
      const r = await cliente.previa(e.ref, e.estilo || undefined);
      e.tarea = r.tarea.id;
      const fin = await S.seguirTarea(cliente, r.tarea.id, () => {});
      if (previas.get(k) !== e) return; // se soltó mientras tanto
      if (fin.estado === "terminada" && /^\/api\/previas\/t-\d+$/.test(fin.resultado.url)) {
        e.url = URL.createObjectURL(await cliente.png(fin.resultado.url));
        e.datos = fin.resultado;
        e.estado = "lista";
      } else {
        const codigo = fin.error && fin.error.codigo;
        if (codigo === "DXF_CHANGED" || codigo === "NO_SESSION") {
          previas.delete(k);
          vista.recargar = codigo === "DXF_CHANGED"
            ? "El DXF cambió en el disco desde que se cargó: vuelva a cargarlo para ver las vistas previas."
            : "El trabajador ya no tiene este DXF cargado: vuelva a cargarlo.";
          pintar();
        } else if (fin.estado === "cancelada") {
          previas.delete(k);
        } else {
          e.estado = "error";
          e.mensaje = "Vista previa: " + D.textoError(fin);
        }
      }
    } catch (err) {
      if (previas.get(k) !== e) return;
      if (err.estadoHttp === 409) {
        previas.delete(k);
        vista.recargar = err.message;
        pintar();
      } else {
        e.estado = "error";
        e.mensaje = "Vista previa: " + err.message;
      }
    }
    avisarUI();
  }

  function soltar(b) {
    const k = clave(b);
    const e = previas.get(k);
    if (!e || e.estado !== "pidiendo") return;
    previas.delete(k);
    if (e.tarea) cliente.cancelar(e.tarea).catch(() => {});
  }

  function reintentar(b) {
    const e = previas.get(clave(b));
    if (e && e.estado === "error") previas.delete(clave(b));
  }

  // La sección «Exportar» va en su propio contenedor (debajo del panel): el editor la repinta
  // cuando cambia el plano sin volver a dibujar la carpeta.
  const anfitrion = document.createElement("div");
  anfitrion.id = "exportar-dxf";
  panel.after(anfitrion);
  // El estilo de impresión, entre la carpeta y «Exportar»: se arma una vez (no en cada repintado,
  // así el selector no se cierra mientras se elige).
  const anfitrionEstilo = document.createElement("div");
  anfitrionEstilo.id = "estilo-dxf";
  anfitrionEstilo.hidden = true;
  anfitrion.before(anfitrionEstilo);

  /** El estilo elegido con el SHA-256 de su tabla: {ctb, sha256, transparencia}; null sin lista. */
  function estiloElegido() {
    if (!vista.estilo) return null;
    const t = vista.estilo.ctb && vista.estilos.estilos.find((x) => x.nombre === vista.estilo.ctb);
    return { ctb: vista.estilo.ctb, sha256: t ? t.sha256 : null, transparencia: vista.estilo.transparencia };
  }

  function pintarEstilo() {
    const e = vista.estado;
    const visible = !!(vista.estilos && e && e.exportador && e.exportador.disponible && e.dxf);
    anfitrionEstilo.hidden = !visible;
    if (!visible) {
      anfitrionEstilo.replaceChildren();
      return;
    }
    if (anfitrionEstilo.firstChild) return;
    const caja = nodo("div", { class: "estilo-dxf" });
    caja.appendChild(nodo("div", { class: "nombre" }, "Estilo de impresión"));
    const fila = nodo("div", { class: "fila" });
    fila.appendChild(nodo("label", { for: "estilo-ctb" }, "Tabla (CTB)"));
    const selector = nodo("select", { id: "estilo-ctb" });
    selector.appendChild(nodo("option", { value: "" }, "Sin CTB"));
    for (const t of vista.estilos.estilos) {
      const o = nodo("option", { value: t.nombre }, t.nombre);
      o.title = t.descripcion || "";
      selector.appendChild(o);
    }
    selector.value = vista.estilo.ctb || "";
    fila.appendChild(selector);
    const casilla = nodo("label", { class: "casilla-transparencia" });
    const marca = nodo("input", { type: "checkbox", id: "imprimir-transparencia" });
    marca.checked = vista.estilo.transparencia !== false;
    casilla.append(marca, " Imprimir transparencia");
    casilla.title = "Sin marcar, no se dibujan los rellenos con transparencia del 80 % o más " +
      "(veladuras casi invisibles, como las de los paneles de PVcase).";
    const descripcion = nodo("div", { class: "dato descripcion-ctb" });
    const ayuda = nodo("div", { class: "dato" }, "Para las vistas previas y «Exportar». Los detalles ya " +
      "exportados se quedan como están (el panel Selección dice con qué estilo salieron).");
    const describir = () => {
      const t = vista.estilos.estilos.find((x) => x.nombre === vista.estilo.ctb);
      descripcion.textContent = t ? (t.descripcion || "(sin descripción)") + " · SHA-256 " + t.sha256.slice(0, 12) + "…"
        : "Colores y grosores del DXF, sin tabla de impresión.";
    };
    const cambiar = () => {
      vista.estilo = { ctb: selector.value || null, transparencia: marca.checked };
      describir();
      pintarExportar();
      pintarMiniaturas(); // cada estilo tiene su vista previa: se piden las que falten
      if (UI()) UI().refrescar();
    };
    selector.addEventListener("change", cambiar);
    marca.addEventListener("change", cambiar);
    describir();
    caja.append(fila, casilla, descripcion);
    if (vista.estilos.aviso) caja.appendChild(nodo("div", { class: "aviso-dxf" }, vista.estilos.aviso));
    caja.appendChild(ayuda);
    anfitrionEstilo.replaceChildren(caja);
  }

  async function cargarEstilos() {
    try {
      vista.estilos = await cliente.estilos();
    } catch (err) {
      vista.estilos = { estilos: [], por_defecto: { ctb: null, transparencia: true },
        aviso: "No se pudo leer la lista de tablas de estilos: " + err.message };
    }
    vista.estilo = { ctb: vista.estilos.por_defecto.ctb, transparencia: vista.estilos.por_defecto.transparencia };
  }
  function pintarExportar() {
    const seccion = seccionExportar();
    anfitrion.replaceChildren(...(seccion ? [seccion] : []));
    anfitrion.hidden = !seccion;
  }

  window.EditorPanelDxf = { previa, soltar, reintentar, alCambiarPlano: () => pintarExportar(),
    // El estilo de impresión elegido ({ctb, sha256, transparencia}) o null (sin lista todavía).
    estilo: estiloElegido,
    // La carpeta del DXF cargado (o null): el panel de la ortofoto toma de aquí dxf.crs.
    catalogo: () => (vista.estado && vista.estado.dxf) || null,
    // El estilo tal como lo pide el servidor ({ctb, transparencia}, sin sha256) o null.
    estiloPedido: () => vista.estilo || null,
    // La vista previa preparada del DXF cargado (dxf.preparacion de /api/estado) o null.
    preparacion: () => (vista.estado && vista.estado.dxf && vista.estado.dxf.preparacion) || null };

  // ---------------------------------------------------------------------------------------
  // Exportar (etapa 3).
  // ---------------------------------------------------------------------------------------

  const B = window.EditorBloques;
  const x = vista.exportacion;
  const enMarcha = (t) => !S.FINALES.includes(t.foto.estado);

  function textoTrabajo(t) {
    const f = t.foto;
    if (enMarcha(t)) return D.textoAvance(f);
    if (f.estado === "terminada") {
      const r = f.resultado;
      let texto = "Exportado: " + r.paquete + (r.en_cache ? " (ya estaba publicado: se usó tal cual)" : "") +
        " · estilo: " + D.textoEstilo(r.estilo);
      if (r.movidos && r.movidos.length) texto += " · " + r.movidos.length + " archivo(s) viejos movidos a _para_borrar";
      return texto;
    }
    return D.textoError(f);
  }

  function seccionExportar() {
    const ui = UI();
    const bloques = ui ? ui.colocaciones().filter((c) => c.bloque).length : 0;
    if (!bloques && !x.trabajos.length) return null;
    const caja = nodo("div", { class: "exportar-dxf" });
    caja.appendChild(nodo("div", { class: "nombre" }, "Exportar"));
    const enCurso = x.trabajos.some(enMarcha);
    const boton = nodo("button", { type: "button", id: "btn-exportar" },
      "Exportar bloques del plano (" + bloques + ")");
    boton.disabled = !bloques || enCurso || x.pidiendo;
    boton.title = "Un paquete (PDF + manifiesto) por bloque, a su escala, en la carpeta de paquetes del DXF";
    boton.addEventListener("click", exportar);
    caja.appendChild(boton);
    if (vista.estilo) {
      caja.appendChild(nodo("div", { class: "dato estilo-exportar" }, "Con el estilo: " + D.textoEstilo(estiloElegido())));
    }
    if (x.omitidos.length) {
      caja.appendChild(lista(x.omitidos.map((o) => "'" + o.id + "' no se exporta: " + o.motivo + "."), "avisos-dxf"));
    }
    for (const t of x.trabajos) {
      const fila = nodo("div", { class: "trabajo-exportar " + t.foto.estado, "data-tarea": t.foto.id });
      fila.appendChild(nodo("div", { class: "nombre" }, t.ids.join(", ") + " · " + B.textoEscala(t.escala)));
      if (enMarcha(t)) {
        const barra = nodo("progress", { max: "100" });
        if (typeof (t.foto.avance || {}).percent === "number") barra.value = t.foto.avance.percent;
        fila.appendChild(barra);
      }
      if (t.foto.estado === "fallida") fila.appendChild(cajaError(t.foto, "dato"));
      else fila.appendChild(nodo("div", { class: "dato" }, textoTrabajo(t)));
      if (enMarcha(t)) {
        const cancelar = nodo("button", { type: "button" }, "Cancelar");
        cancelar.disabled = !!t.foto.cancelando;
        cancelar.addEventListener("click", () => cliente.cancelar(t.foto.id).catch((err) => {
          vista.error = err.message;
          pintar();
        }));
        fila.appendChild(cancelar);
      }
      caja.appendChild(fila);
    }
    if (enCurso) {
      const botones = nodo("div", { class: "botones" });
      const todo = nodo("button", { type: "button" }, "Cancelar todo");
      todo.addEventListener("click", () => {
        for (const t of x.trabajos.filter(enMarcha)) cliente.cancelar(t.foto.id).catch(() => {});
      });
      const fuerza = nodo("button", { type: "button", class: "peligro" }, "Detener a la fuerza");
      fuerza.title = "Cierra el trabajador del exportador sin esperar a que cancele. Lo que estaba " +
        "exportando se descarta y hay que volver a cargar el DXF.";
      fuerza.addEventListener("click", detenerALaFuerza);
      botones.append(todo, fuerza);
      caja.appendChild(botones);
    }
    return caja;
  }

  async function exportar() {
    const ui = UI();
    if (!ui) return;
    const catalogo = vista.estado && vista.estado.dxf;
    const { pedidos, omitidos } = B.pedidosExportar(ui.colocaciones(), catalogo, ui.zona());
    x.omitidos = omitidos;
    x.trabajos = x.trabajos.filter(enMarcha); // los terminados de antes ya no hacen falta
    if (!pedidos.length) {
      pintar();
      return;
    }
    x.pidiendo = true;
    pintar();
    let r;
    try {
      r = await cliente.exportar(pedidos, vista.estilo || undefined);
    } catch (err) {
      if (err.estadoHttp === 409) vista.recargar = err.message; // DXF cambiado o sesión vencida
      else vista.error = err.message;
      x.pidiendo = false;
      await refrescar();
      return;
    }
    x.pidiendo = false;
    // Dos copias del mismo bloque a la misma escala son UNA tarea (un paquete).
    const porTarea = new Map();
    r.tareas.forEach((foto, i) => {
      if (!porTarea.has(foto.id)) {
        const t = { foto, ids: [], escala: pedidos[i].escala };
        porTarea.set(foto.id, t);
        x.trabajos.push(t);
      }
      porTarea.get(foto.id).ids.push(pedidos[i].id);
    });
    pintar();
    await Promise.all([...porTarea.values()].map(seguirExportacion));
    await refrescar();
  }

  async function seguirExportacion(t) {
    try {
      t.foto = await S.seguirTarea(cliente, t.foto.id, (foto) => {
        t.foto = foto;
        pintar();
      });
    } catch (err) {
      t.foto = Object.assign({}, t.foto, { estado: "fallida", error: { mensaje: err.message } });
    }
    if (t.foto.estado === "terminada" && UI()) {
      for (const id of t.ids) UI().aplicarExportado(id, t.foto.resultado);
    }
    const codigo = t.foto.error && t.foto.error.codigo;
    if (codigo === "DXF_CHANGED" || codigo === "NO_SESSION") {
      vista.recargar = codigo === "DXF_CHANGED"
        ? "El DXF cambió en el disco: vuelva a cargarlo y exporte de nuevo."
        : "El trabajador ya no tiene este DXF cargado: vuelva a cargarlo.";
    }
    pintar();
  }

  async function detenerALaFuerza() {
    if (!window.confirm("¿Detener a la fuerza el trabajador del exportador?\n\nLo que está exportando " +
        "se descarta (no deja archivos a medias) y lo que espera turno se cancela. Después hay que " +
        "volver a cargar el DXF.")) return;
    try {
      await cliente.detener();
    } catch (err) {
      vista.error = err.message;
    }
    await refrescar();
  }

  // Paquetes exportados antes de recargar la página: el editor los reconoce al abrir un plano.
  cliente.exportados().then((r) => UI() && UI().registrarDetalles(r.detalles), () => {});

  async function recargar() {
    vista.error = null;
    try {
      const r = await cliente.recargarDxf(vista.estilo || undefined);
      vista.tarea = r.tarea;
      await seguir(r.tarea.id);
      return;
    } catch (err) {
      vista.error = err.message;
    }
    await refrescar();
  }

  async function accion(fn) {
    try {
      await fn();
    } catch (err) {
      vista.error = err.message;
    }
    await refrescar();
  }

  async function seguir(id) {
    vista.inicioTarea = Date.now(); // para «lleva 1 min 05 s» (la carga de un DXF grande tarda)
    try {
      await S.seguirTarea(cliente, id, (foto) => {
        vista.tarea = foto;
        pintar();
      });
    } catch (err) {
      vista.error = err.message;
    }
    await refrescar();
  }

  boton.addEventListener("click", async () => {
    vista.ocupado = true;
    vista.error = null;
    boton.textContent = "Eligiendo el DXF…";
    pintar();
    try {
      const r = await cliente.elegirDxf(vista.estilo || undefined);
      if (r.tarea) {
        vista.tarea = r.tarea;
        vista.ocupado = false;
        boton.textContent = "Cargar DXF";
        await seguir(r.tarea.id);
        return;
      }
    } catch (err) {
      vista.error = err.message;
    }
    vista.ocupado = false;
    boton.textContent = "Cargar DXF";
    await refrescar();
  });

  setInterval(() => {
    cliente.latido().catch((err) => {
      vista.error = err.message;
      pintar();
    });
  }, LATIDO_MS);

  (async () => {
    await cargarEstilos(); // antes de la carpeta: las vistas previas ya salen con el estilo
    await refrescar();
    // Página recargada a mitad de una carga: seguirla.
    const t = vista.estado && vista.estado.tarea;
    if (t) {
      vista.tarea = t;
      if (!S.FINALES.includes(t.estado)) await seguir(t.id);
      else pintar();
    }
  })();
})();
