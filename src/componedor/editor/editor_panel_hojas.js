/*
 * Barra «Hoja N de M» y «Nueva hoja a partir de esta» (plano versión 7). Solo con el servidor
 * local («Abrir editor.bat»): escribe la hoja nueva y el índice <proyecto>.hojas.json en la
 * carpeta del editor (planos_editor.py). La lógica sin pantalla está en editor_hojas.js.
 *
 *   window.EditorPanelHojas.refrescar(): vuelve a pedir las hojas del plano abierto (y los
 *   valores automáticos del rótulo).
 */
(function () {
  "use strict";

  const S = window.EditorServidor;
  const H = window.EditorHojas;
  const UI = () => window.EditorUI;
  const selector = document.getElementById("selector-hoja");
  const boton = document.getElementById("btn-nueva-hoja");
  if (!selector || !boton) return;
  const conexion = S.detectar(window.location);
  const cliente = conexion ? S.crearCliente(conexion, window.fetch.bind(window)) : null;
  const vista = { info: null, ocupado: false };
  window.EditorPruebaHojas = { vista };

  if (!cliente) {
    selector.disabled = true;
    boton.disabled = true;
    const motivo = "Varias hojas: abra el editor con «Abrir editor.bat» (hace falta el servidor local).";
    selector.title = motivo;
    boton.title = motivo;
    pintar();
    window.EditorPanelHojas = { refrescar: () => {} };
    return;
  }

  function opcion(valor, texto, elegida) {
    const o = document.createElement("option");
    o.value = valor;
    o.textContent = texto;
    if (elegida) o.selected = true;
    return o;
  }

  function pintar() {
    const info = vista.info;
    const archivo = UI() ? UI().archivo() : null;
    selector.replaceChildren();
    if (!info || !info.indice) {
      selector.appendChild(opcion("", archivo ? "Hoja única · " + archivo : "Hoja sin guardar", true));
      selector.disabled = true;
    } else {
      info.hojas.forEach((h, i) => selector.appendChild(opcion(h, "Hoja " + (i + 1) + " de " + info.hojas.length +
        " · " + h + (info.existen && info.existen[i] === false ? " (no está)" : ""), i === info.posicion)));
      selector.disabled = vista.ocupado;
    }
    boton.disabled = vista.ocupado;
    boton.title = archivo ? "Crea la hoja siguiente con el mismo rótulo y el área de dibujo vacía."
      : "Guarde primero este plano en la carpeta del editor («Guardar plano»).";
  }

  async function refrescar() {
    const archivo = UI() ? UI().archivo() : null;
    if (!archivo) {
      vista.info = null;
      UI() && UI().fijarAutomaticos({});
      pintar();
      return;
    }
    try {
      vista.info = await cliente.hojas({ archivo, rotulo: UI().rotulo() || {},
        campos: H.camposAutomaticos(UI().definicionRotulo()) });
    } catch (e) {
      vista.info = null;
    }
    UI().fijarAutomaticos(vista.info ? vista.info.automaticos : {});
    pintar();
  }

  async function guardarActual() {
    const ui = UI();
    await cliente.guardarPlano(ui.archivo(), ui.textoPlano(), false);
    ui.guardadoEn(ui.archivo());
  }

  async function nuevaHoja() {
    const ui = UI();
    const archivo = ui.archivo();
    if (!archivo) {
      ui.mensaje("Guarde primero este plano en la carpeta del editor («Guardar plano») y vuelva a intentarlo.", "error");
      return;
    }
    vista.ocupado = true;
    pintar();
    try {
      const lista = await cliente.planos();
      if (!lista.planos.some((p) => p.toLowerCase() === archivo.toLowerCase())) {
        ui.mensaje("«" + archivo + "» no está en la carpeta del editor: guárdelo allí («Guardar plano») y vuelva " +
          "a intentarlo.", "error");
        return;
      }
      const info = await cliente.hojas({ archivo, campos: H.camposAutomaticos(ui.definicionRotulo()) });
      const indice = info.indice || H.sinJson(archivo);
      const hojas = info.indice ? info.hojas.slice() : [archivo];
      const posicion = info.indice ? info.posicion : 0;
      const nombre = H.nombreNuevaHoja(indice, lista.planos);
      if (!confirm("Se guardará «" + archivo + "» y se creará «" + nombre + "» con el mismo rótulo (sin título) " +
        "y el área de dibujo vacía. ¿Seguir?")) return;
      // Al crear el índice, «hoja» y «de» de esta hoja pasan a salir solos (si no, diría «1 de 1»).
      if (!info.indice) ui.quitarHojaYDe();
      await guardarActual();
      const { plano } = H.planoNuevaHoja(JSON.parse(ui.textoPlano()), archivo, ui.definicionRotulo());
      const texto = JSON.stringify(plano, null, 2) + "\n";
      await cliente.guardarPlano(nombre, texto, true);
      hojas.splice(posicion + 1, 0, nombre);
      await cliente.guardarIndice(indice, hojas);
      if (!ui.abrirTexto(texto, nombre)) return; // (no debería pasar: la escribió el editor)
      ui.guardadoEn(nombre);
      await refrescar();
      ui.mensaje("Hoja nueva «" + nombre + "» (hoja " + (posicion + 2) + " de " + hojas.length + "): el rótulo se " +
        "copió sin el título; revise notas, convenciones y revisiones. El índice es «" + indice + H.SUFIJO + "».", "ok");
    } catch (e) {
      ui.mensaje("No se pudo crear la hoja nueva: " + e.message, "error");
    } finally {
      vista.ocupado = false;
      pintar();
    }
  }

  async function cambiarHoja(destino) {
    const ui = UI();
    const actual = ui.archivo();
    if (!destino || destino === actual) return;
    vista.ocupado = true;
    pintar();
    try {
      if (ui.hayCambios()) {
        if (!confirm("Hay cambios en «" + actual + "»: se guardan antes de pasar a «" + destino + "». ¿Seguir?")) {
          return;
        }
        await guardarActual();
      }
      const r = await cliente.leerPlano(destino);
      // Si no abre (p. ej. falta un paquete), sigue la hoja de antes con SU nombre: nada se pisa.
      if (ui.abrirTexto(r.texto, r.archivo)) ui.guardadoEn(r.archivo);
    } catch (e) {
      ui.mensaje("No se pudo abrir «" + destino + "»: " + e.message, "error");
    } finally {
      vista.ocupado = false;
      await refrescar();
    }
  }

  boton.addEventListener("click", nuevaHoja);
  selector.addEventListener("change", () => cambiarHoja(selector.value));
  window.EditorPanelHojas = { refrescar, nuevaHoja, cambiarHoja };
  pintar();
})();
