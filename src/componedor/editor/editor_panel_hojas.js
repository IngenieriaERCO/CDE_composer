/*
 * Proyectos con índice (<proyecto>.hojas.json, plano versión 7) en las pestañas del editor
 * (subfase 8b). Las pestañas reemplazan al selector «Hoja N de M» y a «Nueva hoja a partir de
 * esta»; lo que ya se creó con ellos se abre así: al abrir una de sus hojas, el editor ofrece abrir
 * el proyecto completo, una pestaña por hoja. Los archivos viejos no se tocan: al guardar se
 * propone «<proyecto>_proyecto.json» (versión 8). Hace falta el servidor local para leer las
 * otras hojas.
 *
 *   window.EditorPanelHojas.ofrecerIndice(): después de abrir un plano de las versiones 1 a 7.
 */
(function () {
  "use strict";

  const S = window.EditorServidor;
  const UI = () => window.EditorUI;
  const conexion = S.detectar(window.location);
  const cliente = conexion ? S.crearCliente(conexion, window.fetch.bind(window)) : null;
  const vista = { ocupado: false };
  window.EditorPruebaHojas = { vista };

  async function ofrecerIndice() {
    const ui = UI();
    const archivo = ui ? ui.archivo() : null;
    if (!cliente || !archivo || !ui.viejo()) return false;
    vista.ocupado = true;
    try {
      const info = await cliente.hojas({ archivo });
      if (!info.indice || info.hojas.length < 2) return false;
      if (!confirm("«" + archivo + "» es la hoja " + (info.posicion + 1) + " del proyecto «" + info.indice + "» (" +
        info.hojas.length + " hojas). ¿Abrir el proyecto completo, una pestaña por hoja?\n\nLos archivos no se " +
        "tocan; al guardar se propone «" + info.indice + "_proyecto.json».")) return false;
      const hojas = [];
      for (const h of info.hojas) {
        const r = await cliente.leerPlano(h);
        hojas.push({ nombre: h.replace(/\.json$/i, ""), texto: r.texto });
      }
      return ui.abrirIndice(hojas, info.indice + ".hojas.json");
    } catch (e) {
      ui.mensaje("No se pudo abrir el proyecto completo: " + e.message, "error");
      return false;
    } finally {
      vista.ocupado = false;
    }
  }

  window.EditorPanelHojas = { ofrecerIndice };
})();
