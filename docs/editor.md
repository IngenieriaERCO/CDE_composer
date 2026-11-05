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

## 3. Qué se ve en la hoja

| Elemento | Aspecto |
|---|---|
| Hoja A1 completa | `plantilla.png` de fondo (rótulo incluido, sin detalles). |
| Área de dibujo | Borde azul discontinuo: es la ÚNICA zona activa. |
| Rótulo, localización, notas, convenciones, cajetín | Capa gris rayada: bloqueadas, no se puede colocar nada encima. Salen solo de los datos `zonas` (el editor no deduce nada del dibujo). |
| Elementos fijos (rosa de los vientos, recuadro de capas) | Borde naranja discontinuo con su nombre «(fijo)». Se pueden tapar, pero se advierte; el borde se pone rojo si algo los tapa. |
| Detalle | Su miniatura; borde gris = página; borde celeste discontinuo = dibujo real (`page_bounds_mm`). Seleccionado: borde azul grueso. Con advertencias: borde amarillo, naranja o rojo. |

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
| Mover la hoja | Arrastrar el fondo. |
| Acercar / alejar | Rueda del mouse (hacia el cursor) o botones **+** / **−**. |
| Ver la hoja completa | **Ajustar**. |
| Paso de ajuste | Selector **Paso**: 0,1 / 1 / 5 / 10 mm (al arrastrar y con las flechas). |
| Mover el seleccionado | Flechas: un paso (↑ = +Y, hacia arriba del papel). Con **Shift**: 10 pasos. |
| Quitar el seleccionado | **Supr**. |
| Quitar la selección | Clic en el fondo. |
| Guardar | **Ctrl+S** o **Guardar plano**. |

## 5. Advertencias

Son las mismas de `componer`, con el mismo texto (salen de un único lugar,
`advertencias.py`). Ninguna impide guardar ni componer.

| Nivel | Cuándo | Qué significa |
|---|---|---|
| Advertencia (amarillo) | Se traslapan las PÁGINAS de dos detalles, pero no sus dibujos. | El margen blanco del de encima tapa una franja del de abajo. |
| ADVERTENCIA FUERTE (naranja) | Se traslapan los DIBUJOS de dos detalles. | El de encima tapa parte del dibujo del de abajo. |
| ADVERTENCIA FUERTE (naranja) | La PÁGINA de un detalle tapa un elemento fijo (p. ej. la rosa). | Su fondo blanco lo tapa, aunque el dibujo no lo toca. |
| ADVERTENCIA MUY FUERTE (rojo) | El DIBUJO de un detalle se monta sobre un elemento fijo. | El dibujo y su fondo blanco tapan el elemento. |

Mientras el exportador siga dejando un fondo blanco en cada detalle, lo que está encima tapa
lo de abajo.

## 6. Guardar y abrir

- **Guardar plano** escribe un `plano.json` versión 1 (ver [formato_plano.md](formato_plano.md)):
  el formato, `plantilla: null` y los detalles en el orden de apilado con `id`, `manifiesto` y
  `posicion_mm` redondeada a 0,01 mm (siempre hacia dentro del área de dibujo, para no salirse
  por un redondeo). Texto con saltos de línea LF.
- En Edge y Chrome aparece el diálogo de **Guardar como** (nombre sugerido `plano.json`). Si el
  navegador no lo ofrece o falla (permisos, archivo abierto desde el disco), el plano se
  **descarga** a la carpeta de descargas: **muévalo** a la carpeta de `editor.html` antes de
  componer. Si usted cancela el diálogo, no pasa nada.
- **Dónde guardarlo**: en la **misma carpeta que `editor.html`**. Las rutas del plano
  (`formato`, `manifiesto`) son relativas a esa carpeta. La pantalla muestra la carpeta en la
  que se generó el editor; es un dato informativo (desde una página no se puede saber la
  ruta real del disco): si movió el editor, use la carpeta donde está ahora.
- **Abrir plano.json** carga un plano guardado. Debe ser versión 1 y cada manifiesto debe
  estar en el catálogo del editor; si no, un mensaje explica qué falla y no se carga nada. Un
  detalle con `centrar: true` se coloca centrado (igual que `componer`); uno que se sale del
  área de dibujo se acomoda dentro y se avisa.
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
