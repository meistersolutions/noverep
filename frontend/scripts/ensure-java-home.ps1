# Fixes malformed JAVA_HOME (e.g. two paths joined with ";") and falls back to Android Studio JBR.

function Fix-JavaHome {
    if ($env:JAVA_HOME -and $env:JAVA_HOME.Contains(';')) {
        Write-Warning "JAVA_HOME contains semicolon - using first JDK root only."
        $parts = $env:JAVA_HOME -split ';' | ForEach-Object { $_.Trim() } | Where-Object { $_ }
        $root = $parts | Where-Object { $_ -notmatch '\\bin$' } | Select-Object -First 1
        if (-not $root) { $root = $parts | Select-Object -First 1 }
        $env:JAVA_HOME = $root
    }

    $javaExe = Join-Path $env:JAVA_HOME 'bin\java.exe'
    if ($env:JAVA_HOME -and (Test-Path $javaExe)) {
        return $env:JAVA_HOME
    }

    $candidates = @(
        'C:\Program Files\Android\Android Studio\jbr',
        "$env:ProgramFiles\Android\Android Studio\jbr",
        "$env:LocalAppData\Programs\Android Studio\jbr",
        'C:\Program Files\Java\jdk-21'
    )

    foreach ($pattern in $candidates) {
        $java = Join-Path $pattern 'bin\java.exe'
        if (Test-Path $java) {
            $env:JAVA_HOME = $pattern
            return $env:JAVA_HOME
        }
    }

    throw "JAVA_HOME is not set to a valid JDK. Set JAVA_HOME to Android Studio jbr folder."
}

$resolved = Fix-JavaHome
Write-Host ('JAVA_HOME=' + $resolved) -ForegroundColor Green
& (Join-Path $resolved 'bin\java.exe') -version
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
