@echo off
chcp 65001 >nul
setlocal

rem ===========================================================================
rem  Scribouille - installation
rem  Double-cliquez sur ce fichier. Relancable autant de fois que necessaire.
rem
rem  Options :
rem    installer.bat --locuteurs        installe aussi la separation des locuteurs
rem    installer.bat --sans-locuteurs   installation legere, sans question
rem    installer.bat --verifier         affiche seulement le bilan
rem ===========================================================================

cd /d "%~dp0"

set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY (
    where python >nul 2>&1 && set "PY=python"
)

if not defined PY (
    echo.
    echo   Python est introuvable sur ce poste.
    echo.
    echo   Installez-le depuis https://www.python.org/downloads/
    echo   et cochez "Add python.exe to PATH" pendant l'installation.
    echo.
    pause
    exit /b 1
)

%PY% "%~dp0installer.py" %*
set "CODE=%ERRORLEVEL%"

echo.
pause
exit /b %CODE%
