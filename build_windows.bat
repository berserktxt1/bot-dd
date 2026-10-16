@echo off
rem ===================================================================
rem  Gera release\DDClassicoBot\DDClassicoBot.exe e release\DDClassicoBot.zip
rem  Requisitos (so para quem vai COMPILAR): Python 3.12 64 bits no PATH.
rem  Uso: clique duas vezes neste arquivo ou rode "build_windows.bat".
rem ===================================================================
setlocal
cd /d "%~dp0"

if not exist .venv-build (
    echo [1/5] Criando ambiente virtual...
    py -3.12 -m venv .venv-build 2>nul || python -m venv .venv-build
    if errorlevel 1 goto :erro
)
call .venv-build\Scripts\activate.bat

echo [2/5] Instalando dependencias...
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt -r requirements-dev.txt
if errorlevel 1 goto :erro

if /i not "%1"=="--sem-testes" (
    echo [3/5] Executando testes...
    python -m pytest -q tests
    if errorlevel 1 goto :erro
) else (
    echo [3/5] Testes pulados.
)

echo [4/5] Compilando com PyInstaller...
python -m PyInstaller --noconfirm --clean --distpath dist --workpath build packaging\DDClassicoBot.spec
if errorlevel 1 goto :erro

echo [5/5] Montando release...
if exist release rmdir /s /q release
mkdir release
xcopy /e /i /q dist\DDClassicoBot release\DDClassicoBot >nul
copy /y README.md release\DDClassicoBot\LEIA-ME.md >nul
copy /y docs\USO.txt release\DDClassicoBot\COMO-USAR.txt >nul
python -m zipfile -c release\DDClassicoBot.zip release\DDClassicoBot
if errorlevel 1 goto :erro

echo.
echo Pronto:
echo   %CD%\release\DDClassicoBot\DDClassicoBot.exe
echo   %CD%\release\DDClassicoBot.zip
endlocal
exit /b 0

:erro
echo.
echo *** Falha na compilacao. Veja as mensagens acima. ***
endlocal
exit /b 1
