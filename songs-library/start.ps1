# Start Songs Library (Docker) locally.
# Usage: .\start.ps1   or   start.cmd

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot
. "$PSScriptRoot\_docker.ps1"

if (-not (Test-Path -Path ".\data")) {
    New-Item -ItemType Directory -Path ".\data" | Out-Null
    Write-Host "Created .\data"
}

Ensure-DockerRunning

Write-Host "Building and starting songs-library..."
docker compose up -d --build
if ($LASTEXITCODE -ne 0) {
    Write-Error "docker compose up failed (exit $LASTEXITCODE)."
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "Songs Library: http://127.0.0.1:8100/"
Write-Host ""
docker compose ps
