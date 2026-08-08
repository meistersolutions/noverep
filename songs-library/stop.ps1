# Stop Songs Library (Docker). SQLite data in .\data is preserved.
# Usage: .\stop.ps1   or   stop.cmd

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot
. "$PSScriptRoot\_docker.ps1"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error "Docker CLI not found."
    exit 1
}

if (-not (Test-DockerDaemon)) {
    Write-Host "Docker Desktop is not running — nothing to stop."
    exit 0
}

Write-Host "Stopping songs-library..."
docker compose down
if ($LASTEXITCODE -ne 0) {
    Write-Error "docker compose down failed (exit $LASTEXITCODE)."
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "Stopped. Data in .\data is preserved."
