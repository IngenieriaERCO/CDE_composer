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

### Subfase 4.1 — Rótulo en blanco v2, campos de texto y rosa movible ✅ (2026-11-06, sin commit)

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

### Subfase 4.2a — Notas del rótulo y HOJA / DE alineados ✅ (2026-11-09, sin commit)

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

### Subfase 4.2b — Convenciones (biblioteca de símbolos vectoriales) ✅ (2026-11-09, sin commit)

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

### Subfase 4.2c — Viñetas en las notas y opacidad por símbolo ✅ (2026-11-09, sin commit)

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

### Subfase 4.2d — Firma con imagen en `componer` ✅ (2026-11-09, sin commit)

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

### Subfase 4.2e — Firma con imagen más grande (caja ampliada) ✅ (2026-11-09, sin commit)

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

### Subfase 4.2f — Firmas por persona ✅ (2026-11-09, sin commit)

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

### Subfase 4.3a — Editor: datos y modelo del rótulo (sin formularios) ✅ (2026-11-09, sin commit)

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

**Corrección de REV.** (2026-11-09, sin commit): la fila «0» es la emisión final (para
construcción) y A, B, C son emisiones previas. Antes el orden era 0 < A < B < C y con
revisiones 0, A y B salía REV. = B (incorrecto). Ahora el `orden` de `revisiones` en
`A1_ERCO.json` es `["A", "B", "C", "0"]`: con «0», REV. = 0; si no, la mayor letra llena entre
C, B y A; sin revisiones, vacía. La función `ultima_revision` no cambió (toma la de mayor
orden); cambió el dato del formato, los textos de ayuda y el mensaje de letra inválida, que
ahora lista «A, B, C, 0». Pruebas: casos 0+A+B → 0, solo A+B → B, solo 0 → 0, ninguna → vacía
(en `ultima_revision` y en `componer`). Suite: **630**, todas pasan. `ejemplo_rotulo_v2.pdf`
regenerado: REV. = 0.

**Pendiente (4.3b)**: formularios del rótulo (campos simples, revisiones y firmas, con selector
de fecha en `formato_fecha`); notas típicas con casillas, orden subir/bajar y notas a mano
(copiadas en `adicionales`); selector de convenciones con miniaturas y descripción editable;
`proyecto.json` (prellenado por copia); pegar, recortar y limpiar la firma en imagen; validación
en vivo. Después (4.3e/f): maquetación en JavaScript con avisos idénticos a Python y vista
previa dibujada.

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
- **Versionado de plantillas**: decidir con Alan si `plantillas/*.pdf` entra al repositorio.
- **Detalles que no caben en A1** (plano_completo, via_ma): el inventario sugiere una escala
  aproximada; reexportarlos a esa escala es una decisión de diseño, fuera del componedor.
