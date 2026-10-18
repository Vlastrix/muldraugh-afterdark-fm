param([string]$ZomboidDir = (Join-Path $env:USERPROFILE 'Zomboid'))
$ErrorActionPreference = 'Stop'
$source = Join-Path $PSScriptRoot 'dist\0.7.4-dev\Test-Mod\AfterdarkGameLab'
if (-not (Test-Path -LiteralPath (Join-Path $source '42\mod.info'))) {
    throw 'Build the experimental package first with Build-Release.ps1.'
}
$modsRoot = [System.IO.Path]::GetFullPath((Join-Path $ZomboidDir 'mods'))
$destination = [System.IO.Path]::GetFullPath((Join-Path $modsRoot 'AfterdarkGameLab'))
if ([System.IO.Path]::GetDirectoryName($destination) -ne $modsRoot) { throw 'Invalid test mod destination.' }
$marker = Join-Path $destination '.afterdark-game-lab-managed'
if ((Test-Path -LiteralPath $destination) -and -not (Test-Path -LiteralPath $marker)) {
    throw 'An unmanaged test mod already exists. Nothing was overwritten.'
}
New-Item -ItemType Directory -Path $destination -Force | Out-Null
Copy-Item -Path (Join-Path $source '*') -Destination $destination -Recurse -Force
Set-Content -LiteralPath $marker -Value 'AfterdarkGameLab local transport experiment' -Encoding ASCII
Write-Output "Game network test mod installed: $destination"
Write-Output 'Restart Zomboid and enable Muldraugh Afterdark FM Game Lab [B42.21] on the test server.'
