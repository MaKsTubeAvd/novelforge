@echo off
setlocal
cd /d "%~dp0"
set "NFSDK="
for /d %%D in ("%~dp0..\renpy-*-sdk" "%~dp0renpy-*-sdk") do (
    if exist "%%~fD\lib\py3-windows-x86_64\python.exe" set "NFSDK=%%~fD"
)
if defined NFSDK (
    "%NFSDK%\lib\py3-windows-x86_64\python.exe" app.py --sdk "%NFSDK%"
    goto done
)
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 app.py
) else (
    python app.py
)
:done
if errorlevel 1 pause
