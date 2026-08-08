# Shared Docker Desktop helpers for Songs Library scripts.

function Invoke-DockerQuiet {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Args
    )
    # docker writes connection errors to stderr; with $ErrorActionPreference=Stop
    # that becomes a terminating NativeCommandError. Keep Continue for the call.
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & docker @Args 1>$null 2>$null
        return ($LASTEXITCODE -eq 0)
    } finally {
        $ErrorActionPreference = $prev
    }
}

function Test-DockerDaemon {
    return (Invoke-DockerQuiet -Args @("info"))
}

function Get-DockerDesktopPath {
    $candidates = @(
        "${env:ProgramFiles}\Docker\Docker\Docker Desktop.exe",
        "${env:ProgramFiles(x86)}\Docker\Docker\Docker Desktop.exe",
        "$env:LOCALAPPDATA\Docker\Docker Desktop.exe"
    )
    foreach ($path in $candidates) {
        if ($path -and (Test-Path -LiteralPath $path)) {
            return $path
        }
    }
    return $null
}

function Wait-DockerDaemon {
    param(
        [int]$TimeoutSeconds = 180,
        [int]$PollSeconds = 3
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-DockerDaemon) {
            return $true
        }
        Start-Sleep -Seconds $PollSeconds
        Write-Host "  still waiting for Docker Desktop..."
    }
    return $false
}

function Ensure-DockerRunning {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Write-Error "Docker CLI not found. Install Docker Desktop, then retry."
        exit 1
    }

    if (Test-DockerDaemon) {
        return
    }

    Write-Host "Docker Desktop is not running. Starting it..."
    $desktop = Get-DockerDesktopPath
    if (-not $desktop) {
        Write-Error "Docker Desktop is not running and Docker Desktop.exe was not found. Start Docker Desktop manually, then retry."
        exit 1
    }

    Start-Process -FilePath $desktop | Out-Null
    Write-Host "Waiting for Docker engine (up to 3 minutes)..."
    if (-not (Wait-DockerDaemon -TimeoutSeconds 180)) {
        Write-Error "Docker Desktop did not become ready in time. Open Docker Desktop, wait until it says Running, then retry .\start.cmd"
        exit 1
    }
    Write-Host "Docker is ready."
}
