# Compila e confere o JonFlow no Windows do mantenedor, como a CI faria, e (com -Publicar) cria a Release.
#
# Para quando a CI do GitHub não está disponível. Compila a tag da versão (vX.Y.Z) numa pasta separada
# (build-tag\vX.Y.Z, um "git worktree"), sem mexer na sua cópia: testes no Windows, os dois .exe (autoteste e
# interface sem Python no PATH), as capturas da interface em 100/125/150% com a auditoria de layout,
# SHA256SUMS.txt, build-info.json e as notas da versão. Os arquivos ficam em build-tag\vX.Y.Z\release.
#
# Uso (PowerShell, na pasta do projeto, em qualquer branch):
#   powershell -ExecutionPolicy Bypass -File tools\compilar_local.ps1                     # só compila e confere
#   powershell -ExecutionPolicy Bypass -File tools\compilar_local.ps1 -Publicar           # e cria a Release (gh)
#   powershell -ExecutionPolicy Bypass -File tools\compilar_local.ps1 -Tag v0.5.1         # outra tag
#
# Requisitos: Python 3.12 64 bits (o build_windows.bat cria o .venv-build), git, e o gh logado para -Publicar.
# A tela precisa ser de 1920x1080 ou maior para a auditoria de layout.
param([switch]$Publicar, [string]$Tag)

$ErrorActionPreference = "Stop"
$repo = Split-Path $PSScriptRoot -Parent

function Falhar($msg) { Write-Host ""; Write-Host "*** $msg ***" -ForegroundColor Red; exit 1 }
function Etapa($msg) { Write-Host ""; Write-Host "== $msg ==" -ForegroundColor Cyan }
function Gravar($path, $text) { [IO.File]::WriteAllText($path, $text, (New-Object Text.UTF8Encoding $false)) }
function Versao($dir) { ([regex]'__version__ = "([^"]+)"').Match((Get-Content "$dir\src\ddbot\__init__.py" -Raw)).Groups[1].Value }

# programas externos que escrevem no erro: no PowerShell 5.1 viram exceção com "Stop"
function Git-Quieto([string[]]$a) {
    $ErrorActionPreference = "Continue"
    $out = & git -C $repo @a 2>&1
    return @{ ok = ($LASTEXITCODE -eq 0); out = "$out" }
}

# o exe é programa de janela: Start-Process espera o código de saída; trava vira falha
function Rodar-Exe($exe, [string[]]$argList, $timeoutMs) {
    $p = Start-Process $exe -ArgumentList $argList -PassThru
    if (-not $p.WaitForExit($timeoutMs)) { $p.Kill(); Falhar "o exe travou ($($argList -join ' '))" }
    return $p.ExitCode
}

Etapa "Preparando a tag numa pasta separada"
if (-not $Tag) { $Tag = "v$(Versao $repo)" }
Git-Quieto @("fetch", "--tags", "origin") | Out-Null
if (-not (Git-Quieto @("rev-parse", "--verify", "$Tag^{commit}")).ok) { Falhar "a tag $Tag não existe (nem no GitHub)" }
$root = Join-Path $repo "build-tag\$Tag"
if (Test-Path $root) {
    $r = Git-Quieto @("worktree", "remove", "--force", $root)
    if (Test-Path $root) { Remove-Item -Recurse -Force $root }
    Git-Quieto @("worktree", "prune") | Out-Null
}
$r = Git-Quieto @("worktree", "add", "--detach", $root, $Tag)
if (-not $r.ok) { Falhar "git worktree falhou: $($r.out)" }
Set-Location $root
$versao = Versao $root
if ("v$versao" -ne $Tag) { Falhar "a tag $Tag tem a versão $versao no código" }
$commit = (git rev-parse HEAD).Trim()
Write-Host "versão $versao, commit $commit, pasta $root"

Etapa "Compilando (build_windows.bat)"
cmd /c "build_windows.bat --sem-testes"
if ($LASTEXITCODE -ne 0) { Falhar "a compilação falhou" }
$py = "$root\.venv-build\Scripts\python.exe"

Etapa "Testes no Windows"
foreach ($d in @("test-results", "zipcheck", "screenshots")) { if (Test-Path $d) { Remove-Item -Recurse -Force $d } }
New-Item -ItemType Directory -Force test-results | Out-Null
$escala = (& $py tools\display_scale.py).Trim()
Write-Host $escala
& $py -m pytest -q tests -rs -p no:cacheprovider --junitxml=test-results\pytest-windows.xml
if ($LASTEXITCODE -ne 0) { Falhar "testes falharam no Windows" }
$suite = ([xml](Get-Content test-results\pytest-windows.xml)).testsuites.testsuite
$aprovados = [int]$suite.tests - [int]$suite.failures - [int]$suite.errors - [int]$suite.skipped
$testes = "$aprovados de $($suite.tests) aprovados ($($suite.failures) falhas, $($suite.skipped) pulados; $escala)"

Etapa "Testando os .exe sem Python no PATH"
Expand-Archive release\JonFlow.zip -DestinationPath zipcheck -Force
$zipExe = (Resolve-Path zipcheck\JonFlow\JonFlow.exe).Path
New-Item -ItemType Directory -Force zipcheck\unico | Out-Null
Copy-Item release\JonFlow.exe zipcheck\unico\
$unicoExe = (Resolve-Path zipcheck\unico\JonFlow.exe).Path
$pathAntes = $env:PATH
$env:PATH = "C:\Windows\System32;C:\Windows"
try {
    foreach ($exe in @($zipExe, $unicoExe)) {
        $nome = if ($exe -eq $zipExe) { "zip" } else { "unico" }
        $env:DDBOT_SELFTEST_OUT = "$root\test-results\exe-$nome-selftest.json"
        if ((Rodar-Exe $exe @("--selftest") 240000) -ne 0) { Falhar "autoteste do exe ($nome) falhou" }
        $env:DDBOT_SMOKE_OUT = "$root\test-results\exe-$nome-gui-smoke.json"
        if ((Rodar-Exe $exe @("--gui-smoke", "8") 180000) -ne 0) { Falhar "teste de interface do exe ($nome) falhou" }
        if (-not (Test-Path (Join-Path (Split-Path $exe) "dados\config.json"))) { Falhar "o exe ($nome) não criou dados\config.json ao lado de si" }
        Write-Host "exe ($nome): autoteste e interface OK"
    }
} finally {
    $env:PATH = $pathAntes
    Remove-Item Env:DDBOT_SMOKE_OUT, Env:DDBOT_SELFTEST_OUT -ErrorAction SilentlyContinue
}

Etapa "Capturas da interface e auditoria de layout (100%, 125%, 150%)"
New-Item -ItemType Directory -Force screenshots | Out-Null
try {
    foreach ($s in @("1.0", "1.25", "1.5")) {
        $env:DDBOT_UI_SCALE = $s
        $env:DDBOT_HOME = "$root\zipcheck\shots-home-$s"
        $p = Start-Process $zipExe -ArgumentList @("--screenshots", "$root\screenshots") -PassThru
        if (-not $p.WaitForExit(420000)) { $p.Kill(); Falhar "as capturas travaram em $s" }
    }
} finally { Remove-Item Env:DDBOT_UI_SCALE, Env:DDBOT_HOME -ErrorAction SilentlyContinue }
$rel = @(Get-ChildItem screenshots -Filter *_layout.json -ErrorAction SilentlyContinue)
if ($rel.Count -lt 3) { Falhar "faltam relatórios de layout ($($rel.Count) de 3); a tela tem 1920x1080?" }
$ruins = @()
foreach ($f in $rel) {
    $r = Get-Content $f.FullName -Raw | ConvertFrom-Json
    foreach ($p in @($r.problemas_layout.PSObject.Properties)) { $ruins += "$($f.Name) / $($p.Name)" }
}
if ($ruins.Count) { $ruins | ForEach-Object { Write-Host $_ }; Falhar "layout com problemas (imagens em screenshots\)" }
Write-Host "layout sem problemas nas 3 escalas"

Etapa "SHA-256, build-info.json e notas da versão"
$somas = [ordered]@{}
foreach ($f in @("JonFlow.zip", "JonFlow.exe")) { $somas[$f] = (Get-FileHash "release\$f" -Algorithm SHA256).Hash.ToLower() }
Gravar "$root\release\SHA256SUMS.txt" ((($somas.Keys | ForEach-Object { "$($somas[$_])  $_" }) -join "`n") + "`n")
$info = [ordered]@{
    versao         = $versao
    commit         = $commit
    ref            = "refs/tags/$Tag"
    ci_execucao    = "local"
    ci_url         = ""
    compilado_em   = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    python         = (& $py --version).Trim()
    pyinstaller    = (& $py -m PyInstaller --version).Trim()
    testes_windows = $testes
    sha256         = $somas
}
Gravar "$root\release\build-info.json" ($info | ConvertTo-Json -Depth 4)
$notas = (Get-Content docs\RELEASE_NOTES.md -Raw -Encoding UTF8)
$notas = $notas.Replace("- Execução da CI: {RUN_URL}", "- Compilação: local, no Windows do mantenedor (a CI do GitHub não estava disponível), com o script ``tools/compilar_local.ps1``")
$notas = $notas.Replace(" Os pulados são os testes de layout (``test_gui_layout.py``), que precisam de tela 1920×1080: nessa rodada a tela do runner é 1024×768; eles rodam no passo com a escala em 125% e no Linux.", "")
$notas = $notas.Replace("{COMMIT}", $commit).Replace("{TESTES}", $testes).Replace("{SHA_ZIP}", $somas["JonFlow.zip"]).Replace("{SHA_EXE}", $somas["JonFlow.exe"])
Gravar "$root\release\release-notes.md" $notas
Get-Content release\SHA256SUMS.txt
Write-Host "testes: $testes"

if (-not $Publicar) {
    Write-Host ""
    Write-Host "Pronto. Arquivos em $root\release. Para publicar: rode de novo com -Publicar." -ForegroundColor Green
    exit 0
}

Etapa "Publicando a Release $Tag"
$ErrorActionPreference = "Continue"
& gh release view $Tag *> $null
$existe = ($LASTEXITCODE -eq 0)
$ErrorActionPreference = "Stop"
if ($existe) { Falhar "a Release $Tag já existe: confira no GitHub antes de substituir" }
& gh release create $Tag release\JonFlow.zip release\JonFlow.exe release\SHA256SUMS.txt release\build-info.json `
    --verify-tag --title "JonFlow $versao" --notes-file release\release-notes.md
if ($LASTEXITCODE -ne 0) { Falhar "o gh não criou a Release" }
& gh release view $Tag
Write-Host "Release $Tag publicada." -ForegroundColor Green
