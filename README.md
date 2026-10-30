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

Ejemplos rápidos (uno por comando):

```powershell
python -m componedor.cli hoja-vacia --orientacion horizontal --salida data/output/a1_horizontal.pdf
python -m componedor.cli hoja-formato --formato formatos/A1_ERCO.json --salida data/output/a1_erco.pdf --guias
python -m componedor.cli colocar --formato formatos/A1_ERCO.json --detalle data/input/detalle.pdf --salida data/output/a1_detalle.pdf --centrar
python -m componedor.cli referencia --formato formatos/A1_ERCO.json --salida data/output/referencia_A1.pdf
```

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
`--manifiesto` (en cualquier modo) se imprime además el rectángulo que ocupa el dibujo en
el papel y una comprobación informativa entre la matriz y los trazos del PDF.

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
