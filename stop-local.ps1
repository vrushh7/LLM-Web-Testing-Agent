$ErrorActionPreference = "SilentlyContinue"

$ports = @(8000, 5173, 5174)
$processIds = foreach ($port in $ports) {
    Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue |
        Where-Object { $_.State -eq "Listen" } |
        Select-Object -ExpandProperty OwningProcess
}

$processIds = $processIds | Sort-Object -Unique

if ($processIds.Count -eq 0) {
    Write-Host "No HINSA AI dev servers are listening on ports 8000, 5173, or 5174."
    exit 0
}

foreach ($processId in $processIds) {
    $process = Get-Process -Id $processId
    Write-Host "Stopping $($process.ProcessName) on PID $processId"
    Stop-Process -Id $processId -Force
}

Write-Host "Stopped HINSA AI dev servers."
