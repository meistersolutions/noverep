# Stop Songs Library (Docker). SQLite data in .\data is preserved.
# Usage: .\stop.ps1   or   stop.cmd

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

Write-Host "Stopping songs-library..."
docker compose down
if ($LASTEXITCODE -ne 0) {
    Write-Error "docker compose down failed (exit $LASTEXITCODE)."
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "Stopped. Data in .\data is preserved."
