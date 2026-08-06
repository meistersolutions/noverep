# Show Songs Library container status.
# Usage: .\status.ps1

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot
docker compose ps
