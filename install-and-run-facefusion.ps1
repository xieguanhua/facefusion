param(
    [ValidateSet('auto', 'cpu', 'cuda', 'tensorrt', 'openvino')]
    [string]$Accelerator = 'auto',
    [switch]$OpenBrowser,
    [switch]$SkipWinget,
    [switch]$SkipCondaInit,
    [bool]$AutoFallbackCN = $true,
    [bool]$RepairCondaPath = $true,
    [switch]$InstallPyInstaller,
    [switch]$NoRun,
    [string]$EnvName = 'facefusion'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Write-Step {
    param([string]$Message)
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Resolve-CondaExe {
    $cmd = Get-Command conda -ErrorAction SilentlyContinue
    if ($cmd) {
        $candidate = $null
        if ($cmd | Get-Member -Name Path -MemberType NoteProperty,Property -ErrorAction SilentlyContinue) {
            $candidate = $cmd.Path
        }
        if ((-not $candidate) -and ($cmd | Get-Member -Name Source -MemberType NoteProperty,Property -ErrorAction SilentlyContinue)) {
            $candidate = $cmd.Source
        }
        if ((-not $candidate) -and ($cmd | Get-Member -Name Definition -MemberType NoteProperty,Property -ErrorAction SilentlyContinue)) {
            $candidate = $cmd.Definition
        }
        if ($candidate -and (Test-Path $candidate)) {
            return $candidate
        }
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

    throw "conda not found. Verify Miniconda is installed, then reopen PowerShell and retry."
}

function Ensure-CondaPath {
    param([string]$CondaExePath)

    if (-not $RepairCondaPath) {
        return
    }

    if (-not $CondaExePath -or -not (Test-Path $CondaExePath)) {
        Write-Warning "Conda executable path is invalid. Skip PATH repair."
        return
    }

    $scriptsDir = Split-Path -Parent $CondaExePath
    if (-not $scriptsDir) {
        Write-Warning "Cannot resolve conda Scripts directory. Skip PATH repair."
        return
    }
    $condaRoot = Split-Path -Parent $scriptsDir
    if (-not $condaRoot) {
        Write-Warning "Cannot resolve conda root directory. Skip PATH repair."
        return
    }
    $requiredSegments = @(
        $condaRoot,
        (Join-Path $condaRoot "Scripts"),
        (Join-Path $condaRoot "condabin")
    )

    # Make current PowerShell session usable immediately.
    $processPathParts = @($env:Path -split ';' | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne '' })
    foreach ($segment in $requiredSegments) {
        $existsInProcess = $false
        foreach ($part in $processPathParts) {
            if ($part.ToLowerInvariant() -eq $segment.ToLowerInvariant()) {
                $existsInProcess = $true
                break
            }
        }
        if (-not $existsInProcess) {
            $processPathParts += $segment
        }
    }
    $env:Path = ($processPathParts -join ';')

    # Persist to user PATH for future terminals.
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $userPathParts = @()
    if ($userPath) {
        $userPathParts = @($userPath -split ';' | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne '' })
    }

    $changed = $false
    foreach ($segment in $requiredSegments) {
        $existsInUser = $false
        foreach ($part in $userPathParts) {
            if ($part.ToLowerInvariant() -eq $segment.ToLowerInvariant()) {
                $existsInUser = $true
                break
            }
        }
        if (-not $existsInUser) {
            $userPathParts += $segment
            $changed = $true
        }
    }

    if ($changed) {
        Write-Step "Repair conda PATH (User scope)"
        [Environment]::SetEnvironmentVariable("Path", ($userPathParts -join ';'), "User")
        Write-Host "Conda PATH repaired for future terminals." -ForegroundColor Green
    }
    else {
        Write-Host "Conda PATH already healthy. Skip repair." -ForegroundColor DarkGray
    }
}

function Test-UrlReachable {
    param(
        [string]$Url,
        [int]$TimeoutSec = 6
    )

    try {
        $response = Invoke-WebRequest -Uri $Url -Method Head -TimeoutSec $TimeoutSec -UseBasicParsing
        return ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400)
    }
    catch {
        return $false
    }
}

function Resolve-CNMirrorFallback {
    if (-not $AutoFallbackCN) {
        return @{
            UseCnFallback = $false
            NvidiaReachable = $true
        }
    }

    Write-Step "Check network reachability for package sources"
    $pypiReachable = Test-UrlReachable -Url "https://pypi.org/simple"
    $condaReachable = Test-UrlReachable -Url "https://repo.anaconda.com/pkgs/main"
    $nvidiaPypiReachable = Test-UrlReachable -Url "https://pypi.nvidia.com"

    Write-Host "pypi.org reachable: $pypiReachable" -ForegroundColor DarkGray
    Write-Host "repo.anaconda.com reachable: $condaReachable" -ForegroundColor DarkGray
    Write-Host "pypi.nvidia.com reachable: $nvidiaPypiReachable" -ForegroundColor DarkGray

    $useCnFallback = -not ($pypiReachable -and $condaReachable)
    if ($useCnFallback) {
        Write-Host "Global source check failed. Enable CN mirror fallback." -ForegroundColor Yellow
    }
    else {
        Write-Host "Global sources reachable. Keep default upstream sources." -ForegroundColor DarkGray
    }

    return @{
        UseCnFallback = $useCnFallback
        NvidiaReachable = $nvidiaPypiReachable
    }
}

function Set-PipCNMirrorEnv {
    if ($script:UseCnFallback) {
        $env:PIP_INDEX_URL = "https://pypi.tuna.tsinghua.edu.cn/simple"
        $env:PIP_TRUSTED_HOST = "pypi.tuna.tsinghua.edu.cn"
        Write-Host "PIP mirror enabled: $env:PIP_INDEX_URL" -ForegroundColor DarkGray
    }
}

function Clear-PipCNMirrorEnv {
    if ($script:UseCnFallback) {
        Remove-Item Env:PIP_INDEX_URL -ErrorAction SilentlyContinue
        Remove-Item Env:PIP_TRUSTED_HOST -ErrorAction SilentlyContinue
    }
}

function Get-CondaMirrorArgs {
    if ($script:UseCnFallback) {
        return @(
            "--override-channels",
            "-c", "https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main",
            "-c", "https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/conda-forge"
        )
    }
    return @()
}

function Test-CondaInstalled {
    $cmd = Get-Command conda -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source) {
        return $true
    }

    $candidates = @(
        "$env:USERPROFILE\miniconda3\Scripts\conda.exe",
        "$env:USERPROFILE\Miniconda3\Scripts\conda.exe",
        "$env:ProgramData\miniconda3\Scripts\conda.exe",
        "$env:ProgramData\Miniconda3\Scripts\conda.exe"
    )
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $true
        }
    }
    return $false
}

function Install-WingetPackageIfMissing {
    param(
        [string]$DisplayName,
        [string]$CheckCommand,
        [string]$PackageId,
        [string[]]$ExtraArgs = @()
    )

    if (Get-Command $CheckCommand -ErrorAction SilentlyContinue) {
        Write-Host "$DisplayName already detected. Skip install." -ForegroundColor DarkGray
        return
    }

    Write-Host "$DisplayName not found. Install via winget..." -ForegroundColor Yellow
    & winget install -e --id $PackageId @ExtraArgs --accept-package-agreements --accept-source-agreements
}

function Install-BaseDependencies {
    Write-Step "Install base dependencies (Git / Miniconda / FFmpeg)"

    Install-WingetPackageIfMissing -DisplayName "Git" -CheckCommand "git" -PackageId "Git.Git"

    if (Test-CondaInstalled) {
        Write-Host "Conda already detected. Skip install." -ForegroundColor DarkGray
    }
    else {
        Write-Host "Conda not found. Install Miniconda via winget..." -ForegroundColor Yellow
        & winget install -e --id Anaconda.Miniconda3 --version py312_25.1.1-2 --override "/AddToPath=1" --accept-package-agreements --accept-source-agreements
    }

    Install-WingetPackageIfMissing -DisplayName "FFmpeg" -CheckCommand "ffmpeg" -PackageId "Gyan.FFmpeg" -ExtraArgs @("--version", "7.0.2")
}

function Get-DetectedAccelerator {
    $gpuNames = @()
    try {
        $gpuNames = @(Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name)
    }
    catch {
        Write-Warning "Cannot read GPU information. Fallback to CPU."
    }

    if ($gpuNames.Count -gt 0) {
        Write-Host "Detected GPU: $($gpuNames -join ' | ')" -ForegroundColor DarkGray
    }

    foreach ($name in $gpuNames) {
        if ($name -match 'NVIDIA') {
            return 'cuda'
        }
    }
    foreach ($name in $gpuNames) {
        if ($name -match 'Intel.*Arc|Intel\(R\).*Arc') {
            return 'openvino'
        }
    }
    return 'cpu'
}

function Ensure-CondaEnv {
    param(
        [string]$CondaExePath,
        [string]$Name
    )

    if (-not $SkipCondaInit) {
        Write-Step "Initialize conda (conda init --all)"
        & $CondaExePath init --all
    }

    Write-Step "Check and create conda environment: $Name"
    $envsJson = & $CondaExePath env list --json | ConvertFrom-Json
    $exists = $false
    foreach ($path in $envsJson.envs) {
        if ($path -match "[\\/]" + [Regex]::Escape($Name) + "$") {
            $exists = $true
            break
        }
    }

    if (-not $exists) {
        $createArgs = @("create", "--name", $Name, "python=3.12", "pip=25.0", "-y")
        $createArgs += Get-CondaMirrorArgs
        & $CondaExePath @createArgs
    }
    else {
        Write-Host "Environment already exists. Skip creation." -ForegroundColor DarkGray
    }
}

function Install-AcceleratorDependencies {
    param(
        [string]$CondaExePath,
        [string]$Name,
        [string]$Mode
    )

    switch ($Mode) {
        'cuda' {
            Write-Step "Install CUDA dependencies (cuda-runtime + cudnn)"
            & $CondaExePath install -n $Name nvidia/label/cuda-12.9.1::cuda-runtime nvidia/label/cudnn-9.10.0::cudnn -y
        }
        'tensorrt' {
            Write-Step "Install CUDA dependencies (TensorRT prerequisite)"
            & $CondaExePath install -n $Name nvidia/label/cuda-12.9.1::cuda-runtime nvidia/label/cudnn-9.10.0::cudnn -y
            Write-Step "Install TensorRT"
            Set-PipCNMirrorEnv
            if (-not $script:NvidiaReachable) {
                Write-Warning "pypi.nvidia.com is unreachable. TensorRT install may fail in current network."
            }
            & $CondaExePath run -n $Name pip install tensorrt==10.12.0.36 --extra-index-url https://pypi.nvidia.com
            Clear-PipCNMirrorEnv
        }
        'openvino' {
            Write-Step "Install OpenVINO"
            $installArgs = @("install", "-n", $Name, "openvino=2025.3.0", "-y")
            $installArgs += Get-CondaMirrorArgs
            & $CondaExePath @installArgs
        }
        default {
            Write-Step "CPU mode. Skip accelerator dependencies."
        }
    }
}

function Install-FaceFusion {
    param(
        [string]$CondaExePath,
        [string]$Name,
        [string]$Mode
    )

    $onnxruntime = 'default'
    if ($Mode -in @('cuda', 'tensorrt')) {
        $onnxruntime = 'cuda'
    }
    elseif ($Mode -eq 'openvino') {
        $onnxruntime = 'openvino'
    }

    Write-Step "Install FaceFusion Python dependencies (install.py --onnxruntime $onnxruntime)"
    Set-PipCNMirrorEnv
    & $CondaExePath run -n $Name python install.py --onnxruntime $onnxruntime
    Clear-PipCNMirrorEnv
}

function Install-PackagingTools {
    param(
        [string]$CondaExePath,
        [string]$Name
    )

    Write-Step "Pre-install PyInstaller for later packaging"
    Set-PipCNMirrorEnv
    & $CondaExePath run -n $Name pip install pyinstaller
    Clear-PipCNMirrorEnv
    Write-Host "Later packaging command: conda run -n $Name pyinstaller --noconfirm --name facefusion facefusion.py" -ForegroundColor Yellow
}

function Run-FaceFusion {
    param(
        [string]$CondaExePath,
        [string]$Name
    )

    $args = @('run')
    if ($OpenBrowser) {
        $args += '--open-browser'
    }

    Write-Step "Start FaceFusion"
    & $CondaExePath run -n $Name python facefusion.py @args
}

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot

if (-not (Test-Path (Join-Path $repoRoot 'install.py'))) {
    throw "install.py not found in current directory. Place this script in the facefusion repo root."
}
if (-not (Test-Path (Join-Path $repoRoot 'facefusion.py'))) {
    throw "facefusion.py not found in current directory. Verify repository integrity."
}

if (-not $SkipWinget) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "winget not found. Install dependencies manually, then rerun with -SkipWinget."
    }
    Install-BaseDependencies
}

$mirrorFallbackState = Resolve-CNMirrorFallback
$script:UseCnFallback = [bool]$mirrorFallbackState.UseCnFallback
$script:NvidiaReachable = [bool]$mirrorFallbackState.NvidiaReachable

$condaExe = Resolve-CondaExe
Ensure-CondaPath -CondaExePath $condaExe
Ensure-CondaEnv -CondaExePath $condaExe -Name $EnvName

$selected = $Accelerator
if ($selected -eq 'auto') {
    $selected = Get-DetectedAccelerator
    Write-Host "Auto-selected accelerator: $selected" -ForegroundColor Green
}
else {
    Write-Host "Manual accelerator: $selected" -ForegroundColor Green
}

Install-AcceleratorDependencies -CondaExePath $condaExe -Name $EnvName -Mode $selected
Install-FaceFusion -CondaExePath $condaExe -Name $EnvName -Mode $selected

if ($InstallPyInstaller) {
    Install-PackagingTools -CondaExePath $condaExe -Name $EnvName
}

if (-not $NoRun) {
    Run-FaceFusion -CondaExePath $condaExe -Name $EnvName
}
else {
    Write-Step "Installation finished (run skipped by parameter)"
}
