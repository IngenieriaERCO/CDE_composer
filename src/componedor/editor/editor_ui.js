/*
 * Editor de planos — interfaz (SVG + DOM). Toda la geometría y las reglas están en
 * editor_logica.js (EditorLogica); aquí solo se dibuja y se responde al usuario.
 *
 * El lienzo SVG usa como unidades los píxeles de plantilla.png (Y hacia abajo); los mm de
 * papel (Y hacia arriba) se convierten SOLO con EditorLogica.papelAPantalla/pantallaAPapel.
 *
 * Etapa 2: además de los detalles exportados (c.detalle, c.pos = esquina inferior izquierda),
 * el plano puede tener BLOQUES de un DXF sin exportar (c.bloque, c.escala, c.centro): una caja
 * exacta con centro fijo y la vista previa PNG del trabajador (editor_bloques.js; el PNG lo
 * pide editor_panel_dxf.js). paginaDe/dibujoDe/escalaDe tratan los dos igual.
 */
(function () {
  "use strict";

  const L = window.EditorLogica;
  const B = window.EditorBloques;
  const DATOS = JSON.parse(document.getElementById("datos-editor").textContent);
  const svg = document.getElementById("hoja");
  const NS = svg.namespaceURI; // namespace del SVG en línea (sin escribir ninguna URL)
  const ESCALA = L.escalaDeImagen(DATOS.hoja, DATOS.imagen_plantilla);
  const ZONA = L.zonaEditable(DATOS);
  const ANCHO_PX = DATOS.imagen_plantilla.ancho_px;
  const ALTO_PX = DATOS.imagen_plantilla.alto_px;
  const CATALOGO = DATOS.detalles;
  // Rosa de los vientos (subfase 4.1): null si el formato no la declara (datos anteriores).
  const ROSA = DATOS.rosa_vientos || null;
  const ROSA_ORIGEN = ROSA ? [ROSA.rect_mm[0], ROSA.rect_mm[1]] : null;
  // Rótulo (subfase 4.3a): definición, catálogo de notas, símbolos y anchos de la fuente.
  // null con datos anteriores o con un formato sin sección "rotulo".
  const R = window.EditorRotulo;
  const F = window.EditorFormularios; // formularios del rótulo (4.3b)
  const V = window.EditorVistaPrevia; // vista previa del rótulo (4.3f): qué y dónde
  const LR = window.EditorLienzoRotulo; // y su dibujo en el lienzo
  const DATOS_ROTULO = DATOS.rotulo || null;
  const DEFINICION_ROTULO = DATOS_ROTULO ? DATOS_ROTULO.definicion : null;
  // proyecto.json (editor --proyecto): valores que prellenan un plano NUEVO.
  const PRELLENADO = DATOS_ROTULO ? F.valoresProyecto(DATOS_ROTULO.proyecto, DEFINICION_ROTULO) : {};

  const estado = {
    colocaciones: [], // [{id, detalle, pos: [x, y]}], en orden de apilado
    seleccion: null, // id
    rosa: ROSA ? { visible: true, pos: ROSA_ORIGEN.slice() } : null,
    rosaSeleccionada: false,
    // Rótulo (4.3a): modelo que conserva intacto lo que no se toca; plano abierto, para
    // guardarlo idéntico si no se cambia nada.
    rotulo: R.crearModelo(null, DEFINICION_ROTULO),
    original: null,
    // Ortofoto del plano (versión 4): {archivo, bytes, crs, crs_dibujo, opacidad} o null. Se
    // conserva aunque el editor esté sin servidor (se guarda igual).
    ortofoto: null,
    // Varias hojas (versión 7): el nombre del plano.json abierto o guardado (en la carpeta del
    // editor), los campos copiados de otra hoja que faltan revisar ({hoja, revisar, valores al
    // abrir}) y los valores automáticos del rótulo (hoja, de, número de plano) del índice.
    archivo: null,
    copiado: null,
    automaticos: {},
    paso: 1,
    cambios: false,
    vista: { x: 0, y: 0, ancho: ANCHO_PX, alto: ALTO_PX },
  };
  R.prellenar(estado.rotulo, PRELLENADO); // plano nuevo: los datos del proyecto quedan copiados
  let arrastre = null; // {c, dx, dy} en mm (c: detalle o bloque), {rosa: true, dx, dy} o {c, tirador: true}
  let paneo = null; // {x, y, vista} en px de pantalla
  let ultimasAdvertencias = [];

  // ---------------------------------------------------------------------------------------
  // Utilidades
  // ---------------------------------------------------------------------------------------

  function nodoSvg(nombre, atributos, padre) {
    const nodo = document.createElementNS(NS, nombre);
    for (const [clave, valor] of Object.entries(atributos || {})) nodo.setAttribute(clave, valor);
    if (padre) padre.appendChild(nodo);
    return nodo;
  }

  function nodo(nombre, atributos, texto) {
    const n = document.createElement(nombre);
    for (const [clave, valor] of Object.entries(atributos || {})) {
      if (clave === "class") n.className = valor;
      else n.setAttribute(clave, valor);
    }
    if (texto !== undefined) n.textContent = texto;
    return n;
  }

  const mm = (v) => v.toFixed(2).replace(".", ",");
  const mm1 = (v) => v.toFixed(1).replace(".", ",");

  function rectSvg(nodoRect, rectPapel) {
    const r = L.rectPapelAPantalla(rectPapel, ESCALA);
    nodoRect.setAttribute("x", r.x);
    nodoRect.setAttribute("y", r.y);
    nodoRect.setAttribute("width", r.ancho);
    nodoRect.setAttribute("height", r.alto);
    return r;
  }

  // ---------------------------------------------------------------------------------------
  // Detalles exportados y bloques sin exportar: la misma forma para todo lo demás.
  // ---------------------------------------------------------------------------------------

  const esBloque = (c) => !!c.bloque;
  // Zona borrador (Fase 10e): un «bloque» sin exportar cuyo origen es un rectángulo del Model
  // Space (c.bloque.zona = {rect, capas, excluir, modo, desmarcadas}); su nombre es c.bloque.nombre.
  const esZona = (c) => !!(c.bloque && c.bloque.zona);
  // Lo que se ve en la hoja (Fase 11): el dibujo y el margen de la hoja (el del detalle o el de
  // componedor.json), no la página del paquete con el margen de la exportación. c.pos sigue
  // siendo la esquina de la PÁGINA del paquete (posicion_mm): el dibujo no se mueve.
  B.fijarMargenHoja(L.margenDe(null, DATOS));
  const margenDe = (c) => L.margenDe(c, DATOS);
  const paginaBloque = (c) => B.paginaMm(c.bloque.tamano_m, c.escala, B.margenHoja());
  const paginaDe = (c) => esBloque(c) ? B.rectCentrado(c.centro, paginaBloque(c))
    : L.visibleEnPapel(c.detalle, c.pos, margenDe(c));
  const dibujoDe = (c) => esBloque(c) ? B.rectDibujo(c.centro, paginaBloque(c), B.margenHoja())
    : L.dibujoEnPapel(c.detalle, c.pos);
  const escalaDe = (c) => esBloque(c) ? c.escala : c.detalle.escala;
  const estadoBloque = (c) => B.estadoCaja(c.centro, paginaBloque(c), ZONA);
  const sugeridaDe = (c) => c.bloque.sugerida !== undefined && c.bloque.sugerida !== null ? c.bloque.sugerida
    : B.escalaSugerida(c.bloque.tamano_m, B.margenHoja(), ZONA, escalasDe(c));
  const escalasDe = (c) => c.bloque.escalas || B.ESCALAS;
  const P = () => window.EditorPanelDxf || null; // el panel del DXF (vista previa); null sin él
  const PO = () => window.EditorPanelOrtofoto || null; // el panel de la ortofoto; null sin él
  const O = window.EditorOrtofoto;

  /** Estado de la vista previa de un bloque: {estado, url, datos, caja_cad, mm_por_unidad, mensaje}. */
  function previaDe(c) {
    const panel = P();
    return panel ? panel.previa(c.bloque) : { estado: "sin_servidor",
      mensaje: "Vista previa: abra el editor con «Abrir editor.bat»." };
  }

  let temporizadorMensaje = null;
  function mensaje(texto, tipo) {
    const caja = document.getElementById("mensaje");
    caja.textContent = texto;
    caja.className = "mensaje " + (tipo || "");
    caja.hidden = false;
    clearTimeout(temporizadorMensaje);
    if (tipo !== "error") temporizadorMensaje = setTimeout(() => (caja.hidden = true), 6000);
  }
  document.getElementById("mensaje").addEventListener("click", (e) => (e.currentTarget.hidden = true));

  function marcarCambios() {
    estado.cambios = true;
    if (estado.copiado) { // un campo copiado de otra hoja que se cambió ya está revisado
      estado.copiado.revisar = window.EditorHojas.porRevisar(estado.copiado.revisar, estado.copiado.valores,
        (campo) => R.valor(estado.rotulo, campo));
    }
    programarVistaPrevia(); // el rótulo pudo cambiar (los paneles llaman aquí)
    // El aviso de «ESC: DEFINIR» de la imagen de localización depende de la escala escrita.
    const pl = window.EditorPanelLocalizacion;
    if (pl && pl.alCambiarRotulo) pl.alCambiarRotulo();
  }

  // ---------------------------------------------------------------------------------------
  // Capas fijas del lienzo: plantilla, zonas bloqueadas, área de dibujo, elementos fijos.
  // ---------------------------------------------------------------------------------------

  const defs = nodoSvg("defs", {}, svg);
  const rayado = nodoSvg("pattern", { id: "rayado", width: 8, height: 8, patternUnits: "userSpaceOnUse",
    patternTransform: "rotate(45)" }, defs);
  nodoSvg("rect", { width: 8, height: 8, fill: "rgba(107,114,128,0.18)" }, rayado);
  nodoSvg("line", { x1: 0, y1: 0, x2: 0, y2: 8, stroke: "rgba(75,85,99,0.35)", "stroke-width": 3 }, rayado);

  nodoSvg("rect", { x: 0, y: 0, width: ANCHO_PX, height: ALTO_PX, fill: "#fff" }, svg);
  const fondo = nodoSvg("image", { x: 0, y: 0, width: ANCHO_PX, height: ALTO_PX,
    preserveAspectRatio: "none" }, svg);
  fondo.setAttribute("href", DATOS.imagen_plantilla.data_url);

  const capaBloqueos = nodoSvg("g", {}, svg);
  // Solo los datos `zonas` deciden qué está bloqueado: el editor no deduce nada del dibujo.
  for (const zona of DATOS.zonas) {
    if (zona.editable) continue;
    const bloqueo = nodoSvg("rect", { class: "zona-bloqueada" }, capaBloqueos);
    rectSvg(bloqueo, zona.rect_mm);
    nodoSvg("title", {}, bloqueo).textContent = zona.nombre + " (bloqueada)";
  }
  if (ZONA) rectSvg(nodoSvg("rect", { class: "zona-activa" }, svg), ZONA);

  // La rosa va debajo de los detalles, como en el PDF (es parte de la hoja base). plantilla.png
  // ya viene SIN la rosa: se dibuja solo aquí, en su posición actual.
  // La ortofoto (detrás de los detalles marcados, o extendida a toda el área) y la cuadrícula
  // de coordenadas, debajo de la rosa: la rosa nunca queda tapada por la foto (como en el PDF).
  const capaOrtofoto = nodoSvg("g", { class: "capa-ortofoto" }, svg);
  const capaCuadricula = nodoSvg("g", { class: "capa-cuadricula" }, svg);
  const capaRosa = nodoSvg("g", {}, svg);

  const capaElementos = nodoSvg("g", {}, svg);
  const nodosElementos = new Map();
  for (const el of DATOS.elementos_plantilla) {
    if (ROSA && el.nombre === L.ROSA) continue; // la rosa se dibuja en capaRosa
    const marco = nodoSvg("rect", { class: "elemento-fijo" }, capaElementos);
    const rect = rectSvg(marco, el.rect_mm);
    const etiqueta = nodoSvg("text", { class: "etiqueta-fijo", x: rect.x, y: rect.y - 3 }, capaElementos);
    etiqueta.textContent = el.nombre + " (fijo)";
    nodosElementos.set(el.nombre, marco);
  }

  // Vista previa (4.3f), en el orden de componer: los símbolos de convenciones son parte de la
  // hoja base (debajo de los detalles); textos, etiquetas «ESC» y firmas van encima.
  // La imagen de localización del rótulo (en su recuadro), debajo de los textos del rótulo.
  const capaLocalizacion = nodoSvg("g", { class: "capa-localizacion" }, svg);
  const capasVistaPrevia = { simbolos: nodoSvg("g", { class: "vp-capa" }, svg) };
  const capaDetalles = nodoSvg("g", {}, svg);
  capasVistaPrevia.textos = nodoSvg("g", { class: "vp-capa" }, svg);
  capasVistaPrevia.etiquetas = nodoSvg("g", { class: "vp-capa" }, svg);
  capasVistaPrevia.firmas = nodoSvg("g", { class: "vp-capa" }, svg);
  capasVistaPrevia.problemas = nodoSvg("g", { class: "vp-capa vp-ayuda" }, svg);

  // ---------------------------------------------------------------------------------------
  // Vista: zoom y desplazamiento (viewBox en píxeles de la plantilla).
  // ---------------------------------------------------------------------------------------

  function aplicarVista() {
    const v = estado.vista;
    svg.setAttribute("viewBox", [v.x, v.y, v.ancho, v.alto].join(" "));
  }

  function ajustarVista() {
    const margen = 0.03;
    const caja = svg.getBoundingClientRect();
    const proporcion = caja.width && caja.height ? caja.width / caja.height : ANCHO_PX / ALTO_PX;
    let ancho = ANCHO_PX * (1 + 2 * margen);
    let alto = ALTO_PX * (1 + 2 * margen);
    if (ancho / alto > proporcion) alto = ancho / proporcion;
    else ancho = alto * proporcion;
    estado.vista = { x: (ANCHO_PX - ancho) / 2, y: (ALTO_PX - alto) / 2, ancho, alto };
    aplicarVista();
  }

  function zoom(factor, centro) {
    const v = estado.vista;
    const c = centro || { x: v.x + v.ancho / 2, y: v.y + v.alto / 2 };
    const ancho = Math.min(Math.max(v.ancho / factor, ANCHO_PX * 0.02), ANCHO_PX * 4);
    const real = v.ancho / ancho;
    estado.vista = {
      x: c.x - (c.x - v.x) / real,
      y: c.y - (c.y - v.y) / real,
      ancho: ancho,
      alto: v.alto / real,
    };
    aplicarVista();
  }

  /** Punto del evento en píxeles de la plantilla (unidades del SVG). */
  function puntoSvg(ev) {
    const p = svg.createSVGPoint();
    p.x = ev.clientX;
    p.y = ev.clientY;
    return p.matrixTransform(svg.getScreenCTM().inverse());
  }

  function puntoPapel(ev) {
    const p = puntoSvg(ev);
    return L.pantallaAPapel(p.x, p.y, ESCALA);
  }

  // ---------------------------------------------------------------------------------------
  // Detalles en el lienzo.
  // ---------------------------------------------------------------------------------------

  function colocadosParaAdvertencias() {
    return estado.colocaciones.map((c) => ({
      id: c.id,
      pagina: paginaDe(c),
      dibujo: dibujoDe(c),
      tiene_fondo: esBloque(c) ? false : c.detalle.tiene_fondo, // el exportador nuevo no pone fondo
    }));
  }

  /** Avisos de los bloques sin exportar (no caben, se salen, cuántos faltan por exportar). */
  function advertenciasBloques() {
    const lista = [];
    const bloques = estado.colocaciones.filter(esBloque);
    for (const c of bloques) {
      const e = estadoBloque(c);
      if (!e.cabe) {
        const sugerida = sugeridaDe(c);
        lista.push({ nivel: "muy_fuerte", ids: [c.id], texto: "'" + c.id + "' no cabe en el área de dibujo a " +
          B.textoEscala(c.escala) + ": sobran " + mm1(e.exceso[0]) + " × " + mm1(e.exceso[1]) + " mm" +
          (sugerida ? "; sugerida " + B.textoEscala(sugerida) : "") + "." });
      } else if (!e.dentro) {
        lista.push({ nivel: "muy_fuerte", ids: [c.id], texto: "'" + c.id +
          "' se sale del área de dibujo: muévalo (cabe a " + B.textoEscala(c.escala) + ")." });
      }
    }
    for (const c of bloques) {
      if (!B.esNormalizada(c.escala, escalasDe(c))) {
        lista.push({ nivel: "aviso", ids: [c.id], texto: "'" + c.id + "': escala no normalizada (" +
          B.textoEscala(c.escala) + ")." });
      }
    }
    const zonas = bloques.filter(esZona);
    const soloBloques = bloques.length - zonas.length;
    if (soloBloques) {
      lista.push({ nivel: "aviso", ids: [], texto: soloBloques + " bloque(s) del DXF sin exportar: el plano " +
        "se guarda como versión 3 y componer pedirá exportarlos primero." });
    }
    if (zonas.length) {
      lista.push({ nivel: "aviso", ids: [], texto: zonas.length + " zona(s) borrador sin exportar: el plano " +
        "se guarda como versión 6 y componer pedirá exportarlas primero («Exportar bloques y zonas»)." });
    }
    const ZE = window.EditorZonas;
    // Una zona (borrador o exportada) a otra escala que la de su dibujo: los textos cambian de tamaño.
    for (const c of estado.colocaciones) {
      const dibujo = esZona(c) ? c.bloque.zona.escala_dibujo : c.zona ? c.zona.escala_dibujo : null;
      const aviso = dibujo && ZE ? ZE.avisoEscala(esZona(c) ? c.escala : c.detalle.escala, dibujo) : null;
      if (aviso) lista.push({ nivel: "aviso", ids: [c.id], texto: "'" + c.id + "': " + aviso });
    }
    for (const [a, b] of (ZE ? ZE.zonasRepetidas(estado.colocaciones) : [])) {
      lista.push({ nivel: "muy_fuerte", ids: [a, b], texto: "'" + a + "' y '" + b + "' tienen el mismo nombre y la " +
        "misma escala: serían el MISMO paquete. Cambie el nombre de una." });
    }
    return lista;
  }

  /** Estado de la rosa para la lógica: {visible, rect} o null (el formato no tiene rosa). */
  function rosaParaLogica() {
    if (!estado.rosa) return null;
    return { visible: estado.rosa.visible, rect: L.rectRosa(ROSA.rect_mm, estado.rosa.pos) };
  }

  function dibujarRosa(tapada) {
    capaRosa.replaceChildren();
    if (!estado.rosa || !estado.rosa.visible) return; // oculta: desaparece y la zona queda libre
    const rect = L.rectRosa(ROSA.rect_mm, estado.rosa.pos);
    const clases = ["rosa"];
    if (estado.rosaSeleccionada) clases.push("sel");
    const g = nodoSvg("g", { class: clases.join(" ") }, capaRosa);
    const r = L.rectPapelAPantalla(rect, ESCALA);
    if (ROSA.imagen && ROSA.imagen.data_url) {
      const imagen = nodoSvg("image", { x: r.x, y: r.y, width: r.ancho, height: r.alto,
        preserveAspectRatio: "none" }, g);
      imagen.setAttribute("href", ROSA.imagen.data_url);
    }
    const marco = nodoSvg("rect", { class: "elemento-fijo rosa-marco" + (tapada ? " tapado" : "") }, g);
    rectSvg(marco, rect);
    const etiqueta = nodoSvg("text", { class: "etiqueta-fijo", x: r.x, y: r.y - 3 }, g);
    etiqueta.textContent = L.ROSA + " (movible)";
    g.addEventListener("pointerdown", empezarArrastreRosa);
  }

  const ORDEN_NIVEL = { aviso: 1, fuerte: 2, muy_fuerte: 3 };

  /**
   * Para la ortofoto: por cada colocación con «Usar ortofoto», la página en la hoja y la caja CAD que la cubre
   * {id, pagina, caja, mm_por_unidad, motivo} (motivo: por qué no hay caja, o null).
   */
  const marcados = () => estado.colocaciones.filter((c) => c.ortofoto === true);
  /** «Extender a todo el layout»: vale solo con UN detalle con ortofoto (si no, recortadas). */
  const extendida = () => !!(estado.ortofoto && estado.ortofoto.extender && marcados().length === 1);

  function cajasOrtofoto() {
    const extender = extendida();
    return marcados().map((c) => {
      // El mapeo CAD → papel es el de la página ENTERA del paquete; la foto va detrás de lo
      // que se ve (el mismo recorte que el dibujo) o, extendida, de toda el área de dibujo.
      const paginaDetalle = esBloque(c) ? paginaDe(c) : L.paginaEnPapel(c.detalle, c.pos);
      const pagina = extender ? ZONA.slice() : paginaDe(c);
      const r = { id: c.id, pagina, paginaDetalle, caja: null, mm_por_unidad: null, motivo: null };
      if (esBloque(c)) {
        const p = previaDe(c);
        if (!p.caja_cad || !p.mm_por_unidad) {
          r.motivo = "sin la caja CAD del bloque: cargue su DXF";
          return r;
        }
        r.caja = O.cajaCadBloque(pagina, c.centro, B.centroCaja(p.caja_cad), B.mmPorUnidadCad(p.mm_por_unidad, c.escala));
        r.mm_por_unidad = p.mm_por_unidad;
        return r;
      }
      const d = c.detalle;
      if (!d.cad_a_pagina || !d.mm_por_unidad) {
        r.motivo = "el catálogo no trae su matriz CAD (vuelva a generar el editor)";
        return r;
      }
      r.caja = O.cajaCadDetalle(paginaDetalle, d.cad_a_pagina, pagina);
      r.mm_por_unidad = d.mm_por_unidad;
      if (!r.caja) r.motivo = "su dibujo está girado en la página: sin ortofoto en el editor";
      return r;
    });
  }

  const LO = window.EditorLocalizacion;
  const CAMPO_LOCALIZACION = LO ? LO.campoImagen(DEFINICION_ROTULO) : null;

  /** La imagen de localización en su recuadro (entera, centrada, sin deformar), como componer.
   *  Si el plano la tiene pero no está cargada, un recuadro punteado con su nombre. */
  function dibujarLocalizacion() {
    capaLocalizacion.replaceChildren();
    if (!CAMPO_LOCALIZACION) return;
    const valor = R.valor(estado.rotulo, CAMPO_LOCALIZACION.nombre);
    if (!valor) return;
    const panel = window.EditorPanelLocalizacion;
    const img = panel ? panel.imagen() : null;
    if (img) {
      const r = L.rectPapelAPantalla(LO.contener(CAMPO_LOCALIZACION.rect_mm, img.px[0], img.px[1]), ESCALA);
      const n = nodoSvg("image", { x: r.x, y: r.y, width: r.ancho, height: r.alto, preserveAspectRatio: "none",
        class: "imagen-localizacion" }, capaLocalizacion);
      n.setAttribute("href", img.url);
      return;
    }
    const r = L.rectPapelAPantalla(CAMPO_LOCALIZACION.rect_mm, ESCALA);
    nodoSvg("rect", { x: r.x, y: r.y, width: r.ancho, height: r.alto, class: "localizacion-pendiente" }, capaLocalizacion);
    nodoSvg("text", { x: r.x + 4, y: r.y + 14, class: "etiqueta-fijo" }, capaLocalizacion).textContent =
      "Imagen de localización: " + String(valor.archivo).split(/[\\/]/).pop();
  }

  let ultimasCuadriculas = [];

  /** La cuadrícula de coordenadas (cuadricula.py en el PDF): líneas sobre la foto y etiquetas en
   *  la franja de afuera. También donde la foto no cubre. */
  function dibujarCuadricula() {
    capaCuadricula.replaceChildren();
    ultimasCuadriculas = [];
    const o = estado.ortofoto;
    if (!o || !o.cuadricula) return;
    const panel = PO();
    const intervalo = o.intervalo_m || (panel && panel.intervalo ? panel.intervalo() : null) || 50;
    const medir = O.medidorCuadricula(FUENTE_ROTULO);
    const altura = O.alturaCuadricula(FUENTE_ROTULO);
    const rosa = rosaParaLogica();
    const fijos = DATOS.zonas.filter((z) => !z.editable).map((z) => z.rect_mm)
      .concat(rosa && rosa.visible ? [rosa.rect] : [])
      .concat((etiquetasActuales.textos || []).map((x) => x.celda_mm).filter(Boolean));
    const C = O.CUADRICULA;
    for (const r of cajasOrtofoto()) {
      if (!r.caja) continue;
      const otras = estado.colocaciones.filter((c) => c.id !== r.id).map(paginaDe);
      const k = r.mm_por_unidad / 1000;
      const g = O.cuadricula(r.pagina, r.caja.map((v) => v * k), intervalo, fijos.concat(otras),
        DATOS.marco_mm || null, medir, altura);
      g.id = r.id;
      g.intervalo_m = intervalo;
      ultimasCuadriculas.push(g);
      for (const [x0, y0, x1, y1] of g.lineas) {
        const a = L.papelAPantalla(x0, y0, ESCALA);
        const b = L.papelAPantalla(x1, y1, ESCALA);
        nodoSvg("line", { x1: a.x, y1: a.y, x2: b.x, y2: b.y, stroke: C.color,
          "stroke-width": C.grosor_mm * ESCALA.pxPorMmX, class: "linea-cuadricula" }, capaCuadricula);
      }
      for (const et of g.etiquetas) {
        const p = L.papelAPantalla(et.base[0], et.base[1], ESCALA);
        const n = nodoSvg("text", { x: p.x, y: p.y, class: "etiqueta-cuadricula", "data-eje": et.eje,
          "font-size": C.em_mm * ESCALA.pxPorMmY,
          transform: et.giro ? "rotate(-90 " + p.x + " " + p.y + ")" : "" }, capaCuadricula);
        n.textContent = et.texto;
      }
    }
  }

  /**
   * El aviso de cobertura de la ortofoto de un detalle con «Usar ortofoto» (null si la foto lo
   * cubre entero, si no la usa o si su vista previa no llegó todavía).
   */
  function avisoOrtofoto(c) {
    const panel = PO();
    if (!estado.ortofoto || !panel || c.ortofoto !== true) return null;
    const r = cajasOrtofoto().find((x) => x.id === c.id);
    if (!r || !r.caja) return null;
    const p = panel.previa(r.caja, r.mm_por_unidad, r.id);
    if (p.estado !== "lista") return null;
    return O.avisoCobertura(p.cobertura, r.caja, p.foto || null, r.mm_por_unidad);
  }

  /** Sobre la página del detalle, en el centro: el aviso corto, en ámbar (visible aunque no haya foto). */
  function pintarAvisoOrtofoto(g, c, pagina) {
    const a = avisoOrtofoto(c);
    if (!a) return;
    const r = L.rectPapelAPantalla(pagina, ESCALA);
    const marco = nodoSvg("rect", { class: "aviso-ortofoto-marco " + a.nivel, x: r.x, y: r.y, width: r.ancho,
      height: r.alto }, g);
    nodoSvg("title", {}, marco).textContent = a.largo;
    // Grande y en el centro de la página (proporcional al detalle): que se lea sin acercarse.
    const letra = Math.max(9, Math.min(r.ancho / 20, r.alto / 6, 32));
    const t = nodoSvg("text", { class: "aviso-ortofoto-hoja " + a.nivel, x: r.x + r.ancho / 2,
      y: r.y + r.alto / 2, "text-anchor": "middle", "dominant-baseline": "middle", "font-size": letra }, g);
    t.textContent = a.corto;
    nodoSvg("title", {}, t).textContent = a.largo;
  }

  /** Advertencias: un detalle con «Usar ortofoto» que la foto no cubre (o cubre en parte). */
  function advertenciasOrtofoto() {
    const lista = [];
    for (const c of estado.colocaciones) {
      const a = avisoOrtofoto(c);
      if (a) lista.push({ nivel: a.nivel, ids: [c.id], texto: "'" + c.id + "': " + a.largo });
    }
    return lista;
  }

  function dibujarOrtofoto() {
    capaOrtofoto.replaceChildren();
    const panel = PO();
    if (!estado.ortofoto || !panel) return;
    capaOrtofoto.setAttribute("opacity", String(estado.ortofoto.opacidad));
    for (const r of cajasOrtofoto()) {
      if (!r.caja) continue;
      const p = panel.previa(r.caja, r.mm_por_unidad, r.id);
      if (p.estado !== "lista" || !p.url || !(p.cobertura > 0)) continue; // sin foto: nada
      const pantalla = L.rectPapelAPantalla(r.pagina, ESCALA);
      const imagen = nodoSvg("image", { x: pantalla.x, y: pantalla.y, width: pantalla.ancho, height: pantalla.alto,
        preserveAspectRatio: "none", class: "ortofoto", "data-id": r.id }, capaOrtofoto);
      imagen.setAttribute("href", p.url);
    }
  }

  function dibujarDetalles(niveles) {
    capaDetalles.replaceChildren();
    for (const c of estado.colocaciones) {
      const clases = ["detalle"];
      if (niveles.has(c.id)) clases.push(niveles.get(c.id));
      if (c.id === estado.seleccion) clases.push("sel");
      if (esBloque(c)) {
        dibujarBloque(c, clases);
        continue;
      }
      const g = nodoSvg("g", { class: clases.join(" "), "data-id": c.id }, capaDetalles);
      const pagina = paginaDe(c); // lo que se ve: el dibujo y el margen
      const r = L.rectPapelAPantalla(pagina, ESCALA);
      if (extendida() && c.ortofoto !== true) rectSvg(nodoSvg("rect", { class: "fondo-blanco" }, g), pagina);
      // La miniatura es de la página entera: se pone en su sitio y se recorta a lo que se ve
      // (un <svg> anidado corta lo que sale de su caja), como el clip de componer.
      const entera = L.rectPapelAPantalla(L.paginaEnPapel(c.detalle, c.pos), ESCALA);
      const ventana = nodoSvg("svg", { x: r.x, y: r.y, width: r.ancho, height: r.alto, class: "recorte-detalle" }, g);
      const imagen = nodoSvg("image", { x: entera.x - r.x, y: entera.y - r.y, width: entera.ancho, height: entera.alto,
        preserveAspectRatio: "none" }, ventana);
      imagen.setAttribute("href", c.detalle.miniatura.data_url);
      rectSvg(nodoSvg("rect", { class: "pagina" }, g), pagina);
      rectSvg(nodoSvg("rect", { class: "dibujo" }, g), L.dibujoEnPapel(c.detalle, c.pos));
      const etiqueta = nodoSvg("text", { class: "etiqueta", x: r.x + 3, y: r.y + 11 }, g);
      etiqueta.textContent = c.id;
      pintarAvisoOrtofoto(g, c, pagina);
      g.addEventListener("pointerdown", (ev) => empezarArrastre(ev, c));
    }
  }

  const TIRADOR_PX = 12;

  /** Un bloque sin exportar: su caja exacta, la vista previa encima y, si está seleccionado,
   *  el tirador de la esquina superior derecha para cambiar la escala. */
  function dibujarBloque(c, clases) {
    const e = estadoBloque(c);
    clases.push("bloque");
    if (!e.cabe || !e.dentro) clases.push("no-cabe");
    const g = nodoSvg("g", { class: clases.join(" "), "data-id": c.id }, capaDetalles);
    const pagina = paginaDe(c);
    const r = L.rectPapelAPantalla(pagina, ESCALA);
    if (extendida() && c.ortofoto !== true) rectSvg(nodoSvg("rect", { class: "fondo-blanco" }, g), pagina);
    const previa = previaDe(c);
    if (previa.estado === "lista" && previa.caja_cad && previa.mm_por_unidad) {
      const k = B.mmPorUnidadCad(previa.mm_por_unidad, c.escala);
      const rect = L.rectPapelAPantalla(B.imagenEnPapel(previa.datos, B.centroCaja(previa.caja_cad), c.centro, k), ESCALA);
      const imagen = nodoSvg("image", { x: rect.x, y: rect.y, width: rect.ancho, height: rect.alto,
        preserveAspectRatio: "none", class: "previa-bloque" }, g);
      imagen.setAttribute("href", previa.url);
    }
    rectSvg(nodoSvg("rect", { class: "pagina" }, g), pagina);
    rectSvg(nodoSvg("rect", { class: "dibujo" }, g), dibujoDe(c));
    nodoSvg("text", { class: "etiqueta", x: r.x + 3, y: r.y + 11 }, g).textContent =
      c.id + " · " + B.textoEscala(c.escala) + (esZona(c) ? " · zona borrador (sin exportar)" : " · vista previa (sin exportar)");
    if (esZona(c)) g.classList.add("zona-borrador");
    const estadoTexto = !e.cabe ? "no cabe: sobran " + mm1(e.exceso[0]) + " × " + mm1(e.exceso[1]) + " mm" +
      (sugeridaDe(c) ? "; sugerida " + B.textoEscala(sugeridaDe(c)) : "")
      : !e.dentro ? "se sale del área de dibujo"
        : previa.estado === "pidiendo" ? "Pidiendo vista previa…"
          : previa.estado === "lista" ? "" : previa.mensaje || "";
    if (estadoTexto) {
      nodoSvg("text", { class: "estado-bloque", x: r.x + 3, y: r.y + r.alto - 4 }, g).textContent = estadoTexto;
    } else {
      pintarAvisoOrtofoto(g, c, pagina);
    }
    g.addEventListener("pointerdown", (ev) => empezarArrastre(ev, c));
    if (c.id === estado.seleccion) {
      const t = nodoSvg("rect", { class: "tirador", x: r.x + r.ancho - TIRADOR_PX / 2, y: r.y - TIRADOR_PX / 2,
        width: TIRADOR_PX, height: TIRADOR_PX }, g);
      nodoSvg("title", {}, t).textContent = "Arrastre para cambiar la escala (el centro no se mueve)";
      t.addEventListener("pointerdown", (ev) => empezarTirador(ev, c));
    }
  }

  function actualizar() {
    // Mismos elementos que usa componer: la rosa en su posición actual (oculta: no cuenta).
    const elementos = L.elementosVisibles(DATOS.elementos_plantilla, rosaParaLogica());
    const lista = L.advertencias(colocadosParaAdvertencias(), elementos, DATOS.advertencias)
      .concat(advertenciasBloques(), advertenciasEstilo(), advertenciasOrtofoto(), advertenciasHoja());
    // Etiquetas «ESC: 1:N» (4.3f): las mismas que pondría componer, con sus avisos al final.
    etiquetasActuales = calcularEtiquetas(elementos);
    for (const aviso of etiquetasActuales.avisos) lista.push({ nivel: "aviso", texto: aviso, ids: [] });
    ultimasAdvertencias = lista;
    const niveles = new Map();
    const tapados = new Set();
    for (const a of lista) {
      for (const id of a.ids) {
        const actual = niveles.get(id);
        if (!actual || ORDEN_NIVEL[a.nivel] > ORDEN_NIVEL[actual]) niveles.set(id, a.nivel);
      }
      if (a.elemento) tapados.add(a.elemento);
    }
    for (const [nombre, rect] of nodosElementos) rect.classList.toggle("tapado", tapados.has(nombre));
    dibujarRosa(tapados.has(L.ROSA));
    dibujarOrtofoto();
    dibujarCuadricula();
    dibujarLocalizacion();
    dibujarDetalles(niveles);
    pintarRosa();
    pintarPropiedades();
    pintarListaPlano();
    pintarAdvertencias(lista);
    panelRotulo.refrescar(); // ESCALA depende de los detalles colocados
    programarVistaPrevia();
    const panelDxf = P();
    if (panelDxf && panelDxf.alCambiarPlano) panelDxf.alCambiarPlano(); // «Exportar (N)»
    const panelOrtofoto = PO();
    if (panelOrtofoto && panelOrtofoto.alCambiarPlano) panelOrtofoto.alCambiarPlano();
  }

  // ---------------------------------------------------------------------------------------
  // Vista previa del rótulo (4.3f): textos, notas, convenciones, firmas y etiquetas «ESC».
  // El rótulo solo se vuelve a dibujar si cambian sus valores o las escalas; al arrastrar un
  // detalle solo cambian las etiquetas. Un dibujo por cuadro (requestAnimationFrame).
  // ---------------------------------------------------------------------------------------

  const FUENTE_ROTULO = DATOS_ROTULO ? DATOS_ROTULO.fuente : null;
  const CON_VISTA_PREVIA = !!(DATOS_ROTULO && FUENTE_ROTULO && FUENTE_ROTULO.anchos_em && V && LR);
  const CON_ETIQUETAS = CON_VISTA_PREVIA && typeof FUENTE_ROTULO.ascenso_em === "number" && !!ZONA;
  const casillaVistaPrevia = document.getElementById("vista-previa");
  const lienzoRotulo = CON_VISTA_PREVIA ? LR.crear({ svg, capas: capasVistaPrevia, escala: ESCALA,
    fuente: FUENTE_ROTULO, simbolos: DATOS_ROTULO.simbolos }) : null;
  let etiquetasActuales = { textos: [], avisos: [] };
  let claveRotulo = null;
  let cuadroPendiente = false;

  function calcularEtiquetas(elementos) {
    if (!CON_ETIQUETAS) return { textos: [], avisos: [] };
    return V.etiquetasEscala({
      detalles: estado.colocaciones.map((c) => ({ id: c.id, dibujo_mm: dibujoDe(c),
        denominador: escalaDe(c), con_etiqueta: c.etiqueta_escala !== false })),
      area_mm: ZONA, elementos: elementos.map((e) => [e.nombre, e.rect_mm]), fuente: FUENTE_ROTULO,
    });
  }

  function programarVistaPrevia() {
    if (!lienzoRotulo || cuadroPendiente) return;
    cuadroPendiente = true;
    requestAnimationFrame(dibujarVistaPrevia);
  }

  function dibujarVistaPrevia() {
    cuadroPendiente = false;
    if (!lienzoRotulo) return;
    if (!casillaVistaPrevia.checked) {
      if (claveRotulo !== null) lienzoRotulo.limpiar();
      claveRotulo = null;
      return;
    }
    const rotulo = R.serializar(estado.rotulo);
    const escalas = estado.colocaciones.map(escalaDe);
    const clave = JSON.stringify([rotulo === undefined ? null : rotulo, escalas, estado.automaticos]);
    if (clave !== claveRotulo) {
      claveRotulo = clave;
      lienzoRotulo.dibujarRotulo(V.piezasRotulo({ rotulo, definicion: DEFINICION_ROTULO, fuente: FUENTE_ROTULO,
        simbolos: DATOS_ROTULO.simbolos, catalogo: DATOS_ROTULO.notas, escalas, automaticos: estado.automaticos }));
    }
    lienzoRotulo.dibujarEtiquetas(etiquetasActuales.textos);
  }

  if (casillaVistaPrevia) {
    casillaVistaPrevia.disabled = !lienzoRotulo;
    if (!lienzoRotulo) {
      casillaVistaPrevia.checked = false;
      casillaVistaPrevia.parentElement.title = "Este editor no tiene los datos del rótulo (formato sin rótulo o datos anteriores a la 4.3f).";
    }
    casillaVistaPrevia.addEventListener("change", programarVistaPrevia);
  }

  // ---------------------------------------------------------------------------------------
  // Paneles: catálogo, propiedades, lista del plano, advertencias.
  // ---------------------------------------------------------------------------------------

  function tarjeta(detalle, habilitada) {
    const t = nodo("div", { class: "tarjeta" + (habilitada ? "" : " deshabilitada") });
    const img = nodo("img", { alt: detalle.id });
    img.src = detalle.miniatura.data_url;
    t.appendChild(img);
    const info = nodo("div");
    info.appendChild(nodo("div", { class: "nombre" }, detalle.id));
    info.appendChild(nodo("div", { class: "dato" },
      "1:" + detalle.escala + " · página " + mm(detalle.tamano_pagina_mm[0]) + " × " +
      mm(detalle.tamano_pagina_mm[1]) + " mm"));
    info.appendChild(nodo("div", { class: "dato" }, detalle.cabe ? "Cabe en el área de dibujo" : "NO cabe"));
    if (detalle.estilo && window.EditorDxf) {
      info.appendChild(nodo("div", { class: "dato estilo-detalle" }, "Estilo: " + window.EditorDxf.textoEstilo(detalle.estilo)));
    }
    const boton = nodo("button", { type: "button" }, "Agregar al plano");
    boton.disabled = !habilitada;
    boton.addEventListener("click", () => agregar(detalle));
    info.appendChild(boton);
    t.appendChild(info);
    if (!habilitada) {
      for (const nota of detalle.notas) t.appendChild(nodo("div", { class: "nota-detalle" }, nota));
    }
    return t;
  }

  function pintarCatalogo() {
    const disponibles = document.getElementById("catalogo");
    const noCaben = document.getElementById("no-caben");
    const rechazados = document.getElementById("rechazados");
    const caben = CATALOGO.filter((d) => d.cabe);
    const fuera = CATALOGO.filter((d) => !d.cabe);
    disponibles.replaceChildren(...caben.map((d) => tarjeta(d, true)));
    noCaben.replaceChildren(...fuera.map((d) => tarjeta(d, false)));
    rechazados.replaceChildren(...DATOS.rechazados.map((r) => {
      const caja = nodo("div", { class: "rechazado" });
      caja.appendChild(nodo("div", { class: "nombre" }, r.prefijo));
      const ul = nodo("ul");
      for (const m of r.motivos) ul.appendChild(nodo("li", {}, m));
      caja.appendChild(ul);
      return caja;
    }));
    if (!caben.length) disponibles.appendChild(nodo("div", { class: "vacio" }, "Ninguno."));
    if (!fuera.length) noCaben.appendChild(nodo("div", { class: "vacio" }, "Ninguno."));
    if (!DATOS.rechazados.length) rechazados.appendChild(nodo("div", { class: "vacio" }, "Ninguno."));
  }

  function seleccionada() {
    return estado.colocaciones.find((c) => c.id === estado.seleccion) || null;
  }

  function pintarPropiedades() {
    const panel = document.getElementById("propiedades");
    const c = seleccionada();
    if (!c) {
      panel.replaceChildren(nodo("div", { class: "vacio" }, estado.rosaSeleccionada
        ? "Rosa de los vientos seleccionada: arrástrela o muévala con las flechas; su posición exacta está en el panel «Rosa de los vientos»."
        : "Haga clic en un detalle del plano para moverlo o editar su posición."));
      return;
    }
    if (esBloque(c)) {
      pintarPropiedadesBloque(panel, c);
      return;
    }
    const pagina = L.paginaEnPapel(c.detalle, c.pos);
    const visible = paginaDe(c);
    const dibujo = L.dibujoEnPapel(c.detalle, c.pos);
    // Se muestra exactamente lo que se guardará (0,01 mm, redondeado hacia dentro del área).
    const guardada = L.redondearDetalle(c.pos, c.detalle, margenDe(c), ZONA);
    const filas = [
      nodo("div", { class: "fila" }, ""),
      campo("X (mm)", guardada[0], 0),
      campo("Y (mm)", guardada[1], 1),
      ...(c.zona ? [nodo("div", { class: "medida" }, "Exportado desde la zona «" + c.zona.nombre + "» del Model " +
        "Space. Si cambia el DXF: «Volver a cargar» y «Volver a exportar zonas» (queda en este mismo lugar)."),
      ...(c.zona.escala_dibujo ? lineasEscalaDibujo(c.zona.escala_dibujo, c.detalle.escala) : [])] : []),
      nodo("div", { class: "medida" }, "Esquina inferior izquierda de la PÁGINA (posicion_mm)."),
      nodo("div", { class: "medida" }, "Página: X " + mm(pagina[0]) + " a " + mm(pagina[2]) +
        ", Y " + mm(pagina[1]) + " a " + mm(pagina[3]) + " mm"),
      nodo("div", { class: "medida" }, "Dibujo: X " + mm(dibujo[0]) + " a " + mm(dibujo[2]) +
        ", Y " + mm(dibujo[1]) + " a " + mm(dibujo[3]) + " mm"),
      campoMargen(c),
      nodo("div", { class: "medida" }, "Se ve: X " + mm(visible[0]) + " a " + mm(visible[2]) +
        ", Y " + mm(visible[1]) + " a " + mm(visible[3]) + " mm (" + mm(visible[2] - visible[0]) + " × " +
        mm(visible[3] - visible[1]) + " mm: es lo que debe caber en el área de dibujo)."),
      ...filasEstilo(c),
    ];
    filas[0].appendChild(nodo("strong", {}, c.id));
    filas[0].appendChild(nodo("span", { class: "medida" }, " · " + c.detalle.id + " · 1:" + c.detalle.escala));
    const botones = nodo("div", { class: "botones" });
    const acciones = [
      ["Centrar", () => mover(c, L.centrarDetalle(c.detalle, margenDe(c), ZONA))],
      ["Traer al frente", () => reordenar(c, +Infinity)],
      ["Enviar atrás", () => reordenar(c, -Infinity)],
      ["Quitar", () => quitar(c)],
    ];
    for (const [texto, accion] of acciones) {
      const b = nodo("button", { type: "button" }, texto);
      b.addEventListener("click", accion);
      botones.appendChild(b);
    }
    panel.replaceChildren(...filas, casillaOrtofoto(c), casillaEscala(c), botones);
  }

  // Estilo de impresión con que se exportó cada detalle (de su manifiesto) frente al elegido en
  // el panel del DXF. Los que difieren se quedan como están, con aviso.
  const DX = () => window.EditorDxf || null;
  const estiloElegido = () => (P() && P().estilo ? P().estilo() : null);

  function filasEstilo(c) {
    if (!c.detalle.estilo || !DX()) return [];
    const filas = [nodo("div", { class: "medida estilo-detalle" }, "Estilo: " + DX().textoEstilo(c.detalle.estilo))];
    const elegido = estiloElegido();
    if (DX().mismoEstilo(c.detalle.estilo, elegido) === false) {
      filas.push(nodo("div", { class: "medida aviso-escala" }, "Exportado con otro estilo que el elegido para " +
        "exportar (" + DX().textoEstilo(elegido) + "): se queda así."));
    }
    return filas;
  }

  /** Versión 7: hoja vacía y campos del rótulo copiados de otra hoja todavía sin revisar. */
  function advertenciasHoja() {
    const lista = [];
    if (!estado.colocaciones.length) {
      lista.push({ nivel: "aviso", ids: [], texto: "La hoja no tiene detalles: al componer sale solo el rótulo." });
    }
    for (const campo of (estado.copiado && estado.copiado.revisar) || []) {
      lista.push({ nivel: "aviso", ids: [], texto: "Rótulo · " + campo + ": copiado de la hoja «" +
        estado.copiado.hoja + "», revíselo (el aviso se quita al cambiarlo)." });
    }
    return lista;
  }

  function advertenciasEstilo() {
    const elegido = estiloElegido();
    if (!elegido || !DX()) return [];
    return estado.colocaciones.filter((c) => !esBloque(c) && DX().mismoEstilo(c.detalle.estilo, elegido) === false)
      .map((c) => ({ nivel: "aviso", ids: [], texto: "'" + c.id + "': exportado con " + DX().textoEstilo(c.detalle.estilo) +
        ", distinto del estilo elegido para exportar (" + DX().textoEstilo(elegido) + "): se queda así." }));
  }

  /** «Usar ortofoto» del detalle (versión 5): solo los marcados la llevan detrás. */
  function casillaOrtofoto(c) {
    const fila = nodo("label", { class: "casilla-ortofoto" });
    const casilla = nodo("input", { type: "checkbox", id: "usar-ortofoto" });
    casilla.checked = c.ortofoto === true;
    casilla.disabled = !estado.ortofoto;
    fila.title = estado.ortofoto ? "La ortofoto del plano va detrás de este detalle, recortada a su página."
      : "Primero cargue una ortofoto («Cargar ortofoto»).";
    casilla.addEventListener("change", () => usarOrtofoto(c, casilla.checked));
    fila.append(casilla, " Usar ortofoto");
    const a = avisoOrtofoto(c);
    if (!a) return fila;
    const caja = nodo("div");
    caja.append(fila, nodo("div", { class: "aviso-ortofoto-seleccion " + a.nivel }, a.largo));
    return caja;
  }

  /** «Mostrar escala»: la etiqueta «ESC: 1:N» debajo del detalle (en la hoja y en el PDF). */
  function casillaEscala(c) {
    const fila = nodo("label", { class: "casilla-ortofoto casilla-escala" });
    const casilla = nodo("input", { type: "checkbox", id: "mostrar-escala" });
    casilla.checked = c.etiqueta_escala !== false;
    fila.title = "Escribe «ESC: 1:N» debajo del detalle. Desmárquelo si el dibujo ya trae su escala escrita.";
    casilla.addEventListener("change", () => mostrarEscala(c, casilla.checked));
    fila.append(casilla, " Mostrar escala («ESC: 1:N»)");
    const dibujo = esZona(c) ? c.bloque.zona.escala_dibujo : c.zona ? c.zona.escala_dibujo : null;
    if (!dibujo) return fila;
    const caja = nodo("div");
    caja.append(fila, nodo("div", { class: "medida" }, "El dibujo ya trae «ESC " + B.textoEscala(dibujo) + "» escrito."));
    return caja;
  }

  function mostrarEscala(c, si) {
    if ((c.etiqueta_escala !== false) === !!si) return;
    if (si) delete c.etiqueta_escala;
    else c.etiqueta_escala = false;
    marcarCambios();
    actualizar();
  }

  function usarOrtofoto(c, si) {
    if ((c.ortofoto === true) === !!si) return;
    c.ortofoto = !!si;
    marcarCambios();
    actualizar();
  }

  const numero1 = (v) => v.toFixed(3).replace(".", ",");

  /** Propiedades de un bloque sin exportar: escala (selector), centro, página y vista previa. */
  function pintarPropiedadesBloque(panel, c) {
    const b = c.bloque;
    const e = estadoBloque(c);
    const sugerida = sugeridaDe(c);
    const pagina = paginaBloque(c);
    const titulo = nodo("div", { class: "fila" });
    titulo.appendChild(nodo("strong", {}, c.id));
    const etiqueta = etiquetaDe(b); // un anónimo se muestra por capa + handle, no por su *U
    titulo.appendChild(nodo("span", { class: "medida" }, esZona(c) ? " · zona borrador del Model Space · sin exportar"
      : " · bloque «" + etiqueta + "» · sin exportar"));
    const filas = [titulo, ...(esZona(c) ? filasZona(c) : [
      nodo("div", { class: "medida" }, b.dxf.nombre + (etiqueta !== b.nombre ? " · anónimo " + b.nombre : "") +
        (b.ocurrencia > 1 || b.total_ocurrencias > 1 ? " · ocurrencia " + b.ocurrencia : "") + " · handle " + b.handle)]),
      nodo("div", { class: "medida" }, "Tamaño real: " + numero1(b.tamano_m[0]) + " × " + numero1(b.tamano_m[1]) + " m")];
    const fila = nodo("div", { class: "fila" });
    fila.appendChild(nodo("label", { for: "escala-bloque" }, "Escala"));
    const selector = nodo("select", { id: "escala-bloque" });
    const lista = escalasDe(c).slice();
    if (!lista.includes(c.escala)) lista.push(c.escala);
    for (const n of lista.sort((x, y) => x - y)) {
      const opcion = nodo("option", { value: String(n) }, B.textoEscala(n) + (n === sugerida ? " (sugerida)"
        : B.esNormalizada(n, escalasDe(c)) ? "" : " (no normalizada)"));
      if (n === c.escala) opcion.selected = true;
      selector.appendChild(opcion);
    }
    selector.addEventListener("change", () => cambiarEscala(c, parseFloat(selector.value)));
    fila.appendChild(selector);
    // Escala escrita a mano: «1:3500» o «3500» (entero de 1 a 100000; puede no ser normalizada).
    const filaEscrita = nodo("div", { class: "fila" });
    filaEscrita.appendChild(nodo("label", { for: "escala-escrita" }, "o escriba"));
    const escrita = nodo("input", { type: "text", id: "escala-escrita", inputmode: "numeric",
      placeholder: "1:3500", title: "Escriba 1:N o N (entero de 1 a 100000) y pulse Enter" });
    escrita.value = B.textoEscala(c.escala);
    escrita.addEventListener("change", () => escribirEscala(c, escrita.value));
    filaEscrita.appendChild(escrita);
    filas.push(fila, filaEscrita,
      campoCentro("Centro X (mm)", c.centro[0], 0), campoCentro("Centro Y (mm)", c.centro[1], 1),
      nodo("div", { class: "medida" }, "Página a " + B.textoEscala(c.escala) + ": " + (b.caja_exacta ? "" : "≤ ") +
        mm(pagina[0]) + " × " + mm(pagina[1]) + " mm (centro fijo al cambiar la escala)."),
      ...(B.esNormalizada(c.escala, escalasDe(c)) ? [] : [nodo("div", { class: "medida aviso-escala" },
        "Escala no normalizada (" + B.textoEscala(c.escala) + "): se permite; el paquete y el rótulo la usan tal cual.")]),
      nodo("div", { class: e.cabe && e.dentro ? "medida" : "medida no-cabe" }, !e.cabe
        ? "NO CABE: sobran " + mm1(e.exceso[0]) + " × " + mm1(e.exceso[1]) + " mm" +
          (sugerida ? "; sugerida " + B.textoEscala(sugerida) : "") + ". Se puede guardar, pero componer lo rechaza."
        : !e.dentro ? "Se sale del área de dibujo: muévalo." : "Cabe en el área de dibujo."));
    const previa = previaDe(c);
    const textoPrevia = { lista: "Vista previa lista" + (previa.datos && previa.datos.en_cache ? " (de la caché)" : "") + ".",
      pidiendo: "Pidiendo vista previa al trabajador…" }[previa.estado] || previa.mensaje || "";
    if (textoPrevia) filas.push(nodo("div", { class: "medida" }, textoPrevia));
    filas.push(nodo("div", { class: "medida" }, "Teclas + y − (o el tirador de la esquina) cambian la escala."));
    const botones = nodo("div", { class: "botones" });
    const acciones = [
      ...(esZona(c) && window.EditorPanelZonas ? [["Editar zona…", () => window.EditorPanelZonas.editar(c)]] : []),
      ["Centrar", () => moverCentro(c, B.centroZona(ZONA))],
      ["Escala sugerida", () => sugerida && cambiarEscala(c, sugerida)],
      ["Ajustar a la hoja", () => ajustarALaHoja(c)],
      ["Traer al frente", () => reordenar(c, +Infinity)],
      ["Enviar atrás", () => reordenar(c, -Infinity)],
      ["Quitar", () => quitar(c)],
    ];
    if (previa.estado === "error" && P()) acciones.splice(2, 0, ["Reintentar vista previa", () => { P().reintentar(b); actualizar(); }]);
    for (const [texto, accion] of acciones) {
      const boton = nodo("button", { type: "button" }, texto);
      boton.addEventListener("click", accion);
      if (texto === "Escala sugerida") boton.disabled = !sugerida || sugerida === c.escala;
      botones.appendChild(boton);
    }
    panel.replaceChildren(...filas, casillaOrtofoto(c), casillaEscala(c), botones);
  }

  /** Lo propio de una zona borrador en el panel Selección: nombre (editable), DXF, zona y capas. */
  function filasZona(c) {
    const b = c.bloque;
    const z = b.zona;
    const fila = nodo("div", { class: "fila" });
    fila.appendChild(nodo("label", { for: "nombre-zona-hoja" }, "Nombre"));
    const input = nodo("input", { type: "text", id: "nombre-zona-hoja", maxlength: "40" });
    input.value = b.nombre;
    input.title = "El nombre del paquete al exportar (<nombre>_1-N). No cambia al exportar.";
    input.addEventListener("change", () => renombrarZona(c, input.value));
    fila.appendChild(input);
    const n = (v) => v.toFixed(3).replace(".", ",");
    const capas = z.capas ? "solo " + z.capas.length + " capa(s)" : z.excluir ? "todas menos " + z.excluir.length
      : "todas las capas";
    return [fila,
      nodo("div", { class: "medida" }, b.dxf.nombre + " · zona X " + n(z.rect[0]) + " a " + n(z.rect[2]) +
        ", Y " + n(z.rect[1]) + " a " + n(z.rect[3])),
      nodo("div", { class: "medida" }, "Capas: " + capas + ". «Editar zona…» abre el Model Space para cambiar el " +
        "rectángulo o las capas."),
      ...lineasEscalaDibujo(z.escala_dibujo, c.escala)];
  }

  /** La escala a la que está dibujada una zona y, si va a otra, el aviso ámbar. */
  function lineasEscalaDibujo(nDibujo, nZona) {
    const ZE = window.EditorZonas;
    if (!nDibujo) return [nodo("div", { class: "medida" }, "Escala del dibujo: no se sabe (sin «ESC 1:N» leído).")];
    const aviso = ZE ? ZE.avisoEscala(nZona, nDibujo) : null;
    return [nodo("div", { class: "medida" }, "Dibujada a " + B.textoEscala(nDibujo) + "."),
      ...(aviso ? [nodo("div", { class: "medida aviso-escala" }, aviso)] : [])];
  }

  /** Cambia el nombre de una zona borrador (limpio como lo dejará el servidor; único en la hoja). */
  function renombrarZona(c, texto) {
    const ZE = window.EditorZonas;
    const r = ZE ? ZE.limpiarNombre(texto) : { nombre: texto };
    if (r.error) {
      mensaje(r.error, "error");
      pintarPropiedades();
      return;
    }
    const otros = new Set(estado.colocaciones.filter((x) => x !== c).map((x) => x.id.toLowerCase()));
    if (otros.has(r.nombre.toLowerCase())) {
      mensaje("Ya hay un elemento «" + r.nombre + "» en el plano: elija otro nombre.", "error");
      pintarPropiedades();
      return;
    }
    if (r.nombre !== c.bloque.nombre) {
      const antes = c.id;
      c.bloque.nombre = r.nombre;
      c.bloque.etiqueta = r.nombre;
      c.id = r.nombre;
      if (estado.seleccion === antes) estado.seleccion = c.id;
      marcarCambios();
    }
    actualizar();
  }

  /**
   * «Agregar a la hoja» del cuadro «Zonas del modelo» (Fase 10e): la zona como borrador, con su
   * nombre (Zona_01… o el escrito) y su tamaño real a la escala elegida, centrada en el área de
   * dibujo (corrida si ya hay otra ahí). z: {nombre, rect, capas, excluir, modo, desmarcadas,
   * escala, catalogo}. Devuelve su id.
   */
  function agregarZona(z) {
    const catalogo = z.catalogo;
    const mmU = catalogo.unidades && catalogo.unidades.mm_por_unidad;
    const ids = new Set(estado.colocaciones.map((c) => c.id));
    const c = { id: L.idUnico(z.nombre, ids), escala: z.escala, bloque: null };
    c.bloque = datosZona(z, catalogo, mmU, c.id);
    let centro = B.centroZona(ZONA);
    const ocupado = (p) => estado.colocaciones.some((x) => esBloque(x) && x.centro[0] === p[0] && x.centro[1] === p[1]);
    for (let i = 0; i < 20 && ocupado(centro); i++) centro = [centro[0] + 10, centro[1] - 10];
    c.centro = B.centroLimitado(centro, paginaBloque(c), ZONA);
    // «Mostrar escala» empieza desmarcado si el dibujo ya trae su «ESC 1:N» y es la misma escala
    // con que se exporta (si no, la del dibujo diría otra: se deja marcado). Solo al agregar.
    if (L.etiquetaInicial(z.escala_dibujo, z.escala) === false) c.etiqueta_escala = false;
    estado.colocaciones.push(c);
    estado.seleccion = c.id;
    marcarCambios();
    actualizar();
    return c.id;
  }

  function datosZona(z, catalogo, mmU, nombre) {
    const ZE = window.EditorZonas;
    const tam = ZE.tamanoM(z.rect, mmU);
    return { dxf: dxfDe(catalogo), nombre, etiqueta: nombre, handle: null, ocurrencia: 1, total_ocurrencias: 1,
      tamano_m: tam, caja_exacta: true, sugerida: B.escalaSugerida(tam, B.margenHoja(), ZONA),
      escalas: catalogo.escalas || B.ESCALAS,
      zona: { rect: z.rect.slice(), capas: z.capas || null, excluir: z.excluir || null, modo: z.modo || "excluir",
        desmarcadas: (z.desmarcadas || []).slice(), escala_dibujo: z.escala_dibujo || null } };
  }

  /** «Editar zona…» → «Guardar cambios en la hoja»: otro rectángulo, capas o escala; el centro y
   *  el nombre se quedan. */
  function actualizarZona(id, z) {
    const c = estado.colocaciones.find((x) => x.id === id && esZona(x));
    if (!c) return false;
    const catalogo = z.catalogo;
    const anterior = c.bloque;
    c.bloque = datosZona(z, catalogo, catalogo.unidades.mm_por_unidad, anterior.nombre);
    c.escala = z.escala;
    if (P()) P().soltar(anterior); // la vista previa de la zona vieja ya no hace falta
    c.original = null;
    estado.seleccion = c.id;
    marcarCambios();
    actualizar();
    return true;
  }

  function campoCentro(etiqueta, valor, indice) {
    const fila = nodo("div", { class: "fila" });
    fila.appendChild(nodo("label", {}, etiqueta));
    const input = nodo("input", { type: "text", inputmode: "decimal" });
    input.value = mm(Math.round(valor * 100) / 100);
    input.addEventListener("change", () => {
      const numero = parseFloat(input.value.replace(",", "."));
      const c = seleccionada();
      if (!c || !esBloque(c) || !isFinite(numero)) {
        pintarPropiedades();
        return;
      }
      const centro = c.centro.slice();
      centro[indice] = numero;
      moverCentro(c, centro);
    });
    fila.appendChild(input);
    return fila;
  }

  /** Margen alrededor del dibujo de este detalle (Fase 11). Vacío: el de componedor.json. */
  function campoMargen(c) {
    const fila = nodo("div", { class: "fila margen-detalle" });
    fila.appendChild(nodo("label", { for: "margen-detalle" }, "Margen (mm)"));
    const general = L.margenDe(null, DATOS);
    const input = nodo("input", { type: "text", inputmode: "decimal", id: "margen-detalle",
      placeholder: mm(general) + " (general)" });
    input.value = typeof c.margen === "number" ? mm(c.margen) : "";
    input.title = "Borde blanco que se deja alrededor del dibujo en la hoja, de 0 a " + L.MARGEN_MAXIMO_MM +
      " mm. Vacío: el de componedor.json (" + mm(general) + " mm).";
    input.addEventListener("change", () => {
      const texto = input.value.trim().replace(",", ".");
      const numero = texto === "" ? null : Number(texto);
      if (numero !== null && !L.margenValido(numero)) {
        mensaje("El margen va de 0 a " + L.MARGEN_MAXIMO_MM + " mm (vacío: el general, " + mm(general) + " mm).", "error");
        pintarPropiedades();
        return;
      }
      if (numero !== null && !L.cabeDetalle(c.detalle, numero, ZONA)) {
        mensaje("Con " + mm(numero) + " mm de margen '" + c.id + "' no cabe en el área de dibujo.", "error");
        pintarPropiedades();
        return;
      }
      if (numero === null) delete c.margen;
      else c.margen = numero;
      const dentro = L.clampDetalle(c.pos, c.detalle, margenDe(c), ZONA);
      if (dentro) c.pos = dentro; // si con el margen nuevo se salía, se acomoda
      marcarCambios();
      actualizar();
    });
    fila.appendChild(input);
    return fila;
  }

  function campo(etiqueta, valor, indice) {
    const fila = nodo("div", { class: "fila" });
    fila.appendChild(nodo("label", {}, etiqueta));
    const input = nodo("input", { type: "text", inputmode: "decimal" });
    input.value = mm(valor);
    input.addEventListener("change", () => {
      const numero = parseFloat(input.value.replace(",", "."));
      const c = seleccionada();
      if (!c || !isFinite(numero)) {
        pintarPropiedades();
        return;
      }
      const pos = c.pos.slice();
      pos[indice] = numero;
      mover(c, pos);
    });
    fila.appendChild(input);
    return fila;
  }

  function pintarListaPlano() {
    const lista = document.getElementById("lista-plano");
    lista.replaceChildren(...estado.colocaciones.map((c) => {
      const li = nodo("li", { class: c.id === estado.seleccion ? "sel" : "" }, esBloque(c)
        ? c.id + " (centro " + mm1(c.centro[0]) + "; " + mm1(c.centro[1]) + ") · " + B.textoEscala(c.escala) +
          (esZona(c) ? " · zona borrador" : " · sin exportar")
        : c.id + " (" + mm1(c.pos[0]) + "; " + mm1(c.pos[1]) + ")");
      li.addEventListener("click", () => seleccionar(c.id));
      return li;
    }));
    if (!estado.colocaciones.length) {
      lista.appendChild(nodo("li", { class: "vacio" }, "Vacío: agregue detalles desde el panel izquierdo."));
    }
  }

  function pintarAdvertencias(lista) {
    const ul = document.getElementById("advertencias");
    if (!lista.length) {
      ul.replaceChildren(nodo("li", { class: "ninguna" }, "Sin advertencias."));
      return;
    }
    ul.replaceChildren(...lista.map((a) => nodo("li", { class: a.nivel }, a.texto)));
  }

  /**
   * Panel «Rótulo» (4.3b): formularios de los campos simples, revisiones y firmas
   * (editor_panel_rotulo.js). Lo que no se toca se guarda tal como vino.
   */
  const panelRotulo = window.EditorPanelRotulo.crear({
    panel: document.getElementById("panel-rotulo"),
    datos: DATOS_ROTULO,
    modelo: () => estado.rotulo,
    escalas: () => estado.colocaciones.map(escalaDe),
    automatico: (campo) => estado.automaticos[campo],
    alCambiar: marcarCambios,
  });

  /** Panel «Notas» (4.3c): catálogo con casillas y notas del plano (editor_panel_notas.js). */
  const panelNotas = window.EditorPanelNotas.crear({
    panel: document.getElementById("panel-notas"),
    datos: DATOS_ROTULO,
    modelo: () => estado.rotulo,
    alCambiar: marcarCambios,
  });

  /** Panel «Convenciones» (4.3d): símbolos con casillas y su lista (editor_panel_convenciones.js). */
  const panelConvenciones = window.EditorPanelConvenciones.crear({
    panel: document.getElementById("panel-convenciones"),
    datos: DATOS_ROTULO,
    modelo: () => estado.rotulo,
    alCambiar: marcarCambios,
  });

  function pintarRotulo() {
    panelRotulo.pintar();
    panelNotas.reiniciar(); // vuelve a leer las notas del rótulo actual
    panelConvenciones.reiniciar(); // y las convenciones
  }

  /** Panel «Rosa de los vientos»: mostrar/ocultar, X / Y y restaurar posición. */
  function pintarRosa() {
    const panel = document.getElementById("panel-rosa");
    if (!estado.rosa) {
      panel.replaceChildren(nodo("div", { class: "vacio" }, "El formato no tiene rosa de los vientos."));
      return;
    }
    const casilla = nodo("input", { type: "checkbox", id: "mostrar-rosa" });
    casilla.checked = estado.rosa.visible;
    casilla.addEventListener("change", () => mostrarRosa(casilla.checked));
    const etiqueta = nodo("label", { class: "casilla", for: "mostrar-rosa" });
    etiqueta.append(casilla, " Mostrar rosa de los vientos");
    const filas = [etiqueta];
    if (estado.rosa.visible) {
      const tamano = L.tamanoRosa(ROSA.rect_mm);
      const guardada = L.redondearDentro(estado.rosa.pos, tamano, ZONA);
      filas.push(campoRosa("X (mm)", guardada[0], 0), campoRosa("Y (mm)", guardada[1], 1),
        nodo("div", { class: "medida" }, "Esquina inferior izquierda del rectángulo de la rosa (" +
          mm(tamano[0]) + " × " + mm(tamano[1]) + " mm)."));
    } else {
      filas.push(nodo("div", { class: "medida" }, "Oculta: no sale en el plano y no genera advertencias."));
    }
    const restaurar = nodo("button", { type: "button" }, "Restaurar posición");
    restaurar.title = "Volver a su lugar original (" + mm(ROSA_ORIGEN[0]) + "; " + mm(ROSA_ORIGEN[1]) + ") mm";
    restaurar.addEventListener("click", restaurarRosa);
    const botones = nodo("div", { class: "botones" });
    botones.appendChild(restaurar);
    filas.push(botones);
    panel.replaceChildren(...filas);
  }

  function campoRosa(etiqueta, valor, indice) {
    const fila = nodo("div", { class: "fila" });
    fila.appendChild(nodo("label", {}, etiqueta));
    const input = nodo("input", { type: "text", inputmode: "decimal" });
    input.value = mm(valor);
    input.addEventListener("change", () => {
      const numero = parseFloat(input.value.replace(",", "."));
      if (!isFinite(numero)) {
        pintarRosa();
        return;
      }
      const pos = estado.rosa.pos.slice();
      pos[indice] = numero;
      moverRosa(pos);
    });
    fila.appendChild(input);
    return fila;
  }

  // ---------------------------------------------------------------------------------------
  // Acciones.
  // ---------------------------------------------------------------------------------------

  function seleccionar(id) {
    estado.seleccion = id;
    if (id) estado.rosaSeleccionada = false;
    actualizar();
  }

  function seleccionarRosa() {
    estado.seleccion = null;
    estado.rosaSeleccionada = true;
    actualizar();
  }

  /** Mueve la rosa: igual que un detalle, siempre COMPLETA dentro del área de dibujo. */
  function moverRosa(pos) {
    if (!estado.rosa) return;
    const limitada = L.clampAZona(pos, L.tamanoRosa(ROSA.rect_mm), ZONA);
    if (!limitada) return;
    if (limitada[0] !== estado.rosa.pos[0] || limitada[1] !== estado.rosa.pos[1]) {
      estado.rosa.pos = limitada;
      marcarCambios();
    }
    actualizar();
  }

  function mostrarRosa(visible) {
    if (!estado.rosa || estado.rosa.visible === visible) return;
    estado.rosa.visible = visible;
    if (!visible) estado.rosaSeleccionada = false;
    marcarCambios();
    actualizar();
  }

  function restaurarRosa() {
    if (!estado.rosa) return;
    if (!estado.rosa.visible) {
      estado.rosa.visible = true;
      marcarCambios();
    }
    moverRosa(ROSA_ORIGEN.slice()); // vuelve a su sitio y vuelve a dibujar
  }

  function agregar(detalle) {
    const ids = new Set(estado.colocaciones.map((c) => c.id));
    const id = L.idUnico(detalle.id, ids);
    const margen = L.margenDe(null, DATOS);
    let pos = L.clampDetalle(L.centrarDetalle(detalle, margen, ZONA), detalle, margen, ZONA);
    if (!pos) {
      mensaje("'" + detalle.id + "' no cabe en el área de dibujo.", "error");
      return;
    }
    // Si ya hay un detalle exactamente ahí (p. ej. otra copia), se corre 10 mm para que se vea.
    const ocupada = (p) => estado.colocaciones.some((c) => c.pos[0] === p[0] && c.pos[1] === p[1]);
    for (let i = 0; i < 20 && ocupada(pos); i++) {
      pos = L.clampDetalle([pos[0] + 10, pos[1] - 10], detalle, margen, ZONA);
    }
    estado.colocaciones.push({ id, detalle, pos });
    estado.seleccion = id;
    marcarCambios();
    actualizar();
  }

  /**
   * El nombre que se muestra de un bloque: su etiqueta (capa + handle en un anónimo). El
   * plano.json no la guarda (solo el *U y el handle): al abrir un plano se busca por handle en
   * la carpeta cargada, si es la del mismo DXF; si no, el nombre.
   */
  let ultimoCatalogo = null;
  function etiquetaDe(b) {
    if (b.etiqueta) return b.etiqueta;
    const c = ultimoCatalogo;
    const x = c && c.dxf.sha256 === b.dxf.sha256 ? c.bloques.find((y) => y.handle === b.handle) : null;
    return (x && x.etiqueta) || b.nombre;
  }

  /** El DXF de la carpeta, uno por sha256 (los bloques del mismo DXF comparten su entrada). */
  const dxfsPorSha = new Map();
  function dxfDe(catalogo) {
    const sha = catalogo.dxf.sha256;
    if (!dxfsPorSha.has(sha)) dxfsPorSha.set(sha, B.entradaDxf(catalogo));
    return dxfsPorSha.get(sha);
  }

  /** «Agregar al plano» de un bloque de la carpeta del DXF: caja a la escala sugerida, centrada. */
  function agregarBloque(b, catalogo) {
    const etiqueta = b.etiqueta || b.nombre;
    if (!b.tamano_m || !b.unidades || !b.unidades.verificadas) {
      mensaje("'" + etiqueta + "': sin unidades verificadas no se sabe su tamaño en papel; no se puede colocar.", "error");
      return null;
    }
    const escalas = catalogo.escalas || B.ESCALAS;
    const ids = new Set(estado.colocaciones.map((c) => c.id));
    const c = { id: L.idUnico(b.archivo || b.nombre, ids), escala: b.escala_sugerida || escalas[escalas.length - 1],
      bloque: { dxf: dxfDe(catalogo), nombre: b.nombre, etiqueta, handle: b.handle, ocurrencia: b.ocurrencia,
        total_ocurrencias: b.total_ocurrencias, tamano_m: b.tamano_m.slice(), caja_exacta: b.caja_exacta,
        sugerida: b.escala_sugerida, escalas } };
    let centro = B.centroZona(ZONA);
    const ocupado = (p) => estado.colocaciones.some((x) => esBloque(x) && x.centro[0] === p[0] && x.centro[1] === p[1]);
    for (let i = 0; i < 20 && ocupado(centro); i++) centro = [centro[0] + 10, centro[1] - 10];
    c.centro = B.centroLimitado(centro, paginaBloque(c), ZONA);
    estado.colocaciones.push(c);
    estado.seleccion = c.id;
    if (!b.escala_sugerida) mensaje("'" + etiqueta + "' no cabe ni a 1:" + escalas[escalas.length - 1] + ": queda en rojo.", "aviso");
    marcarCambios();
    actualizar();
    return c.id;
  }

  /** Mueve un bloque por su centro: si cabe, la página queda completa dentro del área. */
  function moverCentro(c, centro) {
    const limitado = B.centroLimitado(centro, paginaBloque(c), ZONA);
    if (limitado[0] !== c.centro[0] || limitado[1] !== c.centro[1]) {
      c.centro = limitado;
      marcarCambios();
    }
    actualizar();
  }

  /** La escala que el usuario escribió («1:3500» o «3500»). */
  function escribirEscala(c, texto) {
    const r = B.leerEscalaEscrita(texto, escalasDe(c));
    if (r.error) {
      mensaje(r.error, "error");
      pintarPropiedades();
      return;
    }
    if (r.aviso) mensaje(B.textoEscala(r.n) + ": " + r.aviso + " (se permite).", "aviso");
    cambiarEscala(c, r.n);
  }

  /** «Ajustar a la hoja»: la escala exacta más grande con la que cabe (puede no ser normalizada). */
  function ajustarALaHoja(c) {
    const n = B.escalaAjustada(c.bloque.tamano_m, B.margenHoja(), ZONA);
    if (!n) {
      mensaje("'" + c.id + "' no cabe en el área de dibujo ni a 1:" + B.ESCALA_MAXIMA + ".", "error");
      return;
    }
    if (!B.esNormalizada(n, escalasDe(c))) mensaje(B.textoEscala(n) + ": la más grande que cabe (escala no normalizada).", "aviso");
    // Con el centro fijo la caja puede quedar afuera: se acomoda dentro (es una sola acción).
    c.escala = n;
    moverCentro(c, c.centro);
    marcarCambios();
  }

  /** Cambia la escala de un bloque: el CENTRO no se mueve (aunque la caja quede afuera). */
  function cambiarEscala(c, n) {
    if (!esBloque(c) || !(n > 0) || n === c.escala) {
      actualizar();
      return;
    }
    c.escala = n;
    marcarCambios();
    actualizar();
  }

  /** Mueve con la regla de componer: la PÁGINA siempre queda dentro del área de dibujo. */
  function mover(c, pos) {
    if (esBloque(c)) {
      const p = paginaBloque(c);
      moverCentro(c, [pos[0] + p[0] / 2, pos[1] + p[1] / 2]);
      return;
    }
    const limitada = L.clampDetalle(pos, c.detalle, margenDe(c), ZONA);
    if (!limitada) return;
    if (limitada[0] !== c.pos[0] || limitada[1] !== c.pos[1]) {
      c.pos = limitada;
      marcarCambios();
    }
    actualizar();
  }

  function reordenar(c, destino) {
    const i = estado.colocaciones.indexOf(c);
    estado.colocaciones.splice(i, 1);
    if (destino > 0) estado.colocaciones.push(c);
    else estado.colocaciones.unshift(c);
    marcarCambios();
    actualizar();
  }

  function quitar(c) {
    estado.colocaciones = estado.colocaciones.filter((x) => x !== c);
    // La vista previa que esperaba turno ya no hace falta (si ningún otro usa ese bloque).
    if (esBloque(c) && P() && !estado.colocaciones.some((x) => esBloque(x) &&
        x.bloque.handle === c.bloque.handle && x.bloque.dxf.sha256 === c.bloque.dxf.sha256)) {
      P().soltar(c.bloque);
    }
    estado.seleccion = null;
    marcarCambios();
    actualizar();
  }

  // ---------------------------------------------------------------------------------------
  // Mouse: arrastrar detalles, desplazar la hoja, zoom con la rueda.
  // ---------------------------------------------------------------------------------------

  /** Detalles cuya página contiene el punto (mm de papel), del de ENCIMA al de abajo. */
  function detallesEnPunto(p) {
    return estado.colocaciones.filter((c) => {
      const r = paginaDe(c);
      return p.x >= r[0] && p.x <= r[2] && p.y >= r[1] && p.y <= r[3];
    }).reverse();
  }

  function empezarArrastre(ev, c) {
    if (ev.button !== 0) return;
    ev.stopPropagation();
    const p = puntoPapel(ev);
    if (ev.altKey) {
      // Alt + clic: el de debajo del seleccionado en ese punto (en ciclo). Sin Alt, el clic
      // toma el de encima, como en el PDF.
      ev.preventDefault();
      const pila = detallesEnPunto(p);
      const actual = pila.findIndex((x) => x.id === estado.seleccion);
      c = pila[(actual + 1) % pila.length] || c;
    }
    if (estado.seleccion !== c.id) seleccionar(c.id);
    // Un bloque se arrastra por su centro (ajustado al paso); un detalle, por su esquina.
    const ref = esBloque(c) ? c.centro : c.pos;
    arrastre = { c, dx: p.x - ref[0], dy: p.y - ref[1] };
    svg.setPointerCapture(ev.pointerId);
  }

  /** El tirador de la esquina: la escala estándar que deja la esquina más cerca del puntero. */
  function empezarTirador(ev, c) {
    if (ev.button !== 0) return;
    ev.stopPropagation();
    arrastre = { c, tirador: true };
    svg.setPointerCapture(ev.pointerId);
  }

  /** La rosa se arrastra como un detalle (mismo paso de ajuste). Está debajo de los
   * detalles: donde un detalle la tapa, el clic toma el detalle. */
  function empezarArrastreRosa(ev) {
    if (ev.button !== 0) return;
    ev.stopPropagation();
    const p = puntoPapel(ev);
    if (!estado.rosaSeleccionada) seleccionarRosa();
    arrastre = { rosa: true, dx: p.x - estado.rosa.pos[0], dy: p.y - estado.rosa.pos[1] };
    svg.setPointerCapture(ev.pointerId);
  }

  svg.addEventListener("pointerdown", (ev) => {
    if (ev.button !== 0 || arrastre) return;
    paneo = { x: ev.clientX, y: ev.clientY, vista: Object.assign({}, estado.vista) };
    svg.classList.add("paneando");
    svg.setPointerCapture(ev.pointerId);
  });

  svg.addEventListener("pointermove", (ev) => {
    const p = puntoPapel(ev);
    document.getElementById("cursor").textContent = "Cursor: X " + mm(p.x) + "  Y " + mm(p.y) + " mm";
    if (arrastre) {
      const pos = [L.ajustarAPaso(p.x - arrastre.dx, estado.paso),
        L.ajustarAPaso(p.y - arrastre.dy, estado.paso)];
      if (arrastre.tirador) {
        const c = arrastre.c;
        cambiarEscala(c, B.escalaPorTirador(c.centro, [p.x, p.y], c.bloque.tamano_m, B.margenHoja(), escalasDe(c)));
      } else if (arrastre.rosa) moverRosa(pos);
      else if (esBloque(arrastre.c)) moverCentro(arrastre.c, pos);
      else mover(arrastre.c, pos);
    } else if (paneo) {
      const caja = svg.getBoundingClientRect();
      const factor = paneo.vista.ancho / caja.width;
      estado.vista.x = paneo.vista.x - (ev.clientX - paneo.x) * factor;
      estado.vista.y = paneo.vista.y - (ev.clientY - paneo.y) * factor;
      aplicarVista();
    }
  });

  function terminar(ev) {
    if ((arrastre || paneo) && svg.hasPointerCapture(ev.pointerId)) svg.releasePointerCapture(ev.pointerId);
    if (paneo && Math.abs(ev.clientX - paneo.x) + Math.abs(ev.clientY - paneo.y) < 3 && !arrastre) {
      if (estado.seleccion || estado.rosaSeleccionada) { // clic en el fondo: quita la selección
        estado.rosaSeleccionada = false;
        seleccionar(null);
      }
    }
    arrastre = null;
    paneo = null;
    svg.classList.remove("paneando");
  }
  svg.addEventListener("pointerup", terminar);
  svg.addEventListener("pointercancel", terminar);
  svg.addEventListener("pointerleave", () => (document.getElementById("cursor").textContent = "Cursor: —"));

  svg.addEventListener("wheel", (ev) => {
    ev.preventDefault();
    zoom(ev.deltaY < 0 ? 1.15 : 1 / 1.15, puntoSvg(ev));
  }, { passive: false });

  // ---------------------------------------------------------------------------------------
  // Teclado: flechas (paso; Shift = 10 pasos), Supr = quitar, Ctrl+S = guardar; con un bloque
  // sin exportar seleccionado, + y − cambian su escala. Nada de esto actúa si el foco está en
  // un cuadro de texto (ni en una lista desplegable).
  // ---------------------------------------------------------------------------------------

  // Vista limpia: el botón la deja fija; la tecla V la muestra mientras se mantiene.
  let vistaLimpiaFija = false;
  let teclaV = false;
  const botonVistaLimpia = document.getElementById("btn-vista-limpia");
  function aplicarVistaLimpia() {
    svg.classList.toggle("vista-limpia", vistaLimpiaFija || teclaV);
    botonVistaLimpia.setAttribute("aria-pressed", String(vistaLimpiaFija));
  }
  botonVistaLimpia.addEventListener("click", () => {
    vistaLimpiaFija = !vistaLimpiaFija;
    aplicarVistaLimpia();
  });
  document.addEventListener("keyup", (ev) => {
    if (ev.key === "v" || ev.key === "V") {
      teclaV = false;
      aplicarVistaLimpia();
    }
  });
  window.addEventListener("blur", () => {
    teclaV = false; // si se suelta la V fuera de la ventana
    aplicarVistaLimpia();
  });

  document.addEventListener("keydown", (ev) => {
    if (ev.ctrlKey && (ev.key === "s" || ev.key === "S")) {
      ev.preventDefault();
      guardar();
      return;
    }
    const etiqueta = ev.target.tagName;
    if (etiqueta === "INPUT" || etiqueta === "SELECT" || etiqueta === "TEXTAREA" || ev.target.isContentEditable) return;
    if ((ev.key === "v" || ev.key === "V") && !ev.ctrlKey && !ev.altKey && !ev.metaKey) {
      teclaV = true;
      aplicarVistaLimpia();
      return;
    }
    const paso = estado.paso * (ev.shiftKey ? 10 : 1);
    const movimientos = { ArrowLeft: [-paso, 0], ArrowRight: [paso, 0], ArrowUp: [0, paso], ArrowDown: [0, -paso] };
    if (estado.rosaSeleccionada && estado.rosa && estado.rosa.visible) {
      if (movimientos[ev.key]) {
        ev.preventDefault();
        const [dx, dy] = movimientos[ev.key];
        moverRosa([estado.rosa.pos[0] + dx, estado.rosa.pos[1] + dy]);
      }
      return; // Supr no quita la rosa: se oculta con la casilla
    }
    const c = seleccionada();
    if (!c) return;
    if ((ev.key === "+" || ev.key === "-") && esBloque(c) && !ev.ctrlKey && !ev.altKey && !ev.metaKey) {
      ev.preventDefault();
      cambiarEscala(c, B.escalaVecina(c.escala, ev.key === "+" ? +1 : -1, escalasDe(c)));
      return;
    }
    if (movimientos[ev.key]) {
      ev.preventDefault();
      const [dx, dy] = movimientos[ev.key]; // en papel, Y hacia arriba: flecha arriba = +Y
      if (esBloque(c)) moverCentro(c, [c.centro[0] + dx, c.centro[1] + dy]);
      else mover(c, [c.pos[0] + dx, c.pos[1] + dy]);
    } else if (ev.key === "Delete") {
      quitar(c);
    }
  });

  // ---------------------------------------------------------------------------------------
  // Guardar y abrir plano.json.
  // ---------------------------------------------------------------------------------------

  const SEPARADOR = DATOS.carpeta_editor.includes("\\") ? "\\" : "/";

  function pintarDondeGuardar() {
    const caja = document.getElementById("donde-guardar");
    caja.replaceChildren(
      nodo("strong", {}, "Guarde el plano.json en la MISMA carpeta que este editor.html "),
      nodo("span", {}, "(las rutas del plano son relativas a esa carpeta). Al generar el editor, " +
        "esa carpeta era: "),
      nodo("code", {}, DATOS.carpeta_editor),
      nodo("span", {}, " (dato informativo: si movió el editor, use la carpeta donde está ahora).")
    );
  }

  function mostrarComando(nombre) {
    const base = nombre.replace(/\.json$/i, "");
    const ruta = DATOS.carpeta_editor + SEPARADOR;
    const comando = 'python -m componedor.cli componer "' + ruta + nombre + '" --salida "' +
      ruta + base + '.pdf"';
    document.getElementById("texto-comando").textContent = comando;
    document.getElementById("comando").hidden = false;
  }

  function descargar(texto, nombre) {
    const blob = new Blob([texto], { type: "application/json" });
    const enlace = nodo("a", { download: nombre });
    enlace.href = URL.createObjectURL(blob);
    document.body.appendChild(enlace);
    enlace.click();
    enlace.remove();
    setTimeout(() => URL.revokeObjectURL(enlace.href), 1000);
  }

  async function guardar() {
    // Una hoja vacía (solo el rótulo) se guarda en la versión 7; componer avisa.
    const texto = textoPlano();
    if (window.showSaveFilePicker) {
      try {
        const archivo = await window.showSaveFilePicker({
          suggestedName: "plano.json",
          types: [{ description: "Plano (JSON)", accept: { "application/json": [".json"] } }],
        });
        const escritor = await archivo.createWritable();
        await escritor.write(new Blob([texto], { type: "application/json" }));
        await escritor.close();
        estado.archivo = archivo.name;
        guardado(archivo.name, false);
        if (window.EditorPanelHojas) window.EditorPanelHojas.refrescar();
        return;
      } catch (error) {
        if (error && error.name === "AbortError") return; // el usuario canceló: nada que hacer
        // Otro error (permisos, página abierta desde file://…): se usa la descarga normal.
      }
    }
    descargar(texto, "plano.json");
    guardado("plano.json", true);
  }

  /** plano.json con los detalles, la rosa y (si se abrió un plano que lo traía) el rótulo.
   *  Sin los campos retirados del rótulo (disenador, revisor): R.paraGuardar los quita. */
  function textoPlano() {
    // Versión 6: las zonas (borradores y exportadas) van en la lista "dxf" del plano.
    return L.serializarPlano(estado.colocaciones, DATOS, {
      rosa: estado.rosa, rotulo: R.paraGuardar(estado.rotulo), original: estado.original,
      ortofoto: estado.ortofoto, copiado: estado.copiado });
  }

  function guardado(nombre, descargado) {
    estado.cambios = false;
    mostrarComando(nombre);
    // Bloques sin exportar: se guarda igual (versión 3), con aviso; componer los pedirá.
    const avisos = advertenciasBloques().map((a) => a.texto);
    const extra = avisos.length ? "\n- " + avisos.join("\n- ") : "";
    if (descargado) {
      mensaje("Se descargó '" + nombre + "' en la carpeta de descargas del navegador.\n" +
        "Muévalo a la carpeta de este editor.html antes de componer." + extra, avisos.length ? "aviso" : "ok");
    } else {
      mensaje("Plano guardado como '" + nombre + "'. Verifique que quedó en la carpeta de este editor.html." + extra,
        avisos.length ? "aviso" : "ok");
    }
  }

  function abrir(texto, archivo) {
    const resultado = L.leerPlano(texto, DATOS);
    if (resultado.errores.length) {
      mensaje("No se pudo abrir el plano:\n- " + resultado.errores.join("\n- "), "error");
      return false; // el plano de antes sigue abierto, con su nombre
    }
    estado.colocaciones = resultado.colocaciones;
    for (const c of estado.colocaciones) { // un DXF = una entrada (por sha256), como al agregar
      const dueño = esBloque(c) ? c.bloque : c.zona || null; // c.zona: exportado desde una zona
      if (!dueño) continue;
      if (!dxfsPorSha.has(dueño.dxf.sha256)) dxfsPorSha.set(dueño.dxf.sha256, dueño.dxf);
      dueño.dxf = dxfsPorSha.get(dueño.dxf.sha256);
      if (esBloque(c) && c.bloque.zona) c.bloque.dxf = dueño.dxf;
    }
    estado.seleccion = null;
    estado.rosaSeleccionada = false;
    // Sin "rosa_vientos" en el plano: visible y en su sitio (lo mismo que hace componer).
    if (ROSA) estado.rosa = resultado.rosa || { visible: true, pos: ROSA_ORIGEN.slice() };
    estado.rotulo = R.crearModelo(resultado.rotulo, DEFINICION_ROTULO); // se conserva al guardar
    estado.original = resultado.original;
    estado.ortofoto = resultado.ortofoto || null;
    estado.archivo = archivo || null;
    estado.copiado = resultado.copiado ? Object.assign({}, resultado.copiado, { valores: Object.fromEntries(
      resultado.copiado.revisar.map((c) => [c, R.valor(estado.rotulo, c)])) }) : null;
    estado.automaticos = {};
    if (PO() && PO().repintar) PO().repintar();
    if (window.EditorPanelLocalizacion) window.EditorPanelLocalizacion.repintar();
    pintarRotulo();
    estado.cambios = resultado.avisos.length > 0; // si se ajustó algo, hay cambios por guardar
    actualizar();
    const resumen = "Plano abierto: " + resultado.colocaciones.length + " detalle(s).";
    if (resultado.avisos.length) mensaje(resumen + "\n- " + resultado.avisos.join("\n- "), "");
    else mensaje(resumen, "ok");
    return true;
  }

  document.getElementById("btn-guardar").addEventListener("click", guardar);
  document.getElementById("btn-abrir").addEventListener("click", () => {
    if (estado.cambios && !confirm("Hay cambios sin guardar. ¿Abrir otro plano de todos modos?")) return;
    document.getElementById("archivo-plano").click();
  });
  document.getElementById("archivo-plano").addEventListener("change", (ev) => {
    const archivo = ev.target.files[0];
    ev.target.value = "";
    if (!archivo) return;
    archivo.text().then((texto) => {
      abrir(texto, archivo.name);
      if (window.EditorPanelHojas) window.EditorPanelHojas.refrescar();
    }, (e) => mensaje("No se pudo leer el archivo: " + e.message, "error"));
  });
  document.getElementById("btn-copiar").addEventListener("click", () => {
    const texto = document.getElementById("texto-comando").textContent;
    const copiado = () => mensaje("Comando copiado.", "ok");
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(texto).then(copiado, () => seleccionarTexto());
    } else {
      seleccionarTexto();
    }
  });
  function seleccionarTexto() {
    const rango = document.createRange();
    rango.selectNodeContents(document.getElementById("texto-comando"));
    const sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(rango);
    mensaje("Seleccioné el comando: cópielo con Ctrl+C.", "");
  }

  window.addEventListener("beforeunload", (ev) => {
    if (!estado.cambios) return;
    ev.preventDefault();
    ev.returnValue = "";
  });

  // ---------------------------------------------------------------------------------------
  // Barra superior e inicio.
  // ---------------------------------------------------------------------------------------

  document.getElementById("btn-acercar").addEventListener("click", () => zoom(1.25));
  document.getElementById("btn-alejar").addEventListener("click", () => zoom(1 / 1.25));
  document.getElementById("btn-ajustar").addEventListener("click", ajustarVista);
  document.getElementById("paso").addEventListener("change", (ev) => {
    estado.paso = parseFloat(ev.target.value);
  });
  window.addEventListener("resize", ajustarVista);

  /**
   * Una carpeta de DXF nueva (cargada o vuelta a cargar): los bloques colocados de ese mismo
   * archivo con otro sha256 (el DXF cambió) pasan al DXF nuevo, con su tamaño actualizado.
   */
  function catalogoCambiado(catalogo) {
    if (!catalogo) return;
    const nuevo = dxfDe(catalogo);
    ultimoCatalogo = catalogo;
    let cambiados = 0;
    for (const c of estado.colocaciones) {
      if (!esBloque(c) && c.zona) { // exportada desde una zona: para «Volver a exportar zonas»
        const dz = c.zona.dxf;
        if (dz && dz !== nuevo && dz.archivo === nuevo.archivo && dz.sha256 !== nuevo.sha256) {
          if (nuevo.id === null) nuevo.id = dz.id;
          c.zona.dxf = nuevo;
          cambiados++;
        }
        continue;
      }
      const d = esBloque(c) ? c.bloque.dxf : null;
      if (!d || d === nuevo || d.archivo !== nuevo.archivo || d.sha256 === nuevo.sha256) continue;
      const b = catalogo.bloques.find((x) => x.handle === c.bloque.handle);
      if (nuevo.id === null) nuevo.id = d.id; // el plano sigue nombrándolo igual
      c.bloque.dxf = nuevo;
      c.original = null; // cambió su DXF: al guardar se escribe con los datos nuevos
      if (b && b.tamano_m) Object.assign(c.bloque, { tamano_m: b.tamano_m.slice(), caja_exacta: b.caja_exacta,
        sugerida: b.escala_sugerida });
      cambiados++;
    }
    if (cambiados) {
      marcarCambios();
      mensaje(cambiados + " bloque(s) o zona(s) del plano pasan al DXF que se volvió a cargar (cambió desde que " +
        "se colocaron). Las zonas ya exportadas se actualizan con «Volver a exportar zonas».", "aviso");
    }
    actualizar();
  }

  /**
   * Agrega al catálogo los detalles de paquetes exportados desde el editor (etapa 3), si no
   * están (por su manifiesto). Devuelve la entrada del catálogo de cada uno.
   */
  function registrarDetalles(detalles) {
    const salida = [];
    let nuevos = 0;
    for (const d of detalles || []) {
      let entrada = CATALOGO.find((x) => x.manifiesto === d.manifiesto);
      if (!entrada) {
        entrada = Object.assign({}, d, { id: L.idUnico(d.id, new Set(CATALOGO.map((x) => x.id))) });
        CATALOGO.push(entrada);
        nuevos++;
      }
      salida.push(entrada);
    }
    if (nuevos) pintarCatalogo();
    return salida;
  }

  /**
   * Un bloque exportado pasa a ser un detalle normal: su paquete, con la página donde la pone el
   * centro CAD (centro − desde_centro_mm). Si por redondeo se saliera del área, se acomoda.
   * Devuelve true si cambió algo.
   */
  function aplicarExportado(idPlano, resultado) {
    const i = estado.colocaciones.findIndex((c) => c.id === idPlano && (esBloque(c)
      ? (esZona(c) ? resultado.tipo === "zona" : c.bloque.handle === resultado.handle) && c.escala === resultado.escala
      : !!c.zona && resultado.tipo === "zona" && c.detalle.escala === resultado.escala)); // volver a exportar
    if (i < 0) return false; // se quitó o se cambió mientras se exportaba
    const c = estado.colocaciones[i];
    const [detalle] = registrarDetalles([resultado.detalle]);
    // El centro: el del borrador, o (volver a exportar) el de la página del detalle de hoy.
    const centroDe = esBloque(c) ? c.centro
      : [c.pos[0] + c.detalle.tamano_pagina_mm[0] / 2, c.pos[1] + c.detalle.tamano_pagina_mm[1] / 2];
    const pos = B.posicionExportada(centroDe, resultado.desde_centro_mm);
    const limitada = L.clampDetalle(pos, detalle, margenDe(c), ZONA) || pos;
    const nueva = { id: c.id, detalle, pos: limitada };
    if (typeof c.margen === "number") nueva.margen = c.margen; // volver a exportar: su margen
    if (c.etiqueta_escala === false) nueva.etiqueta_escala = false;
    if (c.ortofoto === true) nueva.ortofoto = true; // exportado: sigue con su ortofoto
    // Una zona exportada recuerda su zona (se guarda en el plano y se puede volver a exportar).
    if (esZona(c)) {
      nueva.zona = Object.assign({ nombre: c.bloque.nombre, tamano_m: c.bloque.tamano_m.slice(), dxf: c.bloque.dxf },
        c.bloque.zona);
    } else if (c.zona) {
      nueva.zona = c.zona;
    }
    estado.colocaciones[i] = nueva;
    marcarCambios();
    actualizar();
    return true;
  }

  /** La ortofoto del plano cambió (panel de la ortofoto): {archivo, …} o null para quitarla. */
  function fijarOrtofoto(o) {
    estado.ortofoto = o;
    marcarCambios();
    actualizar();
  }

  window.EditorUI = { agregarBloque, catalogoCambiado, refrescar: () => actualizar(),
    // Varias hojas (editor_panel_hojas.js): el plano como texto y objeto, abrir otro con su
    // nombre, si hay cambios, el rótulo y los valores automáticos (hoja, de, número de plano).
    textoPlano, abrirTexto: abrir, archivo: () => estado.archivo, hayCambios: () => !!estado.cambios,
    guardadoEn: (nombre) => { estado.archivo = nombre; estado.cambios = false; mostrarComando(nombre); },
    mensaje, definicionRotulo: () => DEFINICION_ROTULO, rotulo: () => R.serializar(estado.rotulo),
    quitarHojaYDe: () => {
      const H = window.EditorHojas;
      for (const [campo, tipo] of Object.entries(H.camposAutomaticos(DEFINICION_ROTULO))) {
        if (tipo !== "numero_siguiente") R.cambiar(estado.rotulo, campo, undefined);
      }
    },
    fijarAutomaticos: (valores) => {
      estado.automaticos = valores || {};
      panelRotulo.pintar();
      programarVistaPrevia();
    },
    colocaciones: () => estado.colocaciones, zona: () => ZONA, aplicarExportado, registrarDetalles,
    // Zonas borrador (Fase 10e): agregar desde el cuadro «Zonas del modelo», cambiarla al editarla,
    // y los nombres que ya usa el plano (para pedir el siguiente Zona_NN).
    agregarZona, actualizarZona, nombresEnUso: () => estado.colocaciones.map((c) => c.id),
    ortofoto: () => estado.ortofoto, fijarOrtofoto, cajasOrtofoto,
    marcadosOrtofoto: () => marcados().length, extendida, cuadriculas: () => ultimasCuadriculas,
    // Imagen de localización (y su escala): valores del rótulo que no edita el formulario.
    rotuloValor: (campo) => R.valor(estado.rotulo, campo),
    cambiarRotulo: (campo, valor) => {
      R.cambiar(estado.rotulo, campo, valor);
      marcarCambios();
      actualizar();
    } };

  // Para la verificación automática del reporte (no la usa la interfaz).
  window.EditorPrueba = { estado, agregar: (id) => agregar(CATALOGO.find((d) => d.id === id)),
    cambiarEscala: (id, n) => cambiarEscala(estado.colocaciones.find((c) => c.id === id), n),
    escribirEscala: (id, texto) => escribirEscala(estado.colocaciones.find((c) => c.id === id), texto),
    ajustarALaHoja: (id) => ajustarALaHoja(estado.colocaciones.find((c) => c.id === id)),
    moverCentro: (id, centro) => moverCentro(estado.colocaciones.find((c) => c.id === id), centro),
    usarOrtofoto: (id, si) => usarOrtofoto(estado.colocaciones.find((c) => c.id === id), si),
    mostrarEscala: (id, si) => mostrarEscala(estado.colocaciones.find((c) => c.id === id), si),
    seleccionar, caja: (id) => paginaDe(estado.colocaciones.find((c) => c.id === id)),
    previa: (id) => previaDe(estado.colocaciones.find((c) => c.id === id)),
    mover: (id, pos) => mover(estado.colocaciones.find((c) => c.id === id), pos),
    texto: textoPlano, advertencias: () => ultimasAdvertencias,
    moverRosa, mostrarRosa, restaurarRosa, abrir,
    rotulo: () => R.serializar(estado.rotulo), validacionRotulo: () => panelRotulo.validacion(),
    validacionNotas: () => panelNotas.validacion(), validacionConvenciones: () => panelConvenciones.validacion(),
    // 4.3f: dibuja la vista previa ya (sin esperar al cuadro) y devuelve lo que dibujó.
    vistaPrevia: () => {
      dibujarVistaPrevia();
      return { etiquetas: etiquetasActuales, activa: !!(casillaVistaPrevia && casillaVistaPrevia.checked) };
    },
    // Encuadra un rectángulo de papel [x0, y0, x1, y1] (mm), como si se acercara con la rueda.
    verPapel: (rect) => {
      const r = L.rectPapelAPantalla(rect, ESCALA);
      const caja = svg.getBoundingClientRect();
      const proporcion = caja.width / caja.height;
      let ancho = r.ancho;
      let alto = r.alto;
      if (ancho / alto > proporcion) alto = ancho / proporcion;
      else ancho = alto * proporcion;
      estado.vista = { x: r.x + r.ancho / 2 - ancho / 2, y: r.y + r.alto / 2 - alto / 2, ancho, alto };
      aplicarVista();
    },
    ajustar: ajustarVista, escala: ESCALA };

  if (CON_VISTA_PREVIA) {
    const diferencia = LR.diferenciaDeFuente(FUENTE_ROTULO);
    if (diferencia !== null && diferencia > 0.005) {
      mensaje("La vista previa del rótulo usa una «Arial» que mide distinto de la de componer (" +
        (diferencia * 100).toFixed(1).replace(".", ",") + " %): las posiciones son las de componer, pero las letras pueden verse algo distintas.", "aviso");
    }
  }
  pintarCatalogo();
  pintarRotulo();
  pintarDondeGuardar();
  ajustarVista();
  actualizar();
})();
