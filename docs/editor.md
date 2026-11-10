# Editor de planos (editor.html)

Un editor visual para armar un plano sin escribir coordenadas a mano: la hoja A1 completa
de fondo, el rótulo bloqueado y los detalles se arrastran dentro del área de dibujo, como en
el Layout de AutoCAD. Guarda un `plano.json`; el PDF final lo genera `componer`.

> El editor es solo una ayuda. `componer` vuelve a validar todo; si hay una diferencia con
> lo que muestra el editor, manda `componer`.

## 1. Generar el editor

```powershell
python -m componedor.cli editor data/input --formato formatos/A1_ERCO.json --salida data/editor
```

- `data/input`: carpeta con los paquetes del exportador (PDF + manifiesto).
- `--notas <carpeta>` (opcional, subfase 4.3a): las **notas típicas** del catálogo del rótulo.
  Se leen todos los `.txt` de la carpeta y sus subcarpetas, con las mismas reglas que
  `componer` (una nota por línea, viñetas con `- `, comentarios con `#`). **Cada subcarpeta es
  un grupo** del catálogo y su nombre es el título del grupo (`vias`, `mov_tierras`,
  `hidraulica`…); los `.txt` de la carpeta raíz van en el grupo **«General»**. Los problemas de
  lectura (archivo que no está en UTF-8, viñeta antes de una nota…) se muestran al generar el
  editor y quedan en los datos.

  ```powershell
  python -m componedor.cli editor data/input --formato formatos/A1_ERCO.json --salida data/editor --notas "C:\...\notas_tipicas"
  ```
- `data/editor`: carpeta del editor. Queda ahí `editor.html` (más `editor_datos.json`,
  `plantilla.png` y `miniaturas/`, que son los mismos datos de `preparar-editor`).
- Si la carpeta ya tiene contenido, agregue `--sobrescribir`: se reemplaza solo lo que genera
  el editor (un `plano.json` guardado por usted no se toca).

`editor.html` es **un solo archivo**: trae dentro el HTML, el estilo, el programa, los datos y
las imágenes. Se abre con **doble clic** en Edge o Chrome; no necesita servidor ni internet y
no contiene ninguna dirección externa. Las imágenes son solo para mostrar: el PDF final sale
vectorial.

Vuelva a generar el editor cuando cambien los paquetes de la carpeta de entrada.

## 2. Usarlo, paso a paso

1. Abra `editor.html` (doble clic).
2. En el panel izquierdo, **Detalles disponibles**: pulse **Agregar al plano**. El detalle
   aparece centrado en el área de dibujo. Puede agregar el mismo detalle varias veces: cada
   copia lleva un id único (`perfil_k0010`, `perfil_k0010_2`, …) y se corre 10 mm para que se
   vea.
3. **Arrastre** el detalle con el mouse. Su PÁGINA completa siempre queda dentro del área de
   dibujo: si lo lleva al rótulo, se detiene en el borde (la misma regla estricta que usa
   `componer`, así que el editor nunca produce un plano que `componer` rechace por salirse).
4. Para una posición exacta, seleccione el detalle y escriba **X** e **Y** en el panel
   **Selección**: son mm de papel de la esquina inferior izquierda de la PÁGINA del detalle (el
   `posicion_mm` del plano.json), con origen abajo a la izquierda de la hoja e Y hacia arriba,
   como en AutoCAD.
5. Revise la lista **Advertencias** (ver abajo).
6. Pulse **Guardar plano** (o Ctrl+S) y guárdelo **en la misma carpeta que `editor.html`**.
7. Copie el comando que aparece abajo (**Copiar comando**) y ejecútelo para generar el PDF:

   ```powershell
   python -m componedor.cli componer "C:\...\data\editor\plano.json" --salida "C:\...\data\editor\plano.pdf"
   ```

## 2b. Rosa de los vientos: mover u ocultar

La rosa de la plantilla se puede mover o quitar, como en el Layout se mueve un bloque:

- **Arrastrarla** con el mouse, igual que un detalle (con el **Paso** de ajuste elegido).
  Siempre queda **completa dentro del área de dibujo**: si la lleva afuera, se detiene en el
  borde. Al hacer clic queda seleccionada (borde azul) y se mueve también con las **flechas**
  (Shift: 10 pasos).
- Panel **Rosa de los vientos** (a la derecha):
  - casilla **Mostrar rosa de los vientos**: desmarcada, la rosa desaparece de la hoja, no
    sale en el PDF, **no genera advertencias** y su zona queda libre;
  - **X** e **Y**: esquina inferior izquierda del rectángulo de la rosa (38,98 × 39,00 mm), en
    mm de papel;
  - **Restaurar posición**: la vuelve a su lugar original (615,94; 25,21) y la muestra.
- La rosa va **debajo** de los detalles (como en el PDF): donde un detalle la tapa, el clic
  toma el detalle.
- **Lo que se ve es lo que sale**: la imagen de fondo (`plantilla.png`) ya viene **sin** la
  rosa; el editor la dibuja solo en su posición actual, y `componer` hace lo mismo en el PDF
  (la quita de la plantilla y la vuelve a dibujar como vector donde usted la dejó).
- Se guarda en el plano.json como `"rosa_vientos": {"visible": ..., "posicion_mm": [x, y]}`.

## 2c. Rótulo: formularios (subfase 4.3b; notas y convenciones llegan en la 4.3c y 4.3d)

Generar el editor con todo lo del rótulo:

```
python -m componedor.cli editor data/input --formato formatos/A1_ERCO.json --salida data/editor ^
    --notas "C:\...\notas_tipicas" --firmas firmas --proyecto "C:\...\proyecto.json"
```

- `--notas`: catálogo de notas típicas (subcarpetas = grupos).
- `--firmas <carpeta>`: la carpeta de firmas (una subcarpeta por persona). El editor solo
  recibe los **nombres** de las personas, para elegirlos en una lista; **las imágenes nunca se
  incrustan** en editor.html. Se omiten, con aviso, las carpetas sin PNG o con un nombre que
  `componer` no aceptaría.
- `--proyecto <proyecto.json>`: datos que se repiten en todos los planos del proyecto
  (diseñador, revisor, nombres y matrículas de las firmas, prefijo del No. PLANO). Esquema en
  [formato_proyecto.md](formato_proyecto.md). **Solo prellena un plano NUEVO**; al guardar,
  los valores quedan copiados en el plano.json (`componer` no lee proyecto.json). Un plano que
  se abre no se toca. Si el proyecto tiene errores, el editor no se genera y se listan todos.

Panel **Rótulo** (a la derecha), por secciones que se pliegan:

- **Datos del plano**: Título, No. PLANO, HOJA, DE, coordenadas ESTE/NORTE, ESC. de
  localización, Diseñador y Revisor. Las celdas de varias líneas (Título 3, Diseñador y Revisor
  3, REVISÓ 2) usan una caja de varios renglones: **una línea por renglón**. Debajo, **ESCALA**
  y **REV.** calculadas, de solo lectura, con la misma regla que `componer` (REV.: «0» si existe
  la emisión 0; si no, la letra más alta entre C, B y A; vacía sin revisiones).
- **Revisiones**: una tarjeta por revisión con **VER.** (lista con las letras libres: 0, A, B o
  C, sin repetir), Fecha, Descripción, Dibujó, Diseñó, Revisó y Aprobó; botones **Quitar** y
  **Agregar revisión** (toma la primera letra libre; cámbiela en la lista).
- **Firmas**: DIBUJÓ, DISEÑÓ, REVISÓ y APROBÓ con Nombre, Matrícula, Firma y Fecha. La firma es
  **Texto** (p. ej. iniciales) o **Persona**: un nombre de la lista de `--firmas` o **«Persona
  nueva…»** (se escribe el nombre de su carpeta: letras con tilde y ñ, números, espacio, «_» y
  «-»); en el plano queda `{"imagen": "<persona>"}` y `componer` busca su PNG (y lo valida).
- **Cargar firma…** (subfase 4.3b2), en cada fila de firmas: prepara el `firma.png` de una
  persona a partir de una foto o un escaneo. Ver «2c-bis».

### 2c-bis. Cargar, recortar y limpiar una firma

En el diálogo **Cargar firma…**:

1. **Imagen**: «Elegir imagen…» o **Ctrl+V** para pegar una imagen copiada (p. ej. un recorte de
   pantalla). Luego **arrastre un rectángulo** sobre la firma para recortarla («Quitar recorte»
   vuelve a la imagen entera).
2. **Limpieza**: el fondo claro pasa a **transparente** con un umbral suave por luminosidad.
   - **Compensar sombras e iluminación despareja** (activada): antes del umbral, el editor
     estima el color del papel en cada zona (máximo por bloques de ~1/40 del lado mayor, cierre
     entre bloques vecinos y suavizado) y divide la imagen por él; así una foto con sombra o con
     luz de un lado queda con el papel blanco y se vuelve transparente.
   - **Umbral automático** (método de Otsu, sobre la imagen ya compensada y recortada): es el
     umbral inicial al cargar la imagen; el botón lo vuelve a calcular.
   - **Control del umbral** de 40 a 250: **bajar el valor = más fondo transparente; si baja
     demasiado, se pierde el trazo fino.**
   - Si **más del 25 %** de los píxeles de la firma quedan opacos, aviso: «Parece que queda
     fondo… Revise el umbral o repita la foto con más luz.»
   - Tinta **en su color** o **en negro**. El resultado se ve sobre un **fondo cuadriculado** (lo cuadriculado
   es lo transparente). Se recorta solo al trazo con 2 px de margen y se achica a un máximo de
   **600 × 200 px** (proporcional); si el PNG pasara de **100 KB**, se achica un 15 % más hasta
   que quepa. Debajo se ve tamaño, peso y transparencia, y la revisión con **los mismos textos
   que `componer`** (firmas.py).
3. **Guardar**: escriba el **nombre de la persona** (las mismas reglas que `componer`: sin
   puntos ni rutas). **Guardar en la carpeta de firmas…** (Edge y Chrome) le pide elegir y
   autorizar la carpeta `firmas/` y escribe `firmas/<persona>/firma.png` (pregunta antes de
   reemplazar una que ya exista). Si el navegador no lo permite, **Descargar firma.png** la deja
   en Descargas y el diálogo dice que debe moverla a `firmas/<persona>/firma.png`. En los dos
   casos la fila queda con `{"imagen": "<persona>"}`. **Solo usar el nombre** pone la persona sin
   guardar imagen (si ya tiene su firma.png).

**Privacidad**: la imagen se procesa **solo en este navegador**, sin internet; **nunca** se
guarda en el editor.html ni en el plano.json, y al **cerrar** el diálogo se descarta (no queda
nada de ella en la página).
- **Fechas**: se escriben a mano o con el **calendario** (ícono a la derecha), que las escribe en
  el `formato_fecha` del formato (A1 ERCO: `dd/mm/aa`, p. ej. 09/11/26).
- **Problemas del rótulo**: validación en vivo con **los mismos textos que `componer`**: tipo
  de valor, salto de línea en una celda de una línea, letras de revisión inválidas o repetidas,
  columnas desconocidas, caracteres que Arial no tiene (p. ej. «中») y una lista de líneas con
  más líneas de las que admite la celda. La casilla con problema se pone en rojo. **Si el texto
  cabe en su celda (y si se reduce) todavía lo dice solo `componer`** (subfase 4.3e).

Reglas al escribir:

- **Vaciar un campo lo quita del plano**: vuelve su valor por defecto (p. ej. «DEFINIR» en ESC.
  de localización, que se ve como texto gris de ejemplo).
- Se respeta la forma que traía el plano: un nombre dado como lista de líneas sigue siendo
  lista; un número (`"hoja": 1`) sigue siendo número si escribe un número.
- Lo que el formulario no sabe mostrar (un campo que el formato no tiene, notas tomadas de
  archivos `.txt`, un valor raro) aparece en **Se conserva sin editar** y se guarda tal cual.
- Las convenciones del plano se conservan; su edición llega en la 4.3d.

Presentación compacta (4.3c): cada revisión con **VER. y Fecha en la misma línea**, la
descripción debajo y **Dibujó / Diseñó / Revisó / Aprobó en una cuadrícula de 2 × 2**; las
revisiones se muestran **en el orden del rótulo** (de arriba abajo: 0, C, B, A), no en el
orden en que se llenaron (el plano.json conserva su orden). En Firmas, **Nombre | Matrícula** en
una fila y **Firma | Fecha** en otra. El **Título crece solo** con el texto, sin barra, hasta
unos 6 renglones.

**Abrir y guardar sin tocar nada deja el plano.json idéntico**; al editar, solo cambia lo
editado. El editor recuerda el plano abierto y solo cambia lo que usted toca: un detalle que
no se movió sale tal como venía (incluso con `"centrar": true`), el formato, la plantilla y el
rótulo se conservan, y la rosa solo se escribe si el plano ya la traía o si usted la movió u
ocultó.

## 2d. Notas (subfase 4.3c)

Panel **Notas** (a la derecha, debajo de Rótulo):

- **Notas del plano**: la lista de lo que irá en la celda NOTAS, con su **número en vivo**
  (1…N; las viñetas no se numeran). Cada nota tiene **↑ subir**, **↓ bajar** y **✕ quitar**, y
  su **texto y sus viñetas se pueden editar**, porque la nota queda **copiada** en el plano (no
  enlazada al .txt). El texto va en una sola línea (Enter no hace salto); `componer` la parte en
  la celda. Viñetas: una por línea.
- Si el plano trae `"archivos"` (notas desde .txt), se muestran como **«Vienen de archivos
  (editar a mano)»** y se conservan intactos: en el PDF van primero, por eso la numeración de
  la lista se ve como «+1.», «+2.»… (sigue después de ellas).
- **Agregar nota a mano**: texto y, si quiere, viñetas (una por línea).
- **Notas típicas**: el catálogo de `--notas`, por grupo (subcarpeta). Cada nota tiene una
  **casilla**: al marcarla pasa al final de «Notas del plano»; al desmarcarla, sale. Una nota ya
  elegida no se repite. Si la línea del .txt traía su propio número («3. …»), se ve el aviso de
  que se quitó.
- Lo elegido se guarda en `rotulo.notas.adicionales`, en el orden de la lista: texto, u objeto
  `{"texto", "vinetas"}` si lleva viñetas. Lo que no se toca sale tal como venía.
- **Problemas de las notas**, en vivo y con los mismos textos que `componer`: forma de la nota,
  saltos de línea, viñetas mal formadas, caracteres que Arial no tiene (la nota queda en rojo) y
  el aviso de número propio. Una nota vacía es un aviso del editor (`componer` la omite sin
  decir nada). **Si las notas caben en la celda todavía lo dice solo `componer`** (4.3e).
- Al abrir un plano, una nota igual a una del catálogo queda con su casilla marcada.
- **Notas que ya vienen de archivos**: si una ruta de `"archivos"` es el **mismo .txt** que uno
  del catálogo (la ruta se compara como la resuelve `componer`: desde la carpeta del
  plano.json, que es la del editor, con `\` o `/`, `.` y `..`, sin distinguir mayúsculas en
  Windows), sus notas típicas aparecen con la **casilla desactivada** y la etiqueta **«ya
  incluida desde archivos»**, para no duplicarlas; la cabecera del .txt dice cómo lo trae el
  plano. Un .txt con el mismo contenido en **otra** carpeta es otro archivo y no cuenta.
- Si una nota de la lista (copiada o a mano) tiene el **mismo texto** que una de esos .txt
  (espacios y número propio normalizados como en `componer`; las viñetas no cuentan), se avisa
  en vivo: **«esta nota ya viene en <archivo> (línea n); saldría dos veces en el plano»**, y la
  nota queda en amarillo. Es un aviso del editor: `componer` la escribiría dos veces.
- El editor solo conoce las notas de los .txt del catálogo (`--notas`); de un .txt de
  `"archivos"` que no está en el catálogo dice «no está en el catálogo: el editor no ve sus
  notas».

## 2e. Convenciones (subfase 4.3d)

Panel **Convenciones** (a la derecha, debajo de Notas):

- **Convenciones del plano** (n de 24): cada una con su **miniatura**, su número de casilla y,
  en vivo, **en qué lugar de la leyenda queda**: «columna izquierda, fila 3»… El llenado es
  por columna, como en `componer`: 1–12 en la columna izquierda y 13–24 en la derecha. Botones
  **↑ subir**, **↓ bajar** y **✕ quitar**; la **descripción se puede editar** (hasta 2 líneas,
  una por renglón). Vacía = la descripción por defecto del índice (se ve en gris).
- **Símbolos disponibles**: los de `simbolos/indice.json`, con su miniatura (PNG incrustado,
  dibujado con su opacidad: `limite_predio_proyectado` al 50 %) y su descripción por defecto.
  Cada uno tiene una **casilla**: marcar = al final de la lista; desmarcar = sale. Un símbolo
  no se repite. Con 24 en la lista, marcar uno más no lo agrega y avisa: «La tabla de
  convenciones está llena: admite 24 (dos columnas de 12). Quite una para agregar otra.»
- Se guarda en `rotulo.convenciones` en el orden de la lista: `{"simbolo": "<id>"}` y
  `"descripcion"` **solo si** usted la cambió respecto de la de por defecto. Lo que no se toca
  sale tal como vino.
- Un símbolo que el plano trae y **el índice no tiene** se conserva (se puede mover o quitar) y
  se marca en rojo como **«símbolo desconocido»**.
- **Problemas de las convenciones**, en vivo y con los mismos textos que `componer`: símbolo
  que no está en la biblioteca (con la lista de válidos), repetido, más de 24, campo
  desconocido, descripción con un tipo o un número de líneas que la celda no admite y
  caracteres que Arial no tiene. **Si cada descripción cabe en su casilla todavía lo dice solo
  `componer`** (4.3e).

## 3. Qué se ve en la hoja

| Elemento | Aspecto |
|---|---|
| Hoja A1 completa | `plantilla.png` de fondo (rótulo incluido, sin detalles). |
| Área de dibujo | Borde azul discontinuo: es la ÚNICA zona activa. |
| Rótulo, localización, notas, convenciones, cajetín | Capa gris rayada: bloqueadas, no se puede colocar nada encima. Salen solo de los datos `zonas` (el editor no deduce nada del dibujo). |
| Rosa de los vientos | Dibujada por el editor en su posición actual, con borde naranja discontinuo y el nombre «rosa_vientos (movible)». Se arrastra (ver sección 2b). El borde se pone rojo si un detalle la tapa. |
| Otros elementos fijos (si el formato los declara) | Borde naranja discontinuo con su nombre «(fijo)». Se pueden tapar, pero se advierte; el borde se pone rojo si algo los tapa. |
| Detalle | Su miniatura; borde gris = página; borde celeste discontinuo = dibujo real (`page_bounds_mm`). Seleccionado: borde azul grueso. Con advertencias: borde amarillo, naranja o rojo. |

### Con o sin fondo: el editor muestra lo que saldrá en el PDF

- **Paquetes nuevos del exportador (sin fondo)**: la miniatura es **transparente**. Dos
  detalles traslapados se ven uno a través del otro, igual que en el PDF: nada tapa nada.
- **Paquetes antiguos (con fondo blanco de página)**: la miniatura es **opaca**, porque en el
  PDF ese fondo sí tapa lo que queda debajo.

El editor lo sabe por el dato `tiene_fondo` de cada detalle (lo detecta `preparar-editor`
con la misma regla que `componer`). Las miniaturas tienen hasta 1400 px de lado para que se
vean nítidas al acercar.

### Vista limpia

El botón **Vista limpia** (o mantener pulsada la tecla **V**) oculta todo lo que es ayuda de
edición: el rayado de las zonas bloqueadas, el borde del área de dibujo, los contornos de
página y de dibujo, las etiquetas de los detalles, las marcas de los elementos fijos (también
el borde de la rosa, no la rosa) y la selección. Queda solo la plantilla con los detalles y
la rosa, como saldrá impreso (salvo los textos del rótulo y las etiquetas «ESC: 1:N», que
el editor todavía no muestra: ver Limitaciones).

- El **botón** es un interruptor: queda presionado hasta que lo vuelva a pulsar.
- La **tecla V** es momentánea: vista limpia mientras la mantiene; al soltarla vuelve todo.
- El **arrastre sigue funcionando** en vista limpia (y las flechas, y el panel de selección).

### Detalles traslapados: elegir el de abajo

- Un **clic** en la zona traslapada selecciona el de **encima** (el que va después en el plano).
- **Alt + clic** en ese punto selecciona el de **debajo**; repetido, recorre todos los que hay
  en ese punto y vuelve al de encima.
- En la lista **En el plano** del panel derecho, un clic selecciona cualquier detalle, aunque
  esté tapado. Luego se mueve con las flechas o con X / Y.

Panel izquierdo: detalles disponibles (miniatura, escala 1:N, tamaño de página, si cabe), los
que **no caben** (deshabilitados, con su nota y la escala sugerida aproximada) y los
**rechazados** con sus motivos (no se pueden agregar).

Panel derecho: la selección (X, Y, página y dibujo en mm; botones **Centrar**, **Traer al
frente**, **Enviar atrás**, **Quitar**), la lista **En el plano** (orden de apilado: el último
queda encima, igual que en plano.json; un clic selecciona) y las **Advertencias**.

La barra superior muestra la posición del **cursor** sobre la hoja, en mm de papel.

## 4. Atajos

| Acción | Cómo |
|---|---|
| Mover un detalle | Arrastrarlo con el botón izquierdo. |
| Seleccionar el detalle de debajo | **Alt + clic** (repetido: recorre la pila), o clic en la lista **En el plano**. |
| Vista limpia | Botón **Vista limpia** (fija) o mantener la tecla **V** (momentánea). |
| Mover la hoja | Arrastrar el fondo. |
| Acercar / alejar | Rueda del mouse (hacia el cursor) o botones **+** / **−**. |
| Ver la hoja completa | **Ajustar**. |
| Paso de ajuste | Selector **Paso**: 0,1 / 1 / 5 / 10 mm (al arrastrar y con las flechas). |
| Mover el seleccionado (detalle o rosa) | Flechas: un paso (↑ = +Y, hacia arriba del papel). Con **Shift**: 10 pasos. |
| Mostrar / ocultar la rosa | Casilla **Mostrar rosa de los vientos**. **Restaurar posición** la devuelve a su sitio. |
| Quitar el seleccionado | **Supr**. |
| Quitar la selección | Clic en el fondo. |
| Guardar | **Ctrl+S** o **Guardar plano**. |

## 5. Advertencias

Son las mismas de `componer`, con el mismo texto (salen de un único lugar,
`advertencias.py`). Ninguna impide guardar ni componer.

Dependen de si el detalle de **encima** (o el que toca un elemento fijo) tiene fondo blanco:

| Nivel | Cuándo | Con fondo (paquete antiguo) | Sin fondo (paquete nuevo) |
|---|---|---|---|
| Advertencia (amarillo) | Se traslapan las PÁGINAS de dos detalles, no sus dibujos. | El margen blanco del de encima tapa una franja del de abajo. | **No se avisa**: no tapa nada. |
| ADVERTENCIA FUERTE (naranja) | Se traslapan los DIBUJOS de dos detalles. | El de encima tapa parte del dibujo del de abajo. | Sus líneas quedarán superpuestas en el plano. |
| ADVERTENCIA FUERTE (naranja) | La PÁGINA de un detalle toca un elemento fijo (p. ej. la rosa). | Su fondo blanco lo tapa, aunque el dibujo no lo toca. | **No se avisa**. |
| ADVERTENCIA MUY FUERTE (rojo) | El DIBUJO de un detalle se monta sobre un elemento fijo. | El dibujo y su fondo blanco tapan el elemento. | Sus líneas quedarán encima del elemento. |

La rosa cuenta **en su posición actual**; oculta, no cuenta. `componer` usa la misma regla
con la posición guardada en el plano.json.

Si dos detalles se cruzan y solo uno tiene fondo, cuenta el de **encima**: un detalle con
fondo que está debajo no tapa al de encima.

## 6. Guardar y abrir

- **Guardar plano** escribe un `plano.json` (ver [formato_plano.md](formato_plano.md)): el
  formato, `plantilla: null`, los detalles en el orden de apilado con `id`, `manifiesto` y
  `posicion_mm` redondeada a 0,01 mm (siempre hacia dentro del área de dibujo, para no salirse
  por un redondeo) y, si la rosa no está visible y en su lugar, `rosa_vientos` (visible y
  posición, con el mismo redondeo). Con la rosa (o con un `rotulo` o un
  `"etiqueta_escala": false`) el plano es **versión 2**; si no, versión 1. Texto con saltos
  de línea LF.
- Si el plano se **abrió**, lo que no se tocó sale **tal como venía** (ver «2c. Rótulo»):
  abrir y guardar sin cambios da el mismo JSON.
- El rótulo se edita en los paneles **Rótulo** y **Notas** (secciones 2c y 2d); lo que no se
  edita ahí (convenciones, notas de archivos .txt, lo que el formulario no sabe mostrar) se
  **conserva tal cual** al guardar. Lo
  mismo con `"etiqueta_escala": false`.
- En Edge y Chrome aparece el diálogo de **Guardar como** (nombre sugerido `plano.json`). Si el
  navegador no lo ofrece o falla (permisos, archivo abierto desde el disco), el plano se
  **descarga** a la carpeta de descargas: **muévalo** a la carpeta de `editor.html` antes de
  componer. Si usted cancela el diálogo, no pasa nada.
- **Dónde guardarlo**: en la **misma carpeta que `editor.html`**. Las rutas del plano
  (`formato`, `manifiesto`) son relativas a esa carpeta. La pantalla muestra la carpeta en la
  que se generó el editor; es un dato informativo (desde una página no se puede saber la
  ruta real del disco): si movió el editor, use la carpeta donde está ahora.
- **Abrir plano.json** carga un plano guardado. Debe ser versión 1 o 2 y cada manifiesto debe
  estar en el catálogo del editor; si no, un mensaje explica qué falla y no se carga nada. Un
  detalle con `centrar: true` se coloca centrado (igual que `componer`); uno que se sale del
  área de dibujo se acomoda dentro y se avisa (lo mismo la rosa). Sin `rosa_vientos`, la rosa
  queda visible y en su lugar original.
- Si cierra o recarga la página con cambios sin guardar, el navegador pide confirmación.

## 7. Limitaciones

- No hay deshacer (Ctrl+Z): use **Quitar** y vuelva a agregar, o abra el plano guardado.
- Solo posición: no gira ni escala detalles (vienen a escala 1:N del exportador), ni usa
  anclas CAD.
- El catálogo es el de la carpeta con la que se generó el editor; un plano con paquetes de
  otra carpeta no se puede abrir aquí.
- Las miniaturas son imágenes de baja resolución, solo para ubicar; la exactitud la da
  `componer` (verifica cada dibujo a ±0,1 mm).
- Un detalle que no cabe en el área de dibujo no se puede colocar (reexpórtelo a otra escala).
- Todavía no muestra ni edita los **textos del rótulo** ni las **etiquetas «ESC: 1:N»** de
  los detalles (los escribe `componer`; una etiqueta que no cabe se avisa al componer).
