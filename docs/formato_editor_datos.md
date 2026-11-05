# Datos del editor de planos (`editor_datos.json`, versión 1)

El comando `preparar-editor` deja en una carpeta todo lo que necesita el editor HTML de
planos (subfase 3.3) para mostrar la hoja A1 completa y dejar arrastrar los detalles:

```powershell
python -m componedor.cli preparar-editor data/input --formato formatos/A1_ERCO.json --salida data/editor [--sobrescribir]
```

```
data/editor/
  editor_datos.json      estructura de abajo
  plantilla.png          la hoja con el rótulo, SIN detalles (lado mayor: 1600 px)
  miniaturas/<id>.png    una por detalle aceptado (lado mayor: 600 px)
```

Las imágenes son **solo para mostrar** en el editor. El editor escribe un `plano.json`
(ver [formato_plano.md](formato_plano.md)) y el PDF final lo genera siempre `componer`,
vectorial, **revalidando todo**: estos datos nunca son la fuente de la verdad.

Si la carpeta ya tiene contenido, `preparar-editor` no la pisa salvo con `--sobrescribir`;
en ese caso reemplaza solo lo que genera (`editor_datos.json`, `plantilla.png` y las
miniaturas, borrando las viejas) y no toca nada más.

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
  "imagen_plantilla": {"archivo": "plantilla.png", "ancho_px": 1600, "alto_px": 1131},
  "zonas": [
    {"nombre": "area_dibujo", "rect_mm": [22.7, 22.7, 662.4, 571.3], "editable": true},
    {"nombre": "rotulo", "rect_mm": [672.4, 12.7, 828.3, 581.3], "editable": false}
  ],
  "elementos_plantilla": [
    {"nombre": "rosa_vientos", "rect_mm": [612.56, 51.55, 651.52, 90.50]}
  ],
  "detalles": [
    {
      "id": "perfil_k0010",
      "manifiesto": "../input/perfil_k0010.manifest.json",
      "bloque": "Perfil_K0010",
      "escala": 50.0,
      "tamano_pagina_mm": [416.98, 119.40],
      "limites_dibujo_mm": [10.43, 5.74, 406.55, 113.66],
      "cabe": true,
      "notas": [],
      "miniatura": {"archivo": "miniaturas/perfil_k0010.png", "ancho_px": 600, "alto_px": 172}
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
| `imagen_plantilla` | `plantilla.png` y su tamaño real en píxeles. |
| `zonas[]` | Cada zona del formato con `rect_mm` `[x0, y0, x1, y1]`. **Solo `area_dibujo` es `editable: true`**; el rótulo y las demás zonas están bloqueadas. |
| `elementos_plantilla[]` | Cosas fijas del rótulo dentro del área de dibujo (rosa de los vientos, recuadro de capas). Se pueden tapar, pero `componer` lo advierte. |
| `detalles[]` | Solo paquetes **aceptados** (completos, íntegros, coherentes, escala garantizada). |
| `detalles[].id` | Id sugerido para el plano (= prefijo del paquete; único). |
| `detalles[].manifiesto` | Ruta del manifiesto, para escribir en `plano.json`. |
| `detalles[].tamano_pagina_mm` | `[ancho, alto]` de la página del detalle: lo que ocupa en la hoja. |
| `detalles[].limites_dibujo_mm` | Caja del dibujo real (`page_bounds_mm`) en mm, relativa a la **esquina inferior izquierda de la página del detalle**, Y hacia arriba. Con la página en `(x, y)`, el dibujo queda en `[x + x0, y + y0, x + x1, y + y1]`. |
| `detalles[].cabe` | Si la página cabe por tamaño en `area_dibujo` (misma regla que `colocar`). Uno que no cabe se lista, pero no se puede colocar. |
| `detalles[].notas` | Notas del inventario (no cabe, escala sugerida aproximada, duplicado). |
| `detalles[].miniatura` | PNG del detalle y su tamaño en píxeles. |
| `rechazados[]` | Paquetes rechazados con sus motivos (`[categoría] texto`, los del importador). El editor los lista pero **no se pueden arrastrar**. |

La aceptación y los motivos salen del inventario (`inventario.construir_inventario`, que usa
el importador): `preparar-editor` no repite ninguna validación.
