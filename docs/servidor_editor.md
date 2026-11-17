# Servidor local del editor y «Cargar DXF» (etapa 1)

El editor (`editor.html`) sigue siendo un solo archivo que funciona con doble clic, sin
servidor. Para **cargar un DXF** y ver sus bloques, el editor necesita a alguien que lea el DXF:
el **trabajador** del Exportador Vectorial (`cde-exporter worker`). Como una página web no
puede lanzar programas, `Abrir editor.bat` levanta un **servidor local** que hace de puente.

```
Edge  ──HTTP (127.0.0.1, token)──>  servidor del Componedor  ──JSON por stdin/stdout──>  cde-exporter worker
```

Etapa 1 (esta): cargar el DXF y ver la carpeta de bloques. Todavía **no** se arrastran bloques
al plano ni se exporta (etapas 2 y 3).

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

   Al final, «No exportables» (bloques anónimos, XREF…) y los avisos del trabajador.

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
"exportador": {"comando": "cde-exporter", "trabajo": "data/cache_exportador", "margen_mm": 5}
```

| Clave | Obligatoria | Qué es |
|---|---|---|
| `comando` | sí | El comando del exportador (se busca en el PATH) o una lista `[programa, argumentos…]`. El servidor le agrega `worker --work-dir <trabajo>`. |
| `trabajo` | sí | Carpeta del trabajador (sus temporales y caché de vistas previas) y de los registros. Se crea. Está en `data/`, fuera de git. |
| `margen_mm` | no (5) | Margen de página con que se exportará; se manda en `load` y vale para toda la sesión del trabajador. |

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
- **Ninguna ruta entrega archivos del disco** salvo el propio `editor.html`, y ninguna recibe rutas
  ni opciones para el comando del exportador. El DXF lo elige el cuadro nativo y se valida
  (archivo que existe, extensión `.dxf`) antes de mandarlo al trabajador.
- **Firmas**: no cambia nada. El servidor no tiene ninguna ruta hacia `firmas/` y el HTML solo
  trae los nombres de las personas. Las imágenes solo las lee `componer`, para el PDF.
- Los nombres de bloque vienen del DXF: el editor los escribe siempre como texto, nunca como
  HTML.

## Cómo se habla con el trabajador

El Componedor **no importa código del exportador**: lo lanza como comando externo y le habla JSON
por líneas (protocolo 1.0; contrato en `docs/protocolo_trabajador.md` del repositorio del
exportador, aprobado el 2026-11-17 y comparado con esta implementación). `load` se pide con el
margen de `componedor.json`, `units: null` e `include_layers: false`: la tabla de capas todavía
no se usa y así la carga ahorra 1–2 s en bloques grandes.

- **Arranque perezoso**: el trabajador se lanza la primera vez que se pide «Cargar DXF», no al abrir
  el editor. El servidor espera el mensaje `ready` hasta 30 s y comprueba la versión mayor 1 del
  protocolo y del manifiesto.
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
| `GET /api/tareas/<id>` | Foto de la tarea: `estado` (`en_cola`, `en_curso`, `terminada`, `fallida`, `cancelada`), `avance`, `resultado`, `error` {`codigo`, `mensaje`, `consejo`}, `sin_noticias_s`. |
| `POST /api/tareas/<id>/cancelar` | Cancela la tarea. |
| `POST /api/trabajador/reiniciar` | Sale del estado «detenido»: el próximo pedido lanza otro trabajador. |
| `POST /api/latido` | Señal del editor (cada minuto). Cualquier pedido de la API también cuenta. |

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

Una prueba usa el `cde-exporter` real si está instalado. La verificación en Edge
(`data/verificacion/verificar_servidor_dxf.mjs`, fuera de git) repite el recorrido completo en
el navegador.
