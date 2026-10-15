@echo off
rem Doble clic para preparar el entorno (solo la primera vez) y abrir el piano.
rem Los argumentos se pasan a la aplicacion, p. ej.:  ejecutar.bat --modo ritmo
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto :abrir

rem Busca Python: primero "python", luego el lanzador "py" de Windows.
set "PYTHON="
python --version >nul 2>&1 && set "PYTHON=python"
if not defined PYTHON py -3 --version >nul 2>&1 && set "PYTHON=py -3"
if not defined PYTHON (
    echo No se encontro Python. Instala Python 3.9 o superior desde https://www.python.org
    pause
    exit /b 1
)
echo Preparando el entorno, esto tarda un par de minutos la primera vez...
%PYTHON% -m venv .venv || goto :error
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :error

:abrir
".venv\Scripts\python.exe" -m piano_aereo %*
if errorlevel 1 pause
exit /b

:error
echo.
echo No se pudo preparar el entorno. Revisa la conexion a internet y vuelve a intentarlo.
pause
exit /b 1
