param([string]$ZomboidDir = (Join-Path $env:USERPROFILE 'Zomboid'))
$ErrorActionPreference = 'Stop'
$source = Join-Path $PSScriptRoot 'mod\PearCarRadio'
$modsRoot = [System.IO.Path]::GetFullPath((Join-Path $ZomboidDir 'mods'))
$destination = [System.IO.Path]::GetFullPath((Join-Path $modsRoot 'PearCarRadio'))
if ([System.IO.Path]::GetDirectoryName($destination) -ne $modsRoot) {
    throw 'Destino fuera de la carpeta de mods.'
}
$marker = Join-Path $destination '.pear-radio-managed'
if ((Test-Path -LiteralPath $destination) -and -not (Test-Path -LiteralPath $marker)) {
    throw "Ya existe un mod en $destination que no pertenece a este instalador. No se sobrescribio."
}
New-Item -ItemType Directory -Path $destination -Force | Out-Null
Set-Content -LiteralPath $marker -Value 'PearCarRadio local development copy' -Encoding ASCII
Copy-Item -Path (Join-Path $source '*') -Destination $destination -Recurse -Force
Write-Host "Mod instalado en: $destination"
Write-Host 'Reinicia Zomboid y activa Pear Car Radio (SP MVP) en los mods de la partida.'
