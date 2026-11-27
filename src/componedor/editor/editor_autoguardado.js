/*
 * Copia automática del trabajo sin guardar (subfase 8d), con el servidor local:
 *
 * - Cada minuto, si hay cambios sin guardar y el proyecto cambió desde la última copia, se
 *   escribe editor/<proyecto>.autoguardado.json (planos_editor.py). Nunca pisa el archivo real.
 *   <proyecto> es el nombre del archivo abierto o guardado (sin .json); sin nombre, «sin_nombre».
 * - Al guardar el proyecto, la copia se borra sola.
 * - Al abrir el editor, si hay una copia más nueva que su archivo (o de un proyecto que nunca se
 *   guardó), se ofrece recuperarla; si no se quiere, se ofrece borrarla.
 *
 * Sin el servidor no hace nada (el navegador no puede escribir archivos por su cuenta).
 */
(function () {
  "use strict";

  const S = window.EditorServidor;
  const UI = () => window.EditorUI;
  const conexion = S.detectar(window.location);
  const cliente = conexion ? S.crearCliente(conexion, window.fetch.bind(window)) : null;
  const CADA_MS = 60 * 1000;
  const vista = { base: null, ultimoTexto: null, ultimo: null, error: null, ocupado: false };
  window.EditorPruebaAutoguardado = { vista, ahora: () => autoguardar(), ofrecer: () => ofrecer() };

  /** El nombre de la copia: «Obra.json» y «Obra.hojas.json» → «Obra»; sin nombre, «sin_nombre». */
  function base() {
    const archivo = UI() ? UI().archivo() : null;
    if (!archivo) return "sin_nombre";
    return String(archivo).replace(/\.hojas\.json$/i, "").replace(/\.json$/i, "");
  }

  async function autoguardar() {
    const ui = UI();
    if (!cliente || !ui || vista.ocupado || !ui.hayCambios()) return false;
    const texto = ui.textoPlano();
    const b = base();
    if (texto === vista.ultimoTexto && b === vista.base) return false; // nada nuevo desde la última copia
    vista.ocupado = true;
    try {
      await cliente.guardarAutoguardado({ base: b, archivo: ui.archivo(), viejo: ui.viejo(), texto });
      if (vista.base && vista.base !== b) cliente.borrarAutoguardado(vista.base).catch(() => {}); // cambió el nombre
      vista.base = b;
      vista.ultimoTexto = texto;
      vista.ultimo = Date.now();
      vista.error = null;
      return true;
    } catch (e) {
      vista.error = e.message;
      return false;
    } finally {
      vista.ocupado = false;
    }
  }

  /** Al guardar el proyecto: la copia ya no hace falta. */
  async function alGuardar() {
    if (!cliente) return;
    const bases = new Set([vista.base, base()].filter(Boolean));
    vista.base = null;
    vista.ultimoTexto = null;
    for (const b of bases) await cliente.borrarAutoguardado(b).catch(() => {});
  }

  const hora = (s) => new Date(s * 1000).toLocaleString("es-CO", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });

  /** Al abrir el editor: las copias más nuevas que su archivo se ofrecen para recuperar. */
  async function ofrecer() {
    if (!cliente || !UI()) return false;
    let lista;
    try {
      lista = (await cliente.autoguardados()).autoguardados.filter((c) => c.mas_nueva);
    } catch (e) {
      return false;
    }
    for (const c of lista) {
      const nombre = c.archivo || "el proyecto sin guardar";
      const cuando = hora(c.modificado);
      const detalle = c.archivo_modificado ? " (más nueva que el archivo, guardado el " + hora(c.archivo_modificado) + ")" : "";
      if (confirm("Hay una copia automática de «" + nombre + "» del " + cuando + detalle + ": cambios que no se " +
        "guardaron (¿se cerró el editor o se cayó?).\n\n¿Recuperarla? (El archivo guardado no se toca hasta que " +
        "usted guarde.)")) {
        try {
          const r = await cliente.leerAutoguardado(c.base);
          if (UI().abrirRecuperado(r.texto, r.archivo, r.viejo)) {
            vista.base = c.base;
            vista.ultimoTexto = null;
            return true;
          }
        } catch (e) {
          UI().mensaje("No se pudo recuperar la copia automática: " + e.message, "error");
        }
        return false;
      }
      if (confirm("¿Borrar la copia automática de «" + nombre + "» del " + cuando + "? (Si no, se ofrece la " +
        "próxima vez.)")) {
        await cliente.borrarAutoguardado(c.base).catch(() => {});
      }
    }
    return false;
  }

  window.EditorAutoguardado = { alGuardar, ofrecer, autoguardar };
  if (!cliente) return;
  setInterval(autoguardar, CADA_MS);
  setTimeout(ofrecer, 800); // después de que el editor arranca
})();
