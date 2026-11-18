/*
 * Editor de planos — botón «Cargar DXF» y carpeta de bloques (etapa 1), «Agregar al plano» y
 * vistas previas PNG (etapa 2). Solo pantalla: la conexión está en editor_servidor.js, los
 * textos en editor_dxf.js y los bloques en la hoja en editor_ui.js (window.EditorUI).
 *
 * Sin servidor (editor abierto con doble clic) el botón queda desactivado con una explicación
 * y el panel no se muestra: el editor es el de siempre (un plano versión 3 se abre igual, con
 * las cajas sin vista previa). Todavía no se exporta.
 *
 * window.EditorPanelDxf (lo usa editor_ui.js):
 *   previa(bloque)  → {estado: "pidiendo"|"lista"|"error"|"sin_dxf"|"recargar"|"sin_servidor",
 *                      url, datos: {px, cad_a_px, ...}, caja_cad, mm_por_unidad, mensaje}
 *                     La primera vez que se pregunta por un bloque del DXF cargado, la pide.
 *   soltar(bloque)  → ya no hace falta (se quitó del plano): cancela la que esperaba turno.
 *   reintentar(bloque) → olvida un error para volver a pedirla.
 * Una vista previa es la de un DXF (sha256) y un handle: sirve a cualquier escala.
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

  const vista = { estado: null, tarea: null, error: null, ocupado: false, recargar: null };
  const previas = new Map(); // "sha256|handle" → estado de su vista previa
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

  function lista(textos, clase) {
    const ul = nodo("ul", { class: clase });
    for (const t of textos) ul.appendChild(nodo("li", {}, t));
    return ul;
  }

  function tarjetaBloque(b, catalogo) {
    const t = nodo("div", { class: "bloque-dxf", "data-ref": b.ref });
    t.appendChild(nodo("div", { class: "nombre" }, b.nombre));
    for (const linea of D.lineasBloque(b)) t.appendChild(nodo("div", { class: "dato" }, linea));
    if (b.notas.length) t.appendChild(lista(b.notas, "notas-bloque"));
    const agregar = nodo("button", { type: "button" }, "Agregar al plano");
    const usable = !!(b.tamano_m && b.unidades && b.unidades.verificadas);
    agregar.disabled = !usable || !UI();
    agregar.title = usable ? "Caja exacta a la escala sugerida, en el centro del área de dibujo"
      : "Sin unidades verificadas no se sabe su tamaño en papel.";
    agregar.addEventListener("click", () => UI() && UI().agregarBloque(b, catalogo));
    t.appendChild(agregar);
    return t;
  }

  function carpeta(catalogo) {
    const c = nodo("details", { class: "carpeta-dxf", open: "" });
    const resumen = nodo("summary");
    resumen.appendChild(nodo("span", { class: "nombre" }, catalogo.dxf.nombre));
    resumen.appendChild(nodo("span", { class: "dato" }, " · " + D.resumenDxf(catalogo)));
    c.appendChild(resumen);
    c.appendChild(nodo("div", { class: "dato" }, D.detalleDxf(catalogo)));
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
    for (const b of catalogo.bloques) bloques.appendChild(tarjetaBloque(b, catalogo));
    if (!catalogo.bloques.length) bloques.appendChild(nodo("div", { class: "vacio" }, "Ningún bloque exportable."));
    c.appendChild(bloques);
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
      caja.appendChild(nodo("div", { class: "dato" }, D.textoAvance(vista.tarea)));
      const cancelar = nodo("button", { type: "button" }, "Cancelar");
      cancelar.disabled = !!vista.tarea.cancelando;
      cancelar.addEventListener("click", () => accion(() => cliente.cancelar(vista.tarea.id)));
      caja.appendChild(cancelar);
      hijos.push(caja);
    } else if (vista.tarea && vista.tarea.estado !== "terminada") {
      hijos.push(nodo("div", { class: vista.tarea.estado === "cancelada" ? "aviso-dxf" : "error-dxf" },
        D.textoError(vista.tarea)));
    }
    if (e && e.dxf) hijos.push(carpeta(e.dxf));
    panel.replaceChildren(...hijos);
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

  const clave = (b) => b.dxf.sha256 + "|" + b.handle;
  const avisarUI = () => UI() && UI().refrescar();

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
    const e = { estado: "pidiendo", ref: bc.ref, caja_cad: bc.caja_cad,
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
      const r = await cliente.previa(e.ref);
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

  window.EditorPanelDxf = { previa, soltar, reintentar };

  async function recargar() {
    vista.error = null;
    try {
      const r = await cliente.recargarDxf();
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
      const r = await cliente.elegirDxf();
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
