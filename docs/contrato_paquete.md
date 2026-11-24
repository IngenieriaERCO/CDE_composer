# Contrato del paquete del Exportador Vectorial

Qué espera el componedor de cada detalle que entrega el Exportador Vectorial, y qué hace
con cada campo. La referencia del lado del exportador es su `docs/manifiesto.md`
(esquema `cde-detail-manifest` 1.0) y su módulo `src/cde_exporter/cad/manifest.py`. La
lectura en el componedor está en `src/componedor/manifiesto.py` (`leer_manifiesto`).

## 0. Flujo completo

```
localizar ──► integridad ──► coherencia ──► importar ──────► colocar --manifiesto
(paquete.py)  (integridad.py) (coherencia.py) (importador.py)
                                              └────────────► inventario (inventario.py)
```

1. **Localizar** (`paquete.localizar_paquetes`, `paquete_de_manifiesto`): un paquete por cada
   `<prefijo>.manifest.json`; se empareja su PDF por `pdf.file_name` y su TXT; el manifiesto
   se lee con `manifiesto.leer_manifiesto` (estructura). Estado completo / incompleto /
   inválido.
2. **Integridad** (`integridad.verificar_integridad`): el PDF es exactamente el descrito
   (existe, bytes, SHA-256, abre, una página).
3. **Coherencia** (`coherencia.verificar_coherencia`): la geometría del manifiesto
   corresponde al PDF (a–h) y la escala física está garantizada (i).
4. **Importar** (`importador.importar_paquete`): la ÚNICA puerta de entrada. Acepta el
   paquete solo si está completo, íntegro y coherente; si no, lanza `PaqueteRechazado` con
   TODOS los motivos, uno por línea, con categoría y el nombre del paquete:
   - `[manifiesto]` la estructura del manifiesto no es válida;
   - `[archivos]` falta el PDF, el nombre no coincide, PDF sin manifiesto, manifiesto
     ausente, o el PDF indicado no es el del paquete;
   - `[integridad]` falla una comprobación de integridad;
   - `[coherencia]` falla una comprobación de coherencia a–h;
   - `[escala]` escala física no garantizada (comprobación i).

   ```
   Paquete 'detalle' rechazado (2 motivos):
     - [integridad] el contenido del PDF cambió después de exportarse (mismo tamaño, otro SHA-256)
     - [escala] escala física no garantizada: ...
   ```
   `colocar --manifiesto` usa el importador.
5. **Inventario** (`inventario.construir_inventario`, CLI `inventario`): una fila por paquete
   con bloque, escala, tamaño del dibujo y de la página, estado (aceptado / rechazado, con
   los mismos motivos del importador) y, con un formato, si la **página** cabe en la zona
   (misma regla que `colocar`). No caber no es rechazo: es una nota con una escala sugerida
   **aproximada** de la lista estándar (1:50 … 1:10000), calculada escalando el contenido
   (página − 2 × `pdf.margin_mm`); sin margen conocido, no hay sugerencia. Dos paquetes con
   el mismo `pdf.sha256` llevan la nota «duplicado de …» (ojo: el exportador escribe un
   `/ID` aleatorio, así que dos extracciones del mismo bloque NO son duplicados; solo lo son
   las copias del mismo archivo).

## 1. Los tres archivos del paquete

Cada detalle se publica como tres archivos con el mismo prefijo, en la misma carpeta:

| Archivo | Contenido | Uso en el componedor |
|---|---|---|
| `<prefijo>.pdf` | El detalle vectorial, una página, ya a escala física 1:N. | Se coloca en la hoja sin escalar. |
| `<prefijo>.txt` | Informe legible del exportador (resumen, avisos). | Solo para personas; no se lee. |
| `<prefijo>.manifest.json` | El contrato técnico (UTF-8). | Se lee y se valida antes de usar el PDF. |

- El exportador publica el manifiesto **el último**: un PDF sin su manifiesto es un paquete
  incompleto y no se usa.
- Con varias referencias de un mismo bloque, el prefijo lleva número:
  `<prefijo>_001.pdf`, `<prefijo>_001.manifest.json`, …
- `pdf.file_name` del manifiesto es el **nombre** del PDF (sin ruta) y debe estar junto al
  manifiesto.

### Cómo se localiza un paquete (`paquete.localizar_paquetes`)

Se recorre una carpeta (y sus subcarpetas con `--recursivo`). En cada carpeta:

1. Hay **un paquete por cada `<prefijo>.manifest.json`**. El prefijo es el nombre sin
   `.manifest.json`, así que funciona con prefijos numerados (`<prefijo>_001`).
2. El PDF se busca por **`pdf.file_name` del manifiesto, en la misma carpeta** del
   manifiesto; no se supone que se llame como el prefijo. Si `pdf.file_name` no existe pero
   sí `<prefijo>.pdf`, el problema dice «el manifiesto indica X pero la carpeta tiene Y».
   Si no hay ninguno, «falta el PDF X»: paquete incompleto.
3. El TXT `<prefijo>.txt` es opcional: si falta no es un problema.
4. Un **PDF sin manifiesto**: `<p>.pdf` con su `<p>.txt` pero sin `<p>.manifest.json` es una
   publicación cortada a medias (el exportador publica PDF, TXT y por último el manifiesto)
   y se informa como paquete incompleto («PDF sin manifiesto: no se usa»). Un PDF solo, sin
   TXT ni manifiesto, se toma como suelto (p. ej. una prueba) y se ignora. Un corte justo
   después del PDF no se distingue de un PDF suelto.
5. Los demás archivos (`.dxf`, `.svg`, etc.) se ignoran sin avisos.
6. Un manifiesto inválido no detiene el recorrido: se lista con sus problemas (y su PDF no
   sale aparte como huérfano).

Estados: **completo** (manifiesto válido y su PDF presente), **incompleto** (falta el PDF, o
PDF sin manifiesto), **inválido** (el manifiesto no pasa `leer_manifiesto`). Localizar no
abre el PDF ni calcula su hash: eso lo hace la verificación de integridad (abajo).

Desde la terminal: `python -m componedor.cli paquetes <carpeta> [--recursivo] [--verificar]`
imprime la tabla (prefijo, estado, bloque, escala, tamaño de página y, con `--verificar`,
integridad OK / FALLA / —) y los problemas de cada paquete. Al final, si hay PDF sueltos
ignorados, una línea informativa «PDF sin paquete (ignorados): n — nombres» (no cambia los
estados ni el código). Código 0 si todos están completos e íntegros (también si la carpeta no
tiene paquetes) y 1 si alguno está incompleto, inválido o falla la integridad.

### Integridad del paquete (`integridad.verificar_integridad`)

Solo para paquetes **completos**; los incompletos o inválidos quedan como «no verificable
(paquete …)» sin error. Se comprueba, en este orden:

| # | Comprobación | Si falla |
|---|---|---|
| a | El PDF existe y es un archivo. | Se detiene: no hay nada que medir. |
| b | Tamaño en bytes = `pdf.bytes`. | «el PDF tiene X bytes y el manifiesto dice Y: el archivo fue modificado o está incompleto». Se sigue. |
| c | SHA-256 = `pdf.sha256` (lectura por bloques de 1 MB, nunca el archivo entero en memoria). | Con el mismo tamaño: «el contenido del PDF cambió después de exportarse». Con otro tamaño: el hash tampoco coincide, como era de esperar. |
| d | Abre con PyMuPDF, no está dañado (no hubo que repararlo) ni cifrado. | El motivo («PyMuPDF no puede abrir…», «está cifrado…», «está dañado…»). Se detiene: sin abrir no se cuentan páginas. |
| e | El PDF tiene 1 página y `pdf.page_count` también dice 1. | «el PDF tiene N página(s) y el manifiesto dice M: un detalle es una sola página». |

Ojo: un PDF con un solo byte cambiado suele abrir sin problema; solo el SHA-256 lo delata.
La integridad NO compara tamaño de página, escala ni matriz: eso es la coherencia (abajo).

### Coherencia del paquete (`coherencia.verificar_coherencia`)

¿El manifiesto describe de verdad la geometría del PDF? Solo se verifica un paquete
**completo cuya integridad pasa**; si no, queda «no verificable (…)» sin error. En orden:

| # | Comprobación | Tolerancia | Si falla |
|---|---|---|---|
| a | Rotación de la página del PDF = 0 | exacto | «incompatible: el PDF tiene /Rotate N». **Se detiene**: la matriz supone una página sin girar y las demás medidas no tendrían sentido. |
| b | Tamaño visible del PDF (`colocar.tamano_visible_mm`) = `pdf.page_size_mm` | ±0,1 mm | La página no mide lo que dice el manifiesto. |
| c | `pdf.page_size_mm` = `pdf.expected_page_size_mm` | ±0,1 mm | El tamaño medido no es el calculado con la escala. |
| d | `scale.factor_mm_per_cad_unit` = `units.millimeters_per_unit` / `scale.denominator` | relativa < 1e-6 | El factor no corresponde a las unidades y al 1:N. |
| e | Matriz: a = factor, d = −factor, b = c = 0 | relativa < 1e-6 | Si b o c ≠ 0: «matriz con giro o inclinación: todavía no soportada» (limitación del componedor, no manifiesto inválido). |
| f | Las 4 esquinas de `cad_bounds` pasadas por la matriz = `page_bounds_mm` | ±0,01 mm | `page_bounds_mm` no es `cad_bounds` transformado. |
| g | `page_bounds_mm` dentro de la página (0 ≤ x0 < x1 ≤ ancho, 0 ≤ y0 < y1 ≤ alto) | exacto | El dibujo declarado se sale de la página. |
| h | Trazos del PDF (`comprobacion_dibujo`, sin el fondo blanco) = `page_bounds_mm`. Con máscara de recorte (`pdf.drawing.mask`, esquema 1.5) cada trazo se recorta antes, a mano, a `mask.zone_page_mm`: `get_drawings()` no aplica la máscara | ±0,5 mm | Los trazos no están donde dice el manifiesto (diferencia máxima); con máscara, también «sin trazos dentro de la zona de la máscara». |
| i | **Regla de uso:** `scale.physical_scale_guaranteed` = true | exacto | «escala física no garantizada»; cita `scale.physical_scale_reason` si viene. |

**Regla de uso de `physical_scale_guaranteed`.** El componedor solo compone a escala
paquetes cuya escala física está garantizada por el exportador. Si es `false`, el paquete
no es un manifiesto inválido (su estructura es correcta), pero **se rechaza** en la
coherencia (comprobación i) y `colocar --manifiesto` no lo coloca.

`colocar --manifiesto` localiza el paquete del manifiesto (su carpeta y su prefijo) y exige:
estado completo, `--detalle` igual al PDF de `pdf.file_name`, integridad OK y coherencia OK.
Si algo falla no coloca nada y lista los problemas.

Desde la terminal: `python -m componedor.cli verificar-paquete <prefijo>.manifest.json`
muestra todas las comprobaciones de integridad y coherencia (esperado / medido /
tolerancia / PASA o FALLA) y «RESULTADO: PASA» o «RESULTADO: FALLA (n …)»; código 0 o 1.
`paquetes --verificar` agrega las columnas «Integridad» y «Coherencia».

## 2. Campos obligatorios

Son los que el componedor necesita para componer. Si falta alguno, o llega en `null`, o
tiene un tipo o valor inválido, el manifiesto se rechaza. El mensaje distingue
«falta el campo» de «es null (motivo)».

| Ruta | Tipo | Regla | Para qué lo usa el componedor |
|---|---|---|---|
| `document_type` | texto | igual a `"cde-detail-manifest"` | Saber que es un manifiesto de detalle. |
| `schema_version` | texto | versión mayor 1 (`1`, `1.0`, `1.3`…) | Compatibilidad del contrato (ver §4). |
| `model_version` | texto | presente | Trazabilidad (hoy `"2"`); no cambia el comportamiento. |
| `units.millimeters_per_unit` | número | finito, > 0 | mm reales por unidad CAD (m → 1000). |
| `scale.denominator` | número | finito, > 0 | El N de la escala 1:N (rótulo, comprobaciones). |
| `scale.factor_mm_per_cad_unit` | número | finito, > 0 | mm de papel por unidad CAD (1:50 en m → 20). |
| `scale.physical_scale_guaranteed` | booleano | `true` o `false` (estructura) | Si la escala física está comprobada. Regla de uso: debe ser `true` para componer (coherencia, comprobación i). |
| `pdf.file_name` | texto | nombre sin ruta (sin `\` ni `/`) | Encontrar el PDF junto al manifiesto. |
| `pdf.bytes` | entero | ≥ 1 | Integridad del PDF (2.3). |
| `pdf.sha256` | texto | 64 hexadecimales en minúscula | Integridad del PDF (2.3). En 2.1 solo se valida el formato. |
| `pdf.page_count` | entero | ≥ 1 | Debe ser 1 página por detalle. |
| `pdf.page_size_mm` | [ancho, alto] | 2 números finitos > 0 | Tamaño real de la página del detalle. |
| `pdf.expected_page_size_mm` | [ancho, alto] | 2 números finitos > 0 | Tamaño calculado por la escala; coherencia (comprobación c). |
| `pdf.drawing.cad_bounds.min` / `.max` | [x, y] | 2 números finitos; max > min | Caja del dibujo en coordenadas CAD. |
| `pdf.drawing.page_bounds_mm` | `{x0, y0, x1, y1}` | números finitos; x1 > x0, y1 > y0 | Caja del dibujo en la página (mm, Y abajo). |
| `pdf.drawing.cad_to_page.units` | texto | igual a `"mm"` | Unidades de la página en la matriz. |
| `pdf.drawing.cad_to_page.origin` | texto | igual a `"top-left"` | Origen de la página en la matriz. |
| `pdf.drawing.cad_to_page.y_axis` | texto | igual a `"down"` | Sentido de Y en la página. |
| `pdf.drawing.cad_to_page.matrix` | [a, b, c, d, e, f] | 6 números finitos | CAD → página: `x = a·X + c·Y + e`, `y = b·X + d·Y + f`. Anclar puntos CAD en el papel. |
| `validation.status` | texto | `complete` o `complete_with_warnings` | Estado final del exportador; un paquete publicado nunca trae otro. |

### Campos que el exportador puede dejar en `null` y el componedor exige

| Ruta | Cuándo llega en `null` (según el exportador) |
|---|---|
| `units.millimeters_per_unit` | El exportador no pudo determinar las unidades del dibujo. |
| `scale.denominator`, `scale.factor_mm_per_cad_unit` | El detalle se exportó sin escala nominal 1:N. |
| `pdf.expected_page_size_mm` | Sin escala nominal no hay tamaño esperado. |
| `pdf.drawing` (objeto entero) | El exportador no dibujó nada en el PDF. |

Un paquete así es válido para el exportador, pero el componedor no puede componerlo a escala:
se rechaza con «es null (motivo)».

## 3. Campos opcionales (informativos)

Pueden faltar, venir en `null` o cambiar de forma sin que el componedor falle. No se validan.

| Ruta | Contenido |
|---|---|
| `generated_at` | Fecha y hora de la extracción. |
| `exporter.*` | Versiones del exportador, ezdxf y PyMuPDF. |
| `source.*` | DXF de origen (nombre, hash, tamaño), bloque (`block_name`, que el resumen muestra si existe), referencia elegida. |
| `units.declared_code`, `units.name`, `units.status`, `units.user_override` | Detalle de las unidades. |
| `scale.requested`, `scale.physical_scale_reason` | Escala pedida en texto y motivo si no está garantizada. |
| `pdf.margin_mm` | Margen pedido al exportar. No se usa para componer (la matriz y `page_bounds_mm` ya lo incluyen). Si falta, es null o no es un número ≥ 0, `Manifiesto.pdf.margen_mm` queda en `None` y no se rechaza. |
| `pdf.content_size_mm` | Tamaño del contenido según la caja del CAD. |
| `entities` | Inventario de entidades por tipo, capa y estado (`conserved`, `transformed`, `simplified`, `omitted`, `unsupported`, `not_visible`). |
| `fonts`, `dependencies` | Fuentes usadas y dependencias externas. |
| `notices` | Avisos por severidad (`info`, `warning`, `critical`) y categoría. |
| `validation.checks` | Comprobaciones del exportador. |
| `options` | Opciones con que se ejecutó la extracción. |

## 4. Versiones y campos desconocidos

- Se acepta cualquier `schema_version` con **versión mayor 1** (`1`, `1.0`, `1.3`, `1.10.2`):
  una versión menor solo agrega información.
- Una versión mayor distinta (`2.0`, `0.9`) se rechaza con un mensaje claro: puede haber
  cambios que rompan la lectura.
- `model_version` se exige presente pero no se compara: es trazabilidad del exportador.
- Los **campos desconocidos se ignoran** (a diferencia del validador del exportador, que es
  estricto). Así una versión 1.x con campos nuevos se sigue pudiendo leer.

### Versiones del exportador y lo que se probó con el Componedor

| Versión | Qué agrega (ver `docs/manifiesto.md` del Exportador) | Con el Componedor |
|---|---|---|
| `1.2` | `selection.clip` (recorte a la zona de `cad extract-modelspace`) y avisos `MODELSPACE_CLIPPED` / `MODELSPACE_NOT_CLIPPED`. | Sin probar con un paquete real: no hubo paquetes de Model Space recortado. Solo agrega claves que se ignoran. |
| `1.3` | En `options`: `units`, `instancing`, `xobject`, `clip`, `exporter_version`. | Probada: los paquetes de «Exportar» del editor (etapa 3 y bloques anónimos, PRGD y GUAMO) se importan, se verifican y se componen. |
| `1.4` | En `options`: `plot_style` (`null` o `{name, sha256}` de la CTB) y `print_transparency`; avisos `PLOT_STYLE_APPLIED` y `HATCH_TRANSPARENT_OMITTED`. | **Probada el 2026-11-19** con el Exportador real (dev, 7154704) y PRGD: «via tunez» 1:500 y la mesa I1.M1.PV1_12900 1:75, con las opciones por defecto y con `plot_style` = `CTB_ERCO_V2.ctb` y `print_transparency: false`. Se importan, aparecen en el catálogo del editor y se componen (con ortofoto y cuadrícula). No hizo falta ningún cambio. |
| `1.5` | `pdf.drawing.mask` (`null`, o `zone_cad`, `zone_page_mm` y `bleed_mm` de la máscara de recorte de una zona del Model Space); con máscara, `cad_bounds` y `page_bounds_mm` son lo que se ve. | **Probada el 2026-11-24** con los paquetes de zona del Exportador (402ad72) en `data/verificacion/zonas_3`, `zonas_4` y `zonas_5` de su repositorio: los 14 pasan integridad y coherencia (h con diferencia 0,000 mm). `manifiesto.py` lee `mask.zone_page_mm` (si viene, se valida) y la h recorta los trazos a esa zona. |

## 5. Quién valida qué

- `manifiesto.leer_manifiesto`: solo la **estructura** (es el único lector del manifiesto;
  `colocar`, `referencia --detalle`, `paquetes` y `verificar-paquete` lo usan).
- `integridad.py`: que el PDF sea exactamente el descrito (existe, bytes, SHA-256, abre,
  una página). Ver «Integridad del paquete».
- `coherencia.py`: que la geometría del manifiesto corresponda al PDF y la regla de uso de
  la escala física. Ver «Coherencia del paquete».

## 6. Cómo se informa un manifiesto inválido

`leer_manifiesto` junta **todos** los problemas en un solo `ManifiestoInvalido`, uno por
línea, con la ruta del campo. Ejemplo:

```
El manifiesto 'detalle.manifest.json' no es válido (3 problemas):
- pdf.page_size_mm: falta el campo
- scale.denominator: es null (el detalle se exportó sin escala nominal 1:N)
- pdf.drawing.cad_to_page.units: debe ser 'mm'; tiene 'm'
```

Si falta un objeto entero (p. ej. `scale`), se informa una sola vez y no por cada campo
interno. Un JSON mal formado o un archivo inexistente dan un mensaje claro (con línea y
columna del error de JSON), nunca un traceback.

Desde la terminal: `python -m componedor.cli leer-manifiesto <prefijo>.manifest.json`
muestra un resumen (bloque, escala, tamaño de página, estado de validación) o la lista de
problemas; termina con código 0 o 1.
