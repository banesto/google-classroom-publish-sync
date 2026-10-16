# Recreate the current user's shortcut without reinstalling or changing saved logins.
param(
    [ValidateSet('chalkboard-check', 'chalkboard-book', 'chalkboard-pencil')]
    [string]$ShortcutIcon = 'chalkboard-book'
)
$ErrorActionPreference = 'Stop'
$installRoot = Join-Path $env:LOCALAPPDATA 'ClassroomPublisher'
$appRoot = Join-Path $installRoot 'app'
$pythonExe = Join-Path $appRoot '.venv\Scripts\python.exe'
$pythonwExe = Join-Path $appRoot '.venv\Scripts\pythonw.exe'
foreach ($requiredPath in @($pythonExe, $pythonwExe)) {
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
        throw 'Classroom Publisher is not installed. Run install-windows.ps1 first.'
    }
}
$iconOutput = & $pythonExe -c "from classroom_publisher.icons import icon_path; print(icon_path('$ShortcutIcon'))"
if ($LASTEXITCODE -ne 0) { throw 'Could not locate the installed shortcut icon. Run install-windows.ps1 again.' }
$sourceIcon = ([string]$iconOutput).Trim()
if (-not (Test-Path -LiteralPath $sourceIcon -PathType Leaf)) {
    throw "Shortcut icon does not exist: $sourceIcon"
}
# A separate, content-named path avoids reusing the old shortcut's cached icon.
$iconDirectory = Join-Path $installRoot 'icons'
New-Item -ItemType Directory -Force -Path $iconDirectory | Out-Null
$iconHash = (Get-FileHash -LiteralPath $sourceIcon -Algorithm SHA256).Hash.Substring(0, 12)
$iconPath = Join-Path $iconDirectory "$ShortcutIcon-$iconHash.ico"
Copy-Item -LiteralPath $sourceIcon -Destination $iconPath -Force
$configPath = Join-Path $installRoot 'config.json'
$shellObject = New-Object -ComObject WScript.Shell
$shortcutPath = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Classroom Publisher.lnk'
$shortcut = $shellObject.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $pythonwExe
$shortcut.Arguments = '-m classroom_publisher.cli gui --config "' + $configPath + '"'
$shortcut.WorkingDirectory = $appRoot
# IconLocation is a COM property, not a command line: do not embed quote characters.
$shortcut.IconLocation = $iconPath + ',0'
$shortcut.Save()
$savedShortcut = $shellObject.CreateShortcut($shortcutPath)
if ($savedShortcut.TargetPath -ne $pythonwExe -or $savedShortcut.IconLocation -ne ($iconPath + ',0')) {
    throw "The shortcut could not be verified: $shortcutPath"
}
Write-Host "Repaired desktop shortcut using $ShortcutIcon. If its old image remains, refresh the desktop (F5)."
