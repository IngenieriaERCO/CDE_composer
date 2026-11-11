/*
 * Editor de planos — diálogo «Cargar firma…» (subfase 4.3b2). Solo pantalla: el
 * procesamiento está en editor_firma.js (EditorFirma).
 *
 * 1. La persona elige un archivo de imagen o pega una con Ctrl+V.
 * 2. Recorte: arrastra un rectángulo sobre la imagen.
 * 3. Limpieza: «Compensar sombras e iluminación despareja» (activada), umbral (control
 *    deslizante de 40 a 250; el inicial y el botón «Umbral automático» = Otsu; bajar el valor =
 *    más fondo transparente), aviso si queda más del 25 % opaco, tinta en color original o en negro; vista sobre
 *    fondo cuadriculado; recorte automático al trazo con 2 px; PNG con alfa de hasta
 *    600 x 200 px y 100 KB, revisado en vivo con los textos de firmas.py.
 * 4. Guardar: en firmas/<persona>/firma.png dentro de la carpeta que elija (showDirectoryPicker,
 *    Edge y Chrome) o descargar firma.png. La fila del plano queda con {"imagen": "<persona>"}.
 *
 * PRIVACIDAD: la imagen se procesa SOLO en este navegador (sin red), nunca se escribe en el
 * editor.html ni en el plano.json, y al cerrar el diálogo se descarta (lienzos vaciados y el
 * diálogo quitado de la página).
 */
(function (raiz) {
  "use strict";

  const LADO_MAX_ORIGEN = 3000; // una foto enorme se achica al cargarla (para procesar rápido)
  const UMBRAL_INICIAL = 200;

  function nodo(nombre, atributos, texto) {
    const n = document.createElement(nombre);
    for (const [clave, v] of Object.entries(atributos || {})) {
      if (clave === "class") n.className = v;
      else n.setAttribute(clave, v);
    }
    if (texto !== undefined) n.textContent = texto;
    return n;
  }

  /** zlib (deflate) del navegador, para el PNG. */
  async function deflateNavegador(bytes) {
    const flujo = new Blob([bytes]).stream().pipeThrough(new CompressionStream("deflate"));
    return new Uint8Array(await new Response(flujo).arrayBuffer());
  }

  const kb = (n) => (n / 1024).toFixed(1).replace(".", ",") + " KB";

  /** opciones: {fila ("DIBUJÓ"), persona (nombre inicial), alUsar(persona)}. */
  function abrir(opciones) {
    const E = raiz.EditorFirma;
    let origen = null; // {ancho, alto, datos} de la imagen cargada (solo en memoria)
    let recorte = null; // {x, y, ancho, alto} en px de la imagen
    let resultado = null; // {png, ancho, alto, revision, limpia}
    let arrastre = null;
    let escala = 1; // px de pantalla por px de imagen en el lienzo de origen
    let turno = 0;

    const dialogo = nodo("dialog", { class: "dialogo-firma" });
    dialogo.appendChild(nodo("h3", {}, "Cargar firma — " + opciones.fila));
    dialogo.appendChild(nodo("p", { class: "privacidad" }, "La imagen se procesa solo en este navegador, sin " +
      "internet: no se guarda en el editor ni en el plano.json (el plano solo lleva el nombre de la persona) y se " +
      "descarta al cerrar este diálogo."));

    // 1. Imagen
    const archivo = nodo("input", { type: "file", accept: "image/*", hidden: "" });
    const elegir = nodo("button", { type: "button" }, "Elegir imagen…");
    elegir.addEventListener("click", () => archivo.click());
    archivo.addEventListener("change", () => {
      if (archivo.files[0]) cargar(archivo.files[0]);
      archivo.value = "";
    });
    const filaCarga = nodo("div", { class: "fila-carga" });
    filaCarga.append(elegir, archivo, nodo("span", { class: "medida" }, "o pegue una imagen con Ctrl+V"));
    dialogo.appendChild(nodo("div", { class: "paso" }, "1. Imagen y recorte"));
    dialogo.appendChild(filaCarga);
    const lienzoOrigen = nodo("canvas", { class: "lienzo-origen", width: "640", height: "200" });
    const quitarRecorte = nodo("button", { type: "button" }, "Quitar recorte");
    quitarRecorte.addEventListener("click", () => {
      recorte = null;
      dibujarOrigen();
      procesar();
    });
    const ayudaRecorte = nodo("div", { class: "medida" }, "Arrastre un rectángulo sobre la imagen para quedarse con la firma.");
    dialogo.append(lienzoOrigen, ayudaRecorte, quitarRecorte);

    // 2. Limpieza
    dialogo.appendChild(nodo("div", { class: "paso" }, "2. Limpieza"));
    const compensar = nodo("input", { type: "checkbox" });
    compensar.checked = true;
    compensar.addEventListener("change", () => {
      if (!origen) return;
      ponerUmbral(E.umbralAutomatico(origen, { recorte, compensar: compensar.checked }));
      procesar();
    });
    const filaCompensar = nodo("label", { class: "fila-tinta", title: "Estima el color del papel en cada zona y lo " +
      "vuelve blanco antes del umbral: sirve para fotos con sombra o con luz de un lado." });
    filaCompensar.append(compensar, " Compensar sombras e iluminación despareja");
    const umbral = nodo("input", { type: "range", min: String(E.UMBRAL_MIN), max: String(E.UMBRAL_MAX), step: "1",
      value: String(UMBRAL_INICIAL) });
    const valorUmbral = nodo("span", { class: "medida" }, String(UMBRAL_INICIAL));
    umbral.addEventListener("input", () => {
      valorUmbral.textContent = umbral.value;
      procesar();
    });
    const ayudaUmbral = "Bajar el valor = más fondo transparente; si baja demasiado, se pierde el trazo fino.";
    const filaUmbral = nodo("label", { class: "fila-umbral", title: ayudaUmbral });
    filaUmbral.append(nodo("span", {}, "Umbral del fondo"), umbral, valorUmbral);
    const automatico = nodo("button", { type: "button", title: "Calcula el umbral que mejor separa tinta y papel (método de Otsu)" },
      "Umbral automático");
    automatico.addEventListener("click", () => {
      if (!origen) return;
      ponerUmbral(E.umbralAutomatico(origen, { recorte, compensar: compensar.checked }));
      procesar();
    });
    const filaAyuda = nodo("div", { class: "fila-carga" });
    filaAyuda.append(automatico, nodo("span", { class: "medida ayuda-umbral" }, ayudaUmbral));
    const tintaOriginal = nodo("input", { type: "radio", name: "tinta", value: "original" });
    tintaOriginal.checked = true;
    const tintaNegra = nodo("input", { type: "radio", name: "tinta", value: "negro" });
    for (const r of [tintaOriginal, tintaNegra]) r.addEventListener("change", procesar);
    const filaTinta = nodo("div", { class: "fila-tinta" });
    const l1 = nodo("label");
    l1.append(tintaOriginal, " Tinta en su color");
    const l2 = nodo("label");
    l2.append(tintaNegra, " Tinta en negro");
    filaTinta.append(l1, l2);
    const cuadricula = nodo("div", { class: "cuadricula-firma" });
    const lienzoResultado = nodo("canvas", { class: "lienzo-resultado", width: "1", height: "1" });
    cuadricula.appendChild(lienzoResultado);
    const info = nodo("div", { class: "info-firma" }, "Cargue una imagen.");
    const problemas = nodo("ul", { class: "advertencias" });
    dialogo.append(filaCompensar, filaUmbral, filaAyuda, filaTinta, cuadricula, info, problemas);

    // 3. Guardar
    dialogo.appendChild(nodo("div", { class: "paso" }, "3. Guardar"));
    const persona = nodo("input", { type: "text", value: opciones.persona || "", placeholder: "Nombre de la persona" });
    const errorNombre = nodo("div", { class: "nota-detalle" });
    const donde = nodo("div", { class: "medida" });
    persona.addEventListener("input", actualizarNombre);
    const filaPersona = nodo("label", { class: "campo" });
    filaPersona.append(nodo("span", { class: "etiqueta" }, "Persona (nombre de su carpeta en firmas/)"), persona);
    dialogo.append(filaPersona, errorNombre, donde);
    const botones = nodo("div", { class: "botones" });
    const guardarCarpeta = nodo("button", { type: "button", class: "principal" }, "Guardar en la carpeta de firmas…");
    guardarCarpeta.hidden = !raiz.showDirectoryPicker;
    const descargar = nodo("button", { type: "button" }, "Descargar firma.png");
    const usar = nodo("button", { type: "button", title: "Poner esta persona en la fila sin guardar la imagen (ya tiene su firma.png)" }, "Solo usar el nombre");
    const cerrar = nodo("button", { type: "button" }, "Cerrar");
    botones.append(guardarCarpeta, descargar, usar, cerrar);
    const mensaje = nodo("div", { class: "mensaje-firma", role: "status" });
    dialogo.append(botones, mensaje);

    guardarCarpeta.addEventListener("click", guardarEnCarpeta);
    descargar.addEventListener("click", descargarPng);
    usar.addEventListener("click", () => {
      if (!nombreValido()) return;
      opciones.alUsar(persona.value);
      decir("La fila " + opciones.fila + " queda con la firma de «" + persona.value + "».", "ok");
    });
    cerrar.addEventListener("click", () => dialogo.close());
    dialogo.addEventListener("close", descartar);
    dialogo.addEventListener("paste", (ev) => {
      const item = [...(ev.clipboardData ? ev.clipboardData.items : [])].find((i) => i.type.startsWith("image/"));
      if (!item) return;
      ev.preventDefault();
      cargar(item.getAsFile());
    });

    // Recorte con el mouse.
    lienzoOrigen.addEventListener("pointerdown", (ev) => {
      if (!origen) return;
      const p = puntoImagen(ev);
      arrastre = { x: p.x, y: p.y };
      lienzoOrigen.setPointerCapture(ev.pointerId);
    });
    lienzoOrigen.addEventListener("pointermove", (ev) => {
      if (!arrastre) return;
      const p = puntoImagen(ev);
      recorte = { x: Math.min(arrastre.x, p.x), y: Math.min(arrastre.y, p.y),
        ancho: Math.abs(p.x - arrastre.x), alto: Math.abs(p.y - arrastre.y) };
      dibujarOrigen();
    });
    lienzoOrigen.addEventListener("pointerup", () => {
      if (!arrastre) return;
      arrastre = null;
      if (recorte && (recorte.ancho < 5 || recorte.alto < 5)) recorte = null;
      dibujarOrigen();
      procesar();
    });

    document.body.appendChild(dialogo);
    dialogo.showModal();
    actualizarNombre();

    // -------------------------------------------------------------------------------------

    function puntoImagen(ev) {
      const caja = lienzoOrigen.getBoundingClientRect();
      const fx = lienzoOrigen.width / caja.width;
      const x = ((ev.clientX - caja.left) * fx) / escala;
      const y = ((ev.clientY - caja.top) * fx) / escala;
      return { x: Math.max(0, Math.min(origen.ancho, x)), y: Math.max(0, Math.min(origen.alto, y)) };
    }

    async function cargar(blob) {
      try {
        const mapa = await createImageBitmap(blob);
        const f = Math.min(1, LADO_MAX_ORIGEN / Math.max(mapa.width, mapa.height));
        const ancho = Math.max(1, Math.round(mapa.width * f));
        const alto = Math.max(1, Math.round(mapa.height * f));
        const temporal = nodo("canvas", { width: String(ancho), height: String(alto) });
        const ctx = temporal.getContext("2d");
        ctx.drawImage(mapa, 0, 0, ancho, alto);
        mapa.close();
        const datos = ctx.getImageData(0, 0, ancho, alto);
        temporal.width = temporal.height = 0;
        origen = E.imagen(ancho, alto, datos.data);
        recorte = null;
        decir("", "");
        dibujarOrigen();
        ponerUmbral(E.umbralAutomatico(origen, { recorte, compensar: compensar.checked })); // umbral inicial: Otsu
        procesar();
      } catch (e) {
        decir("No se pudo leer la imagen: " + e.message, "error");
      }
    }

    function dibujarOrigen() {
      const ctx = lienzoOrigen.getContext("2d");
      if (!origen) return;
      escala = Math.min(640 / origen.ancho, 260 / origen.alto, 1);
      lienzoOrigen.width = Math.max(1, Math.round(origen.ancho * escala));
      lienzoOrigen.height = Math.max(1, Math.round(origen.alto * escala));
      const temporal = nodo("canvas", { width: String(origen.ancho), height: String(origen.alto) });
      temporal.getContext("2d").putImageData(new ImageData(origen.datos, origen.ancho, origen.alto), 0, 0);
      ctx.drawImage(temporal, 0, 0, lienzoOrigen.width, lienzoOrigen.height);
      temporal.width = temporal.height = 0;
      if (recorte) {
        const r = [recorte.x * escala, recorte.y * escala, recorte.ancho * escala, recorte.alto * escala];
        ctx.fillStyle = "rgba(17, 24, 39, 0.45)"; // lo que queda afuera, oscurecido
        ctx.fillRect(0, 0, lienzoOrigen.width, r[1]);
        ctx.fillRect(0, r[1] + r[3], lienzoOrigen.width, lienzoOrigen.height - r[1] - r[3]);
        ctx.fillRect(0, r[1], r[0], r[3]);
        ctx.fillRect(r[0] + r[2], r[1], lienzoOrigen.width - r[0] - r[2], r[3]);
        ctx.strokeStyle = "#1d4ed8";
        ctx.lineWidth = 2;
        ctx.setLineDash([6, 4]);
        ctx.strokeRect(r[0], r[1], r[2], r[3]);
      }
    }

    function ponerUmbral(valor) {
      umbral.value = String(valor);
      valorUmbral.textContent = String(valor);
    }

    function tinta() {
      return tintaNegra.checked ? "negro" : "original";
    }

    function rutaFirma() {
      return "firmas/" + (persona.value || "<persona>") + "/firma.png";
    }

    /** Vuelve a generar el PNG (el último pedido manda si hay varios en curso). */
    async function procesar() {
      if (!origen) return;
      const mio = ++turno;
      const r = await E.generar(origen, { recorte, umbral: Number(umbral.value), tinta: tinta(), compensar: compensar.checked },
        deflateNavegador, rutaFirma(), "firma");
      if (mio !== turno || !dialogo.isConnected) return;
      resultado = r.error ? null : r;
      if (r.error) {
        lienzoResultado.width = lienzoResultado.height = 1;
        info.textContent = r.error;
        problemas.replaceChildren(nodo("li", { class: "muy_fuerte" }, r.error));
        return;
      }
      lienzoResultado.width = r.ancho;
      lienzoResultado.height = r.alto;
      lienzoResultado.getContext("2d").putImageData(new ImageData(r.limpia.datos, r.ancho, r.alto), 0, 0);
      info.textContent = r.ancho + " × " + r.alto + " px · " + kb(r.png.length) + " · " +
        (r.revision.alfa ? "con transparencia (canal alfa)" : "SIN transparencia") +
        (r.reducciones ? " · se achicó " + r.reducciones + " vez/veces para no pasar de 100 KB" : "");
      const lista = r.revision.problemas.map((p) => nodo("li", { class: "muy_fuerte" }, p));
      if (r.avisoFondo) lista.push(nodo("li", { class: "fuerte aviso-fondo" }, r.avisoFondo));
      if (!r.revision.alfa) lista.push(nodo("li", { class: "fuerte" }, E.avisoSinAlfa(persona.value, "firma.png", "firmas.?.firma")));
      if (!lista.length) lista.push(nodo("li", { class: "ninguna" }, "Cumple lo que pide componer: PNG con alfa, hasta 600 × 200 px y 100 KB."));
      problemas.replaceChildren(...lista);
    }

    function actualizarNombre() {
      const problema = E.problemaNombre(persona.value);
      errorNombre.textContent = problema;
      persona.classList.toggle("invalido", !!problema && persona.value !== "");
      donde.textContent = "Se guarda como " + rutaFirma() + " (la carpeta de firmas del formato; A1 ERCO: " +
        "Componedor\\firmas\\, fuera de git).";
    }

    function nombreValido() {
      const problema = E.problemaNombre(persona.value);
      if (problema) {
        decir(problema, "error");
        persona.focus();
        return false;
      }
      return true;
    }

    function listoParaGuardar() {
      if (!nombreValido()) return false;
      if (!resultado || resultado.revision.problemas.length) {
        decir("Todavía no hay una firma válida para guardar.", "error");
        return false;
      }
      return true;
    }

    async function guardarEnCarpeta() {
      if (!listoParaGuardar()) return;
      let carpeta;
      try {
        carpeta = await raiz.showDirectoryPicker({ id: "firmas", mode: "readwrite" });
      } catch (e) {
        if (e && e.name === "AbortError") return;
        decir("El navegador no dejó elegir la carpeta (" + e.message + "): use «Descargar firma.png».", "error");
        return;
      }
      try {
        const sub = await carpeta.getDirectoryHandle(persona.value, { create: true });
        let existe = true;
        try {
          await sub.getFileHandle("firma.png");
        } catch (e) {
          existe = false;
        }
        if (existe && !confirm("Ya existe " + carpeta.name + "/" + persona.value + "/firma.png. ¿Reemplazarla?")) return;
        const archivoFirma = await sub.getFileHandle("firma.png", { create: true });
        const escritor = await archivoFirma.createWritable();
        await escritor.write(new Blob([resultado.png], { type: "image/png" }));
        await escritor.close();
        opciones.alUsar(persona.value);
        const nota = carpeta.name.toLowerCase() === "firmas" ? "" : " Ojo: la carpeta elegida se llama «" + carpeta.name +
          "»; componer busca en la carpeta de firmas del formato (Componedor\\firmas\\).";
        decir("Guardada en " + carpeta.name + "/" + persona.value + "/firma.png y puesta en la fila " + opciones.fila + "." + nota, "ok");
      } catch (e) {
        decir("No se pudo guardar: " + e.message + ". Use «Descargar firma.png».", "error");
      }
    }

    function descargarPng() {
      if (!listoParaGuardar()) return;
      const url = URL.createObjectURL(new Blob([resultado.png], { type: "image/png" }));
      const enlace = nodo("a", { download: "firma.png" });
      enlace.href = url;
      document.body.appendChild(enlace);
      enlace.click();
      enlace.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      opciones.alUsar(persona.value);
      decir("Se descargó firma.png en la carpeta de descargas. Muévala a firmas/" + persona.value + "/firma.png (la " +
        "carpeta de firmas del formato) antes de componer. La fila " + opciones.fila + " ya quedó con «" + persona.value + "».", "ok");
    }

    function decir(texto, tipo) {
      mensaje.textContent = texto;
      mensaje.className = "mensaje-firma " + (tipo || "");
    }

    /** Al cerrar: nada de la imagen queda en la página. */
    function descartar() {
      turno++;
      origen = null;
      resultado = null;
      recorte = null;
      for (const lienzo of [lienzoOrigen, lienzoResultado]) lienzo.width = lienzo.height = 0;
      dialogo.remove();
    }
  }

  raiz.EditorDialogoFirma = { abrir };
})(typeof self !== "undefined" ? self : this);
