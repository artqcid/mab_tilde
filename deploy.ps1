# deploy.ps1 -- Build + Deploy mab~ nach Max 9
#
# Usage: .\deploy.ps1 [-NoBuild] [-Target <Max8|Max9>]
#
# Kopiert .mxe64 + inference_worker.py ins Max-Package.
# WICHTIG: inference_worker.py MUSS mit deployt werden (Bug 2 --
# C++ und Python teilen sich das argparse-Layout, bei Version-Mismatch
# startet der Worker nicht).

param(
    [switch]$NoBuild,
    [ValidateSet("Max 8", "Max 9")]
    [string]$Target = "Max 9"
)

$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot
$buildDir = "$projectRoot\build\Debug"
$targetDir = "$env:USERPROFILE\Documents\$Target\Packages\mab_tilde"

# 1. Build
if (-not $NoBuild) {
    Write-Host "=== Building ===" -ForegroundColor Cyan
    cmake --preset debug -S $projectRoot -B $buildDir
    if ($LASTEXITCODE -ne 0) { throw "cmake configure failed" }
    cmake --build --preset debug -j 8
    if ($LASTEXITCODE -ne 0) { throw "cmake build failed" }
    Write-Host "Build OK" -ForegroundColor Green
}

# 2. Deploy .mxe64
$externals = "$targetDir\externals"
$support = "$targetDir\support"
New-Item -ItemType Directory -Path $externals -Force | Out-Null
New-Item -ItemType Directory -Path $support -Force | Out-Null

$mxes = @("mab~.mxe64", "mc.mab~.mxe64", "mcs.mab~.mxe64", "mab.info.mxe64")
Write-Host "=== Deploying .mxe64 to $externals ===" -ForegroundColor Cyan
foreach ($mxe in $mxes) {
    $src = "$buildDir\$mxe"
    if (Test-Path $src) {
        Copy-Item $src $externals -Force
        Write-Host "  $mxe" -ForegroundColor Green
    } else {
        Write-Host "  SKIP $mxe (not found)" -ForegroundColor Yellow
    }
}

# 3. Deploy inference_worker.py (Bug 2!)
Write-Host "=== Deploying inference_worker.py to $support ===" -ForegroundColor Cyan
$worker = "$projectRoot\inference_worker.py"
if (Test-Path $worker) {
    Copy-Item $worker $support -Force
    Write-Host "  inference_worker.py" -ForegroundColor Green
} else {
    throw "inference_worker.py not found in project root"
}

# 4. Clean __pycache__ (verhindert stale .pyc)
$pyc = "$support\__pycache__"
if (Test-Path $pyc) {
    Remove-Item $pyc -Recurse -Force
    Write-Host "  __pycache__ removed" -ForegroundColor DarkGray
}

# 5. Set MAB_PROJECT_DIR env var + create venv junction (GPU/CUDA support)
Write-Host "=== Environment setup ===" -ForegroundColor Cyan
$oldEnv = [Environment]::GetEnvironmentVariable("MAB_PROJECT_DIR", "User")
if ($oldEnv -ne $projectRoot) {
    [Environment]::SetEnvironmentVariable("MAB_PROJECT_DIR", $projectRoot, "User")
    Write-Host "  MAB_PROJECT_DIR = $projectRoot" -ForegroundColor Green
}

# venv junction: falls find_worker_dir über den Max-Package-Pfad auflöst,
# findet worker_find_venv_python das .venv via Junction
$venvJunction = "$targetDir\.venv"
if (Test-Path $venvJunction) {
    Remove-Item $venvJunction -Force -ErrorAction SilentlyContinue
}
New-Item -ItemType Junction -Path $venvJunction -Target "$projectRoot\.venv" -Force | Out-Null
Write-Host "  .venv junction -> $projectRoot\.venv" -ForegroundColor Green

Write-Host "=== Deploy complete ===" -ForegroundColor Green
Write-Host "Restart Max $Target to load new externals." -ForegroundColor Yellow
