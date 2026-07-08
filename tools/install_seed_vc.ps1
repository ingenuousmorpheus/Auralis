param(
    [string]$InstallRoot = "$env:LOCALAPPDATA\Auralis\providers\seed-vc"
)

$ErrorActionPreference = "Stop"
$repo = "https://github.com/Plachtaa/seed-vc.git"

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "Git is required to install the optional Seed-VC provider."
}
if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "The Python launcher is required."
}

New-Item -ItemType Directory -Force -Path (Split-Path $InstallRoot) | Out-Null
if (-not (Test-Path "$InstallRoot\.git")) {
    git clone --depth 1 $repo $InstallRoot
}

if (-not (Test-Path "$InstallRoot\.venv\Scripts\python.exe")) {
    py -3.11 -m venv "$InstallRoot\.venv"
}

$python = "$InstallRoot\.venv\Scripts\python.exe"
& $python -m pip install --upgrade pip wheel setuptools
& $python -m pip install torch==2.4.0 torchvision==0.19.0 torchaudio==2.4.0 --index-url https://download.pytorch.org/whl/cu121

$filtered = Join-Path $env:TEMP "auralis-seed-vc-requirements.txt"
Get-Content "$InstallRoot\requirements.txt" |
    Where-Object { $_ -notmatch '^(torch|torchvision|torchaudio)(\s|=|$)' } |
    Set-Content -Encoding utf8 $filtered
& $python -m pip install -r $filtered
& $python -m pip install "setuptools<81"

& $python -c "import torch; print('Seed-VC ready. CUDA:', torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"
