/*
 * Editor de planos — bloques de un DXF colocados en la hoja SIN exportar todavía (etapa 2).
 * Lógica pura (sin pantalla): funciona en el navegador (window.EditorBloques) y en Node
 * (module.exports), para probarla desde pytest contra Python.
 *
 * Un bloque colocado es una CAJA EXACTA: la página que tendrá el paquete al exportarlo a 1:N,
 * con la fórmula del contrato del trabajador (igual que bloques_dxf.pagina_mm en Python):
 *
 *     página_mm = tamaño_m × 1000 ÷ N + 2 × margen_mm      (por eje)
 *
 * Se guarda su CENTRO en la hoja (centro_mm, mm de papel, Y hacia arriba). Al cambiar la
 * escala el centro no se mueve: solo cambia el tamaño de la caja (y de la vista previa).
 *
 * La vista previa es el PNG del trabajador. El contrato garantiza un solo marco para la caja
 * de `load`, la del PNG y la del manifiesto, y `cad_to_px` sin giro con a = −d. Así cada punto
 * CAD (X, Y) va al papel con la misma fórmula que la caja:
 *
 *     papel = P + k·(X − Cx, Y − Cy),   k = mm por unidad ÷ N
 *     (C: centro de la caja de load; P: centro de la caja en la hoja)
 *
 * y las esquinas del PNG, de píxel a CAD: X = (px − e) ÷ a, Y = (py − f) ÷ d. Cambiar la escala
 * solo cambia k: no hace falta otra vista previa.
 */
(function (raiz, fabrica) {
  "use strict";
  const api = fabrica();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    raiz.EditorBloques = api;
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const EPS_MM = 1e-6; // igual que formato.EPS_MM
  // Escalas normalizadas de ingeniería. Igual que inventario.ESCALAS_ESTANDAR (una prueba lo
  // compara). Una escala escrita a mano puede no estar aquí: entero de 1 a ESCALA_MAXIMA.
  const ESCALAS = [5, 10, 20, 25, 50, 75, 100, 200, 250, 500, 750, 1000, 1500, 2000, 2500,
    3000, 4000, 5000, 7500, 10000];
  const ESCALA_MAXIMA = 100000; // igual que inventario.ESCALA_MAXIMA

  // ---------------------------------------------------------------------------------------
  // Tamaño, escala y si cabe (mismas reglas que Python).
  // ---------------------------------------------------------------------------------------

  /** Igual que bloques_dxf.pagina_mm. */
  function paginaMm(tamanoM, n, margen) {
    return [tamanoM[0] * 1000 / n + 2 * margen, tamanoM[1] * 1000 / n + 2 * margen];
  }

  /** Igual que colocar.exceso_de_tamano: cuánto sobra [ancho, alto]; [0, 0] si cabe. */
  function excesoDeTamano(tamano, zona) {
    const dx = tamano[0] - (zona[2] - zona[0]);
    const dy = tamano[1] - (zona[3] - zona[1]);
    return [dx > EPS_MM ? dx : 0, dy > EPS_MM ? dy : 0];
  }

  const cabePorTamano = (tamano, zona) => {
    const e = excesoDeTamano(tamano, zona);
    return e[0] === 0 && e[1] === 0;
  };

  /** Igual que bloques_dxf.escala_sugerida: la primera estándar con la que cabe, o null. */
  function escalaSugerida(tamanoM, margen, zona, escalas) {
    for (const n of escalas || ESCALAS) {
      if (cabePorTamano(paginaMm(tamanoM, n, margen), zona)) return n;
    }
    return null;
  }

  /**
   * La escala vecina en la lista. paso +1 = «+»: el dibujo más GRANDE en el papel (N menor,
   * de 1:100 a 1:50); paso −1 = «−»: más chico (N mayor). En los extremos, la misma. Si n no
   * está en la lista, la más cercana en esa dirección.
   */
  function escalaVecina(n, paso, escalas) {
    const lista = (escalas || ESCALAS).slice().sort((a, b) => a - b);
    if (paso > 0) {
      const menores = lista.filter((x) => x < n);
      return menores.length ? menores[menores.length - 1] : n;
    }
    const mayores = lista.filter((x) => x > n);
    return mayores.length ? mayores[0] : n;
  }

  const textoEscala = (n) => "1:" + (Number.isInteger(n) ? n : String(n));

  /** "1:2000" → 2000; null si no es «1:N» con N entero de 1 a 100000 (igual que
   *  plano_dxf.leer_escala). */
  function leerEscala(texto) {
    const m = typeof texto === "string" ? /^1:(\d+)$/.exec(texto) : null;
    const n = m ? parseInt(m[1], 10) : 0;
    return n >= 1 && n <= ESCALA_MAXIMA ? n : null;
  }

  const esNormalizada = (n, escalas) => (escalas || ESCALAS).includes(n);

  /**
   * Lo que el usuario escribe en «Escala»: «1:3500», «3500» o «1 : 3500». {n, aviso} o {error}.
   * N entero de 1 a 100000; si no es normalizada, se permite con el aviso «escala no normalizada».
   */
  function leerEscalaEscrita(texto, escalas) {
    const limpio = String(texto === undefined || texto === null ? "" : texto).replace(/\s+/g, "");
    const m = /^(?:1:)?(\d+)$/.exec(limpio);
    const n = m ? parseInt(m[1], 10) : NaN;
    if (!(n >= 1 && n <= ESCALA_MAXIMA)) {
      return { error: "Escala no válida: escriba 1:N o N, con N entero de 1 a " + ESCALA_MAXIMA +
        " (por ejemplo 1:3500)." };
    }
    return { n, aviso: esNormalizada(n, escalas) ? null : "escala no normalizada" };
  }

  /**
   * «Ajustar a la hoja»: la escala EXACTA más grande (N entero más chico) con la que la página
   * cabe en la zona, aunque no sea normalizada. null si ni a 1:100000 cabe o el margen no deja
   * lugar.
   */
  function escalaAjustada(tamanoM, margen, zona) {
    const libre = [zona[2] - zona[0] - 2 * margen, zona[3] - zona[1] - 2 * margen];
    if (libre[0] <= 0 || libre[1] <= 0) return null;
    let n = Math.max(1, Math.ceil(Math.max(tamanoM[0] * 1000 / libre[0], tamanoM[1] * 1000 / libre[1]) - 1e-9));
    while (n <= ESCALA_MAXIMA && !cabePorTamano(paginaMm(tamanoM, n, margen), zona)) n++; // por redondeo
    return n <= ESCALA_MAXIMA ? n : null;
  }

  // ---------------------------------------------------------------------------------------
  // La caja en la hoja: centro fijo.
  // ---------------------------------------------------------------------------------------

  /** Página [x0, y0, x1, y1] centrada en `centro`. */
  function rectCentrado(centro, pagina) {
    return [centro[0] - pagina[0] / 2, centro[1] - pagina[1] / 2,
      centro[0] + pagina[0] / 2, centro[1] + pagina[1] / 2];
  }

  /** El dibujo dentro de la página: la página sin el margen (la matriz centra el dibujo). */
  function rectDibujo(centro, pagina, margen) {
    const r = rectCentrado(centro, pagina);
    return [r[0] + margen, r[1] + margen, r[2] - margen, r[3] - margen];
  }

  /**
   * El centro al MOVER la caja: en cada eje, si la página cabe, se limita para que quede
   * completa dentro de la zona (la regla de componer); si no cabe, el centro queda dentro de
   * la zona (la caja se ve en rojo).
   */
  function centroLimitado(centro, pagina, zona) {
    const eje = (c, tam, z0, z1) => {
      if (tam <= z1 - z0 + EPS_MM) return Math.min(Math.max(c, z0 + tam / 2), z1 - tam / 2);
      return Math.min(Math.max(c, z0), z1);
    };
    return [eje(centro[0], pagina[0], zona[0], zona[2]), eje(centro[1], pagina[1], zona[1], zona[3])];
  }

  /** Centro del área (donde aparece un bloque nuevo). */
  const centroZona = (zona) => [(zona[0] + zona[2]) / 2, (zona[1] + zona[3]) / 2];

  /**
   * Estado de la caja: {cabe, dentro, exceso: [dx, dy]} — `cabe` por tamaño (si no, ninguna
   * posición sirve: hay que cambiar la escala) y `dentro` si la página está completa en la zona.
   */
  function estadoCaja(centro, pagina, zona) {
    const exceso = excesoDeTamano(pagina, zona);
    const r = rectCentrado(centro, pagina);
    const dentro = zona[0] - r[0] <= EPS_MM && zona[1] - r[1] <= EPS_MM &&
      r[2] - zona[2] <= EPS_MM && r[3] - zona[3] <= EPS_MM;
    return { cabe: exceso[0] === 0 && exceso[1] === 0, dentro, exceso };
  }

  /**
   * Escala al arrastrar el tirador (una esquina) con el centro fijo: de la lista, la que deja
   * la esquina de la página más cerca del puntero.
   */
  function escalaPorTirador(centro, punto, tamanoM, margen, escalas) {
    const dx = Math.abs(punto[0] - centro[0]);
    const dy = Math.abs(punto[1] - centro[1]);
    let mejor = null;
    let distancia = Infinity;
    for (const n of escalas || ESCALAS) {
      const p = paginaMm(tamanoM, n, margen);
      const d = Math.hypot(dx - p[0] / 2, dy - p[1] / 2);
      if (d < distancia - 1e-9) {
        distancia = d;
        mejor = n;
      }
    }
    return mejor;
  }

  // ---------------------------------------------------------------------------------------
  // Vista previa: del PNG al papel.
  // ---------------------------------------------------------------------------------------

  /** mm de papel por unidad CAD a 1:N. */
  const mmPorUnidadCad = (mmPorUnidad, n) => mmPorUnidad / n;

  const centroCaja = (caja) => [(caja.min[0] + caja.max[0]) / 2, (caja.min[1] + caja.max[1]) / 2];

  /** Un punto CAD en la hoja (mm de papel). */
  function cadAPapel(punto, centroCad, centro, k) {
    return [centro[0] + k * (punto[0] - centroCad[0]), centro[1] + k * (punto[1] - centroCad[1])];
  }

  /** Un punto de la imagen (px, Y hacia abajo) en CAD, con cad_to_px = [a, 0, 0, d, e, f]. */
  function pxACad(px, py, m) {
    return [(px - m[4]) / m[0], (py - m[5]) / m[3]];
  }

  /**
   * Rectángulo [x0, y0, x1, y1] (mm de papel) donde va el PNG entero: sus esquinas (0, 0) y
   * (ancho, alto) en píxeles (el píxel (0, 0) ocupa de 0 a 1). previa: {px, cad_a_px}.
   */
  function imagenEnPapel(previa, centroCad, centro, k) {
    const arribaIzq = cadAPapel(pxACad(0, 0, previa.cad_a_px), centroCad, centro, k);
    const abajoDer = cadAPapel(pxACad(previa.px[0], previa.px[1], previa.cad_a_px), centroCad, centro, k);
    return [arribaIzq[0], abajoDer[1], abajoDer[0], arribaIzq[1]];
  }

  // ---------------------------------------------------------------------------------------
  // plano.json versión 3 (plano_dxf.py en Python).
  // ---------------------------------------------------------------------------------------

  const r2 = (v) => Math.round(v * 100) / 100;
  const esObjeto = (v) => v !== null && typeof v === "object" && !Array.isArray(v);
  const esNumero = (v) => typeof v === "number" && isFinite(v);
  const CLAVES_DXF = ["archivo", "bytes", "id", "margen_mm", "sha256", "unidades"];
  const CLAVES_PENDIENTE = ["centro_mm", "etiqueta_escala", "id", "origen"];
  const CLAVES_ORIGEN = ["bloque", "caja_exacta", "dxf", "escala", "handle", "ocurrencia", "tamano_m"];

  function desconocida(objeto, validas) {
    return Object.keys(objeto).find((k) => !validas.includes(k));
  }

  /** La entrada "dxf" de un DXF cargado (sin id: se pone al guardar). catalogo: la carpeta. */
  function entradaDxf(catalogo) {
    return {
      id: null,
      archivo: catalogo.dxf.archivo_plano || catalogo.dxf.ruta || catalogo.dxf.nombre,
      sha256: catalogo.dxf.sha256,
      bytes: typeof catalogo.dxf.bytes === "number" ? catalogo.dxf.bytes : null,
      unidades: catalogo.unidades ? catalogo.unidades.nombre : null,
      margen_mm: catalogo.margen_mm,
      nombre: catalogo.dxf.nombre,
    };
  }

  /** Nombre del archivo de una ruta del plano (con / o \). */
  const nombreArchivo = (ruta) => String(ruta).split(/[\\/]/).pop();

  /** "dxf": [...] de un plano → Map(id → entrada). Problemas en `errores`. */
  function leerListaDxf(lista, errores) {
    const dxfs = new Map();
    if (!Array.isArray(lista)) {
      errores.push("dxf: se esperaba una lista [{\"id\", \"archivo\", \"sha256\", ...}].");
      return dxfs;
    }
    lista.forEach((d, i) => {
      const donde = "dxf[" + i + "]";
      if (!esObjeto(d)) return errores.push(donde + ": se esperaba un objeto {...}.");
      const otra = desconocida(d, CLAVES_DXF);
      if (otra) return errores.push(donde + "." + otra + ": campo no reconocido.");
      if (typeof d.id !== "string" || !d.id.trim()) return errores.push(donde + ".id: se esperaba un texto no vacío.");
      if (dxfs.has(d.id)) return errores.push(donde + ".id: '" + d.id + "' está repetido.");
      if (typeof d.archivo !== "string" || !d.archivo.trim()) return errores.push(donde + ".archivo: se esperaba la ruta del DXF.");
      if (typeof d.sha256 !== "string" || !/^[0-9a-f]{64}$/.test(d.sha256)) {
        return errores.push(donde + ".sha256: se esperaba el SHA-256 del DXF (64 caracteres hexadecimales).");
      }
      if (!esNumero(d.margen_mm) || d.margen_mm < 0) return errores.push(donde + ".margen_mm: se esperaba un número ≥ 0.");
      dxfs.set(d.id, { id: d.id, archivo: d.archivo, sha256: d.sha256,
        bytes: typeof d.bytes === "number" ? d.bytes : null,
        unidades: typeof d.unidades === "string" ? d.unidades : null,
        margen_mm: d.margen_mm, nombre: nombreArchivo(d.archivo) });
    });
    return dxfs;
  }

  /**
   * Un detalle pendiente del plano → {id, bloque, escala, centro, etiqueta_escala} (bloque:
   * los datos de "origen" más su DXF), o null con el problema en `errores`.
   */
  function leerPendiente(item, donde, dxfs, errores) {
    const otra = desconocida(item, CLAVES_PENDIENTE);
    if (otra) return errores.push(donde + "." + otra + ": campo no reconocido en un bloque sin exportar."), null;
    const o = item.origen;
    if (!esObjeto(o)) return errores.push(donde + ".origen: se esperaba un objeto."), null;
    const otraO = desconocida(o, CLAVES_ORIGEN);
    if (otraO) return errores.push(donde + ".origen." + otraO + ": campo no reconocido."), null;
    const dxf = dxfs.get(o.dxf);
    if (!dxf) return errores.push(donde + ".origen.dxf: '" + o.dxf + "' no está en la lista \"dxf\" del plano."), null;
    if (typeof o.bloque !== "string" || !o.bloque) return errores.push(donde + ".origen.bloque: se esperaba el nombre del bloque."), null;
    if (typeof o.handle !== "string" || !/^[0-9A-F]+$/.test(o.handle)) {
      return errores.push(donde + ".origen.handle: se esperaba el handle (hexadecimal en mayúsculas)."), null;
    }
    if (!Number.isInteger(o.ocurrencia) || o.ocurrencia < 1) return errores.push(donde + ".origen.ocurrencia: se esperaba un entero ≥ 1."), null;
    const n = leerEscala(o.escala);
    if (!n) return errores.push(donde + ".origen.escala: se esperaba «1:N»."), null;
    const t = o.tamano_m;
    if (!Array.isArray(t) || t.length !== 2 || !t.every((v) => esNumero(v) && v >= 0)) {
      return errores.push(donde + ".origen.tamano_m: se esperaba [ancho, alto] en m."), null;
    }
    if (o.caja_exacta !== undefined && typeof o.caja_exacta !== "boolean") {
      return errores.push(donde + ".origen.caja_exacta: se esperaba true o false."), null;
    }
    const c = item.centro_mm;
    if (!Array.isArray(c) || c.length !== 2 || !c.every(esNumero)) {
      return errores.push(donde + ".centro_mm: se esperaba [x, y] con 2 números en mm."), null;
    }
    if (item.etiqueta_escala !== undefined && typeof item.etiqueta_escala !== "boolean") {
      return errores.push(donde + ".etiqueta_escala: se esperaba true o false."), null;
    }
    return {
      bloque: { dxf, nombre: o.bloque, handle: o.handle, ocurrencia: o.ocurrencia,
        tamano_m: t.slice(), caja_exacta: o.caja_exacta !== false,
        // Lo que solo sabe la carpeta del DXF cargado (para la vista previa).
        ref: null, caja_cad: null, mm_por_unidad: null, sugerida: null },
      escala: n,
      centro: c.slice(),
      etiqueta_escala: item.etiqueta_escala,
    };
  }

  /**
   * Los ids de los DXF para guardar: los que ya traían (plano abierto) se conservan; los
   * nuevos reciben d1, d2… (el primero libre). Mismo sha256 = mismo DXF.
   */
  function asignarIdsDxf(entradas) {
    const porSha = new Map();
    const usados = new Set(entradas.filter((d) => d.id).map((d) => d.id));
    for (const d of entradas) if (d.id && !porSha.has(d.sha256)) porSha.set(d.sha256, d.id);
    let n = 1;
    for (const d of entradas) {
      if (d.id) continue;
      if (!porSha.has(d.sha256)) {
        while (usados.has("d" + n)) n++;
        porSha.set(d.sha256, "d" + n);
        usados.add("d" + n);
      }
      d.id = porSha.get(d.sha256);
    }
    return porSha;
  }

  /** La lista "dxf" del plano (una entrada por id, en el orden en que aparecen). */
  function listaDxf(entradas) {
    const vistos = new Map();
    for (const d of entradas) {
      if (vistos.has(d.id)) continue;
      const e = { id: d.id, archivo: d.archivo, sha256: d.sha256 };
      if (d.bytes !== null && d.bytes !== undefined) e.bytes = d.bytes;
      if (d.unidades) e.unidades = d.unidades;
      e.margen_mm = d.margen_mm;
      vistos.set(d.id, e);
    }
    return [...vistos.values()];
  }

  /** La entrada pendiente de un bloque colocado (id del DXF ya asignado). */
  function pendienteParaGuardar(c) {
    const b = c.bloque;
    const d = {
      id: c.id,
      origen: { dxf: b.dxf.id, bloque: b.nombre, handle: b.handle, ocurrencia: b.ocurrencia,
        escala: textoEscala(c.escala), tamano_m: b.tamano_m.slice(), caja_exacta: b.caja_exacta },
      centro_mm: [r2(c.centro[0]), r2(c.centro[1])],
    };
    if (c.etiqueta_escala === false) d.etiqueta_escala = false;
    return d;
  }

  // ---------------------------------------------------------------------------------------
  // Exportar (etapa 3).
  // ---------------------------------------------------------------------------------------

  /**
   * Qué bloques sin exportar del plano se pueden pedir al servidor con la carpeta cargada:
   * {pedidos: [{id, handle, sha256, escala, centro_mm}], omitidos: [{id, motivo}]}. No se
   * piden los que no caben o se salen del área, ni los de otro DXF (u otra versión del mismo).
   */
  function pedidosExportar(colocaciones, catalogo, zona) {
    const pedidos = [];
    const omitidos = [];
    for (const c of colocaciones) {
      if (!c.bloque) continue;
      const b = c.bloque;
      const pagina = paginaMm(b.tamano_m, c.escala, b.dxf.margen_mm);
      const e = estadoCaja(c.centro, pagina, zona);
      let motivo = null;
      if (!catalogo) motivo = "cargue «" + b.dxf.nombre + "» con «Cargar DXF»";
      else if (catalogo.dxf.sha256 !== b.dxf.sha256) {
        motivo = catalogo.dxf.nombre === b.dxf.nombre
          ? "el DXF cambió desde que se colocó: «Volver a cargar» primero"
          : "es de «" + b.dxf.nombre + "» y el cargado es «" + catalogo.dxf.nombre + "»";
      } else if (!catalogo.sesion_activa) motivo = "vuelva a cargar el DXF («Volver a cargar»)";
      else if (!catalogo.bloques.some((x) => x.handle === b.handle)) motivo = "el bloque ya no está en el DXF";
      else if (!e.cabe) motivo = "no cabe a " + textoEscala(c.escala) + ": cambie la escala";
      else if (!e.dentro) motivo = "se sale del área de dibujo: muévalo";
      if (motivo) omitidos.push({ id: c.id, motivo });
      else pedidos.push({ id: c.id, handle: b.handle, sha256: b.dxf.sha256, escala: c.escala,
        centro_mm: c.centro.slice() });
    }
    return { pedidos, omitidos };
  }

  /** Esquina inferior izquierda de la página exportada para un bloque con centro `centro`
   *  (el servidor da `desde_centro_mm`, que vale para cualquier copia a esa escala). */
  const posicionExportada = (centro, desdeCentro) => [centro[0] - desdeCentro[0], centro[1] - desdeCentro[1]];

  return { EPS_MM, ESCALAS, ESCALA_MAXIMA, esNormalizada, leerEscalaEscrita, escalaAjustada, pedidosExportar, posicionExportada, paginaMm, excesoDeTamano, escalaSugerida, escalaVecina, textoEscala,
    leerEscala, rectCentrado, rectDibujo, centroLimitado, centroZona, estadoCaja, escalaPorTirador,
    mmPorUnidadCad, centroCaja, cadAPapel, pxACad, imagenEnPapel, entradaDxf, nombreArchivo,
    leerListaDxf, leerPendiente, asignarIdsDxf, listaDxf, pendienteParaGuardar };
});
