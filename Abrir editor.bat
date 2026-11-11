@echo off
rem Genera el editor de planos con componedor.json y lo abre en el navegador.
rem Doble clic desde el Explorador; no hace falta abrir una consola.
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"
rem Con el python del sistema, el paquete se toma de src\ aunque no esté instalado.
set "PYTHONPATH=%~dp0src"
if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
) else (
  echo No se encontró .venv\Scripts\python.exe; se usa «python» del sistema.
  set "PY=python"
)
"%PY%" -m componedor.cli editor --config componedor.json --sobrescribir
if errorlevel 1 (
  echo.
  echo No se pudo generar el editor. Revise el mensaje de arriba.
  pause
  exit /b 1
)
start "" "editor\editor.html"
endlocal
