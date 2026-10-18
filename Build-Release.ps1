$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$buildPython = Join-Path $PSScriptRoot '.tools\stream-build\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $buildPython)) {
    py -3.12 -m venv .tools\stream-build
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the build environment.' }
}
& $buildPython -m pip install -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw 'Could not install build dependencies.' }
& $buildPython tools\build_release.py
if ($LASTEXITCODE -ne 0) { throw 'Release build failed.' }
