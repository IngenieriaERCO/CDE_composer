# Datos del editor de planos (`editor_datos.json`, versión 1)

El comando `preparar-editor` deja en una carpeta todo lo que necesita el editor HTML de
planos (subfase 3.3) para mostrar la hoja A1 completa y dejar arrastrar los detalles. El
comando `editor` arma lo mismo en una carpeta temporal, lo incrusta en `editor.html` y no deja
nada de esto al lado: `preparar-editor` sirve para revisar estos archivos por separado.

```powershell
python -m componedor.cli preparar-editor data/input --formato formatos/A1_ERCO.json --salida resultados/datos_editor [--sobrescribir]
```

```
resultados/datos_editor/
  editor_datos.json      estructura de abajo
  plantilla.png          la hoja con el rótulo, SIN detalles y SIN la rosa de los vientos
                         (lado mayor: 1600 px)
  plantilla.svg          la misma hoja en VECTOR (subfase 4.3f): trazos y textos como curvas;
                         el editor.html la incrusta en lugar del PNG (nítida al acercar)
  rosa.png               la rosa sola, transparente (lado mayor: 600 px); solo si el formato
                         tiene plantilla y declara la rosa
  simbolos/<id>.png      cada símbolo de convenciones, transparente, a 20 px/mm (subfase 4.3a)
  miniaturas/<id>.png    una por detalle aceptado (lado mayor: 1400 px; transparente si el
                         detalle no tiene fondo de página, opaca si lo tiene)
```

Desde la subfase 4.1 la rosa se puede mover u ocultar: por eso `plantilla.png` sale sin ella
(se quita igual que en `componer`) y el editor la dibuja con `rosa.png` en su posición actual.

Las imágenes son **solo para mostrar** en el editor. El editor escribe un `plano.json`
(ver [formato_plano.md](formato_plano.md)) y el PDF final lo genera siempre `componer`,
vectorial, **revalidando todo**: estos datos nunca son la fuente de la verdad.

Si la carpeta ya tiene contenido, `preparar-editor` no la pisa salvo con `--sobrescribir`;
en ese caso reemplaza solo lo que genera (`editor_datos.json`, `plantilla.png`,
`plantilla.svg` y las miniaturas, borrando las viejas) y no toca nada más.

## Coordenadas

- Todo en **mm**, sistema de papel: origen en la esquina inferior izquierda de la hoja,
  X a la derecha, **Y hacia arriba** (igual que `plano.json` y `colocar --posicion`).
- Las imágenes tienen el origen arriba a la izquierda con Y hacia abajo (como cualquier
  imagen). Para pasar de mm a píxeles use por separado
  `ancho_px / ancho_mm` en X y `alto_px / alto_mm` en Y (los píxeles se redondean hacia
  arriba: p. ej. 1600 x 1131 px para 841 x 594 mm) y recuerde invertir Y.
- Las rutas (`formato`, `manifiesto`, imágenes) son relativas a la carpeta de los datos.
  Si el editor guarda el `plano.json` en esa misma carpeta, puede copiarlas tal cual.

## Estructura

```json
{
  "version": 1,
  "formato": "../../formatos/A1_ERCO.json",
  "hoja": {"ancho_mm": 841.0, "alto_mm": 594.0},
  "imagen_plantilla": {"archivo": "plantilla.png", "ancho_px": 1600, "alto_px": 1131,
                       "svg": {"archivo": "plantilla.svg"}},
  "zonas": [
    {"nombre": "area_dibujo", "rect_mm": [22.7, 22.7, 662.4, 571.3], "editable": true},
    {"nombre": "rotulo", "rect_mm": [672.4, 12.7, 828.3, 581.3], "editable": false}
  ],
  "elementos_plantilla": [
    {"nombre": "rosa_vientos", "rect_mm": [615.94, 25.21, 654.92, 64.21]}
  ],
  "rosa_vientos": {
    "nombre": "rosa_vientos",
    "rect_mm": [615.94, 25.21, 654.92, 64.21],
    "imagen": {"archivo": "rosa.png", "ancho_px": 600, "alto_px": 601}
  },
  "detalles": [
    {
      "id": "perfil_k0010",
      "manifiesto": "../input/perfil_k0010.manifest.json",
      "bloque": "Perfil_K0010",
      "escala": 50.0,
      "tamano_pagina_mm": [416.98, 119.40],
      "limites_dibujo_mm": [10.43, 5.74, 406.55, 113.66],
      "cabe": true,
      "tiene_fondo": false,
      "notas": [],
      "miniatura": {"archivo": "miniaturas/perfil_k0010.png", "ancho_px": 1400, "alto_px": 401}
    }
  ],
  "rechazados": [
    {"prefijo": "malo", "manifiesto": "../input/malo.manifest.json",
     "motivos": ["[escala] escala física no garantizada: ..."]}
  ]
}
```

| Campo | Significado |
|---|---|
| `version` | Versión de esta estructura (hoy 1). |
| `formato` | Ruta del formato, para escribir en `plano.json`. |
| `hoja` | Tamaño de la hoja en mm. |
| `imagen_plantilla` | `plantilla.png` y su tamaño real en píxeles (el lienzo del editor usa esos píxeles como unidades). **(4.3f, aditivo):** `svg` → `plantilla.svg`, la misma hoja en vector; el editor.html la incrusta en lugar del PNG. Sin `svg` (datos anteriores), el editor usa el PNG. |
| `zonas[]` | Cada zona del formato con `rect_mm` `[x0, y0, x1, y1]`. **Solo `area_dibujo` es `editable: true`**; el rótulo y las demás zonas están bloqueadas. |
| `elementos_plantilla[]` | Cosas fijas del rótulo dentro del área de dibujo, en su lugar de la plantilla (hoy solo la rosa de los vientos). Se pueden tapar, pero `componer` lo advierte. |
| `rosa_vientos` | **(Agregado en la subfase 4.1; aditivo.)** La rosa movible: `rect_mm` es su lugar original en la plantilla y `imagen` su PNG (`null` si el formato no tiene plantilla). `null` si el formato no declara la rosa. Para las advertencias, el editor reemplaza en `elementos_plantilla` la rosa por su rectángulo actual (u omite la rosa si está oculta), igual que `rosa.elementos_visibles` en `componer`. |
| `detalles[]` | Solo paquetes **aceptados** (completos, íntegros, coherentes, escala garantizada). |
| `detalles[].id` | Id sugerido para el plano (= prefijo del paquete; único). |
| `detalles[].manifiesto` | Ruta del manifiesto, para escribir en `plano.json`. |
| `detalles[].tamano_pagina_mm` | `[ancho, alto]` de la página del detalle: lo que ocupa en la hoja. |
| `detalles[].limites_dibujo_mm` | Caja del dibujo real (`page_bounds_mm`) en mm, relativa a la **esquina inferior izquierda de la página del detalle**, Y hacia arriba. Con la página en `(x, y)`, el dibujo queda en `[x + x0, y + y0, x + x1, y + y1]`. |
| `detalles[].cabe` | Si la página cabe por tamaño en `area_dibujo` (misma regla que `colocar`). Uno que no cabe se lista, pero no se puede colocar. |
| `detalles[].cad_a_pagina` | **(Agregado con la ortofoto; aditivo.)** La matriz `cad_to_page` del manifiesto `[a, b, c, d, e, f]` (CAD → mm de página, origen arriba-izquierda, Y abajo). Con ella el editor sabe qué caja CAD cubre la página del detalle, para poner la ortofoto detrás. `null` si el manifiesto no la trae. |
| `detalles[].mm_por_unidad` | **(Agregado con la ortofoto.)** mm reales por unidad CAD (`units.millimeters_per_unit`: 1000 si el dibujo está en m). |
| `detalles[].tiene_fondo` | **(Agregado en la subfase 3.4; aditivo, el resto no cambia.)** `true` si el PDF trae el fondo blanco de página completa (paquetes antiguos del exportador), `false` si no. Misma regla con la que `componer` lo detecta (`comprobacion_dibujo.tiene_fondo_de_pagina`). Decide si la miniatura es transparente u opaca y qué advertencias de traslape aplican. Si falta (datos anteriores), el editor supone `true`. |
| `detalles[].notas` | Notas del inventario (no cabe, escala sugerida aproximada, duplicado). |
| `detalles[].miniatura` | PNG del detalle y su tamaño en píxeles. |
| `rotulo` | **(Agregado en la subfase 4.3a; aditivo.)** `null` si el formato no tiene sección `rotulo`. Si la tiene: `definicion` (celdas del rótulo en mm, alturas, líneas, `formato_fecha`; desde la 4.3f cada tabla trae `cuerpo_y`: `[abajo, arriba]` del cuerpo de la tabla sin encabezado, o `null`, para la caja de la firma de `firmas.caja_firma`), `fuente` (`nombre`, `altura_mayusculas`, `anchos_em`: ancho de avance de cada carácter en fracciones del em, el mismo que usa `componer`, y —4.3b— `rangos_unicode`: todos los caracteres que la fuente tiene, como rangos `[desde, hasta]` de puntos de código, para marcar los faltantes igual que `componer`; —4.3f— `ascenso_em` y `descenso_em`: la caja de línea de la fuente en fracciones del em, el descenso positivo hacia abajo, la misma de `Fuente.caja_vertical_mm`, para colocar las etiquetas «ESC: 1:N» como `componer`), `notas` (catálogo de notas típicas de `--notas`, o `null`: `grupos` → `archivos` → `notas` con `texto`, `vinetas` y `origen`, más `avisos` y `problemas` de lectura por archivo; desde el ajuste de la 4.3c cada archivo trae también `ruta_plano`, su ruta vista desde la carpeta del editor —donde va el plano.json— con «/», y `absoluta`, para saber qué notas típicas ya entran por `rotulo.notas.archivos`), `simbolos` (cada símbolo de convenciones: `id`, `descripcion`, `opacidad`, `tamano_dibujo_mm`, `margen_mm` e `imagen` → `simbolos/<id>.png`, transparente, 20 px/mm, con su opacidad) y `avisos`. **(Subfase 4.3b, aditivo):** `personas_firmas` (de `--firmas`: lista de NOMBRES de las carpetas de personas, ordenada; `null` sin `--firmas`) y `proyecto` (de `--proyecto`: el proyecto.json ya validado, ver [formato_proyecto.md](formato_proyecto.md); `null` sin `--proyecto`). **Nunca** trae imágenes de firmas, sus nombres de archivo ni la carpeta. |
| `rechazados[]` | Paquetes rechazados con sus motivos (`[categoría] texto`, los del importador). El editor los lista pero **no se pueden arrastrar**. |

La aceptación y los motivos salen del inventario (`inventario.construir_inventario`, que usa
el importador): `preparar-editor` no repite ninguna validación.
