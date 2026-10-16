# Installs for the current Windows user. No administrator rights needed.
param(
    [ValidateSet('chalkboard-check', 'chalkboard-book', 'chalkboard-pencil')]
    [string]$ShortcutIcon = 'chalkboard-book'
)
$ErrorActionPreference = 'Stop'
$installRoot = Join-Path $env:LOCALAPPDATA 'ClassroomPublisher'
$appRoot = Join-Path $installRoot 'app'
$sourceRoot = $PSScriptRoot
if ([IO.Path]::GetFullPath($sourceRoot).TrimEnd('\') -eq [IO.Path]::GetFullPath($appRoot).TrimEnd('\')) {
    throw 'Run the installer from the extracted download, not from the installed app folder.'
}
Get-Command py -ErrorAction Stop | Out-Null
New-Item -ItemType Directory -Force -Path $appRoot | Out-Null
foreach ($entry in @('src', 'pyproject.toml', 'README.md', 'LIVE-TEST.md', 'config.example.json', 'ui.reference.json', 'scripts', 'docs')) {
    Copy-Item -Path (Join-Path $sourceRoot $entry) -Destination $appRoot -Recurse -Force
}
$pythonExe = Join-Path $appRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $pythonExe)) {
    & py -3 -m venv (Join-Path $appRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Could not create Python environment.' }
}
& $pythonExe -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'Could not update pip. Check your internet connection.' }
& $pythonExe -m pip install --upgrade $appRoot
if ($LASTEXITCODE -ne 0) { throw 'Could not install Classroom Publisher.' }
$configPath = Join-Path $installRoot 'config.json'
if (-not (Test-Path $configPath)) {
    Copy-Item (Join-Path $appRoot 'config.example.json') $configPath
}
& $pythonExe -m classroom_publisher.cli context-menu install --config $configPath
if ($LASTEXITCODE -ne 0) { throw 'Could not install Explorer action.' }
& (Join-Path $appRoot 'scripts\repair-shortcut.ps1') -ShortcutIcon $ShortcutIcon
Write-Host "Installed. Edit $configPath, then open the Classroom Publisher desktop shortcut."
Write-Host 'First live Classroom test is still required; see README.md.'
Start-Process notepad.exe -ArgumentList ('"' + $configPath + '"')
