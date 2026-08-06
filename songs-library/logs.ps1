# Follow Songs Library container logs.
# Usage: .\logs.ps1

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot
docker compose logs -f
