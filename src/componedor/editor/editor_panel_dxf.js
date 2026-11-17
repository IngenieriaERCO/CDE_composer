/*
 * Editor de planos — botón «Cargar DXF» y carpeta de bloques (etapa 1). Solo pantalla: la
 * conexión está en editor_servidor.js y los textos en editor_dxf.js.
 *
 * Sin servidor (editor abierto con doble clic) el botón queda desactivado con una explicación
 * y el panel no se muestra: el editor es el de siempre. Todavía no se arrastran bloques al
 * plano ni se exporta.
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

  const vista = { estado: null, tarea: null, error: null, ocupado: false };
  window.EditorPruebaDxf = { vista, conexion };

  if (!conexion) {
    boton.disabled = true;
    boton.title = SIN_SERVIDOR;
    panel.hidden = true;
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

  function tarjetaBloque(b) {
    const t = nodo("div", { class: "bloque-dxf", "data-ref": b.ref });
    t.appendChild(nodo("div", { class: "nombre" }, b.nombre));
    for (const linea of D.lineasBloque(b)) t.appendChild(nodo("div", { class: "dato" }, linea));
    if (b.notas.length) t.appendChild(lista(b.notas, "notas-bloque"));
    return t;
  }

  function carpeta(catalogo) {
    const c = nodo("details", { class: "carpeta-dxf", open: "" });
    const resumen = nodo("summary");
    resumen.appendChild(nodo("span", { class: "nombre" }, catalogo.dxf.nombre));
    resumen.appendChild(nodo("span", { class: "dato" }, " · " + D.resumenDxf(catalogo)));
    c.appendChild(resumen);
    c.appendChild(nodo("div", { class: "dato" }, D.detalleDxf(catalogo)));
    if (!catalogo.sesion_activa) {
      c.appendChild(nodo("div", { class: "aviso-dxf" },
        "El trabajador del exportador se reinició desde que se cargó este DXF: la lista sigue " +
        "sirviendo para mirar, pero vuelva a cargarlo antes de exportar."));
    }
    if (catalogo.avisos.length) c.appendChild(lista(catalogo.avisos, "avisos-dxf"));
    if (catalogo.problemas.length) c.appendChild(lista(catalogo.problemas, "problemas-dxf"));
    const bloques = nodo("div", { class: "bloques-dxf" });
    for (const b of catalogo.bloques) bloques.appendChild(tarjetaBloque(b));
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
    try {
      vista.estado = await cliente.estado();
      vista.error = null;
    } catch (err) {
      vista.error = err.message;
    }
    pintar();
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
