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
# Build from this checkout, not the long-lived app staging folder (which may
# contain stale setuptools build output from an earlier installation).
& $pythonExe -m pip install --upgrade --force-reinstall --no-cache-dir $sourceRoot
if ($LASTEXITCODE -ne 0) { throw 'Could not install Classroom Publisher.' }
# Check the actual imported package before registering shortcuts/menu actions.
# -I prevents the current directory or PYTHONPATH from masking the installation.
$verifyCode = @'
import hashlib
import pathlib
import sys
import classroom_publisher
source = pathlib.Path(sys.argv[1]) / 'src' / 'classroom_publisher'
installed = pathlib.Path(classroom_publisher.__file__).resolve().parent
for expected in source.rglob('*'):
    if expected.is_file() and expected.suffix in ('.py', '.ico', '.png'):
        actual = installed / expected.relative_to(source)
        if not actual.is_file() or hashlib.sha256(actual.read_bytes()).digest() != hashlib.sha256(expected.read_bytes()).digest():
            raise SystemExit('Installed file differs from checkout: ' + str(actual))
print('Verified installed application: ' + str(installed))
'@
& $pythonExe -I -c $verifyCode $sourceRoot
if ($LASTEXITCODE -ne 0) { throw 'Installed code verification failed. Do not publish with this installation.' }
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
