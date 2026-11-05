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

**Pendiente (después de la Fase 3)**: deshacer en el editor; el catálogo es el de la carpeta
con que se generó; el fondo blanco del exportador sigue tapando lo que queda debajo.

## Pendientes (después de las Fases 1 y 2)

- **Mayúsculas/minúsculas del nombre del PDF en Windows**: `localizar_paquetes` busca
  `pdf.file_name` comparando el nombre exacto. En Windows el sistema de archivos no
  distingue mayúsculas, así que un manifiesto con «Detalle.pdf» y un archivo «detalle.pdf»
  hoy sale como «el manifiesto indica X pero la carpeta tiene Y». Decidir si se acepta
  (con aviso) o se exige igualdad exacta.
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
- **Detalles que no caben en A1** (plano_completo, via_ma): el inventario sugiere una escala
  aproximada; reexportarlos a esa escala es una decisión de diseño, fuera del componedor.
