@echo off
rem Doble clic para preparar el entorno (solo la primera vez) y abrir el piano.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Preparando el entorno, esto tarda un par de minutos la primera vez...
    python -m venv .venv || goto :error
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :error
)
".venv\Scripts\python.exe" -m piano_aereo %*
goto :eof

:error
echo.
echo No se pudo preparar el entorno. Comprueba que Python 3.9 o superior esta instalado.
pause
