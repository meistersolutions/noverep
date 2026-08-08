# Show Songs Library container status.
# Usage: .\status.ps1

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot
. "$PSScriptRoot\_docker.ps1"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error "Docker CLI not found."
    exit 1
}

if (-not (Test-DockerDaemon)) {
    Write-Host "Docker Desktop is not running."
    exit 1
}

docker compose ps
