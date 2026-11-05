# Componedor PDF (ERCO)

Arma planos A1 exactos en PDF a partir de los detalles vectoriales del
Exportador Vectorial, sin abrir AutoCAD.

## Instalación (Windows, PowerShell)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

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
| `componer` | Compone un plano con varios detalles a partir de un `plano.json` (ver [docs/formato_plano.md](docs/formato_plano.md)). |
| `preparar-editor` | Prepara `editor_datos.json`, `plantilla.png` y miniaturas para el editor de planos (ver [docs/formato_editor_datos.md](docs/formato_editor_datos.md)). |
| `detectar-elementos` | Mide los elementos fijos de la plantilla dentro del área de dibujo (rosa, recuadro de capas) y genera un PDF de verificación. |

Ejemplos rápidos (uno por comando):

```powershell
python -m componedor.cli hoja-vacia --orientacion horizontal --salida data/output/a1_horizontal.pdf
python -m componedor.cli hoja-formato --formato formatos/A1_ERCO.json --salida data/output/a1_erco.pdf --guias
python -m componedor.cli colocar --formato formatos/A1_ERCO.json --detalle data/input/detalle.pdf --salida data/output/a1_detalle.pdf --centrar
python -m componedor.cli referencia --formato formatos/A1_ERCO.json --salida data/output/referencia_A1.pdf
python -m componedor.cli leer-manifiesto data/input/detalle.manifest.json
python -m componedor.cli paquetes data/input --recursivo --verificar
python -m componedor.cli verificar-paquete data/input/detalle.manifest.json
python -m componedor.cli inventario data/input --formato formatos/A1_ERCO.json
python -m componedor.cli componer data/planos/mi_plano.json --salida data/output/mi_plano.pdf
python -m componedor.cli preparar-editor data/input --formato formatos/A1_ERCO.json --salida data/editor
python -m componedor.cli detectar-elementos --formato formatos/A1_ERCO.json --salida data/output/elementos_plantilla.pdf
```

El contrato del paquete del exportador (PDF + TXT + manifiesto) está en
[docs/contrato_paquete.md](docs/contrato_paquete.md).

## Uso detallado

Crear una hoja A1 vacía (horizontal 841 x 594 mm o vertical 594 x 841 mm):

```powershell
python -m componedor.cli hoja-vacia --orientacion horizontal --salida data/output/a1_horizontal.pdf
```

Crear una hoja con el marco del formato A1 ERCO (y, con `--guias`, las zonas como
líneas discontinuas con su nombre). Al final imprime una tabla con cada zona y su tamaño en mm:

```powershell
python -m componedor.cli hoja-formato --formato formatos/A1_ERCO.json --salida data/output/a1_erco.pdf --guias
```

Colocar un detalle PDF del exportador (ya viene a escala física, se coloca **sin escalar**:
1 mm del detalle = 1 mm en la hoja) en una zona, en una posición dada (esquina inferior
izquierda del detalle, en mm de papel) o centrado:

```powershell
python -m componedor.cli colocar --formato formatos/A1_ERCO.json --detalle data/input/detalle.pdf --salida data/output/a1_detalle.pdf --posicion 100 200
python -m componedor.cli colocar --formato formatos/A1_ERCO.json --detalle data/input/detalle.pdf --salida data/output/a1_detalle.pdf --centrar --zona area_dibujo --guias
```

El detalle entra como vector (Form XObject). Se usa su tamaño visible (CropBox y /Rotate).
Si no cabe en la zona, el programa explica cuánto se pasa y no crea el archivo.

Con el manifiesto del exportador se puede anclar un punto CAD a un punto del papel (por
ejemplo, que una esquina o un eje del dibujo caiga en una coordenada exacta de la hoja):

```powershell
python -m componedor.cli colocar --formato formatos/A1_ERCO.json --detalle data/input/perfil_k0010.pdf --manifiesto data/input/perfil_k0010.manifest.json --salida data/output/a1_ancla.pdf --ancla-cad 1000000.00 2000000.00 --ancla-papel 40 300
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

### Validación con geometría de referencia

`referencia` genera en memoria un detalle sintético a 1:50 (cuadrado de 5 x 5 m, rectángulo
de 5 x 2 m, diagonal, texto «REFERENCIA 1:50» y una marca de orientación), lo ancla en la
hoja (esquina inferior izquierda del cuadrado en (100, 100) mm), guarda el PDF y lo mide:
hoja, marco, plantilla, tamaños y posiciones (±0,1 mm), escala medida (1:50, diferencia
relativa < 0,0005), orientación, que no haya imágenes nuevas y que el texto siga siendo
texto. Escribe un TXT con el mismo nombre del PDF y termina con código 0 si todo pasa y 1
si algo falla.

```powershell
python -m componedor.cli referencia --formato formatos/A1_ERCO.json --salida data/output/referencia_A1.pdf
python -m componedor.cli referencia --formato formatos/A1_ERCO.json --salida data/output/referencia_A1.pdf --sin-plantilla --sobrescribir
python -m componedor.cli referencia --formato formatos/A1_ERCO.json --salida data/output/referencia_A1.pdf --detalle data/input/detalle.pdf --manifiesto data/input/detalle.manifest.json --sobrescribir
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
python -m componedor.cli componer data/planos/mi_plano.json --salida data/output/mi_plano.pdf --sobrescribir
```

Cada detalle pasa por el importador; si alguno se rechaza, no se genera el PDF. Cada
página debe quedar dentro del área de dibujo (el rótulo es inamovible). Los traslapes entre
detalles son advertencias. El PDF se verifica antes de entregarlo (posición de cada dibujo
±0,1 mm, rótulo intacto, sin imágenes nuevas).

### Elementos fijos de la plantilla y datos del editor

El rótulo trae elementos dentro del área de dibujo (rosa de los vientos, recuadro «LAYERS
AUTORIZADOS»). Se declaran en `elementos_plantilla` del formato (rectángulos en mm de
papel, medidos con `detectar-elementos`, nunca inventados) y `componer` advierte si un
detalle los tapa con su página (ADVERTENCIA FUERTE) o si su dibujo se monta encima
(ADVERTENCIA MUY FUERTE). No es error.

`preparar-editor` deja en una carpeta los datos y las imágenes que usará el editor HTML
de planos: zonas (solo el área de dibujo es editable), elementos fijos, detalles aceptados
con miniatura y rechazados con sus motivos. Estructura en
[docs/formato_editor_datos.md](docs/formato_editor_datos.md).

## Formatos

`formatos/A1_ERCO.json` define la hoja, el marco y las zonas (área de dibujo, rótulo,
localización, notas, convenciones, cajetín) como `[xmin, ymin, xmax, ymax]` en mm, con
origen en la esquina inferior izquierda de la hoja horizontal, además de los grosores de
línea (marco 0,5 mm, guías 0,13 mm) y, opcionalmente, `"plantilla"`: ruta del PDF del
rótulo, relativa a la carpeta del JSON (`"../plantillas/rotulo_A1_ERCO.pdf"`).
Al cargarlo se valida la geometría y que la plantilla exista.

## Pruebas

```powershell
python -m pytest -q
```

Estado del proyecto: ver [docs/estado_proyecto.md](docs/estado_proyecto.md).
