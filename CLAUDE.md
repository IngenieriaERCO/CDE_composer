# CLAUDE.md — Componedor PDF (ERCO)

## Qué es este proyecto

Aplicación en Python que arma planos físicos exactos (por ahora A1) a partir de los
detalles vectoriales que entrega el **Exportador Vectorial** (repositorio CDE_manager).
Hace lo que hoy se hace a mano en AutoCAD (Layout + ventanas gráficas + rótulo + plot a PDF),
pero sin abrir CAD.

Es un servicio **distinto** del exportador. No importa código del exportador; solo
lee sus paquetes de salida (PDF + manifiesto JSON).

## Quién trabaja aquí

- Usuario: practicante de ingeniería civil. Conoce AutoCAD/Civil 3D muy bien,
  Python a nivel básico. Explica en español, con términos de planos (hoja, marco,
  ventana gráfica, escala 1:N, rótulo), paso a paso.
- Todo el texto para el usuario (mensajes, errores, informes, README) en **español**.
  Código, nombres de funciones y variables pueden ir en español o inglés, pero
  consistentes dentro de cada módulo.

## Reglas de trabajo

1. **Una subfase a la vez.** No adelantar trabajo de subfases siguientes.
2. **Antes de escribir código**: explicar en pocas líneas qué archivos vas a crear o
   tocar y por qué. Si algo no está claro, preguntar.
3. **Módulos pequeños** con una sola responsabilidad. Preferir archivos nuevos a
   reescribir archivos existentes.
4. **Cada función nueva lleva prueba** en `tests/`. Correr `python -m pytest -q`
   al terminar y reportar el número de pruebas.
5. **Nunca rasterizar** los detalles: todo lo que venga como vector debe seguir
   siendo vector en el PDF final.
6. **Commits**: solo cuando el usuario lo pida. Uno por fase cerrada, mensaje
   `Fase N: ...`. No hacer push sin que el usuario lo pida.
7. No subir archivos de `data/` ni planos de ERCO al repositorio (confidenciales).
8. Mantener el `README.md` y `pyproject.toml` al día con lo que realmente existe.
9. Mantener `docs/estado_proyecto.md` actualizado al cerrar cada subfase
   (qué se hizo, pruebas, pendientes).

## Stack (mínimo a propósito)

- Python 3.12, entorno `.venv`.
- **PyMuPDF** (`import pymupdf`) para crear páginas, dibujar y colocar PDFs como
  vector (`Page.show_pdf_page`).
- **pytest** para pruebas.
- No agregar otras dependencias sin justificarlo y preguntar.

## Convenciones de unidades y coordenadas

- **Todo en milímetros** en configuración, modelo e interfaz.
- Conversión a puntos PDF solo en la capa de dibujo: `1 mm = 72 / 25.4 pt`.
- Sistema de papel: origen en la **esquina inferior izquierda** de la hoja, X hacia
  la derecha, Y hacia arriba (igual que el Layout de AutoCAD). PyMuPDF usa Y hacia
  abajo: la conversión se hace en un solo módulo de transformaciones.
- Tolerancia de validación de medidas: **±0,1 mm**.
- Matriz `pdf.drawing.cad_to_page` del manifiesto: `[a, b, c, d, e, f]` con
  `x_pag = a*X + c*Y + e`, `y_pag = b*X + d*Y + f` (punto CAD → mm de la página del detalle).
- Unidades: CAD en unidades del dibujo (p. ej. m); página en mm, origen arriba-izquierda,
  Y abajo (`units "mm"`, `origin "top-left"`, `y_axis "down"`). 1:50 en m → a = 20, d = −20.
- La matriz ya incluye margen y centrado del dibujo: **nunca suponer un margen fijo**; usar
  la matriz y `page_bounds_mm`.
- La hoja se crea en su orientación real (A1 horizontal = 841 × 594 mm, rotación 0).
  No usar el truco de AutoCAD de hoja vertical con `/Rotate`.

## Formato A1 ERCO (medido del rótulo oficial, Layout "01")

Referencia: `_01_Rotulo_para_diseños_externos_Pliego_V2.dwg`, plot con
DWG To PDF.pc3, `ISO_full_bleed_A1_(594.00_x_841.00_MM)`, escala 1:1, mm,
CTB_ERCO_V2.ctb. Coordenadas en mm, origen inferior izquierdo de la hoja horizontal.

| Elemento | X min | Y min | X max | Y max | Tamaño |
|---|---|---|---|---|---|
| Hoja | 0 | 0 | 841 | 594 | 841 × 594 |
| Marco (margen 12,7 en los 4 lados) | 12,7 | 12,7 | 828,3 | 581,3 | 815,6 × 568,6 |
| Área de dibujo (ventana gráfica principal) | 22,7 | 22,7 | 662,4 | 571,3 | 639,7 × 548,6 |
| Columna del rótulo | 672,4 | 12,7 | 828,3 | 581,3 | 155,9 × 568,6 |
| Localización (dentro del rótulo) | 672,4 | 424,4 | 828,3 | 571,2 | 155,9 × 146,8 |
| Notas | 672,4 | 270,5 | 828,3 | 424,4 | |
| Convenciones | 672,4 | 137,7 | 828,3 | 270,5 | |
| Cajetín (revisiones, logo, título, firmas, escala, n.º plano) | 672,4 | 12,7 | 828,3 | 137,7 | |

Separaciones: el área de dibujo queda a 10 mm del marco y a 10 mm de la columna del rótulo.

## Fases vigentes

**Fase 1 — Núcleo de composición PDF**: hoja A1 vacía (horizontal y vertical), marco
y márgenes, colocar un PDF vectorial en una región conocida, transformaciones
CAD (m) → papel (mm) → PDF (pt), validación con geometría de referencia.

**Fase 2 — Ingesta y validación del extractor**: localizar PDF + manifiesto JSON,
verificar integridad (hash) y coherencia, leer escala, dimensiones y matriz
CAD → página, rechazar entradas inválidas con mensajes claros, inventario de detalles.

Fuera de alcance por ahora: otros tamaños de hoja, cuadrícula de coordenadas,
localización automática (QGIS), estilos de impresión CTB, Microsoft Graph/SharePoint.

## Estructura del repositorio

```
Componedor/   (carpeta raíz, en Documents)
  src/componedor/        # paquete
  tests/                 # pruebas pytest
  formatos/              # definiciones de hoja (A1_ERCO.json) — desde la subfase 1.2
  plantillas/            # PDF del rótulo limpio — cuando se incorpore
  data/input/            # paquetes del exportador (no se versiona)
  data/output/           # resultados (no se versiona)
  docs/estado_proyecto.md
  CLAUDE.md  README.md  pyproject.toml  .gitignore
```

Ejecución: `python -m componedor.cli <subcomando> ...`
