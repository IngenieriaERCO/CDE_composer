/*
 * Editor de planos — lógica de las CONVENCIONES del rótulo (subfase 4.3d). Pura, sin pantalla:
 * funciona en el navegador (window.EditorConvenciones) y en Node (module.exports).
 *
 * - Lista editable: rotulo.convenciones ([{"simbolo", "descripcion"?}]) -> elementos {simbolo,
 *   descripcion (la que se ve), original, tocado}. Al guardar, lo no tocado sale tal como vino;
 *   lo tocado o nuevo, {"simbolo": id} y "descripcion" SOLO si es distinta de la de por defecto
 *   (la del índice de símbolos). Un símbolo que el índice no tiene se conserva y se marca.
 * - Casilla de la leyenda: llenado por columna, como `componer` (rotulo_formato: pareja
 *   izquierda de arriba abajo, luego la derecha): con 24, 1–12 izquierda y 13–24 derecha.
 * - Validación: los MISMOS textos que rotulo._convenciones (+ _contenido y la revisión de
 *   caracteres de la fuente sobre la celda «convenciones.<k>.descripcion»). Desde la 4.3e la
 *   descripción también se MIDE (editor_maquetacion.js, vía F.validarTexto): «no cabe» y «se
 *   escribió a X mm», con los textos de `componer`.
 * - Subfase 9a: un renglón también puede ser una MUESTRA de línea o de relleno
 *   ({"tipo": "linea" | "relleno", ...}, reglas en editor_muestras.js). Sin `tipo`, símbolo.
 */
(function (raiz, fabrica) {
  "use strict";
  const enNode = typeof module === "object" && module.exports;
  const F = enNode ? require("./editor_formularios.js") : raiz.EditorFormularios;
  const MU = enNode ? require("./editor_muestras.js") : raiz.EditorMuestras;
  const api = fabrica(F, MU);
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    raiz.EditorConvenciones = api;
  }
})(typeof self !== "undefined" ? self : this, function (F, MU) {
  "use strict";

  const esObjeto = (v) => v !== null && typeof v === "object" && !Array.isArray(v);
  const clonar = (v) => (v === undefined ? undefined : JSON.parse(JSON.stringify(v)));
  const CAMPO = "convenciones";

  /** El campo de convenciones de la definición (o null). */
  function campo(definicion) {
    if (!definicion) return null;
    for (const [nombre, c] of Object.entries(definicion.campos)) if (c.tipo === "convenciones") return Object.assign({ nombre }, c);
    return null;
  }

  /** Casilla de la posición i (0…): {numero 1…, columna "izquierda"|"derecha", fila 1…}. */
  function casilla(i, capacidad) {
    const porColumna = Math.max(1, Math.floor(capacidad / 2));
    return { numero: i + 1, columna: i < porColumna ? "izquierda" : "derecha", fila: (i % porColumna) + 1,
      dentro: i < capacidad };
  }

  /** Celda de la descripción de la posición i, para F.validarTexto. */
  function celdaDescripcion(c, i) {
    const d = c.descripciones[i];
    return { ruta: c.nombre + "." + (i + 1) + ".descripcion", ancho_mm: d.rect_mm[2] - d.rect_mm[0],
      altura_mm: d.altura_mm, altura_min_mm: d.altura_min_mm, lineas_max: d.lineas_max,
      rect_mm: d.rect_mm.slice(), alinear: d.alinear };
  }

  // ---------------------------------------------------------------------------------------
  // Validación (mismos textos que rotulo._convenciones).
  // ---------------------------------------------------------------------------------------

  /** {errores, avisos} de rotulo.convenciones. `simbolos`: los del editor (orden del índice). */
  function validarConvenciones(valor, definicion, fuente, simbolos) {
    const errores = [];
    const avisos = [];
    const c = campo(definicion);
    if (valor === undefined || !c) return { errores, avisos };
    const donde = "rotulo." + c.nombre;
    if (!Array.isArray(valor)) {
      errores.push(donde + ": se esperaba una lista de {\"simbolo\": ..., \"descripcion\": ...}; tiene " + F.tipo(valor));
      return { errores, avisos };
    }
    if (!valor.length) return { errores, avisos };
    if (valor.length > c.capacidad) {
      errores.push(donde + ": hay " + valor.length + " convenciones y la tabla admite " + c.capacidad +
        " (dos columnas de " + Math.floor(c.capacidad / 2) + ")");
    }
    const porId = new Map((simbolos || []).map((s) => [s.id, s]));
    const validos = (simbolos || []).map((s) => s.id).join(", ");
    const vistos = {};
    valor.forEach((item, i) => {
      const sitio = donde + "[" + i + "]";
      if (!esObjeto(item)) {
        errores.push(sitio + ": se esperaba un objeto {\"simbolo\": ...}; tiene " + F.tipo(item));
        return;
      }
      const tipo = MU.tipoDe(item);
      if (!MU.TIPOS.includes(tipo)) {
        errores.push(sitio + ".tipo: se esperaba «simbolo», «linea» o «relleno»; tiene " + F.tipo(tipo));
        return;
      }
      const claves = MU.CLAVES[tipo];
      for (const k of Object.keys(item).filter((k) => !claves.includes(k)).sort()) {
        errores.push(sitio + "." + k + ": campo no reconocido (campos válidos: " + claves.join(", ") + ")");
      }
      if (MU.esMuestra(tipo)) {
        errores.push(...MU.leerMuestra(item, sitio, F.tipo).errores);
        if (i >= c.capacidad) return;
        if (MU.descripcionVacia(item.descripcion)) {
          errores.push(MU.errorFaltaDescripcion(sitio));
          return;
        }
        const r = F.validarTexto(item.descripcion, celdaDescripcion(c, i), sitio + ".descripcion", fuente,
          definicion.relleno_mm, definicion.interlineado);
        errores.push(...r.errores);
        avisos.push(...r.avisos);
        return;
      }
      const ident = item.simbolo;
      if (!porId.has(ident)) {
        errores.push(sitio + ".simbolo: " + F.tipo(ident) + " no está en la biblioteca (símbolos válidos: " + validos + ")");
        return;
      }
      if (ident in vistos) {
        errores.push(sitio + ".simbolo: '" + ident + "' está repetido (ya está en " + donde + "[" + vistos[ident] + "])");
        return;
      }
      vistos[ident] = i;
      if (i >= c.capacidad) return;
      const celda = celdaDescripcion(c, i);
      const texto = "descripcion" in item ? item.descripcion : porId.get(ident).descripcion;
      const r = F.validarTexto(texto, celda, sitio + ".descripcion", fuente, definicion.relleno_mm,
        definicion.interlineado);
      errores.push(...r.errores);
      avisos.push(...r.avisos);
    });
    return { errores, avisos };
  }

  // ---------------------------------------------------------------------------------------
  // Lista editable.
  // ---------------------------------------------------------------------------------------

  /** ¿Una convención que la lista sabe mostrar? (una muestra, solo con valores válidos). */
  function representable(item) {
    if (!esObjeto(item)) return false;
    const tipo = MU.tipoDe(item);
    if (!MU.TIPOS.includes(tipo) || !Object.keys(item).every((k) => MU.CLAVES[tipo].includes(k))) return false;
    if (item.descripcion !== undefined && !F.representable(item.descripcion)) return false;
    if (MU.esMuestra(tipo)) return MU.leerMuestra(item, "", F.tipo).muestra !== null;
    return typeof item.simbolo === "string";
  }

  /**
   * {items, editable}. Cada item: {tipo, simbolo, descripcion (texto que se ve), original,
   * tocado, conocido (está en el índice)}; una muestra trae además color, grosor_mm y trazo
   * (línea) u opacidad (relleno), con los valores por defecto ya puestos.
   */
  function lista(valor, simbolos) {
    const porId = new Map((simbolos || []).map((s) => [s.id, s]));
    const editable = valor === undefined || (Array.isArray(valor) && valor.every(representable));
    const items = editable && Array.isArray(valor) ? valor.map((item) => {
      const tipo = MU.tipoDe(item);
      if (MU.esMuestra(tipo)) {
        return Object.assign(MU.leerMuestra(item, "", F.tipo).muestra, {
          descripcion: clonar(item.descripcion), original: clonar(item), tocado: false, conocido: true });
      }
      return {
        tipo,
        simbolo: item.simbolo,
        descripcion: item.descripcion !== undefined ? clonar(item.descripcion)
          : (porId.has(item.simbolo) ? porId.get(item.simbolo).descripcion : ""),
        original: clonar(item),
        tocado: false,
        conocido: porId.has(item.simbolo),
      };
    }) : [];
    return { items, editable };
  }

  /** Item nuevo desde el índice (descripción por defecto). */
  function itemDeSimbolo(id, simbolos) {
    const s = (simbolos || []).find((x) => x.id === id);
    return s ? { tipo: MU.TIPO_SIMBOLO, simbolo: id, descripcion: s.descripcion, original: undefined, tocado: true,
      conocido: true } : null;
  }

  /** Muestra nueva ("linea" o "relleno") con los valores por defecto y SIN descripción. */
  function itemDeMuestra(tipo) {
    return Object.assign({ tipo }, MU.POR_DEFECTO[tipo], { descripcion: undefined, original: undefined,
      tocado: true, conocido: true });
  }

  /**
   * Cómo se guarda: el original si no se tocó; si no, {simbolo} (+ descripcion si cambió) o,
   * en una muestra, {tipo, descripcion, color, grosor_mm, trazo} / {tipo, descripcion, color,
   * opacidad (solo si es menor que 1)}.
   */
  function itemParaGuardar(item, simbolos) {
    if (!item.tocado && item.original !== undefined) return clonar(item.original);
    if (MU.esMuestra(item.tipo)) {
      const salida = { tipo: item.tipo };
      if (item.descripcion !== undefined) salida.descripcion = clonar(item.descripcion);
      salida.color = item.color;
      if (item.tipo === "linea") {
        salida.grosor_mm = item.grosor_mm;
        salida.trazo = item.trazo;
      } else if (item.opacidad !== 1) {
        salida.opacidad = item.opacidad;
      }
      return salida;
    }
    const s = (simbolos || []).find((x) => x.id === item.simbolo);
    const salida = { simbolo: item.simbolo };
    const igual = s && typeof item.descripcion === "string" && item.descripcion === s.descripcion;
    if (!igual && item.descripcion !== undefined) salida.descripcion = clonar(item.descripcion);
    return salida;
  }

  /** rotulo.convenciones para guardar (lista vacía -> undefined: se quita). */
  function convencionesParaGuardar(items, simbolos) {
    return items.length ? items.map((x) => itemParaGuardar(x, simbolos)) : undefined;
  }

  /**
   * Marcar un símbolo: al final de la lista. {items, aviso}: no se repite, y con la tabla llena
   * (capacidad) no se agrega y vuelve un aviso claro.
   */
  function marcar(items, id, simbolos, capacidad) {
    if (items.some((x) => x.simbolo === id)) return { items: items.slice(), aviso: "" };
    if (items.length >= capacidad) {
      return { items: items.slice(), aviso: "La tabla de convenciones está llena: admite " + capacidad +
        " (dos columnas de " + Math.floor(capacidad / 2) + "). Quite una para agregar otra." };
    }
    const item = itemDeSimbolo(id, simbolos);
    return { items: item ? items.concat([item]) : items.slice(), aviso: "" };
  }

  /** Agregar una muestra al final: {items, aviso} (con la tabla llena no se agrega). */
  function agregarMuestra(items, tipo, capacidad) {
    if (items.length >= capacidad) {
      return { items: items.slice(), aviso: "La tabla de convenciones está llena: admite " + capacidad +
        " (dos columnas de " + Math.floor(capacidad / 2) + "). Quite una para agregar otra." };
    }
    return { items: items.concat([itemDeMuestra(tipo)]), aviso: "" };
  }

  /** Cambiar color, grosor, trazo u opacidad de una muestra. */
  function cambiarMuestra(item, cambios) {
    return Object.assign({}, item, cambios, { tocado: true });
  }

  function desmarcar(items, id) {
    return items.filter((x) => x.simbolo !== id);
  }

  function mover(items, i, paso) {
    const j = i + paso;
    if (j < 0 || j >= items.length) return items.slice();
    const copia = items.slice();
    [copia[i], copia[j]] = [copia[j], copia[i]];
    return copia;
  }

  function quitar(items, i) {
    return items.filter((x, k) => k !== i);
  }

  /** Cambiar la descripción visible (texto del formulario; vacío = la de por defecto). */
  function cambiarDescripcion(item, texto, simbolos) {
    const nuevo = F.valorDeTexto(texto, item.descripcion);
    if (MU.esMuestra(item.tipo)) return Object.assign({}, item, { descripcion: nuevo, tocado: true });
    const s = (simbolos || []).find((x) => x.id === item.simbolo);
    return Object.assign({}, item, { descripcion: nuevo === undefined ? (s ? s.descripcion : "") : nuevo, tocado: true });
  }

  return {
    campo,
    casilla,
    celdaDescripcion,
    validarConvenciones,
    representable,
    lista,
    itemDeSimbolo,
    itemDeMuestra,
    itemParaGuardar,
    agregarMuestra,
    cambiarMuestra,
    convencionesParaGuardar,
    marcar,
    desmarcar,
    mover,
    quitar,
    cambiarDescripcion,
  };
});
