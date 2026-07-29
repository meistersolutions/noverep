# Build latest NoRepeat APK and install on connected Android device (USB or wireless adb).
# Fixes JAVA_HOME automatically before Gradle runs.
#
# Usage (PowerShell):
#   cd frontend
#   npm run cap:deploy:android:win
#
# Wireless debugging:
#   adb pair <ip>:<pairing-port> <code>
#   adb connect <ip>:<connect-port>
#   npm run cap:deploy:android:win

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

. (Join-Path $PSScriptRoot 'ensure-java-home.ps1')

Write-Host "`n→ Checking adb devices…" -ForegroundColor Cyan
$devices = adb devices | Select-String 'device$'
if (-not $devices) {
    Write-Host @"

No Android device found.
Wireless debugging:
  1. Phone: Developer options → Wireless debugging → Pair device with pairing code
  2. adb pair <ip>:<pairing-port> <6-digit-code>
  3. adb connect <ip>:<connect-port>
  4. adb devices
  5. npm run cap:deploy:android:win
"@ -ForegroundColor Yellow
    exit 1
}
Write-Host "Device(s): $($devices -join ', ')" -ForegroundColor Green

Write-Host "`n→ Syncing Capacitor web bundle…" -ForegroundColor Cyan
npm run cap:sync
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "`n→ Building debug APK…" -ForegroundColor Cyan
$gradleJavaHome = $env:JAVA_HOME.Replace('\', '/')
Set-Location (Join-Path $root 'android')
.\gradlew.bat assembleDebug --no-daemon "-Dorg.gradle.java.home=$gradleJavaHome"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$apk = Join-Path $root 'android\app\build\outputs\apk\debug\app-debug.apk'
if (-not (Test-Path $apk)) {
    Write-Error "APK not found at $apk"
}

Write-Host "`n→ Installing $apk …" -ForegroundColor Cyan
adb install -r $apk
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "`n✓ Installed NoRepeat (com.noverep.app) v$((Get-Content (Join-Path $root 'package.json') -Raw | ConvertFrom-Json).version)" -ForegroundColor Green
