# Formato de plano.json (versiones 1 y 2)

Un `plano.json` dice **qué detalles van en una hoja y dónde** y, desde la versión 2, **qué
se escribe en el rótulo** y **dónde va la rosa de los vientos**. Lo lee el comando
`componer`:

```powershell
python -m componedor.cli componer data/planos/mi_plano.json --salida data/output/mi_plano.pdf [--sobrescribir] [--guias]
```

El editor HTML (`editor.html`) lo escribe arrastrando y soltando, pero el componedor
**siempre** lo revalida todo: el editor nunca es la fuente de la verdad.

- **Versión 1**: solo detalles. Sigue siendo válida.
- **Versión 2** (subfase 4.1): lo mismo más `rotulo`, `rosa_vientos` y, en cada detalle,
  `etiqueta_escala`. Todo eso es opcional.

## Ejemplo (versión 2)

Archivo `data/planos/mi_plano.json`:

```json
{
  "version": 2,
  "formato": "../../formatos/A1_ERCO.json",
  "plantilla": null,
  "detalles": [
    {"id": "via_ma", "manifiesto": "../input/via_ma_5000.manifest.json", "posicion_mm": [30, 175]},
    {"id": "perfil", "manifiesto": "../input/perfil_k0010.manifest.json", "posicion_mm": [30, 30]},
    {"id": "otro",   "manifiesto": "../input/otro.manifest.json", "centrar": true, "etiqueta_escala": false}
  ],
  "rosa_vientos": {"visible": true, "posicion_mm": [610, 520]},
  "rotulo": {
    "localizacion_escala": "1:25.000",
    "este": "4.876.543,21",
    "norte": "2.012.345,67",
    "revisiones": [
      {"ver": "0", "fecha": "2026-11-06", "descripcion": "EMISIÓN PARA CONSTRUCCIÓN",
       "dibujo": "LANP", "diseno": "LANP", "reviso": "A. GÓMEZ", "aprobo": "JP"},
      {"ver": "A", "fecha": "2026-10-20", "descripcion": "EMISIÓN PARA REVISIÓN INTERNA"}
    ],
    "disenador": "INGENIERÍA DE DISEÑO S.A.S.",
    "revisor": "INTERVENTORÍA LTDA.",
    "titulo": "VÍA DE ACCESO PRINCIPAL MA: PLANTA GENERAL, PERFIL LONGITUDINAL Y SECCIONES TÍPICAS",
    "firmas": {
      "dibujo": {"nombre": "LUIS Á. NÚÑEZ P.", "matricula": "PRACTICANTE", "fecha": "2026-11-06"},
      "reviso": {"nombre": ["ANDRÉS GÓMEZ", "(DIRECTOR TÉCNICO)"], "matricula": "25202-654321"}
    },
    "hoja": 1,
    "de": 3,
    "no_plano": "ERCO-PSF-CIV-PL-0001"
  }
}
```

## Campos

| Campo | Tipo | Obligatorio | Significado |
|---|---|---|---|
| `version` | entero | sí | `1` o `2`. |
| `formato` | texto (ruta) | sí | Formato de hoja (p. ej. `A1_ERCO.json`). |
| `plantilla` | texto (ruta) o `null` | no | PDF del rótulo. Si falta o es `null`, se usa la plantilla del formato. |
| `detalles` | lista (al menos 1) | sí | Los detalles, **en orden de apilado**: el último queda encima. |
| `detalles[].id` | texto no vacío | sí | Nombre del detalle en el plano. **Único**. |
| `detalles[].manifiesto` | texto (ruta) | sí | `<prefijo>.manifest.json` del paquete del exportador. |
| `detalles[].posicion_mm` | `[x, y]` (números) | uno de los dos | Esquina inferior izquierda de la **página** del detalle, en mm de papel. |
| `detalles[].centrar` | `true` | uno de los dos | Centra la página del detalle en el área de dibujo. |
| `detalles[].etiqueta_escala` | `true` / `false` | no (v2) | `false`: ese detalle no lleva la etiqueta «ESC: 1:N». Por defecto `true`. |
| `rosa_vientos` | objeto | no (v2) | `{"visible": true/false, "posicion_mm": [x, y]}`, ambos opcionales (ver abajo). |
| `rotulo` | objeto | no (v2) | Valores de los campos del rótulo (ver abajo). |

Reglas:

- **Rutas**: todas son relativas a la **carpeta donde está el plano.json** (no al directorio
  desde donde se corre el comando). También se aceptan rutas absolutas.
- **Unidades y coordenadas**: mm, sistema de papel (origen en la esquina inferior izquierda
  de la hoja, X a la derecha, Y hacia arriba), igual que `colocar --posicion`.
- Cada detalle lleva `posicion_mm` **o** `centrar: true`, nunca ambos ni ninguno
  (`centrar: false` junto con `posicion_mm` es válido).
- El mismo paquete puede ir varias veces (con `id` distintos); se verifica una sola vez.
- **Campos desconocidos se rechazan** (un error de tipeo como `"centar"` no pasa en
  silencio). `rotulo`, `rosa_vientos` y `etiqueta_escala` en un plano versión 1 son error
  («solo existe en la versión 2 del plano»).
- Todavía **no** se admiten anclas CAD en el plano.json (solo posición o centrado).

Si el archivo no cumple, `componer` muestra **todos** los problemas juntos, uno por línea,
con la ruta del campo, por ejemplo:

```
El plano 'plano.json' no es válido (2 problemas):
- detalles[1].id: 'd1' está repetido (ya lo usa detalles[0]); cada id debe ser único
- detalles[2]: falta posicion_mm [x, y] o centrar: true (uno de los dos)
```

## Rosa de los vientos (`rosa_vientos`, versión 2)

La rosa viene dibujada en la plantilla del rótulo (elemento `rosa_vientos` del formato, en
X 615,94 a 654,92 e Y 25,21 a 64,21 mm). Se puede **ocultar** o **mover**:

| Campo | Por defecto | Significado |
|---|---|---|
| `visible` | `true` | `false`: la rosa no sale en el plano. |
| `posicion_mm` | su lugar original | Esquina inferior izquierda del **rectángulo de la rosa** (mm de papel, Y hacia arriba), como `posicion_mm` de un detalle. |

- Sin `rosa_vientos` (o en un plano versión 1): visible y en su lugar.
- La rosa movida debe quedar **completa dentro de `area_dibujo`**; si no, error con los mm
  que se pasa. Mismo tamaño, sin rotación.
- Las advertencias de «detalle sobre elemento» usan la **posición nueva**. Oculta: no avisa
  y su zona queda libre.
- Cómo lo hace `componer`: siempre la **quita** de la plantilla (redacción de PyMuPDF solo en
  su rectángulo + 2 mm: se borran los trazos completamente contenidos y su texto; el marco y
  lo demás no se tocan, y se comprueba que el resto de la plantilla quedó idéntico) y, si
  es visible, la **vuelve a dibujar como vectores** copiándola de la plantilla original
  (`show_pdf_page` con `clip`). En su lugar original el resultado es igual a la plantilla
  sin tocar (misma geometría, ±0,1 mm).
- Si el formato no declara `rosa_vientos`, poner `rosa_vientos` en el plano es error.

## Rótulo (`rotulo`, versión 2)

Qué se puede escribir y **dónde** (celdas en mm) lo define la sección `"rotulo"` del formato
(`formatos/A1_ERCO.json`); el plano solo trae los **textos**. Todo es opcional: un campo que
falta queda vacío, salvo su valor por defecto. `null` o `""` dejan la celda vacía.

| Campo del plano | Tipo | Celda (A1 ERCO v2) |
|---|---|---|
| `localizacion_escala` | texto | ESC del recuadro de localización. Por defecto **`DEFINIR`**. |
| `este`, `norte` | texto | Coordenadas de la localización. |
| `titulo` | texto o lista de hasta 3 líneas | Título del plano (2,5 mm; se puede reducir hasta 2,0 mm). |
| `disenador`, `revisor` | texto o lista de hasta 3 líneas | Celdas a la izquierda y a la derecha del logo. |
| `revisiones` | lista de objetos | Tabla de revisiones (ver abajo). |
| `firmas` | objeto por fila | Tabla DIBUJÓ / DISEÑÓ / REVISÓ / APROBÓ (ver abajo). |
| `hoja`, `de` | texto o entero | HOJA __ DE __ (las dos celdas tienen el mismo rango en X, 812,9–827,4 mm, y van centradas: los dos valores quedan uno debajo del otro). |
| `no_plano` | texto | No. PLANO. |
| `notas` | objeto | `{"archivos": [...], "adicionales": [...]}`: notas numeradas (ver «Notas»). |
| `convenciones` | lista (máx. 24) | `[{"simbolo": "corte"}, {"simbolo": "via_existente", "descripcion": "…"}]` (ver «Convenciones»). |
| `escala` | **calculada** | No se escribe: es la escala de los detalles si todos tienen la misma (`1:1.000`), si no `INDICADAS`. |
| `rev` | **calculada** | No se escribe: la letra de mayor orden con revisión llena (0 < A < B < C); sin revisiones, vacía. |

**Revisiones**: cada revisión lleva su propia letra `"ver"` (`"0"`, `"A"`, `"B"` o `"C"`) y
se escribe en **la fila de esa letra** (no por orden de llegada); la letra se imprime en la
columna VER solo en las filas llenas. Columnas: `fecha`, `descripcion`, `dibujo`, `diseno`,
`reviso`, `aprobo` (todas opcionales). Letras repetidas: error. Las columnas DIBUJÓ a APROBÓ
son angostas (unos 10 mm útiles): use iniciales.

**Firmas**: `{"dibujo"|"diseno"|"reviso"|"aprobo": {"nombre", "matricula", "firma", "fecha"}}`.
`firma` es texto opcional (por defecto vacía). La fila REVISÓ admite 2 líneas en cada celda
(`"nombre": ["ANDRÉS GÓMEZ", "(DIRECTOR TÉCNICO)"]`).

**Escalas**: siempre con punto de miles: `1:50`, `1:1.000`, `1:10.000` (celda ESCALA y
etiquetas «ESC: 1:N»).

### Cómo se acomoda el texto

- Fuente: **Arial** (ruta configurable en el formato, `rotulo.fuente.archivo`), **embebida**
  en el PDF, con tildes y ñ. El texto queda como texto real: se puede buscar y copiar.
- La altura es la de las **mayúsculas** (como la altura de texto de AutoCAD). El texto queda
  centrado en alto en su celda y alineado a la izquierda, al centro o a la derecha según el
  formato, con 0,6 mm de relleno contra los bordes.
- Un texto largo en una celda de varias líneas se **parte por palabras**; una lista son
  líneas explícitas (no se parten).
- Si no cabe: solo donde el formato lo permite (`altura_min_mm`, hoy solo el título), se
  reduce de 0,1 en 0,1 mm hasta la mínima, **con advertencia**. Si ni así cabe, **error**
  con el campo, el texto y las medidas; nunca se recorta ni se reduce en silencio:

```
No se compone el plano. El rótulo tiene 1 problema:
- campo 'no_plano': «ERCO-PSF-CIV-PL-0001-PLANTA-GENERAL-...» mide 138.5 mm y la celda permite 114.9 mm (altura 2.5 mm)
```

### Convenciones (`rotulo.convenciones`, subfase 4.2b)

```json
"convenciones": [
  {"simbolo": "corte"},
  {"simbolo": "via_existente", "descripcion": "VÍA SUÁREZ – LA GLORIA"}
]
```

- Cada convención es un **símbolo** de la biblioteca (`simbolos/indice.json`) y, opcional,
  una **descripción** propia; sin ella va la descripción por defecto del índice.
- **Símbolos disponibles** (biblioteca extraída del plano PRGE-25-0044-CIV-PL-101_A):
  `limite_predio`, `curvas_nivel`, `cuerpos_agua`, `linea_electrica`, `via_existente`,
  `via_carreteable`, `limite_predio_proyectado`, `gps`, `panel_3vx8`, `panel_3vx24`, `corte`,
  `relleno`.
- **Llenado por columna**: las primeras 12 van en la columna izquierda (símbolo +
  descripción) de arriba abajo; de la 13.ª a la 24.ª, en la columna derecha. Máximo 24.
- **El símbolo** se copia como **vector** desde la biblioteca (`show_pdf_page`), **centrado**
  en su casilla. Nunca se agranda: si no cabe en el espacio útil (casilla menos 0,6 mm por
  lado: unos 20,2 × 9,3 mm en las filas 1 a 8 y 20,2 × 8,4 mm en las 9 a 12) se reduce,
  `f = min(1, ancho útil / ancho, alto útil / alto)`, con advertencia («se redujo al 90.6 %»).
  Con la biblioteca actual, solo `curvas_nivel` (9,23 mm de alto) se reduce, y solo si cae
  en las filas 9 a 12.
- **Opacidad** (subfase 4.2c): un símbolo del índice puede llevar `"opacidad"` (mayor que 0 y
  hasta 1; por defecto 1). Se aplica al colocarlo con un estado gráfico del PDF (`ExtGState`
  `/CA` y `/ca`): **sigue siendo vector**, no se rasteriza y sus trazos no cambian.
  `limite_predio_proyectado` usa **0,5**: el mismo naranja que `limite_predio`, con
  transparencia. La verificación además comprueba que ningún trazo del símbolo quede más
  opaco que lo pedido.
- **La descripción** se acomoda como cualquier texto: 1,8 mm (mín. 1,5), hasta 2 líneas,
  alineada a la izquierda; si no cabe, error con el campo, el texto y el tamaño.
- **Errores juntos**: símbolo inexistente (con la lista de los válidos), símbolo repetido,
  más de 24, campos desconocidos y caracteres que la fuente no tiene. Si falta la
  biblioteca o su índice, el error dice qué falta y cómo generarla.
- **Verificación en el PDF**: en la casilla de cada símbolo hay **exactamente sus trazos** (los
  del índice) y su caja es la esperada tras el escalado (±0,1 mm); la descripción pasa por
  la verificación de textos (posición y dentro de su celda).

**La biblioteca** (`extraer-simbolos`, una sola vez):

```powershell
python -m componedor.cli extraer-simbolos "C:\...\PRGE-25-0044-CIV-PL-101_A_Plano_Movimiento_de_Tierras.pdf"
```

Lee la leyenda de la página 1 del plano (misma rejilla que el rótulo v2), la normaliza
(quita el /Rotate 270), aísla cada símbolo con redacciones (`show_pdf_page` con `clip` no
quita contenido, solo lo oculta) y lo copia como vector a `simbolos/convenciones_erco.pdf`, una
página por símbolo; verifica que cada uno tenga los mismos trazos y la misma caja (±0,1 mm)
que en el plano y escribe `simbolos/indice.json` (conserva los ids y descripciones que ya
tenga). El PDF de la biblioteca sale de un plano de ERCO y **no se versiona**; el índice sí.

### Notas (`rotulo.notas`, subfase 4.2a)

```json
"notas": {
  "archivos": ["../notas/generales_vias.txt", "../notas/drenaje.txt"],
  "adicionales": ["ESTE PLANO REEMPLAZA A LA REVISIÓN A."]
}
```

- **Archivos de notas** (`.txt`, rutas relativas a la carpeta del plano.json): UTF-8 (con o
  sin BOM), **una nota por línea**. Se ignoran las líneas en blanco y las que empiezan con
  `#` (comentarios). **Sin número**: el componedor numera solo. Si una línea ya trae su
  número («3. …» o «3) …»), se quita **con advertencia** («3.5 M» no cuenta como número: le
  falta el espacio).

  ```text
  # Notas generales de vías
  LAS DIMENSIONES ESTÁN EN METROS, SALVO QUE SE INDIQUE OTRA UNIDAD.
  LAS COORDENADAS ESTÁN REFERIDAS AL SISTEMA MAGNA-SIRGAS ORIGEN NACIONAL.
  LAS ALCANTARILLAS SERÁN:
  - DE CONCRETO REFORZADO.
  - CON PENDIENTE MÍNIMA DEL 2 %.
  ```

- **Viñetas** (subfase 4.2c): una línea que empieza con `- ` es una **viñeta de la nota
  anterior** del mismo archivo: sin número, con «•» y su texto con una sangría más profunda
  que la de la nota. Una viñeta antes de cualquier nota del archivo es **error**.
- **Adicionales**: lista; cada elemento es un texto (una nota) o un objeto
  `{"texto": "LOS MATERIALES CUMPLIRÁN:", "vinetas": ["NORMA A.", "NORMA B."]}` (sin saltos de
  línea; campos desconocidos son error).
- **Orden y numeración**: primero las de los archivos (en el orden de la lista), luego las
  adicionales; numeración continua 1, 2, 3, …
- **Cómo quedan** (celda NOTAS: X 673,2–827,4, Y 271,3–419,3 mm):
  - número a la izquierda y texto con **sangría francesa** (las líneas que siguen de una nota
    empiezan donde empieza su texto, no bajo el número; la sangría es el ancho del número más
    largo más un espacio);
  - viñetas: «•» donde empieza el texto de la nota y el texto de la viñeta más adentro (el
    ancho de «• »), también con sangría francesa; **sin** espacio extra entre la nota y sus
    viñetas ni entre viñetas;
  - corte por palabras; **medio renglón** extra entre una nota y la siguiente (después de la
    última viñeta);
  - el bloque va **pegado arriba** de la celda (no centrado). La celda termina 1,7 mm por
    debajo de la etiqueta «NOTAS» de la plantilla (Y 420,96–422,99): la primera línea, con su
    caja completa, queda a 1,8 mm de ella.
  - altura **1,8 mm**; caben unas 51 líneas de unos 99 caracteres en mayúscula.
- **Si no caben**: **todas** bajan juntas de 0,1 en 0,1 mm hasta **1,5 mm**, con advertencia.
  Si ni así caben, error con el campo, el tamaño y desde qué nota ya no caben, sin PDF:

  ```
  - campo 'notas': 69 notas (69 líneas a 1.5 mm (la mínima permitida)) ocupan 246.3 mm de alto y la celda permite 146.8 mm; no caben desde la nota 42 (muchas.txt, línea 42): «NOTA DE PRUEBA NÚMERO 42.»
  ```

- **Errores juntos**: archivo inexistente, archivo que no está en UTF-8, archivo sin notas,
  caracteres que la fuente no tiene, campos desconocidos y tipos equivocados salen todos a la
  vez, con la nota y su origen («generales.txt, línea 7», «adicionales[1]»).
- **Verificación en el PDF**: cada línea, como todo texto, en su sitio y dentro de la celda
  (±0,1 mm); además, en la celda se leen **tantas líneas como se escribieron** (con las de
  las viñetas) y la numeración leída es **1…N sin saltos** (las viñetas no se numeran).

## Etiqueta «ESC: 1:N» de cada detalle

`componer` escribe junto a cada detalle su escala real (la del manifiesto), p. ej.
`ESC: 1:1.000`, con mayúsculas de 2,5 mm:

1. centrada **debajo del dibujo** del detalle (`page_bounds_mm`), a 3 mm de él;
2. si ahí no cabe, centrada **encima**, a 3 mm.

Un sitio sirve si la caja completa de la etiqueta (con el ascenso y el descenso de la fuente)
queda dentro de `area_dibujo` y no se monta sobre el dibujo de otro detalle, la rosa
(visible) ni otra etiqueta. Si no sirve ninguno, **no se dibuja** y se
avisa con una advertencia (mueva el detalle o ponga `"etiqueta_escala": false`).

Las etiquetas y los campos calculados se escriben siempre que el formato tenga la sección
`"rotulo"`, también en un plano versión 1.

## Qué hace `componer` con el plano

1. Lee y valida el plano.json.
2. Carga el formato y decide dónde va la rosa (o si va oculta).
3. Cada detalle pasa por `importar_paquete` (la única puerta: completo, íntegro y
   coherente, con escala física garantizada). Si hay paquetes rechazados **no se genera
   el PDF**: se listan todos, con el `id` del detalle y los motivos.
4. **Posiciones**: la página completa de cada detalle debe quedar dentro de
   `area_dibujo`, con la misma regla estricta que `colocar`. Si no, error con el `id`, los
   mm que se pasa y la zona que invade. **El rótulo es inamovible**: no se permite poner
   detalles sobre él ni sobre otras zonas.
5. **Traslapes**: no son error, son advertencias (entre detalles, y de un detalle sobre un
   elemento fijo como la rosa, en su posición final). Ver `docs/editor.md`, sección 5.
6. **Rótulo y etiquetas**: valida los valores del rótulo, calcula ESCALA y REV., acomoda cada
   texto en su celda y coloca las etiquetas «ESC: 1:N». Un texto que no cabe es error (no se
   genera el PDF); una etiqueta que no cabe, advertencia.
7. Crea la hoja con la plantilla, quita la rosa y la vuelve a dibujar donde corresponda,
   inserta los detalles en orden (sin reescalar, como vector) y escribe los textos.
8. Guarda en un archivo temporal y **verifica** el PDF: el dibujo de cada detalle está donde
   dice el plano (±0,1 mm, medido con `get_drawings()` sin el fondo blanco), el marco del
   rótulo no se movió, no hay imágenes nuevas, la rosa quedó donde se pidió (sus trazos son
   los originales trasladados, ±0,1 mm) y, para cada línea de texto (campos, tablas y
   etiquetas «ESC: 1:N»), leyendo los caracteres del PDF con `get_text("rawdict")`:
   - **posición**: su primer carácter está en la base esperada y el texto leído es el
     escrito (±0,1 mm) (en las notas, además: líneas leídas = escritas y numeración 1…N;
     en las convenciones: trazos de cada símbolo y su caja en la casilla);
   - **celda**: la caja que forman los bboxes de sus caracteres (ancho de avance y caja de
     línea de la fuente: ascenso y descenso) queda dentro del rectángulo de su celda,
     ±0,1 mm. En una etiqueta ESC la «celda» es la caja que se le reservó al colocarla. Si
     se sale, error con el campo, el texto y cuántos mm se sale por cada lado, por ejemplo:

     ```
     - texto 'no_plano': «ERCO-PSF-CIV-PL-0001» se sale de su celda X 690.90 a 730.54, Y 13.50 a 20.10 0.30 mm por la derecha (medido en el PDF: X 691.50 a 730.84, Y 14.81 a 18.71; tolerancia ±0.1 mm)
     ```

   Si todo pasa, lo renombra a la salida; si algo falla, borra el temporal y no queda PDF.
9. Imprime un resumen: cada detalle con su posición final, la rosa, ESCALA y REV., las
   etiquetas, las advertencias y la ruta del PDF.

Si el PDF de salida ya existe, `componer` no lo pisa salvo con `--sobrescribir`. `--guias`
dibuja las zonas del formato como en `colocar`.
