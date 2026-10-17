@echo off
rem ===================================================================
rem  Gera release\JonFlow\JonFlow.exe e release\JonFlow.zip
rem  Requisitos (so para quem vai COMPILAR): Python 3.12 64 bits.
rem  Uso: clique duas vezes neste arquivo ou rode "build_windows.bat".
rem       "build_windows.bat --sem-testes" pula os testes.
rem ===================================================================
setlocal
cd /d "%~dp0"

if defined CI (
    rem na CI o Python ja vem preparado: usa o atual
    set "PY=python"
    goto :deps
)

if exist .venv-build\Scripts\python.exe (
    .venv-build\Scripts\python.exe -c "import sys,struct; sys.exit(0 if sys.version_info[:2]==(3,12) and struct.calcsize('P')==8 else 1)"
    if errorlevel 1 (
        echo Ambiente de compilacao com versao errada: recriando...
        rmdir /s /q .venv-build
    )
)
if not exist .venv-build\Scripts\python.exe (
    echo [1/5] Criando ambiente virtual com Python 3.12 64 bits...
    py -3.12-64 -m venv .venv-build
    if errorlevel 1 (
        echo Python 3.12 64 bits nao encontrado. Instale em https://www.python.org/downloads/
        goto :erro
    )
)
set "PY=.venv-build\Scripts\python.exe"

:deps
echo [2/5] Instalando dependencias...
%PY% -m pip install -r requirements.txt -r requirements-dev.txt
if errorlevel 1 goto :erro

if /i not "%1"=="--sem-testes" (
    echo [3/5] Executando testes...
    %PY% -m pytest -q tests
    if errorlevel 1 goto :erro
) else (
    echo [3/5] Testes pulados.
)

echo [4/5] Compilando com PyInstaller...
%PY% -m PyInstaller --noconfirm --clean --distpath dist --workpath build packaging\JonFlow.spec
if errorlevel 1 goto :erro
echo      ... e a versao em arquivo unico
%PY% -m PyInstaller --noconfirm --clean --distpath dist-unico --workpath build-unico packaging\JonFlow-arquivo-unico.spec
if errorlevel 1 goto :erro

echo [5/5] Montando release...
if exist release rmdir /s /q release
if exist release (
    echo A pasta release esta em uso: feche o JonFlow.exe aberto dela e rode de novo.
    goto :erro
)
mkdir release
if errorlevel 1 goto :erro
xcopy /e /i /q dist\JonFlow release\JonFlow >nul
if errorlevel 1 goto :erro
copy /y README.md release\JonFlow\LEIA-ME.md >nul
if errorlevel 1 goto :erro
copy /y docs\USO.txt release\JonFlow\COMO-USAR.txt >nul
if errorlevel 1 goto :erro
if exist release\JonFlow\dados (
    echo Encontrei dados pessoais dentro do pacote; abortando.
    goto :erro
)
%PY% -m zipfile -c release\JonFlow.zip release\JonFlow
if errorlevel 1 goto :erro
copy /y dist-unico\JonFlow.exe release\JonFlow.exe >nul
if errorlevel 1 goto :erro

echo.
echo Pronto:
echo   %CD%\release\JonFlow\JonFlow.exe
echo   %CD%\release\JonFlow.zip
echo   %CD%\release\JonFlow.exe  (arquivo unico, roda sozinho)
endlocal
exit /b 0

:erro
echo.
echo *** Falha na compilacao. Veja as mensagens acima. ***
if not defined CI pause
endlocal
exit /b 1
