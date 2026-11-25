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

## Fase 2 — Ingesta y validación del extractor ✅ CERRADA (2026-11-02)

Resumen: el componedor lee los paquetes del Exportador Vectorial (PDF + TXT + manifiesto)
por una sola puerta (`importador.importar_paquete`): localiza el paquete, valida la
estructura del manifiesto, verifica la integridad del PDF (bytes, SHA-256, que abra, una
página) y la coherencia de la geometría (página, escala, matriz, cad_bounds, page_bounds,
trazos) con la regla de uso de la escala física. Rechaza con todos los motivos y su
categoría. `inventario` resume una carpeta: aceptados, rechazados, si caben en el área de
dibujo y una escala sugerida. 272 pruebas, todas sintéticas.

Comandos nuevos: `leer-manifiesto`, `paquetes [--verificar]`, `verificar-paquete`,
`inventario` (ver README).

### Subfase 2.1 — Contrato del paquete del exportador ✅ (2026-11-02)

**Inspección del exportador** (solo lectura): el manifiesto lo genera
`src/cde_exporter/cad/manifest.py` (`DOCUMENT_TYPE = "cde-detail-manifest"`,
`SCHEMA_VERSION = "1.0"`; `model_version` "2" sale de `detail_model.py`). Documentación en
su `docs/manifiesto.md`; no hay JSON Schema (el esquema está declarado en Python).
`validation.status`: `complete` | `complete_with_warnings`; severidades `info` | `warning` |
`critical`; estados de entidades `conserved`, `transformed`, `simplified`, `omitted`,
`unsupported`, `not_visible`. Seis campos que el componedor necesita pueden venir en null
según el exportador (unidades, escala, tamaño esperado, margen, `pdf.drawing`).

**Qué se hizo**
- `docs/contrato_paquete.md`: los tres archivos, campos obligatorios (ruta, tipo, regla,
  uso), campos que pueden venir null, opcionales informativos, versiones y qué queda para
  2.3/2.4.
- `manifiesto.py` (solo biblioteca estándar): dataclasses frozen `Manifiesto`, `Unidades`,
  `Escala`, `GeometriaPdf`, `Dibujo` (reutiliza `MatrizCad`); `leer_manifiesto(ruta)` valida
  solo estructura y junta todos los problemas en un `ManifiestoInvalido` (uno por línea, con
  la ruta del campo; «falta el campo» vs «es null (motivo)»; un objeto que falta se informa
  una sola vez). Versión mayor 1; campos desconocidos e informativos se ignoran.
- CLI `leer-manifiesto <ruta>`: resumen (bloque, escala, tamaño, estado) o error; 0/1.
- `cad_a_papel.leer_geometria_manifiesto`: sin cambios, con nota hacia `manifiesto.py`.
- `CLAUDE.md`: línea sobre el contrato. `README.md`: comando nuevo.

**Pruebas**: 204, todas pasan (75 nuevas). Manifiestos sintéticos de
`conftest.manifiesto_paquete` (quitar/cambiar campos, versión mínima), sin datos de ERCO:
completo y mínimo, campos desconocidos, falta de cada uno de los 25 obligatorios, null en
los 6 que el exportador puede dejar null, varios problemas a la vez (5 en un mensaje),
22 casos de tipos y valores (texto, booleano, matriz de 5, NaN, inf, negativos, SHA-256,
nombre con ruta…), versiones 1.x aceptadas y 2.0/0.9/«v1» rechazadas, JSON mal formado,
JSON que no es objeto, archivo inexistente y el CLI.

**Manifiestos reales** (copiados de solo lectura a `data/input`, no se versionan, ninguna
prueba depende de ellos): perfil_k0010 (1:50, 416,98 x 119,40 mm), plano_completo (1:1000,
817,44 x 772,52 mm) y via_ma (1:1000, 2551,01 x 1885,27 mm): los tres con estructura
válida, escala física garantizada y `complete_with_warnings`.

### Subfase 2.2 — Localizar paquetes y emparejar sus archivos ✅ (2026-11-02)

**Qué se hizo**
- Ajuste a 2.1: `pdf.margin_mm` pasa a opcional informativo (`margen_mm` = None si falta,
  es null o no es válido; no se rechaza). Contrato y pruebas actualizados.
- `paquete.py` (solo biblioteca estándar): `Paquete` (prefijo, rutas de manifiesto, PDF y
  TXT, manifiesto, problemas; `estado` completo / incompleto / invalido),
  `localizar_paquetes(carpeta, recursivo)` y `CarpetaInvalida`. Un paquete por manifiesto;
  PDF por `pdf.file_name` en la misma carpeta («indica X pero la carpeta tiene Y»); TXT
  opcional; PDF + TXT sin manifiesto = incompleto; PDF suelto, .dxf, .svg… ignorados;
  manifiesto inválido listado sin detener el recorrido. No abre PDF ni calcula hashes.
- CLI `paquetes <carpeta> [--recursivo]`: tabla, problemas y conteo; 0 si todos completos.
- `docs/contrato_paquete.md`: sección «Cómo se localiza un paquete». README actualizado.

**Pruebas**: 222, todas pasan (18 nuevas, sintéticas en tmp_path, PDF de bytes
ficticios): completo con y sin TXT, manifiesto sin PDF, PDF sin manifiesto, inválido junto
a válido, `file_name` distinto del prefijo, PDF de otro nombre, prefijos `_001/_002/_010`,
extras y PDF suelto ignorados, recursivo/no recursivo, PDF en otra carpeta, carpeta
inexistente/archivo/vacía y CLI (tabla, problemas, códigos). Más 4 de margen opcional.

**Real**: `paquetes data/input` → perfil_k0010, plano_completo y via_ma: 3 completos,
código 0.

### Subfase 2.3 — Integridad del paquete ✅ (2026-11-02)

**Qué se hizo**
- Ajuste a 2.2: `paquetes` agrega al final «PDF sin paquete (ignorados): n — nombres»
  (`paquete.localizar_con_sueltos`); no cambia estados ni código de salida.
- `integridad.py`: `verificar_integridad(paquete)` → `ResultadoIntegridad` (OK / FALLA /
  «no verificable (paquete …)»), reutilizando `validacion.Comprobacion` (nuevo campo
  opcional `detalle`). Orden: existe → bytes → SHA-256 (por bloques de 1 MB,
  `sha256_archivo`) → abre sin daños ni cifrado → 1 página (PDF y manifiesto). Se detiene
  solo si seguir es imposible. Mensajes distinguen tamaño distinto («modificado o
  incompleto») de mismo tamaño con otro hash («el contenido cambió después de
  exportarse»). No compara página, escala ni matriz (2.4).
- CLI `paquetes --verificar`: columna «Integridad», «Problemas de integridad» y código 1 si
  alguno falla.
- Hallazgo: un PDF con un byte cambiado abre normalmente en PyMuPDF; solo el SHA-256 lo
  detecta. Un PDF recortado abre «reparado» (se informa como dañado). Los tres PDF reales
  abren sin reparar ni cifrado.

**Pruebas**: 239, todas pasan (17 nuevas). `conftest.crear_paquete_real` escribe PDF y
manifiesto con bytes y SHA-256 reales: íntegro; un byte cambiado (falla el hash, el
tamaño pasa); recortado (falla el tamaño); no es PDF con hash correcto (no abre, no se
cuentan páginas); 2 páginas con manifiesto de 1 y de 2; PDF que desaparece; incompleto e
inválido no verificables; hash de 5 MB por bloques (espía de lecturas ≤ 1 MB); CLI con y sin
`--verificar`; PDF sueltos.

**Real**: `paquetes data/input --verificar` → 3 paquetes OK, código 0. Prueba a mano: copia
de perfil_k0010 en una carpeta temporal con un byte cambiado (mismo tamaño) → FALLA
«SHA-256: el contenido del PDF cambió después de exportarse», código 1; original intacto.

### Subfase 2.4 — Coherencia del paquete y lector único del manifiesto ✅ (2026-11-02)

**Qué se hizo**
- `coherencia.py`: `verificar_coherencia(paquete, integridad=None)` y
  `verificar_paquete(paquete)` → (integridad, coherencia). Solo paquetes completos con
  integridad OK; si no, «no verificable (…)». Comprobaciones a–i: rotación 0 (si no, se
  detiene), tamaño visible = page_size (±0,1), page_size = expected (±0,1), factor = mm por
  unidad / N (rel. < 1e-6), matriz a = factor, d = −factor, b = c = 0 («giro o inclinación:
  todavía no soportada»), cad_bounds por la matriz = page_bounds (±0,01, 4 esquinas),
  page_bounds dentro de la página, trazos = page_bounds (±0,5, sin fondo blanco) y regla de
  uso `physical_scale_guaranteed` = true (cita `physical_scale_reason`).
- Lector único: borrados `cad_a_papel.leer_geometria_manifiesto`, `GeometriaManifiesto`, el
  `ManifiestoInvalido` antiguo y, en `comprobacion_dibujo.py`, `exigir_coherencia`,
  `comparar_con_manifiesto` y `ComparacionLimites` (los reemplazan a, b y h).
  `limites_dibujo_en_papel(limites, alto, origen)`. `validar_detalle_real` usa
  `leer_manifiesto`. `ResultadoVerificacion` común (validacion.py) para integridad y
  coherencia; `manifiesto.Escala.motivo_no_garantizada` (opcional).
- `colocar --manifiesto`: `paquete.paquete_de_manifiesto` + exige completo, `--detalle` =
  PDF del manifiesto, integridad OK y coherencia OK; si no, no coloca y lista problemas
  (antes, una diferencia de trazos era solo advertencia). Ancla y rectángulo del dibujo
  igual que antes.
- CLI: `paquetes --verificar` con columna «Coherencia»; nuevo `verificar-paquete`.

**Pruebas**: 247, todas pasan. `conftest.crear_paquete_real` arma paquetes coherentes
(dibujo = matriz del manifiesto) con opciones (rotación, otro tamaño de página, dibujo
desplazado). Un caso por cada comprobación a–i que falla solo esa, matriz con giro,
escala no garantizada con y sin motivo, no verificables, `colocar --manifiesto` (incoherente,
integridad fallida, escala no garantizada, `--detalle` distinto, incompleto, inválido,
archivo que no es manifiesto) y la salida/código de `paquetes --verificar` y
`verificar-paquete`. Las pruebas del lector antiguo se quitaron: sus casos ya están en
`test_manifiesto.py` y `test_coherencia.py`.

**Real** (`paquetes data/input --verificar`: 3 OK / 3 OK, código 0):

| Paquete | a | b | c | d | h: dif. máx. | Tiempo (integridad + coherencia) |
|---|---|---|---|---|---|---|
| perfil_k0010 | 20.000000000000004 | 0 | 0 | −20.000000000000004 | 0,000005 mm | 0,09 s |
| plano_completo | 1.0 | 0 | 0 | −1.0 | 0,000039 mm | 1,03 s |
| via_ma | 1.0 | 0 | 0 | −1.0 | 0,000052 mm | 1,10 s |

El tiempo es casi todo `get_drawings()` (comprobación h); el SHA-256 tarda ~0,01 s.

### Subfase 2.5 — Importador e inventario ✅ (2026-11-02)

**Qué se hizo**
- Ajuste a 2.4: en la comprobación e, b y c cuentan como cero si
  |valor| <= 1e-9 · |factor| (pruebas con b = 1e-16, pasa; y b = 0,01, «giro o inclinación»).
- `importador.py`: `importar_paquete(ruta_manifiesto, pdf_esperado=None)` →
  `PaqueteAceptado` (paquete, integridad, coherencia); única puerta de entrada. Si no,
  `PaqueteRechazado` con todos los motivos «[categoría] texto» ([manifiesto], [archivos],
  [integridad], [coherencia], [escala]) y el nombre del paquete. `evaluar_paquete` hace lo
  mismo sin lanzar error (lo usa el inventario). `paquete.Paquete` separa
  `problemas_manifiesto` y `problemas_archivos` (`problemas` sigue existiendo).
- `colocar --manifiesto` usa `importar_paquete`; se borraron `paquete_utilizable` y
  `PaqueteNoUtilizable` del CLI.
- `inventario.py`: `construir_inventario(carpeta, formato, zona, recursivo)` →
  `EntradaInventario` (prefijo, carpeta, bloque, escala, página, dibujo, estado, motivos,
  cabe, notas). «Cabe» con la misma regla que `colocar` (`colocar.exceso_de_tamano`, nueva);
  no caber es nota, no rechazo; escala sugerida aproximada de la lista estándar (con
  `pdf.margin_mm`); «duplicado de …» por SHA-256.
- CLI `inventario <carpeta> [--recursivo] [--formato] [--zona]`: tabla, motivos, notas y
  resumen; código 1 solo si hay rechazados.

**Pruebas**: 272, todas pasan (25 nuevas). Un rechazo por categoría, PDF indicado que no
es el del paquete, manifiesto inexistente, varios motivos en un mensaje (3 motivos;
manifiesto + archivos), aceptado; inventario con aceptado/rechazado (mismos motivos que el
importador), cabe, no cabe con margen (sugiere 1:100), sin margen (sin sugerencia), ni con
1:10000, zona inexistente, duplicado, recursivo, CLI sin formato (sin «Cabe»), no caber con
código 0, rechazados con código 1, carpeta vacía y otra zona.

**Real**
- `inventario data/input --formato formatos/A1_ERCO.json`: 3 aceptados; perfil_k0010 cabe;
  plano_completo no cabe (sugerida 1:1500, ≈ 548,3 x 518,3 mm) y via_ma no cabe (sugerida
  1:5000, ≈ 518,2 x 385,1 mm). Código 0.
- Inventario recursivo (solo lectura) de `Exportador Vectorial/data/output/referencia`:
  5 aceptados (3 copias de perfil_k0010 en carpetas distintas, plano_completo, via_ma), 2 no
  caben. Las 3 copias de perfil_k0010 NO salen como duplicadas: sus PDF tienen SHA-256
  distintos (el exportador escribe un `/ID` aleatorio en cada extracción).

## Fase 3 — Planos con varios detalles ✅ COMPLETA (rama `fase-3`, 2026-11-05)

Resumen: `componer` arma un plano con varios detalles desde un `plano.json`, revalidándolo
todo y verificando la geometría; los elementos fijos del rótulo se advierten; y `editor`
genera un editor visual de un solo archivo para armar el plano arrastrando detalles.

### Subfase 3.1 — Comando `componer` y formato plano.json ✅ (2026-11-05)

**Qué se hizo**
- `plano.py`: `leer_plano(ruta)` → `Plano` / `DetallePlano` (frozen); `PlanoInvalido` junta
  todos los problemas con la ruta del campo. Versión 1; rutas relativas a la carpeta del
  plano.json; cada detalle con `posicion_mm` o `centrar: true` (uno solo); `id` único (se
  detecta aunque el detalle tenga otros errores); campos desconocidos rechazados.
- `componer.py`: `componer_plano(plano, salida, sobrescribir, guias)`. Formato y plantilla
  (la del plano o la del formato); cada detalle por `importar_paquete` (un mismo manifiesto
  se importa una vez; si hay rechazados, se listan todos y no se genera nada); la página
  de cada detalle dentro de `area_dibujo` con la regla estricta de `colocar` (error con
  `id`, mm que se pasa y zona invadida); traslapes de páginas (advertencia) y de dibujos
  (ADVERTENCIA FUERTE, con la nota del fondo blanco); hoja base + `insertar_pagina` en orden;
  PDF temporal verificado (dibujo de cada detalle ±0,1 mm, marco del rótulo, sin imágenes
  nuevas) y renombrado; el temporal se borra ante cualquier falla. Si el conteo de trazos
  (hoja base + trazos de cada detalle) no cuadra, error explícito: no se verifica a ciegas.
- `colocar.motivo_fuera_de_zona` (separado de `_exigir_que_quepa`, misma regla) y
  `comprobacion_dibujo.limites_de_trazos` (separado de `medir_limites_trazos`).
- CLI `componer PLANO --salida PDF [--sobrescribir] [--guias]`: resumen con la posición
  final de cada detalle, advertencias y ruta del PDF.
- `docs/formato_plano.md`; README actualizado.

**Pruebas**: 316, todas pasan (44 nuevas, sintéticas). plano.json: válido, rutas relativas,
plantilla opcional, 14 casos de detalles inválidos (id repetido, sin posición ni centrar,
ambos, campo desconocido…), raíz inválida (versión 2, versión texto…), varios problemas a
la vez, JSON mal formado. componer: dos detalles con geometría medida, centrar, mismo
paquete dos veces, guías, fuera del área (con mm), encima del rótulo, más grande que el
área, rechazados entre varios, traslape de páginas y de dibujos (advertencias), salida
existente con y sin `--sobrescribir`, plantilla del plano, conteo de trazos que no cuadra,
detalle corrido detectado por la verificación (sin dejar temporales), CLI desde otra
carpeta y errores del CLI.

**Real**: `data/planos/prueba_dos_k0010.json` (no se versiona) con perfil_k0010 dos veces,
en (30, 440) y (237, 40) mm → `data/output/prueba_dos_k0010.pdf`: sin advertencias,
verificado, 1 imagen (logo), 2681 trazos = 2119 del rótulo + 2 × 281. Ojo: el de abajo a la
derecha (página hasta X 653,98, Y 40–159,4) tapa la rosa de los vientos con su fondo blanco.

### Subfase 3.2 — Elementos de la plantilla y datos del editor ✅ (2026-11-05)

**Qué se hizo**
- `formato.py`: clave opcional `elementos_plantilla` → `Formato.elementos_plantilla`
  (`ElementoPlantilla(nombre, rect)`); valida lista de objetos con exactamente `nombre`
  (texto único) y `rect_mm` (x0 < x1, y0 < y1, dentro de la hoja).
- `elementos_plantilla.py`: `detectar_elementos(formato)` mide trazos, textos e imágenes de
  la plantilla (colocada como en `componer`) dentro de `area_dibujo`, sin su propio borde,
  y los agrupa por cercanía (3 mm); `pdf_verificacion` los dibuja en rojo con sus
  coordenadas. CLI `detectar-elementos --formato --salida [--sobrescribir]`.
- `componer`: ADVERTENCIA FUERTE si la página de un detalle tapa un elemento; ADVERTENCIA
  MUY FUERTE si su dibujo se monta encima. No es error.
- `inventario.EntradaInventario`: + `ruta_manifiesto` y `limites_pagina_mm`.
- `datos_editor.py`: `construir_datos_editor` y `preparar_editor` (editor_datos.json,
  plantilla.png de 1600 px, miniaturas de 600 px; máximos configurables por parámetro).
  Solo `area_dibujo` editable; detalles aceptados con `limites_dibujo_mm` relativos a la
  esquina inferior izquierda de su página (Y arriba, vía `limites_dibujo_en_papel`);
  rechazados con motivos. CLI `preparar-editor CARPETA --formato --salida [--sobrescribir]`.
- `docs/formato_editor_datos.md`; README.

**Medición real** (`detectar-elementos`, PDF `data/output/elementos_plantilla.pdf`):
1. X 612,56–651,52, Y 51,55–90,50 mm (69 trazos + textos N, S, E W): rosa de los vientos.
2. X 611,67–659,60, Y 25,48–34,84 mm (41 trazos): recuadro «LAYERS AUTORIZADOS».
Confirmados a ojo con el PDF y copiados a `A1_ERCO.json` como `rosa_vientos` y
`recuadro_capas` (exactos, sin holgura). `conftest.escribir_formato` los quita (son del
rótulo real; las pruebas usan plantilla sintética y pasan sus propios elementos).

**Pruebas**: 344, todas pasan (28 nuevas): valores confirmados de A1_ERCO.json, elementos en el formato (lectura y 8 casos
inválidos), detección en plantilla sintética (exacto, agrupado, sin elementos, sin
plantilla), PDF de verificación, CLI `detectar-elementos`, advertencias de `componer`
(lejos, dibujo encima, solo la página, dos elementos, CLI), datos del editor (hoja, zonas,
solo `area_dibujo` editable, detalles, rechazados, coordenadas del dibujo iguales a las de
`componer`, PNG y tamaños, tamaño configurable, carpeta existente, CLI).

**Real**
- `preparar-editor data/input` → `data/editor/`: 3 aceptados, 1 cabe, 2 elementos fijos.
- `componer data/planos/prueba_dos_k0010.json` → «ADVERTENCIA MUY FUERTE: el dibujo
  'k0010_abajo_der' se monta sobre 'rosa_vientos' de la plantilla (31.0 x 39.0 mm)»; el
  PDF se genera igual (advertencia, no error) y la verificación pasa.

### Subfase 3.3 — Editor HTML de planos ✅ (2026-11-05)

**Qué se hizo**
- `advertencias.py`: plantillas de texto de las 4 advertencias de traslape en un solo lugar;
  `componer` las usa (mismos mensajes exactos; las 344 pruebas siguieron pasando) y se
  incrustan en el editor.
- Recursos del editor en `src/componedor/editor/` (declarados en `pyproject.toml`):
  `editor.html`, `editor.css`, `editor_logica.js` (funciones PURAS, también para Node:
  `papelAPantalla`/`pantallaAPapel` —única inversión de Y, escala X e Y por separado—,
  `clampAZona`, `posicionCentrada`, `redondearDentro`, `interseccion`, `advertencias`,
  `idUnico`, `serializarPlano`, `leerPlano`) y `editor_ui.js` (SVG + DOM, sin librerías).
- `editor_html.py`: `generar_editor` reutiliza `preparar_editor` y escribe `editor.html` con
  todo incrustado (CSS, JS, datos, imágenes en base64, plantillas de advertencias, carpeta del
  editor solo informativa). CLI `editor CARPETA --formato --salida [--sobrescribir]`.
- Editor: hoja completa de fondo, zonas no editables rayadas y bloqueadas (solo de `zonas`),
  elementos fijos en naranja, catálogo (aceptados, no caben con escala sugerida, rechazados con
  motivos), agregar varias veces (ids únicos; la copia se corre 10 mm), arrastre con límite
  estricto al área de dibujo, paso 0,1/1/5/10 mm, X/Y editables (muestran lo que se guardará),
  Centrar / Traer al frente / Enviar atrás / Quitar, flechas (Shift ×10), Supr, zoom con rueda
  y botones, desplazamiento, posición del cursor en mm, advertencias en vivo (mismo texto y
  niveles que componer), Guardar (`showSaveFilePicker`; si falla, descarga; la cancelación se
  ignora; LF; redondeo a 0,01 mm hacia dentro del área), comando de componer para copiar,
  Abrir plano.json (versión, catálogo, `centrar`, ajuste al área con aviso), aviso de cambios
  sin guardar.
- `docs/editor.md`; README.

**Pruebas**: 366, todas pasan (22 nuevas). Python: un solo HTML, sin URLs http(s) ni recursos
externos, marcadores reemplazados, datos incrustados válidos (solo `area_dibujo` editable,
imágenes PNG en base64, plantillas iguales a las de componer), carpeta existente con y sin
`--sobrescribir`, CLI. JavaScript con Node (17, ninguna saltada): inversión de Y y escalas,
clamp (6 casos, aceptados por la regla de componer), no cabe, centrado idéntico a Python,
redondeo hacia dentro en los bordes, paso e ids, advertencias idénticas a las de componer
(4 tipos, mismo orden y texto), plano escrito por JS que `leer_plano` + `componer_plano`
aceptan, `leerPlano` (versión, catálogo, rechazado, repetido, fuera del área, JSON roto).

**Verificación en Edge real** (script `data/verificacion_editor/verificar_editor.mjs`, fuera
del repositorio; maneja Edge sin ventana por su protocolo de depuración desde Node): abrir
desde file://, agregar dos K0010, arrastrarlos con eventos reales de mouse (quedan limitados a
las esquinas del área y aparecen las advertencias muy fuertes por la rosa y el recuadro), X/Y
escritos, flechas, Guardar con cancelación (nada) y con falla de permisos (descarga),
plano.json con LF; ningún error de JavaScript. `componer` con ese plano: aceptado, sin
advertencias, verificado.

### Subfase 3.4 — El editor muestra el resultado real (paquetes sin fondo) ✅ (2026-11-05)

**Qué se hizo**
- `comprobacion_dibujo.tiene_fondo_de_pagina` (misma regla que ignora el fondo al medir).
  `componer` la usa por paquete (`DetalleColocado.tiene_fondo`) y `preparar-editor` por
  detalle aceptado (`tiene_fondo` en editor_datos.json, campo aditivo).
- Miniaturas: transparentes si el detalle no tiene fondo, opacas si lo tiene; lado mayor
  1400 px (antes 600). Peso de editor.html: data/input 1,03 MB, data/input_reales 1,10 MB,
  data/input_sinfondo 0,22 MB.
- Advertencias (`advertencias.py`, fuente única): dos textos nuevos sin mencionar el fondo
  (`dibujos_sin_fondo`, `dibujo_sobre_elemento_sin_fondo`) y la tabla de decisión
  `clave_traslape_detalles` / `clave_sobre_elemento` (lo que tapa es el de ENCIMA; sin fondo,
  un traslape solo de páginas o una página sobre un elemento no avisan). El JS aplica la
  misma tabla. Con fondo, todo igual que antes.
- Editor: **Vista limpia** (botón interruptor y tecla V sostenida; el arrastre sigue
  activo), **Alt + clic** para seleccionar el detalle de debajo (en ciclo); clic normal = el
  de encima; la lista «En el plano» selecciona cualquiera.
- docs: editor.md, formato_editor_datos.md, README.

**Pruebas**: 391, todas pasan (25 nuevas). Detección de fondo; miniatura transparente vs
opaca (canal alfa y píxel de la esquina); `tiene_fondo` en editor_datos.json; textos nuevos
y tablas de decisión; componer con paquetes con y sin fondo (páginas sin fondo no avisan,
solo tapa el de encima, dibujos y rosa sin fondo, con fondo igual que antes); paridad
Python↔JS con un plano mixto que produce los SEIS tipos y 5 casos puntuales. Pruebas
existentes ajustadas: solo `test_datos_editor.test_preparar_escribe_json_y_png` (tamaño de
miniatura 600 → 1400 px) y `test_editor_js.test_advertencias_iguales_que_componer` (ahora
con paquetes con y sin fondo y los seis tipos).

**Verificación en Edge** (`data/verificacion_editor/verificar_sinfondo.mjs`, fuera del
repo, con data/input_sinfondo): 18 comprobaciones OK, sin errores de JavaScript: dos K0010
sin fondo traslapados se ven uno a través del otro; clic en el traslape = el de encima;
Alt+clic = el de abajo (y en ciclo); lista y flechas para el de abajo; vista limpia oculta
las ayudas y deja las miniaturas; arrastre en vista limpia; tecla V momentánea; componer da
las mismas advertencias que el editor.

**Pendiente (después de la Fase 3)**: deshacer en el editor; el catálogo es el de la carpeta
con que se generó; los paquetes antiguos con fondo siguen tapando lo que queda debajo
(reexportarlos con el exportador nuevo lo resuelve).

## Fase 4 — Rótulo con datos (rama `fase-4`, en curso)

### Subfase 4.1 — Rótulo en blanco v2, campos de texto y rosa movible ✅ (2026-11-06, commit 067cad0)

**Qué se hizo**
- **Plantilla v2**: `A1_ERCO.json` apunta a `plantillas/rotulo_A1_ERCO_v2.pdf` (reemplaza a
  la v1; marco, área de dibujo y columna del rótulo no cambian). `elementos_plantilla`: solo
  la rosa, medida con `detectar-elementos` y confirmada a ojo: X 615,94 a 654,92, Y 25,21 a
  64,21 mm. El recuadro «LAYERS AUTORIZADOS» ya no existe en la v2.
- **Sección `"rotulo"` del formato** (`rotulo_formato.py`, esquema versión 1): fuente
  (Arial, ruta configurable), relleno 0,6 mm, interlineado 1,6, y los campos medidos del
  rótulo v2: `texto` (celda, alineación, altura de mayúsculas, altura mínima, líneas, valor
  por defecto o calculado) y `tabla` (filas y columnas en mm; revisiones con
  `columna_clave: "ver"` y orden A < B < C < 0 —corregido después, ver «Corrección de REV.»
  en la subfase 4.3a—; firmas por fila). Se valida: campos
  desconocidos, tipos, celdas dentro de la zona `rotulo`, sin traslapes, alto suficiente,
  calculados conocidos. Todos los problemas en un solo error.
- **plano.json versión 2** (`plano.py`): `rotulo` (objeto; su contenido lo valida
  `componer` contra el formato), `rosa_vientos` (`visible`, `posicion_mm`) y
  `etiqueta_escala` por detalle. La versión 1 sigue válida (sin esas claves).
- **Texto**: `fuente.py` (altura de mayúsculas leída de la tabla OS/2: Arial 1467/2048 =
  0,716; caracteres que la fuente no tiene = error), `maquetacion.py` (alineación, bloque
  centrado en alto, corte por palabras, líneas explícitas, reducción de 0,1 en 0,1 mm hasta
  la mínima con advertencia, error claro con campo, texto y medidas), `textos_pdf.py`
  (escribe con `insert_text` y Arial embebida completa; reemplaza la tabla ToUnicode de esa
  fuente para que «-» y el espacio se lean y busquen bien —Arial comparte glifo con el guion
  blando y el espacio no separable—; verificación por carácter, ±0,1 mm),
  `texto_escala.py` («1:1.000», punto de miles siempre).
- **Rótulo** (`rotulo.py`): valores del plano, `localizacion_escala` = DEFINIR por defecto,
  ESCALA calculada (común o INDICADAS), REV. = la letra de mayor orden llena (vacía si no hay
  revisiones), cada revisión en la fila de SU letra (repetidas = error; la letra se imprime
  en VER solo en filas llenas), DISEÑADOR / REVISOR a izquierda y derecha del logo, FIRMA
  como texto opcional.
- **Etiqueta «ESC: 1:N»** por detalle (`etiquetas_escala.py`): 2,5 mm, centrada 3 mm bajo
  el dibujo; si no cabe, encima; nunca sobre otro dibujo, la rosa ni otra etiqueta; si no
  cabe, advertencia. `"etiqueta_escala": false` la quita.
- **Rosa movible** (`rosa.py`, `composicion.hoja_base_con_rosa`): `componer` siempre la
  quita (redacción solo en su rectángulo + 2 mm, trazos completamente contenidos y texto;
  se comprueba que el resto de la plantilla quedó idéntico) y, si es visible, la vuelve a
  dibujar como vectores (`show_pdf_page` con `clip`, desde una copia de la plantilla con
  todo lo demás borrado). Debe quedar dentro de `area_dibujo` (error claro). Advertencias con
  la posición nueva; oculta no avisa. Con la plantilla real, en su sitio: 536 trazos, misma
  geometría que la plantilla sin tocar (diferencia 0,000 mm) y las mismas letras N S E W.
- **Editor**: `plantilla.png` sin la rosa y `rosa.png` transparente aparte (`rosa_vientos`
  en editor_datos.json, aditivo). La rosa se arrastra (paso de ajuste, flechas, X/Y), casilla
  «Mostrar rosa de los vientos», botón «Restaurar posición»; oculta desaparece y no avisa.
  Guarda plano.json v2 con `rosa_vientos`; abre v1 y v2 y conserva `rotulo` y
  `etiqueta_escala` tal cual. Advertencias con `elementosVisibles` (igual que
  `rosa.elementos_visibles`).
- `cli componer`: el resumen informa la rosa, ESCALA, REV. y las etiquetas.
- **Textos dentro de su celda en el PDF guardado** (agregado tras la revisión, 2026-11-09):
  `textos_pdf.verificar_textos` hace, además de la comprobación de posición, una segunda:
  la unión de los bboxes de los caracteres de cada línea (`get_text("rawdict")`) debe
  quedar dentro del rectángulo de su celda (`TextoMaquetado.celda_mm`), ±0,1 mm; si no,
  error con campo, texto y mm que se sale por cada lado, y no queda PDF. Las etiquetas ESC
  usan como celda su caja reservada, que ahora incluye el ascenso y el descenso de la fuente
  (`Fuente.caja_vertical_mm`); con esa misma caja se revisan sus choques con otros dibujos,
  la rosa y otras etiquetas. En el ejemplo real (52 líneas) la holgura mínima en las
  celdas del rótulo es 0,51 mm (ESCALA, en alto).
- docs: formato_plano.md (v2, rótulo, rosa, etiquetas), editor.md, formato_editor_datos.md,
  README.

**Pruebas**: 514, todas pasan (123 nuevas; 6 de ellas por la comprobación de celda: lados
que se salen, caja vertical de la fuente, textos dentro de su celda que pasan, un texto
forzado 0,3 mm fuera de su celda que falla, `componer` sin PDF en ese caso, y la caja de la
etiqueta ESC): fuente (OS/2, medidas, errores), escalas,
maquetación (alineación, centrado, cortes, reducción, los tres tipos de error), esquema del
rótulo (A1 ERCO, 21 casos inválidos, celdas fuera o traslapadas), llenado del rótulo (defectos, calculados, revisiones
por letra, todos los problemas juntos), etiquetas (debajo, encima, obstáculos, opción),
textos en el PDF (búsqueda con guion y tildes, una sola fuente embebida, altura real de las
mayúsculas 5,0 ± 0,05 mm, verificación de un texto corrido), rosa (en su sitio = plantilla
sin tocar ±0,1 mm, movida, oculta, «resto idéntico», verificación de una rosa corrida, copia
vectorial), componer con rótulo y rosa (completo, v1 con defectos, texto que no cabe sin
PDF, etiqueta que no cabe, rosa movida / oculta / fuera del área / sin rosa en el formato,
resumen del CLI), plano.json v2, editor JS (v2 de ida y vuelta con componer, paridad de
advertencias con la rosa movida y oculta) y datos del editor (rosa.png, plantilla sin rosa).
Pruebas existentes ajustadas: la plantilla v2 y los elementos confirmados
(`test_formato`, `test_elementos_plantilla`), versión no soportada 2 → 3 (`test_plano`,
`test_editor_js.test_leer_plano`) y `rosa.png` en la carpeta del editor (`test_editor_html`).

**Verificación en Edge** (`data/verificacion_editor/verificar_rosa.mjs`, fuera del repo, con
data/input_sinfondo y el formato real): 26 comprobaciones OK, sin errores de JavaScript:
rosa en su lugar al abrir, arrastre con paso de 1 mm y tope en el área, X/Y y flechas,
advertencia sobre la rosa movida y ninguna sobre su sitio viejo, ocultar (desaparece, sin
advertencias), guardar v2 y componer con las mismas advertencias, restaurar posición,
abrir un plano con rótulo y conservarlo, vista limpia. El PDF compuesto coincide con lo que
muestra el editor.

**Ejemplos** (datos de prueba, en `data/`, no se versionan): `data/planos/ejemplo_rotulo_v2.json`
→ `data/output/ejemplo_rotulo_v2.pdf` (todos los campos llenos, título de 3 líneas, dos
detalles a 1:5.000 y 1:50 → ESCALA «INDICADAS», REV. «B», rosa movida);
`data/planos/ejemplo_rotulo_v2_no_cabe.json` (No. PLANO demasiado largo → error claro, sin
PDF).

**Pendiente**
- **«Dirigido a»**: la plantilla v2 trae en el margen izquierdo la anotación «ESTE DOCUMENTO
  ES PROPIEDAD DE ERCO ENERGY DIRIGDO A XXXX» sin trazos (solo anotación, que no pasa al
  PDF). No se agrega por ahora; **consultar con Alan** si debe ser un campo del rótulo.
- Subfase 4.2: notas y símbolos de convenciones (4.2a hecha, ver abajo; 4.2b pendiente).
- El editor no muestra ni edita los textos del rótulo ni las etiquetas «ESC: 1:N».
- La fuente va embebida completa (~0,5 MB por plano): no se usa `subset_fonts` porque
  reduciría también las fuentes de los detalles y de la plantilla.
- La ruta de Arial es la de Windows (`C:/Windows/Fonts/arial.ttf`); en otro equipo se
  cambia en el formato.

### Subfase 4.2a — Notas del rótulo y HOJA / DE alineados ✅ (2026-11-09, commit 64c27f0)

**Qué se hizo**
- **Esquema** (`rotulo_formato.py`, cambio aditivo, la sección sigue en versión 1): tipo de
  campo nuevo `"notas"` (`rect_mm`, `altura_mm`, `altura_min_mm`, `separacion_notas` en
  renglones). En `A1_ERCO.json`: `notas` en X 673,2–827,4, Y 271,3–419,3, 1,8 mm (mín.
  1,5), medio renglón entre notas.
- **Notas** (`notas.py`): lectura de .txt UTF-8 (con o sin BOM), una nota por línea, sin
  líneas en blanco ni comentarios `#`; número propio («3.» o «3)») quitado con advertencia;
  numeración automática continua (archivos primero, adicionales después); sangría francesa
  según el número más largo; medio renglón entre notas; bloque pegado arriba; reducción
  conjunta de 0,1 en 0,1 mm hasta 1,5 con advertencia; si no caben, error con el campo, el
  tamaño y desde qué nota (y su origen), sin PDF. `verificar_notas`: líneas leídas en la celda
  = escritas y numeración 1…N sin saltos (además de posición y celda de cada línea).
- **plano.json v2**: `"rotulo": {"notas": {"archivos": [...], "adicionales": [...]}}`; rutas
  relativas a la carpeta del plano (`preparar_rotulo` recibe la carpeta). Todos los problemas
  juntos (archivo inexistente, no UTF-8, sin notas, caracteres que la fuente no tiene, tipos,
  campos desconocidos).
- **Etiqueta «NOTAS» de la plantilla**: medida en X 746,3–754,9, Y 420,96–422,99. La celda
  termina en 419,3 (1,66 mm debajo); en el ejemplo, la caja de la primera línea llega a
  419,17: **1,79 mm libres** hasta la etiqueta.
- **HOJA / DE**: DE pasa a X 812,9–827,4 (igual que HOJA), ambos centrados. En el ejemplo los
  dos valores tienen centro en X 820,15 mm (antes 1,75 mm de diferencia).
- `maquetacion.partir_en_lineas` y `alturas_a_probar` (antes privadas) y
  `textos_pdf.leer_linea` / `caracteres_de_pagina` se reutilizan en las notas; `cli
  componer` informa «Notas: N nota(s) en L línea(s), a H mm».
- docs: formato_plano.md (sección Notas, HOJA/DE, verificación).

**Pruebas**: 538, todas pasan (24 nuevas): lectura (blancos, comentarios, número propio con y
sin espacio, BOM y CRLF, inexistente, no UTF-8, vacío, orden archivos/adicionales, problemas
juntos), maquetación (número y sangría francesa, bloque arriba, interlineado y medio renglón,
sangría con «12.», reducción conjunta, error desde qué nota, palabra demasiado ancha, sin
notas), rótulo con notas (numeración y todos los problemas juntos), verificación en el PDF
(pasa; falla con una línea de más y con numeración con salto), esquema (A1 ERCO, campos
inválidos, traslape), HOJA y DE con el mismo centro en el formato y en el PDF, y `componer`
(txt + adicionales en el PDF y en el resumen, reducción con advertencia, error sin PDF).
Pruebas existentes ajustadas: `test_rotulo_formato` (campo `notas` en el conjunto, cantidad
de celdas, mensaje de tipo con «notas»).

**Ejemplo** (`data/`, no se versiona): `data/notas/generales_vias.txt` (7 notas) y
`data/notas/drenaje.txt` (3), ficticios, más 2 adicionales en
`data/planos/ejemplo_rotulo_v2.json` → `data/output/ejemplo_rotulo_v2.pdf`: 12 notas en 17
líneas a 1,8 mm, sin advertencias.

**Pendiente**: 4.2b, convenciones (símbolos). El editor todavía no edita las notas.

### Subfase 4.2b — Convenciones (biblioteca de símbolos vectoriales) ✅ (2026-11-09, commit 955cf08)

**Qué se hizo**
- **Esquema** (`rotulo_formato.py`, aditivo): tipo `"convenciones"` con la rejilla
  (`filas_y_mm`: 13 líneas, 12 filas; `columnas_x_mm`: símbolo / descripción / símbolo /
  descripción), alturas de la descripción (1,8 mm, mín. 1,5, hasta 2 líneas) y la ruta de la
  biblioteca. En `A1_ERCO.json`, medida en la plantilla v2: filas 259,88 … 137,71, columnas
  672,4 / 693,84 / 750,32 / 771,82 / 828,2. Llenado por columna (1–12 izquierda, 13–24
  derecha). Las 48 casillas entran en la revisión de «dentro del rótulo / sin traslapes».
- **Biblioteca** (`simbolos.py`, comando `extraer-simbolos <plano.pdf>`): normaliza la página
  (quita /Rotate), mide cada casilla de símbolo (trazos completamente dentro, ±0,3 mm), aísla
  cada símbolo con redacciones (primero la columna, luego el símbolo) y lo copia como vector
  a una página propia (caja + 0,5 mm); verifica trazos y caja (±0,1 mm) y escribe el índice
  (conserva ids y descripciones). Hallazgo: MuPDF decide si un trazo «toca» la redacción con
  su caja ensanchada, y con 0,5 mm borraba círculos pequeños de un símbolo de prueba; por eso
  el margen de redacción es adaptativo (0,5 / 1 / 2 / 3 mm) y solo se acepta el que deja
  exactamente los trazos medidos (si un margen grande metiera trazos vecinos, no cuadra).
- **Biblioteca real**: `simbolos/convenciones_erco.pdf` (51,2 KB, 12 páginas, se generó en
  ~80 s desde PRGE-25-0044-CIV-PL-101_A, página 1, /Rotate 270, ~262.000 trazos) y
  `simbolos/indice.json` con los ids y descripciones acordados. `simbolos/*.pdf` está en
  `.gitignore`; el índice sí se versiona.
- **plano.json v2**: `"rotulo": {"convenciones": [{"simbolo": "corte"}, {"simbolo": ...,
  "descripcion": "..."}]}`. Validación con todos los problemas juntos: símbolo inexistente
  (lista los válidos), repetido, más de 24, campos desconocidos, caracteres que la fuente no
  tiene, biblioteca o índice ausentes (dice qué falta y cómo generarla). Sin convenciones en
  el plano, la biblioteca no hace falta.
- **Colocación** (`colocar_simbolo`): centrado en la casilla, `f = min(1, ancho_útil/ancho,
  alto_útil/alto)`, nunca se agranda; si f < 1, advertencia con el símbolo, la casilla y el
  porcentaje. Los símbolos se dibujan en la hoja base (antes de los detalles), como vector.
- **Verificación en el PDF guardado** (`verificar_simbolos`): en cada casilla, exactamente los
  trazos del índice y la caja esperada tras el escalado (±0,1 mm); descripción por
  `verificar_textos`. `cli componer` informa «Convenciones: N símbolo(s): X a escala 1:1, Y
  reducido(s)».
- docs: formato_plano.md (sección Convenciones y `extraer-simbolos`), README.

**Pruebas**: 557, todas pasan (19 nuevas), con un plano y una biblioteca SINTÉTICOS
(`conftest.crear_plano_con_leyenda`: plano girado 270°, rejilla, descripciones en trazos,
símbolos de línea, relleno, puntos, malla, uno muy ancho y uno muy alto): extracción (trazos
y caja de cada símbolo, página solo con el símbolo, índice escrito; ids provisionales sin
índice y casillas omitidas; casilla vacía, ids repetidos, hoja de otro tamaño, página
inexistente; CLI), biblioteca ausente / sin medir, colocación (centrado, sin agrandar,
reducción), y en `componer`: llenado por columna con desborde de la 13.ª a la columna
derecha, descripción propia, símbolo ancho reducido con advertencia, símbolo alto 1:1 arriba
y reducido en la fila 10, todos los problemas juntos (más de 24, repetido, inexistente, campo
desconocido, carácter sin glifo, tipo), biblioteca ausente al componer, descripción que no
cabe, **falla forzada de la verificación** (símbolo corrido 0,3 mm → error sin PDF) y el
resumen del CLI. Esquema: rejilla de A1 ERCO y orden de llenado, 4 casos inválidos. Pruebas
existentes ajustadas: `test_rotulo_formato` (campo `convenciones`, +48 celdas, mensaje del
tipo).

**Ejemplo** (`data/`, no se versiona): las 12 convenciones en
`data/planos/ejemplo_rotulo_v2.json` (con «VÍA SUÁREZ – LA GLORIA» como descripción propia de
`via_existente`) → `data/output/ejemplo_rotulo_v2.pdf`: 12 símbolos a escala 1:1, ninguno
reducido, sin advertencias; la hoja sigue con 1 sola imagen (el logo).

**Pendiente**
- ~~Pregunta para Alan: ¿«límite de predio proyectado» debe verse distinto de «límite de
  predio»?~~ En el plano de origen los dos son idénticos (mismo naranja, 13,25 × 0,51 mm).
  Decisión (2026-11-09): mismo naranja con transparencia 0,5 (subfase 4.2c).
- La biblioteca tiene 12 símbolos de un solo plano; sumar otros cuando aparezcan (otra
  leyenda: otro `extraer-simbolos` con su índice).
- El editor todavía no edita notas ni convenciones.

### Subfase 4.2c — Viñetas en las notas y opacidad por símbolo ✅ (2026-11-09, commit 1b31025)

**Qué se hizo**
- **Viñetas** (`notas.py`): en los .txt, una línea que empieza con `- ` es una viñeta de la
  nota anterior del mismo archivo (error claro si no hay nota antes; un `-` solo se ignora);
  en el plano.json, cada elemento de `adicionales` es un texto o `{"texto": ..., "vinetas":
  [...]}` (campos desconocidos, texto vacío o viñetas mal formadas: error). Se dibujan con
  «•» donde empieza el texto de la nota y su texto un poco más adentro (ancho de «• »),
  con sangría francesa; sin espacio extra entre la nota y sus viñetas ni entre viñetas (el
  medio renglón va solo entre notas). Misma reducción 1,8 → 1,5 mm y mismos errores (el de
  ancho dice «nota k, viñeta j»). Verificación: líneas escritas = leídas (las de las viñetas
  cuentan), dentro de la celda, y numeración 1…N (las viñetas no se numeran).
- **Opacidad por símbolo** (`simbolos.py`): campo opcional `"opacidad"` (0 < o ≤ 1, por
  defecto 1) en `simbolos/indice.json`; `extraer-simbolos` lo conserva al regenerar.
  Se aplica al colocar el símbolo envolviéndolo en un estado gráfico `ExtGState` (`/CA`,
  `/ca`) en una página intermedia: sigue siendo vector, sin imágenes y con los mismos trazos.
  La verificación de trazos no cambia; además comprueba que ningún trazo del símbolo quede
  más opaco que lo pedido. `limite_predio_proyectado` usa 0,5.

**Pruebas**: 568, todas pasan (11 nuevas): viñetas en el txt (con sangría, comentario,
«-» solo y número que se conserva dentro de la viñeta), viñeta antes de una nota (también al
pasar de un archivo a otro), adicionales como objeto y sus errores, maquetación (signo en la
X del texto, texto más adentro, sangría francesa, sin medio renglón dentro de la nota, medio
renglón al final, numeración sin viñetas), reducción (36 líneas sueltas se reducen; las
mismas 36 como notas con viñetas caben a 1,8 mm), error de ancho de una viñeta, verificación
en el PDF, `componer` de punta a punta y el error sin PDF; opacidad leída, validada y
conservada por `extraer-simbolos`, aplicada en el PDF (mismo color, trazos y opacidad 0,5;
el otro símbolo opaco; sin imágenes nuevas) y falla forzada si no se aplica. Prueba
existente ajustada: `test_notas.test_verificar_notas_en_el_pdf` (la cantidad de líneas ahora
es un dato del resultado, no se recalcula).

**Ejemplo**: `data/output/ejemplo_rotulo_v2.pdf` regenerado; «límite de predio proyectado»
con el mismo naranja (1,0; 0,498; 0) y opacidad 0,5, vector; la hoja sigue con una sola
imagen (el logo).

### Subfase 4.2d — Firma con imagen en `componer` ✅ (2026-11-09, commit a21ab27)

Sin editor todavía: pegar, recortar y limpiar la firma irá en la 4.3b.

**Qué se hizo**
- **Formato** (aditivo): `rotulo.carpeta_firmas` (una ruta o una lista; A1 ERCO:
  `["../firmas", "../data/firmas"]`: `firmas/` para las reales y `data/firmas/` para
  ejemplos, las dos fuera de git) y `"acepta_imagen": true` en la columna `firma` de la tabla
  `firmas` (sin carpeta con celdas que la aceptan: error del formato).
- **plano.json v2** (sin cambiar de versión): la celda FIRMA acepta texto (como antes) o
  `{"imagen": "<id>"}` → `<carpeta>/<id>.png`.
- **`firmas.py`**: validación con todos los problemas juntos (id inválido o inexistente,
  repetido en dos carpetas, no es PNG, más de 600 × 200 px o de 100 KB, campo desconocido,
  celda que no acepta imagen; sin alfa = advertencia); colocación proporcional y centrada,
  nunca mayor que a 300 ppp; inserción con `insert_image` (máscara SMask); verificación:
  caja ±0,1 mm dentro de la celda, máscara presente e igual byte a byte al canal alfa del
  PNG (sin alfa: el `digest` de los píxeles), SHA-256 del archivo para el mensaje.
- **Regla de imágenes** en `componer`: de «no hay imágenes nuevas» a «exactamente las de la
  hoja base más una por firma pedida» (los detalles siguen sin poder traer imágenes).
- **Peso**: `insert_image` dejaba cada firma sin comprimir (~300 KB con su máscara); el PDF
  se guarda con `deflate_images=True` (sin pérdida; trazos y fuentes no cambian): cada firma
  pesa ~7 KB.
- `cli componer`: «Firmas en imagen: N (celda: id al X % de su tamaño a 300 ppp)».
- **Privacidad**: firmas fuera de git (`firmas/*.png` en `.gitignore`; `data/` ya lo estaba),
  fuera de editor.html, el plano.json solo guarda el id; ponerlas solo en los PDF emitidos.
- docs: formato_plano.md (sección «Firma con imagen» con la nota de privacidad).

**Pruebas**: 578, todas pasan (10 nuevas), con PNG SINTÉTICOS generados en tmp: formato (A1
ERCO solo acepta imagen en FIRMA; falta de carpeta, `acepta_imagen` mal, lista vacía),
colocación (chica queda a 300 ppp; grande proporcional al espacio útil), dos firmas en el
PDF con máscara y dentro de su celda junto a una firma de texto, firma sin alfa (advertencia,
sin máscara, verificada por píxeles), todos los problemas juntos y los casos aparte (más de
600 × 200 px, repetida, id con «..»), y **fallas forzadas** sin PDF: firma corrida 0,3 mm,
otra imagen en su lugar, sin máscara y una imagen de más.

**Ejemplo** (`data/`, no se versiona): dos firmas FICTICIAS (garabatos dibujados por script,
480 × 160 px con alfa) en `data/firmas/`, usadas en DIBUJÓ y DISEÑÓ de
`data/planos/ejemplo_rotulo_v2.json`: quedan al 24 % de su tamaño a 300 ppp (9,9 × 3,3 mm),
con máscara; la hoja tiene 3 imágenes (logo + 2 firmas).

**Pendiente**: el editor (pegar, recortar y limpiar el fondo: 4.3b); `proyecto.json` con el
registro de personas; con Alan: en qué emisiones va la firma y la autorización de cada persona.

### Subfase 4.2e — Firma con imagen más grande (caja ampliada) ✅ (2026-11-09, commit 7a73381)

**Qué se hizo** (sin tocar la plantilla)
- **Formato** (aditivo): `"alto_max_mm"` en la columna `firma` (A1 ERCO: 5,0 tras el ajuste;
  por defecto también 5,0 si la columna acepta imagen y no lo declara; error si va sin
  `acepta_imagen` o no es positivo). Cada celda de tabla conoce el cuerpo de su tabla (Y 20,9
  a 43,5 en firmas).
- **Caja de la firma** (`firmas.caja_firma`): ancho de la columna FIRMA menos el relleno (17,0
  mm), alto max(`alto_max_mm`, alto útil de su fila) (5,0 mm en DIBUJÓ, DISEÑÓ y APROBÓ; 7,9 mm
  en REVISÓ), centrada en su fila y corrida hacia adentro si se saldría del
  cuerpo de la tabla (menos el relleno): nunca sobre el encabezado ni fuera de la tabla. La
  imagen va proporcional y centrada en su caja, nunca mayor que a 300 ppp.
- **Montaje**: si las firmas de dos filas se cruzan, advertencia con las filas y el tamaño
  del cruce (`firmas.montajes`).
- **Verificación**: la firma dentro de su caja ampliada (±0,1 mm) y sin pisar el encabezado
  ni salirse del cuerpo de la tabla, con máscara y huella (como en la 4.2d).

**Ajuste** (mismo día): `alto_max_mm` de 8,0 a **5,0** en A1 ERCO y alto de la caja =
max(`alto_max_mm`, alto útil de su fila), para que REVISÓ use sus 7,9 mm y las filas de 4,5
mm se monten menos.

**Pruebas**: 585, todas pasan (7 nuevas en la 4.2e): caja centrada en su fila (DISEÑÓ, 5,0
mm), fila más alta que `alto_max_mm` con su propia altura (REVISÓ, 7,9 mm), corrida por el
límite en la primera (DIBUJÓ, hacia abajo hasta 42,9) y la última fila (APROBÓ, hacia arriba
desde 21,5), `alto_max_mm` en el formato (sin `acepta_imagen`, cero, por defecto 5),
firma de 600 × 200 px centrada en REVISÓ (17,0 × 5,67 mm), montaje DIBUJÓ / DISEÑÓ con
advertencia (15,0 × 5,0 mm cada una), DIBUJÓ + REVISÓ sin advertencia, y falla forzada «pisa
el encabezado» sin PDF. Pruebas ajustadas de la 4.2d: la colocación (ahora dentro de la
caja), la firma dentro del ancho de la columna y del cuerpo de la tabla, y la frase del
resumen.

**Ejemplo**: tres firmas ficticias de 600 × 200 px (DIBUJÓ, DISEÑÓ y REVISÓ). DIBUJÓ: 15,00 ×
5,00 mm, X 759,20–774,20, Y 37,90–42,90; DISEÑÓ: 15,00 × 5,00 mm, Y 34,25–39,25 (se montan
1,35 mm → advertencia); REVISÓ: 17,00 × 5,67 mm, X 758,20–775,20, Y 27,12–32,78 (sin montaje).

**Pendiente**: decidir con Alan si el cruce de 1,35 mm entre DIBUJÓ y DISEÑÓ es aceptable.

### Subfase 4.2f — Firmas por persona ✅ (2026-11-09, commit 3d325b3)

**Qué se hizo**
- **Una carpeta por persona** (`firmas.py`): `{"imagen": "<persona>"}` → `<carpeta>/<persona>/
  firma.png`; sin `firma.png` y con un solo PNG, ese; con varios, error que pide nombrar uno
  `firma.png` o usar `{"imagen": "<persona>/<archivo>"}` (variante, sin `.png`). Reemplaza la
  estructura plana de la 4.2d (`<carpeta>/<id>.png`), que deja de usarse.
- **Nombres**: letras con tildes y ñ, números, espacio, `_` y `-` («Luis Ángel Núñez»), sin
  espacios en los extremos; se rechazan `..`, rutas absolutas, `\`, `:`, puntos y cualquier
  separador distinto del único `/`. En Windows la búsqueda no distingue mayúsculas; las
  tildes se comparan normalizadas (Unicode NFC).
- Misma validación de imagen (PNG, 600 × 200 px, 100 KB, alfa) y misma lista
  `carpeta_firmas`; persona con carpeta en dos lugares: error. Los mensajes nombran la
  persona y las rutas donde se buscó.
- `.gitignore`: toda la carpeta `firmas/` (antes solo `firmas/*.png`), además de `data/`.
- docs: formato_plano.md (estructura, nombres, errores y privacidad), README.

**Pruebas**: 604, todas pasan (19 nuevas, con PNG sintéticos en tmp): persona con tildes,
espacios y mayúsculas distintas, variante, un solo PNG con otro nombre, varios PNG sin
`firma.png`, variante inexistente, carpeta sin PNG, y 16 rutas o nombres peligrosos
(`..`, absolutas, `\`, `:`, doble `/`, espacios en los extremos, punto, vacío, no texto).
Pruebas de la 4.2d/4.2e ajustadas a la estructura por persona (rutas y mensajes).

**Ejemplo**: las 3 firmas ficticias pasaron a `data/firmas/Ficticia Núñez/firma.png`,
`data/firmas/Ficticia Ocaña/firma.png` y `data/firmas/Ficticia Gómez/firma.png`; el plano de
ejemplo usa `{"imagen": "Ficticia Núñez"}`, etc. Mismos tamaños que en la 4.2e.

### Subfase 4.3a — Editor: datos y modelo del rótulo (sin formularios) ✅ (2026-11-09, commit b4716f9)

Decisiones (Paso 0): notas COPIADAS al plano.json (en `adicionales`, con viñetas);
`proyecto.json` como prellenado por copia (4.3b); fechas con selector, formato por defecto
`dd/mm/aa` configurable; orden de notas con subir/bajar; firmas NUNCA en editor.html.

**Qué se hizo**
- **`datos_rotulo_editor.py`**: catálogo de notas típicas leído de forma recursiva con
  `notas.leer_archivo_notas` (cada subcarpeta = un grupo con su nombre; la raíz = «General»;
  grupos → archivos → notas con viñetas, avisos y problemas de lectura); símbolos de
  convenciones en PNG transparente a 20 px/mm con su opacidad (aviso si falta la biblioteca);
  tabla de anchos de Arial (`Fuente.anchos_em`, 201 caracteres); definición del rótulo en JSON.
- **Formato**: `rotulo.formato_fecha` (A1 ERCO `"dd/mm/aa"`; día, mes y año una vez cada uno,
  separadores `/`, `-` o `.`).
- **`editor` / `preparar-editor --notas <carpeta>`**: `editor_datos.json` gana la clave
  `rotulo` (aditiva) y `simbolos/<id>.png`; todo se incrusta en editor.html. El resumen del
  comando dice cuántas notas, grupos y símbolos trae, los problemas de lectura y el peso.
- **`editor_rotulo.js`** (modelo puro, probado con Node): guarda el `rotulo` tal como vino y
  solo reemplaza los campos cambiados (`cambiar`, `serializar`); notas adicionales normalizadas
  `{texto, vinetas}` y escritas como texto u objeto; `noRepresentable` lista lo que los
  formularios no sabrán editar (notas de archivos .txt, títulos en lista, nombres en varias
  líneas, campos que el formato no tiene).
- **`editor_logica.js`**: `leerPlano` devuelve el plano original y recuerda cada detalle;
  `objetoPlano`/`serializarPlano` conservan lo no tocado (detalles sin mover tal como venían,
  incluso con `centrar`; formato y plantilla originales; rosa solo si cambió o ya estaba;
  mismo orden de claves). Corrección de paso: si el original no traía `"plantilla"`, ya no se
  agrega `"plantilla": null`.
- **Interfaz**: panel «Rótulo» informativo (catálogo, símbolos, rótulo del plano abierto y lo
  que se conserva sin editar).

**Pruebas**: 628, todas pasan (24 nuevas): catálogo por grupos recursivo (General primero,
subcarpetas anidadas, viñetas, número propio, archivo no UTF-8, viñeta suelta, carpeta vacía o
inexistente), tabla de anchos = medida de Python (±1e-6 mm), definición del rótulo, 8 formatos
de fecha, símbolos PNG a 20 px/mm con opacidad 0,5, aviso sin biblioteca, `editor --notas` con
una firma presente en la carpeta de firmas que **no** llega al HTML, formato sin rótulo; con
Node: **ida y vuelta idéntica** de 6 planos (v1 con `centrar`, sin plantilla, rosa oculta,
rosa `{}`, ejemplo completo con notas, viñetas, 12 convenciones y 3 firmas con imagen, rótulo
con campos raros) y del ejemplo real de `data/` (si está), solo cambia lo que se toca, plano
nuevo sin rosa por defecto, modelo (cambiar, volver atrás, quitar), notas con viñetas que
conservan `archivos`, avisos de lo no editable, resumen del catálogo.

**Verificación en Edge** (`data/verificacion_editor/verificar_rotulo.mjs`, fuera del repo):
12 comprobaciones OK, sin errores de JavaScript: catálogo por grupos, 12 símbolos en PNG, tabla
de anchos y formato de fecha, ninguna firma en el HTML, panel «Rótulo», **abrir el ejemplo
real y guardarlo sin tocar nada da el mismo JSON** (también el archivo descargado), `componer`
acepta el plano guardado (12 convenciones, 3 firmas), mover un detalle solo cambia ese detalle.
La verificación de la 4.1 (rosa) sigue toda OK.

**Peso**: editor de `data/input_ejemplo` (2 paquetes reales) con 11 notas típicas y 12
símbolos: **576 KB**; el rótulo aporta 77 KB (símbolos 61 KB, definición + anchos + notas
16 KB), como se estimó; el resto son miniaturas (via_ma: 255 KB).

**Corrección de REV.** (2026-11-09, commit b4716f9 junto con la 4.3a): la fila «0» es la emisión final (para
construcción) y A, B, C son emisiones previas. Antes el orden era 0 < A < B < C y con
revisiones 0, A y B salía REV. = B (incorrecto). Ahora el `orden` de `revisiones` en
`A1_ERCO.json` es `["A", "B", "C", "0"]`: con «0», REV. = 0; si no, la mayor letra llena entre
C, B y A; sin revisiones, vacía. La función `ultima_revision` no cambió (toma la de mayor
orden); cambió el dato del formato, los textos de ayuda y el mensaje de letra inválida, que
ahora lista «A, B, C, 0». Pruebas: casos 0+A+B → 0, solo A+B → B, solo 0 → 0, ninguna → vacía
(en `ultima_revision` y en `componer`). Suite: **630**, todas pasan. `ejemplo_rotulo_v2.pdf`
regenerado: REV. = 0.

### Subfase 4.3b — Editor: formularios del rótulo, parte 1 ✅ (2026-11-09, commit 39f73e1)

**Qué se hizo**
- **Panel «Rótulo»** con formularios (`editor_panel_rotulo.js`, solo pantalla; reglas en
  `editor_formularios.js`, lógica pura probada con Node):
  - **Datos del plano**: Título, No. PLANO, HOJA, DE, ESTE, NORTE, ESC. de localización,
    Diseñador, Revisor (caja de varios renglones en las celdas de varias líneas: una línea por
    renglón). ESCALA y REV. calculadas, solo lectura, con la regla de `componer`.
  - **Revisiones**: tarjeta por revisión con VER. (lista de letras libres, sin repetir), fecha,
    descripción, dibujó, diseñó, revisó, aprobó; Quitar y Agregar revisión.
  - **Firmas**: DIBUJÓ, DISEÑÓ, REVISÓ (2 líneas), APROBÓ con nombre, matrícula, fecha y firma
    como **Texto** o **Persona** (lista de `--firmas`, guarda `{"imagen": "<persona>"}`).
  - **Fechas** con calendario que escribe en `formato_fecha` (`dd/mm/aa`).
  - **Validación en vivo con los mismos textos que `rotulo.py`/`firmas.py`**: campos
    desconocidos, calculados escritos, tipos, saltos de línea, letras inválidas o repetidas,
    columnas desconocidas, imagen fuera de FIRMA o con nombre inválido, caracteres que la
    fuente no tiene y lista de líneas de más. La casilla con problema queda en rojo. Una
    persona que no está en la lista es aviso. **Si el texto cabe** sigue siendo de `componer`
    (4.3e).
  - Forma de los valores: se respeta la del plano (lista sigue lista; entero sigue entero);
    campo vacío = se quita (vuelve su `por_defecto`).
- **`editor --firmas <carpeta>`** (`firmas.personas_firmas`): solo NOMBRES de las carpetas de
  personas (con PNG y nombre válido; las demás se omiten con aviso). Ninguna imagen, nombre de
  archivo ni ruta de la carpeta llega al HTML.
- **`editor --proyecto <proyecto.json>`** (`proyecto.py`, esquema versión 1 en
  `docs/formato_proyecto.md`): `nombre` (informativo), `disenador`, `revisor`,
  `prefijo_no_plano` y `firmas.<fila>.{nombre, matricula}`; validado contra el formato con todos
  los problemas juntos (si falla, no se genera el editor). Prellena SOLO un plano nuevo
  (`EditorRotulo.prellenar`); al guardar queda copiado en el plano.json.
- **Fuente**: `Fuente.rangos_unicode()` (Arial: 145 rangos, ~2 KB) en la tabla de la fuente
  del editor: el JavaScript sabe exactamente qué caracteres tiene Arial (coincide con
  `has_glyph` en los 196 608 primeros puntos de código).
- `noRepresentable` ya no avisa las listas de líneas (ahora se editan); avisa valores que el
  formulario no sabe mostrar.

**Pruebas**: **672**, todas pasan (42 nuevas): proyecto.json (válido, 9 problemas juntos,
versión, archivo inexistente / JSON roto / no UTF-8, formato sin rótulo); personas (nombres con
tildes, sin PNG, nombre inválido, carpeta vacía o inexistente); `editor --firmas` incrusta solo
los nombres (ni el base64 de 3 PNG sintéticos, ni «firma.png», ni la ruta, ni nada copiado a
la carpeta del editor); `editor --proyecto` válido e inválido; rangos de la fuente = caracteres
faltantes; con Node: **los 22 problemas de un rótulo malo salen con el mismo texto en
JavaScript y en Python** (ni uno más ni uno menos), valores válidos sin problemas en los dos,
REV. y ESCALA iguales a Python, fechas en 4 formatos y fechas inválidas, forma de los valores,
revisiones (agregar, cambiar letra, llenar las 4, quitar), firmas (texto, persona, quitar),
**ida y vuelta tras editar** (solo cambia lo editado, mismo orden de claves, y Python acepta
el resultado), ida y vuelta sin tocar (6 planos), prellenado de proyecto (plano nuevo sí,
abierto no, copiado al guardar y aceptado por Python).

**Verificación en Edge** (`data/verificacion_editor/verificar_formularios.mjs`, fuera del
repo): 14 comprobaciones OK, sin errores de JavaScript: lista de 3 personas y ninguna imagen
en el HTML; plano nuevo prellenado desde `data/proyecto_ejemplo.json` y aceptado por
`componer`; el ejemplo real abierto y guardado sin tocar = idéntico; REV. «0», ESCALA
«INDICADAS»; editar con el formulario (HOJA, quitar NORTE, descripción, revisión C con fecha del
calendario 09/11/26, APROBÓ de texto a persona) da el original + solo esos 5 cambios y
`componer` lo acepta (4 firmas en imagen, REV. 0); un «中» en No. PLANO muestra el texto de
Python y la casilla en rojo. Las verificaciones de la 4.3a (actualizada: ahora los nombres de
personas sí van; las imágenes no), de la rosa y del editor base siguen todas OK.

**Peso**: editor de `data/input_ejemplo` con notas, símbolos, 3 personas y proyecto: **624 KB**
(era 576 KB: +48 KB, sobre todo los dos JS nuevos y los rangos de la fuente).

**Pendiente**: 4.3b2 (pegar, recortar y limpiar la firma en imagen), 4.3c (notas típicas con
casillas, orden subir/bajar y notas a mano), 4.3d (convenciones con miniaturas), 4.3e/f
(maquetación en JavaScript: si cabe y si se reduce, con avisos idénticos a Python; vista previa
dibujada). El calendario abre en la fecha escrita solo si está en `formato_fecha`: las fechas
del ejemplo real (`data/`) se pasaron a `dd/mm/aa` (06/11/26) y el PDF compone igual (mismas
1427 palabras salvo las 7 fechas, mismos 20 086 trazos y 4 imágenes, REV. 0).

### Subfase 4.3c — Editor: notas (y panel Rótulo compacto) ✅ (2026-11-09, commit 3680f57)

**Qué se hizo**
- **Panel «Notas»** (`editor_panel_notas.js`, solo pantalla; reglas en `editor_notas.js`, lógica
  pura probada con Node):
  - **Notas del plano**: lista con numeración en vivo (1…N; con `archivos`, «+1.», «+2.»…
    porque van después de las de los .txt), ↑ ↓ ✕, texto (una línea; Enter no hace salto) y
    viñetas (una por línea) editables: la nota está copiada.
  - **Notas típicas** por grupo con casillas: marcar = al final de la lista; desmarcar = sale;
    no se repite. Clave de cada nota: ruta relativa del .txt + línea
    («vias/generales_vias.txt, línea 4»), porque el `origen` de Python solo trae el nombre del
    archivo. Al abrir un plano, una nota igual a una típica queda marcada. El aviso de número
    propio de la línea del .txt se muestra junto a la nota.
  - **Agregar nota a mano**, con viñetas.
  - Se guarda en `rotulo.notas.adicionales` en el orden de la lista; lo no tocado sale tal como
    venía (`original`); `archivos` y cualquier otra clave de `notas` intactos. Adicionales que
    la lista no sabe mostrar: la lista queda de solo lectura y se conservan.
  - **Validación en vivo con los mismos textos que `notas.py` y `rotulo._notas`**: tipo de
    `notas`, campos desconocidos, `archivos` y `adicionales` mal formados, salto de línea, texto
    vacío en un objeto, viñetas que no son lista de textos, caracteres que la fuente no tiene
    y el aviso de número propio. Una nota adicional vacía: aviso propio del editor (Python la
    omite sin mensaje). Los .txt de `archivos` no se leen desde el navegador (solo se revisa que
    sea lista de textos); con `archivos`, el «la nota k» de los mensajes de caracteres cuenta
    solo las adicionales. Si caben: `componer` (4.3e).
- **Panel Rótulo compacto** (sin cambiar reglas): revisiones con VER. y Fecha en una línea y
  Dibujó/Diseñó/Revisó/Aprobó en 2 × 2, mostradas en el orden del rótulo (0, C, B, A;
  `ordenRotulo`, la lista del plano no se reordena); firmas con Nombre | Matrícula y Firma |
  Fecha; el Título crece solo hasta ~6 renglones. Panel derecho de 330 a 380 px.

**Pruebas**: **686**, todas pasan (14 nuevas, con Node): errores de 5 casos de notas malas =
los de Python (mismos textos, ni uno más ni uno menos); avisos de número propio = los de
Python; nota vacía (Python callado, editor avisa); catálogo real de `catalogo_notas` (claves,
aviso de número propio, marcar sin repetir, desmarcar); enlazar notas del plano con el
catálogo; operaciones (subir, bajar, quitar, a mano con viñetas); lista no representable se
conserva; ida y vuelta sin tocar (6 planos) y tras elegir, ordenar y editar (solo cambia
`adicionales`, la nota no tocada sale igual, Python la acepta); orden de revisiones 0, C, B, A.

**Verificación en Edge** (`data/verificacion_editor/verificar_notas.mjs`, fuera del repo):
14 comprobaciones OK, sin errores de JavaScript, con el ejemplo real: archivos como «Vienen de
archivos», catálogo General (1), hidraulica (3), vias (7), numeración «+1. +2.», guardar sin
tocar = idéntico; marcar 3 típicas, desmarcar una, quitar y volver a poner otra (no se repite),
subir/bajar, editar texto y nota a mano con viñetas → el plano guardado = original con solo
`adicionales` cambiado, y `componer` lo compone con esas notas en el PDF; «中» da el texto de
Python y la nota en rojo; «3. …» a mano da el aviso de número propio; revisiones 0, B, A;
Título sin barra. Las verificaciones de la 4.3b (ajustada al nuevo orden de las revisiones),
4.3a, rosa y editor base siguen OK.

**Peso**: editor del ejemplo **655 KB** (670 617 bytes; era 624 KB: +31 KB de los dos JS nuevos
y los ajustes).

**Ajuste (2026-11-10, commit 3680f57): notas que ya vienen de archivos.**
- Python (`datos_rotulo_editor.rutas_desde_el_plano`): cada .txt del catálogo lleva `ruta_plano`
  (relativa a la carpeta del editor, donde va el plano.json) y `absoluta`.
- JavaScript (`editor_notas.js`): `archivosIncluidos` compara cada ruta de `archivos` con esas
  rutas (normalizando `\`, `.`, `..`, tildes y mayúsculas); sus notas típicas quedan con la
  casilla desactivada y «ya incluida desde archivos», no se pueden marcar (`marcar` las
  rechaza) ni se enlazan al abrir un plano. `avisosRepetidas`: una adicional con el mismo texto
  (normalizado como `notas._nota`) que una nota de esos .txt da «esta nota ya viene en
  <archivo> (línea n); saldría dos veces en el plano» (aviso del editor; la nota en amarillo).
  Un .txt de `archivos` fuera del catálogo no se puede leer desde el navegador: el panel lo dice.
- Pruebas: **695**, todas pasan (9 nuevas, con Node): rutas del catálogo vistas desde el plano;
  «mismo archivo» igual a `componer` (ruta resuelta desde la carpeta del plano y
  `os.path.samefile`) con `\`, `.`, `..`, mayúsculas, ruta absoluta, otro archivo con el mismo
  contenido, archivo inexistente y ruta mal escrita; «mismo texto» igual a `notas.leer_notas`
  (espacios, número propio, viñetas que no cuentan, sin punto o en minúsculas = distinta);
  incluidas que no se marcan ni se enlazan.
- Verificación en Edge (`verificar_notas_archivos.mjs`, plano de prueba
  `data/editor_rotulo/plano_notas_archivos.json`): 9 comprobaciones OK, sin errores de
  JavaScript; las de notas, formularios y rótulo siguen OK. Editor del ejemplo: 662 KB.

**Pendiente** (al cerrar la 4.3c): 4.3b2 (firma en imagen: pegar, recortar, limpiar), 4.3d
(convenciones), 4.3e/f (maquetación en JavaScript y vista previa).

### Subfase 4.3d — Editor: convenciones ✅ (2026-11-10, commit d032e3b)

**Qué se hizo**
- **Panel «Convenciones»** (`editor_panel_convenciones.js`, solo pantalla; reglas en
  `editor_convenciones.js`, lógica pura probada con Node):
  - **Convenciones del plano** (n de 24): miniatura, número y lugar en la leyenda en vivo
    («columna izquierda, fila 3»; llenado por columna 1–12 / 13–24, como `rotulo_formato`),
    ↑ ↓ ✕ y descripción editable (vacía = la de por defecto, en gris).
  - **Símbolos disponibles**: los del índice con su miniatura (PNG ya incrustado, con su
    opacidad) y casilla; sin repetir; con 24, aviso «La tabla de convenciones está llena…».
  - Se guarda en `rotulo.convenciones`: `{"simbolo"}` y `"descripcion"` solo si es distinta de la
    de por defecto (una lista de líneas sigue siendo lista); lo no tocado sale como vino; un
    símbolo que el índice no tiene se conserva y se marca «símbolo desconocido».
  - **Validación en vivo con los mismos textos que `rotulo._convenciones`** (tipo, más de 24,
    objeto, campo desconocido, id inexistente con la lista de válidos, repetido) y la revisión
    de la descripción en su celda `convenciones.<k>.descripcion` (tipo, saltos, líneas de más,
    carácter sin glifo). Si cabe: `componer` (4.3e).
- `docs/editor.md`: sección 2e; se arregló un párrafo que la inserción de la 2d había partido.

**Pruebas**: **714**, todas pasan (19 nuevas, con Node y una biblioteca sintética real hecha
con `extraer_simbolos`): errores de 7 casos malos = los de `preparar_rotulo` (mismos textos);
3 casos válidos sin problemas en los dos; mensajes de id inexistente y repetido; casillas
(1, 12, 13, 24, 25); marcar sin repetir y tope de 24 con aviso; descripción solo si cambió;
desconocido y no representable; ida y vuelta sin tocar (incluidas las 12 del ejemplo, que la
biblioteca sintética no conoce) y tras ordenar y editar (solo cambia lo tocado; Python acepta).

**Verificación en Edge** (`data/verificacion_editor/verificar_convenciones.mjs`, fuera del
repo): 11 comprobaciones OK, sin errores de JavaScript, con el ejemplo real: 12 convenciones
y 12 casillas marcadas, «columna izquierda, fila 1…12», miniaturas cargadas, guardar sin tocar
= idéntico; desmarcar y volver a marcar `gps`, subirla, editar «CORTE (TERRAPLÉN)» y vaciar la
de `via_existente` → solo esos cambios, y `componer` lo compone (12 símbolos, «VÍA EXISTENTE»
por defecto en el PDF); «中» da el texto de Python; un `no_existe` queda en la casilla 13
(columna derecha, fila 1), marcado como desconocido, con el error de Python, y se conserva
al guardar. Las verificaciones de notas, notas desde archivos, formularios y rótulo siguen OK.
Con la biblioteca actual hay 12 símbolos: la columna derecha y el tope de 24 se prueban con
Node (y la columna derecha también en Edge, con el símbolo desconocido).

**Peso**: editor del ejemplo **681 KB** (697 523 bytes; era 662 KB).

**Pendiente** (al cerrar la 4.3d): 4.3b2 (firma en imagen: pegar, recortar, limpiar), 4.3e/f
(maquetación en JavaScript: si cabe y si se reduce; vista previa dibujada).

### Subfase 4.3b2 — Editor: cargar, recortar y limpiar una firma ✅ CERRADA (2026-11-10, commit 5beb494)

(La 4.3d quedó en el commit d032e3b.)

**Qué se hizo**
- **`editor_firma.js`** (lógica pura, Node y navegador): recorte, limpieza con umbral suave por
  luminosidad (Y = 0,299 R + 0,587 G + 0,114 B; transición de 40 niveles), tinta en su color
  («despegada» del blanco) o en negro, recorte al trazo (alfa ≥ 16) con 2 px, reducción
  proporcional por promedio de área con alfa premultiplicado a 600 × 200 px, codificador PNG
  RGBA propio (filtro adaptativo; la compresión zlib la pone el navegador con
  `CompressionStream("deflate")` o Node con `zlib`), y si pasa de 100 KB se achica un 15 % y
  se repite. `revisarPng` y `avisoSinAlfa` con los textos de Python; `problemaNombre` con las
  reglas de `firmas.NOMBRE_VALIDO`.
- **`firmas.py`**: la revisión del PNG pasó a `revisar_png` y el aviso a `aviso_sin_alfa`
  (públicas, mismo comportamiento y mismos textos; `pedir_firma` las usa).
- **Diálogo «Cargar firma…»** (`editor_dialogo_firma.js`): elegir archivo o pegar con Ctrl+V,
  recorte con el mouse, umbral con control deslizante, tinta, vista sobre fondo cuadriculado,
  tamaño/peso/alfa y revisión en vivo, nombre de la persona, «Guardar en la carpeta de
  firmas…» (`showDirectoryPicker`: escribe `<carpeta>/<persona>/firma.png`, pregunta antes de
  reemplazar y avisa si la carpeta no se llama firmas), «Descargar firma.png» (y dice que va en
  `firmas/<persona>/`) y «Solo usar el nombre». La fila queda con `{"imagen": "<persona>"}`.
  Privacidad: todo en memoria; al cerrar se vacían los lienzos y se quita el diálogo.
- **«Persona nueva…»** en la lista de personas de la firma (y en Persona sin lista): se escribe
  el nombre, se valida con las reglas de firmas.py y queda `{"imagen": "<persona>"}`; las
  personas nuevas se suman a la lista de la sesión.
- Cosméticos: miniaturas de Convenciones sobre gris claro (#eef0f3) con borde; ✕ de quitar
  siempre rojo en Notas, Convenciones y Revisiones (el «Quitar» de Revisiones pasó a ✕). Los
  símbolos de línea muy fina (línea eléctrica, curvas de nivel) siguen tenues en la miniatura
  de 60 × 22 px: en el PDF van en vector.

**Pruebas**: **735**, todas pasan (21 nuevas, con Node y un garabato sintético con ruido):
umbral suave; garabato con recorte manual (la línea gris del borde queda fuera), fondo con
ruido todo transparente, recorte al trazo exacto con 2 px, reducción proporcional, PNG RGBA
con alfa que pasa `firmas.revisar_png`; tinta en su color o en negro; sin trazo = error claro;
peor caso de peso (más de 100 KB) achicado hasta caber; **mismos textos que
`firmas.revisar_png`** en 5 casos (no PNG, más ancho, más de 100 KB, las dos cosas, sin alfa) y
el aviso sin alfa; 14 nombres de persona = `firmas._partes_del_id`; **componer acepta la firma
generada por JavaScript** (con alfa, sin advertencias). La prueba de la 4.3b sobre «firma.png»
en el HTML se ajustó: el código del diálogo nombra «firma.png»; lo prohibido es el archivo de
una persona.

**Verificación en Edge** (`data/verificacion_editor/verificar_firma.mjs`, fuera del repo): 16
comprobaciones OK, sin errores de JavaScript: 4 botones «Cargar firma…»; pegar una imagen
sintética (Ctrl+V) y recortarla con el mouse (eventos reales); revisión «Cumple lo que pide
componer»; nombre con punto rechazado; «Guardar en la carpeta de firmas…» disponible (el diálogo
de carpeta no se puede automatizar); descarga de firma.png con el aviso de dónde va; al cerrar
no queda diálogo, lienzo ni la imagen en la página; el plano.json solo lleva
`{"imagen": "Ficticia Prueba Editor"}`; editor.html en disco sin cambios (SHA-256); la firma pasa
`firmas.revisar_png` (600 × 146 px, alfa, 18 KB) y `componer` la pone en APROBÓ (4 firmas en
imagen); «Persona nueva…» escrita a mano; 17 ✕ en rojo; miniaturas sobre gris. La firma de
prueba se borra de data/firmas/ al terminar. Las verificaciones de convenciones, notas, notas
desde archivos, formularios y rótulo (ajustadas: buscan el archivo de una persona, no el texto
«firma.png») siguen OK.

**Peso**: editor del ejemplo **718 KB** (735 509 bytes; era 681 KB).

**Mejora (2026-11-10, en el mismo commit 5beb494): sombras e iluminación despareja.**
- `editor_firma.js`: `estimarFondo` (máximo por bloques de ~1/40 del lado mayor, cierre
  morfológico entre bloques vecinos —máximo y luego mínimo— y promedio 3 x 3, interpolación
  bilineal) y `compensarFondo` (cada píxel dividido por su fondo, antes del umbral; opción
  activada por defecto). `umbralOtsu` (si varios umbrales empatan —un hueco sin píxeles entre
  tinta y papel— toma el centro, para no adelgazar los bordes suavizados) y `umbralAutomatico`
  (sobre la imagen recortada y compensada; entre 40 y 250). `fraccionOpaca` y `avisoFondo`
  (más del 25 % de la firma opaca).
- Diálogo: casilla «Compensar sombras e iluminación despareja» (activada; al cambiarla se
  recalcula el umbral automático), botón «Umbral automático», umbral inicial = Otsu, control
  de 40 a 250 con la ayuda «Bajar el valor = más fondo transparente; si baja demasiado, se
  pierde el trazo fino.» y el aviso de fondo.
- Pruebas: **742**, todas pasan (7 nuevas, con Node y una «foto» sintética con degradado de
  245 a 135, sombra ×0,6 y ruido): fondo estimado (mitad de los píxeles con error del orden del
  ruido, 99 % bajo 25; el papel compensado más oscuro queda transparente con el umbral
  automático); con compensación el papel queda transparente (< 0,1 % opaco) y el trazo se
  conserva (> 97 %), sin compensación queda fondo opaco y salta el aviso; Otsu igual a una
  referencia en Python en 3 casos; rango 40–250 y dirección (bajar = más transparente); textos
  del aviso.
- Verificación en Edge (`verificar_firma_fondo.mjs`): 11 comprobaciones OK, sin errores de
  JavaScript; la de la firma y las demás siguen OK (la de formularios se ajustó: `data/firmas`
  puede tener carpetas reales del usuario y subcarpetas).
- Editor del ejemplo: **727 KB** (744 405 bytes).

**Cierre de la 4.3b2**: commit **5beb494** en `fase-4`; **742 pruebas**, todas pasan.

### Subfase 4.3e — Editor: avisos «no cabe / se reducirá» ✅ (2026-11-10, commit f64977a)

El editor **mide** cada texto del rótulo como `componer` y avisa en vivo, junto al campo, con
los mismos textos. Sigue siendo una ayuda: `componer` vuelve a maquetar y validar todo.

- **`editor_maquetacion.js`** (nuevo, lógica pura, Node y navegador): copia de
  `maquetacion.py` (`alturasAProbar`, `partirEnLineas`, `maquetar` con las posiciones de cada
  línea) y de `notas.maquetar_notas` (`maquetarNotas`: numeradas, sangría francesa, viñetas,
  media línea entre notas, pegadas arriba). Ancho = suma de avances de la tabla `anchos_em` ×
  tamaño (como PyMuPDF, sin kerning: diferencia medida 0 mm en 3000 textos). Para que los textos
  sean idénticos: `fmt` redondea como `f"{v:.1f}"` de Python (al par en los empates exactos:
  0.25 -> «0.2»; `toFixed` daría «0.3»), `redondear`/`redondearEntero` como `round`, y los
  espacios son los de `str.split()`/`strip()` (incluye el espacio duro). Un carácter que la
  tabla del editor no trae (p. ej. «Ω», que Arial sí tiene) no se mide: `{sin_medir}`.
- **`editor_formularios.js`**: `validarTexto` maqueta (celda con `rect_mm` y `alinear`, más el
  interlineado): «no cabe» = el error de `TextoNoCabe`; reducción = la advertencia de
  `rotulo.preparar_rotulo`; sin medir = aviso del editor «el editor no puede medir los
  caracteres …; componer dirá si el texto cabe». Sin valor se mide el por defecto («DEFINIR»),
  como Python. Cubre título, campos simples, revisiones y firmas (nombre, matrícula, cargo).
  `mensajeDeCampo`/`mensajesDeCampo`: qué mensajes son de qué campo (incluye «campo 'titulo',
  línea 2:» y «… el campo 'titulo' se escribió a …»).
- **`editor_convenciones.js`**: la descripción se mide por la misma vía.
- **`editor_notas.js`**: `validarNotas(valor, fuente, catalogo, definicion)` mide las notas
  (`medirNotas`): las de los .txt de `"archivos"` que están en el catálogo van primero (en su
  orden; un .txt repetido, dos veces, como Python), luego las adicionales. Si un .txt no está en
  el catálogo (o tuvo problemas al leerse), no se mide: aviso **ámbar e informativo** «el editor
  no puede medir las notas: '<archivo>' no está en el catálogo; componer lo comprobará», que no
  cuenta como error. Además, los avisos de lectura de esos .txt (número propio) se muestran
  primero, en el orden de `componer` (ajustada la prueba de la 4.3c que esperaba otro orden).
  `mensajesTamano` reparte los mensajes por nota adicional.
- **Pantalla**: rótulo — casilla roja («no cabe») o ámbar («se reducirá») y la lista de
  mensajes debajo del campo (en revisiones y firmas, al pie de la tarjeta); notas — error en la
  tarjeta de la nota (el textarea de viñetas en rojo si el problema es de una viñeta) y los
  generales (reducción de todas, notas de archivos, «no se puede medir») arriba de «Notas del
  plano»; convenciones — debajo de la descripción. Todo, además, en la lista de Problemas de
  cada panel, con el mismo estilo (`.advertencias.problemas-rotulo`). Se quitaron los textos
  «el editor todavía no lo calcula».
- `editor_html.py` / `editor.html`: nuevo marcador `/*@@JS_MAQUETACION@@*/`, antes de los
  formularios.

**Pruebas**: **791**, todas pasan (49 nuevas):
- `test_editor_maquetacion_js.py` (12): números y espacios como Python; alturas a probar; anchos
  ±1e-9 mm (300 textos al azar); corte en líneas; **todas las celdas de A1** con 35 textos, 7
  listas y 3 enteros (> 1500 casos: mismas líneas, posiciones, anchos, alturas y textos de «no
  cabe»), celda baja inventada (falta de alto, alineación derecha y centrada); título lleno en 3
  líneas, reducido y que no cabe; **justo en el borde** (el texto más ancho que cabe a cada
  altura de 2,5 a 2,0 y uno con un punto más; firmas, revisiones y No. PLANO al borde exacto);
  600 textos al azar; notas (vacías, viñetas, palabra más ancha que el texto o que la viñeta, 9 y
  10 notas, y las fronteras con A1: 20 notas largas a 1,8 mm, 21 a 1,7, 24 a 1,5 y 25 no caben);
  16 juegos de notas al azar; textos de las advertencias.
- `test_editor_cabe_js.py` (37): `F.validarRotulo` / `C.validarConvenciones` / `N.validarNotas`
  contra `preparar_rotulo` sobre los mismos valores (mismos errores; sin errores, mismas
  advertencias): título que cabe, se reduce (2,1 mm) y no cabe, 8 títulos límite (3 y 4 líneas a
  mano, saltos de línea, palabra larga, tildes/ñ/guiones, vacío, entero); revisiones y firmas;
  por defecto; caracteres sin ancho; 8 casos de convenciones (1,7 mm y «no cabe»); notas
  adicionales en las fronteras 20/21/24/25; 10 casos con archivos del catálogo, viñetas y
  repetidos; archivo fuera del catálogo (aviso, sin error); sin definición no se mide; reparto de
  mensajes por campo y por nota.
- Las pruebas de paridad anteriores siguen igual (p. ej. los 22 problemas de los formularios).
  Límite conocido: un entero de más de 15 cifras pierde precisión al leerse en JavaScript (no se
  usa en el rótulo; la prueba usa enteros normales). Las pruebas con PyMuPDF midiendo cientos de
  notas tardan: el barrido de notas se redujo a las fronteras.

**Verificación en Edge** (`data/verificacion_editor/verificar_maquetacion.mjs` y
`esperado_cabe.py`, fuera del repo; editor propio en `data/editor_cabe`, generado **sin
`--firmas` ni `--proyecto`**): 25 comprobaciones OK, **sin errores de JavaScript**. Cada mensaje
de la pantalla se compara con Python sobre el plano.json que guardaría el editor: título que se
reduce a **2,2 mm** (ámbar, aviso debajo y en Problemas; `componer` escribe el PDF con el mismo
aviso); descripción de convención que no cabe (rojo, mismo aspecto que los demás errores;
`componer` se niega con el mismo error); nota que no cabe (solo esa nota en rojo); 21 notas que
bajan a 1,7 mm (aviso arriba de la lista); .txt fuera del catálogo (solo avisos); una revisión y
una firma que no caben (cada error al pie de su tarjeta). Capturas en
`data/verificacion_editor/maquetacion/`: `01_titulo_se_reduce.png`, `02_convencion_no_cabe.png`,
`03_nota_no_cabe.png`, `04_revision_y_firma_no_caben.png`.

**Peso**: editor del ejemplo **754 KB** (772 484 bytes; era 727 KB, 744 405 bytes): **+27,4 KB**,
todo código (16 KB del módulo nuevo, con sus comentarios; ~12 KB en los demás); los datos no
cambian.

**Nota**: el `editor.html` sigue llevando rutas absolutas del disco (las del catálogo de notas,
4.3c, y `carpeta_editor`), que incluyen la carpeta de usuario de Windows. No es de esta
subfase; queda anotado por si se comparte un editor fuera del equipo.

### Subfase 4.3f — Editor: vista previa dibujada en el lienzo ✅ (2026-11-10, commit e597ebc)

Con la casilla **«Vista previa del rótulo»** (barra de arriba, encendida al abrir) el lienzo
dibuja en su sitio lo que escribirá `componer`, con las MISMAS posiciones y alturas. Sigue
siendo una ayuda: `componer` vuelve a maquetar y validar todo.

- **Datos nuevos** (aditivos): `rotulo.fuente.ascenso_em` / `descenso_em` (la caja de línea de
  `Fuente.caja_vertical_mm`; propiedades nuevas `Fuente.ascender_em` / `descender_em`) y
  `cuerpo_y` en cada tabla de la definición (para `firmas.caja_firma`).
- **`editor_vista_previa.js`** (nuevo, lógica pura, Node y navegador): `piezasRotulo` recorre
  los campos en el orden de `preparar_rotulo` (descripciones de convenciones, tablas, campos de
  texto con ESCALA/REV. calculadas y «DEFINIR» por defecto, y al final las notas) y maqueta con
  `editor_maquetacion.js`; copias de `colocar_simbolo`, `caja_firma` y `colocar_etiquetas` (con
  sus avisos). A diferencia de Python, un campo con problema no detiene el resto: sale en
  `problemas` con su celda y el mismo texto del error. `editor_notas.js`: la lista de notas en el
  orden de `componer` pasó a una función exportada, `notasParaComponer` (`medirNotas` la usa;
  mismo comportamiento).
- **`editor_lienzo_rotulo.js`** (nuevo, solo pantalla): capas SVG con una sola transformación
  mm → px; en el orden de `componer`: símbolos (PNG de 20 px/mm ya incrustados) debajo de los
  detalles; textos, etiquetas, cajas de firma y marcas de problema encima. Texto: Arial, sin
  kerning ni ligaduras, `textLength` = ancho calculado, y escrito **100 veces más grande** y
  reducido con `scale`: a ~3 unidades de tamaño Chromium redondea el avance de cada letra
  (diferencia de hasta 1,24 %); aumentado, la Arial del navegador mide como la tabla (0,010 %).
  Campo con problema: celda en rojo (ámbar si no se puede medir), nada dibujado, el mensaje al
  pasar el ratón; en vista limpia las marcas se ocultan y los textos quedan. Firma en imagen:
  caja punteada con «firma: <persona>» (la imagen nunca está en el editor). Si la Arial del
  navegador mide distinto (> 0,5 %), aviso al abrir.
- **`editor_ui.js`**: el rótulo se vuelve a dibujar solo si cambian sus valores o las escalas
  (clave JSON); al arrastrar solo se recalculan las etiquetas «ESC»; un dibujo por cuadro
  (`requestAnimationFrame`). Los avisos de etiquetas que no caben van **en vivo** al final de
  Advertencias, con el texto de `componer` (aunque la casilla esté apagada).
- **Plantilla en vector**: `preparar-editor` escribe además `plantilla.svg` (la misma hoja base
  sin detalles ni rosa, `get_svg_image(text_as_path=True)`); `imagen_plantilla.svg` en los
  datos; el editor.html la incrusta (base64) en lugar del PNG, como capa fija creada una sola
  vez. Datos sin `svg`: se usa el PNG.

**Pruebas**: **822**, todas pasan (31 nuevas):
- `test_editor_vista_previa_js.py` (26): plano completo (título reducido, revisiones A/B/0,
  firmas en texto y en imagen, 2 convenciones, notas de 2 .txt del catálogo + adicionales con
  viñetas) y 11 variaciones (por defecto, INDICADAS, sin detalles, líneas explícitas, saltos de
  línea, vacíos, revisiones, descripción vacía, notas reducidas…) contra `preparar_rotulo`:
  mismos textos en el mismo orden, bases, anchos, alturas y celdas, símbolos (casilla, escala,
  página y dibujo) y cajas de firma, ±1e-6 mm; 20 notas reducidas; 8 campos con problema (no
  cabe, salto de línea, tipo, carácter sin glifo, notas, descripción, firma): solo ese campo en
  `problemas`, con el mismo texto que Python, y lo demás igual que Python sin ese campo; símbolo
  fuera de la biblioteca; .txt fuera del catálogo (aviso); `colocarSimbolo` (400 casos al
  azar), `cajaFirma` (todas las celdas de firmas × 5 altos × 3 rellenos) y `etiquetasEscala`
  (254 planos, más de 10 avisos) contra Python.
- `test_datos_rotulo_editor.py` (2): `ascenso_em`/`descenso_em` reproducen
  `caja_vertical_mm`; `cuerpo_y` de cada tabla.
- `test_datos_editor.py` (1): `plantilla.svg` es A1, sin rosa, sin `<text>`, sin cargar nada de
  afuera y, rasterizada, igual que `plantilla.png`.
- `test_editor_html.py` (2 nuevas, 2 ajustadas): plantilla SVG incrustada (y PNG si no hay
  SVG), casilla y orden de los módulos; la lista de archivos incluye `plantilla.svg`.

**Verificación en Edge** (`data/verificacion_editor/verificar_vista_previa.mjs` y
`esperado_vista_previa.py`, fuera del repo; editor propio en `data/editor_vista_previa`,
**sin `--firmas` ni `--proyecto`**): **todo OK, sin errores de JavaScript**.
- Plano con título, n.º de plano, hoja, revisiones, firmas, 4 convenciones, notas (un .txt y
  adicionales con viñetas) y tres perfiles K0010 apilados a 2 mm: las **47 líneas** del lienzo
  están en el PDF de `componer` con el mismo texto y su base a **0,0000 mm** (tolerancia ±0,1
  mm); el PDF escribe 614 caracteres en la columna del rótulo y el lienzo dibuja 614; 4
  símbolos en el mismo rectángulo que Python (±1e-6 mm); 2 etiquetas «ESC: 1:50» (p2 debajo,
  p3 encima) y el aviso de p1 en Advertencias **idéntico** al de `componer`.
- Título que no cabe: celda en rojo, nada del título dibujado, el mensaje es el error de
  `componer` (que se niega); lo demás igual que el PDF anterior; firma `{"imagen": "Persona
  Ficticia"}`: caja punteada en el rectángulo de `caja_firma` (±1e-6 mm).
- Casilla apagada: nada de la vista previa; vista limpia: textos sí, marcas no.
- **Nitidez** (vista limpia, zona del logo y una línea del cajetín muy de cerca): con el SVG el
  87 % de los píxeles de línea son tinta plena; con el PNG anterior, 42 % (borroso).
- **Arrastre** (120 movimientos de un detalle, con su etiqueta): trabajo por movimiento
  **3,95 ms sin vista previa y 3,86 ms con ella** (p95 5,5 / 5,4 ms); cuadro completo 16,7 /
  16,6 ms (60 cuadros/s; en otra corrida un cuadro suelto de la vista previa subió la media a
  23 ms, con p95 21,8 ms). Arrastre real con el ratón: la etiqueta sigue al detalle.
- Capturas en `data/verificacion_editor/vista_previa/`: `01_plano_completo.png`,
  `02_notas_y_convenciones.png`, `03_cajetin.png`, `04_etiquetas_esc.png`,
  `05_no_cabe_y_firma.png`, `06_nitidez_svg.png` y `06_nitidez_png.png`.

**Peso** (`editor data/input_ejemplo --notas data/notas_tipicas`, mismo comando antes y
después): **772 232 → 921 559 bytes (754 → 900 KB, +146 KB)**: +116 KB por la plantilla en
vector (SVG 120 KB, 160 KB en base64, en lugar del PNG de 42 KB en base64) y +30 KB de código
(los dos módulos nuevos, 24,5 KB con comentarios, y los cambios en `editor_ui.js`).

**Límites**: no se ve la imagen de las firmas (solo su caja); las posiciones de los detalles
son las del editor antes de redondearlas a 0,01 mm al guardar (una etiqueta puede quedar
≤ 0,005 mm corrida respecto del PDF).

### Orden del proyecto ✅ (2026-11-11, commit a99216d)

No es una subfase: ordena carpetas y accesos directos para el uso diario.

**Qué se hizo**
- **Carpetas en la raíz**: `planos/` (los plano.json del usuario), `editor/` (solo
  `editor.html`), `resultados/` (los PDF), `firmas/<persona>/` y `notas/<grupo>/`. Todas fuera de
  git (`.gitignore` con «/» al inicio, para no ignorar `src/componedor/editor/`). `data/` queda
  con `input/` (paquetes de prueba del exportador), `pruebas/` (input_ejemplo, input_sinfondo,
  input_reales y 3 planos de prueba), `verificacion/` (antes `verificacion_editor/`; scripts y
  capturas, sin los perfiles de Edge) y `proyecto_ejemplo.json`. Se borraron los 7 editores
  viejos `data/editor*`, `data/output` (lo reemplaza `resultados/`), `data/notas` y
  `data/notas_tipicas` (ahora `notas/`), las 12 carpetas `perfil_edge` (~1,25 GB) y una firma
  duplicada; `data/` pasó de 1,47 GB a 13 MB.
- **`componedor.json`** (nuevo, versionado) y `configuracion.py`: `formato` general, sección
  `editor` (paquetes, salida, notas, firmas, proyecto) y sección `componer` (resultados). Rutas
  relativas al archivo; clave desconocida o ruta inexistente es error, con todos los problemas
  juntos.
- **`editor --config componedor.json`**: todas las rutas del archivo (no se mezclan con las de la
  línea de comandos). **`componer --config`**: usa el formato de la configuración (avisa si el
  plano indicaba otro) y deja el PDF en `resultados/<nombre del plano>.pdf`.
  **`componer --codigo-avisos`**: código 3 si el PDF salió con advertencias.
- **`Abrir editor.bat`** y **`Componer.bat`** (CRLF; `*.bat text eol=crlf` en `.gitattributes`):
  generan y abren el editor / componen el plano arrastrado (o el que se pide con doble clic), lo
  abren y, con errores o advertencias, esperan una tecla. Usan `.venv\Scripts\python.exe` o, si
  no está, el `python` del sistema (con `PYTHONPATH=src`).
- **Firmas solo en `firmas/`**: `A1_ERCO.json` → `"carpeta_firmas": ["../firmas"]` (se quitó
  `../data/firmas`); textos del diálogo «Cargar firma…» al día.
- **`editor/` sin subproductos**: `generar_editor` arma datos, plantilla (PNG y SVG), rosa,
  miniaturas y símbolos en una carpeta temporal, los incrusta y deja solo `editor.html`; al
  regenerar quita los subproductos de versiones anteriores por su nombre exacto (nunca un
  plano.json). `preparar-editor` los sigue dejando para revisarlos. `componer` no lee ninguno.
- Los planos del usuario (`PRUEBAFROTULO`, `plano_FIRMA2`, `plano_firma`) pasaron a `planos/` con
  las rutas corregidas; en `plano_firma`, APROBÓ usa ahora «Ficticia Gómez» (la persona
  «Ficticia Prueba Editor» la había creado y borrado `verificar_firma.mjs`).

**Verificación**
- Cada plano movido se compuso antes y después del cambio: textos con posición, trazos,
  imágenes (SHA-256) y página a 150 ppp píxel a píxel, **iguales** (también los 3 planos de
  `data/pruebas/planos`; `ejemplo_rotulo_v2_no_cabe` da el mismo error de siempre). Los 3 planos
  de `planos/` se componen con `Componer.bat` (`plano_firma` con 1 advertencia: firmas de DIBUJÓ
  y DISEÑÓ montadas 1,4 mm).
- `editor.html` generado sin subproductos: **idéntico byte a byte** al anterior; abierto en Edge.

**Pruebas**: **849**, todas pasan (27 nuevas desde la 4.3f): `test_configuracion.py`
(configuración, `editor --config`, `componer --config` y `--codigo-avisos`, los dos `.bat`) y
`test_editor_html.py` (solo queda editor.html, rutas relativas a la carpeta del editor, limpieza
de subproductos viejos, `preparar_editor` en otra carpeta).

**Rutas en las secciones anteriores**: los textos de las subfases citan rutas de entonces
(`data/editor_rotulo`, `data/output/...`, `data/verificacion_editor/...`, `data/notas`). Hoy:
los scripts y capturas están en `data/verificacion/`, los paquetes de prueba en `data/pruebas/` y
lo demás se borró (se regenera con los comandos). Los scripts `.mjs` conservan sus rutas viejas
(son registro; para volver a correrlos hay que actualizarlas).

### Rótulo: franja del logo sin DISEÑADOR ni REVISOR ✅ (2026-11-17, commit ec654d1)

**Qué se hizo**
- Se averiguó cómo estaba hecha la franja: los títulos «DISEÑADOR | REVISOR» y la línea vertical
  venían **dentro de la plantilla v2** (trazos SHX + 2 anotaciones invisibles, en una fila de
  Y 99,4–106,2 mm, encima del logo); los nombres («Luis Angel», «Alan Ruiz» en GUAMO) eran los
  campos `disenador` y `revisor` del rótulo, escritos por código a los lados del logo.
- **Plantilla v3** (`plantilla_v3.py`, comando `crear-plantilla-v3`, documentado en el README):
  desde la v2, **sin modificarla** (MD5 `d905e79296e4216cd003e4ee1e7487e6` antes y después),
  borra los 26 trazos que caen completos en esa fila (14 letras de DISEÑADOR, 11 de REVISOR y la
  línea vertical) y sus 2 anotaciones; no tapa nada con blanco. La fila queda vacía con su
  línea de abajo (opción A). El logo se reinserta (misma imagen, byte a byte, sin
  recomprimir; mismo tamaño) corrido **−2,06 mm** en X: su parte visible queda centrada en la
  columna del rótulo (750,35 mm). Se verifica sola (fuera de la fila y del logo, 0 píxeles
  distintos a 100 ppp). `formatos/A1_ERCO.json` usa la v3.
- **Campos retirados**: `disenador` y `revisor` salen del formato y pasan a
  `"campos_retirados"`. Un plano.json o proyecto.json viejo que los traiga sigue abriendo y
  componiendo: se ignoran y se avisa **una vez** con el mismo texto en `componer`,
  `editor --proyecto` y el editor (`rotulo_formato.AVISO_CAMPOS_RETIRADOS`, incrustado en la
  definición del rótulo). El editor ya no muestra los campos Diseñador y Revisor, no los
  prellena desde proyecto.json, no los repite en la lista de «no editable» y **los quita al
  guardar** (`editor_rotulo.paraGuardar`): un plano viejo, una vez guardado, ya no los trae y
  `Componer.bat` deja de detenerse por ese aviso. La validación sí los ve, para avisar al abrir.
- Paridad: Python y el editor leen la misma definición, así que la maquetación y la vista previa
  dejan de dibujar esos campos a la vez; el fondo del editor (SVG de la v3) tiene el logo
  centrado igual que el PDF (centro visible 750,39 mm en los dos).

**Verificación**: `resultados/planoguamo_prueba.pdf` desde `editor/planoguamo_prueba.json` con
`Componer.bat`: sin errores, 1 aviso (campos retirados), sin «Alan Ruiz» ni «Luis Angel» en la
franja (sigue «Luis Angel Nuñez» en la fila DIBUJÓ, como debe) y logo centrado (750,39 mm).
El PDF anterior quedó en `_para_borrar/resultados_antes_v3/`.

**Pruebas**: **867**, todas pasan (18 nuevas: `test_plantilla_v3.py` con una plantilla
sintética de la misma geometría, y `test_campos_retirados.py`: formato, `componer` de un plano
viejo, proyecto.json, datos del editor, paridad del aviso con el JS y que el editor los quite
al guardar, con el plano guardado compuesto en Python sin el aviso). ruff: los mismos
hallazgos que había en `HEAD` (ninguno nuevo; los 173 previos son de todo el proyecto).

**Nota**: el aviso es una advertencia de `componer`, así que `Componer.bat` se detiene a
mostrarla con un plano viejo que todavía no se volvió a guardar en el editor.

### Integración con el exportador — Etapa 1: servidor local y «Cargar DXF» ✅ (2026-11-17)

Plan aprobado (2026-11-17) en etapas:
- 0: el trabajador del exportador, que hace el agente del Exportador;
- 1: esta;
- 2: arrastrar las cajas exactas, la escala con el centro fijo y la vista previa PNG del
  trabajador;
- 3: «Exportar»;
- 4: componer desde el editor y el caso del DXF cambiado.

Decisiones:
- el trabajador persistente `cde-exporter worker` se lanza como comando externo;
- la vista previa es el PNG que da el trabajador;
- los paquetes van en `data/input/dxf/<dxf>/`;
- `plano.json` pasa a la versión 3 solo si el plano usa un DXF.

La especificación usada son los puntos 1–11 de la revisión del contrato. Ya se comparó con el
contrato final (`docs/protocolo_trabajador.md` del exportador, aprobado el 2026-11-17): coincide
en todo lo de fondo. Lo nuevo del contrato se agregó al trabajador falso: esquema 1.3 en `ready`,
`stage` en `status`, handles en hexadecimal y mayúsculas, `file_stem` saneado (§5.1),
`bounds_with_hidden` e `include_layers`. El Componedor ahora pide `load` con
`include_layers: false`.

**Qué se hizo**
- **`Abrir editor.bat`**: genera el editor y arranca `componedor servidor --config
  componedor.json`. Si el servidor no arranca, abre `editor.html` sin servidor, como antes.
- **Servidor** (`servidor.py`, `aplicacion_editor.py`):
  - solo escucha en 127.0.0.1, con el puerto que elija el sistema;
  - un token al azar en `?t=` para la página y en la cabecera `X-Componedor-Token` para la API;
  - `Host` exacto, `Origin` propio (obligatorio en POST), `Sec-Fetch-Site`, POST JSON de hasta
    64 KB;
  - no entrega otro archivo que `editor.html` y no recibe rutas;
  - el registro no guarda el token;
  - se apaga tras 30 min sin señal del editor.
- **Cuadro nativo** (`dialogo_dxf.py`): `tkinter` en un proceso aparte, delante del navegador. La
  ruta se valida (existe y es `.dxf`).
- **Trabajador** (`trabajador.py`, `proceso_windows.py`):
  - se lanza al primer «Cargar DXF», creado suspendido dentro de un **Job Object** con «matar al
    cerrar»; si el servidor muere, mueren el lanzador `cde-exporter.exe` y su `python.exe`;
  - stderr va a `data/cache_exportador/trabajador.log`;
  - espera `ready` hasta 30 s y comprueba la versión mayor 1;
  - mensajes claros si no está instalado, si no tiene la orden `worker` (el caso de hoy), si
    no responde o si se cae.
- **Canal** (`canal_trabajador.py`):
  - cola propia y un pedido a la vez (nunca provoca `BUSY`; si llega igual, se reintenta una
    vez);
  - cancelar en cola, en curso, o a la fuerza si no se nota en 60 s;
  - tras 2 caídas seguidas queda detenido, con el botón «Reiniciar trabajador»;
  - cada trabajador nuevo es una sesión nueva.
- **Carpeta de bloques** (`bloques_dxf.py`):
  - tamaño real en m, unidades y **escala sugerida** (la primera de `ESCALAS_ESTANDAR` con la
    que `página = tamaño × 1000 ÷ N + 2 × margen` cabe en el área de dibujo, con la regla de
    `colocar`);
  - notas: caja aproximada, sólidos 3D, proxies, regiones, imágenes, capas ocultas, unidades
    sin verificar, no cabe;
  - un bloque mal descrito se descarta con su motivo.
- **Editor**:
  - `editor_servidor.js` detecta el servidor y le habla;
  - `editor_dxf.js` arma los textos;
  - `editor_panel_dxf.js` pone el botón «Cargar DXF», la barra de avance con «Cancelar» y la
    carpeta encima de «Detalles disponibles»; los nombres siempre van como texto, nunca como
    HTML.
- Sin servidor el editor es el de siempre: el botón está desactivado con su explicación y el
  panel no se muestra.
- `componedor.json`: sección nueva y opcional `exportador` (`comando`, `trabajo`, `margen_mm`).
- Documentación: [servidor_editor.md](servidor_editor.md), `editor.md` §2f, README.

**Pruebas**: **977**, todas pasan (110 nuevas). Usan un **trabajador falso**
(`tests/trabajador_falso.py`) que habla el protocolo 1.0, y una prueba usa el `cde-exporter`
real si está instalado. Cubren:
- el Job Object, incluido que el trabajador y su nieto mueran si muere el servidor;
- el cliente del protocolo;
- la cola, con cancelación normal y a la fuerza, caídas y reinicio;
- la carpeta;
- el cuadro, con `tkinter` falso;
- el servidor: Host, token, Origin, límites y registro;
- el comando `servidor`, la configuración y el `.bat`;
- el JS en Node.

ruff: los mismos 173 hallazgos de `HEAD`.

**Verificación en Edge** (`data/verificacion/verificar_servidor_dxf.mjs`, fuera de git): todo
OK.
- Sin servidor: el botón está desactivado.
- Desde `file://` la API queda bloqueada, y el POST con `Origin: null` recibe 403.
- Con el trabajador falso:
  - avance, carpeta con 6 bloques (tildes, «Ø», ocurrencias 1 y 2 de 2, un nombre con
    `<b>` que se muestra como texto), notas, «No exportables», aviso;
  - recargar la página conserva la carpeta;
  - cancelar avisa «Carga cancelada.» y deja la carpeta anterior;
  - el resto del editor funciona igual.
- Con el `cde-exporter` real de hoy aparece el aviso «no tiene la orden «worker»».
- Sin errores de JavaScript.

**Pendiente de esta etapa**
- Probar el cuadro nativo a mano: en Edge sin ventana no se puede hacer clic.

### Integración con el exportador — Etapa 2: bloques en la hoja y vista previa ✅ (2026-11-17, commit ab77c6f)

Decisiones (visto bueno del 2026-11-17):
- (a) solo capas visibles en la vista previa;
- (b) plano.json versión 3 con `centro_mm` y `origen`;
- (c) un bloque que no cabe se queda en rojo y se guarda con aviso; `componer` lo rechaza;
- (d) teclas + y −, que no actúan con el foco en un cuadro de texto;
- nombres de paquete con nuestro propio sufijo de hash al agregar la escala (las carpetas
  `.cde-tmp-*` en `localizar_paquetes` quedan para la etapa 3).

**Qué se hizo**
- **Caja exacta** (`editor_bloques.js`, lógica pura): página = tamaño_m × 1000 ÷ N + 2 × margen;
  centro fijo al cambiar la escala; el centro se limita al mover (si cabe, la página completa en
  el área); escala vecina (+ / −) y escala por tirador (la esquina más cerca del puntero).
- **Vista previa PNG**: el PNG va al papel por coordenadas CAD (`cad_to_px` del contrato: sin
  giro, a = −d), con la misma fórmula de la caja; al cambiar la escala solo se reescala (no se
  pide otra). Llega como `blob:` (el token va en la cabecera).
- **Editor** (`editor_ui.js`, `editor_panel_dxf.js`):
  - «Agregar al plano» en cada tarjeta (desactivado sin unidades verificadas);
  - la caja punteada con la imagen encima, «Pidiendo vista previa…», y en rojo con «no cabe:
    sobran X × Y mm; sugerida 1:N»;
  - Propiedades del bloque: selector de escala (la sugerida marcada), «Escala sugerida»,
    centro X / Y, página, estado de la vista previa y «Reintentar»;
  - arrastre por el centro (con el paso), flechas, teclas + / −, tirador;
  - advertencias: no cabe, se sale y «N bloque(s) sin exportar»; las de traslapes, rosa y
    etiquetas «ESC» funcionan igual que con los detalles;
  - «Volver a cargar» si el DXF cambió (`DXF_CHANGED`) o el trabajador ya no lo tiene
    (`NO_SESSION`); los bloques puestos pasan al DXF nuevo, con su tamaño nuevo.
- **Servidor** (`aplicacion_editor.py`, `servidor.py`, `previa_dxf.py`):
  - `POST /api/previa {ref}`, `GET /api/previas/<id>` (solo PNG dentro de
    `<trabajo>/previews`), `POST /api/dxf/recargar`;
  - dos pedidos del mismo bloque en curso son una tarea; cargar otro DXF cancela las previas en
    cola;
  - la respuesta de `preview` se comprueba (b = c = 0, a = −d, `png` en la carpeta).
- **plano.json versión 3** (`plano_dxf.py`, `plano.py`, `editor_logica.js`): lista `dxf` y
  detalles pendientes con `origen` y `centro_mm`; abrir y guardar sin tocar nada da el mismo
  archivo; las versiones 1 y 2 no cambian.
- **componer** dice qué bloques faltan por exportar (y cuáles no caben) y no compone.
- **Nombres de paquete** (`nombres_paquete.py`): `<file_stem>_1-N`, o recortado con nuestro hash
  antes de la escala si pasa de 60 caracteres (para la etapa 3).
- `componedor.json`: `exportador.cache_previas_mb` opcional (`--preview-cache-mb`).
- La espera de `ready` pasó de 30 s a **60 s**: el exportador real, la primera vez después de
  actualizarlo, tardó más de 30 s en arrancar (compila sus archivos); después, unos 10 s.

**Con el exportador real** (su etapa 2 ya tiene `preview`), GUAMO_prueba.dxf:
- `load` en 3,4 s, 1 bloque (BLOQUE1), escala sugerida 1:5000;
- vista previa en 6–7 s, 1070 × 1500 px, transparente;
- lo dibujado, llevado a CAD con su matriz, cae dentro de la caja de `load`;
- el PNG real trae un borde transparente alrededor de lo dibujado: no estorba, porque se pone
  por su matriz.

**Pruebas**: **1045**, todas pasan (68 nuevas). Nuevas:
- `test_previa_dxf`, `test_plano_v3`, `test_nombres_paquete`, `test_editor_bloques_js`;
- en `test_trabajador`, `test_aplicacion_editor`, `test_servidor`, `test_configuracion`,
  `test_bloques_dxf` y `test_editor_dxf_js`.

Cubren:
- la paridad JS–Python: página, exceso, escala sugerida, lista de escalas;
- que un punto CAD caiga en el mismo lugar del papel por la caja y por el PNG del trabajador
  falso (< medio píxel);
- `preview`, caché, `NO_SESSION` y `DXF_CHANGED`;
- PNG fuera de la carpeta;
- la versión 3 de ida y vuelta y `componer` con pendientes;
- el exportador real con GUAMO.

ruff: los mismos 173 hallazgos de `HEAD`.

**Verificación en Edge** (`data/verificacion/verificar_bloques_dxf.mjs`, fuera de git): todo OK,
53 comprobaciones.
- Agregar y vista previa: el PNG cae en la caja ±1 px.
- Lo dibujado más chico que la caja cae en su lugar por coordenadas CAD.
- Selector: 1:2500 no cabe, queda en rojo con el centro fijo y el PNG al doble.
- Teclas + / −, también las del teclado numérico; no actúan con el foco en «Centro X» ni en el
  selector.
- Tirador hacia adentro y hacia afuera.
- Arrastre con paso de 1 mm y límite del área.
- Versión 3 idéntica al abrir y guardar.
- DXF cambiado → «Volver a cargar».
- Sin servidor, las cajas sin vista previa.
- GUAMO real.
- Sin errores de JavaScript.

**Pendiente**
- Etapa 3: «Exportar» (con `nombres_paquete` e ignorar `.cde-tmp-*` en `localizar_paquetes`).
- Probar el cuadro nativo a mano (sigue de la etapa 1).

### Integración con el exportador — Etapa 3: «Exportar» ✅ (2026-11-18, commit 099055a)

**Qué se hizo**
- **Exportar** (`aplicacion_editor.py`, `exportar_dxf.py`, `POST /api/exportar`):
  - un pedido `export` con un solo trabajo por bloque, en la cola del canal (uno a la vez);
    dos copias del mismo bloque a la misma escala son una sola tarea;
  - salida en `<exportador.paquetes>/<DXF>/<file_stem>_1-N` (por defecto `data/input/dxf/`),
    con `nombres_paquete` (nuestro hash si pasa de 60 caracteres);
  - opciones recomendadas del contrato (`solids: footprint`, `omit_unsupported: true`),
    `overwrite: false`, `write_summary: false`.
- **Caché por paquetes publicados**: si el paquete ya está y es el de este bloque (SHA-256 del
  DXF, handle, escala, margen) y pasa `importar_paquete`, se usa sin exportar.
- **Paquetes viejos**: si en su lugar hay otro, sus archivos se mueven a
  `_para_borrar/paquetes_<fecha>/…` (nunca se borran; `exportador.para_borrar`).
- **Verificación de cada paquete**: `importar_paquete` y que sea el pedido (los mismos cuatro
  datos y una página que no pase de la caja del editor); si no, `PAQUETE_NO_VALIDO`.
- **Colocación por el centro CAD**: posición = centro − (px, alto − py), con (px, py) =
  `cad_to_page` · centro de la caja de `load`. El resultado trae `desde_centro_mm` para cada copia.
- **DXF cambiado**:
  - antes del pedido, el servidor compara tamaño y fecha con los de la carga (la regla §9) y
    responde 409 «vuelva a cargarlo», también para lo que saldría de la caché;
  - si cambia mientras el trabajo espera turno, el trabajador responde `DXF_CHANGED`.
- **Cancelar** (en cola o en curso) y **Detener a la fuerza** (`Canal.detener`,
  `POST /api/trabajador/detener`): cierra el Job sin esperar; lo en curso y lo en cola queda
  cancelado; la sesión se pierde (hay que volver a cargar).
- **`localizar_paquetes`** ignora las carpetas y archivos `.cde-tmp-*`; el editor se genera
  mirando también las subcarpetas de `editor.paquetes` (los exportados aparecen en el catálogo).
- **Editor** (`editor_panel_dxf.js`, `editor_ui.js`, `editor_bloques.js`):
  - «Exportar bloques del plano (N)», con un trabajo por paquete y su barra de avance;
  - Cancelar, «Cancelar todo» y «Detener a la fuerza» (con confirmación);
  - los que no se exportan, con su motivo;
  - cada bloque exportado pasa a ser un detalle normal (su paquete entra al catálogo);
  - `GET /api/exportados` para el editor que se recarga.
- `componedor.json`: `exportador.paquetes` y `exportador.para_borrar`, opcionales.

**Con el exportador real** (su etapa 3 ya tiene `export`), GUAMO_prueba.dxf, BLOQUE1 a 1:5000:
- exportado, verificado por el Componedor y colocado por el centro CAD;
- la segunda vez, de la caché;
- el `export` tardó unos 9,5 min en pytest y unos 6 min en Edge (el contrato estimaba ~94 s):
  observación para el Exportador.

**Pruebas**: **1080** pasan y 1 se salta (la larga con el real: `COMPONEDOR_PRUEBA_LARGA=1`;
corrida aparte, pasa). Nuevas: `test_exportar_dxf`, `test_exportar_editor`,
`test_detalle_exportado`, y en `test_servidor`, `test_configuracion`, `test_editor_bloques_js`,
`test_editor_dxf_js`. El trabajador falso publica paquetes coherentes (pasan `importar_paquete`)
y comprueba lo del contrato (`OUTPUT_EXISTS`, nombres §5.1, margen distinto, `DXF_CHANGED`,
cancelar). Incluye componer un plano con el paquete exportado.

ruff: los mismos 173 hallazgos de `HEAD`.

**Verificación en Edge** (`data/verificacion/verificar_exportar_dxf.mjs`, fuera de git): todo OK.
- Dos trabajos con barra de avance (las dos vigas en uno), el segundo «En espera».
- Los bloques pasan a detalles por el centro CAD.
- Caché y recargar la página.
- Cancelar y detener a la fuerza (0,4 s), con «Volver a cargar».
- DXF cambiado: no exporta ni usa la caché; el paquete viejo va a `_para_borrar`.
- Exportador real con GUAMO.
- Sin errores de JavaScript.

Las de las etapas 1 y 2 siguen todo OK.

**Pendiente**
- Etapa 4: componer desde el editor.
- Probar el cuadro nativo a mano (sigue de la etapa 1).

### Ajustes tras la etapa 3 (2026-11-18, sin commit)

Repositorios reorganizados por Alan: `CDE_Composer` (este) y `CDE_Extractor` (el exportador);
se trabaja en `dev` (commit 8e03b55: reglas de Git en CLAUDE.md).

1. **Escalas** (`inventario.ESCALAS_ESTANDAR` = `editor_bloques.ESCALAS`, con prueba de paridad):
   - Causa: la lista saltaba de 1:2500 a 1:5000. BLOQUE1 de GUAMO no cabe a 1:2500 (sobran
     1,4 mm de alto), así que la sugerida salía 1:5000.
   - La lista nueva tiene 20 escalas: 1:5, 10, 20, 25, 50, 75, 100, 200, 250, 500, 750, 1000,
     1500, 2000, 2500, 3000, 4000, 5000, 7500 y 10000. La sugerida es la primera que cabe: para
     BLOQUE1, 1:3000 (329 × 460 mm).
   - Escala **escrita a mano** («1:3500» o «3500»): entero de 1 a 100000; si no es normalizada,
     aviso «escala no normalizada»; + y − pasan a la vecina de la lista; se guarda tal cual en
     la versión 3; la usan el paquete (`_1-3500`), la caché y el rótulo.
   - **Ajustar a la hoja**: la escala exacta más grande que cabe (BLOQUE1: 1:2507).
   - En la versión 3 la escala debe ser entera (antes se admitían decimales, que el editor nunca
     escribía).
2. **Rótulo con «342,55» y «297,00»**:
   - Causa: la **restauración de formularios del navegador**. Al volver a la página (atrás en el
     historial) pone los valores guardados en los cuadros por orden, y los de «Centro X / Y» del
     bloque seleccionado caían en «No. PLANO» y «HOJA», sin avisar al editor: se veían, pero no
     estaban en el modelo.
   - Corrección: `editor_sin_autorrelleno.js` (se carga primero) pone `autocomplete="off"` en
     todos los cuadros, también en los que se crean después.
   - De paso, las flechas con un bloque seleccionado daban un error de JavaScript: arreglado.
3. **Errores claros** (`mensajes_trabajador.py`):
   - `INTERNAL`, `DXF_INVALID` y los errores por trabajo de `export` muestran un mensaje para el
     usuario; el texto técnico y la ruta del registro van en «Ver detalle»;
   - sin «Repita el pedido» cuando el error es determinista.
4. **Paquetes viejos**:
   - el trabajador publica en una carpeta de preparación (`.componedor-nuevo-<n>`);
   - el viejo se mueve a `_para_borrar/` solo después de publicar y verificar el nuevo;
   - si se cancela o falla, el viejo queda donde estaba.
5. **Tiempo**:
   - BLOQUE1 a 1:3000 con el exportador real y el equipo en reposo: `export` 182,7 s (el
     Exportador midió 166 s). Por etapa: extract 53,1 · analyze 48,1 · draw 3,0 · pdf 67,2 ·
     checks 11,2 · publish 0,1 s.
   - `load`: 13,1 s (lectura 3,7 s); arranque del trabajador: 5,7 s.
   - Los 9,5 min del día anterior: un ensayo propio colgado desde el 17-11 gastaba CPU
     (detenido) y corrían pruebas a la vez.
6. **Documento para Alan**: [instalacion_y_uso.md](instalacion_y_uso.md).

**Pruebas**: **1101** pasan y 1 se salta (la larga con el real). ruff: los mismos 173 hallazgos.
Verificación en Edge todo OK:
- `verificar_rotulo_bloques.mjs` (nuevo): el rótulo no cambia por acciones sobre un bloque ni
  al volver atrás; «Ver detalle»;
- las de las etapas 1, 2 y 3 (con el exportador real), ajustadas a la lista nueva.

### Bloques anónimos en la carpeta del DXF (2026-11-18, sin commit)

El Exportador ofrece en `load` los `*U` del Model Space que dibujan muchas entidades (mesas de
PVcase, tablas de Civil 3D), con `anonymous`, `label` (capa + handle del INSERT, que es el nombre
que se muestra y el del paquete) y `visible_entities`; los pequeños van a `omitted` con
`anonymous: true`.

Decisiones del usuario (2026-11-18):
1. el umbral lo manda el Componedor en `load` (`anonymous_min_entities`), configurable en
   `componedor.json` → `exportador.anonimos_min_entidades` (100 por defecto);
2. «Ver vista previa» en cada tarjeta;
3. sin el campo `origin`.

**Qué se hizo**
- **Configuración** (`configuracion.py`, `componedor.json`): `exportador.anonimos_min_entidades`,
  entero ≥ 1, 100 por defecto. `aplicacion_editor` lo manda en `load` como
  `anonymous_min_entities`.
- **Carpeta** (`bloques_dxf.py`): cada bloque lleva `anonimo`, `etiqueta` (= `label`, o el nombre
  si falta) y `entidades_visibles`. Los anónimos de `omitted` no se listan (pueden ser miles: en
  Plano_completo, 3 318): solo `anonimos_omitidos` = {cantidad, máximo de entidades visibles}.
  `anonimos_min_entidades` va en la carpeta para explicarlo.
- **Editor**:
  - `editor_dxf.js` (lógica pura): `nombreBloque`, `separarBloques`, `filtrarBloques` (todas las
    palabras, en etiqueta, `*U`, capa o handle, sin mayúsculas ni tildes), `textosAnonimos` y la
    línea del anónimo («bloque anónimo *U76 · 1 250 entidades visibles»); el resumen dice
    «3 bloques · 4 anónimos».
  - `editor_panel_dxf.js`: subsección **«Anónimos (opcionales) (N)»**, cerrada por defecto, con
    la explicación, cuántos pequeños no se ofrecen, el filtro y las tarjetas (hasta 200 a la
    vez). Abierta/cerrada y el filtro se conservan al repintar, y el filtro no pierde el foco
    con el avance de una exportación.
  - **Ver vista previa** en cada tarjeta (también las de bloques con nombre): la misma vista
    previa que después usa la caja en la hoja (misma caché por sha256 + handle), en pequeño;
    «Ocultar vista previa» la quita.
  - `editor_ui.js`: Propiedades y mensajes muestran la etiqueta («bloque «I1.M1.PV1_12900»» y
    «anónimo *U76 · handle 12900»). El plano.json no la guarda (guarda el `*U` y el handle, como
    antes): al abrir un plano se toma de la carpeta cargada por el handle.
  - Agregar, escalar y exportar: sin cambios, como cualquier bloque; el paquete se llama como la
    etiqueta (`I1.M1.PV1_12900_1-50`) y el manifiesto guarda el `*U`.
- **Trabajador falso**: bloques con `"anonimo": true` y `visible_entities`; aplica
  `anonymous_min_entities` (BAD_REQUEST si no es entero ≥ 1); todos los bloques traen
  `anonymous`, `label` y `visible_entities`.
- Documentación: `editor.md` §2f, `servidor_editor.md`, README.

**Con el Exportador en 92c2c37** («Fase 4b: bloques anónimos *U»):
- `load` lee `anonymous_min_entities` (manda sobre `CDE_ANON_MIN_ENTITIES`) y devuelve el umbral
  usado; la carpeta muestra ese (el de la configuración queda de respaldo). El Exportador admite
  0; nuestra configuración pide ≥ 1 a propósito (con 0 se ofrecerían todos los `*U`, a miles).
- `preview` y `export` aceptan **solo `handle`**, porque el `ref` de un `*U` cambia entre
  sesiones. Antes, el servidor traducía el handle del editor al `ref` de la sesión y mandaba
  `ref` (no fallaba, porque el `ref` salía de la carpeta vigente). Ahora `previa_dxf.pedido_previa`
  y los `jobs` de `export` llevan el `handle` solo. El trabajador falso lo acepta igual que el real
  (sin distinguir mayúsculas; NOT_EXPORTABLE, REFERENCE_NOT_FOUND, BAD_REQUEST si está repetido) y
  devuelve el umbral usado. Prueba nueva: un `*U76` que pasa a `*U80` al guardar se sigue
  previsualizando y exportando por su handle, y el paquete se llama igual.
- **Ensayo con el real**, PRGD-26-1377-GEN-PL-101_1_V0.dxf (158 MB), por `AplicacionEditor`:
  - umbral 100: `load` en 16 s y la respuesta trae `anonymous_min_entities: 100`; **3 de 3**
    anónimos (las mesas `I1.M1.PV1_12900`, `I1.M1.PV2_12962` e `I1.M2.PV4_129C4`, `*U76/78/80`,
    312 entidades visibles cada una, 34,88 × 7,23 m, sugerida 1:75);
  - umbral 300: lo devuelve y siguen las 3 (312 ≥ 300). Con 313: 0 ofrecidos y 3 pequeños
    contados (máximo 312), lo que muestra que el umbral sí filtra;
  - vista previa de `I1.M1.PV1_12900` pedida con `{"handle": "12900"}`: 1500 × 327 px en 0,5 s;
  - exportación a 1:75 con `{"handle": "12900"}`: paquete `I1.M1.PV1_12900_1-75` en 1,5 s,
    verificado por el Componedor (página 475,04 × 106,38 mm, cabe) y puesto por el centro CAD;
    el manifiesto guarda `*U76`, el handle 12900 y la escala física garantizada.
  - Hallazgo: en una carpeta de salida muy profunda, la exportación falla con «No such file or
    directory». La ruta del temporal del Exportador (`.componedor-nuevo-1\.cde-tmp-…\
    .<paquete>.<32 hex>.tmp.dxf`) pasa de 260 caracteres (límite de rutas de Windows). Con
    `data/input/dxf/` queda en unos 190, sin problema. Para el Exportador: dar un mensaje claro
    o acortar sus temporales.

**Pruebas**: **1131** pasan y 1 se salta (la larga con el real). Nuevas: el umbral en la
configuración (válidos e inválidos), la carpeta con anónimos (etiqueta, campos raros, 3 318
pequeños contados y no listados), el umbral de punta a punta con el falso (100, 50 y 300),
exportar un anónimo (paquete con la etiqueta, caché) y en Node los textos, la separación y el
filtro. ruff: los mismos 173 hallazgos.

**Verificación en Edge** (`data/verificacion/verificar_anonimos.mjs`, fuera de git, trabajador
falso): todo OK.
- Subsección cerrada con sus tarjetas ocultas; «Otros 3 anónimos más pequeños…»; «No
  exportables» sin los `*U` pequeños.
- Filtro: «pv1», «pv1 m2», «CALCULO», «12a00», sin coincidencias; conserva el foco.
- «Ver vista previa»: «Pidiendo vista previa…», la imagen como `blob:` (alto ≤ 180 px),
  ocultar y volver a ver.
- Agregar a 1:20, escalar a 1:50 con el centro fijo, guardar y reabrir la versión 3 (igual y
  nombrado por la etiqueta).
- Exportar dos anónimos: `I1.M1.PV1_12900_1-50` y `C-TABLAS_2F10_1-20`, puestos por el centro
  CAD y en «Detalles disponibles».
- Sin errores de JavaScript.

`verificar_bloques_dxf.mjs` se ajustó (cada tarjeta tiene ahora dos botones); las de las etapas
1, 2 y 3 siguen todo OK con el falso.

### Ortofoto de fondo — Etapa 1: cargar, ficha y vista previa (2026-11-18, aprobada; sin commit)

Decisiones del usuario (2026-11-18):
1. una ortofoto por plano, detrás de todos los detalles y recortada a la caja de cada uno;
   fuera de los detalles, en blanco;
2. reproyectar, y si un sistema no se puede determinar, no suponer: aviso amarillo y selector;
3. en el PDF, 300 ppp y JPEG calidad 85, configurables;
4. una copia reducida (etapa 2);
5. opacidad por plano, 100 % por defecto;
6. sin GEODATA, el selector;
7. funcionar con BigTIFF de varios GB, leyendo por ventanas;
8. rasterio.

**Instalación**: `rasterio>=1.4,<2` en el `.venv` (quedó la 1.5.2 con GDAL 3.12.2, numpy 2.5.5,
affine, attrs, certifi, click y pyparsing: 7 paquetes nuevos, ninguno existente cambió; 150 MB).
Agregada a `pyproject.toml`; `pip check` sin problemas.

**Hallazgo**: el Exportador no informaba el sistema del DXF (`load` y el manifiesto no lo
traían). Por eso el sistema del dibujo lo elegía el usuario siempre. (Ya lo informa desde su
58fc279: ver la etapa 2.) **Para el Exportador**: que `load`
devuelva el sistema del DXF (de `GEODATA`). Ojo: el `GEODATA` de PRGD dice «CTM12», pero trae
la autoridad 3115, así que el selector debe dejar corregirlo igual.

**Qué se hizo**
- `ortofoto.py`: lee solo la cabecera con rasterio y arma la ficha con sus avisos («error»,
  «elegir», «aviso»).
  - Un archivo sin georreferencia se rechaza.
  - El sistema sale del archivo o queda en `null`, sin suponer.
  - Avisa si está girada, si le faltan pirámides o mosaicos en archivos grandes, si tiene más
    de 3 bandas o si no es de 8 bits.
  - `leer_sistema("EPSG:n")` acepta solo sistemas proyectados. `SISTEMAS_COMUNES` (Colombia)
    son los del selector.
- `previa_ortofoto.py`: el PNG RGBA de una caja CAD.
  - La caja se lleva al sistema de la ortofoto y se lee solo esa ventana, reducida con
    `out_shape`, que usa las pirámides.
  - Se reproyecta con `reproject`: bilineal para la imagen y vecino más cercano para la máscara.
    La máscara va como 1 (sin foto) y 2 (con foto), porque GDAL cambia los 0 de la fuente.
  - Lo que no tiene foto queda transparente: fuera de la imagen, alfa, «nodata» o máscara.
  - Paleta, gris, 16 bits (brillo 2–98 % calculado una vez para toda la ortofoto, el mismo en
    todos los detalles) y girada.
  - Devuelve también la cobertura.
- `ortofoto_editor.py` (servidor, sin HTTP):
  - elegir con el cuadro nativo (`dialogo_dxf --tipo ortofoto`), estado y quitar;
  - la vista previa se hace en el mismo pedido, de a una, y se guardan las últimas 64;
  - detecta que el archivo cambió en el disco y responde 409.

  Rutas `/api/ortofoto…` con los mismos controles (token, Host, Origin). No usa el trabajador y
  funciona sin la sección `exportador`.
- `componedor.json` → `ortofoto: {ppp: 300, calidad_jpeg: 85}` (`leer_config_ortofoto`). Se lee
  y valida; se usará en la etapa 2.
- plano.json **versión 4** (`plano_ortofoto.py`): `ortofoto: {archivo, bytes, crs, crs_dibujo,
  opacidad}`. `componer` la valida y por ahora compone sin ella, con una advertencia.
- Catálogo del editor: cada detalle trae `cad_a_pagina` (la matriz del manifiesto) y
  `mm_por_unidad`, para saber qué caja CAD cubre su página.
- Editor:
  - `editor_ortofoto.js` es la lógica pura: caja CAD de un detalle exportado (inversa de
    `cad_to_page`) o de un bloque (inversa de `cadAPapel`), ficha, avisos y versión 4.
  - `editor_panel_ortofoto.js`: botón «Cargar ortofoto», panel «Ortofoto», selectores
    («Otro (código EPSG)…»), opacidad, estado por detalle y quitar. Pide las vistas previas
    250 ms después del último cambio, para no pedir una por cada paso del tirador.
  - En la hoja, la capa `capa-ortofoto` va debajo de los detalles, con una imagen exactamente
    sobre la página de cada uno.

**Pruebas**: 1208 pasan y 1 se salta (antes 1131). ruff igual que antes (173).
- `tests/ortofoto_sintetica.py` crea GeoTIFF sintéticos con rasterio: cada píxel dice su
  columna y su fila.
- `test_ortofoto` (11): ficha de cada variante.
  - Mosaicos LZW y JPEG, pirámides, BigTIFF.
  - Sin sistema, sin georreferencia, girada.
  - Gris, 16 bits, RGBA, «nodata», paleta, 5 bandas.
  - Grande sin pirámides; sistemas; `Foto_tunez.tif`.
- `test_previa_ortofoto` (12):
  - cada píxel cae donde va;
  - reducida con pirámides y ampliada;
  - a medias y fuera;
  - reproyección 9377 → 3116;
  - sistema elegido o propio, dibujo en mm;
  - transparencias, paleta, 16 bits con el mismo brillo en dos cajas;
  - girada 90°, BigTIFF con JPEG y pirámides;
  - `Foto_tunez.tif` (cubierta toda y 25 % en la esquina).
- `test_ortofoto_editor` (17), `test_plano_v4` (13), `test_editor_ortofoto_js` (11, Node contra
  Python).
- Además: servidor (2), cuadro (2), configuración (9), el detalle exportado trae la matriz, y
  dos pruebas ajustadas por la versión 4.

**Verificación en Edge** (`data/verificacion/verificar_ortofoto.mjs`, todo OK):
- **A. Trabajador falso + GeoTIFF sintético sin sistema**:
  - dos avisos amarillos y dos selectores; sin sistemas no se dibuja nada;
  - con EPSG:3116 en los dos, la imagen cubre exactamente la página de BLOQUE1 (cubierta
    97,9 %);
  - plano versión 4 con `crs` y `crs_dibujo`.
- **B. Exportador real + PRGD + `Foto_tunez.tif`**:
  - la ficha dice EPSG:9377 y solo pide el sistema del dibujo;
  - con 9377, la ortofoto cae en «via tunez»: caja CAD con el mismo centro que el bloque, que
    contiene la del bloque más 2,5 m por lado (5 mm a 1:500), cubierta 100 %;
  - la mesa `I1.M1.PV1_12900`, al este de la foto, «no cubre este detalle» y no dibuja nada;
  - la capa va debajo de los detalles; opacidad al 60 %; a 1:1000 la caja crece 2,5 m por lado;
  - el plano.json lo lee Python y la ruta lleva al archivo;
  - al recargar la página, «Usar en este plano»; al abrir el plano vuelven el sistema, la
    opacidad y la imagen; abrir y guardar da el mismo JSON;
  - «Quitar ortofoto».
- **C. Sin servidor (file://)**: el botón está desactivado, el panel dice qué ortofoto usa el
  plano y la conserva al guardar.
- Sin errores de JavaScript. Capturas en `data/verificacion/ortofoto_salida/`.

### Ortofoto de fondo — Etapa 2: la ortofoto en el PDF y la copia reducida (2026-11-18, sin commit)

Decisiones del usuario (2026-11-18), al aprobar la etapa 1:
1. empezar la etapa 2;
2. sin excepciones a la regla de seguridad: «Cargar ortofoto» abre el cuadro en la carpeta
   guardada en el plano y avisa si lo elegido no coincide en nombre, tamaño o fecha;
3. el Exportador agrega `dxf.crs` en `load`: el selector sale prellenado y siempre editable;
   sin él, vacío como antes.

**Qué se hizo**
- `ortofoto_render.py` (nuevo) es el pintado común a la vista previa, el PDF y la copia.
  - Lee solo la ventana de la caja, reducida con `out_shape` (usa las pirámides).
  - Para el PDF y la copia, la reducción es un **factor entero** para todo el detalle y la
    ventana se alinea a múltiplos de él: dos mosaicos vecinos leen la misma grilla y no hay
    costuras. Probado: pintar la caja en dos mitades da lo mismo que entera (diferencia ≤ 1 de
    255), también reproyectando.
  - `previa_ortofoto.py` pasa a usarlo, sin cambiar lo que hace.
- `ortofoto_pdf.py` (nuevo), para cada detalle:
  - su página en la hoja → CAD con la inversa de su `cad_to_page`;
  - una cuadrícula a `ppp` en mosaicos de 1024 px, cada uno JPEG (`calidad_jpeg`) con
    `insert_image`, que entra tal cual (DCTDecode);
  - la máscara (SMask) va donde no hay foto o con opacidad menor que 1; un mosaico sin foto no
    se pone;
  - avisos: no cubre el detalle, el detalle tiene fondo blanco (la tapa), dibujo girado;
  - `verificar_ortofoto`: en el PDF guardado, cada mosaico es un JPEG justo en su rectángulo
    (±0,1 mm).
- `ortofoto_copia.py` (nuevo): la copia reducida en `<plano>_ortofoto/`.
  - Un GeoTIFF por detalle, ya en el sistema del dibujo: la página más 10 % por lado.
  - Resolución: la del PDF, pero nunca más fina que la ortofoto original.
  - JPEG en mosaicos de 512 px, con máscara interna, escrito por mosaicos.
  - `indice.json` con el original (nombre, bytes, fecha), el sistema y las cajas.
  - Si está al día no se reescribe; si cambió, se escribe aparte y reemplaza a la vieja (es un
    archivo generado, como el PDF: la vieja se borra, no pasa por `_para_borrar`).
- `ortofoto_fuente.py` (nuevo) decide de dónde sale la ortofoto:
  - el original si existe y coincide (bytes y fecha que guardó el plano);
  - si no, la copia, con advertencia;
  - si tampoco, error claro, igual que sin `crs_dibujo` o con una ortofoto sin sistema y sin
    `crs`.
- `componer`:
  - orden plantilla (rosa, símbolos) → ortofoto → detalles → rótulo;
  - la verificación cuenta las imágenes: plantilla + firmas + mosaicos;
  - con el original, escribe la copia al final (si falla, advertencia: el PDF ya está);
  - `componer_plano(..., config_ortofoto)`, y el CLI con `--config` lee `ortofoto.ppp` y
    `calidad_jpeg`. El resumen dice los mosaicos, el ppp, los MB, la cobertura de cada detalle
    y la copia.
- plano.json versión 4: `ortofoto.modificado` (fecha UTC al segundo), en Python y en el editor.
- Editor:
  - **«Cargar ortofoto»** manda la ruta del plano solo para abrir el cuadro en esa carpeta (el
    servidor no lee nada con ella).
  - Si lo elegido **no coincide** (nombre, tamaño o fecha), el plano no cambia: el panel lista
    qué difiere y ofrece «Usar la cargada en el plano».
  - **`dxf.crs`**: `sistema_dxf.py` (nuevo) lee el objeto del Exportador. El selector «Sistema
    del dibujo» sale prellenado con el código (una vez por DXF y ortofoto; siempre editable;
    vacío si no viene o no sirve). Además se compara la zona del nombre del GEODATA con la del
    código.

**Hallazgo con el Exportador real (58fc279)**: ya manda `dxf.crs`. Para PRGD trae
`name: "Colombia CTM12"`, `epsg: 3115` (de `authority`). 3115 es Colombia West zone; CTM12 es
EPSG:9377. Con 3115 la ortofoto cae a cientos de km y no cubre nada. Por eso, cuando nombre y
código no coinciden:
- sale un **aviso amarillo** que lo explica;
- y un botón **«Usar EPSG:9377 para el dibujo»**.

Ajuste del usuario al aprobar la etapa 2: el selector se preselecciona solo si el código salió
de un `Alias` del GEODATA (`epsg_from: "alias"`); si salió de la autoridad (`"authority"`, como
en PRGD), queda vacío. El aviso amarillo y el botón se mantienen. Edge: 70 comprobaciones, todo
OK.

**Pruebas**: 1264 pasan y 1 se salta (antes 1208). ruff igual que antes (173).
- `test_ortofoto_render` (7): factor entero, ventana alineada, mosaicos sin costuras (con y sin
  reproyección), sin sistema, fuera.
- `test_ortofoto_pdf` (7):
  - cuadrícula exacta y caja CAD de ida y vuelta;
  - **la foto cae donde predice el CAD**: cada píxel del JPEG del PDF, comparado con la
    ortofoto muestreada aparte (bilineal propia, sin el código del Componedor) en el punto CAD
    de ese píxel, da un error medio de 1,1 / 255; corrida 1 mm, más de 8 veces mayor;
  - máscara y opacidad, mosaicos vacíos, girado y fondo, un mosaico que falta.
- `test_componer_ortofoto` (11):
  - mismos trazos y textos que sin ortofoto, y el orden plantilla → JPEG → detalle;
  - la copia (y «al día»), y sin el original o con el original cambiado, la copia con aviso;
  - sin nada que sirva, copia de otro sistema, sin `crs_dibujo`, ortofoto sin sistema;
  - opacidad con paquete con fondo; las diferencias; el resumen del CLI.
- `test_ortofoto_copia` (2), `test_sistema_dxf` (23, con los `dxf.crs` reales de PRGD y GUAMO),
  y más casos en `test_bloques_dxf`, `test_ortofoto_editor`, `test_editor_ortofoto_js` y
  `test_plano_v4`.

**Verificación con PRGD** (`data/verificacion/verificar_ortofoto_pdf.py`; «via tunez» a 1:500 y
la mesa I1.M1.PV1_12900 a 1:75; cada caso en un proceso aparte para medir su pico de memoria):

| | sin ortofoto | `Foto_tunez.tif` (3,3 MB) | BigTIFF sintético de 3,0 GB (32 768² px, 4 cm, sin pirámides ni compresión) |
|---|---|---|---|
| tiempo de componer | 8,2 s | 11,7 s | 15,8 s (21,7 s escribiendo la copia) |
| pico de memoria | 226 MB | 322 MB | 332 MB |
| PDF | 2,35 MB | 3,16 MB | 9,55 MB |
| JPEG de la ortofoto | — | 0,8 MB, 36 mosaicos | 7,2 MB, 36 mosaicos |
| copia reducida | — | 0,03 MB (a 1,08 m: la de la foto) | 6,9 MB (a 4,2 cm: la del PDF) |
| trazos / textos | 9369 | 9369, iguales | 9369, iguales |
| imágenes | 1 (logo) | 1 + 36 JPEG | 1 + 36 JPEG |
| error de posición (0–255) | — | 0,41 (corrida 1 m: 3,59) | 1,50 (corrida 1 m: 61,5) |

- «via tunez»: 5278 × 5401 px, cubierto al 100 %. La mesa queda fuera de la foto: no lleva
  mosaicos y avisa.
- Con 3 GB la memoria es la misma que con 3 MB: se lee por ventanas.
- `Foto_tunez.tif` tiene píxeles de 1,08 m, que a 1:500 son 2,2 mm de papel (unos 12 ppp). A
  300 ppp se agranda 25 veces: se ve suave, no pixelada, y pesa poco, porque el JPEG de una
  imagen suave es chico. La copia queda a la resolución de la foto.

**Verificación en Edge** (`verificar_ortofoto.mjs`, 69 comprobaciones, todo OK):
- **falso con `dxf.crs` EPSG:3116**: el selector sale prellenado con aviso azul; si se cambia,
  avisa que no es el del DXF;
- **real**: EPSG:3115 prellenado, el aviso amarillo de CTM12 y «Usar EPSG:9377»;
- **plano con tamaño y fecha distintos**: dice qué difiere y no dibuja. «Cargar ortofoto» abre
  el cuadro en `data/input/ortofotos` y no cambia el plano. «Usar la cargada en el plano» toma
  tamaño y fecha y conserva sistema y opacidad;
- todo lo de la etapa 1 sigue igual.

### Ortofoto por detalle — Etapa A (2026-11-19, sin commit)

Plan aprobado por el usuario (2026-11-19): la ortofoto se elige **por detalle**; en la etapa B,
«Extender a todo el layout» (con un solo bloque con ortofoto, al área de dibujo, mismo mapeo
CAD→papel; los bloques sin ortofoto con fondo blanco de su página) y la cuadrícula de
coordenadas (vectorial, debajo de los vectores, en la página del bloque, estilo leído del DXF de
PRGD, también sin cobertura). Etapa A, ya hecha:

- **plano.json versión 5**: `"ortofoto": true` en cada detalle (exportado o pendiente) que la
  lleva detrás; sin la clave, `false`. Con la marca y sin la sección `ortofoto`: error. Una
  versión 4 con ortofoto se lee con todos los detalles marcados (en Python y en el editor), que
  es lo que hacía; el editor lo avisa y guarda en versión 5.
- **`componer`**: la ortofoto, la copia reducida y la verificación, solo con los detalles
  marcados. Si ninguno lo está: sin ortofoto, con advertencia, y no hace falta el archivo.
- **Editor**:
  - casilla **«Usar ortofoto»** en Selección (detalle y bloque), desactivada sin ortofoto
    cargada;
  - la capa y el estado del panel, solo con los marcados; el panel avisa si no hay ninguno;
  - al exportar un bloque, el detalle nuevo conserva la marca.

**Pruebas**: 1274 pasan y 1 se salta (antes 1264). ruff igual que antes (173).
- `test_plano_v4` (+7): versión 5, migración de la 4, errores, pendiente con marca en la 4.
- `test_componer_ortofoto` (+2): solo los marcados llevan mosaicos y copia; ninguno marcado,
  sin archivo.
- `test_editor_ortofoto_js`: versión 5 de ida y vuelta (Python la lee), bloque sin exportar,
  abrir y guardar igual, migración de la 4 y errores.

**Verificación en Edge** (`verificar_ortofoto.mjs`, 88 comprobaciones, todo OK):
- **A y B**: sin marcar, nada; marcada la casilla, la ortofoto detrás de ese detalle solo. La
  mesa de PRGD sin marcar no la lleva y su casilla sigue sin marcar. El plano guarda las
  marcas y Python las lee.
- **D**: `foto_google_sat.tif` (EPSG:32618) con PRGD: se reproyecta y queda solo detrás de «via
  tunez», exactamente sobre su página. Abrir esa misma composición como versión 4 avisa la
  migración y deja los dos marcados; al guardar, versión 5.
- **PDF con PRGD y Google, versión 5** («via tunez» marcada, la mesa no): 36 mosaicos, todos de
  «via tunez»; 16,8 s, 332 MB de pico, PDF de 4,6 MB, los mismos 9369 trazos.

### Ortofoto: extender a todo el layout y cuadrícula — Etapa B (2026-11-19, sin commit)

La etapa A tiene commit en dev: 78fa64313d80cc29bb8fdd1455b4aa8954aefea5 («Fase 5b: ortofoto por
detalle (plano.json v5)»).

**Estilo de la cuadrícula**: el DXF de PRGD no trae ninguna (no hay textos de coordenadas; las
capas «GRID» son de perfiles de Civil 3D, vacías). Se copió del PDF del plano de AutoCAD
(`data/input/PRGD-26-1377-GEN-PL-101_1_V0.pdf`, leído con PyMuPDF; página girada 270°):
- 12 líneas negras de 0,085 mm, continuas, que cruzan toda el área de dibujo, cada 50 m;
- 24 etiquetas en ArialMT de 10 pt (cifras de 2,53 mm), negras, formato «4705900.000» (3
  decimales, sin letras). Hay una en cada extremo de cada línea, centradas en la franja de 10 mm
  entre el marco y el área de dibujo y en su línea. El Este va abajo (Y 15,5 a 19,1) y arriba; el
  Norte, girado, a la izquierda (X 16,2 a 19,7) y a la derecha (X 666,1 a 669,6), y se lee de
  abajo hacia arriba;
- sin fondo ni halo. Una prueba reproduce esas posiciones con ±0,2 mm.

**Qué se hizo**
- `cuadricula.py` (nuevo): valores, líneas en la región y etiquetas en la franja de afuera, con
  la fuente del rótulo (embebida una sola vez; ToUnicode corregido con todo).
  - Se omite una etiqueta que se salga del marco o choque con el rótulo, otro detalle, la rosa,
    una etiqueta ESC u otra etiqueta (con aviso).
  - Avisa si las líneas quedan a menos de 15 mm, si no cae ninguna o si serían más de 400.
  - `verificar`: cada etiqueta se lee en el PDF guardado.
- Modo extendido: la región de la ortofoto (y de la copia reducida) es el área de dibujo, con el
  mapeo del único detalle con ortofoto. Con otro número de detalles, advertencia y recortadas.
- `componer`, orden: plantilla → ortofoto → cuadrícula → rosa otra vez (si la foto la tapa) →
  fondos blancos (extendida) → detalles → textos. Los trazos de la base se vuelven a contar
  antes de poner los detalles, y la verificación de cada detalle sigue igual.
- plano.json versión 5: `ortofoto.extender` y `ortofoto.cuadricula {visible, intervalo_m}`.
  `componedor.json` → `ortofoto.cuadricula_intervalo_m` (50). El editor recibe `marco_mm`, y el
  servidor, el intervalo por defecto.
- Editor:
  - capas ortofoto → cuadrícula → rosa → detalles;
  - «Extender a todo el layout» (solo con un detalle marcado) y fondo blanco para los demás;
  - «Cuadrícula de coordenadas» con su intervalo y el resumen en el panel;
  - la misma geometría que Python (`editor_ortofoto.cuadricula`, comparada en las pruebas).

**Pruebas**: 1299 pasan y 1 se salta (antes 1274). ruff igual que antes (173).
- `test_cuadricula` (7, con las posiciones de PRGD);
- más casos en `test_componer_ortofoto` (extendida con el mismo mapeo y fondo blanco; con dos no
  vale; cuadrícula en el PDF; sin cobertura), `test_plano_v4`, `test_configuracion` y
  `test_editor_ortofoto_js` (la cuadrícula del editor igual a la de Python en 4 casos).

**Verificación en Edge** (`verificar_ortofoto.mjs`, 106 comprobaciones, todo OK), fase E con
PRGD y `foto_google_sat.tif`:
- «Extender» solo con un detalle marcado; la foto cubre el área con el mismo mapeo (0,5 m de CAD
  por mm, igual que en su página); la página no se mueve; la mesa con fondo blanco;
- cuadrícula cada 50 m (7 + 6 líneas): etiquetas fuera del área, dentro del marco, formato
  «4705900.000»; a 25 m, 24 líneas; el plano lo guarda;
- al marcar otra vez la mesa, «Extender» desaparece y la foto vuelve a su página.

El script ahora cierra los procesos de Edge que quedaban sueltos y bloqueaban la carpeta de
capturas.

**PDF extendido con PRGD y Google** (`data/verificacion/ortofoto_pdf/extendido.pdf`):
- 56 mosaicos (4,1 MB) sobre toda el área de dibujo; los 20 que quedan fuera de la página de «via
  tunez» caen donde predice su CAD (error medio 0,74 / 255);
- cuadrícula cada 50 m: 7 + 6 líneas y 26 etiquetas, todas legibles en el PDF;
- 19,8 s, 390 MB de pico, PDF de 6,5 MB, copia reducida de 1,4 MB.

### Imagen de localización en el rótulo — Fase 6 ✅ (2026-11-19)

El commit de documentación 3617179 («Docs: contrato de paquete, manifiesto 1.4 probado») está en
dev, sin push.

**Decisiones del usuario**: la imagen va entera y centrada, sin deformar, con bandas blancas
donde sobre. «ESC:», Este y Norte se escriben a mano; mientras «ESC:» esté vacía hay aviso (sale
«DEFINIR»). Un PNG se reduce a ~300 ppp sin pérdida (nunca se agranda) y un JPG va tal cual.
Hay una copia junto al plano (`<plano>_localizacion.<ext>`), que se usa si el original se mueve.
Los `.pgw` / `.jgw` se ignoran por ahora.

**Qué se hizo**
- Formato: campo del rótulo de tipo `"imagen"` (`rotulo_formato.CampoImagen`: `rect_mm`, `ppp`,
  `campo_escala`). En `A1_ERCO.json`, `localizacion_imagen` va en X 673,4 a 827,3, Y 455,8 a
  570,2 mm (medido en la plantilla: entre el título «LOCALIZACIÓN» y la fila de «ESC:»). Se
  revisa que no se monte sobre otra celda.
- `localizacion.py` (nuevo):
  - lee `rotulo.localizacion_imagen` `{archivo, bytes, modificado}`;
  - elige entre el original y la copia, y deja la copia;
  - ajusta la imagen (`contener`) y reduce el PNG;
  - la inserta debajo de los textos;
  - `verificar`: posición ±0,1 mm, píxeles y DCTDecode para el JPG.
- `componer`: la imagen va antes de los textos del rótulo y la verificación cuenta una imagen
  más. `cli` muestra una línea «Imagen de localización…» y la menciona en la verificación.
- Servidor:
  - `localizacion_editor.py` (nuevo);
  - `/api/localizacion`, `/elegir`, `/imagen` y `/quitar`;
  - cuadro nativo `elegir_localizacion` en `dialogo_dxf.py`.
- Editor:
  - `editor_localizacion.js` (lógica pura: `contener`, `enElPdf`, diferencias, ficha);
  - `editor_panel_localizacion.js` (panel bajo el Rótulo);
  - capa `capa-localizacion` en el lienzo;
  - el aviso de «ESC:» vacía se actualiza al escribir en el Rótulo.

**Pruebas**: 1319 pasan y 1 se salta (antes 1299). ruff igual que antes (173).
- `test_localizacion` (15), con PNG sintéticos y JPG:
  - `contener`;
  - el recuadro de A1 no tapa ESC ni las coordenadas;
  - valores mal escritos;
  - un PNG de 3000 × 2000 se reduce a 1818 × 1212 (~300 ppp);
  - un PNG chico no se agranda y un JPG va tal cual;
  - si el original se mueve, se usa la copia (con aviso), y sin copia hay error;
  - aviso de escala vacía;
  - PDF con PNG y JPG (posición, DCT, debajo de los textos);
  - sale «DEFINIR».
- `test_localizacion_editor` (5): estado, imágenes que no sirven, HTTP con token y origen, y
  `contener` y `enElPdf` iguales en JS y Python.

**Verificación en Edge** (`data/verificacion/verificar_localizacion.mjs`, 19 comprobaciones,
todo OK). Con PRGD (Exportador real) y `loc_google.jpg` (1600 × 1200, recortada de la foto de
Google; en `data\` no había una imagen real de QGIS):
- la ficha dice «JPEG · 1600 × 1200 px, 152,5 × 114,4 mm, 266 ppp, va tal cual»;
- la imagen queda en el rectángulo de `contener`, 4:3 en mm;
- el aviso de «ESC:» desaparece al escribir 1:10000;
- el plano guarda `localizacion_imagen` (sin la imagen dentro) y la escala;
- con un plano que no coincide: recuadro punteado, el cuadro se abre en la carpeta del plano, el
  plano no cambia, y «Usar la cargada en el plano» lo corrige;
- «Quitar» funciona;
- sin errores de JavaScript.

**PDF con PRGD** (`data/verificacion/v14/plano_loc_jpg.pdf` y `plano_loc_png.pdf`, con la
ortofoto, la cuadrícula y los dos detalles):
- JPG 1600 × 1200 tal cual (DCT) a 266 ppp, en X 674,1 a 826,6 mm, con «ESC: 1:10000»;
- PNG sintético 3000 × 2000 reducido a 1818 × 1212 (300 ppp), con aviso de «DEFINIR»;
- verificación OK; copias `plano_loc_*_localizacion.*` junto al plano.

### Estilo de impresión al exportar: CTB y transparencia — Fase 7 ✅ (2026-11-21)

Usa las opciones del Exportador `plot_style` y `print_transparency` (manifiesto 1.4, commit
7154704; CTB derivada de PRGD en e8422a4).

**Decisiones del usuario**
1. La CTB se lee de la carpeta del Exportador (`carpeta_ctb`).
2. El nombre del paquete se marca con el hash.
3. La elección no se guarda en el plano.json.
4. Los detalles ya exportados se quedan como están, con aviso y sin botón de reexportar.
5. «Sin CTB» está en el selector.

**Qué se hizo**
- `estilos_impresion.py` (nuevo):
  - lista las `.ctb` de la carpeta (nombre, SHA-256 y descripción);
  - `elegir` acepta solo un nombre de esa lista: nunca una ruta del editor;
  - `marca` arma `_p<sha6>` y `_t`; `opciones` arma lo que va al trabajador;
  - lee el estilo de `options` del manifiesto (1.3: sin CTB y con transparencia).
- `componedor.json` → `exportador`: `carpeta_ctb`, `estilo_impresion` e `imprimir_transparencia`
  (validados; `estilo_impresion` pide `carpeta_ctb`).
- `nombres_paquete.nombre_paquete(…, marca)`: la marca va al final, junto a la escala, y se
  respetan los 60 caracteres.
- `exportar_dxf.Pedido`: incluye el SHA-256 de la CTB y la transparencia. Un paquete con otro estilo
  no sirve de caché y, si recién se exportó, no pasa la verificación.
- Servidor:
  - `GET /api/estilos`;
  - `estilo` en `/api/previa` y `/api/exportar`;
  - la clave de las vistas previas y de las exportaciones en curso incluye el estilo;
  - el resultado y el detalle traen `estilo`, que también va en el catálogo de `editor.html`.
- Editor:
  - recuadro «Estilo de impresión» (selector y casilla);
  - las vistas previas se piden con el estilo;
  - «Exportar» dice con qué estilo exporta;
  - en la tarjeta y en Selección, «Estilo: …»;
  - aviso cuando un detalle salió con otro estilo;
  - lógica en `editor_dxf.js` (`textoEstilo`, `claveEstilo`, `mismoEstilo`).
- Trabajador falso de las pruebas: escribe `plot_style` y `print_transparency` como el real, y
  tiene un modo «ignorar_estilo».

**Pruebas**: 1338 pasan y 1 se salta (antes 1319). ruff igual que antes (173).
- `test_estilos_impresion` (8): lista, solo nombres, marca, nombre largo, manifiesto 1.3/1.4,
  motivos y configuración;
- `test_exportar_estilo` (9):
  - lista y valores por defecto;
  - exportar con CTB, con la caché;
  - convive con el viejo sin CTB, y `_t` solo;
  - si la CTB cambia, sale otro paquete;
  - sin `estilo` en el pedido, el de componedor.json;
  - rutas rechazadas;
  - el paquete sin el estilo pedido no vale;
  - vista previa;
  - HTTP;
- `test_editor_estilo_js` (3): cliente, textos y comparación;
- `test_configuracion` actualizado: `componedor.json` trae las tres claves.

**Verificación con PRGD y el Exportador real** (`data/verificacion/verificar_estilo.mjs`, 28 comprobaciones, todo OK):
- el selector trae «Sin CTB», `CTB_ERCO_derivada_PRGD.ctb` (por defecto) y `CTB_ERCO_V2.ctb`, con
  la transparencia sin marcar; una ruta enviada a mano da 400;
- las tres mesas a 1:75: las vistas previas se dibujaron con la CTB (caché `_pb4a909_t`);
- se exportaron `I1.M1.PV1_12900_1-75_pb4a909_t`, `I1.M1.PV2_12962_1-75_pb4a909_t` e
  `I1.M2.PV4_129C4_1-75_pb4a909_t`;
- el paquete viejo `I1.M1.PV1_12900_1-75` (1.3, sin CTB) quedó con los mismos bytes y no se movió
  nada a `_para_borrar`;
- en Selección sale «Estilo: …»; al elegir «Sin CTB», el aviso aparece en los tres detalles, y al
  volver a la CTB, se va; el plano.json no guarda el estilo;
- colores en los PDF (234 trazos cada uno, 0,709 pt, 0 rellenos transparentes):

| Mesa | Color de los trazos |
|---|---|
| PV1_12900 | (184, 138, 92) |
| PV2_12962 | (110, 138, 221) |
| PV4_129C4 | (115, 184, 92) |

  El paquete viejo de PV1 tenía (127, 95, 63) y 78 rellenos transparentes. El TXT dice
  `PLOT_STYLE_APPLIED` y `HATCH_TRANSPARENT_OMITTED`. Un plano con las tres mesas se compone y
  pasa la verificación.

### Formulario del rótulo en el orden del rótulo — Fase 8 ✅ (2026-11-21)

**Pedido**: TODO el formulario del Rótulo (campos, secciones y paneles) en el orden del rótulo,
de arriba hacia abajo. La primera versión ordenaba solo «Datos del plano»; el usuario cambió esa
decisión.

**Orden**
1. Localización (imagen y ESC. de localización).
2. Coordenadas (Este, Norte).
3. Notas.
4. Convenciones.
5. Revisiones.
6. Título.
7. Firmas.
8. HOJA y DE.
9. ESCALA (calculada).
10. No. PLANO y REV. (calculada).

No cambió cómo funciona ningún campo ni panel; solo su lugar.

**Qué se hizo**
- `editor_formularios.js`:
  - `cajaCampo`: el recuadro de cualquier campo del rótulo (texto, imagen, notas, la unión de las
    celdas de una tabla o de las convenciones);
  - `ordenarPorFilas`: primero el borde superior más alto. Los bordes a ≤ 1 mm del primero de la
    fila son la misma fila y van de izquierda a derecha (FIRMAS 43,5 y HOJA 43,6 mm; No. PLANO y
    REV.);
  - `bloquesRotulo`: todo el formulario en ese orden;
  - `camposSimples` usa el mismo orden y ya no hay lista fija (`ORDEN_CAMPOS`).
- `editor_panel_rotulo.js`:
  - arma el panel con `bloquesRotulo`: campos sueltos seguidos en un grupo, Revisiones y Firmas
    en su sección;
  - coloca las secciones de Imagen, Notas y Convenciones en su lugar;
  - desaparece la sección «Datos del plano», porque sus campos quedan repartidos.
- `editor.html`: los paneles Imagen de localización, Notas y Convenciones pasan a ser secciones
  plegables (`bloque-localizacion`, `bloque-notas`, `bloque-convenciones`) que el Rótulo coloca en
  su sitio. Si el formato no tuviera el campo, quedan después del Rótulo. Sus scripts no
  cambiaron.
- Todos los bloques tienen posición en el formato A1: no hizo falta inventar ninguna.

**Pruebas**: 1342 pasan y 1 se salta (antes 1338). ruff igual que antes (173).
- `test_editor_formularios_js`: la prueba del orden de los campos se actualizó, y hay 4 nuevas:
  - los campos manuales con el formato A1 real;
  - celdas sintéticas: misma fila → izquierda primero; si una celda se mueve, cambia el orden;
  - todo el formulario con el formato A1 real (los 14 bloques en orden, recuadros de las tablas y
    de las convenciones);
  - `ordenarPorFilas` (filas a ≤ 1 mm).

**Verificación en Edge** (`data/verificacion/verificar_orden_rotulo.mjs`, 14 comprobaciones,
todo OK), con `editor/editor.html` recién generado:
- el Rótulo sale en el orden pedido: Imagen, ESC., ESTE, NORTE, Notas, Convenciones, Revisiones,
  Título, Firmas, HOJA, DE, ESCALA*, No. PLANO, REV.* (* de solo lectura); después, como antes,
  los problemas y «Catálogos del editor»;
- ya no hay títulos sueltos de Imagen, Notas y Convenciones en la columna, y sus paneles siguen
  pintando su contenido;
- la tecla Tab recorre los campos en el mismo orden;
- escribir en cada campo llega al rótulo del plano;
- al abrir un plano, el Rótulo se vuelve a pintar en el mismo orden, con sus valores y con los
  paneles en su lugar.

`verificar_localizacion.mjs` (Imagen de localización con PRGD) se volvió a correr: 19 comprobaciones, todo OK (el panel funciona igual en su nuevo lugar). En la Fase 6 se anotaron 22 por error: siempre fueron 19.

### Convenciones: líneas y rellenos — Fase 9a ✅ (2026-11-21)

**Pedido**: la leyenda debe servir para planos muy distintos. Cada renglón puede ser una línea
(color y grosor), un relleno (color) o un símbolo.

**Plan aprobado** (subfases, una a la vez):
- (a) tipos línea y relleno;
- (b) biblioteca versión 2 en `simbolos/` (`carpeta_simbolos`);
- (c) símbolo tomado de un bloque de la lista de «Cargar DXF»;
- (d) recorte de imagen como último recurso, marcado «imagen (no vector)».

**Decisiones del usuario**
1. El símbolo se escoge solo de la lista de bloques; el clic en la vista previa, después.
2. No se pide nada nuevo al Exportador. Primero se prueba la caja eléctrica real.
3. La biblioteca va en `simbolos/`, con ruta configurable; los PDF no van a git.
4. La línea es continua o discontinua.
5. El color, por defecto, el de la capa del DXF según la CTB; el usuario puede cambiarlo. En
   (a) no hay DXF: se elige en el editor (negro o gris por defecto).
6. El recorte de imagen se acepta, en la última subfase.

**Qué se hizo (subfase a)**
- `muestras_leyenda.py` (nuevo):
  - lee y valida `{"tipo": "linea" | "relleno", ...}`, con valores por defecto;
  - `colocar_muestra`: línea de 13 mm o relleno de 13 × 6 mm, centrados en la casilla y más
    cortos si no caben;
  - `dibujar_muestras`: `draw_line` o `draw_rect`, un solo trazo vectorial;
  - `verificar_muestras`: en el PDF, un trazo por casilla, en su sitio (±0,1 mm), con su color,
    grosor (±0,01 mm), trazo y opacidad.
- `rotulo._convenciones`:
  - reparte cada renglón por `tipo` (sin `tipo`, símbolo: igual que antes);
  - las claves válidas dependen del tipo;
  - la descripción de una muestra es obligatoria;
  - la biblioteca solo se carga si hay símbolos.
- `componer` dibuja las muestras en la hoja base, junto a los símbolos, y las verifica. `cli`
  las resume («Convenciones: 1 línea(s) y 1 relleno(s) dibujados como vector.»).
- Editor:
  - `editor_muestras.js` (nuevo): copia de las reglas, los mensajes y la ubicación de Python;
  - `editor_convenciones.js`: validación, lista, guardado, `agregarMuestra` y `cambiarMuestra`;
  - panel Convenciones: botones «+ Línea» y «+ Relleno»; color, grosor y trazo, u opacidad;
    miniatura SVG;
  - vista previa (`piezasRotulo` devuelve `muestras`) y lienzo (`<line>` y `<rect>` SVG).

**Pruebas**: 1373 pasan y 1 se salta (antes 1342). ruff igual que antes (173).
- `test_muestras_leyenda` (14):
  - valores por defecto y errores;
  - ubicación;
  - dibujo y verificación;
  - plano con símbolos y muestras: vector, sin imágenes en las convenciones;
  - solo muestras, sin biblioteca;
  - todos los problemas juntos;
  - falla forzada de color;
  - resumen de `cli`.
- `test_editor_muestras_js` (15): los mismos errores que Python, válidos en los dos, misma
  ubicación, valores por defecto y lo que se guarda, ida y vuelta sin tocar idéntica.
- `test_editor_vista_previa_js` (+2): las muestras se ubican igual que `componer`; una muestra
  con problema no se dibuja y se marca.
- Las pruebas de símbolos, rótulo y convenciones de antes pasan sin cambios.

**Verificación en Edge** (`data/verificacion/verificar_muestras_leyenda.mjs`, 22 comprobaciones,
todo OK), con `editor/editor.html` recién generado y el formato A1 real:
- botones, y siguen los 12 símbolos;
- un símbolo se guarda como antes (`{"simbolo": "limite_predio"}`);
- línea nueva con los valores por defecto, que pide su descripción;
- línea roja de 0,35 mm discontinua y relleno verde al 50 %: el rótulo del plano, las miniaturas
  y la vista previa (vectores SVG) dicen lo mismo;
- guardado y compuesto con `componer`: en el PDF, casilla 2 una línea roja de 0,35 mm
  discontinua, casilla 3 un relleno con opacidad 0,5, casilla 1 el símbolo, y ninguna imagen en
  las convenciones;
- al abrir el plano vuelven los mismos valores; un plano viejo (solo símbolos) se abre y se
  guarda idéntico; sin errores de JavaScript.

### Biblioteca de símbolos versión 2 — Fase 9b ✅ (2026-11-21)

**Pedido**: `simbolos/indice.json` versión 2 (a git) con id, descripción, tipo, origen y fecha;
un PDF por símbolo en `simbolos/biblioteca/<id>.pdf` (fuera de git); carpeta configurable con
`carpeta_simbolos`. Todo lo de hoy debe dar el mismo resultado.

**Qué se hizo**
- `biblioteca_simbolos.py` (nuevo):
  - lee y revisa el índice versión 2 (todos los problemas juntos);
  - escribe el índice;
  - `con_carpeta_simbolos`: el formato con la biblioteca de `carpeta_simbolos`;
  - `migrar_v1`: pasa la versión 1 a la 2 copiando cada página tal cual (`insert_pdf`),
    compara trazo por trazo con la página vieja y solo entonces escribe el índice y MUEVE el
    PDF viejo y una copia del índice viejo a `_para_borrar/simbolos_v1_<fecha>/`; si algo falla,
    borra solo lo que creó y no cambia nada.
- `simbolos.py`:
  - `cargar_biblioteca` lee las dos versiones;
  - cada `Simbolo` sabe su PDF, su página y su margen;
  - `dibujar_simbolos` abre el PDF de cada símbolo;
  - `extraer_simbolos` escribe la versión 2 y conserva los símbolos de otro origen.
- `rotulo.py`: usa el margen de cada símbolo. `datos_rotulo_editor.py`: miniaturas desde el PDF
  de cada símbolo.
- `componedor.json` → `carpeta_simbolos` (opcional, a nivel general): `configuracion`
  (`ConfigEditor.simbolos`, `ConfigComponer.simbolos`, carpeta que debe existir), `componer_plano
  (…, carpeta_simbolos)`, `generar_editor` / `preparar_editor (…, carpeta_simbolos)`, CLI
  `componer --config` y `editor --config`.
- CLI `migrar-simbolos` (`--config` o `--indice`, `--para-borrar`).
- `.gitignore`: `/simbolos/biblioteca/`.
- **Biblioteca real migrada**:
  - `simbolos/indice.json` es versión 2 con los 12 símbolos (origen PRGE-25-0044…, casilla y
    caja de origen; fecha 2026-11-21);
  - los 12 PDF están en `simbolos/biblioteca/`;
  - `convenciones_erco.pdf` y una copia del índice versión 1 esperan en
    `_para_borrar/simbolos_v1_2026-11-21/` la confirmación del usuario.

**Mismo resultado**:
- Antes de cambiar el código se compusieron 6 planos reales con convenciones: `PruebaultimaSup`,
  `planoalan`, `planoguamo_prueba`, `planoprueba`, `PRUEBAFROTULO` y `plano_firma` (12 símbolos).
- Después de migrar se compusieron otra vez, con `--config`. Salieron **iguales**:
  - los mismos trazos (de 801 a 112 953 por plano), textos e imágenes;
  - cada símbolo en la misma casilla, a la misma escala y en la misma posición (±1e-9 mm);
  - las 12 miniaturas del editor, con el mismo SHA-256.

**Pruebas**: 1383 pasan y 1 se salta (antes 1373). ruff igual que antes (173).
- `test_biblioteca_simbolos` (10):
  - la versión 1 se sigue leyendo;
  - migrar no cambia ningún dibujo ni el plano compuesto;
  - migrar se niega sin tocar nada (PDF ya existente, página distinta, ya migrada);
  - índice con 7 problemas;
  - extraer conserva los símbolos de otro origen;
  - `con_carpeta_simbolos`;
  - `componer` y el editor con `carpeta_simbolos`;
  - configuración;
  - `componer --config`;
  - `migrar-simbolos`.
- `test_simbolos` y `test_muestras_leyenda` actualizados a la versión 2: un PDF por símbolo, el
  índice nuevo y los mensajes de PDF faltante.

**Verificación en Edge** (`data/verificacion/verificar_biblioteca_v2.mjs`, 13 comprobaciones,
todo OK):
- el editor de antes de migrar y el regenerado con `--config` tienen los 12 símbolos, las mismas
  descripciones y las mismas miniaturas, byte a byte (con la opacidad 0,5);
- un plano con 4 símbolos se arma, se ve en la vista previa y se compone como «Componer.bat»: en
  el PDF, cada casilla tiene los trazos del índice (554, 1, 507 y 5), con la opacidad 0,5;
- `editor/planoalan.json` (guardado antes) se abre con las mismas convenciones y sin problemas.

### Zonas del Model Space — Fases 10a y 10b (2026-11-24, sin commit)

**Plan aprobado** (Fase 10, una subfase a la vez):
- 10a: comprobación h con máscara;
- 10b: servidor con protocolo 1.1 y vista previa de zona;
- 10c: exportar una zona;
- 10d: modo «Zonas del modelo» en el editor;
- 10e: guardar las zonas en el plano.json y «Volver a exportar zonas».

Decisiones del usuario:
- A. Las zonas van en el plano.json (`dxf.zonas[]`).
- B. Con el nombre vacío, la zona se queda con el nombre que generó el Exportador la primera vez
  (`Zona_01`…). Si el usuario escribe uno, queda ese.
- C. Las capas empiezan todas marcadas (modo «todas menos estas»); «solo estas» es una opción.
- D. Un solo botón vuelve a exportar todas las zonas cuando cambie el DXF.

**10a — Comprobación h con máscara** (manifiesto 1.5, `docs/manifiesto.md` del Exportador,
«Cómo medir los trazos con máscara»):
- `manifiesto.py`: `Dibujo.mascara_mm` = `pdf.drawing.mask.zone_page_mm`. Si `mask` falta
  (esquemas 1.0–1.4) o es null, no hay máscara. Si viene, se valida (objeto, cuatro números,
  x1 > x0 e y1 > y0).
- `comprobacion_dibujo.py`: `recortar_a_zona` recorta el `rect` de cada trazo a la zona, a mano
  con máximos y mínimos, sin `Rect.intersect`. Un segmento horizontal o vertical, de alto o ancho
  cero, se conserva. Se descarta lo que queda entero fuera (la franja del `bleed_mm` o más allá).
  `medir_limites_trazos(pagina, mascara_mm)` la usa.
- `coherencia.py`: la h recorta a la máscara si la hay y lo dice en su nombre («recortados a la
  máscara …»). Sin trazos dentro de la zona, falla con su propio mensaje. La g no cambia.
- Con los paquetes de zona que dejó el Exportador (402ad72) en su
  `data/verificacion/zonas_3`, `zonas_4` y `zonas_5`:
  - antes, la h fallaba en los 4 con máscara de cada carpeta (de 12,9 a 63,1 mm);
  - ahora los 14 paquetes 1.5 pasan integridad y coherencia completas, con la h en 0,000 mm;
  - los de `zonas_1` (esquema 1.4, anteriores al arreglo del Exportador) siguen fallando la g,
    como debe ser.

**10b — Protocolo 1.1 y vista previa de zona**:
- `trabajador.py`: los pedidos dicen `"protocol": "1.1"`. `admite_zonas(ready)` exige 1.1 o más
  para las zonas; un trabajador 1.0 sigue sirviendo para bloques.
- `previa_zona.py` (nuevo):
  - `pedido_previa_zona` valida y arma el `preview` de una zona: `zona` y `vista` como cajas,
    `capas` (solo estas) o `excluir` (todas menos estas, nunca las dos, sin comas) y `escala`
    (entero de 1 a 100 000);
  - `leer_previa_zona` lee la respuesta: `filas_capas`, `grupos`, `entidades`, `papel` y lo común
    con la de un bloque (`previa_dxf.leer_previa`). Si no hay nada que dibujar, da un mensaje claro.
- `aplicacion_editor.py`: `pedir_previa_zona`. Dos pedidos iguales mientras se hace son una sola
  tarea. Da 409 si el trabajador habla la 1.0. El PNG sale por la misma `/api/previas/<id>`.
- `servidor.py`: `POST /api/previa/zona`.
- Pruebas con el falso: `tests/trabajador_falso.py` habla la 1.1 por defecto (con `--protocolo 1.0`
  hace de exportador viejo) y responde `preview` de zona: grupos, filtro de capas, papel, caché
  `ms-…` y `BAD_REQUEST` con una capa que no existe.
- Con el **Exportador real y PRGD-25-1365-CIV-PL-106_1_VA.dxf**
  (`data/verificacion/zonas_10b.py`; PNG y respuestas en `data/verificacion/zonas_10b/`), todo OK:
  - `load` en 142 s; el trabajador dice protocolo 1.1 y manifiesto 1.5;
  - todo el Model Space en 107 s: 6 grupos y 25 830 entidades;
  - el grupo de la zona Zona_01 en 77 s: 16 824 entidades;
  - la zona de Zona_01 sin las 4 capas de cotas, a 1:50, en 0,7 s: 13,40 × 13,00 mm, igual que el
    cálculo a mano, y esas capas con `se_ve: false`;
  - la misma zona a 1:20 sale de la caché, con el papel nuevo;
  - «solo la capa 0» funciona;
  - una capa que no existe da `BAD_REQUEST` con el mensaje del Exportador.

**Pruebas**: **1433 pasan** y 1 se salta (antes 1383). ruff: los mismos 173 hallazgos de antes.
- `test_coherencia_mascara` (12):
  - recortar conserva los segmentos horizontales y verticales, descarta lo de fuera, conserva lo
    que toca el borde y no cambia los trazos recibidos;
  - el manifiesto sin máscara, con máscara y con 3 máscaras mal formadas;
  - la h pasa con la máscara;
  - el mismo PDF sin máscara falla solo la h;
  - sin trazos dentro de la zona, falla con su mensaje.
- `test_previa_zona` (31): el pedido y lo que no vale (12 casos), `admite_zonas` y la respuesta
  del contrato (con grupos, sin papel y 8 respuestas que no cumplen).
- `test_aplicacion_zona` (6): todo el Model Space con grupos, un grupo, la zona con capas
  excluidas y escala, «solo estas», pedidos que no se pueden hacer, una tarea para dos pedidos
  iguales y el exportador 1.0.
- `test_servidor`: la ruta `/api/previa/zona` y su PNG.

**Pendiente para la 10c**: la verificación final de `componer` (`componer.py`, «el dibujo quedó
en…») mide los trazos de cada detalle colocado **sin** la máscara. Una zona con máscara puesta
en la hoja fallaría ahí igual que fallaba la h. Se arregla con la misma `recortar_a_zona`, la
zona trasladada a la posición del detalle, al colocar zonas (10c). → Hecho en la 10c.

10a y 10b: commit 247c0af en dev, con push (2026-11-24).

### Zonas del Model Space — Fase 10c: exportar una zona (2026-11-24, sin commit)

**Qué se hizo**
- `exportar_zona.py` (nuevo):
  - `nombre_de_zona`: el nombre escrito, limpio (§5.1, 40 caracteres como mucho);
  - `nombre_libre`: si viene vacío, el primer `Zona_NN` sin paquetes en la carpeta del DXF ni
    exportándose ahora. Lo elige el Componedor porque el trabajador publica en la carpeta de
    preparación, vacía, y no vería los ya publicados;
  - `leer_zona`, `pagina_de_zona` (la zona a 1:N más los márgenes) y `trabajo_de_zona` (§5.4).
- `exportar_dxf.Pedido`: `zona`, `capas` y `excluir`. En una zona no se compara el handle sino
  `source.block_name` «Model_Space», `selection.kind`, `selection.window` y el filtro de capas.
  Así la misma zona con otras capas no sale de la caché.
- `aplicacion_editor.py`:
  - `exportar_zona`, con la misma cola, preparación, caché, verificación, el paquete viejo a
    `_para_borrar` y la entrada de catálogo para «Detalles disponibles» y `/api/exportados`;
  - lo común con los bloques pasó a `_encolar_export` y `_dxf_para_exportar`;
  - el candado es un `RLock`, para elegir el nombre libre y encolar sin soltarlo.
  El resultado trae `tipo: "zona"`, `nombre`, `nombre_generado`, `zona`, `capas` y `excluir`,
  para que la 10e los guarde.
- `servidor.py`: `POST /api/exportar/zona`.
- `componer.py`: `DetalleColocado.mascara` (la zona de la máscara en mm de papel). La
  verificación final recorta a ella los trazos del detalle (`recortar_a_zona`).
- `tests/trabajador_falso.py`: trabajos de zona en `export`. Publica un paquete 1.5 con
  máscara y una línea que sale de la zona y de la página; con `zona_otra_ventana`, un
  manifiesto de otra ventana.

**Con el Exportador real y PRGD**, con `data/verificacion/zonas_10c.py` (resultados en `data/verificacion/zonas_10c/`), todo OK:
- `load` en 126 s.
- Zona de Zona_01 sin las 4 capas de cotas, a 1:20, nombre «Prueba10c seccion»: 21 s.
  `Prueba10c_seccion_1-20_pb4a909_t`, página 43,5 × 42,5 mm, con máscara; la h da 0,064 mm.
- La misma otra vez sale de la caché en 0,2 s.
- La misma zona con el nombre vacío y todas las capas, a 1:10: `Zona_01_1-10_pb4a909_t`
  (generado), con máscara; la h da 0,000 mm.
- Poste, solo con las capas `0` y `_001_*`, a 1:5: 1,2 s. Sin máscara: todo se pudo recortar.
- Los tres pasan integridad y coherencia, y el inventario con el que se genera el editor
  («Detalles disponibles») los acepta (bloque «Model_Space»).
- Compuestos en un A1 real (`plano_zonas.pdf`), donde dijo el servidor: la verificación final
  pasa con las máscaras. A la vista, los textos que cruzan el borde quedan cortados en la zona,
  todo sigue siendo vector y la única imagen es la del rótulo.
- Los paquetes quedaron en `data/input/dxf/PRGD-25-1365-CIV-PL-106_1_VA/`.

**Pruebas**: **1446 pasan**, 1 se salta y 1 falla de forma intermitente (antes 1433).
- La intermitente no es de la 10c: en dos corridas fue una distinta de `test_servidor`
  (`test_post_exige_origin_propio_y_json`, `test_las_rutas_de_la_ortofoto_piden_token_y_origen`),
  con `ConnectionAbortedError` 10053.
- El servidor rechaza un cuerpo sin leerlo (por ejemplo, el de 64 KB → 413) y Windows a veces
  corta la conexión antes de que el cliente lea la respuesta.
- Solas pasan 6 de 6 veces. Queda pendiente, aparte.

ruff: los mismos 173 hallazgos de antes.
- `test_exportar_zona` (13):
  - nombre, nombre libre, leer la zona y el trabajo;
  - el `Pedido` de zona;
  - exportar con nombre, que queda en el catálogo;
  - `Zona_01` y `Zona_02` generados, y la misma zona por su nombre sale de la caché;
  - dos zonas generadas a la vez;
  - otras capas no salen de la caché y el viejo va a `_para_borrar`;
  - un paquete de otra ventana da `PAQUETE_NO_VALIDO`;
  - 7 pedidos que no se atienden;
  - el exportador 1.0;
  - la zona se compone con su máscara;
  - sin el recorte, la verificación final fallaría.
- `test_servidor`: `/api/exportar/zona` y `/api/exportados`.

10c: commit dc1d794 en dev, con push (2026-11-24).

### Zonas del Model Space — Fase 10d: «Zonas del modelo» en el editor (2026-11-24, sin commit)

**Qué se hizo**
- `editor_zonas.js` (nuevo, lógica sin pantalla, en Node y en el navegador):
  - px ↔ CAD con `cad_a_px`;
  - el rectángulo arrastrado como zona CAD (normalizada, limitada a la imagen, a milésimas de
    unidad; menos de 4 px es un clic);
  - el grupo bajo un clic (el más chico que lo contiene);
  - la vista «de cerca» (la zona más 15 %);
  - el tamaño en la hoja (igual que `exportar_zona.pagina_de_zona`), si cabe en el área de
    dibujo del A1 y la escala sugerida;
  - el filtro de capas (modos «excluir» y «solo»);
  - los cuerpos de `/api/previa/zona` y `/api/exportar/zona` y los textos (zona, grupo, «lleva
    1 min 05 s»).
- `editor_panel_zonas.js` (nuevo): el cuadro «Zonas del modelo». Tiene la imagen con los grupos
  (G1, G2…) y la zona en un SVG, los botones de grupo, el arrastre con el ratón y «Ver la zona de
  cerca». Las capas van con casillas (todas marcadas al empezar; «Solo las marcadas»; las
  apagadas en el CAD en gris), con «Ver con estas capas». Luego la escala con el tamaño en la
  hoja (en rojo si no cabe, con la escala que sí), el nombre opcional y «Exportar zona». Lo largo
  se muestra en el cuadro «Trabajando…» con barra, mensaje del trabajador, tiempo transcurrido
  (se repinta cada segundo) y «Cancelar». Las vistas ya pedidas se guardan; pedir otra cancela la
  que esperaba. Lo exportado va a «Detalles disponibles» (`EditorUI.registrarDetalles`) y el
  nombre usado (también el generado) queda en el campo.
- `editor_panel_dxf.js`: botón «Zonas del modelo…» en la carpeta del DXF (desactivado si hay que
  volver a cargar), «lleva …» en la barra de la carga del DXF y `estiloPedido()`.
- `editor_servidor.js`: `previaZona` y `exportarZona`. `editor_html.py` y `editor.html`: los dos
  JS nuevos. `editor.css`: el cuadro.

**Cómo probarlo**: `Abrir editor.bat` → «Cargar DXF» → «Zonas del modelo…» (paso a paso en
`docs/servidor_editor.md`, «Zonas del modelo, paso a paso»).

**Verificación en Edge** (`data/verificacion/verificar_zonas.mjs`, ratón real por CDP; capturas en
`data/verificacion/zonas_salida/`). Todo OK, sin errores de JavaScript.
- Con el trabajador falso (`servidor_bloques_prueba.py --zonas`):
  - el cuadro «Trabajando…», con «lleva N s», la explicación y «Cancelar»;
  - dos grupos (botones y recuadros), y un clic en el grupo 1 abre su vista;
  - la zona arrastrada da exactamente [100, 140, 200, 200];
  - escala sugerida 1:200; a 1:50 avisa en rojo «No cabe… Pruebe 1:200» y «Exportar zona» queda
    desactivado;
  - todas las capas marcadas al empezar; desmarcar COTAS; con «solo» y ninguna, no se exporta;
  - la capa apagada sale en gris;
  - «Ver la zona de cerca» sin COTAS;
  - al exportar con el nombre vacío sale `Zona_01_1-200`, el campo queda en `Zona_01` y aparece
    en «Detalles disponibles».
- Con el **Exportador real y PRGD** (paquetes en `data/verificacion/zonas_real/paquetes/`):
  - la carga muestra «Leyendo el DXF con ezdxf — … · lleva 19 s» y la página responde (10 ms);
  - el DXF queda cargado en 80 s;
  - la primera vista muestra «Dibujando el Model Space: 1950 de 25830 — 34 % · lleva 15 s» y
    tarda 37 s: 6 grupos;
  - el grupo 1 tarda 22 s;
  - la zona de la sección, dibujada con el ratón tras «Ver la zona de cerca», sale exacta
    (±5 mm);
  - sin las 4 capas de cotas, a 1:20: «página 43,5 × 42,5 mm… Cabe»;
  - «Exportar zona» da `Prueba10d_seccion_1-20_pb4a909_t`, que aparece en «Detalles
    disponibles».
  - Esta vez fue más rápido que en la 10b, porque el equipo tenía menos carga.
- Ajuste después de mirar las capturas: en PRGD los grupos están a cientos de km y cada uno es un
  punto en la imagen. Por eso un clic **cerca** de un grupo o en su etiqueta «G1» también lo abre
  (`grupoEnPunto` con tolerancia).

**Pruebas**: **1455 pasan**, 1 se salta (antes 1446) y 1 falla de forma intermitente: la misma
de `test_servidor` de la 10c, ajena a las zonas, que sola pasa. ruff: los mismos 173 hallazgos.
- `test_editor_zonas_js` (9, en Node):
  - px ↔ CAD;
  - la zona arrastrada (al revés, un clic, limitada a la imagen);
  - el grupo bajo el clic y cerca;
  - el tamaño en la hoja igual que Python, el aviso y la escala sugerida;
  - el filtro de capas y sus textos;
  - el orden de las capas;
  - los cuerpos de los pedidos;
  - la vista alrededor y los textos;
  - el editor generado trae los dos JS.

#### Ajuste de la 10d: la vista como en AutoCAD (2026-11-24, sin commit)

Pedido: rueda para acercar y alejar hacia el cursor, rueda apretada y arrastrar para mover,
doble clic con la rueda para ver todo y clic izquierdo y arrastrar para dibujar la zona (también
acercada). La imagen se escala al instante y, al parar la rueda, se pide una vista nítida (con
aviso y usando la caché). La zona queda exacta a cualquier zoom. Ya no hace falta «Ver la zona de
cerca».

**Qué se hizo**
- `editor_zonas.js`: la cámara (`encuadrar`, `zoomEnPunto`, `desplazar`, `factorRueda` de
  ×1,25 por clic de rueda), `cajaDeImagen`, `necesitaVistaNitida` (cubre lo que se ve del dibujo
  y tiene al menos 0,75 px de imagen por px de pantalla) e `interseccion`. `zonaDesdeArrastre`
  recibe los puntos ya en coordenadas del dibujo; menos de 4 px de pantalla es un clic. Se
  quitó `vistaAlrededor`.
- `editor_panel_zonas.js`, reescrito el visor:
  - la cámara en coordenadas CAD y el `viewBox` sacado de ella y de la matriz de la imagen que
    hay;
  - la rueda con `passive: false`;
  - la rueda apretada mueve, sin el autodesplazamiento de Windows;
  - doble clic con la rueda (dos en 400 ms) para ver todo;
  - clic izquierdo para dibujar o, si es un clic, ir al grupo (24 px de tolerancia);
  - la vista nítida 450 ms después de parar, con la imagen actual si alcanza, la de todo si se
    ve todo, la caché del editor o un pedido nuevo que cancela el anterior;
  - los grupos y la zona siempre visibles, con grosores fijos en pantalla;
  - la casilla «Ver la imagen con el filtro de capas» en lugar de «Ver con estas capas»;
  - la barra chica «Pidiendo la vista nítida… · lleva N s · Cancelar» arriba, que no tapa ni
    bloquea.
- **Error de pantalla encontrado en la verificación**: soltar el arrastre fuera del visor, sobre
  el fondo del diálogo, no llegaba al visor y la zona se perdía. Ahora el fin del arrastre se
  escucha en toda la ventana (y en `lostpointercapture`) y el punto se limita al borde del visor.
- **Error de antes, encontrado por la rueda** (`canal_trabajador.py`): si el trabajador respondía
  «no aceptado» a un `cancel` (el pedido ya estaba terminando), el canal lo detenía a la fuerza en
  el acto, y se perdía la sesión del DXF. Ahora solo se lo detiene en el acto si no responde; si
  responde, se espera a que la tarea termine (mismo plazo de 60 s). El trabajador falso tiene
  `--cancel-no-aceptado` para probarlo.

**Cómo probarlo**: `Abrir editor.bat` → «Cargar DXF» → «Zonas del modelo…»; rueda, rueda apretada,
doble clic con la rueda y clic izquierdo (tabla en `docs/servidor_editor.md`).

**Verificación en Edge** (`data/verificacion/verificar_zonas.mjs`, ratón real por CDP: rueda,
botón de la rueda, doble clic con la rueda, clic y arrastre izquierdo). **48 comprobaciones, todo
OK** con el falso (3 de 3 corridas) y con PRGD real.
- Con el falso:
  - cada clic de rueda da ×0,800, ×0,512 o ×1,250, y el punto bajo el cursor se queda (0,02 a
    0,09 px) con la imagen escalada al instante;
  - cinco clics seguidos no piden nada y, al parar, se pide la vista nítida;
  - la rueda apretada mueve y lo de debajo del cursor sigue debajo;
  - la zona arrastrada con la vista acercada sale exacta (±1 px) y su rectángulo sigue exacto
    tras otro zoom (±1,5 px);
  - soltar fuera del visor deja la zona en el borde;
  - el doble clic con la rueda ve todo, de la caché, sin pedidos nuevos;
  - siguen pasando los grupos, «no cabe», capas, el filtro y exportar `Zona_01`.
- Con PRGD:
  - carga en 49 s y todo el Model Space en 31 s;
  - de cientos de km a la sección en 4 tandas de rueda (5 vistas pedidas), con la barra chica
    mientras llega la nítida;
  - la rueda apretada trae la sección al centro;
  - la zona dibujada es exactamente [4736058,98, 2234185,8, 4736059,65, 2234186,45];
  - con el filtro de capas, 1:20 da 43,5 × 42,5 mm y se exporta `Prueba10d_seccion_1-20…`, que
    queda en «Detalles disponibles»;
  - el doble clic con la rueda abarca todo al instante y llega la vista de todo con el filtro;
  - sin errores de JavaScript y sin detener el trabajador.

**Pruebas**: **1459 pasan** y 1 se salta (antes 1455). ruff: los mismos 173 hallazgos.
- `test_editor_zonas_js` (11):
  - cámara: encuadrar, zoom con el punto fijo, desplazar y factor de la rueda;
  - `necesitaVistaNitida` en 6 casos;
  - `interseccion` y la zona desde el arrastre en coordenadas del dibujo.
- `test_canal_trabajador`: un «cancel no aceptado» ya no mata al trabajador.

10d con el ajuste de la vista: commit 9027f35 en dev, con push (2026-11-25).

#### Ajuste de la 10d: vista previa preparada del exportador 1.2 (2026-11-25, sin commit)

Pedido: aprovechar el protocolo 1.2 del exportador (a95d9d5, §4.2), que prepara la vista previa
del Model Space en segundo plano tras `load`: mandar la CTB y la transparencia al cargar, mostrar
«Preparando… lleva N s» y «lista», mostrar `preview_failed` sin romper nada y seguir con 1.1/1.0.

**Qué se hizo**
- `trabajador.py`: protocolo 1.2. Los mensajes `event` (sin pedido) van a `al_evento(nombre,
  data)`; si fallan, se anota y se sigue. `canal_trabajador.py`: `Canal(al_evento=…)` se lo pasa
  a cada trabajador que lanza.
- `preparacion_previa.py` (nuevo): el estado por sesión (preparando, lista, fallida, detenida;
  porcentaje, etapa, transcurrido, segundos, error, estilo) a partir de `preview_preparation` de
  `load` y de los eventos `preview_progress`, `preview_ready` y `preview_failed`. Los de otra
  sesión no se mezclan; no hay estado con un trabajador 1.0/1.1. `pedido_preparar`.
- `aplicacion_editor.py`:
  - `elegir_y_cargar(estilo)` y `recargar(estilo)` mandan `prepare_preview` con la CTB y la
    transparencia del editor; sin estilo, las de `componedor.json`;
  - si la CTB por defecto no existe, se carga igual, sin preparar;
  - `/api/estado` da `dxf.preparacion`.
  `servidor.py`: el `estilo` de los dos pedidos. `previa_zona.py`: `preparada`.
- Editor:
  - `editor_dxf.textoPreparacion` y `transcurrido`;
  - el cliente manda el estilo al cargar;
  - en la carpeta del DXF, la línea azul con barra «Preparando la vista previa del Model Space…
    N % · lleva N s…», la verde «Vista previa lista (se preparó en …): el zoom ya va rápido» o
    la ámbar «No se pudo preparar…: <mensaje>. Todo sigue funcionando…»;
  - mientras se prepara, el editor pregunta cada segundo;
  - la misma línea arriba del cuadro «Zonas del modelo».
- Trabajador falso: protocolo 1.2 por defecto, con preparación en segundo plano (`preparar_s`,
  `preparar_falla`); con `--protocolo 1.1` o `1.0`, sin eventos.

**Verificación en Edge** (`data/verificacion/verificar_preparacion.mjs`; capturas en
`data/verificacion/preparacion_salida/`): **todo OK**, sin errores de JavaScript.
- Falso 1.2, que prepara en 6 s:
  - la línea en la carpeta y en el cuadro, con «lleva N s» y barra;
  - el avance sube solo (0 → 50 %);
  - «Vista previa lista (se preparó en 6 s)…» en verde.
- Falso con falla: «No se pudo preparar la vista previa: MemoryError…», y «Zonas del modelo»
  funciona igual.
- Falso 1.1: sin línea, y todo funciona.
- **PRGD con el exportador real** (estilo de `componedor.json`: CTB derivada, sin
  transparencia):
  - la carga tarda 83 s y la preparación empieza con ella;
  - «Vista previa lista» llega 132 s después de la carga (el equipo estaba ocupado; el
    exportador midió 50 s);
  - después, las vistas de los grupos 1, 2 y 3 salen de lo preparado (`preparada: true`) en
    0,55 / 0,12 / 0,15 s del exportador y 0,7 a 1,2 s en el editor (antes, 20 a 77 s).

**Pruebas**: **1475 pasan** y 1 se salta (antes 1459). ruff: los mismos 173 hallazgos.
- `test_preparacion_previa` (15):
  - el estado: sin nada, avance, lista y tiempo, otra sesión, falla y otra preparación, `load`
    que ya dice lista o fallida, `pedido_preparar`;
  - con el falso: `load` con el estilo del editor hasta «lista», el de `componedor.json`,
    «Volver a cargar», `preview_failed` sin romper nada, el exportador 1.1 y el 1.0, una CTB por
    defecto que no existe no impide cargar, y un estilo que no vale da 400.
- `test_editor_dxf_js`: el cliente manda el estilo al cargar y los textos de la preparación.
- `test_previa_zona`: `preparada`.
- `test_aplicacion_editor`: el `load` lleva `prepare_preview`.

### Pendiente en la Fase 4 (al 2026-11-11)

- **4.4 — en pausa, se va a redefinir.** El alcance anterior (tablas de cantidades de
  movimiento de tierras, escala de colores de cortes y rellenos) queda como referencia hasta la
  nueva definición. La imagen de localización en su recuadro ya está hecha (ver arriba).

### Preguntas abiertas para Alan

1. **¿Qué pasa después de la emisión 0?** La tabla de revisiones del rótulo tiene filas A, B, C
   y 0, y REV. muestra «0» cuando existe (emisión para construcción). Si hay cambios después de
   construcción (¿revisión 1, 2…?, ¿se reemplaza la tabla?), hoy no hay fila ni regla para
   eso.
2. **Firma montada sobre la fila de abajo.** Con `alto_max_mm` = 5,0 la firma de DIBUJÓ (fila de
   4,5 mm, Y 39,0–43,5) baja **1,1 mm** sobre la fila DISEÑÓ (medido en
   `plano_prueba_firma_luis.pdf`, ya borrado con `data/output`; no hay aviso porque esa fila no
   tiene firma). Cuando las dos filas tienen firma sí hay aviso: `planos/plano_firma.json`
   (se regenera con `Componer.bat`) da «firmas de 'dibujo' y 'diseno' montadas, 15,0 × 1,4 mm».
   ¿Es aceptable,
   o se alargan las filas de la tabla de firmas en la plantilla (~7 mm cada una)? Alternativa
   sin tocar la plantilla: bajar `alto_max_mm` a ~3,3 mm (la firma cabe en su fila, más chica).
3. **¿Cuándo se monta el remoto de GitHub?** El repositorio no tiene remoto; `main` está en la
   Fase 2 y las ramas `fase-3` (4 commits) y `fase-4` (21 commits al 2026-11-11, incluye los de
   la Fase 3) no están integradas en `main`. Falta decidir el remoto, quién revisa y cómo se integran.
4. **Firma: ¿nombre completo o iniciales?** Qué va en la columna FIRMA cuando no hay imagen
   (iniciales, rúbrica escrita) y cómo se escribe el NOMBRE en las firmas (completo, con
   segundo apellido, con cargo en segunda línea como REVISÓ).
5. **Versionado al subir el repositorio**: qué entra y qué no. Hoy están **fuera de git**
   (`.gitignore`): `plantillas/*.pdf` (rótulo de ERCO), la biblioteca de símbolos
   `simbolos/*.pdf` (`simbolos/indice.json` sí está versionado), las firmas (`firmas/`, datos
   personales), las notas típicas (`notas/`; vuelven a git si se decide), los planos
   (`planos/`), el editor generado (`editor/`), los PDF (`resultados/`) y todo `data/`. ¿Cuáles
   deben entrar, y dónde viven los que no (¿SharePoint?, ¿carpeta compartida?)?

## Pendientes (después de las Fases 1 y 2)

- **Mayúsculas/minúsculas del nombre del PDF en Windows**: `localizar_paquetes` busca
  `pdf.file_name` comparando el nombre exacto. En Windows el sistema de archivos no
  distingue mayúsculas, así que un manifiesto con «Detalle.pdf» y un archivo «detalle.pdf»
  hoy sale como «el manifiesto indica X pero la carpeta tiene Y». Decidir si se acepta
  (con aviso) o se exige igualdad exacta.
- **Fondo blanco del exportador**: cada detalle trae un rectángulo blanco de página
  completa que tapa lo que haya debajo en la hoja (rótulo, rosa, otros detalles si se
  traslapan). Decidir con el exportador si se quita o si el componedor lo omite.
- ~~Rosa de los vientos y recuadro «LAYERS AUTORIZADOS»~~: resuelto. `componer` y el editor
  advierten si un detalle los tapa (3.2); la v2 ya no trae el recuadro y la rosa se mueve u
  oculta (4.1). `colocar` (un solo detalle) sigue sin tenerla en cuenta.
- **Anotaciones SHX perdidas**: las 83 anotaciones con el texto SHX del rótulo no pasan al
  PDF final (`show_pdf_page` no copia anotaciones); el aspecto no cambia, pero ese texto no
  se puede buscar.
- **Versionado de plantillas**: decidir con Alan si `plantillas/*.pdf` entra al repositorio
  (ahora en «Preguntas abiertas para Alan», punto 5, junto con biblioteca, notas y firmas).
- **Detalles que no caben en A1** (plano_completo, via_ma): el inventario sugiere una escala
  aproximada; reexportarlos a esa escala es una decisión de diseño, fuera del componedor.
