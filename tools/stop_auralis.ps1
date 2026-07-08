$ErrorActionPreference = "Stop"
$runtime = Join-Path $env:LOCALAPPDATA "Auralis\runtime"
$pidFile = Join-Path $runtime "auralis-processes.json"

if (-not (Test-Path -LiteralPath $pidFile)) {
    Write-Host "No saved Auralis processes were found."
    exit 0
}

try {
    $saved = Get-Content -LiteralPath $pidFile -Raw | ConvertFrom-Json
} catch {
    Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
    Write-Host "The saved process file was invalid and has been cleared."
    exit 0
}

$roots = @($saved.backend, $saved.frontend) | Where-Object { $_ } | ForEach-Object { [int]$_ }
$all = Get-CimInstance Win32_Process
$ids = [System.Collections.Generic.HashSet[int]]::new()
foreach ($id in $roots) {
    [void]$ids.Add($id)
}

do {
    $added = $false
    foreach ($process in $all) {
        if (
            $ids.Contains([int]$process.ParentProcessId) -and
            -not $ids.Contains([int]$process.ProcessId)
        ) {
            [void]$ids.Add([int]$process.ProcessId)
            $added = $true
        }
    }
} while ($added)

foreach ($id in @($ids)) {
    Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
}
Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
Write-Host "Auralis has stopped." -ForegroundColor Green
