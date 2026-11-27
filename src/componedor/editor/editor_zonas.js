/*
 * Editor de planos — «Zonas del modelo» (Fase 10d): la lógica, sin pantalla. Funciona en el
 * navegador (window.EditorZonas) y en Node (module.exports), para probarla desde pytest.
 *
 * Coordenadas:
 *   - CAD: el Model Space del DXF, en unidades del dibujo (el marco único del trabajador).
 *   - px: los de la imagen de la vista previa, origen arriba a la izquierda, Y hacia abajo.
 *     La matriz `cad_a_px` del trabajador es [a, 0, 0, d, e, f] con a = −d:
 *     px = a·X + e, py = d·Y + f.
 *
 * Vista como en AutoCAD (ajuste de la 10d): la «cámara» es la ventana CAD que se ve. La rueda
 * acerca y aleja hacia el cursor (`zoomEnPunto`), arrastrar con la rueda la mueve (`desplazar`)
 * y la imagen actual se escala al instante; al parar se pide una vista nítida de la ventana si
 * la imagen que hay no la cubre o se ve pixelada (`necesitaVistaNitida`).
 *
 * La zona es un rectángulo CAD [xmin, ymin, xmax, ymax]. Su página en la hoja, a 1:N, mide
 * ancho·mm_por_unidad/N + 2·margen (igual que exportar_zona.pagina_de_zona en Python).
 *
 * Zonas borrador en la hoja (Fase 10e): una zona agregada a la hoja es una colocación como un
 * bloque sin exportar (c.bloque con `zona`), con su nombre fijo (Zona_01…, editable) y su
 * centro en el papel. «Exportar bloques y zonas» manda un /api/exportar/zona por cada una
 * (`pedidosZonas`), con el centro del borrador: el detalle queda donde estaba.
 *
 * Capas: modo "excluir" (el que se usa al empezar: todas marcadas, se exportan todas menos las
 * desmarcadas) o modo "solo" (se exportan solo las marcadas).
 */
(function (raiz, fabrica) {
  "use strict";
  const api = fabrica(raiz.EditorBloques || (typeof require === "function" ? require("./editor_bloques.js") : null));
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    raiz.EditorZonas = api;
  }
})(typeof self !== "undefined" ? self : this, function (B) {
  "use strict";

  const MIN_PX = 4; // px de PANTALLA: un rectángulo más chico es un clic, no una zona
  const MARGEN_ENCUADRE = 0.05; // «ver todo» y los grupos: 5 % de aire por lado
  const RESOLUCION_MIN = 0.75; // px de la imagen por px de pantalla por debajo: se ve pixelada
  const MODOS = ["excluir", "solo"];

  // ---------------------------------------------------------------------------------------
  // px ↔ CAD
  // ---------------------------------------------------------------------------------------

  function pxACad(m, px, py) {
    return [(px - m[4]) / m[0], (py - m[5]) / m[3]];
  }

  function cadAPx(m, x, y) {
    return [m[0] * x + m[4], m[3] * y + m[5]];
  }

  /** La caja CAD [x0, y0, x1, y1] en px: {x, y, ancho, alto} (para un <rect> del SVG). */
  function cajaAPx(m, caja) {
    const [ax, ay] = cadAPx(m, caja[0], caja[3]); // arriba a la izquierda
    const [bx, by] = cadAPx(m, caja[2], caja[1]); // abajo a la derecha
    return { x: Math.min(ax, bx), y: Math.min(ay, by), ancho: Math.abs(bx - ax), alto: Math.abs(by - ay) };
  }

  /**
   * El rectángulo arrastrado entre dos puntos CAD como zona normalizada, o null si en PANTALLA
   * midió menos de MIN_PX en algún sentido (fue un clic). `pantalla`: los dos puntos en px de
   * pantalla. Vale a cualquier zoom: los puntos ya vienen en coordenadas del dibujo.
   */
  function zonaDesdeArrastre(c1, c2, pantalla) {
    if (pantalla) {
      const [a, b] = pantalla;
      if (Math.abs(b[0] - a[0]) < MIN_PX || Math.abs(b[1] - a[1]) < MIN_PX) return null;
    }
    return redondear([Math.min(c1[0], c2[0]), Math.min(c1[1], c2[1]),
      Math.max(c1[0], c2[0]), Math.max(c1[1], c2[1])]);
  }

  // ---------------------------------------------------------------------------------------
  // La cámara (la ventana CAD que se ve)
  // ---------------------------------------------------------------------------------------

  /** La ventana con la proporción `aspecto` (ancho/alto) que contiene `caja`, centrada, con aire. */
  function encuadrar(caja, aspecto, margen) {
    const aire = margen === undefined ? MARGEN_ENCUADRE : margen;
    let w = (caja[2] - caja[0]) * (1 + 2 * aire);
    let h = (caja[3] - caja[1]) * (1 + 2 * aire);
    if (!(w > 0)) w = h > 0 ? h * aspecto : 1;
    if (!(h > 0)) h = w / aspecto;
    if (w / h < aspecto) w = h * aspecto;
    else h = w / aspecto;
    const cx = (caja[0] + caja[2]) / 2;
    const cy = (caja[1] + caja[3]) / 2;
    return [cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2];
  }

  /**
   * Zoom hacia un punto: el punto CAD `p` se queda donde está en la pantalla. factor < 1 acerca,
   * > 1 aleja (multiplica el tamaño de la ventana).
   */
  function zoomEnPunto(camara, p, factor) {
    return [p[0] - (p[0] - camara[0]) * factor, p[1] - (p[1] - camara[1]) * factor,
      p[0] + (camara[2] - p[0]) * factor, p[1] + (camara[3] - p[1]) * factor];
  }

  /** Mueve la ventana (dx, dy) en unidades del dibujo. */
  function desplazar(camara, dx, dy) {
    return [camara[0] + dx, camara[1] + dy, camara[2] + dx, camara[3] + dy];
  }

  /**
   * El factor de una vuelta de rueda: deltaY > 0 (hacia el usuario) aleja, < 0 acerca, como en
   * AutoCAD. Un «clic» de rueda (deltaY ±100) es ×1,25 o ÷1,25; limitado a [0,5; 2].
   */
  function factorRueda(deltaY) {
    return Math.min(2, Math.max(0.5, Math.pow(1.25, deltaY / 100)));
  }

  /** La caja CAD que representa una imagen (de su matriz y su tamaño en px). */
  function cajaDeImagen(m, px) {
    const a = pxACad(m, 0, px[1]);
    const b = pxACad(m, px[0], 0);
    return [a[0], a[1], b[0], b[1]];
  }

  /**
   * ¿Hace falta pedir otra vista para la ventana `ventana`, vista en `anchoPantalla` px? Sí si
   * la imagen actual no cubre la ventana (con lo que de verdad hay de dibujo: `limite`, la caja
   * de todo el Model Space, si se conoce) o si se ve pixelada (menos de RESOLUCION_MIN px de
   * imagen por px de pantalla).
   */
  function necesitaVistaNitida(m, px, ventana, anchoPantalla, limite) {
    const img = cajaDeImagen(m, px);
    const util = limite ? interseccion(ventana, limite) : ventana;
    if (!util) return false; // la ventana no tiene nada del dibujo: no hay nada que pedir
    const tol = (util[2] - util[0]) * 1e-3;
    const cubre = img[0] <= util[0] + tol && img[1] <= util[1] + tol &&
      img[2] >= util[2] - tol && img[3] >= util[3] - tol;
    const pxImagen = (ventana[2] - ventana[0]) * m[0]; // ancho de la ventana en px de la imagen
    return !cubre || pxImagen / anchoPantalla < RESOLUCION_MIN;
  }

  /** La intersección de dos cajas, o null si no se tocan. */
  function interseccion(a, b) {
    const c = [Math.max(a[0], b[0]), Math.max(a[1], b[1]), Math.min(a[2], b[2]), Math.min(a[3], b[3])];
    return c[0] < c[2] && c[1] < c[3] ? c : null;
  }

  /** A milésimas de unidad (1 mm en un dibujo en metros): números limpios en el plano y la caché. */
  function redondear(caja) {
    return caja.map((v) => Math.round(v * 1000) / 1000);
  }

  /**
   * El grupo (de la vista de todo el Model Space) bajo el punto px, o null: el más chico que lo
   * contiene; si ninguno, el más cercano a menos de `tolPx` px (en un Model Space con grupos a
   * cientos de km, cada grupo es un punto en la imagen: basta un clic cerca o en su etiqueta).
   */
  function grupoEnPunto(m, grupos, p, tolPx) {
    const [x, y] = pxACad(m, p[0], p[1]);
    const dentro = (grupos || []).filter((g) => g.caja[0] <= x && x <= g.caja[2] && g.caja[1] <= y && y <= g.caja[3]);
    if (dentro.length) {
      dentro.sort((a, b) => area(a.caja) - area(b.caja));
      return dentro[0];
    }
    let mejor = null;
    let distMejor = tolPx || 0;
    for (const g of grupos || []) {
      const c = cajaAPx(m, g.caja);
      const dx = Math.max(c.x - p[0], 0, p[0] - (c.x + c.ancho));
      const dy = Math.max(c.y - p[1], 0, p[1] - (c.y + c.alto));
      const d = Math.hypot(dx, dy);
      if (d <= distMejor) {
        mejor = g;
        distMejor = d;
      }
    }
    return mejor;
  }

  const area = (c) => (c[2] - c[0]) * (c[3] - c[1]);

  // ---------------------------------------------------------------------------------------
  // Tamaño en la hoja
  // ---------------------------------------------------------------------------------------

  /** Página [ancho, alto] mm de la zona a 1:N (igual que exportar_zona.pagina_de_zona). */
  function paginaZona(zona, mmPorUnidad, n, margen) {
    const k = mmPorUnidad / n;
    return [(zona[2] - zona[0]) * k + 2 * margen, (zona[3] - zona[1]) * k + 2 * margen];
  }

  /** Tamaño de la zona en metros [ancho, alto] (para la escala sugerida de EditorBloques). */
  function tamanoM(zona, mmPorUnidad) {
    return [(zona[2] - zona[0]) * mmPorUnidad / 1000, (zona[3] - zona[1]) * mmPorUnidad / 1000];
  }

  /** La primera escala normalizada con la que la página cabe en el área de dibujo, o null. */
  function escalaSugerida(zona, mmPorUnidad, margen, area) {
    return B.escalaSugerida(tamanoM(zona, mmPorUnidad), margen, area);
  }

  const mm = (v) => v.toFixed(1).replace(".", ",");

  /**
   * {pagina, dibujo, cabe, texto, aviso}: el tamaño en la hoja y si cabe en el área de dibujo
   * del A1 (la misma regla que el servidor: colocar.exceso_de_tamano).
   */
  function tamanoEnHoja(zona, mmPorUnidad, n, margen, area) {
    const pagina = paginaZona(zona, mmPorUnidad, n, margen);
    const dibujo = [pagina[0] - 2 * margen, pagina[1] - 2 * margen];
    const exceso = B.excesoDeTamano(pagina, area);
    const cabe = exceso[0] === 0 && exceso[1] === 0;
    const texto = "Dibujo " + mm(dibujo[0]) + " × " + mm(dibujo[1]) + " mm; página " + mm(pagina[0]) +
      " × " + mm(pagina[1]) + " mm (con márgenes de " + mm(margen) + " mm).";
    let aviso = null;
    if (!cabe) {
      const sugerida = escalaSugerida(zona, mmPorUnidad, margen, area);
      aviso = "No cabe en el área de dibujo del A1 (" + mm(area[2] - area[0]) + " × " + mm(area[3] - area[1]) +
        " mm): sobran " + mm(exceso[0]) + " × " + mm(exceso[1]) + " mm. " +
        (sugerida ? "Pruebe " + B.textoEscala(sugerida) + " o una zona más chica." : "Haga la zona más chica.");
    }
    return { pagina, dibujo, cabe, texto, aviso };
  }

  // ---------------------------------------------------------------------------------------
  // Capas
  // ---------------------------------------------------------------------------------------

  /** Las filas de capas: primero las que tienen algo en la vista (de más a menos), luego el resto. */
  function ordenarCapas(filas) {
    return (filas || []).slice().sort((a, b) => (b.entidades > 0) - (a.entidades > 0) ||
      b.entidades - a.entidades || a.nombre.localeCompare(b.nombre, "es"));
  }

  /** «apagada en el CAD», etc.: el exportador no dibuja esas capas (solo capas visibles). */
  const textoEstadoCad = (fila) => (fila.estado_cad ? fila.estado_cad + " en el CAD: no se dibuja" : null);

  /**
   * El filtro para el servidor: {capas} (modo «solo») o {excluir} (modo «excluir»), a partir de
   * las capas desmarcadas (Set de nombres) y de todas las capas del DXF (nombres).
   * {error} si en modo «solo» no hay ninguna marcada.
   */
  function filtroCapas(modo, todas, desmarcadas) {
    if (!MODOS.includes(modo)) return { error: "Modo de capas desconocido." };
    const fuera = todas.filter((c) => desmarcadas.has(c));
    if (modo === "excluir") return { excluir: fuera.length ? fuera : null, capas: null };
    const marcadas = todas.filter((c) => !desmarcadas.has(c));
    if (!marcadas.length) return { error: "Marque al menos una capa (modo «solo las marcadas»)." };
    return { capas: marcadas, excluir: null };
  }

  /** Texto corto del filtro: «todas las capas», «todas menos 3», «solo 2 capas». */
  function textoFiltro(f) {
    if (f.error) return f.error;
    if (f.capas) return "solo " + f.capas.length + (f.capas.length === 1 ? " capa" : " capas");
    if (f.excluir) return "todas las capas menos " + f.excluir.length;
    return "todas las capas";
  }

  // ---------------------------------------------------------------------------------------
  // Pedidos al servidor
  // ---------------------------------------------------------------------------------------

  /** Cuerpo de POST /api/previa/zona. Sin zona ni vista: todo el Model Space. */
  function cuerpoPrevia(opciones) {
    const o = opciones || {};
    const cuerpo = {};
    if (o.zona) cuerpo.zona = o.zona;
    if (o.vista) cuerpo.vista = o.vista;
    if (o.filtro && o.filtro.capas) cuerpo.capas = o.filtro.capas;
    if (o.filtro && o.filtro.excluir) cuerpo.excluir = o.filtro.excluir;
    if (o.escala) cuerpo.escala = o.escala;
    if (o.estilo) cuerpo.estilo = o.estilo;
    return cuerpo;
  }

  /** Clave de la caché de vistas previas del editor (el mismo pedido da la misma imagen). */
  const clavePrevia = (cuerpo) => JSON.stringify(cuerpo);

  // ---------------------------------------------------------------------------------------
  // La escala del dibujo: los textos «ESC 1:N» de la zona (orden `texts`, protocolo 1.3)
  // ---------------------------------------------------------------------------------------

  const etiquetaEscala = (c) => (c.eje ? c.eje + " " : "") + B.textoEscala(c.n);

  /**
   * Qué dicen los textos de la zona sobre su escala. activo: la respuesta de /api/textos/zona
   * con el filtro de capas que se exporta; todo: la misma sin filtro (o null si no hay filtro).
   * {estado: "una" | "varias" | "ninguna", propuesta: {n, fuente} | null,
   *  candidatos: [{etiqueta, n, eje, veces, fuente}], excluidas: [{etiqueta, n, capa, fuente}]}.
   * "una": una sola escala sin eje (se pone sola). "varias": varias, o con ejes H/V (se elige).
   * excluidas: escalas que solo están en capas que no se exportan (se avisan; no se usan solas).
   */
  function analizarEscalas(activo, todo) {
    const candidatos = ((activo && activo.candidatos) || []).map((c) => ({
      etiqueta: etiquetaEscala(c), n: c.n, eje: c.eje, veces: c.veces, fuente: (c.fuentes || [])[0] || null }));
    const vistas = new Set(candidatos.map((c) => c.etiqueta));
    const excluidas = ((todo && todo.candidatos) || []).filter((c) => !vistas.has(etiquetaEscala(c))).map((c) => {
      const fuente = (c.fuentes || [])[0] || null;
      return { etiqueta: etiquetaEscala(c), n: c.n, capa: fuente ? fuente.capa : null, fuente };
    });
    const propuesta = activo && activo.propuesta ? { n: activo.propuesta, fuente: candidatos[0] ? candidatos[0].fuente : null } : null;
    return { estado: propuesta ? "una" : candidatos.length ? "varias" : "ninguna", propuesta, candidatos, excluidas };
  }

  /** Una línea del texto de origen, para mostrarlo («SECCIÓN-PEDESTAL 0.40 X 0.40 · ESC-1:10»). */
  const textoFuente = (f) => (f && f.texto ? f.texto.replace(/\s*\n\s*/g, " · ").slice(0, 90) : "");

  /**
   * El aviso ámbar si la zona se exporta a otra escala que la de su dibujo, o null. Los textos
   * salen escalados: dibujo 1:20 a 1:10 → «al doble de su tamaño».
   */
  function avisoEscala(nExporta, nDibujo) {
    if (!(nExporta > 0) || !(nDibujo > 0) || Math.abs(nExporta - nDibujo) < 1e-9) return null;
    const f = nDibujo / nExporta;
    const tamano = Math.abs(f - 2) < 1e-9 ? "al doble de su tamaño" : Math.abs(f - 0.5) < 1e-9 ? "a la mitad de su tamaño"
      : "a " + (Math.round(f * 100) / 100).toString().replace(".", ",") + " veces su tamaño";
    return "El dibujo está a " + B.textoEscala(nDibujo) + " y se exportará a " + B.textoEscala(nExporta) +
      ": los textos saldrán " + tamano + ".";
  }

  // ---------------------------------------------------------------------------------------
  // Zonas borrador en la hoja (Fase 10e)
  // ---------------------------------------------------------------------------------------

  const MAX_NOMBRE = 40; // igual que exportar_zona.MAX_NOMBRE

  /**
   * El nombre como lo dejará el servidor (nombres_paquete.limpiar): sin acentos y solo A–Z,
   * a–z, 0–9, «.», «-», «_» (lo demás, «_»), sin puntos al principio. {nombre} o {error}.
   */
  function limpiarNombre(texto) {
    const sinTildes = String(texto || "").trim().normalize("NFKD").replace(/[\u0300-\u036f]/g, "")
      .replace(/[^\x00-\x7f]/g, "");
    const limpio = sinTildes.replace(/[^A-Za-z0-9._-]/g, "_").replace(/^\.+/, "");
    if (!limpio.replace(/_/g, "")) return { error: "El nombre necesita al menos una letra o un número." };
    if (limpio.length > MAX_NOMBRE) return { error: "El nombre es muy largo (como mucho " + MAX_NOMBRE + " caracteres)." };
    return { nombre: limpio };
  }

  const esZona = (c) => !!(c && c.bloque && c.bloque.zona);
  const esZonaExportada = (c) => !!(c && !c.bloque && c.zona && c.detalle);

  /**
   * Lo que hace falta para exportar una zona del plano: {dxf, tamano_m, nombre, zona: {rect, capas,
   * excluir}, escala, centro}. Un borrador: su escala y su centro. Una zona ya exportada (Fase
   * 10e4, «Volver a exportar zonas»): la escala de su detalle y el centro de su página de hoy.
   */
  function datosParaExportar(c) {
    if (esZona(c)) {
      return { dxf: c.bloque.dxf, tamano_m: c.bloque.tamano_m, nombre: c.bloque.nombre, zona: c.bloque.zona,
        escala: c.escala, centro: c.centro };
    }
    const t = c.detalle.tamano_pagina_mm;
    return { dxf: c.zona.dxf, tamano_m: c.zona.tamano_m, nombre: c.zona.nombre, zona: c.zona,
      escala: c.detalle.escala, centro: [c.pos[0] + t[0] / 2, c.pos[1] + t[1] / 2] };
  }

  /**
   * Los pedidos de /api/exportar/zona de las zonas borrador del plano: {pedidos: [{id, cuerpo}],
   * omitidos: [{id, motivo}]}. `todas`: también las zonas ya exportadas («Volver a exportar
   * zonas», Fase 10e4). Las mismas reglas que los bloques (editor_bloques.pedidosExportar):
   * el DXF cargado y su sesión, que quepa y no se salga del área de dibujo. El cuerpo lleva el
   * centro del borrador (centro_mm): el detalle exportado queda donde estaba.
   */
  function pedidosZonas(colocaciones, catalogo, areaDibujo, estilo, todas) {
    const pedidos = [];
    const omitidos = [];
    for (const c of colocaciones) {
      if (!esZona(c) && !(todas && esZonaExportada(c))) continue;
      const b = datosParaExportar(c);
      const pagina = B.paginaMm(b.tamano_m, b.escala, B.margenHoja()); // lo que se verá en la hoja
      const e = B.estadoCaja(b.centro, pagina, areaDibujo);
      let motivo = null;
      if (!catalogo) motivo = "cargue «" + b.dxf.nombre + "» con «Cargar DXF»";
      else if (catalogo.dxf.sha256 !== b.dxf.sha256) {
        motivo = catalogo.dxf.nombre === b.dxf.nombre
          ? "el DXF cambió desde que se dibujó la zona: «Volver a cargar» primero"
          : "es de «" + b.dxf.nombre + "» y el cargado es «" + catalogo.dxf.nombre + "»";
      } else if (!catalogo.sesion_activa) motivo = "vuelva a cargar el DXF («Volver a cargar»)";
      else if (!e.cabe) motivo = "no cabe a " + B.textoEscala(b.escala) + ": cambie la escala";
      else if (!e.dentro) motivo = "se sale del área de dibujo: muévala";
      if (motivo) {
        omitidos.push({ id: c.id, motivo });
        continue;
      }
      const z = b.zona;
      const cuerpo = { zona: z.rect.slice(), escala: Math.round(b.escala), nombre: b.nombre,
        centro_mm: [Math.round(b.centro[0] * 100) / 100, Math.round(b.centro[1] * 100) / 100] };
      if (z.capas) cuerpo.capas = z.capas.slice();
      if (z.excluir) cuerpo.excluir = z.excluir.slice();
      if (estilo) cuerpo.estilo = estilo;
      pedidos.push({ id: c.id, cuerpo });
    }
    return { pedidos, omitidos };
  }

  /** Dos zonas del plano con el mismo nombre y escala serían el MISMO paquete: [[id, id], …]. */
  function zonasRepetidas(colocaciones) {
    const vistas = new Map();
    const repetidas = [];
    for (const c of colocaciones) {
      if (!esZona(c)) continue;
      const k = c.bloque.nombre.toLowerCase() + "|" + c.escala;
      if (vistas.has(k)) repetidas.push([vistas.get(k), c.id]);
      else vistas.set(k, c.id);
    }
    return repetidas;
  }

  // ---------------------------------------------------------------------------------------
  // Textos
  // ---------------------------------------------------------------------------------------

  const miles = (n) => String(n).replace(/\B(?=(\d{3})+(?!\d))/g, " ");

  function textoGrupo(g) {
    return "Grupo " + g.numero + " · " + miles(g.entidades) + " entidades";
  }

  /** «45 s», «1 min 05 s». */
  function textoTranscurrido(segundos) {
    const s = Math.max(0, Math.floor(segundos));
    if (s < 60) return s + " s";
    return Math.floor(s / 60) + " min " + String(s % 60).padStart(2, "0") + " s";
  }

  /** La zona en texto: esquinas y tamaño en unidades del dibujo. */
  function textoZona(zona, unidades) {
    const u = unidades ? " " + unidades : "";
    const n = (v) => v.toFixed(3).replace(".", ",");
    return "X " + n(zona[0]) + " a " + n(zona[2]) + ", Y " + n(zona[1]) + " a " + n(zona[3]) +
      " (" + n(zona[2] - zona[0]) + " × " + n(zona[3] - zona[1]) + u + ")";
  }

  /**
   * «Exportar todas las hojas» (8c): la cola, hoja por hoja (bloques y luego zonas), y lo que no se
   * pide, cada uno con su hoja. hojas: [{indice, nombre, colocaciones}]. {cola: [{hoja, nombreHoja,
   * id, bloque | zona}], omitidos: [{hoja, nombreHoja, id, motivo}]}. soloZonas: «Volver a exportar
   * zonas de todas las hojas» (todas las zonas, borradores y exportadas).
   */
  function colaDeHojas(hojas, catalogo, area, estilo, soloZonas) {
    const cola = [];
    const omitidos = [];
    for (const h of hojas) {
      const bloques = soloZonas ? { pedidos: [], omitidos: [] } : B.pedidosExportar(h.colocaciones, catalogo, area);
      const zonas = pedidosZonas(h.colocaciones, catalogo, area, estilo, !!soloZonas);
      const de = { hoja: h.indice, nombreHoja: h.nombre };
      for (const o of bloques.omitidos.concat(zonas.omitidos)) omitidos.push(Object.assign({}, de, { id: o.id, motivo: o.motivo }));
      for (const p of bloques.pedidos) cola.push(Object.assign({}, de, { id: p.id, bloque: p }));
      for (const p of zonas.pedidos) cola.push(Object.assign({}, de, { id: p.id, zona: p.cuerpo }));
    }
    return { cola, omitidos };
  }

  return {
    colaDeHojas, MIN_PX, RESOLUCION_MIN, MODOS, pxACad, cadAPx, cajaAPx, zonaDesdeArrastre, redondear,
    encuadrar, zoomEnPunto, desplazar, factorRueda, cajaDeImagen, necesitaVistaNitida, interseccion,
    grupoEnPunto, paginaZona, tamanoM, escalaSugerida, tamanoEnHoja, ordenarCapas, textoEstadoCad,
    filtroCapas, textoFiltro, cuerpoPrevia, clavePrevia, limpiarNombre, esZona, esZonaExportada,
    pedidosZonas, zonasRepetidas, analizarEscalas, avisoEscala, textoFuente, etiquetaEscala, textoGrupo, textoTranscurrido,
    textoZona };
});
