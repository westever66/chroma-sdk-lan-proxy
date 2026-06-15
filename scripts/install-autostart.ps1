param(
    [string]$TaskName = "Chroma SDK LAN Proxy",
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path,
    [string]$ConfigPath = "$env:LOCALAPPDATA\ChromaSdkLanProxy\config.toml",
    [string]$PythonExe = "python",
    [int]$StartupDelaySeconds = 30
)

$ErrorActionPreference = "Stop"

$appDir = Split-Path -Parent $ConfigPath
$logDir = Join-Path $appDir "logs"
New-Item -ItemType Directory -Force -Path $appDir | Out-Null
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

if (-not (Test-Path $ConfigPath)) {
    $exampleConfig = Join-Path $ProjectRoot "examples\config.toml"
    if (-not (Test-Path $exampleConfig)) {
        throw "Example config not found: $exampleConfig"
    }
    Copy-Item $exampleConfig $ConfigPath
    Write-Host "Created config: $ConfigPath"
    Write-Host "Edit bind_host and advertise_host before relying on autostart."
}

$startScript = Join-Path $ProjectRoot "scripts\start-proxy.ps1"
if (-not (Test-Path $startScript)) {
    throw "Start script not found: $startScript"
}

$quotedStartScript = '"' + $startScript + '"'
$quotedProjectRoot = '"' + $ProjectRoot + '"'
$quotedConfigPath = '"' + $ConfigPath + '"'
$quotedPythonExe = '"' + $PythonExe + '"'
$arguments = "-NoProfile -ExecutionPolicy Bypass -File $quotedStartScript -ProjectRoot $quotedProjectRoot -ConfigPath $quotedConfigPath -PythonExe $quotedPythonExe"

$launcherPath = Join-Path $appDir "start-proxy.cmd"
$launcher = @"
@echo off
powershell.exe $arguments
exit /b %ERRORLEVEL%
"@
Set-Content -Path $launcherPath -Value $launcher -Encoding ASCII

$registeredTask = $false
try {
    $action = New-ScheduledTaskAction -Execute $launcherPath
    $trigger = New-ScheduledTaskTrigger -AtLogOn
    $trigger.Delay = "PT${StartupDelaySeconds}S"
    $currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $principal = New-ScheduledTaskPrincipal -UserId $currentUser -LogonType Interactive -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit (New-TimeSpan -Days 0)

    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $action `
        -Trigger $trigger `
        -Principal $principal `
        -Settings $settings `
        -Description "Expose the local Razer Chroma REST SDK to LAN clients." `
        -Force | Out-Null

    $registeredTask = $true
    Write-Host "Registered scheduled task: $TaskName"
} catch {
    Write-Host "Scheduled task registration failed: $($_.Exception.Message)"
    Write-Host "Falling back to the current user's Startup folder."
    $startupDir = [Environment]::GetFolderPath("Startup")
    $startupFile = Join-Path $startupDir "$TaskName.vbs"
    $vbsLauncherPath = $launcherPath.Replace('"', '""')
    $startupLauncher = @"
Set WshShell = CreateObject("WScript.Shell")
WshShell.Run """$vbsLauncherPath""", 0, False
"@
    Set-Content -Path $startupFile -Value $startupLauncher -Encoding ASCII
    Write-Host "Registered Startup folder launcher: $startupFile"
}

Write-Host "Config: $ConfigPath"
Write-Host "Launcher: $launcherPath"
if ($registeredTask) {
    Write-Host "Run now with:"
    Write-Host "  Start-ScheduledTask -TaskName `"$TaskName`""
} else {
    Write-Host "Run now with:"
    Write-Host "  $launcherPath"
}
