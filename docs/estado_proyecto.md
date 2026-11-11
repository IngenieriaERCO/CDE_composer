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

### Pendiente en la Fase 4 (al 2026-11-11)

- **4.4 — en pausa, se va a redefinir.** El alcance anterior (tablas de cantidades de
  movimiento de tierras, escala de colores de cortes y rellenos, imagen de localización en su
  recuadro) queda como referencia hasta la nueva definición.

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
