param(
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$frontend = Join-Path $root "frontend"
$runtime = Join-Path $env:LOCALAPPDATA "Auralis\runtime"
$pidFile = Join-Path $runtime "auralis-processes.json"
$backendOut = Join-Path $runtime "backend.log"
$backendErr = Join-Path $runtime "backend-error.log"
$frontendOut = Join-Path $runtime "frontend.log"
$frontendErr = Join-Path $runtime "frontend-error.log"
$backendUrl = "http://127.0.0.1:8001"
$frontendUrl = "http://127.0.0.1:5173"

New-Item -ItemType Directory -Force -Path $runtime | Out-Null

function Test-Http([string]$Url) {
    try {
        & curl.exe -sS --max-time 2 $Url *> $null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

function Get-LiveSavedProcesses {
    if (-not (Test-Path -LiteralPath $pidFile)) {
        return @()
    }
    try {
        $saved = Get-Content -LiteralPath $pidFile -Raw | ConvertFrom-Json
        return @($saved.backend, $saved.frontend) |
            Where-Object { $_ } |
            ForEach-Object { Get-Process -Id ([int]$_) -ErrorAction SilentlyContinue } |
            Where-Object { $_ }
    } catch {
        return @()
    }
}

$live = @(Get-LiveSavedProcesses)
if ($live.Count -gt 0 -and (Test-Http "$backendUrl/health") -and (Test-Http $frontendUrl)) {
    Write-Host "Auralis is already running." -ForegroundColor Green
    if (-not $NoBrowser) {
        Start-Process $frontendUrl
    }
    exit 0
}

if (Get-NetTCPConnection -LocalPort 8001 -State Listen -ErrorAction SilentlyContinue) {
    throw "Port 8001 is already in use. Close the other program or run 'Stop Auralis.bat'."
}
if (Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue) {
    throw "Port 5173 is already in use. Close the other program or run 'Stop Auralis.bat'."
}
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python was not found on PATH."
}
if (-not (Test-Path -LiteralPath "$env:ProgramFiles\nodejs\npm.cmd")) {
    throw "Node.js/npm was not found."
}
if (-not (Test-Path -LiteralPath (Join-Path $frontend "node_modules"))) {
    Write-Host "Installing the Auralis interface dependencies..." -ForegroundColor Cyan
    & "$env:ProgramFiles\nodejs\npm.cmd" install --prefix $frontend
    if ($LASTEXITCODE -ne 0) {
        throw "npm install failed."
    }
}

Remove-Item -LiteralPath $backendOut, $backendErr, $frontendOut, $frontendErr `
    -Force -ErrorAction SilentlyContinue

Write-Host "Starting Auralis audio engine..." -ForegroundColor Cyan
$backend = Start-Process -FilePath "python" `
    -ArgumentList @(
        "-m", "uvicorn", "auralis.api.main:app",
        "--app-dir", $root,
        "--host", "127.0.0.1",
        "--port", "8001"
    ) `
    -WorkingDirectory $root `
    -WindowStyle Hidden `
    -RedirectStandardOutput $backendOut `
    -RedirectStandardError $backendErr `
    -PassThru

Write-Host "Starting Auralis interface..." -ForegroundColor Cyan
$frontendCommand = "set `"VITE_API=$backendUrl`" && `"$env:ProgramFiles\nodejs\npm.cmd`" run dev -- --host 127.0.0.1"
$frontendProcess = Start-Process -FilePath "cmd.exe" `
    -ArgumentList @("/d", "/s", "/c", $frontendCommand) `
    -WorkingDirectory $frontend `
    -WindowStyle Hidden `
    -RedirectStandardOutput $frontendOut `
    -RedirectStandardError $frontendErr `
    -PassThru

@{
    backend = $backend.Id
    frontend = $frontendProcess.Id
    root = $root
    started_at = (Get-Date).ToString("o")
} | ConvertTo-Json | Set-Content -LiteralPath $pidFile -Encoding UTF8

$ready = $false
for ($attempt = 0; $attempt -lt 40; $attempt++) {
    Start-Sleep -Milliseconds 500
    if ($backend.HasExited) {
        $details = Get-Content -LiteralPath $backendErr -Raw -ErrorAction SilentlyContinue
        throw "The audio engine stopped during startup.`n$details"
    }
    if ($frontendProcess.HasExited) {
        $details = Get-Content -LiteralPath $frontendErr -Raw -ErrorAction SilentlyContinue
        throw "The interface stopped during startup.`n$details"
    }
    if ((Test-Http "$backendUrl/health") -and (Test-Http $frontendUrl)) {
        $ready = $true
        break
    }
}

if (-not $ready) {
    throw "Auralis did not become ready. Logs are in $runtime"
}

Write-Host ""
Write-Host "Auralis is ready: $frontendUrl" -ForegroundColor Green
Write-Host "Use 'Stop Auralis.bat' when you are finished." -ForegroundColor DarkGray
if (-not $NoBrowser) {
    Start-Process $frontendUrl
}
