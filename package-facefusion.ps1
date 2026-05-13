param(
    [string]$EnvName = 'facefusion',
    [string]$OutputName = 'facefusion',
    [switch]$OneFile,
    [switch]$Clean,
    [switch]$ReinstallPyInstaller
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Resolve-CondaExe {
    $cmd = Get-Command conda -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source) {
        return $cmd.Source
    }

    $candidates = @(
        "$env:USERPROFILE\miniconda3\Scripts\conda.exe",
        "$env:USERPROFILE\Miniconda3\Scripts\conda.exe",
        "$env:ProgramData\miniconda3\Scripts\conda.exe",
        "$env:ProgramData\Miniconda3\Scripts\conda.exe"
    )
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    throw "conda not found."
}

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot

if (-not (Test-Path (Join-Path $repoRoot 'facefusion.py'))) {
    throw "facefusion.py not found. Place script in the facefusion repo root."
}

$condaExe = Resolve-CondaExe

if ($ReinstallPyInstaller) {
    & $condaExe run -n $EnvName pip install --upgrade --force-reinstall pyinstaller
}
else {
    & $condaExe run -n $EnvName pip install pyinstaller
}

$args = @('run', '-n', $EnvName, 'pyinstaller', '--noconfirm', '--name', $OutputName)
if ($Clean) {
    $args += '--clean'
}
if ($OneFile) {
    $args += '--onefile'
}
else {
    $args += '--onedir'
}
$args += 'facefusion.py'

& $condaExe @args

Write-Host "Packaging completed. Check dist/$OutputName" -ForegroundColor Green
