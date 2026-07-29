# Build latest NoRepeat APK and install on connected Android device (USB or wireless adb).

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$adbDir = Join-Path $env:LOCALAPPDATA 'Android\Sdk\platform-tools'
if ((Test-Path $adbDir) -and ($env:Path -notlike '*platform-tools*')) {
    $env:Path = "$adbDir;$env:Path"
}

. (Join-Path $PSScriptRoot 'ensure-java-home.ps1')

Write-Host ''
Write-Host 'Checking adb devices...' -ForegroundColor Cyan
$deviceLines = adb devices | Select-Object -Skip 1 | Where-Object { $_ -match '\tdevice(\s|$)' }
if (-not $deviceLines) {
    Write-Host 'No device in adb list; trying mdns wireless connect...' -ForegroundColor Yellow
    $mdns = adb mdns services 2>$null | Select-String '_adb-tls-connect._tcp'
    if ($mdns) {
        $hostPort = ($mdns.ToString() -split '\s+')[-1]
        adb connect $hostPort | Out-Host
        Start-Sleep -Seconds 2
        $deviceLines = adb devices | Select-Object -Skip 1 | Where-Object { $_ -match '\tdevice(\s|$)' }
    }
}
if (-not $deviceLines) {
    Write-Host 'No Android device found. Pair/connect wireless debugging first.' -ForegroundColor Yellow
    exit 1
}
Write-Host ('Device(s): ' + ($deviceLines -join ' | ')) -ForegroundColor Green

Write-Host ''
Write-Host 'Syncing Capacitor web bundle...' -ForegroundColor Cyan
npm run cap:sync
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ''
Write-Host 'Building debug APK...' -ForegroundColor Cyan
$gradleJavaHome = $env:JAVA_HOME.Replace('\', '/')
Set-Location (Join-Path $root 'android')
.\gradlew.bat assembleDebug --no-daemon "-Dorg.gradle.java.home=$gradleJavaHome"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$apk = Join-Path $root 'android\app\build\outputs\apk\debug\app-debug.apk'
if (-not (Test-Path $apk)) {
    Write-Error "APK not found at $apk"
}

Write-Host ''
Write-Host ('Installing ' + $apk + ' ...') -ForegroundColor Cyan
$serial = (($deviceLines | Select-Object -First 1).ToString() -split '\s+')[0]
$adbTarget = if ($serial) { @('-s', $serial) } else { @() }
adb @adbTarget install -r $apk
if ($LASTEXITCODE -ne 0) {
    Write-Host 'Install failed; retrying after uninstall (signature mismatch)...' -ForegroundColor Yellow
    adb @adbTarget uninstall com.noverep.app | Out-Host
    adb @adbTarget install $apk
}
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$appVersion = (Get-Content (Join-Path $root 'package.json') -Raw | ConvertFrom-Json).version
Write-Host ''
Write-Host ('Installed NoRepeat (com.noverep.app) v' + $appVersion) -ForegroundColor Green
