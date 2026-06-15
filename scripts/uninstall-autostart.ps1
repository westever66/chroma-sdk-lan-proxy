param(
    [string]$TaskName = "Chroma SDK LAN Proxy"
)

$ErrorActionPreference = "Stop"

$removed = $false

try {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($null -ne $task) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "Removed scheduled task: $TaskName"
        $removed = $true
    }
} catch {
    Write-Host "Scheduled task removal skipped: $($_.Exception.Message)"
}

$startupDir = [Environment]::GetFolderPath("Startup")
$startupFile = Join-Path $startupDir "$TaskName.vbs"
if (Test-Path $startupFile) {
    Remove-Item -LiteralPath $startupFile -Force
    Write-Host "Removed Startup folder launcher: $startupFile"
    $removed = $true
}

if (-not $removed) {
    Write-Host "Autostart entry not found: $TaskName"
}
