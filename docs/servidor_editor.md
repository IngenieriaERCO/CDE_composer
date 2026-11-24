# Servidor local del editor: «Cargar DXF», vista previa y «Exportar» (etapas 1 a 3)

El editor (`editor.html`) sigue siendo un solo archivo que funciona con doble clic, sin
servidor. Para **cargar un DXF** y ver sus bloques, el editor necesita a alguien que lea el DXF:
el **trabajador** del Exportador Vectorial (`cde-exporter worker`). Como una página web no
puede lanzar programas, `Abrir editor.bat` levanta un **servidor local** que hace de puente.

```
Edge  ──HTTP (127.0.0.1, token)──>  servidor del Componedor  ──JSON por stdin/stdout──>  cde-exporter worker
```

- **Etapa 1**: cargar el DXF y ver la carpeta de bloques.
- **Etapa 2**: poner bloques en la hoja como cajas exactas, cambiarles la escala y ver la vista
  previa PNG del trabajador (ver [editor.md §2f](editor.md#2f-cargar-dxf-con-servidor-local)).
- **Etapa 3**: «Exportar» los bloques del plano a paquetes (PDF + TXT + manifiesto), que pasan a
  ser detalles normales.

## Cómo se usa

1. Doble clic en `Abrir editor.bat`. Genera el editor, arranca el servidor y abre Edge en
   `http://127.0.0.1:<puerto>/?t=<token>`. **Deje abierta la ventana negra**: al cerrarla se
   apagan el servidor y el trabajador. El servidor también se apaga solo tras 30 minutos sin
   señal del editor.
2. En el editor, **Cargar DXF** abre el cuadro de Windows para elegir el archivo. El editor
   muestra la barra de avance (con **Cancelar**) mientras el trabajador lo lee.
3. Arriba de «Detalles disponibles» aparece la **carpeta** del DXF. Cada bloque muestra:
   - nombre y, si se repite, «ocurrencia 2 de 3» y la capa;
   - el tamaño real en m y las unidades (verificadas o no);
   - la **escala sugerida** y el tamaño de la página a esa escala;
   - notas en naranja: caja aproximada, sólidos 3D, objetos proxy, imágenes, capas apagadas o
     congeladas, unidades sin verificar o que no cabe ni a 1:10000.

   Debajo, **«Anónimos (opcionales) (N)»**, cerrada: los bloques anónimos `*U` (mesas de
   PVcase, tablas de Civil 3D…) con `anonimos_min_entidades` entidades visibles o más, con un
   filtro por capa o handle; los más pequeños solo se cuentan. Cada tarjeta, con o sin nombre,
   tiene **Ver vista previa**.

   Al final, «No exportables» (XREF, sin definición…) y los avisos del trabajador.

Si el servidor no arranca, `Abrir editor.bat` abre el editor sin servidor, como antes. Con doble
clic en `editor.html` también se abre sin servidor: el botón «Cargar DXF» aparece desactivado y
explica cómo abrirlo.

Desde la consola:

```powershell
python -m componedor.cli servidor --config componedor.json [--no-abrir] [--puerto 0] [--inactividad-min 30]
```

## Escala sugerida y tamaño de la página

El tamaño de la página del paquete a 1:N sale de la fórmula del contrato del trabajador:

```
página_mm = tamaño_m × 1000 ÷ N + 2 × margen_mm      (por eje; margen de componedor.json)
```

La escala sugerida es la **primera** de la lista estándar (1:50, 1:100, 1:200, 1:250, 1:500,
1:750, 1:1000, 1:1500, 1:2000, 1:2500, 1:5000, 1:10000) con la que esa página cabe en el área de
dibujo (639,7 × 548,6 mm en el A1 ERCO). Es la misma regla de `colocar` y del inventario.

Si la caja del bloque es aproximada (bloques anidados girados), la página real puede salir algo
menor: el editor escribe «página ≤ …». La caja exacta la dará el manifiesto al exportar.

## Configuración (`componedor.json`)

```json
"exportador": {"comando": "cde-exporter", "trabajo": "data/cache_exportador", "margen_mm": 5,
               "anonimos_min_entidades": 100,
               "carpeta_ctb": "../Exportador Vectorial/data/input/ctb",
               "estilo_impresion": "CTB_ERCO_derivada_PRGD.ctb", "imprimir_transparencia": false}
```

| Clave | Obligatoria | Qué es |
|---|---|---|
| `comando` | sí | El comando del exportador (se busca en el PATH) o una lista `[programa, argumentos…]`. El servidor le agrega `worker --work-dir <trabajo>`. |
| `trabajo` | sí | Carpeta del trabajador (sus temporales y caché de vistas previas) y de los registros. Se crea. Está en `data/`, fuera de git. |
| `margen_mm` | no (5) | Margen de página con que se exportará; se manda en `load` y vale para toda la sesión del trabajador. |
| `cache_previas_mb` | no | Tope de la caché de vistas previas del trabajador (`--preview-cache-mb`). Sin la clave, el del trabajador: 500 MB. |
| `paquetes` | no (`data/input/dxf`) | Dónde «Exportar» publica: `<paquetes>/<nombre del DXF>/`. Al generar el editor se miran también las subcarpetas de `editor.paquetes`, así que con el valor por defecto los paquetes exportados aparecen en «Detalles disponibles». |
| `para_borrar` | no (`_para_borrar`) | Adónde se **mueven** (nunca se borran) los paquetes viejos que «Exportar» reemplaza. |
| `anonimos_min_entidades` | no (100) | Entero ≥ 1. Los bloques anónimos `*U` del Model Space que dibujan al menos esas entidades visibles se ofrecen en «Anónimos (opcionales)»; los más pequeños solo se cuentan. Se manda en `load` como `anonymous_min_entities`. |
| `carpeta_ctb` | no | Carpeta de las tablas de estilos de impresión `.ctb` que ofrece el editor (solo ese nivel). Sin ella, solo «sin CTB». |
| `estilo_impresion` | no (null) | La tabla elegida al abrir el editor: el NOMBRE de un `.ctb` de `carpeta_ctb` (sin carpetas). Pide `carpeta_ctb`. Si no está en la carpeta, el editor empieza con «sin CTB» y lo avisa. |
| `imprimir_transparencia` | no (true) | Con `false`, el editor empieza sin imprimir los rellenos con transparencia del 80 % o más (`print_transparency: false`). |

Sin la sección, el editor funciona igual, sin «Cargar DXF», y lo dice.

## Registros (para diagnosticar)

En la carpeta `trabajo`:

| Archivo | Qué guarda |
|---|---|
| `trabajador.log` | Todo lo que el trabajador escribe por stderr (cada arranque empieza con `=== fecha [comando]`). |
| `componedor.log` | Lo que el Componedor anota del canal: líneas de stdout que no son JSON, mensajes sin pedido, «se detiene a la fuerza»… |
| `servidor.log` | Cada pedido HTTP, **sin el token** (se escribe `t=***`). |

## Seguridad y datos

- **Solo 127.0.0.1**, nunca `0.0.0.0`: otra computadora de la red no puede conectarse. El puerto lo
  elige el sistema.
- **Token** de 43 caracteres al azar en cada arranque. La página se pide con `?t=<token>`; la API,
  con la cabecera `X-Componedor-Token`. Sin el token, 403.
- **Host**: debe ser exactamente `127.0.0.1:<puerto>`. Así una página de internet no puede
  usarlo con un nombre que apunte a 127.0.0.1 («DNS rebinding»).
- **Origin**: en un POST es obligatorio y debe ser el del propio servidor. Una página abierta
  con `file://` (Origin «null») u otro sitio reciben 403. Si viene `Sec-Fetch-Site`, debe ser
  `same-origin` (o `none` para abrir la página desde la barra de direcciones).
- POST solo con cuerpo JSON de hasta 64 KB. Rutas desconocidas: 404. Otros métodos: 405.
- **Ninguna ruta entrega archivos del disco** salvo el propio `editor.html` y el PNG de una vista
  previa terminada. El PNG se entrega solo si está **dentro de la carpeta de vistas previas del
  trabajador** (`<trabajo>/previews`, comprobado con la ruta resuelta), y también pide el token.
  Ninguna ruta recibe rutas ni opciones para el comando del exportador: el DXF lo elige el
  cuadro nativo y se valida (archivo que existe, extensión `.dxf`) antes de mandarlo al
  trabajador. Lo único que el editor manda en un cuerpo es el `ref` de un bloque de la carpeta
  ya cargada (y, para «Exportar», la lista de bloques del plano).
- **Ortofoto**: igual que el DXF, la elige el cuadro nativo (se valida: archivo que existe,
  `.tif`/`.tiff`, GeoTIFF georreferenciado). Para su vista previa el editor manda solo números y
  códigos `EPSG:<código>` (validados con GDAL: proyectados); el PNG se hace en memoria y se
  entrega por su id, con el token.
- El PNG no se puede pedir con un `<image href>` directo (no lleva la cabecera del token): el
  editor lo baja con `fetch` y lo muestra como `blob:`. Así el token nunca va en una dirección.
- **Firmas**: no cambia nada. El servidor no tiene ninguna ruta hacia `firmas/` y el HTML solo
  trae los nombres de las personas. Las imágenes solo las lee `componer`, para el PDF.
- Los nombres de bloque vienen del DXF: el editor los escribe siempre como texto, nunca como
  HTML.

## Cómo se habla con el trabajador

El Componedor **no importa código del exportador**: lo lanza como comando externo y le habla JSON
por líneas (protocolo 1.1 desde el 2026-11-24; contrato en `docs/protocolo_trabajador.md` del
repositorio del exportador, aprobado el 2026-11-17 y comparado con esta implementación). Un
trabajador 1.0 sigue sirviendo para bloques; la vista previa de zonas exige que su `ready` diga
1.1 o más (`trabajador.admite_zonas`). `load` se pide con el
margen de `componedor.json`, `units: null` e `include_layers: false`: la tabla de capas todavía
no se usa y así la carga ahorra 1–2 s en bloques grandes.

- **Arranque perezoso**: el trabajador se lanza la primera vez que se pide «Cargar DXF», no al abrir
  el editor. El servidor espera el mensaje `ready` hasta 60 s y comprueba la versión mayor 1 del
  protocolo y del manifiesto. (Con el exportador real, el primer arranque después de actualizarlo
  pasó de 30 s mientras Python compilaba sus archivos; los siguientes, unos 10 s.)
- **Job Object de Windows**: el proceso se crea suspendido, se mete en un Job con «matar al cerrar»
  y recién entonces arranca. `cde-exporter.exe` es un lanzador que arranca `python.exe`; con el
  Job, si el servidor muere (se cierra la ventana, se cae), Windows mata también a ese Python.
- **stderr directo a `trabajador.log`**: esa tubería nunca se llena ni bloquea al trabajador.
- **Un pedido a la vez**: el servidor tiene su propia cola. El editor nunca habla con el
  trabajador; cada pedido crea una tarea y el editor pregunta por su avance cada medio segundo.
  `cancel` y `status` van por fuera de la cola, como permite el contrato. Si igual llegara un
  `BUSY`, se anota y se reintenta una vez.
- **Cancelar**: una tarea en cola se quita al instante; a la que está en curso se le manda
  `cancel`. Si el trabajador no la cancela en 60 s, o no responde al `cancel` en 10 s, se detiene
  a la fuerza (se cierra su Job) y el próximo pedido lanza otro trabajador.
- **Caídas**: si el trabajador termina sin que se le pida, la tarea falla con un mensaje claro y el
  próximo pedido lanza otro. Tras **2 caídas seguidas** el canal se detiene y el editor muestra
  **Reiniciar trabajador**. Cada trabajador nuevo es una sesión nueva: la carpeta del DXF anterior
  se sigue viendo, con el aviso de que hay que volver a cargarlo antes de exportar.
- **Cierre**: al apagar el servidor se manda `close`. Si no termina en 5 s, se cierra su stdin y
  se esperan otros 5 s; al final se cierra el Job.

Si el `cde-exporter` instalado todavía no tiene la orden `worker`, el editor lo dice: «El
cde-exporter instalado no tiene la orden «worker» (es una versión sin trabajador). Actualice el
Exportador Vectorial.»

### Vista previa (`preview`, etapa 2)

- El editor pide la de un bloque al agregarlo (`POST /api/previa {"ref"}`); el servidor la encola
  con `long_side_px: 1500` e `include_hidden_layers: null` (**solo capas visibles**).
- Al trabajador, `preview` y `export` van con el **`handle` solo** del bloque (sin `ref` ni
  `block`): el `ref` de un anónimo (`*U76#1`) puede cambiar entre sesiones porque AutoCAD renumera
  los `*U` al guardar, y el handle no.
- Dos pedidos del mismo bloque mientras se hace son **una sola tarea**. Una ya terminada no se
  reutiliza: el trabajador la devuelve de su caché enseguida (`cached: true`) y, de paso,
  comprueba que el DXF no cambió.
- La respuesta se comprueba (`previa_dxf.py`): `png` dentro de `<trabajo>/previews`, `px` enteros,
  `cad_to_px` con **b = c = 0 y a = −d** (sin giro, misma escala en X e Y) y `bounds`. Si no
  cumple, la tarea falla con el motivo.
- Una vista previa sirve para **cualquier escala**: el editor la reescala alrededor del centro
  (fórmula en `editor_bloques.js`).
- Cargar otro DXF (o volver a cargarlo) **cancela las vistas previas que esperaban turno**, y
  también la que está en curso. Quitar un bloque del plano cancela la suya si todavía esperaba.
- `DXF_CHANGED` (el DXF cambió en el disco) o `NO_SESSION` (el trabajador ya no lo tiene): el
  editor muestra **Volver a cargar** (`POST /api/dxf/recargar`), que repite `load` con la ruta
  que el servidor ya conoce.

### Vista previa de una zona del Model Space (`preview` con `zone`/`view`, Fase 10b)

- `POST /api/previa/zona`; lo valida y lo arma `previa_zona.py`. Siempre **solo capas visibles**
  del CAD (`include_hidden_layers: null`), 1 500 px y el estilo de impresión como en la de un
  bloque.
- Sin `zona` ni `vista`: **todo el Model Space**, con los `groups` del trabajador (grupos de dibujo
  separados por huecos, de más a menos entidades). El editor ofrece cada grupo como `vista` para
  acercarse.
- `zona` (el rectángulo del usuario) con `escala`: el resultado trae `papel` (tamaño en la hoja a
  1:N, página con los márgenes de `load` y si cabe en A1). Cambiar solo la escala devuelve la
  imagen de la caché del trabajador con el `papel` nuevo.
- Capas: `excluir` («todas menos estas», el modo con que empieza el editor) o `capas` («solo
  estas»), nunca las dos; admiten `*` y `?`; sin comas. Una capa de `capas` que no existe:
  la tarea falla con `BAD_REQUEST` del trabajador.
- El resultado trae `filas_capas` (`nombre`, `entidades` en la vista, `estado_cad`, `se_ve`) para
  las casillas del editor, y `entidades` (`en_vista`, `dibujadas`, `sin_caja`).
- La vista previa **no recorta**: lo que cruza el borde se ve entero hasta el borde de la imagen
  (la exportación sí recorta).
- Tiempos con PRGD (97 MB, exportador 402ad72, CTB de `componedor.json`): `load` 142 s; todo el
  Model Space 107 s (incluye calcular las cajas de todo el Model Space, una vez por sesión); un
  grupo de 16 824 entidades 77 s; una zona pequeña 0,5–0,7 s; otra escala, 0,2 s (caché).

### Exportar (`export`, etapa 3)

- **Un pedido `export` por bloque**, con un solo trabajo (`POST /api/exportar`): cada uno tiene su
  tarea, su barra de avance y su «Cancelar». El servidor los pone en su cola, uno a la vez,
  detrás de lo que ya esperaba (p. ej. vistas previas). Dos copias del mismo bloque a la misma
  escala son una sola tarea (un paquete).
- **Dónde y con qué nombre**: `<paquetes>/<DXF>/<file_stem>_1-N` (`nombres_paquete.py`: si pasa de
  60 caracteres, recortado con nuestro sufijo de hash antes de la escala). Opciones: las
  recomendadas por el contrato (`solids: footprint`, `omit_unsupported: true`), `overwrite:
  false`, `write_summary: false`; `units` y `margin_mm` no se mandan (son los de `load`).
- **Antes de pedirlo**:
  - si el DXF cambió en el disco desde que se cargó (tamaño o fecha, la regla §9 del
    contrato), 409 «vuelva a cargarlo», también para lo que saldría de la caché;
  - **caché**: si el paquete ya está publicado y es el de este bloque (SHA-256 del DXF, handle,
    escala y margen) y pasa `importar_paquete`, se usa sin exportar (la tarea nace terminada);
  - el trabajador publica en una **carpeta de preparación** dentro de la del DXF
    (`.componedor-nuevo-<n>`, que `localizar_paquetes` ignora): el paquete viejo, si hay, no
    se toca todavía.
- **Después**: el paquete pasa por `importar_paquete` (completo, íntegro, coherente, escala
  física garantizada) y además tiene que ser el pedido (los mismos cuatro datos y una página que
  no pase de la caja del editor).
  - Si pasa: el paquete viejo (otra versión del DXF, a medio publicar…) se **mueve** a
    `_para_borrar/paquetes_<fecha>/…` y el nuevo pasa a su lugar (mover dentro del mismo disco;
    el manifiesto el último).
  - Si no pasa: `PAQUETE_NO_VALIDO`; el nuevo va a `_para_borrar/` y el viejo queda en su lugar.
  - Si el trabajo se cancela o falla: el viejo queda en su lugar; la carpeta de preparación se
    quita (lo que hubiera publicado va a `_para_borrar/`).
- **Colocación por el centro CAD**: el punto CAD del centro de la caja de `load` va al
  `centro_mm` del plano: `posición = centro − (px, alto − py)`, con `(px, py) = cad_to_page · C`.
  El resultado trae `desde_centro_mm` para colocar cualquier copia del bloque.
- **Cancelar**: en cola se quita; en curso se manda `cancel` (el contrato no deja archivos a
  medias). **Detener a la fuerza** (`POST /api/trabajador/detener`) cierra el Job del
  trabajador sin esperar: lo que estaba en curso y lo que esperaba quedan cancelados y la sesión
  se pierde (hay que volver a cargar el DXF).
- **DXF_CHANGED** en un trabajo que esperaba turno: falla con ese código y el editor muestra
  «Volver a cargar».
- Las carpetas `.cde-tmp-*` que el exportador usa (o deja) en la salida se ignoran al buscar
  paquetes (`localizar_paquetes`).

### Errores para el usuario

`mensajes_trabajador.py` convierte los errores del trabajador que traen texto técnico de Python
(`INTERNAL`, `DXF_INVALID`, y los de un trabajo de `export`: `EXPORT_FAILED`,
`VALIDATION_FAILED`, `CRITICAL_NOTICE`) en un mensaje claro según lo que se hacía (cargar,
vista previa, exportar). El texto técnico queda en `error.detalle` y la ruta del registro en
`error.registro`, para el botón «Ver detalle» del editor. El consejo «Repita el pedido» se quita
cuando el error es determinista (el mismo DXF falla igual); se deja solo si la causa puede pasar
(memoria, disco).

### Lo que el Componedor exige de la respuesta de `load`

`session`, `dxf.name`, `margin_mm` (número ≥ 0) y la lista `blocks`. Sin eso, la carga falla con
«La respuesta del trabajador no se puede usar: …». Un bloque mal descrito se descarta y se
muestra en la carpeta con su motivo, sin tumbar la carpeta entera. Lo que se exige de cada
bloque:

- `ref`, `name` y `handle`: texto no vacío; `handle` nunca null (punto 9 de la revisión del
  contrato);
- `occurrence` y `total_occurrences`: enteros ≥ 1;
- `bounds.exact`: booleano;
- `size_m`: `[ancho, alto]` o `null`.

## API (para quien mantenga el editor)

| Método y ruta | Qué hace |
|---|---|
| `GET /?t=<token>` | El `editor.html` de `editor.salida`, tal cual está en el disco. |
| `GET /api/estado` | Exportador disponible o por qué no, estado del trabajador, la carpeta del último DXF (`sesion_activa`) y la última tarea de carga. |
| `POST /api/dxf/elegir` | Abre el cuadro nativo; si se elige un DXF, encola `load`. Responde `{elegido, tarea}`. 409 si ya hay un cuadro abierto o una carga en curso. |
| `POST /api/dxf/recargar` | «Volver a cargar»: `load` otra vez con la ruta del último DXF elegido. 409 si no hay ninguno o ya se está cargando. |
| `GET /api/estilos` | `{estilos: [{nombre, sha256, descripcion}], por_defecto: {ctb, transparencia}, aviso}`: las tablas `.ctb` de `carpeta_ctb` y los valores de `componedor.json`. Nunca rutas. |
| `POST /api/previa` | Cuerpo `{"ref": "<ref de la carpeta>", "estilo"?: {"ctb": <nombre de /api/estilos> \| null, "transparencia": bool}}` (sin `estilo`, el de `componedor.json`; un nombre que no es de la lista o una ruta: 400): encola `preview` con `plot_style` (la ruta la pone el servidor) y `print_transparency`. Responde `{tarea}`. 409 sin DXF o con la sesión vencida; 404 si el `ref` no está en la carpeta. El resultado de la tarea trae `px`, `cad_a_px`, `caja_cad`, `omitidos`, `en_cache` y `url` (nunca la ruta del PNG). |
| `POST /api/previa/zona` | Cuerpo `{"zona"?: [xmin, ymin, xmax, ymax] \| null, "vista"?: [...] \| null, "excluir"?: [capas] \| null, "capas"?: [capas] \| null, "escala"?: N \| null, "estilo"?}` (unidades del dibujo; N entero de 1 a 100 000; `capas` y `excluir` no van juntas): encola `preview` de una zona (protocolo 1.1, §4.1). Responde `{tarea}`; dos pedidos iguales mientras se hace son una sola tarea. 400 si algo no vale; 409 sin DXF, con la sesión vencida o si el trabajador habla la 1.0. El resultado trae `px`, `cad_a_px`, `caja_cad`, `zona`, `vista`, `capas`, `excluir`, `filas_capas`, `grupos`, `entidades`, `escala`, `papel`, `en_cache` y `url`. |
| `POST /api/exportar` | Cuerpo `{"bloques": [{"id", "handle", "sha256", "escala", "centro_mm"}], "estilo"?: {"ctb", "transparencia"}}` (hasta 200; `estilo` como en `/api/previa`): una tarea por bloque, `{tareas}` en el mismo orden. El paquete lleva la marca del estilo (`_p<sha6>`, `_t`) y se verifica que su manifiesto traiga ese estilo. El resultado de cada una trae `paquete`, `manifiesto` (relativo a la carpeta del editor), `estilo` (`{ctb, sha256, transparencia}` del manifiesto), `posicion_mm`, `desde_centro_mm`, `detalle` (la entrada del catálogo, con su miniatura y su `estilo`), `en_cache`, `movidos` y `avisos`. 409 sin DXF, con la sesión vencida, con el DXF cambiado o de otro DXF; 404 si el bloque no está; 400 si no cabe. |
| `POST /api/trabajador/detener` | «Detener a la fuerza». `{detenido}`. |
| `GET /api/exportados` | Las entradas de catálogo de lo exportado en esta sesión del servidor (para el editor que se recarga). |
| `GET /api/previas/<id>` | El PNG (`image/png`) de esa tarea de vista previa, con el token en la cabecera. 404 si no existe o ya no está en la caché. |
| `GET /api/tareas/<id>` | Foto de la tarea: `estado` (`en_cola`, `en_curso`, `terminada`, `fallida`, `cancelada`), `avance`, `resultado`, `error` {`codigo`, `mensaje`, `consejo`, `detalle`, `registro`}, `sin_noticias_s`. |
| `POST /api/tareas/<id>/cancelar` | Cancela la tarea. |
| `POST /api/trabajador/reiniciar` | Sale del estado «detenido»: el próximo pedido lanza otro trabajador. |
| `POST /api/latido` | Señal del editor (cada minuto). Cualquier pedido de la API también cuenta. |
| `GET /api/ortofoto` | `{ortofoto}`: la ortofoto de esta sesión (`ficha`, `archivo_plano`, `cambio`, `sistemas`) o `null`. También va en `/api/estado`. |
| `POST /api/ortofoto/elegir` | Cuerpo opcional `{"archivo_plano": "<la ruta que guardó el plano>"}`: solo para abrir el cuadro en esa carpeta (si existe); no se lee nada con ella. Abre el cuadro nativo (`.tif`/`.tiff`), lee solo la cabecera y la deja como la ortofoto de la sesión. `{elegida, ortofoto}` (la ficha trae `bytes` y `modificado`: el editor compara con el plano). 400 si no sirve; 409 si ya hay un cuadro abierto. No usa el trabajador. |
| `POST /api/ortofoto/previa` | Cuerpo `{caja_cad: [x0, y0, x1, y1], mm_por_unidad, crs_dibujo, crs_ortofoto?, px?}` (solo números y códigos EPSG): la ortofoto en esa caja CAD, leída por ventanas y reproyectada. Responde `{id, url, px, cobertura, caja_cad}`. 400 si falta un sistema o no es válido; 409 sin ortofoto o si cambió en el disco. Se atiende en el mismo pedido, de a una, y las hechas se guardan (las últimas 64). |
| `GET /api/ortofoto/previas/<id>` | El PNG (con transparencia donde no hay foto) de esa vista previa. 404 si ya no está. |
| `POST /api/ortofoto/quitar` | Olvida la ortofoto de la sesión (el archivo no se toca). |
| `GET /api/localizacion` | `{localizacion}`: la imagen de localización de esta sesión (`nombre`, `archivo_plano`, `bytes`, `modificado`, `px`, `formato`, `cambio`) o `null`. También va en `/api/estado`. |
| `POST /api/localizacion/elegir` | Cuerpo opcional `{"archivo_plano": "<la ruta que guardó el plano>"}`: solo para abrir el cuadro en esa carpeta. Abre el cuadro nativo (`.png`, `.jpg`, `.jpeg`), comprueba que sea un PNG o JPG que se pueda leer y la deja como la imagen de la sesión. `{elegida, localizacion}`. 400 si no sirve; 409 si ya hay un cuadro abierto. |
| `GET /api/localizacion/imagen` | Los bytes de la imagen (`image/png` o `image/jpeg`), con el token en la cabecera. 404 sin imagen; 409 si cambió en el disco desde que se eligió. |
| `POST /api/localizacion/quitar` | Olvida la imagen de la sesión (el archivo no se toca). |

## Pruebas

Con un **trabajador falso** (`tests/trabajador_falso.py`) que habla el protocolo 1.0, así las
pruebas no dependen de `cde-exporter` ni de un DXF real. Cubren:

- el Job Object: el nieto muere, y si el servidor muere el trabajador también;
- el cliente del protocolo: avance, UTF-8, `status` y `cancel` durante un paso que no se corta,
  versión distinta, sin `ready`, línea que no es JSON, caída y exportador sin `worker`;
- la cola: un pedido a la vez, cancelar en cola, en curso y a la fuerza, dos caídas y reiniciar;
- la carpeta de bloques: fórmula de la página, escala sugerida, notas y bloques mal descritos;
- el servidor: Host, token, Origin, Sec-Fetch-Site, límites, el registro sin token y el comando
  `servidor`;
- el JS en Node.

Etapa 2, además:
- `preview` en el trabajador falso: PNG transparente con una marca en un punto CAD conocido;
- un punto CAD cae en el mismo lugar del papel por la caja y por el PNG (< medio píxel);
- `NO_SESSION` y `DXF_CHANGED`, «Volver a cargar» y cancelar las previas en cola;
- el PNG fuera de la carpeta de previas no se entrega;
- la paridad del JS con Python (página, escala sugerida, regla de «cabe», lista de escalas);
- el plano versión 3 de ida y vuelta, y `componer` con bloques pendientes.

Dos pruebas usan el `cde-exporter` real si está instalado; una carga GUAMO_prueba.dxf (fuera de
git; otra ruta con la variable `COMPONEDOR_DXF_REAL`) y pide la vista previa de un bloque. La
verificación en Edge (`data/verificacion/verificar_servidor_dxf.mjs` y
`verificar_bloques_dxf.mjs`, fuera de git) repite los recorridos en el navegador.
