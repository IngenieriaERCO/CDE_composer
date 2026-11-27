@echo off
rem Compone un plano.json con el formato de componedor.json y deja el PDF en
rem resultados\<nombre del plano>.pdf. Con el índice de un proyecto (<proyecto>.hojas.json),
rem todas sus hojas en UN PDF: resultados\<proyecto>_proyecto.pdf.
rem Arrastre un plano.json (o un .hojas.json) sobre este archivo, o haga
rem doble clic y arrastre (o escriba) la ruta del plano en la ventana.
chcp 65001 >nul
setlocal
set "PLANO=%~1"
if defined PLANO goto :tengo_plano
echo Arrastre aquí el plano.json (o escriba su ruta) y pulse Enter:
set /p "PLANO=> "
if not defined PLANO goto :sin_plano
set "PLANO=%PLANO:"=%"
:tengo_plano
if not defined PLANO goto :sin_plano
for %%F in ("%PLANO%") do set "PLANO=%%~fF" & set "NOMBRE=%%~nF"
if not exist "%PLANO%" goto :no_existe
rem El índice de un proyecto (<proyecto>.hojas.json): todas las hojas en <proyecto>_proyecto.pdf.
if /i "%NOMBRE:~-6%"==".hojas" set "NOMBRE=%NOMBRE:~0,-6%_proyecto"
cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"
rem Con el python del sistema, el paquete se toma de src\ aunque no esté instalado.
set "PYTHONPATH=%~dp0src"
set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
if "%PY%"=="python" echo No se encontró .venv\Scripts\python.exe; se usa «python» del sistema.
"%PY%" -m componedor.cli componer "%PLANO%" --config componedor.json --sobrescribir --codigo-avisos
set "CODIGO=%ERRORLEVEL%"
if "%CODIGO%"=="0" goto :abrir
if "%CODIGO%"=="3" goto :avisos
echo.
echo No se generó el PDF: revise los errores de arriba.
pause
exit /b 1
:avisos
echo.
echo El PDF se generó, pero componer dejó advertencias: revíselas arriba.
pause
:abrir
start "" "resultados\%NOMBRE%.pdf"
exit /b 0
:sin_plano
echo No se indicó ningún plano.json.
pause
exit /b 1
:no_existe
echo No existe el archivo: %PLANO%
pause
exit /b 1
