@echo off
setlocal
cd /d "%~dp0"
set "NFSDK=%~1"
if not defined NFSDK set /p "NFSDK=Path to extracted RenPy 8 SDK folder: "
set "NFSDK=%NFSDK:"=%"
if not exist "%NFSDK%\lib\py3-windows-x86_64\python.exe" (
    echo Cannot find the Python interpreter in this SDK.
    pause
    exit /b 1
)
"%NFSDK%\lib\py3-windows-x86_64\python.exe" app.py --sdk "%NFSDK%"
if errorlevel 1 pause
