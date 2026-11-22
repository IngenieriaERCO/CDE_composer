# Formato de plano.json (versiones 1 a 5)

Un `plano.json` dice **qué detalles van en una hoja y dónde** y, desde la versión 2, **qué
se escribe en el rótulo** y **dónde va la rosa de los vientos**. Lo lee el comando
`componer`:

```powershell
python -m componedor.cli componer planos/mi_plano.json --salida resultados/mi_plano.pdf [--sobrescribir] [--guias]
python -m componedor.cli componer planos/mi_plano.json --config componedor.json [--sobrescribir] [--codigo-avisos]
```

Con `--config`, el formato es el de `componedor.json` (aunque el plano indique otro; se avisa)
y el PDF va a `resultados/<nombre del plano>.pdf`; es lo que hace `Componer.bat`. Las demás rutas
siguen siendo relativas a la carpeta del plano.json.

El editor HTML (`editor.html`) lo escribe arrastrando y soltando, pero el componedor
**siempre** lo revalida todo: el editor nunca es la fuente de la verdad.

- **Versión 1**: solo detalles. Sigue siendo válida.
- **Versión 2** (subfase 4.1): lo mismo más `rotulo`, `rosa_vientos` y, en cada detalle,
  `etiqueta_escala`. Todo eso es opcional.
- **Versión 3** (integración con el exportador, etapa 2): la versión 2 más bloques de un DXF
  colocados en el editor y **todavía sin exportar**. El editor la escribe solo cuando el plano
  tiene alguno; `componer` la lee, pero no la compone hasta que estén exportados. Ver
  [Bloques de un DXF sin exportar](#bloques-de-un-dxf-sin-exportar-versión-3).
- **Versión 4** (ortofoto, etapa 1): la versión 3 más `ortofoto`, la ortofoto de fondo del
  plano, detrás de **todos** los detalles. Ver [Ortofoto de fondo](#ortofoto-de-fondo-versión-4).
- **Versión 5** (ortofoto por detalle): la versión 4 más `"ortofoto": true` en cada detalle que la
  lleva detrás. Ver [Ortofoto por detalle](#ortofoto-por-detalle-versión-5).

## Ejemplo (versión 2)

Archivo `planos/mi_plano.json`:

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

| Campo del plano | Tipo | Celda (A1 ERCO) |
|---|---|---|
| `localizacion_escala` | texto | ESC del recuadro de localización. Por defecto **`DEFINIR`**. Se escribe a mano. |
| `localizacion_imagen` | objeto | La imagen de localización (PNG o JPG) en su recuadro. Ver «Imagen de localización». |
| `este`, `norte` | texto | Coordenadas de la localización. |
| `titulo` | texto o lista de hasta 3 líneas | Título del plano (2,5 mm; se puede reducir hasta 2,0 mm). |
| ~~`disenador`, `revisor`~~ | — | **Retirados** (plantilla v3: la franja del logo solo lleva el logo). Un plano viejo que los traiga se compone igual: se ignoran con un solo aviso. |
| `revisiones` | lista de objetos | Tabla de revisiones (ver abajo). |
| `firmas` | objeto por fila | Tabla DIBUJÓ / DISEÑÓ / REVISÓ / APROBÓ (ver abajo). |
| `hoja`, `de` | texto o entero | HOJA __ DE __ (las dos celdas tienen el mismo rango en X, 812,9–827,4 mm, y van centradas: los dos valores quedan uno debajo del otro). |
| `no_plano` | texto | No. PLANO. |
| `notas` | objeto | `{"archivos": [...], "adicionales": [...]}`: notas numeradas (ver «Notas»). |
| `convenciones` | lista (máx. 24) | `[{"simbolo": "corte"}, {"simbolo": "via_existente", "descripcion": "…"}]` (ver «Convenciones»). |
| `escala` | **calculada** | No se escribe: es la escala de los detalles si todos tienen la misma (`1:1.000`), si no `INDICADAS`. |
| `rev` | **calculada** | No se escribe: si hay una revisión con `ver` "0" (emisión final, para construcción), REV. = 0; si no, la mayor letra llena entre C, B y A (emisiones previas); sin revisiones, vacía. Orden en el formato: A < B < C < 0. |

**Revisiones**: cada revisión lleva su propia letra `"ver"` (`"0"`, `"A"`, `"B"` o `"C"`) y
se escribe en **la fila de esa letra** (no por orden de llegada); la letra se imprime en la
columna VER solo en las filas llenas. Columnas: `fecha`, `descripcion`, `dibujo`, `diseno`,
`reviso`, `aprobo` (todas opcionales). Letras repetidas: error. Las columnas DIBUJÓ a APROBÓ
son angostas (unos 10 mm útiles): use iniciales.

**Firmas**: `{"dibujo"|"diseno"|"reviso"|"aprobo": {"nombre", "matricula", "firma", "fecha"}}`.
`firma` es texto opcional (por defecto vacía) **o una imagen**: `{"imagen": "<persona>"}` (ver
«Firma con imagen»). La fila REVISÓ admite 2 líneas en cada celda
(`"nombre": ["ANDRÉS GÓMEZ", "(DIRECTOR TÉCNICO)"]`).

### Imagen de localización (`rotulo.localizacion_imagen`)

Un PNG o JPG (exportado de QGIS, por ejemplo) en el recuadro LOCALIZACIÓN del rótulo. La elige
«Cargar imagen de localización» del editor
([editor.md](editor.md#2h-imagen-de-localización-con-servidor-local)). El plano guarda solo la
ruta, el tamaño y la fecha del archivo; **la imagen nunca va dentro del plano.json**:

```json
"rotulo": {
  "localizacion_imagen": {"archivo": "../qgis/localizacion.png", "bytes": 482113,
                          "modificado": "2026-11-19T15:02:11Z"},
  "localizacion_escala": "1:25.000"
}
```

- `archivo`: relativo a la carpeta del plano (`.png`, `.jpg` o `.jpeg`). `bytes` y `modificado`
  son opcionales, pero sin ellos no se puede saber si el archivo cambió.
- **Recuadro** (A1 ERCO): X 673,4 a 827,3, Y 455,8 a 570,2 mm, entre el título «LOCALIZACIÓN» y
  la fila de «ESC:»; no tapa la escala ni las coordenadas. Lo define el formato (campo de tipo
  `"imagen"`).
- **Ajuste**: entera, centrada y **sin deformar**; lo que sobra queda en blanco.
- **Resolución**: un PNG con más de ~300 ppp en el papel se reduce a 300 ppp (sin pérdida); con
  menos, no se agranda. Un JPG va **tal cual**, sin recomprimir.
- **Escala**: `localizacion_escala` se escribe a mano. Si hay imagen y la escala está vacía, sale
  «DEFINIR» y `componer` lo avisa. Este y Norte también se escriben a mano.
- Los archivos `.pgw` / `.jgw` (georreferencia) no se leen por ahora.

`componer` usa el **original** si existe y coincide con el plano (mismo tamaño y fecha) y deja
una **copia** al lado del plano: `<nombre del plano>_localizacion.png` (o `.jpg`). Si el original
no está o cambió, usa esa copia y lo dice en una advertencia, como con la ortofoto. Si tampoco
hay copia, **no se compone** y el error dice qué hacer. La imagen va debajo de los textos del
rótulo, y la verificación del PDF comprueba que esté en su recuadro (±0,1 mm), con los píxeles
esperados y, si es JPG, que siga siendo el JPEG original.

### Firma con imagen (subfases 4.2d a 4.2f)

```json
"firmas": {
  "dibujo": {"nombre": "LUIS Á. NÚÑEZ P.", "firma": {"imagen": "Luis Ángel Núñez"}},
  "reviso": {"nombre": "ANDRÉS GÓMEZ", "firma": {"imagen": "Andrés Gómez/azul"}},
  "diseno": {"nombre": "MARÍA JOSÉ OCAÑA", "firma": "MJO"}
}
```

- **Una carpeta por persona** (subfase 4.2f) dentro de alguna de las carpetas de
  `rotulo.carpeta_firmas` del formato (A1 ERCO: solo `firmas/` en la raíz de Componedor, **fuera de
  git**):

  ```text
  firmas/
    Luis Ángel Núñez/
      firma.png
    Andrés Gómez/
      firma.png
      azul.png
  ```

  - `{"imagen": "<persona>"}` usa `<persona>/firma.png`. Si no hay `firma.png` y la carpeta
    tiene **un solo** PNG, usa ese; si tiene **varios**, error: nombre uno `firma.png` o use
    `{"imagen": "<persona>/<archivo>"}`.
  - `{"imagen": "<persona>/<archivo>"}` (sin `.png`) elige una **variante** concreta.
  - **Nombres**: letras (con tildes y ñ), números, espacio, `_` y `-` (p. ej. «Luis Ángel
    Núñez»), sin espacios al principio ni al final. Se rechazan `..`, rutas absolutas, `\`,
    `:`, puntos y cualquier separador que no sea el **único** `/` entre persona y archivo.
  - En Windows la búsqueda **no distingue mayúsculas** («luis ángel NÚÑEZ» encuentra «Luis
    Ángel Núñez»); las tildes se comparan normalizadas.
  - Si la misma persona tiene carpeta en dos de las carpetas de firmas, error.
- Solo la columna **FIRMA** la acepta (`"acepta_imagen": true` en el formato); en cualquier
  otra celda es error. El plano.json sigue en versión 2.
- **El archivo**: PNG de hasta **600 × 200 px** y **100 KB**. Sin canal alfa (transparencia) se
  usa, pero con **advertencia**: su fondo blanco tapa las líneas de la celda.
- **Caja de la firma** (subfase 4.2e): la celda FIRMA da solo unos 17,0 × 3,3 mm útiles, así
  que la firma puede ser **más alta que su fila** y montarse sobre las filas vecinas:
  - ancho: el de la columna FIRMA menos 0,6 mm por lado (17,0 mm), como antes;
  - alto: **max(`alto_max_mm`, alto útil de su fila)** (`alto_max_mm` en la columna `firma`
    del formato; A1 ERCO: **5,0 mm**). DIBUJÓ, DISEÑÓ y APROBÓ (3,3 mm útiles) usan 5,0 mm;
    REVISÓ, cuya fila tiene 7,9 mm útiles, usa su propia altura;
  - centrada en **su** fila y, si se saldría del **cuerpo** de la tabla de firmas (Y 20,9 a
    43,5 menos 0,6 mm), **corrida hacia adentro**: nunca sobre el encabezado (la etiqueta
    «FIRMA») ni fuera de la tabla. Por eso la de DIBUJÓ (primera fila) se corre hacia abajo y
    la de APROBÓ (última) hacia arriba;
  - los textos de las otras columnas (NOMBRE, MATRÍCULA, FECHA) no se tocan.
- **Colocación**: proporcional y centrada en su caja y **nunca más grande que su tamaño a
  300 ppp** (una imagen chica queda chica, nunca pixelada). Una firma de 600 × 200 px queda
  de 15,0 × 5,0 mm en DIBUJÓ, DISEÑÓ o APROBÓ y de 17,0 × 5,67 mm en REVISÓ. Se inserta con
  su **máscara de transparencia** (SMask), no con fondo blanco; comprimida sin pérdida.
- **Firmas que se montan**: si las firmas de dos filas quedan de verdad una sobre otra (sus
  rectángulos se cruzan), **advertencia** con las dos filas y el tamaño del cruce; no es
  error. Con 5,0 mm, dos firmas de 600 × 200 px en DIBUJÓ y DISEÑÓ se cruzan 1,35 mm.
- **Errores juntos**: persona inexistente (dice en qué carpetas se buscó), con carpeta en dos
  lugares, sin PNG, con varios PNG y ninguno `firma.png`, variante inexistente (dice qué PNG
  tiene), no es PNG, más de 600 × 200 px o de 100 KB, nombre o ruta inválidos, campo
  desconocido, celda que no acepta imagen. Los mensajes nombran la persona y las rutas.
- **Verificación en el PDF**: la hoja tiene **exactamente** las imágenes de la plantilla (el
  logo) **más una por firma**; los detalles siguen sin poder traer imágenes. Cada firma: su
  rectángulo igual al esperado y dentro de su caja ampliada (±0,1 mm), **sin pisar el
  encabezado** ni salirse del cuerpo de la tabla, con máscara de transparencia, y es la del
  archivo leído (la máscara es byte a byte el canal alfa del PNG; sin alfa, se comparan los
  píxeles; el resumen informa el SHA-256 si falla).

**Privacidad**: una firma en imagen es un dato personal y se puede copiar desde cualquier
archivo donde esté. Por eso: las imágenes van **fuera de git** (toda la carpeta `firmas/` y
`data/` en `.gitignore`), **no se incrustan en editor.html**, el plano.json solo guarda el
nombre de la persona (no la imagen) y conviene ponerlas **solo en los PDF emitidos** (no en
borradores), con la autorización de cada persona. Cada persona tiene su propia carpeta: es
fácil ver qué firmas hay de quién y retirarlas.

El editor puede **preparar** la firma (botón «Cargar firma…», subfase 4.3b2: recortar, pasar el
fondo a transparente y achicar a 600 × 200 px / 100 KB). La imagen se procesa **solo en el
navegador**, sin internet; **nunca** se guarda en el editor.html ni en el plano.json, y se
descarta al cerrar el diálogo. Lo único que sale es el archivo `firma.png` que usted guarda
(directo en `firmas/<persona>/` si el navegador lo permite, o descargado para moverlo ahí) y,
en el plano, `{"imagen": "<persona>"}`.

**Fechas**: `componer` escribe las fechas tal como vienen (texto). El formato define cómo las
escribe el editor con su selector de fecha (calendario, subfase 4.3b): `rotulo.formato_fecha`, por defecto
`"dd/mm/aa"` (A1 ERCO); se admiten día, mes y año una vez cada uno, con `aa` o `aaaa`,
separados por `/`, `-` o `.` (p. ej. `"aaaa-mm-dd"`).

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
- El editor (panel «Convenciones», subfase 4.3d) escribe esta lista en el orden elegido y
  agrega `"descripcion"` solo si la persona cambió la de por defecto.
- **Muestras de línea y relleno** (subfase 9a): un renglón también puede ser una muestra que
  `componer` dibuja como **vector** (sin biblioteca), centrada en la casilla del símbolo:

  ```json
  {"tipo": "linea", "descripcion": "RED DE MEDIA TENSIÓN", "color": "#FF0000",
   "grosor_mm": 0.35, "trazo": "discontinua"},
  {"tipo": "relleno", "descripcion": "ZONA VERDE", "color": "#00A000", "opacidad": 0.5}
  ```

  | Clave | Tipo | Valores |
  |---|---|---|
  | `tipo` | texto | `"simbolo"` (lo de siempre; un renglón sin `tipo` es un símbolo), `"linea"` o `"relleno"`. |
  | `descripcion` | texto o lista de líneas | **Obligatoria** en las muestras (no hay descripción por defecto). |
  | `color` | `"#RRGGBB"` | Por defecto `#000000` (línea) y `#808080` (relleno). |
  | `grosor_mm` | número | Solo línea: de 0,05 a 2; por defecto 0,25. |
  | `trazo` | texto | Solo línea: `"continua"` (por defecto) o `"discontinua"` (guiones de 2 mm, huecos de 1 mm). |
  | `opacidad` | número | Solo relleno: mayor que 0 y hasta 1; por defecto 1. |

  La línea mide 13 mm y el relleno 13 × 6 mm (si la casilla es más chica, se acortan al
  espacio útil). Las muestras pueden repetirse; la biblioteca solo hace falta si hay símbolos.
  Al componer se verifica en el PDF que cada muestra sea un solo trazo en su casilla (±0,1 mm)
  con su color, grosor, trazo y opacidad.
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

**La biblioteca** (`extraer-simbolos`, una sola vez por plano de origen):

```powershell
python -m componedor.cli extraer-simbolos "C:\...\PRGE-25-0044-CIV-PL-101_A_Plano_Movimiento_de_Tierras.pdf"
```

Lee la leyenda de la página 1 del plano (misma rejilla que el rótulo v2), la normaliza
(quita el /Rotate 270), aísla cada símbolo con redacciones (`show_pdf_page` con `clip` no
quita contenido, solo lo oculta) y lo copia como vector a `simbolos/biblioteca/<id>.pdf`, un
PDF por símbolo; verifica que cada uno tenga los mismos trazos y la misma caja (±0,1 mm)
que en el plano y escribe `simbolos/indice.json` versión 2 (conserva los ids, descripciones y
opacidades que ya tenga, y deja tal cual los símbolos de otro origen). Los PDF salen de un plano
de ERCO y **no se versionan**; el índice sí.

#### Biblioteca de símbolos versión 2 (subfase 9b)

```json
{"version": 2,
 "simbolos": [
   {"id": "corte", "descripcion": "CORTE", "tipo": "vector",
    "tamano_mm": [17.695, 7.578], "margen_mm": 0.5, "trazos": 5,
    "origen": {"clase": "plano_pdf", "plano": "PRGE-25-0044-CIV-PL-101_A_Plano_Movimiento_de_Tierras.pdf",
               "pagina": 1, "casilla": 11, "rect_mm": [674.314, 148.124, 692.009, 155.702]},
    "fecha": "2026-11-21"}
 ]}
```

| Clave | Qué es |
|---|---|
| `id` | Letras, números, «_» o «-». Es el nombre de su PDF: `biblioteca/<id>.pdf`, junto al índice. No se repite. |
| `descripcion` | La descripción por defecto en la leyenda. |
| `tipo` | `"vector"` (las imágenes llegan en otra subfase). |
| `tamano_mm` | `[ancho, alto]` del dibujo, sin el margen. La página del PDF mide eso más `margen_mm` por lado. |
| `margen_mm` | Margen alrededor del dibujo en su página (0,5 en los de hoy). |
| `trazos` | Cuántos trazos tiene el PDF: `componer` lo verifica en la casilla. |
| `opacidad` | Opcional, mayor que 0 y hasta 1 (por defecto 1). |
| `origen` | De dónde salió. `"clase": "plano_pdf"`: el plano, la página, la casilla de su leyenda y la caja del dibujo en ese plano. |
| `fecha` | Cuándo entró a la biblioteca (`AAAA-MM-DD`). |

- La carpeta de la biblioteca se elige con `carpeta_simbolos` en `componedor.json` (para el
  editor y para `componer --config`); sin ella, la del formato (`biblioteca` del campo de
  convenciones, `../simbolos/indice.json`).
- Un índice con problemas (id con espacios o repetido, tipo, tamaño, fecha, origen o trazos
  mal) los dice todos juntos; si falta el PDF de un símbolo, dice cuáles y cómo arreglarlo.
- **Versión 1** (un solo `convenciones_erco.pdf`, una página por símbolo) se sigue leyendo igual.
  `migrar-simbolos --config componedor.json` la pasa a la 2: copia cada página **tal cual** (no
  redibuja), verifica que cada PDF nuevo tenga los mismos trazos en el mismo lugar y solo entonces
  escribe el índice nuevo y **mueve** el PDF viejo y una copia del índice viejo a
  `_para_borrar/simbolos_v1_<fecha>/`. Si algo falla, no cambia nada.

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
  línea; campos desconocidos son error). Un texto vacío se omite (no se numera). El editor
  (panel «Notas», subfase 4.3c) escribe aquí las notas elegidas del catálogo y las escritas a
  mano, **copiadas** y en el orden de su lista; no toca `archivos`.
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

## Bloques de un DXF sin exportar (versión 3)

Con «Cargar DXF» (editor abierto con `Abrir editor.bat`) se ponen en la hoja **cajas exactas**
de bloques del DXF: la página que tendrá el paquete al exportarlo a 1:N. Mientras no se
exporten, el plano.json los guarda así:

```json
{
  "version": 3,
  "formato": "../formatos/A1_ERCO.json",
  "plantilla": null,
  "dxf": [
    {"id": "d1", "archivo": "../data/input/dxf/GUAMO_prueba.dxf",
     "sha256": "4b1d…(64 caracteres)", "bytes": 6781020, "unidades": "m", "margen_mm": 5}
  ],
  "detalles": [
    {"id": "Corte_A", "manifiesto": "../data/input/corte_a.manifest.json", "posicion_mm": [30, 40]},
    {"id": "BLOQUE1",
     "origen": {"dxf": "d1", "bloque": "BLOQUE1", "handle": "50CA", "ocurrencia": 1,
                "escala": "1:5000", "tamano_m": [957.18, 1350.019], "caja_exacta": true},
     "centro_mm": [342.55, 297.0]}
  ]
}
```

- **`dxf`** (lista): cada DXF que usan los bloques pendientes.
  - `id`: lo nombra (`d1`, `d2`…).
  - `archivo`: ruta del DXF, relativa a la carpeta del plano (o absoluta si está en otro disco).
  - `sha256`: el del DXF cuando se cargó (64 caracteres hexadecimales en minúsculas).
  - `margen_mm`: el margen de página con que se exportará.
  - `bytes` y `unidades`: informativos.
- **Un detalle pendiente** lleva `origen` y `centro_mm` en lugar de `manifiesto` y
  `posicion_mm` (y, como en la versión 2, `etiqueta_escala` opcional):
  - `origen.dxf`: el `id` de su DXF en la lista.
  - `origen.bloque`, `origen.handle` (el del INSERT, hexadecimal en mayúsculas) y
    `origen.ocurrencia` (1, 2… si el bloque se repite): qué referencia es.
  - `origen.escala`: `"1:N"`, con N entero de 1 a 100000. Puede no ser normalizada (el usuario
    la escribió a mano, p. ej. `"1:3500"`): se usa tal cual.
  - `origen.tamano_m`: `[ancho, alto]` real en m. Con él y la escala sale la página:
    **página_mm = tamaño_m × 1000 ÷ N + 2 × margen_mm** por eje (fórmula del contrato del
    trabajador).
  - `origen.caja_exacta`: `false` si la caja es aproximada (bloques anidados girados); entonces
    la página real puede salir algo menor.
  - `centro_mm`: el **centro** de la página en la hoja (mm de papel, Y hacia arriba). Se guarda
    el centro y no la esquina porque la página exacta la dará el manifiesto al exportar; el
    centro no cambia.
- En un mismo plano se pueden mezclar detalles exportados y pendientes; el orden de `detalles`
  sigue siendo el de apilado.

`componer` (y `Componer.bat`) **no compone un plano con pendientes**. Dice cuáles faltan, a qué
escala, de qué DXF y si alguno no cabe, por ejemplo:

```
Error: No se compone el plano: tiene 2 bloque(s) de DXF sin exportar todavía (plano versión 3). Componer necesita el paquete (PDF + manifiesto) de cada uno:
- 'BLOQUE1': bloque «BLOQUE1» (handle 50CA) a 1:5000, de GUAMO_prueba.dxf
- 'Carro': bloque «Carro frontal 1» (ocurrencia 2, handle 1A3) a 1:50, de GUAMO_prueba.dxf — NO CABE en 'area_dibujo' a 1:50 (página 650.0 × 90.0 mm; sobran 10.3 × 0.0 mm): cambie la escala en el editor
Expórtelos primero (desde el editor, cuando esté la exportación —etapa 3—, o con cde-exporter) y vuelva a componer.
```

## Ortofoto de fondo (versión 4)

Una ortofoto (GeoTIFF) por plano, **detrás de todos los detalles** y recortada a la página de
cada uno; fuera de los detalles, nada. La elige «Cargar ortofoto» del editor
([editor.md](editor.md#2g-ortofoto-de-fondo-con-servidor-local)):

```json
{
  "version": 4,
  "formato": "../formatos/A1_ERCO.json",
  "detalles": [ … ],
  "ortofoto": {"archivo": "../data/input/ortofotos/Foto_tunez.tif", "bytes": 3445480,
               "modificado": "2026-11-18T21:26:25Z", "crs": null,
               "crs_dibujo": "EPSG:9377", "opacidad": 0.6}
}
```

- `archivo` (obligatorio): el `.tif`/`.tiff`, relativo a la carpeta del plano (o absoluto).
- `bytes` y `modificado` (fecha de modificación, UTC, al segundo): los del archivo cuando se
  eligió. Opcionales. Sirven para saber si el archivo que hay es el mismo.
- `crs`: el sistema de la ortofoto **elegido a mano**, solo cuando el archivo no trae el suyo
  (si lo trae, manda el del archivo y aquí va `null`). Siempre `"EPSG:<código>"`.
- `crs_dibujo`: el sistema de coordenadas del DXF. El editor lo prellena con el del DXF
  (`dxf.crs`, del GEODATA), pero lo que se guarda es lo que quedó en el selector. `null`
  mientras no se elija.
- `opacidad`: de 0 a 1 (1 = opaca, por defecto).

Nunca se supone un sistema: sin `crs_dibujo` (o sin el de la ortofoto, si el archivo no lo
trae) el editor no la ubica y lo avisa en amarillo.

### Ortofoto por detalle (versión 5)

Desde la versión 5 la ortofoto va solo detrás de los detalles que la piden (casilla «Usar
ortofoto» del editor). Un perfil u otro bloque que no la necesita queda sin ella:

```json
"detalles": [
  {"id": "via_tunez", "manifiesto": "…", "posicion_mm": [40, 90], "ortofoto": true},
  {"id": "perfil", "manifiesto": "…", "posicion_mm": [300, 40]},
  {"id": "mesa", "origen": {…}, "centro_mm": [560, 60], "ortofoto": true}
]
```

- `ortofoto` (`true` o `false`, opcional): va en detalles exportados y en bloques pendientes.
  Sin la clave es `false`.
- Si un detalle lleva `"ortofoto": true`, el plano debe tener la sección `ortofoto`; si no, es
  error.
- **Migración desde la 4**: la versión 4 ponía la ortofoto detrás de todos. Un plano versión 4
  con `ortofoto` se lee como si **todos** sus detalles la usaran (en `componer` y en el editor).
  El editor lo avisa y lo guarda en versión 5, con todos los detalles marcados.
- Si ninguno la usa, `componer` sale sin ortofoto (con advertencia) y ni siquiera necesita el
  archivo.

### Extender a todo el layout y cuadrícula de coordenadas (versión 5)

```json
"ortofoto": {"archivo": "…", "crs_dibujo": "EPSG:9377", "opacidad": 1,
             "extender": true, "cuadricula": {"visible": true, "intervalo_m": 50}}
```

- `extender` (opcional, `false`): con **un solo** detalle con ortofoto, la foto cubre toda el
  área de dibujo con el mismo mapeo CAD → papel de ese detalle (no se mueve ni se escala nada;
  solo cambia el recorte). Los detalles sin ortofoto llevan un fondo blanco del tamaño de su
  página. Con otro número de detalles no cuenta: cada una va recortada a su página (advertencia).
- `cuadricula` (opcional): `visible` (`false` por defecto) e `intervalo_m` (m, > 0; sin él, el de
  `componedor.json` → `ortofoto.cuadricula_intervalo_m`, 50). Va en la página de cada detalle con
  ortofoto, o en toda el área de dibujo si se extiende, también donde la foto no cubre. Las
  coordenadas son las del sistema del dibujo.
- Estilo copiado del plano de AutoCAD de PRGD (`data/input/PRGD-26-1377-GEN-PL-101_1_V0.pdf`):
  - líneas negras de 0,085 mm que cruzan toda la foto;
  - una etiqueta en cada línea y en los dos extremos, en ArialMT de 10 pt (cifras de 2,53 mm),
    negra, con el formato «4705900.000» (3 decimales, sin letras);
  - las etiquetas van fuera de la foto, sin fondo ni halo, centradas en una franja de 10 mm: la
    del marco al área de dibujo. El Este va abajo y arriba; el Norte, girado a los lados, se lee
    de abajo hacia arriba;
  - una etiqueta que se salga del marco o choque con el rótulo, otro detalle, la rosa, una
    etiqueta «ESC» u otra etiqueta se omite (y se avisa);
  - la cuadrícula va debajo de los vectores de los detalles, y la rosa siempre encima de la foto.

### Cómo la pone `componer`

- **Qué archivo usa**: el original, si existe y coincide con el plano (mismo tamaño y fecha, lo
  que el plano guardó). Si no está o cambió, usa la **copia reducida** de la carpeta del plano
  y lo dice en una advertencia. Si tampoco hay copia que sirva (de esa misma ortofoto y en el
  mismo sistema del dibujo), **no se compone** y el error dice qué hacer.
- **Sistemas**: sin `crs_dibujo`, o con una ortofoto sin sistema y sin `crs`, **no se
  compone** (error claro). Nunca se supone uno. Si son distintos, se reproyecta.
- **Dónde**: por cada detalle que la usa, su página en la hoja se lleva a CAD con la matriz de su
  manifiesto; la ortofoto de esa caja va **exactamente sobre la página**, debajo del detalle.
  Orden: plantilla (con la rosa y los símbolos) → ortofoto → detalles → rótulo.
- **Cómo**: a `ppp` píxeles por pulgada de papel (300) en **mosaicos de 1024 px**, cada uno un
  JPEG (calidad `calidad_jpeg`, 85) que entra tal cual en el PDF. Donde no hay foto, o con
  opacidad menor que 1, el mosaico lleva una máscara de transparencia. Un mosaico sin foto no
  se pone. Se lee la ortofoto **por ventanas** (solo lo de cada mosaico, reducido con las
  pirámides si las hay), así la memoria no depende del tamaño del archivo.
- **Los detalles siguen siendo vectores**: la ortofoto son imágenes aparte. La verificación
  del PDF cuenta exactamente las imágenes de la plantilla, las firmas y los mosaicos (cada uno
  JPEG y en su rectángulo, ±0,1 mm), y mide el dibujo de cada detalle como siempre.
- **Avisos**: la ortofoto no cubre un detalle; un detalle con fondo blanco (paquete antiguo)
  la tapa; un dibujo girado en su página no la lleva.

### Copia reducida (`<plano>_ortofoto/`)

Cada vez que compone con el original, `componer` deja al lado del plano.json la carpeta
`<nombre del plano>_ortofoto/` con:

- un GeoTIFF por detalle (JPEG en mosaicos de 512 px, con máscara), ya en el sistema del
  dibujo. Cubre la página del detalle **más un 10 % por lado** (aguanta mover el detalle o
  cambiarle algo la escala);
- con la resolución que pide el PDF, pero **nunca más fina que la ortofoto original**
  (agrandarla no agrega nada);
- `indice.json`: de qué ortofoto salió (nombre, tamaño, fecha), sistema, ppp y la caja de cada
  archivo.

Si la copia ya está al día no se reescribe. Si cambió, la nueva se escribe aparte y reemplaza a
la vieja (es un archivo generado, como el PDF). Con ella se puede volver a componer el plano en
otro PC sin la ortofoto original, que puede pesar varios GB.

## Qué hace `componer` con el plano

1. Lee y valida el plano.json. Si es versión 3 y tiene bloques sin exportar, se detiene y dice
   cuáles (sección anterior). Si es versión 4 con ortofoto, elige el original o la copia (o se
   detiene si no hay ninguna que sirva).
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
7. Crea la hoja con la plantilla, quita la rosa y la vuelve a dibujar donde corresponda, pone
   la ortofoto (si hay), inserta los detalles en orden (sin reescalar, como vector) y escribe
   los textos.
8. Guarda en un archivo temporal y **verifica** el PDF: el dibujo de cada detalle está donde
   dice el plano (±0,1 mm, medido con `get_drawings()` sin el fondo blanco), el marco del
   rótulo no se movió, no hay más imágenes que las de la plantilla, una por cada firma en
   imagen (cada firma en su celda, con su máscara y la del archivo) y una por cada mosaico de
   la ortofoto (JPEG, en su rectángulo ±0,1 mm), la rosa quedó donde se pidió (sus trazos son
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
