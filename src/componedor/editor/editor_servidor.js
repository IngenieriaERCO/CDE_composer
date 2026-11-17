/*
 * Editor de planos — conexión con el servidor local (etapa 1 de «Cargar DXF»). Sin pantalla:
 * funciona en el navegador (window.EditorServidor) y en Node (module.exports), para probarla
 * desde pytest con un fetch falso.
 *
 * El editor abierto con doble clic (file://) no tiene servidor: `detectar` devuelve null y
 * todo sigue igual que antes. Con «Abrir editor.bat» la página llega desde 127.0.0.1 con el
 * token en la dirección (?t=…); cada pedido a la API lo manda en la cabecera
 * X-Componedor-Token. El editor nunca manda rutas de archivos: el DXF lo elige el cuadro
 * nativo que abre el servidor.
 */
(function (raiz, fabrica) {
  "use strict";
  const api = fabrica();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    raiz.EditorServidor = api;
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const CABECERA = "X-Componedor-Token";
  const FINALES = ["terminada", "fallida", "cancelada"];
  const SIN_CONEXION = "No se pudo hablar con el servidor local: ¿se cerró la ventana de " +
    "«Abrir editor.bat»? El resto del editor sigue funcionando.";

  class ErrorServidor extends Error {
    constructor(mensaje, estadoHttp) {
      super(mensaje);
      this.estadoHttp = estadoHttp;
    }
  }

  /** {token} si la página llegó del servidor local con su token; null si no (file://). */
  function detectar(ubicacion) {
    if (!ubicacion || ubicacion.protocol !== "http:" || ubicacion.hostname !== "127.0.0.1") return null;
    const token = new URLSearchParams(ubicacion.search || "").get("t");
    return token ? { token } : null;
  }

  /** Cliente de la API. `fetchFn` es window.fetch (o uno falso en las pruebas). */
  function crearCliente(conexion, fetchFn) {
    async function pedir(metodo, ruta) {
      const opciones = { method: metodo, cache: "no-store", headers: { [CABECERA]: conexion.token } };
      if (metodo === "POST") {
        opciones.headers["Content-Type"] = "application/json";
        opciones.body = "{}";
      }
      let r;
      try {
        r = await fetchFn(ruta, opciones);
      } catch (e) {
        throw new ErrorServidor(SIN_CONEXION, 0);
      }
      let datos = null;
      try {
        datos = await r.json();
      } catch (e) {
        datos = null;
      }
      if (!r.ok) throw new ErrorServidor((datos && datos.error) || ("Error " + r.status + " del servidor."), r.status);
      return datos;
    }
    const tarea = (id) => "/api/tareas/" + encodeURIComponent(id);
    return {
      estado: () => pedir("GET", "/api/estado"),
      elegirDxf: () => pedir("POST", "/api/dxf/elegir"),
      tarea: (id) => pedir("GET", tarea(id)),
      cancelar: (id) => pedir("POST", tarea(id) + "/cancelar"),
      reiniciar: () => pedir("POST", "/api/trabajador/reiniciar"),
      latido: () => pedir("POST", "/api/latido"),
    };
  }

  /**
   * Pregunta por la tarea cada `cadaMs` hasta que termine; `alAvance(foto)` recibe cada foto
   * (también la última). Devuelve la foto final.
   */
  async function seguirTarea(cliente, id, alAvance, cadaMs, esperar) {
    const pausa = esperar || ((ms) => new Promise((ok) => setTimeout(ok, ms)));
    for (;;) {
      const foto = await cliente.tarea(id);
      alAvance(foto);
      if (FINALES.includes(foto.estado)) return foto;
      await pausa(cadaMs === undefined ? 500 : cadaMs);
    }
  }

  return { CABECERA, FINALES, SIN_CONEXION, ErrorServidor, detectar, crearCliente, seguirTarea };
});
