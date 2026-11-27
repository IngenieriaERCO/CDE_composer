# Editor de planos (editor.html)

Un editor visual para armar un plano sin escribir coordenadas a mano: la hoja A1 completa
de fondo, el rótulo bloqueado y los detalles se arrastran dentro del área de dibujo, como en
el Layout de AutoCAD. Guarda un `plano.json`; el PDF final lo genera `componer`.

> El editor es solo una ayuda. `componer` vuelve a validar todo; si hay una diferencia con
> lo que muestra el editor, manda `componer`.

## 1. Generar el editor

> - `data/input`: los paquetes del Exportador Vectorial (PDF + manifiesto) que el editor ofrece
>   para armar el plano. Hoy son de prueba; en un proyecto real se cambia la ruta en
>   `componedor.json` (`editor.paquetes`).
> - `resultados/`: ahí deja `Componer.bat` el PDF de cada plano (`resultados\<nombre del plano>.pdf`).
> - `data/output` ya no se usa para los planos: lo reemplaza `resultados/`.

**Lo normal: doble clic en `Abrir editor.bat`** (raíz de Componedor). Genera el editor con las
rutas de `componedor.json` y lo abre en el navegador **con el servidor local** que habilita
«Cargar DXF» (ver [2f](#2f-cargar-dxf-con-servidor-local) y
[servidor_editor.md](servidor_editor.md)). Equivale a:

```powershell
python -m componedor.cli editor --config componedor.json --sobrescribir
python -m componedor.cli servidor --config componedor.json
```

Deje abierta la ventana negra mientras usa el editor. Con doble clic en `editor\editor.html` el
editor se abre sin servidor: funciona todo igual, salvo «Cargar DXF».

Las rutas que usa, en `componedor.json` (relativas a la raíz; ver el README):

| Clave | Valor | Qué es |
|---|---|---|
| `formato` | `formatos/A1_ERCO.json` | la hoja (también la usa `Componer.bat`) |
| `editor.paquetes` | `data/input` | los paquetes del exportador que el editor ofrece |
| `editor.salida` | `editor` | dónde queda `editor.html` |
| `editor.notas` | `notas` | catálogo de notas típicas (opcional) |
| `editor.firmas` | `firmas` | carpeta de firmas, una subcarpeta por persona (opcional) |
| `editor.proyecto` | `null` | proyecto.json para prellenar (opcional) |

Sin `componedor.json`, las mismas opciones van a mano (con `--config` no se pueden repetir):

```powershell
python -m componedor.cli editor data/input --formato formatos/A1_ERCO.json --salida editor
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
  python -m componedor.cli editor data/input --formato formatos/A1_ERCO.json --salida editor --notas notas
  ```
- `editor`: carpeta del editor. Queda ahí **solo `editor.html`**: datos, plantilla, rosa,
  miniaturas y símbolos van incrustados dentro. Si quiere ver esos archivos por separado, use
  `preparar-editor`. `componer` no lee ninguno.
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
python -m componedor.cli editor data/input --formato formatos/A1_ERCO.json --salida editor ^
    --notas notas --firmas firmas --proyecto proyecto.json
```

- `--notas`: catálogo de notas típicas (subcarpetas = grupos).
- `--firmas <carpeta>`: la carpeta de firmas (una subcarpeta por persona). El editor solo
  recibe los **nombres** de las personas, para elegirlos en una lista; **las imágenes nunca se
  incrustan** en editor.html. Se omiten, con aviso, las carpetas sin PNG o con un nombre que
  `componer` no aceptaría.
- `--proyecto <proyecto.json>`: datos que se repiten en todos los planos del proyecto
  (nombres y matrículas de las firmas, prefijo del No. PLANO). Esquema en
  [formato_proyecto.md](formato_proyecto.md). **Solo prellena un plano NUEVO**; al guardar,
  los valores quedan copiados en el plano.json (`componer` no lee proyecto.json). Un plano que
  se abre no se toca. Si el proyecto tiene errores, el editor no se genera y se listan todos.

Panel **Rótulo** (a la derecha). **Todo el formulario va en el orden del rótulo, de arriba
hacia abajo**, como se lee la columna del rótulo en la hoja:

1. **Imagen de localización** (sección; ver 2h) y **ESC. de localización**.
2. Coordenadas **ESTE** y **NORTE**.
3. **Notas** (sección; ver 2d).
4. **Convenciones** (sección; ver 2e).
5. **Revisiones** (sección).
6. **Título**.
7. **Firmas** (sección: DIBUJÓ, DISEÑÓ, REVISÓ, APROBÓ).
8. **HOJA** y **DE**.
9. **ESCALA** (calculada).
10. **No. PLANO** y **REV.** (calculada).

El orden sale de las celdas del formato (`formatos/A1_ERCO.json`): cada campo, tabla o panel por
el borde superior de su recuadro; los que están en la misma fila (bordes a 1 mm o menos, como
FIRMAS y HOJA, o No. PLANO y REV.) van de izquierda a derecha. Si una celda cambia de lugar en el
formato, cambia el orden. Los campos sueltos que quedan seguidos van juntos; Imagen, Notas,
Convenciones, Revisiones y Firmas son secciones que se pliegan. Solo cambió el lugar: cada campo y
cada panel funcionan igual que antes.

- Las celdas de varias líneas (Título 3, REVISÓ 2) usan una caja de varios renglones: **una línea
  por renglón**.
- **ESCALA** y **REV.** son calculadas, de solo lectura, con la misma regla que `componer` (REV.:
  «0» si existe la emisión 0; si no, la letra más alta entre C, B y A; vacía sin revisiones).
- **Diseñador y Revisor ya no existen**: la franja del logo de ERCO solo lleva el logo
  (plantilla v3). Un plano.json o proyecto.json viejo que los traiga se abre sin error: se
  ignoran y el panel avisa **una vez** («Aviso: rotulo.disenador, rotulo.revisor: campo(s) que
  el rótulo ya no tiene…», el mismo texto que `componer`). Al **guardar**, el editor los
  **quita** del plano.json: el plano nuevo ya no los trae y `componer` (y `Componer.bat`) ya no
  avisa. Un plano viejo que no se vuelve a guardar sigue componiendo, con ese aviso.
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
  más líneas de las que admite la celda. La casilla con problema se pone en rojo.
- **¿Cabe?** (subfase 4.3e): el editor **mide** cada texto con la tabla de anchos de Arial,
  igual que `componer` (mismo corte en líneas y misma reducción de 0,1 en 0,1 mm hasta la
  altura mínima). Si se escribe más pequeño, la casilla queda en **ámbar** con el aviso
  «Advertencia: en el rótulo, el campo 'titulo' se escribió a 2.2 mm de altura (pedida 2.5 mm)
  para que quepa en su celda.» debajo; si no cabe ni a la mínima, en **rojo** con el error de
  `componer` (campo, texto, medida y tamaño). En revisiones y firmas el mensaje va al pie de la
  tarjeta. Todo aparece además en «Problemas del rótulo». Un carácter que la tabla del editor no
  trae (p. ej. «Ω») no se puede medir: aviso, y `componer` decide.

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

Sección **Notas** del Rótulo (entre las coordenadas y las convenciones, como en el rótulo):

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
  decir nada).
- **¿Caben?** (4.3e): las notas se miden en su celda como en `componer` (las de archivos
  primero, sangría francesa, viñetas, medio renglón entre notas, bajando todas juntas hasta
  1,5 mm). Una nota que no cabe queda en rojo con el error en su tarjeta; «las notas se
  escribieron a X mm» (ámbar) va arriba de «Notas del plano». Si un .txt de `"archivos"` no está
  en el catálogo, el editor no conoce sus notas y **no mide**: aviso ámbar informativo («el
  editor no puede medir las notas: '…' no está en el catálogo; componer lo comprobará»), que no
  es un error del plano.
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

Sección **Convenciones** del Rótulo (entre Notas y Revisiones, como en el rótulo):

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
  caracteres que Arial no tiene. Desde la 4.3e cada descripción se **mide** en su casilla
  (2 líneas, 1,8 -> 1,5 mm): «no cabe» en rojo y «se escribió a X mm» en ámbar, debajo de la
  descripción y en Problemas, con los textos de `componer`.

### Líneas y rellenos (subfase 9a)

Debajo de la lista, **+ Línea** y **+ Relleno** agregan un renglón que no es un símbolo de la
biblioteca: una **muestra** que `componer` dibuja como **vector** en la casilla del símbolo.

- **Línea**: **Color** (por defecto negro), **Grosor (mm)** de 0,05 a 2 (por defecto 0,25) y
  **Trazo** continua o discontinua (guiones de 2 mm con huecos de 1 mm). Se dibuja horizontal,
  de 13 mm de largo, centrada en la casilla.
- **Relleno**: **Color** (por defecto gris) y **Opacidad** (mayor que 0 y hasta 1; 1 = opaco).
  Un rectángulo de 13 × 6 mm, sin borde, centrado en la casilla.
- La **descripción es obligatoria** (una muestra no tiene descripción por defecto): mientras
  esté vacía, Problemas dice «falta la descripción».
- La miniatura y la vista previa del rótulo muestran la muestra con su color, grosor, trazo y
  opacidad. Se sube, se baja y se quita como cualquier convención; cuenta para el tope de 24.
- Se guarda en `rotulo.convenciones` con todos sus valores, por ejemplo
  `{"tipo": "linea", "descripcion": "RED DE MEDIA TENSIÓN", "color": "#FF0000", "grosor_mm":
  0.35, "trazo": "discontinua"}` (ver [formato_plano.md](formato_plano.md#convenciones-rotuloconvenciones-subfase-42b)).
- Los renglones de símbolo funcionan y se guardan como antes. El color tomado de la capa del DXF
  (según la CTB) llega cuando se puedan escoger símbolos del DXF; por ahora el color se elige aquí.

## 2f. Cargar DXF (con servidor local)

Solo con `Abrir editor.bat` (o `componedor servidor`). **Cargar DXF**, en la barra de arriba,
abre el cuadro de Windows para elegir el dibujo. El trabajador del Exportador Vectorial lo lee
una vez, con barra de avance y **Cancelar**, y arriba de «Detalles disponibles» aparece una
**carpeta** con cada bloque del Model Space:

- su nombre (y «ocurrencia 2 de 3» si se repite) y su capa;
- el tamaño real en m y las unidades (verificadas o no);
- la **escala sugerida** (la primera de 1:50, 1:100, … 1:10000 con la que la página cabe en el
  área de dibujo) y el tamaño de esa página;
- notas: caja aproximada («página ≤ …»), sólidos 3D que la vista previa no mostrará, capas
  apagadas o congeladas, unidades sin verificar o que no cabe ni a 1:10000.

Cada tarjeta tiene **Ver vista previa**: la vista previa del bloque (solo capas visibles), en
pequeño dentro de la tarjeta, para reconocerlo antes de agregarlo. Es la misma que después usa
la caja en la hoja (no se pide dos veces). **Ocultar vista previa** la quita.

Debajo de los bloques con nombre, **«Anónimos (opcionales) (N)»**, cerrada por defecto: los
bloques anónimos `*U` del Model Space que dibujan muchas entidades (por defecto 100 o más,
`exportador.anonimos_min_entidades` en `componedor.json`), como las mesas de paneles de PVcase o
las tablas de Civil 3D.

- Se nombran por **capa + handle** (`I1.M1.PV1_12900`), porque AutoCAD renumera los `*U` al
  guardar y el handle no cambia; la tarjeta dice el `*U` y cuántas entidades visibles dibuja.
- **Filtro**: muestra los que tienen todas las palabras escritas en su capa, handle o `*U`, sin
  distinguir mayúsculas ni tildes («pv1 m2»). Se muestran 200 a la vez; el filtro encuentra el
  resto.
- Se agregan, escalan y exportan como cualquier bloque; el paquete se llama como la etiqueta
  (`I1.M1.PV1_12900_1-50`).
- Los anónimos más pequeños (cotas, etiquetas, piezas de Civil 3D, a veces miles) no se ofrecen
  ni se listan: solo se dice cuántos son.

Al final, «No exportables» (XREF, sin definición…). Recargar la página no pierde la carpeta.

Sin servidor, el botón aparece desactivado y explica cómo abrirlo. Si el `cde-exporter`
instalado no tiene la orden `worker`, el editor lo dice.

### Bloques en la hoja: caja exacta y vista previa (etapa 2)

Cada tarjeta de la carpeta tiene **Agregar al plano** (desactivado si las unidades del bloque no
están verificadas: sin ellas no se sabe su tamaño en papel). El bloque aparece en el centro del
área de dibujo como una **caja exacta**: la página que tendrá el paquete al exportarlo a la
escala sugerida (`tamaño_m × 1000 ÷ N + 2 × margen`), con borde morado punteado y la marca
«vista previa (sin exportar)». Enseguida el editor pide su **vista previa** al trabajador
(«Pidiendo vista previa…»; de 1 a 10 s según el bloque) y la pone encima, en su lugar exacto:
el PNG va por coordenadas CAD, así que cae donde caerá el dibujo en el PDF (aunque no muestre
los sólidos 3D). Es una imagen solo para ubicar; el PDF final es vector.

- **Mover**: se arrastra como un detalle (por su centro, con el paso de la barra), con las
  flechas o escribiendo «Centro X / Centro Y» en Propiedades. Si cabe, la página queda siempre
  completa dentro del área de dibujo.
- **Cambiar la escala** (el **centro no se mueve**; solo cambia el tamaño de la caja y de la
  imagen, sin pedir otra vista previa):
  - el selector **Escala** de Propiedades, con las escalas normalizadas (1:5, 1:10, 1:20, 1:25,
    1:50, 1:75, 1:100, 1:200, 1:250, 1:500, 1:750, 1:1000, 1:1500, 1:2000, 1:2500, 1:3000,
    1:4000, 1:5000, 1:7500 y 1:10000; la sugerida marcada) y el botón **Escala sugerida**. La
    sugerida es la más grande de la lista con la que la página cabe;
  - **escribirla a mano** en «o escriba»: `1:3500` o `3500`, entero de 1 a 100000. Si no es
    normalizada se permite, con el aviso «escala no normalizada»; se guarda tal cual en el
    plano.json y la usan el nombre del paquete (`…_1-3500`), la caché y el rótulo;
  - **Ajustar a la hoja**: la escala exacta más grande con la que la página cabe, aunque no
    sea normalizada (BLOQUE1 de GUAMO: 1:2507). Si la caja quedaría afuera, se acomoda dentro;
  - las teclas **+** (dibujo más grande: de 1:100 a 1:75) y **−** (más chico), también las del
    teclado numérico; desde una escala escrita pasan a la anterior o siguiente de la lista. No
    actúan si el foco está en un cuadro de texto o en una lista;
  - el **tirador** (cuadrito blanco en la esquina superior derecha del bloque seleccionado):
    al arrastrarlo, la escala salta a la estándar cuya esquina queda más cerca del puntero.
- **Si no cabe** (o se sale del área): borde rojo y «no cabe: sobran X × Y mm; sugerida 1:N» en
  la caja, en Propiedades y en Advertencias. Se puede guardar igual (con aviso), pero `componer`
  lo rechaza.
- **Guardar**: con bloques sin exportar el plano.json es **versión 3** (ver
  [formato_plano.md](formato_plano.md#bloques-de-un-dxf-sin-exportar-versión-3)). Abrirlo y
  guardarlo sin tocar nada da el mismo archivo. Sin servidor el plano se abre igual: las cajas
  se ven sin vista previa.
- **Si el DXF cambió en el disco** (AutoCAD lo guardó) o el trabajador se reinició, la carpeta
  muestra el aviso y **Volver a cargar**: el servidor lo lee de nuevo con la ruta que ya
  conoce; los bloques puestos pasan al DXF nuevo (con su tamaño nuevo) y se avisa.
- Mientras no se exporten, `componer` dice qué bloques faltan.

### Exportar (etapa 3)

Debajo de la carpeta del DXF, **Exportar bloques del plano (N)** exporta cada bloque sin exportar
a un paquete en `data/input/dxf/<DXF>/` (PDF vectorial + TXT + manifiesto), a la escala que tiene
en la hoja.

- Uno a la vez, cada uno con su **barra de avance** y **Cancelar**; además **Cancelar todo** y
  **Detener a la fuerza** (pide confirmación: corta sin esperar y después hay que volver a
  cargar el DXF).
- No se exportan, con su motivo: los que no caben o se salen del área, los de otro DXF y los de
  una versión anterior del DXF.
- Al terminar, cada bloque **pasa a ser un detalle normal** en la hoja: su paquete, puesto de
  modo que el punto del dibujo que estaba en el centro de la caja quede en el mismo lugar. El
  paquete aparece en «Detalles disponibles» y el plano.json lo guarda con su manifiesto, como
  cualquier detalle.
- Si el paquete ya estaba publicado (mismo bloque, escala, margen y versión del DXF), se usa tal
  cual: «ya estaba publicado».
- Si en su lugar había uno viejo (otra versión del DXF), se **mueve** a `_para_borrar/` (nunca se
  borra) y se dice, pero **solo cuando el nuevo ya se publicó y pasó la verificación**. Si se
  cancela o falla, el viejo queda donde estaba.
- Si el exportador falla, el editor dice qué pasó con un mensaje claro (por ejemplo «No se pudo
  leer el DXF: el exportador encontró un objeto que no entiende») y **Ver detalle** despliega
  el texto técnico y la ruta del registro (`data\cache_exportador\trabajador.log`).
- Si el DXF cambió en el disco, no se exporta: **Volver a cargar** primero.

### Estilo de impresión (CTB y transparencia)

Entre la carpeta del DXF y «Exportar», el recuadro **Estilo de impresión**:

- **Tabla (CTB)**: «Sin CTB» o una de las tablas `.ctb` de la carpeta de `componedor.json`
  (`exportador.carpeta_ctb`, hoy la del Exportador). Debajo, su descripción (p. ej. «Derivada del
  PDF de AutoCAD…») y su SHA-256. Con la tabla, el dibujo sale con sus colores, grises y grosores,
  como al imprimir en AutoCAD.
- **Imprimir transparencia**: sin marcar, no se dibujan los rellenos con transparencia del 80 % o
  más (las veladuras casi invisibles de los paneles de PVcase, que el PDF de AutoCAD tampoco lleva).
- Al abrir el editor salen los valores de `componedor.json` (hoy `CTB_ERCO_derivada_PRGD.ctb` y sin
  transparencia). Lo que se elija **no se guarda en el plano.json**.
- Vale para las **vistas previas** (cada estilo tiene la suya) y para **Exportar**; la sección
  «Exportar» dice con qué estilo va a exportar.
- El editor solo manda el **nombre** de la tabla; la ruta la pone el servidor (si alguien manda
  una ruta, la rechaza).

El nombre del paquete lleva la marca del estilo: `_p` y 6 cifras del SHA-256 de la tabla, y `_t`
si no imprime transparencia. Por ejemplo `I1.M1.PV1_12900_1-75_pb4a909_t`. Así **no choca** con el
paquete viejo sin CTB del mismo bloque y escala (`I1.M1.PV1_12900_1-75`, que se queda donde está), y
si la tabla cambia en el disco sale otro paquete. Un paquete ya publicado se reutiliza solo si su
manifiesto trae el mismo estilo; si el exportador publicara uno con otro estilo, no se usa.

Cada detalle dice con qué estilo se exportó (en «Detalles disponibles» y en el panel Selección:
«Estilo: CTB_ERCO_derivada_PRGD.ctb (b4a909…), sin transparencia» o «sin CTB»). Si es distinto del
elegido, **se queda como está**, con un aviso en Selección y en las advertencias; para cambiarlo,
hay que volver a exportarlo.

## 2g. Ortofoto de fondo (con servidor local)

Solo con `Abrir editor.bat`. **Cargar ortofoto**, en la barra de arriba, abre el cuadro de
Windows para elegir un GeoTIFF (`.tif` o `.tiff`). Una ortofoto por plano, que va **detrás de los
detalles que la usan**, recortada a la página de cada uno; fuera de ellos la hoja queda en blanco.

**Por detalle**: seleccione el detalle y marque **«Usar ortofoto»** en el panel Selección (sirve
para detalles exportados y para bloques del DXF sin exportar). Sin marcar, no la lleva: un perfil,
por ejemplo. La casilla está desactivada mientras no haya ortofoto cargada. Si ninguno está
marcado, el panel Ortofoto lo dice. Un plano versión 4 (de antes, con la ortofoto en todos) se
abre con todos los detalles marcados, con un aviso, y se guarda en versión 5.

En el panel **Ortofoto** (columna derecha) aparece su **ficha**, leída de la cabecera sin abrir
la imagen entera (sirve igual para archivos de varios GB):

- nombre, tamaño en disco y si es BigTIFF; píxeles, color (RGB, RGBA, gris, paleta) y tipo;
- **sistema de coordenadas** (el del archivo, o «el archivo no lo dice»);
- tamaño del píxel en m, cuánto terreno cubre y si está girada;
- pirámides, mosaicos o franjas y compresión (de eso depende la velocidad);
- si tiene fondo transparente (banda alfa, «nodata» o máscara).

**Sistemas de coordenadas: nunca se supone ninguno.**

- **Sistema del dibujo (DXF)**: si el DXF cargado trae su sistema (el GEODATA, que el
  Exportador manda en `dxf.crs`) y el código salió de un **Alias** del GEODATA
  (`epsg_from: "alias"`), el selector sale **prellenado** con ese código y un aviso azul lo dice;
  siempre se puede cambiar. Si el código salió del texto de la **autoridad**
  (`epsg_from: "authority"`), o si el DXF no trae sistema, el selector queda **vacío** y un aviso
  amarillo pide elegirlo (no se dibuja la ortofoto hasta entonces).
- **El código del DXF puede estar mal**: el Componedor compara la zona que dice el nombre del
  GEODATA con la del código. En PRGD el nombre dice «Colombia CTM12» (EPSG:9377) pero el código
  es 3115 (Colombia West zone, sacado de la autoridad): el selector queda vacío, sale un **aviso
  amarillo** y el botón **Usar EPSG:9377 para el dibujo**. Con 3115 la ortofoto caería a cientos
  de km: «no cubre» ningún detalle.
- **Sistema de la ortofoto**: solo se pide si el archivo no trae el suyo (aviso amarillo).
- El selector trae los de Colombia (EPSG:9377 Origen-Nacional, 3116 Bogotá, 3115 Oeste, 3117,
  3118, 3114) y «Otro (código EPSG)…» para escribir cualquiera (`epsg:6247`, `6247` o
  `EPSG:6247`). Solo se aceptan sistemas proyectados, en metros.
- Si los dos sistemas son distintos, la ortofoto se **reproyecta** (aviso azul).

Con los sistemas elegidos, el editor pide la ortofoto de **cada detalle marcado**: la de la caja CAD que
cubre su página en la hoja. La caja sale de la matriz del manifiesto si el detalle ya está
exportado, y del centro y la escala si es un bloque del DXF sin exportar. Al mover un detalle, la
ortofoto se mueve con él. Al cambiar la escala, se pide la de la caja nueva.

- Debajo, el estado de cada detalle: «la ortofoto cubre todo el detalle», «cubre el 40 %», «no
  cubre este detalle» o por qué no se puede (p. ej. un bloque cuyo DXF no está cargado).
- **Opacidad**: de 0 a 100 % (100 % por defecto). Se guarda en el plano.
- **Quitar ortofoto**: la saca del plano (el archivo no se toca).

Se guarda en el plano.json (versión 4) con la ruta del archivo, su tamaño y su fecha, los
sistemas y la opacidad ([formato_plano.md](formato_plano.md#ortofoto-de-fondo-versión-4)). Al
abrir un plano con ortofoto:

- si el servidor ya la tiene cargada, aparece de nuevo;
- si no, el panel dice cuál usa el plano: **Cargar ortofoto** abre el cuadro **en la carpeta
  donde estaba** (el editor solo le pasa esa ruta al cuadro: no se lee nada con ella);
- si la elegida **no coincide** con la del plano en nombre, tamaño o fecha, el plano **no
  cambia**: el panel dice qué difiere y ofrece **Usar la cargada en el plano** (toma la nueva y
  conserva sistemas y opacidad).

Sin servidor (doble clic en `editor.html`) el panel dice qué ortofoto usa el plano y la conserva
al guardar, pero no la dibuja.

**Extender a todo el layout**: aparece en el panel Ortofoto solo cuando hay UN detalle con
ortofoto. La foto cubre toda el área de dibujo, sin mover ni escalar nada (mismo mapeo del
detalle); los demás detalles quedan con fondo blanco. Si después se marca otro, la casilla
desaparece y el panel explica que cada foto va recortada a su página.

**Cuadrícula de coordenadas**: casilla e intervalo en m (por defecto el de `componedor.json`, 50).
Líneas negras finas sobre la foto y, en la franja entre el marco y el área (o alrededor de la
página del detalle), sus coordenadas: Este arriba y abajo, Norte girado a los lados, como el
plano de AutoCAD de PRGD. El panel dice cuántas líneas y etiquetas salen (y cuántas se omiten
por chocar). Se guarda en el plano.

En el PDF la pone `componer` (o `Componer.bat`), detrás de los detalles y recortada igual que
en el editor, a 300 ppp en JPEG (`componedor.json` → `ortofoto`). Ver
[formato_plano.md](formato_plano.md#ortofoto-de-fondo-versión-4).

## 2h. Imagen de localización (con servidor local)

Solo con `Abrir editor.bat`. Al principio del Rótulo (arriba, como en el rótulo), la sección
**Imagen de localización** tiene el botón **Cargar imagen de localización**: abre el cuadro de Windows para
elegir un PNG o JPG (por ejemplo, el mapa de localización exportado de QGIS).

- La imagen aparece en el recuadro LOCALIZACIÓN del rótulo, **entera, centrada y sin
  deformar**. No tapa el título, «ESC:» ni las coordenadas; si sobra espacio, queda en blanco.
- La **ficha** dice el nombre, el formato y los píxeles, cuánto mide en el recuadro y con
  cuántos ppp sale en el PDF: un PNG con más de 300 ppp «se reduce a 300 ppp (sin pérdida)»; con
  menos, «no se agranda»; un JPG «va tal cual, sin recomprimir».
- **Escala**: «ESC:» se escribe a mano en el Rótulo («ESC. de localización»). Mientras esté
  vacía, un **aviso amarillo** dice que en el PDF saldrá «ESC: DEFINIR»; al escribirla, el aviso
  se va. Este y Norte también se escriben a mano, como siempre.
- **Quitar imagen de localización**: la saca del plano (el archivo no se toca).

Se guarda en el plano.json con la ruta, el tamaño y la fecha del archivo; la imagen **no** va
dentro del plano ([formato_plano.md](formato_plano.md#imagen-de-localización-rotulolocalizacion_imagen)).
Al abrir un plano con imagen de localización:

- si el servidor ya la tiene cargada (la misma), se dibuja de nuevo;
- si no, se ve un recuadro punteado con su nombre: **Cargar imagen de localización** abre el
  cuadro **en la carpeta del plano** (el editor solo le pasa esa ruta al cuadro);
- si la elegida **no coincide** con la del plano en nombre, tamaño o fecha, el plano **no
  cambia**: el panel dice qué difiere y ofrece **Usar la cargada en el plano**.

Sin servidor el panel dice qué imagen usa el plano y la conserva al guardar, pero no la dibuja.
En el PDF la pone `componer`; si el original se movió, usa la copia
`<plano>_localizacion.<ext>` que deja al lado del plano (con advertencia).

## 3. Qué se ve en la hoja

**Recorte (Fase 11)**: cada detalle se ve con su dibujo y un borde de **1 mm** (`margen_detalle_mm`
de `componedor.json`), no con la página entera que trae el paquete (5 mm de margen). El recuadro
del detalle, la regla de «no cabe» (rojo) y los traslapes miden eso. En **Selección**, «Margen
(mm)» cambia el borde de ese detalle (de 0 a 50; vacío = el general) y «Se ve: …» dice el
rectángulo que debe caber. X e Y siguen siendo la esquina de la PÁGINA del paquete: el dibujo no
se mueve al cambiar el margen.

| Elemento | Aspecto |
|---|---|
| Hoja A1 completa | La plantilla de fondo (rótulo incluido, sin detalles), en **vector** desde la 4.3f (`plantilla.svg`): sus líneas y letras se ven nítidas a cualquier zoom. |
| Vista previa del rótulo (4.3f) | Textos del rótulo, notas, convenciones, cajas de firma y etiquetas «ESC: 1:N» donde los pondrá `componer` (ver sección 3b). |
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
la rosa, como saldrá impreso. Con la casilla **Vista previa del rótulo** encendida, también
se ven los textos del rótulo, las notas, las convenciones y las etiquetas «ESC: 1:N» (las
marcas rojas o ámbar de la vista previa sí se ocultan: son ayudas).

- El **botón** es un interruptor: queda presionado hasta que lo vuelva a pulsar.
- La **tecla V** es momentánea: vista limpia mientras la mantiene; al soltarla vuelve todo.
- El **arrastre sigue funcionando** en vista limpia (y las flechas, y el panel de selección).

### 3b. Vista previa del rótulo (subfase 4.3f)

La casilla **Vista previa del rótulo** (barra de arriba, encendida al abrir) dibuja sobre la
hoja, en su sitio, lo que `componer` escribirá:

- los **textos del rótulo**: título, No. PLANO, ESCALA y REV. (calculadas), HOJA / DE,
  coordenadas, cada celda de las **revisiones** y de las **firmas**
  (nombre, matrícula, firma en texto, fecha); un campo sin valor muestra su valor por defecto
  («DEFINIR»), como `componer`;
- las **notas** numeradas, con su sangría francesa y sus viñetas (las de los .txt de
  `archivos`, si están en el catálogo, y luego las adicionales);
- los **símbolos de convenciones** en su casilla de la leyenda (centrados y, si no caben,
  reducidos, como `componer`), con su descripción;
- las **etiquetas «ESC: 1:N»** de cada detalle: debajo de su dibujo o, si no caben, encima;
- la **caja de cada firma en imagen**, punteada en azul con «firma: <persona>». La imagen de
  la firma **no** se muestra: el editor nunca la tiene (datos personales).

Qué tan fiel es:

- Las **posiciones y alturas** son las de `componer`: el editor usa la misma maquetación que ya
  usa para medir (copia en JavaScript de la de Python, probada con `pytest` a ±1e-6 mm). Si un
  texto se reduce para caber, se dibuja reducido.
- Las letras son Arial, sin kerning, con el ancho de cada línea fijado al que calcula
  `componer`. En Edge se comprobó contra el PDF compuesto: la base de cada línea coincide con
  la de los caracteres del PDF (diferencia 0,000 mm; tolerancia ±0,1 mm). Si el navegador no
  tiene la misma Arial, el editor lo avisa al abrir.
- Un campo con **problema** (no cabe, salto de línea en una celda de una línea, tipo no
  válido, carácter que Arial no tiene) **no se dibuja**: su celda se marca en **rojo**, y al
  pasar el ratón se lee el mismo error de `componer`. Los demás campos se siguen dibujando.
  Lo que el editor no puede medir (un .txt de notas fuera del catálogo) se marca en **ámbar**.
- Una etiqueta «ESC» que no cabe ni debajo ni encima no se dibuja, y su aviso sale **en vivo**
  en la lista de Advertencias con el texto de `componer` (sección 5).

Al arrastrar un detalle solo se recalculan las etiquetas «ESC»: el rótulo se vuelve a dibujar
únicamente cuando cambian sus datos o las escalas de los detalles. Medido en Edge: el arrastre
cuesta lo mismo con y sin vista previa (~4 ms de trabajo por movimiento; un cuadro, ~17 ms).

El editor sigue siendo una ayuda: `componer` vuelve a maquetar y a validar todo.

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

**«Mostrar escala».** En el panel Selección, debajo de «Usar ortofoto», cada detalle, bloque o zona
borrador tiene el casillero **«Mostrar escala («ESC: 1:N»)»**. Desmarcado, su etiqueta no se
dibuja en la hoja ni sale en el PDF, y su aviso de etiqueta desaparece (se guarda
`"etiqueta_escala": false`). Una zona agregada con su «ESC 1:N» leído del dibujo, a esa misma
escala, empieza desmarcada (el dibujo ya la trae; Selección dice «El dibujo ya trae «ESC 1:10»
escrito.»); a otra escala, o sin escala leída, empieza marcada. Después manda lo que elija el
usuario.

**Etiquetas «ESC: 1:N» (4.3f).** Al final de la lista sale, también en amarillo, el aviso de
`componer` cuando la etiqueta de un detalle no cabe ni debajo ni encima de su dibujo (se
saldría del área de dibujo o se montaría sobre otro dibujo, la rosa u otra etiqueta), por
ejemplo: «Advertencia: no se dibujó la etiqueta «ESC: 1:50» del detalle 'p1': no cabe a 3 mm
de su dibujo (debajo: se monta sobre el dibujo de 'p2'; encima: se monta sobre el dibujo de
'p3'). Mueva el detalle o ponga "etiqueta_escala": false.» Se calcula aunque la vista previa
esté apagada.

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
  abrir y guardar sin cambios da el mismo JSON. Única excepción: los campos retirados del
  rótulo (`disenador`, `revisor`) se quitan al guardar.
- El rótulo se edita en los paneles **Rótulo** y **Notas** (secciones 2c y 2d); lo que no se
  edita ahí (convenciones, notas de archivos .txt, lo que el formulario no sabe mostrar) se
  **conserva tal cual** al guardar. Lo
  mismo con `"etiqueta_escala": false`.
- En Edge y Chrome aparece el diálogo de **Guardar como** (nombre sugerido `plano.json`). Si el
  navegador no lo ofrece o falla (permisos, archivo abierto desde el disco), el plano se
  **descarga** a la carpeta de descargas: **muévalo** a la carpeta de `editor.html` antes de
  componer. Si usted cancela el diálogo, no pasa nada.
- **Dónde guardarlo**: en la **misma carpeta que `editor.html`** (`editor\`) o en `planos\`.
  Las rutas del plano (`formato`, `manifiesto`, notas) son relativas a la carpeta del editor, y
  `planos\` está al mismo nivel, así que el plano sirve igual en las dos. La pantalla muestra la
  carpeta en la que se generó el editor; es un dato informativo (desde una página no se puede
  saber la ruta real del disco): si movió el editor, use la carpeta donde está ahora.
- **Componer**: arrastre el `plano.json` sobre **`Componer.bat`** (o doble clic y arrastre la
  ruta a la ventana). Usa el formato de `componedor.json`, deja el PDF en
  `resultados\<nombre del plano>.pdf` y lo abre; si hay errores o advertencias, los muestra y
  espera una tecla. Desde la consola:
  `python -m componedor.cli componer planos\plano.json --config componedor.json --sobrescribir`.
- **Firmas**: «Cargar firma…» pide una carpeta; elija **`Componedor\firmas`**. `componer` solo
  busca ahí (si elige otra, la firma queda donde `componer` no la encuentra).
- **Abrir plano.json** carga un plano guardado. Debe ser versión 1 o 2 y cada manifiesto debe
  estar en el catálogo del editor; si no, un mensaje explica qué falla y no se carga nada. Un
  detalle con `centrar: true` se coloca centrado (igual que `componer`); uno que se sale del
  área de dibujo se acomoda dentro y se avisa (lo mismo la rosa). Sin `rosa_vientos`, la rosa
  queda visible y en su lugar original.
- Si cierra o recarga la página con cambios sin guardar, el navegador pide confirmación.

### Varias hojas en un proyecto: pestañas (plano versión 8)

Como los layouts de un DWG: todas las hojas del proyecto en un solo archivo. Bajo la barra de
arriba, una **pestaña por hoja** (con cuántas advertencias tiene) y «+»:

- **Clic** en una pestaña: cambia de hoja **al instante**, sin guardar ni preguntar (todas viven
  en la memoria del editor). Cada hoja tiene sus detalles, sus bloques y zonas borrador, su rosa
  y su rótulo; el DXF cargado, la ortofoto y las vistas previas son del proyecto.
- **«+»**: hoja nueva («Hoja 2», «Hoja 3»…) después de la activa, con el área de dibujo vacía y
  el rótulo copiado sin título; notas, convenciones y revisiones quedan en Advertencias
  «copiado de la hoja N, revíselo» hasta que se cambien.
- **Doble clic** en una pestaña: cambiarle el nombre (único).
- **◀ ▶**: mover la hoja activa; **Duplicar**: la copia, con sus detalles y borradores en el mismo
  sitio (sus zonas con otro nombre: cada zona da un paquete); **Borrar** (con confirmación).
- **Hoja, De y No. PLANO** salen solos de la posición de la pestaña (mover una hoja los reordena);
  se pueden escribir a mano.
- **Guardar plano** escribe **un solo archivo** (versión 8) con todas las hojas. Un plano viejo
  (versiones 1 a 7) abre como un proyecto de una hoja y, al guardar, se propone
  `<nombre>_proyecto.json`: el original no se pisa.
- Al abrir una hoja de un proyecto con índice (`.hojas.json`, con el servidor), el editor ofrece
  abrir el proyecto completo, una pestaña por hoja; los archivos viejos no se tocan y al guardar
  se propone `<proyecto>_proyecto.json`.
- «Exportar bloques y zonas» exporta los de la **hoja activa** (exportar todas las hojas de una
  vez llega en la subfase 8c).

## 7. Limitaciones

- Un plano con bloques sin exportar no se compone: hay que exportarlos (etapa 3) antes.
- La vista previa muestra solo las capas visibles y no dibuja los sólidos 3D (la exportación
  sí, como huella en planta).

- No hay deshacer (Ctrl+Z): use **Quitar** y vuelva a agregar, o abra el plano guardado.
- Solo posición: no gira ni escala detalles (vienen a escala 1:N del exportador), ni usa
  anclas CAD.
- El catálogo es el de la carpeta con la que se generó el editor; un plano con paquetes de
  otra carpeta no se puede abrir aquí.
- Las miniaturas son imágenes de baja resolución, solo para ubicar; la exactitud la da
  `componer` (verifica cada dibujo a ±0,1 mm).
- Un detalle que no cabe en el área de dibujo no se puede colocar (reexpórtelo a otra escala).
- La vista previa no muestra la **imagen de las firmas** (solo su caja) ni la tabla de
  cantidades, la escala de colores o la localización (subfase 4.4).
- Las posiciones de los detalles que usa la vista previa son las del editor, antes de
  redondearlas a 0,01 mm al guardar: una etiqueta «ESC» puede quedar hasta 0,005 mm corrida
  respecto del PDF.
