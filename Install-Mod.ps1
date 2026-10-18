param([string]$ZomboidDir = (Join-Path $env:USERPROFILE 'Zomboid'))
$ErrorActionPreference = 'Stop'
$source = Join-Path $PSScriptRoot 'mod\PearCarRadio'
$modsRoot = [System.IO.Path]::GetFullPath((Join-Path $ZomboidDir 'mods'))
$destination = [System.IO.Path]::GetFullPath((Join-Path $modsRoot 'PearCarRadio'))
if ([System.IO.Path]::GetDirectoryName($destination) -ne $modsRoot) {
    throw 'Destination is outside the mods directory.'
}
$marker = Join-Path $destination '.pear-radio-managed'
if ((Test-Path -LiteralPath $destination) -and -not (Test-Path -LiteralPath $marker)) {
    throw "An existing mod at $destination is not managed by this installer. Nothing was overwritten."
}
New-Item -ItemType Directory -Path $destination -Force | Out-Null
Set-Content -LiteralPath $marker -Value 'PearCarRadio local development copy' -Encoding ASCII
Copy-Item -Path (Join-Path $source '*') -Destination $destination -Recurse -Force
Write-Host "Mod installed at: $destination"
Write-Host 'Restart Zomboid and enable Muldraugh Afterdark FM in your save mods.'
