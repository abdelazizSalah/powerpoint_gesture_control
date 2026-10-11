param([switch]$SetupOnly)
$ErrorActionPreference = 'Stop'
$toolDirectory = $PSScriptRoot
$venvDirectory = Join-Path $toolDirectory '.venv'
$toolPython = Join-Path $venvDirectory 'Scripts\python.exe'
$requirementsPath = Join-Path $toolDirectory 'requirements.txt'
$setupMarker = Join-Path $venvDirectory '.requirements-sha256'

if (-not (Test-Path -LiteralPath $toolPython)) {
    $basePython = (Get-Command python -ErrorAction Stop).Source
    & $basePython -c "import sys,struct,tkinter; assert sys.version_info >= (3,10) and struct.calcsize('P') == 8, 'Install 64-bit Python 3.10 or newer with tkinter.'"
    if ($LASTEXITCODE -ne 0) { throw 'Install 64-bit Python 3.10 or newer with tkinter, then try again.' }
    & $basePython -m venv $venvDirectory
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment.' }
}

$requirementsHash = (Get-FileHash -LiteralPath $requirementsPath -Algorithm SHA256).Hash
$installedHash = if (Test-Path -LiteralPath $setupMarker) { (Get-Content -LiteralPath $setupMarker -Raw).Trim() } else { '' }
if ($requirementsHash -ne $installedHash) {
    Write-Host 'Installing the gesture controller dependencies (first run)...'
    & $toolPython -m pip install -r $requirementsPath --disable-pip-version-check
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check your internet connection and Python installation.' }
    Set-Content -LiteralPath $setupMarker -Value $requirementsHash
}

& $toolPython (Join-Path $toolDirectory 'model.py')
if ($LASTEXITCODE -ne 0) { throw 'Gesture model download failed. Check your internet connection.' }
if (-not $SetupOnly) {
    & $toolPython (Join-Path $toolDirectory 'app.py')
    if ($LASTEXITCODE -ne 0) { throw 'The controller could not start. See the error above.' }
}
