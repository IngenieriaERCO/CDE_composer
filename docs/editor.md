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
  por un redondeo) y, si el formato tiene rosa, `rosa_vientos` (visible y posición, con el
  mismo redondeo). Con la rosa (o con un `rotulo` o un `"etiqueta_escala": false` que venían
  en el plano abierto) el plano es **versión 2**; si no, versión 1. Texto con saltos de
  línea LF.
- El editor **no edita el rótulo** (todavía): si abre un plano versión 2 con `rotulo`, lo
  **conserva tal cual** al guardar. Lo mismo con `"etiqueta_escala": false` de cada detalle.
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
