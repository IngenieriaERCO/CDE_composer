# Instalar y usar el Componedor y el Exportador en otro PC

Guía para dejar funcionando, en un PC con Windows, los dos programas:

- **Exportador Vectorial** (repositorio `CDE_Extractor`): lee el DXF y exporta cada bloque como
  paquete (PDF vectorial + TXT + manifiesto). Su orden `cde-exporter worker` es la que usa el
  editor.
- **Componedor** (repositorio `CDE_Composer`): el editor de planos (en el navegador) y `componer`,
  que arma el plano A1 en PDF con el rótulo de ERCO.

Se trabaja siempre en la rama **`dev`** de cada repositorio (`main` está protegido). Tiempo
aproximado: 20 minutos.

## 1. Lo que hace falta en el PC

| Programa | Para qué | Cómo comprobarlo (PowerShell) |
|---|---|---|
| **Python 3.12** (64 bits) | Los dos programas | `py -3.12 --version` → `Python 3.12.x` |
| **Git** | Bajar los repositorios | `git --version` |
| **Microsoft Edge** (o Chrome) | El editor | Viene con Windows |
| Node.js LTS (opcional) | Solo para las pruebas del editor (`pytest` salta esas pruebas si no está) | `node --version` |

Al instalar Python desde python.org, marque **«Add python.exe to PATH»**. El lanzador `py` queda
instalado con él.

## 2. Bajar los dos repositorios en la misma carpeta

En PowerShell (la carpeta `C:\ERCO` es un ejemplo; puede ser otra, pero que no esté dentro de
OneDrive para que los DXF grandes no se sincronicen):

```powershell
mkdir C:\ERCO
cd C:\ERCO
git clone https://github.com/IngenieriaERCO/CDE_Extractor.git
git clone https://github.com/IngenieriaERCO/CDE_Composer.git
cd C:\ERCO\CDE_Extractor; git checkout dev; git branch --show-current   # debe decir: dev
cd C:\ERCO\CDE_Composer;  git checkout dev; git branch --show-current   # debe decir: dev
```

Queda así:

```
C:\ERCO\
  CDE_Extractor\     ← el Exportador Vectorial
  CDE_Composer\      ← el Componedor
```

Para traer cambios más adelante: `git pull` en cada carpeta, siempre en `dev`. No hacer
`git push` a `main`.

## 3. Instalar el Exportador (`CDE_Extractor`)

```powershell
cd C:\ERCO\CDE_Extractor
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

`pip install -e` lo instala «en modo editable»: el programa se ejecuta desde esta carpeta, así
que un `git pull` lo actualiza sin reinstalar (solo hay que reinstalar si cambian las
dependencias de `pyproject.toml`).

**El archivo `.env`** (configuración local del exportador; no va a git):

```powershell
copy .env.example .env
notepad .env
```

Lo que importa para el Componedor son las fuentes: `CDE_FONT_FALLBACK` (archivo de respaldo,
por defecto `arial.ttf`), `CDE_FONT_SUBSTITUTIONS` (JSON familia → archivo) y `CDE_FONT_FOLDER`
(carpeta de fuentes del proyecto). Los demás valores se pueden dejar como vienen. No escriba
contraseñas ni tokens en ese archivo.

**Comprobar** que tiene la orden del trabajador:

```powershell
.\.venv\Scripts\cde-exporter.exe worker --help
```

Debe mostrar `usage: cde-exporter worker [-h] [--work-dir WORK_DIR] [--preview-cache-mb …]`.
Si dice `invalid choice: 'worker'`, la copia no está en `dev` o está vieja: `git checkout dev`,
`git pull` y repetir el `pip install -e ".[dev]"`.

## 4. Instalar el Componedor (`CDE_Composer`)

```powershell
cd C:\ERCO\CDE_Composer
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Sus dependencias son PyMuPDF y rasterio (y pytest para las pruebas). rasterio lee las ortofotos
GeoTIFF; trae GDAL y numpy ya compilados (unos 44 MB de descarga y 150 MB instalado), así que no
hay que instalar GDAL aparte.

**Archivos de ERCO que NO están en git** (son confidenciales o datos personales). Hay que
copiarlos a mano, con estos nombres exactos, desde donde los tenga el equipo:

| Copiar a | Qué es | Sin él |
|---|---|---|
| `plantillas\rotulo_A1_ERCO_v3.pdf` | El rótulo A1 de ERCO (plantilla del plano) | `componer` y el editor no tienen rótulo |
| `simbolos\biblioteca\*.pdf` | La biblioteca de símbolos de convenciones, un PDF por símbolo (`simbolos\indice.json` sí está en git). Si le pasan la versión vieja, `simbolos\convenciones_erco.pdf`, cópiela ahí y corra `python -m componedor.cli migrar-simbolos --config componedor.json` | No se pueden poner símbolos en las convenciones (líneas y rellenos sí) |
| `firmas\<persona>\firma.png` | Una carpeta por persona con su firma | Las firmas no salen en imagen |
| `notas\…\*.txt` | El catálogo de notas típicas | El editor no ofrece notas típicas |

**Comprobar** que todo está bien instalado (tarda unos minutos):

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Debe terminar con `… passed` (unas pocas pruebas pueden aparecer como «skipped»: son las que
usan Node, el exportador real o los archivos de ERCO que falten).

## 5. Conectar el Componedor con el Exportador

El editor lanza el trabajador con el comando de `componedor.json`, sección `exportador`:

```json
"exportador": {"comando": "cde-exporter", "trabajo": "data/cache_exportador", "margen_mm": 5}
```

Con `"cde-exporter"`, Windows lo busca en el PATH, y el que se instaló en el punto 3 está en
`C:\ERCO\CDE_Extractor\.venv\Scripts`, que **no** está en el PATH. Hay dos formas; use una:

- **A (recomendada): la ruta completa en `componedor.json`.** Cambie la línea por:

  ```json
  "exportador": {"comando": "C:\\ERCO\\CDE_Extractor\\.venv\\Scripts\\cde-exporter.exe",
                 "trabajo": "data/cache_exportador", "margen_mm": 5}
  ```

  (en JSON cada `\` se escribe `\\`). Es un ajuste de ESTE PC: no lo suba a git.

- **B: agregar esa carpeta al PATH** de Windows (Configuración → Sistema → Acerca de →
  Configuración avanzada del sistema → Variables de entorno → `Path` → Nuevo →
  `C:\ERCO\CDE_Extractor\.venv\Scripts`). Cierre y vuelva a abrir las ventanas de PowerShell.

Comprobar (desde `C:\ERCO\CDE_Composer`):

```powershell
.\.venv\Scripts\python.exe -c "from componedor.configuracion import leer_config_exportador as l; from componedor.trabajador import resolver_comando as r; print(r(l('componedor.json').comando))"
```

Debe mostrar la ruta del `cde-exporter.exe` (entre corchetes, por ejemplo
`['C:\\ERCO\\CDE_Extractor\\.venv\\Scripts\\cde-exporter.exe']`). Si dice «No se encontró el
comando…», revise el
punto anterior.

## 6. Usar el editor

1. **Doble clic en `Abrir editor.bat`** (en `C:\ERCO\CDE_Composer`). Genera el editor y abre Edge
   en `http://127.0.0.1:<puerto>/?t=…`. **Deje abierta la ventana negra**: es el servidor local;
   al cerrarla se apagan el servidor y el trabajador. Solo atiende a este PC (127.0.0.1).
2. **Cargar DXF**: abre el cuadro de Windows para elegir el dibujo. La primera vez el trabajador
   tarda en arrancar (hasta un minuto después de instalar o actualizar el exportador; luego unos
   10 s). Aparece la carpeta del DXF con sus bloques, su tamaño real y la escala sugerida.
3. **Agregar al plano** pone el bloque como caja exacta con su vista previa. La escala se cambia
   con el selector, escribiéndola («1:3500»), con las teclas + y −, con el tirador de la esquina
   o con «Ajustar a la hoja».
4. **Exportar bloques del plano** crea los paquetes (uno por bloque, con barra de avance,
   Cancelar y «Detener a la fuerza»). Cada bloque exportado pasa a ser un detalle normal.
5. Llene el **rótulo**, las **notas** y las **convenciones** en el panel derecho y **Guardar
   plano** (guárdelo en `planos\` o en `editor\`).
6. **Componer**: arrastre el `plano.json` sobre **`Componer.bat`**. El PDF queda en
   `resultados\<nombre del plano>.pdf` y se abre solo.

Sin el exportador (o abriendo `editor\editor.html` con doble clic) el editor funciona igual
para colocar paquetes que ya existen; solo falta «Cargar DXF».

Guías detalladas: `docs\editor.md`, `docs\servidor_editor.md`, `docs\formato_plano.md`.

## 7. Carpetas que se crean solas

Ninguna va a git (están en `.gitignore`):

| Carpeta | Qué tiene |
|---|---|
| `editor\` | `editor.html` (se regenera cada vez con `Abrir editor.bat`) y los planos que guarde ahí |
| `resultados\` | Los PDF que deja `Componer.bat` |
| `data\cache_exportador\` | La carpeta del trabajador: vistas previas (`previews\`) y los registros `trabajador.log`, `componedor.log` y `servidor.log` |
| `data\input\dxf\<DXF>\` | Los paquetes que publica «Exportar» (uno por bloque y escala) |
| `_para_borrar\paquetes_<fecha>\` | Los paquetes viejos que «Exportar» reemplazó: se **mueven** aquí, nunca se borran. Revíselos y bórrelos a mano cuando quiera |
| `planos\` | Donde conviene guardar los `plano.json` (se crea a mano) |

Los DXF pueden estar en cualquier carpeta; no se copian.

## 8. Si algo falla

| Lo que se ve | Qué hacer |
|---|---|
| «El cde-exporter instalado no tiene la orden «worker»» | El exportador está viejo o no está en `dev`: en `CDE_Extractor`, `git checkout dev`, `git pull` y `pip install -e ".[dev]"` (punto 3). |
| «No se encontró el comando «cde-exporter»…» | El Componedor no encuentra el exportador: punto 5 (ruta completa o PATH). |
| «El trabajador del exportador no respondió en 60 s» | La primera vez después de instalar o actualizar puede tardar. Repita; si sigue, mire `data\cache_exportador\trabajador.log`. |
| «Cargar DXF» aparece desactivado | El editor se abrió sin servidor (doble clic en `editor.html`, o se cerró la ventana negra). Ábralo con `Abrir editor.bat`. |
| Un error con «Ver detalle» | El mensaje dice qué pasó; «Ver detalle» trae el texto técnico y la ruta del registro (`data\cache_exportador\trabajador.log`): cópielos para quien mantiene el Exportador. |
| `Abrir editor.bat` dice «No se pudo generar el editor» | Lea el mensaje: casi siempre falta un archivo de ERCO del punto 4 (por ejemplo la plantilla del rótulo). |
| `pip install` falla con «Microsoft Visual C++ … required» | Instale Python 3.12 de 64 bits desde python.org (las dependencias traen versiones ya compiladas para esa versión). |
| Windows pregunta por el firewall al abrir el editor | Puede cancelar: el servidor solo escucha en 127.0.0.1 (este PC) y no necesita la red. |
