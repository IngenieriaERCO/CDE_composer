# Estado del proyecto

## Fase 1 — Núcleo de composición PDF ✅ CERRADA (2026-10-30)

Resumen: la aplicación arma una hoja A1 ERCO en PDF (rótulo como plantilla o marco
propio), coloca detalles vectoriales sin escalar (por posición, centrados o anclando un
punto CAD con la matriz del manifiesto) y se valida a sí misma con un detalle de
geometría conocida (`referencia`): tamaños y posiciones ±0,1 mm, escala 1:50 exacta,
orientación, sin rasterizar y texto como texto. 129 pruebas.

Comandos: `hoja-vacia`, `hoja-formato`, `colocar`, `referencia` (ver README).

### Subfase 1.1 — Base del repositorio y hoja A1 vacía ✅ (2026-10-29)

**Qué se hizo**
- Estructura del repositorio: `src/componedor`, `tests`, `data/input`, `data/output`
  (sin versionar), `docs`, `README.md`, `pyproject.toml`, `.gitignore`.
- Entorno `.venv` con Python 3.12.10; proyecto instalado en modo editable
  (`pip install -e ".[dev]"`) con PyMuPDF 2.0 y pytest 9.2.
- `unidades.py`: `mm_a_pt`, `pt_a_mm` (1 mm = 72 / 25,4 pt).
- `hoja.py`: `A1_MM = (841, 594)`, `tamano_hoja_mm(orientacion)`,
  `crear_hoja(orientacion)` → PDF de 1 página, rotación 0, en su orientación real.
- `cli.py`: subcomando `hoja-vacia --orientacion {horizontal|vertical} --salida RUTA
  [--sobrescribir]`. Se niega a reemplazar un archivo existente sin `--sobrescribir`
  y muestra el tamaño de la página en mm al terminar.

**Pruebas**: 11 pruebas, todas pasan (`python -m pytest -q`).
- Conversión mm/pt (una pulgada, ida y vuelta).
- Tamaño de página horizontal y vertical con tolerancia ±0,1 mm.
- Una sola página y rotación 0 en ambas orientaciones.
- Orientación inválida → `ValueError` con mensaje en español (módulo y CLI).
- CLI: crea el archivo, no sobrescribe sin permiso, sobrescribe con `--sobrescribir`.

### Subfase 1.2 — Marco, márgenes y zonas del formato A1 ERCO ✅ (2026-10-29)

**Qué se hizo**
- PyMuPDF fijado en `>=1.24,<2`, misma versión mayor que el Exportador Vectorial
  (que usa 1.28.2). `.venv` recreado; quedó PyMuPDF 1.28.2 sin dependencias extra.
  Las 11 pruebas de la 1.1 siguieron pasando.
- `formatos/A1_ERCO.json`: hoja, marco y zonas (`area_dibujo`, `rotulo`, `localizacion`,
  `notas`, `convenciones`, `cajetin`) en mm, origen inferior izquierdo; grosores
  marco 0,5 mm y guías 0,13 mm.
- `formato.py`: `cargar_formato` / `validar_formato` → `Formato`. Errores
  `FormatoInvalido` en español: medidas positivas, hoja en el origen, marco dentro de la
  hoja, zonas dentro del marco, `area_dibujo` y `rotulo` sin traslape, subzonas dentro
  del rótulo, grosores positivos, archivo inexistente o JSON mal escrito.
- `transformaciones.py`: `rect_papel_a_pdf` (mm, Y arriba → pt, Y abajo) y su inversa
  `rect_pdf_a_papel`. Único lugar donde se invierte Y.
- `dibujo.py`: `dibujar_marco` (0,5 mm, negro) y `dibujar_guias` (0,13 mm, gris,
  discontinua 2/1 mm, nombre de la zona en Helvetica 6 pt).
- `hoja.py`: nueva `crear_pagina(ancho_mm, alto_mm)`; `crear_hoja` la reutiliza.
- `cli.py`: subcomando `hoja-formato --formato --salida [--guias] [--sobrescribir]`,
  imprime tabla de zonas con coordenadas y tamaño en mm.

**Pruebas**: 34 pruebas, todas pasan (`python -m pytest -q`).
- Transformación de rectángulos en las 4 esquinas de la hoja e ida y vuelta.
- Carga de `A1_ERCO.json` y 9 casos de formato inválido (zona fuera del marco, traslape,
  subzona fuera del rótulo, zona faltante, grosor 0, rectángulo mal escrito, etc.).
- PDF generado (con y sin guías): marco leído con `get_drawings()` en
  12,7 / 12,7 / 828,3 / 581,3 mm (±0,1 mm); 6 guías discontinuas y sus nombres solo con
  `--guias`; sin imágenes; 1 página; rotación 0.
- CLI: tabla con tamaños (marco 815,6 × 568,6; área de dibujo 639,7 × 548,6), negativa a
  sobrescribir y JSON inválido.

**Notas**
- El rótulo comparte tres bordes con el marco: con `--guias` la línea discontinua del
  rótulo queda encima del marco. Es solo ayuda visual.

### Subfase 1.3 — Colocar un PDF vectorial en una región conocida ✅ (2026-10-29)

**Qué se hizo**
- `colocar.py`: `colocar_detalle(hoja, formato, origen, posicion_mm=None, pagina=0,
  zona="area_dibujo")` → rectángulo ocupado en mm de papel. `posicion_mm` es la esquina
  inferior izquierda (Y arriba); `None` centra en la zona. Sin escalar (escala 1:N ya
  aplicada por el exportador). Inserta con `show_pdf_page` (Form XObject, vector).
  Usa `rect_papel_a_pdf`; no invierte Y por su cuenta.
  También `tamano_visible_mm` y `posicion_centrada`. Errores `DetalleInvalido` en español:
  no cabe (tamaño del detalle, tamaño de la zona y cuánto se pasa a lo ancho/alto o por
  qué lado), zona o página inexistente, archivo inexistente o que no es PDF.
- `cli.py`: subcomando `colocar --formato --detalle --salida (--posicion X Y | --centrar)
  [--zona] [--guias] [--sobrescribir]`. Imprime tamaño del detalle y rectángulo ocupado.
  Valida todo antes de escribir: si el detalle no cabe, no se crea el archivo.

**CropBox y /Rotate de la página de origen (cómo se resolvió)**
- Manda el tamaño visible (`page.rect`: CropBox girado según /Rotate).
- Hallazgo: en PyMuPDF 1.28.2 `show_pdf_page` ignora el /Rotate del origen (recorta con
  medidas giradas sobre el contenido sin girar) y su parámetro `rotate` reescala;
  `Page.remove_rotation()` pierde el CropBox y desplaza el contenido.
- Solución: copiar la página a un documento temporal en memoria, ponerle /Rotate 0
  (conserva el CropBox) y llamar a `show_pdf_page(..., rotate=-rotación_origen)` con un
  destino del tamaño visible exacto → factor de escala 1. Verificado píxel a píxel contra
  la página de origen en 0/90/180/270 con y sin CropBox desplazado, y en las pruebas por
  geometría (incluida una marca de orientación).

**Pruebas**: 50 pruebas, todas pasan (`python -m pytest -q`).
- PDF sintético (120 x 80 mm, rectángulo 100 x 50, diagonal, texto, marca de orientación)
  creado en `tests/conftest.py`.
- Posición conocida: rectángulo de 100 x 50 mm en su lugar (±0,1 mm) leído con
  `get_drawings()`. Centrado: centro del detalle = centro de la zona.
- Sin imágenes, entra como Form XObject, el texto se encuentra con `get_text`.
- /Rotate 0, 90, 180 y 270: tamaño colocado = visible; rectángulo y marca donde deben.
- CropBox desplazado: tamaño visible y contenido corrido correctamente.
- Detalle más grande que la zona y posición fuera de la zona: mensaje claro; en el CLI,
  código 1 y sin archivo.

**Notas**
- Al leer con `get_drawings()` un rectángulo girado llega como 4 segmentos (`l`) y no
  como `re`; las pruebas lo tienen en cuenta.
- `show_pdf_page` crea dos XObjects anidados (envoltorio `fzFrm0` + la página).

### Subfase 1.3b — Rótulo como plantilla PDF ✅ (2026-10-30)

**Inspección de `plantillas/rotulo_A1_ERCO.pdf`** (solo lectura)
- Tamaño visible 841,022 x 594,078 mm (2384 x 1684 pt, redondeo de AutoCAD):
  diferencia +0,02 x +0,08 mm. **/Rotate 0** (no 270). CropBox = MediaBox.
- 2119 trazos (10 832 segmentos); grosores 0,72 pt (mayoría), 0,84, 0,24, 0,12 y 0 pt.
- 1 imagen: logo ERCO (885 x 273 px) en X 761,0–817,2 / Y 79,4–96,7 mm (cajetín).
- Fuentes BodoniMT y SymbolMT. El texto del rótulo es geometría SHX; texto real solo
  N/S/E/W de la rosa y una viñeta de las notas.
- 83 anotaciones *Square* con el texto SHX como comentario (búsqueda en AutoCAD).
  `show_pdf_page` no copia anotaciones: no pasan al plano final (el aspecto no cambia).
- Medidas leídas (mm, origen inferior izquierdo): marco 12,70/12,70/828,25/581,24;
  área de dibujo 22,69/22,69/662,39/571,25; localización 672,38/424,31/828,25/571,16.
  Coinciden con A1_ERCO.json (≤0,09 mm). El contenido está anclado abajo a la izquierda
  (marco a 12,70 mm del borde inferior y 12,84 del superior): colocar en (0, 0) es correcto.
- **Elementos dentro del área de dibujo** (reportados, no quitados):
  1. Rosa de los vientos: X 612,7–650,4 / Y 53,5–89,3 mm (69 trazos + textos N/S/E/W).
  2. Recuadro "LAYERS AUTORIZADOS ESC: 1:500": X 611,7–659,6 / Y 25,5–34,8 mm
     (41 trazos + 1 anotación).
  3. Borde del área de dibujo duplicado (uno de 0,72 pt y otro de grosor 0, sin relleno).
- Fuera del marco: línea de borde de hoja en [0, 0, 840,95, 593,94] y un texto vertical
  tenue en el margen izquierdo.

**Qué se hizo**
- `A1_ERCO.json`: clave opcional `"plantilla": "../plantillas/rotulo_A1_ERCO.pdf"`
  (relativa a la carpeta del JSON).
- `formato.py`: `Formato.plantilla`; si la clave existe valida texto, extensión .pdf y que
  el archivo exista. `cargar_formato(..., usar_plantilla=False)` la ignora.
- `colocar.py`: la inserción con corrección de /Rotate pasó a `insertar_pagina()` (la usan
  detalles y plantilla); `abrir_pdf()` compartido.
- `plantilla.py`: `colocar_plantilla()` → `InformePlantilla`. Tamaño ±0,5 mm (si no,
  `PlantillaInvalida` con la diferencia); colocación en (0, 0) sin escalar; validación
  cruzada `leer_marco()`: el trazo más parecido al marco del formato debe estar a ±0,5 mm,
  si no, error con la diferencia por lado.
- `cli.py`: `hoja-formato` y `colocar` usan la plantilla si existe (primero la plantilla,
  luego guías, luego detalle) e imprimen tamaño, diferencia y marco leído;
  `--sin-plantilla` la omite. Con plantilla no se dibuja el marco propio de 0,5 mm.
- `.gitignore`: `plantillas/*.pdf`.

**Pruebas**: 65 pruebas, todas pasan. No dependen del rótulo real: plantilla sintética en
`conftest.py` (2384 x 1684 pt, marco, línea del rótulo, logo como imagen; /Rotate 0/90/270).
- Plantilla redondeada aceptada, diferencia reportada, marco coincide (0/90/270).
- Plantilla de otro tamaño y marco corrido: error claro con las diferencias; en el CLI,
  sin archivo.
- PDF final: solo la imagen propia de la plantilla, ninguna adicional; plantilla debajo
  del detalle (orden de dibujo); sin marco propio encima. `--sin-plantilla`: sin imágenes.
- Validación de la clave `plantilla` en el formato (ruta relativa, inexistente, no .pdf).

**Resultado real**: `data/output/prueba_rotulo.pdf` con `perfil_k0010.pdf` centrado:
plantilla 841,02 x 594,08 mm (+0,02 x +0,08), marco leído 12,70/12,70/828,25/581,24 mm
(diferencia máx. 0,06 mm), detalle 417,0 x 119,4 mm en X 134,06–551,04 / Y 237,30–356,70.
Hoja 841 x 594 mm, /Rotate 0, 1 imagen (logo), texto del K0010 buscable.

**Pendientes / a decidir**
- Con Alan: si `plantillas/*.pdf` se versiona.
- Qué hacer con la rosa de los vientos y el recuadro de capas dentro del área de dibujo
  (hoy limitan el espacio útil abajo a la derecha; `colocar` no los tiene en cuenta).

### Subfase 1.4 — Transformaciones CAD → papel → PDF ✅ (2026-10-30)

**Qué se hizo**
- `transformaciones.py`: `punto_pagina_a_papel` / `punto_papel_a_pagina` (página del
  detalle, mm, Y abajo ↔ papel, Y arriba, con origen opcional del detalle en la hoja).
  Sigue siendo el único lugar donde se invierte Y (verificado con grep).
- `cad_a_papel.py`: `MatrizCad` (`cad_a_pagina`, `pagina_a_cad`; `MatrizNoInvertible`
  con mensaje claro), `cad_a_papel(x, y, origen, alto_pagina, matriz)`,
  `origen_para_ancla`, `limites_dibujo_en_papel` y `leer_geometria_manifiesto` (lee SOLO
  `pdf.page_size_mm`, `pdf.drawing.cad_to_page` y `pdf.drawing.page_bounds_mm`; la Fase 2
  la reemplaza por el importador completo). `ManifiestoInvalido` con el campo exacto.
- `comprobacion_dibujo.py`: `medir_limites_trazos` (con `get_drawings()`, ignora el fondo
  blanco de página completa que pone el exportador), `comparar_con_manifiesto`
  (advertencia si > 0,5 mm, no error) y `exigir_coherencia` (error si el PDF tiene
  /Rotate o su tamaño no coincide con `page_size_mm` ±0,5 mm: el ancla quedaría mal).
- `cli.py colocar`: `--manifiesto`, `--ancla-cad X Y`, `--ancla-papel X Y`. Combinaciones
  validadas a mano con mensajes en español (código 2). Con manifiesto imprime el
  rectángulo del dibujo en papel y la comprobación matriz vs PDF. `hoja_con_detalle`
  devuelve `ResultadoColocar`.
- `CLAUDE.md`: 3 líneas sobre `cad_to_page` en Convenciones.
- `data/input/perfil_k0010.manifest.json`: copiado (solo lectura allá) de
  `Exportador Vectorial/data/output/referencia/perfil_k0010/`, cuyo PDF es idéntico
  (mismo SHA-256) a nuestro `perfil_k0010.pdf`.

**Pruebas**: 110 pruebas, todas pasan. Sin datos de ERCO: matriz sintética (escala 20,
e y f ~1e8, márgenes distintos de 5 mm), PDF de 260 x 120 mm con fondo blanco y un
rectángulo de 10 x 4 unidades CAD, manifiesto mínimo sintético.
- Ida y vuelta CAD → página → CAD y página → CAD → página con error < 0,001 mm.
- Rectángulo colocado con ancla: sus esquinas leídas con `get_drawings()` caen donde
  predice `cad_a_papel` (±0,1 mm); el punto del ancla cae exactamente en el pedido.
- Manifiesto con campos faltantes, units/origin/y_axis distintos, matriz de 5 números o
  no numérica, page_size o page_bounds mal formados, JSON roto, archivo inexistente.
- Matriz no invertible; manifiesto de otro PDF; detalle con /Rotate.
- CLI: opciones incompatibles (6 casos), ancla fuera de la zona y manifiesto inválido sin
  crear archivo, advertencia si page_bounds no coincide.

**Resultado real (K0010)**
- Comprobación matriz vs PDF: límites de los trazos = `page_bounds_mm`, diferencia
  0,000 mm. `page_bounds_mm.x0` = 10,43 mm (confirma que no hay margen fijo de 5 mm).
- `--centrar`: dibujo en X 144,49–540,61 / Y 243,04–350,96 mm.
- `--ancla-cad` = `cad_bounds.min` del manifiesto, `--ancla-papel 40 300`: el dibujo
  quedó en X 40,00–436,12 / Y 300,00–407,91 mm; medido en el PDF final: X 40,000–436,118
  / Y 300,000–407,914 (280 trazos del K0010).

**Hallazgos**
- El exportador pinta un **fondo blanco de página completa** debajo del dibujo. En la
  hoja ese fondo tapa lo que haya debajo del rectángulo del detalle (p. ej. la rosa de los
  vientos o líneas del rótulo si el detalle se les encima).

### Subfase 1.5 — Validación con geometría de referencia ✅ (2026-10-30)

**Qué se hizo**
- `referencia.py`: detalle sintético generado en memoria, matriz 1:50 (a = 20, d = −20,
  e y f ~1e8, coordenadas CAD inventadas), fondo blanco, cuadrado 5 x 5 m, rectángulo
  5 x 2 m, diagonal, texto «REFERENCIA 1:50» y marca roja asimétrica (giro/espejo).
  `factor_error` solo para pruebas negativas.
- `validacion.py`: `Comprobacion(seccion, nombre, pasa, esperado, medido, tolerancia)`
  para hoja (1 página, 841 x 594 ±0,1, rotación 0), marco (±0,1 sin plantilla; ±0,5 con
  plantilla usando `buscar_marco`, la misma búsqueda de la validación cruzada), tamaño de
  plantilla, cuadrado y rectángulo (tamaño y esquina ±0,1 frente a `cad_a_papel`),
  escala medida (dif. relativa < 0,0005), orientación, imágenes = las de la plantilla y
  texto real. Detalle real opcional: límites vs `page_bounds_mm` en papel (±0,2) y
  tamaño vs `page_size_mm` (±0,1). Lo esperado se calcula de forma independiente.
- Reutilización: `comprobacion_dibujo.es_fondo_blanco` / `trazos_sin_fondo` (la misma
  lógica del fondo blanco, ahora para cualquier rectángulo); `plantilla.buscar_marco`;
  `composicion.hoja_base` (antes dentro de `cli.py`); `formato.PlantillaNoEncontrada`.
- `informe.py`: TXT UTF-8 (saltos LF) por secciones y «RESULTADO: PASA» o
  «RESULTADO: FALLA (n comprobaciones)».
- `comando_referencia.py` + CLI `referencia --formato --salida [--sin-plantilla]
  [--sobrescribir] [--detalle --manifiesto]`: PDF + TXT, imprime el informe, código 0/1.
  Si falta la plantilla, avisa y sigue sin ella.

**Pruebas**: 129, todas pasan. Ninguna lee archivos de ERCO ni de `data/`.
- Comando completo con plantilla sintética y sin plantilla: todo PASA.
- Negativas: detalle desplazado 1 mm (FALLA: esquina del cuadrado, del rectángulo y
  orientación; el tamaño sigue PASA) y escalado 1 % (FALLA: tamaños, escala 1:49,50…);
  código de salida 1.
- Reproducibilidad: dos corridas dan los mismos valores medidos.
- Detalle real sintético con manifiesto (PASA) y con page_bounds corrido 0,5 mm (FALLA).

**Resultado real**
- Con el rótulo real: todo PASA (marco leído 12,700/12,700/828,252/581,237; plantilla
  841,022 x 594,078 mm; 1 imagen = logo).
- Sin plantilla: todo PASA (marco 12,700/12,700/828,300/581,300).
- Con `--detalle` K0010 y su manifiesto: tamaño 416,980 x 119,403 = page_size_mm y límites
  del dibujo = page_bounds_mm en papel (diferencia 0,000 mm).

## Pendientes (para después de la Fase 1)

- **Fondo blanco del exportador**: cada detalle trae un rectángulo blanco de página
  completa que tapa lo que haya debajo en la hoja (rótulo, rosa, otros detalles si se
  traslapan). Decidir con el exportador si se quita o si el componedor lo omite.
- **Rosa de los vientos y recuadro «LAYERS AUTORIZADOS»** dentro del área de dibujo del
  rótulo: `colocar` no los tiene en cuenta (un detalle puede quedar encima). Decidir si se
  tratan como zonas ocupadas o se quitan del rótulo.
- **Anotaciones SHX perdidas**: las 83 anotaciones con el texto SHX del rótulo no pasan al
  PDF final (`show_pdf_page` no copia anotaciones); el aspecto no cambia, pero ese texto no
  se puede buscar.
- **Versionado de plantillas**: decidir con Alan si `plantillas/*.pdf` entra al repositorio.
- Fase 2: importador completo del manifiesto (hash, versión de esquema, escala, unidades,
  coherencia, inventario de detalles); reemplaza a `leer_geometria_manifiesto`.
