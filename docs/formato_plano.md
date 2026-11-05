# Formato de plano.json (versión 1)

Un `plano.json` dice **qué detalles van en una hoja y dónde**. Lo lee el comando
`componer`:

```powershell
python -m componedor.cli componer data/planos/mi_plano.json --salida data/output/mi_plano.pdf [--sobrescribir] [--guias]
```

En la subfase 3.3 lo escribirá un editor HTML (arrastrar y soltar), pero el componedor
**siempre** lo revalida todo: el editor nunca es la fuente de la verdad.

## Ejemplo completo

Archivo `data/planos/dos_detalles.json`:

```json
{
  "version": 1,
  "formato": "../../formatos/A1_ERCO.json",
  "plantilla": null,
  "detalles": [
    {"id": "perfil_arriba", "manifiesto": "../input/perfil_k0010.manifest.json", "posicion_mm": [30, 440]},
    {"id": "perfil_abajo",  "manifiesto": "../input/perfil_k0010.manifest.json", "posicion_mm": [237, 40]},
    {"id": "otro",          "manifiesto": "../input/otro.manifest.json", "centrar": true}
  ]
}
```

## Campos

| Campo | Tipo | Obligatorio | Significado |
|---|---|---|---|
| `version` | entero | sí | Versión del formato. Hoy solo `1`. |
| `formato` | texto (ruta) | sí | Formato de hoja (p. ej. `A1_ERCO.json`). |
| `plantilla` | texto (ruta) o `null` | no | PDF del rótulo. Si falta o es `null`, se usa la plantilla del formato. |
| `detalles` | lista (al menos 1) | sí | Los detalles, **en orden de apilado**: el último queda encima. |
| `detalles[].id` | texto no vacío | sí | Nombre del detalle en el plano. **Único**. |
| `detalles[].manifiesto` | texto (ruta) | sí | `<prefijo>.manifest.json` del paquete del exportador. |
| `detalles[].posicion_mm` | `[x, y]` (números) | uno de los dos | Esquina inferior izquierda de la **página** del detalle, en mm de papel. |
| `detalles[].centrar` | `true` | uno de los dos | Centra la página del detalle en el área de dibujo. |

Reglas:

- **Rutas**: todas son relativas a la **carpeta donde está el plano.json** (no al directorio
  desde donde se corre el comando). También se aceptan rutas absolutas.
- **Unidades y coordenadas**: mm, sistema de papel (origen en la esquina inferior izquierda
  de la hoja, X a la derecha, Y hacia arriba), igual que `colocar --posicion`.
- Cada detalle lleva `posicion_mm` **o** `centrar: true`, nunca ambos ni ninguno
  (`centrar: false` junto con `posicion_mm` es válido).
- El mismo paquete puede ir varias veces (con `id` distintos); se verifica una sola vez.
- **Campos desconocidos se rechazan** (un error de tipeo como `"centar"` no pasa en
  silencio). Si hace falta un campo nuevo, se agrega al formato con una versión nueva.
- Todavía **no** se admiten anclas CAD en el plano.json (solo posición o centrado).

Si el archivo no cumple, `componer` muestra **todos** los problemas juntos, uno por línea,
con la ruta del campo, por ejemplo:

```
El plano 'plano.json' no es válido (2 problemas):
- detalles[1].id: 'd1' está repetido (ya lo usa detalles[0]); cada id debe ser único
- detalles[2]: falta posicion_mm [x, y] o centrar: true (uno de los dos)
```

## Qué hace `componer` con el plano

1. Lee y valida el plano.json.
2. Carga el formato y crea la hoja con la plantilla (como `colocar`).
3. Cada detalle pasa por `importar_paquete` (la única puerta: completo, íntegro y
   coherente, con escala física garantizada). Si hay paquetes rechazados **no se genera
   el PDF**: se listan todos, con el `id` del detalle y los motivos.
4. **Posiciones**: la página completa de cada detalle debe quedar dentro de
   `area_dibujo`, con la misma regla estricta que `colocar`. Si no, error con el `id`, los
   mm que se pasa y la zona que invade. **El rótulo es inamovible**: no se permite poner
   detalles sobre él ni sobre otras zonas.
5. **Traslapes entre detalles**: no son error, son advertencias:
   - «Advertencia: las PÁGINAS de 'a' y 'b' se traslapan» (los dibujos no);
   - «ADVERTENCIA FUERTE: los DIBUJOS de 'a' y 'b' se traslapan».

   Mientras el exportador siga dejando un fondo blanco en cada detalle, el que está encima
   tapa al de abajo en la zona del traslape.
6. Inserta los detalles en orden, sin reescalar (ya vienen a escala 1:N) y como vector.
7. Guarda en un archivo temporal y **verifica** el PDF: el dibujo de cada detalle está donde
   dice el plano (±0,1 mm, medido con `get_drawings()` sin el fondo blanco), el marco del
   rótulo no se movió y no hay imágenes nuevas. Si todo pasa, lo renombra a la salida; si
   algo falla, borra el temporal y no queda PDF.
8. Imprime un resumen: cada detalle con su posición final, las advertencias y la ruta del PDF.

Si el PDF de salida ya existe, `componer` no lo pisa salvo con `--sobrescribir`. `--guias`
dibuja las zonas del formato como en `colocar`.
