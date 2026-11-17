# proyecto.json — datos que se repiten en todos los planos de un proyecto

**Versión 1** (subfase 4.3b). Lo lee `editor --proyecto <proyecto.json>` (y `preparar-editor`)
para **prellenar el rótulo de un plano NUEVO** en el editor. Al guardar, los valores quedan
**copiados** en el plano.json: `componer` no lee proyecto.json y un plano no depende de él.
Un plano que se **abre** en el editor no se toca (lo que trae el plano manda).

Lo valida `componedor/proyecto.py` contra el formato al generar el editor. Si tiene errores, el
editor no se genera y se listan **todos** los problemas juntos.

## Ejemplo

```json
{
  "version": 1,
  "nombre": "PARQUE SOLAR FOTOVOLTAICO",
  "prefijo_no_plano": "ERCO-PSF-CIV-PL-",
  "firmas": {
    "dibujo": {"nombre": "LUIS Á. NÚÑEZ P.", "matricula": "PRACTICANTE"},
    "diseno": {"nombre": "MARÍA JOSÉ OCAÑA", "matricula": "25202-123456"},
    "reviso": {"nombre": ["ANDRÉS GÓMEZ", "(DIRECTOR TÉCNICO)"], "matricula": "25202-654321"},
    "aprobo": {"nombre": "JULIÁN PÉREZ", "matricula": "25202-111222"}
  }
}
```

## Claves

| Clave | Obligatoria | Qué es | Va al plano como |
|---|---|---|---|
| `version` | sí | Siempre `1`. | — |
| `nombre` | no | Nombre del proyecto. **Informativo**: el editor lo muestra; no va al rótulo. | — |
| `disenador`, `revisor` | no | **Retirados**: el rótulo ya no tiene DISEÑADOR ni REVISOR (plantilla v3). Un proyecto viejo que los traiga sigue valiendo; se ignoran y `editor --proyecto` avisa una vez. | — |
| `prefijo_no_plano` | no | Comienzo del No. PLANO; el usuario completa el número en el editor. | `rotulo.no_plano` |
| `firmas` | no | Por fila (`dibujo`, `diseno`, `reviso`, `aprobo`): solo `nombre` y `matricula`. | `rotulo.firmas.<fila>.nombre` / `.matricula` |

Reglas de los textos (las mismas que los valores del rótulo en `componer`,
[formato_plano.md](formato_plano.md)):

- texto o número entero;
- en una celda de **varias líneas** (nombre de REVISÓ: 2) también una
  lista de líneas explícitas, `["LÍNEA 1", "LÍNEA 2"]`;
- en una celda de **una sola línea**, sin saltos de línea (`prefijo_no_plano` siempre es una
  línea).

No se admiten (error claro): claves desconocidas, filas de firmas que el formato no tiene, y
en las firmas otras columnas que `nombre` y `matricula` (la firma en imagen y la fecha se
eligen en cada plano). El archivo va en **UTF-8**.

Si cabe o no cada texto en su celda lo comprueba `componer` al componer el plano (y el editor,
desde la subfase 4.3e).

## Dónde guardarlo

En la carpeta del proyecto, junto a sus planos. Tiene nombres y matrículas (datos personales):
no lo suba al repositorio si es de un proyecto real de ERCO (`data/` no se versiona).
