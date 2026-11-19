# Componedor PDF (ERCO)

Arma planos A1 exactos en PDF a partir de los detalles vectoriales del
Exportador Vectorial, sin abrir AutoCAD.

## Instalación (Windows, PowerShell)

Para instalar todo en otro PC (este repositorio, el Exportador `CDE_Extractor`, los archivos de
ERCO que no están en git y cómo conectarlos), siga
[docs/instalacion_y_uso.md](docs/instalacion_y_uso.md). En resumen, para el Componedor:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Uso diario: dos accesos directos (doble clic)

1. **`Abrir editor.bat`**: genera el editor con las rutas de `componedor.json` y lo abre en el
   navegador con un **servidor local** (solo en esta computadora, `127.0.0.1`) que habilita
   **«Cargar DXF»** y **«Cargar ortofoto»** (un GeoTIFF de fondo, detrás de los detalles; ver
   [docs/editor.md](docs/editor.md#2g-ortofoto-de-fondo-con-servidor-local)). Deje abierta esa ventana negra mientras usa el editor: al cerrarla se apaga
   el servidor. Si el servidor no puede arrancar, el `.bat` abre el editor sin servidor, como
   antes. Arme el plano y guarde el `plano.json` en `editor\` (al lado de `editor.html`) o en
   `planos\`: las dos carpetas están al mismo nivel, así que el plano funciona en cualquiera.
2. **`Componer.bat`**: arrastre un `plano.json` sobre él (o haga doble clic y arrastre la ruta a
   la ventana). Compone con el formato de `componedor.json`, deja el PDF en
   `resultados\<nombre del plano>.pdf` y lo abre. Si hay errores o advertencias, los muestra y
   espera una tecla (con error no hay PDF).

Los dos usan `.venv\Scripts\python.exe` si existe; si no, el `python` del sistema. Regenerar el
editor nunca borra los `plano.json` que usted guardó.

## Carpetas de trabajo

| Carpeta | Qué guarda | ¿Va a git? |
|---|---|---|
| `planos/` | sus `plano.json` (y, si llevan ortofoto, su copia reducida `<plano>_ortofoto/`, que deja `componer`) | no (datos de ERCO) |
| `editor/` | `editor.html`, el único archivo que genera el editor (todo va incrustado dentro); y los planos que usted guarde ahí, con su `<plano>_ortofoto/` | no (se regenera) |
| `resultados/` | los PDF que deja `Componer.bat` | no |
| `firmas/<persona>/firma.png` | las firmas en imagen, una carpeta por persona | no (datos personales) |
| `notas/<grupo>/*.txt` | el catálogo de notas típicas (cada subcarpeta es un grupo) | no, hasta que se decida |
| `data/input` | paquetes del Exportador Vectorial (PDF + manifiesto) | no |
| `data/pruebas` | paquetes y planos de prueba que se conservan (una prueba lee `planos/ejemplo_rotulo_v2.json`) | no |
| `data/verificacion` | scripts y capturas de las verificaciones del editor en Edge | no |
| `data/cache_exportador` | carpeta del trabajador del exportador («Cargar DXF») y los registros `trabajador.log`, `componedor.log` y `servidor.log` | no |

- `data/input`: los paquetes del Exportador Vectorial (PDF + manifiesto) que el editor ofrece
  para armar el plano. Hoy son de prueba; en un proyecto real se cambia la ruta en
  `componedor.json` (`editor.paquetes`).
- `resultados/`: ahí deja `Componer.bat` el PDF de cada plano (`resultados\<nombre del plano>.pdf`).
- `data/output` ya no se usa para los planos: lo reemplaza `resultados/`.

## Configuración (`componedor.json`)

Un solo archivo en la raíz con todas las rutas, para generar siempre el mismo editor y
componer siempre con el mismo formato. Las rutas son relativas a la carpeta del archivo:

```json
{
  "version": 1,
  "formato": "formatos/A1_ERCO.json",
  "editor": {"paquetes": "data/input", "salida": "editor", "notas": "notas",
             "firmas": "firmas", "proyecto": null},
  "componer": {"resultados": "resultados"},
  "exportador": {"comando": "cde-exporter", "trabajo": "data/cache_exportador", "margen_mm": 5},
  "ortofoto": {"ppp": 300, "calidad_jpeg": 85}
}
```

`formato`, `editor.paquetes`, `editor.salida` y `componer.resultados` son obligatorios;
`notas`, `firmas` y `proyecto` son opcionales (`null` = no se usa). Una clave mal escrita o una
ruta que no existe es error, y se listan todos los problemas juntos.

La sección `exportador` es opcional: sin ella el editor funciona igual, pero sin «Cargar DXF».
`comando` es el comando del Exportador Vectorial (o una lista `[programa, argumentos…]`);
`trabajo`, la carpeta del trabajador (se crea); `margen_mm`, el margen de página con que se
exportará (por defecto 5 mm); `cache_previas_mb` (opcional), el tope de la caché de vistas previas
del trabajador (por defecto, el suyo: 500 MB); `paquetes` (opcional, `data/input/dxf`), dónde
publica «Exportar»; `para_borrar` (opcional, `_para_borrar`), adónde se mueven los paquetes viejos;
`anonimos_min_entidades` (opcional, 100), cuántas entidades visibles debe dibujar un bloque
anónimo `*U` para ofrecerlo en «Anónimos (opcionales)».
Ver [docs/servidor_editor.md](docs/servidor_editor.md).

La sección `ortofoto` es opcional (sin ella, los mismos valores): `ppp` (de 72 a 1200) es la
resolución con que va la ortofoto en el PDF, en píxeles por pulgada de papel, y `calidad_jpeg`
(de 1 a 100), su calidad. `componer --config` (y `Componer.bat`) las usa; sin `--config`, 300 y
85; `cuadricula_intervalo_m` (50) es el intervalo por defecto de la cuadrícula de
coordenadas. Al componer con la ortofoto original, `componer` deja una **copia reducida** en
`<nombre del plano>_ortofoto/`, al lado del plano.json, para poder volver a componerlo sin el
original (ver [docs/formato_plano.md](docs/formato_plano.md#ortofoto-de-fondo-versión-4)).

## Comandos

Todos se ejecutan como `python -m componedor.cli <comando> ...`. Las medidas van en mm de
papel (origen en la esquina inferior izquierda de la hoja, Y hacia arriba).

| Comando | Qué hace |
|---|---|
| `hoja-vacia` | Hoja A1 vacía, horizontal o vertical. |
| `hoja-formato` | Hoja del formato: rótulo (plantilla) o marco propio, y guías de zonas. |
| `colocar` | Coloca un detalle PDF sin escalar: por posición, centrado o anclando un punto CAD. |
| `referencia` | Compone un detalle de medidas conocidas, mide el PDF y escribe un informe PASA/FALLA. |
| `leer-manifiesto` | Lee un manifiesto del exportador, valida su estructura y muestra un resumen. |
| `paquetes` | Localiza los paquetes del exportador en una carpeta y dice si están completos; con `--verificar`, agrega integridad (bytes, SHA-256, que abra, una página) y coherencia (geometría del manifiesto contra el PDF, escala física garantizada). |
| `verificar-paquete` | Muestra todas las comprobaciones de integridad y coherencia de un paquete y «RESULTADO: PASA / FALLA». |
| `inventario` | Lista los detalles de una carpeta: aceptados o rechazados (con motivos), tamaños, si caben en la zona y escala sugerida. |
| `componer` | Compone un plano con varios detalles a partir de un `plano.json`: detalles, textos del rótulo, etiquetas «ESC: 1:N» y rosa de los vientos (ver [docs/formato_plano.md](docs/formato_plano.md)). Con `--config componedor.json`, usa ese formato y deja el PDF en `resultados/`; con `--codigo-avisos`, termina con código 3 si hubo advertencias. |
| `editor` | Genera `editor.html`, un editor visual de planos de un solo archivo (arrastrar detalles y la rosa, y guardar el plano.json). Con `--config componedor.json` toma todas las rutas del archivo. Ver [docs/editor.md](docs/editor.md). |
| `servidor` | Abre ese `editor.html` desde un servidor local (solo `127.0.0.1`, con token) que habilita «Cargar DXF» con el trabajador del exportador (`cde-exporter worker`). Solo `--config componedor.json`; `--no-abrir`, `--puerto`, `--inactividad-min`. Lo usa `Abrir editor.bat`. Ver [docs/servidor_editor.md](docs/servidor_editor.md). |
| `preparar-editor` | Deja por separado los datos e imágenes que el editor lleva incrustados (`editor_datos.json`, `plantilla.png`, `plantilla.svg`, `rosa.png`, miniaturas y símbolos), para revisarlos (ver [docs/formato_editor_datos.md](docs/formato_editor_datos.md)). |
| `crear-plantilla-v3` | Crea `plantillas/rotulo_A1_ERCO_v3.pdf` desde la v2 (que no se toca): sin la fila DISEÑADOR \| REVISOR y con el logo centrado. Ver «Rótulo (plantilla)». |
| `detectar-elementos` | Mide los elementos fijos de la plantilla dentro del área de dibujo (la rosa de los vientos) y genera un PDF de verificación. |
| `extraer-simbolos` | Arma la biblioteca de símbolos de CONVENCIONES (vector) desde la leyenda de un plano real: `simbolos/convenciones_erco.pdf` (no se versiona) e `indice.json`. |

Ejemplos rápidos (uno por comando):

```powershell
python -m componedor.cli hoja-vacia --orientacion horizontal --salida resultados/a1_horizontal.pdf
python -m componedor.cli hoja-formato --formato formatos/A1_ERCO.json --salida resultados/a1_erco.pdf --guias
python -m componedor.cli colocar --formato formatos/A1_ERCO.json --detalle data/input/detalle.pdf --salida resultados/a1_detalle.pdf --centrar
python -m componedor.cli referencia --formato formatos/A1_ERCO.json --salida resultados/referencia_A1.pdf
python -m componedor.cli leer-manifiesto data/input/detalle.manifest.json
python -m componedor.cli paquetes data/input --recursivo --verificar
python -m componedor.cli verificar-paquete data/input/detalle.manifest.json
python -m componedor.cli inventario data/input --formato formatos/A1_ERCO.json
python -m componedor.cli componer planos/mi_plano.json --config componedor.json --sobrescribir
python -m componedor.cli componer planos/mi_plano.json --salida resultados/mi_plano.pdf
python -m componedor.cli editor --config componedor.json --sobrescribir
python -m componedor.cli editor data/input --formato formatos/A1_ERCO.json --salida editor
python -m componedor.cli preparar-editor data/input --formato formatos/A1_ERCO.json --salida resultados/datos_editor
python -m componedor.cli detectar-elementos --formato formatos/A1_ERCO.json --salida resultados/elementos_plantilla.pdf
python -m componedor.cli extraer-simbolos "C:\...\plano_con_leyenda.pdf" --formato formatos/A1_ERCO.json
```

El contrato del paquete del exportador (PDF + TXT + manifiesto) está en
[docs/contrato_paquete.md](docs/contrato_paquete.md).

## Uso detallado

Crear una hoja A1 vacía (horizontal 841 x 594 mm o vertical 594 x 841 mm):

```powershell
python -m componedor.cli hoja-vacia --orientacion horizontal --salida resultados/a1_horizontal.pdf
```

Crear una hoja con el marco del formato A1 ERCO (y, con `--guias`, las zonas como
líneas discontinuas con su nombre). Al final imprime una tabla con cada zona y su tamaño en mm:

```powershell
python -m componedor.cli hoja-formato --formato formatos/A1_ERCO.json --salida resultados/a1_erco.pdf --guias
```

Colocar un detalle PDF del exportador (ya viene a escala física, se coloca **sin escalar**:
1 mm del detalle = 1 mm en la hoja) en una zona, en una posición dada (esquina inferior
izquierda del detalle, en mm de papel) o centrado:

```powershell
python -m componedor.cli colocar --formato formatos/A1_ERCO.json --detalle data/input/detalle.pdf --salida resultados/a1_detalle.pdf --posicion 100 200
python -m componedor.cli colocar --formato formatos/A1_ERCO.json --detalle data/input/detalle.pdf --salida resultados/a1_detalle.pdf --centrar --zona area_dibujo --guias
```

El detalle entra como vector (Form XObject). Se usa su tamaño visible (CropBox y /Rotate).
Si no cabe en la zona, el programa explica cuánto se pasa y no crea el archivo.

Con el manifiesto del exportador se puede anclar un punto CAD a un punto del papel (por
ejemplo, que una esquina o un eje del dibujo caiga en una coordenada exacta de la hoja):

```powershell
python -m componedor.cli colocar --formato formatos/A1_ERCO.json --detalle data/input/perfil_k0010.pdf --manifiesto data/input/perfil_k0010.manifest.json --salida resultados/a1_ancla.pdf --ancla-cad 1000000.00 2000000.00 --ancla-papel 40 300
```

`--ancla-cad X Y` (unidades del dibujo) y `--ancla-papel X Y` (mm de papel) van juntos,
requieren `--manifiesto` y no se combinan con `--posicion` ni `--centrar`. Con
`--manifiesto` (en cualquier modo) el paquete debe estar completo, íntegro y coherente
(incluida la escala física garantizada) y `--detalle` debe ser el PDF que indica el
manifiesto; si no, no se coloca y se listan los problemas. Se imprime además el rectángulo
que ocupa el dibujo en el papel.

En todos los subcomandos, si el archivo de salida ya existe el programa se niega a
reemplazarlo; para reemplazarlo, agregue `--sobrescribir`.

### Rótulo (plantilla)

Si el formato tiene la clave `"plantilla"`, `hoja-formato` y `colocar` ponen ese PDF del
rótulo (impreso desde AutoCAD a 1:1) como fondo de la hoja, en (0, 0), sin escalar; los
detalles van encima. Se acepta una diferencia de tamaño de hasta ±0,5 mm (AutoCAD redondea
a puntos enteros) y se comprueba que el marco del rótulo coincide con el marco del formato
(±0,5 mm). Con plantilla no se dibuja el marco propio (el rótulo trae el oficial).
Para generar la hoja sin rótulo agregue `--sin-plantilla`.

El PDF del rótulo (`plantillas/*.pdf`) es material de ERCO y no se versiona.

**Plantilla v3** (la que usa hoy `formatos/A1_ERCO.json`): es la v2 sin la fila
«DISEÑADOR | REVISOR» (encima del logo; queda vacía) y con el logo de ERCO centrado en la
columna del rótulo. Como `plantillas/` no va a git, se genera en cada equipo desde la v2, que
**no se modifica**:

```powershell
python -m componedor.cli crear-plantilla-v3
# = --origen plantillas/rotulo_A1_ERCO_v2.pdf --salida plantillas/rotulo_A1_ERCO_v3.pdf
```

Borra (no tapa con blanco) los trazos que caen completos dentro de esa fila (las letras y la
línea vertical) y sus dos anotaciones invisibles, y reinserta la misma imagen del logo (sin
recomprimirla) corrida en X. Se verifica sola: la v2 conserva su MD5, fuera de la fila y del
logo la hoja se ve igual píxel a píxel y el logo queda centrado ±0,1 mm; si algo falla, no
escribe nada. Para reemplazar una v3 existente, `--sobrescribir`.

### Validación con geometría de referencia

`referencia` genera en memoria un detalle sintético a 1:50 (cuadrado de 5 x 5 m, rectángulo
de 5 x 2 m, diagonal, texto «REFERENCIA 1:50» y una marca de orientación), lo ancla en la
hoja (esquina inferior izquierda del cuadrado en (100, 100) mm), guarda el PDF y lo mide:
hoja, marco, plantilla, tamaños y posiciones (±0,1 mm), escala medida (1:50, diferencia
relativa < 0,0005), orientación, que no haya imágenes nuevas y que el texto siga siendo
texto. Escribe un TXT con el mismo nombre del PDF y termina con código 0 si todo pasa y 1
si algo falla.

```powershell
python -m componedor.cli referencia --formato formatos/A1_ERCO.json --salida resultados/referencia_A1.pdf
python -m componedor.cli referencia --formato formatos/A1_ERCO.json --salida resultados/referencia_A1.pdf --sin-plantilla --sobrescribir
python -m componedor.cli referencia --formato formatos/A1_ERCO.json --salida resultados/referencia_A1.pdf --detalle data/input/detalle.pdf --manifiesto data/input/detalle.manifest.json --sobrescribir
```

Si el PDF de la plantilla no existe, avisa y sigue sin ella. Con `--detalle` y
`--manifiesto` agrega la sección «detalle real»: coloca ese detalle centrado en una hoja
limpia y compara los límites del dibujo con `page_bounds_mm` (±0,2 mm) y el tamaño de
página con `page_size_mm` (±0,1 mm).

### Paquetes del exportador

Cada detalle llega como paquete: `<prefijo>.pdf`, `<prefijo>.txt` y
`<prefijo>.manifest.json`. Flujo: localizar → integridad → coherencia → importar →
inventario (ver [docs/contrato_paquete.md](docs/contrato_paquete.md)).

```powershell
# Leer un manifiesto y validar su estructura (resumen o lista de problemas):
python -m componedor.cli leer-manifiesto data/input/detalle.manifest.json

# Localizar los paquetes de una carpeta; con --verificar, integridad y coherencia:
python -m componedor.cli paquetes data/input --verificar

# Todas las comprobaciones de un paquete, con esperado / medido / tolerancia:
python -m componedor.cli verificar-paquete data/input/detalle.manifest.json

# Inventario: aceptados / rechazados, si caben en el área de dibujo y escala sugerida:
python -m componedor.cli inventario data/input --recursivo --formato formatos/A1_ERCO.json
```

Un paquete solo se acepta si está completo, íntegro (bytes y SHA-256 del PDF), coherente
(geometría del manifiesto contra el PDF) y con la escala física garantizada. Si no, los
motivos salen con su categoría: `[manifiesto]`, `[archivos]`, `[integridad]`,
`[coherencia]` o `[escala]`. `inventario` termina con código 1 solo si hay rechazados; que
un detalle no quepa en la zona es una nota, no un rechazo.

### Varios detalles en un plano (`componer`)

Un `plano.json` lista los detalles (por su manifiesto) y dónde va cada uno: `posicion_mm`
(esquina inferior izquierda de la página del detalle, mm de papel) o `centrar: true`. Las
rutas son relativas a la carpeta del plano.json. Formato completo y reglas en
[docs/formato_plano.md](docs/formato_plano.md).

```powershell
python -m componedor.cli componer planos/mi_plano.json --config componedor.json --sobrescribir
python -m componedor.cli componer planos/mi_plano.json --salida resultados/mi_plano.pdf --sobrescribir
```

Con `--config` se usa el formato de `componedor.json` aunque el plano indique otro (lo avisa) y el
PDF va a `<resultados>/<nombre del plano>.pdf`; no se combina con `--salida`. Las demás rutas del
plano (paquetes, notas) siguen siendo relativas al plano.json, esté donde esté. Es lo que hace
`Componer.bat`.

Cada detalle pasa por el importador; si alguno se rechaza, no se genera el PDF. Cada
página debe quedar dentro del área de dibujo (el rótulo es inamovible). Los traslapes entre
detalles son advertencias. El PDF se verifica antes de entregarlo (posición de cada dibujo
±0,1 mm, rótulo intacto, sin imágenes nuevas, rosa y textos en su sitio ±0,1 mm).

**Rótulo y rosa (plano.json versión 2)**: la sección `rotulo` del plano trae los textos
(título, revisiones, firmas, No. PLANO, HOJA/DE, coordenadas…), las **notas** (archivos .txt
con una nota por línea y viñetas con «- », más notas adicionales; numeradas solas, con
sangría francesa) y las
**convenciones** (símbolos copiados como vector de la biblioteca `simbolos/`, que se arma una
vez con `extraer-simbolos`, más su descripción) y, en la celda FIRMA, texto o una **imagen**
(`{"imagen": "<persona>"}` → `firmas/<persona>/firma.png`, una carpeta por persona, fuera de
git, con transparencia); ESCALA (`1:1.000` o
`INDICADAS`) y REV. (la última letra de las revisiones) se calculan solos. Los textos se
escriben en Arial embebida, centrados en su celda; si uno no cabe, error claro con el campo,
el texto y las medidas (nunca se recorta). Cada detalle lleva su etiqueta «ESC: 1:N». La
rosa de los vientos se puede mover u ocultar con `rosa_vientos`. La versión 1 sigue valiendo.

### Editor visual de planos (`editor`)

La forma recomendada de armar un plano: doble clic en `Abrir editor.bat`, arrastre los
detalles dentro del área de dibujo (el rótulo está bloqueado), guarde el `plano.json` en
`editor\` o `planos\` y arrástrelo sobre `Componer.bat`. Lo mismo desde la consola:

```powershell
python -m componedor.cli editor --config componedor.json --sobrescribir
# ... abrir editor/editor.html, armar el plano y guardar editor/plano.json ...
python -m componedor.cli componer editor/plano.json --config componedor.json --sobrescribir
```

Sin `componedor.json`, las rutas se dan a mano (no se mezclan con `--config`):
`editor data/input --formato formatos/A1_ERCO.json --salida editor --notas notas --firmas firmas
--proyecto proyecto.json`.

`editor.html` es un solo archivo (sin servidor, sin internet, sin librerías externas). Muestra
en vivo las mismas advertencias que `componer`. Con los paquetes nuevos del exportador (sin
fondo blanco) las miniaturas son transparentes y se ve lo mismo que saldrá en el PDF; la
**Vista limpia** (botón o tecla V) oculta las ayudas de edición. La rosa de los vientos se
arrastra como un detalle, se oculta con una casilla y se devuelve a su sitio con «Restaurar
posición». El panel **Rótulo** tiene formularios para los campos del rótulo (título, No. PLANO,
HOJA/DE, coordenadas…), las **revisiones** y las **firmas** (texto o una
persona de la lista de `--firmas` o nueva; «Cargar firma…» recorta y limpia una imagen de la
firma solo en el navegador y la guarda como `firmas/<persona>/firma.png`, sin incrustarla
nunca), con calendario para las fechas (`dd/mm/aa`), ESCALA y REV.
calculadas y validación en vivo con los mismos textos que `componer`. Cada texto del rótulo
(título, revisiones, firmas, notas y descripciones de convenciones) se **mide** como en
`componer`: si se reducirá, aviso ámbar «se escribió a X mm» junto al campo; si no cabe ni a la
altura mínima, error rojo con el mismo texto de `componer` (el editor ayuda; `componer` vuelve a
validar todo). `--proyecto` prellena un
plano nuevo con los datos que se repiten ([docs/formato_proyecto.md](docs/formato_proyecto.md)).
El panel **Notas** muestra el catálogo de notas típicas por tema con casillas, la lista de
notas del plano (numerada en vivo, con subir/bajar/quitar y texto editable) y notas a mano con
viñetas; se guardan copiadas en `rotulo.notas.adicionales`.
Abrir y guardar un plano sin tocar nada deja el plano.json idéntico; al editar, solo cambia lo
editado. El panel **Convenciones** muestra los símbolos del índice como miniaturas con
casillas, y la lista del plano con la casilla de la leyenda de cada uno (columna y fila, en
vivo), subir/bajar/quitar y descripción editable (tope de 24). De las firmas solo llegan los
**nombres** de las personas: las imágenes nunca se incrustan.
Con la casilla **Vista previa del rótulo**, el lienzo dibuja en su sitio los textos del rótulo,
las notas numeradas, los símbolos de convenciones, las etiquetas «ESC: 1:N» y la caja de cada
firma en imagen, con las mismas posiciones y alturas que `componer`. Un campo que no cabe no se
dibuja y su celda queda en rojo; una etiqueta «ESC» que no cabe se avisa en vivo. La plantilla
de fondo va en vector (nítida al acercar).
Guía completa en [docs/editor.md](docs/editor.md).
Si Node está instalado, `pytest` prueba también la lógica del editor (JavaScript).

**«Cargar DXF»** (etapa 1, con `Abrir editor.bat`): el servidor abre el cuadro de Windows para
elegir un DXF, el trabajador del Exportador Vectorial lo lee una sola vez y el editor muestra
una **carpeta** con sus bloques: tamaño real en m, unidades, **escala sugerida** (la primera de
la lista estándar con la que la página cabe en el área de dibujo) y notas (caja aproximada,
sólidos 3D, capas ocultas, unidades sin verificar). Requiere un `cde-exporter` con la orden
`worker`; si el instalado no la tiene, el editor lo dice. Detalles y seguridad en
[docs/servidor_editor.md](docs/servidor_editor.md).

**Bloques en la hoja** (etapa 2): «Agregar al plano» pone un bloque como **caja exacta** (la
página que tendrá al exportarlo a 1:N) con la **vista previa PNG** del trabajador encima, en su
lugar exacto. La escala se cambia con el selector, las teclas **+ / −** o el tirador de la
esquina, y el centro no se mueve; si no cabe, queda en rojo. Un plano con bloques sin exportar se
guarda como **versión 3** ([docs/formato_plano.md](docs/formato_plano.md)); `componer` dice qué
falta por exportar.

**Exportar** (etapa 3): «Exportar bloques del plano» publica un paquete por bloque en
`data/input/dxf/<DXF>/`, uno a la vez, con barra de avance, Cancelar y «Detener a la fuerza».
Cada paquete se verifica (`importar_paquete` y que sea el pedido) y el bloque pasa a ser un
detalle normal, puesto por el centro CAD. Lo ya publicado se reutiliza; los paquetes viejos que
se reemplazan se mueven a `_para_borrar/`.

### Elementos fijos de la plantilla y datos del editor

El rótulo v2 trae un elemento dentro del área de dibujo: la rosa de los vientos. Se declara
en `elementos_plantilla` del formato (rectángulo en mm de papel, medido con
`detectar-elementos`, nunca inventado) y `componer` advierte si un detalle la tapa con su
página (ADVERTENCIA FUERTE) o si su dibujo se monta encima (ADVERTENCIA MUY FUERTE), con la
rosa en su posición final. No es error.

`preparar-editor` deja en una carpeta los datos y las imágenes que el editor HTML lleva
incrustados (el comando `editor` ya no los deja junto a `editor.html`): zonas (solo el área de dibujo es editable), elementos fijos, detalles aceptados
con miniatura y rechazados con sus motivos. Estructura en
[docs/formato_editor_datos.md](docs/formato_editor_datos.md).

## Formatos

`formatos/A1_ERCO.json` define la hoja, el marco y las zonas (área de dibujo, rótulo,
localización, notas, convenciones, cajetín) como `[xmin, ymin, xmax, ymax]` en mm, con
origen en la esquina inferior izquierda de la hoja horizontal, además de los grosores de
línea (marco 0,5 mm, guías 0,13 mm) y, opcionalmente:

- `"plantilla"`: ruta del PDF del rótulo, relativa a la carpeta del JSON
  (`"../plantillas/rotulo_A1_ERCO_v3.pdf"`, generada con `crear-plantilla-v3`);
- `"elementos_plantilla"`: elementos fijos medidos dentro del área de dibujo (la rosa);
- `"rotulo"`: los campos de texto del rótulo (celda en mm, alineación, altura de texto,
  líneas, valor por defecto o calculado), las notas, la rejilla de convenciones con la ruta de
  la biblioteca de símbolos (`../simbolos/indice.json`), los `campos_retirados` (campos que
  el rótulo ya no tiene, hoy `disenador` y `revisor`: un plano viejo que los traiga se compone
  igual, se ignoran con un solo aviso) y la fuente
  (`C:/Windows/Fonts/arial.ttf`). Esquema versionado y validado: campos desconocidos, celdas
  fuera del rótulo o traslapadas son error.

`simbolos/indice.json` (se versiona) lista los símbolos de convenciones (id, descripción por
defecto, caja y trazos medidos); `simbolos/convenciones_erco.pdf` (no se versiona: sale de un
plano de ERCO) los trae como vectores, uno por página. Se generan con `extraer-simbolos`.

Al cargarlo se valida la geometría y que la plantilla exista; la fuente se comprueba al
componer.

## Pruebas

```powershell
python -m pytest -q
```

Estado del proyecto: ver [docs/estado_proyecto.md](docs/estado_proyecto.md).
