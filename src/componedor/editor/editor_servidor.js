/*
 * Editor de planos — conexión con el servidor local (etapa 1 de «Cargar DXF»). Sin pantalla:
 * funciona en el navegador (window.EditorServidor) y en Node (module.exports), para probarla
 * desde pytest con un fetch falso.
 *
 * El editor abierto con doble clic (file://) no tiene servidor: `detectar` devuelve null y
 * todo sigue igual que antes. Con «Abrir editor.bat» la página llega desde 127.0.0.1 con el
 * token en la dirección (?t=…); cada pedido a la API lo manda en la cabecera
 * X-Componedor-Token. El editor nunca manda rutas de archivos: el DXF lo elige el cuadro
 * nativo que abre el servidor; para la vista previa (etapa 2) solo manda el `ref` de un bloque
 * de la carpeta ya cargada, y el PNG lo baja con el token en la cabecera (por eso no puede ir
 * en un <image href> directo: se convierte en un blob).
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
    async function pedir(metodo, ruta, cuerpo, comoBlob) {
      const opciones = { method: metodo, cache: "no-store", headers: { [CABECERA]: conexion.token } };
      if (metodo === "POST") {
        opciones.headers["Content-Type"] = "application/json";
        opciones.body = JSON.stringify(cuerpo || {});
      }
      let r;
      try {
        r = await fetchFn(ruta, opciones);
      } catch (e) {
        throw new ErrorServidor(SIN_CONEXION, 0);
      }
      if (comoBlob && r.ok) return r.blob();
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
      // estilo: el elegido en el editor ({ctb, transparencia}): el exportador 1.2 prepara la
      // vista previa del Model Space con él desde la carga. Sin él, el de componedor.json.
      elegirDxf: (estilo) => pedir("POST", "/api/dxf/elegir", estilo ? { estilo } : {}),
      recargarDxf: (estilo) => pedir("POST", "/api/dxf/recargar", estilo ? { estilo } : {}),
      // estilo: {ctb: <nombre de la lista de /api/estilos> | null, transparencia}; sin él, el
      // de componedor.json. Nunca rutas: la de la tabla la pone el servidor.
      previa: (ref, estilo) => pedir("POST", "/api/previa", estilo ? { ref, estilo } : { ref }),
      estilos: () => pedir("GET", "/api/estilos"),
      // El PNG de una vista previa terminada (url: la que dio la tarea, /api/previas/<id>).
      png: (url) => pedir("GET", url, null, true),
      // Etapa 3: un pedido «export» por bloque; «Detener a la fuerza»; lo ya exportado.
      exportar: (bloques, estilo) => pedir("POST", "/api/exportar", estilo ? { bloques, estilo } : { bloques }),
      detener: () => pedir("POST", "/api/trabajador/detener"),
      // Zonas del Model Space (Fase 10d): solo números y nombres de capa; nunca rutas.
      previaZona: (cuerpo) => pedir("POST", "/api/previa/zona", cuerpo),
      exportarZona: (cuerpo) => pedir("POST", "/api/exportar/zona", cuerpo),
      exportados: () => pedir("GET", "/api/exportados"),
      tarea: (id) => pedir("GET", tarea(id)),
      cancelar: (id) => pedir("POST", tarea(id) + "/cancelar"),
      reiniciar: () => pedir("POST", "/api/trabajador/reiniciar"),
      latido: () => pedir("POST", "/api/latido"),
      // Ortofoto: el cuadro nativo la elige; el editor manda solo números y códigos EPSG.
      ortofoto: () => pedir("GET", "/api/ortofoto"),
      // archivoPlano: la ruta que guardó el plano, solo para abrir el cuadro en su carpeta.
      elegirOrtofoto: (archivoPlano) => pedir("POST", "/api/ortofoto/elegir",
        archivoPlano ? { archivo_plano: archivoPlano } : {}),
      quitarOrtofoto: () => pedir("POST", "/api/ortofoto/quitar"),
      previaOrtofoto: (cuerpo) => pedir("POST", "/api/ortofoto/previa", cuerpo),
      // Imagen de localización (rótulo): la elige el cuadro nativo; la ruta del plano, solo
      // para abrirlo en su carpeta. La imagen se baja con el token (blob).
      localizacion: () => pedir("GET", "/api/localizacion"),
      elegirLocalizacion: (archivoPlano) => pedir("POST", "/api/localizacion/elegir",
        archivoPlano ? { archivo_plano: archivoPlano } : {}),
      quitarLocalizacion: () => pedir("POST", "/api/localizacion/quitar"),
      imagenLocalizacion: () => pedir("GET", "/api/localizacion/imagen", null, true),
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
