@echo off
chcp 65001 >nul
setlocal

rem ===========================================================================
rem  Scribouille - lancement
rem  Utilise l'environnement isole cree par installer.bat.
rem  La fenetre de console se ferme d'elle-meme : l'application a la sienne.
rem ===========================================================================

cd /d "%~dp0"

if exist "%~dp0.venv\Scripts\pythonw.exe" (
    start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0transcriber.pyw"
    exit /b 0
)

echo.
echo   L'application n'est pas encore installee.
echo   Lancez d'abord "installer.bat", puis reessayez.
echo.
pause
exit /b 1
