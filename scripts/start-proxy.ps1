param(
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path,
    [string]$ConfigPath = "$env:LOCALAPPDATA\ChromaSdkLanProxy\config.toml",
    [string]$PythonExe = "python"
)

$ErrorActionPreference = "Stop"

$srcPath = Join-Path $ProjectRoot "src"
if (-not (Test-Path $srcPath)) {
    throw "Project src directory not found: $srcPath"
}

$env:PYTHONPATH = $srcPath
& $PythonExe -m chroma_sdk_lan_proxy --config $ConfigPath
exit $LASTEXITCODE
