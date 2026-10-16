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
$shellObject = New-Object -ComObject WScript.Shell
$shortcutPath = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Classroom Publisher.lnk'
$shortcut = $shellObject.CreateShortcut($shortcutPath)
$shortcut.TargetPath = Join-Path $appRoot '.venv\Scripts\pythonw.exe'
$shortcut.Arguments = '-m classroom_publisher.cli gui --config "' + $configPath + '"'
$shortcut.WorkingDirectory = $appRoot
$iconPath = & $pythonExe -c "from classroom_publisher.icons import icon_path; print(icon_path('$ShortcutIcon'))"
if ($LASTEXITCODE -ne 0) { throw 'Could not locate the installed shortcut icon.' }
$shortcut.IconLocation = '"' + $iconPath.Trim() + '",0'
$shortcut.Save()
Write-Host "Installed. Edit $configPath, then open the Classroom Publisher desktop shortcut."
Write-Host 'First live Classroom test is still required; see README.md.'
Start-Process notepad.exe -ArgumentList ('"' + $configPath + '"')
