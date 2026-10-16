$ErrorActionPreference = 'Stop'
$installRoot = Join-Path $env:LOCALAPPDATA 'ClassroomPublisher'
$pythonExe = Join-Path $installRoot 'app\.venv\Scripts\python.exe'
& $pythonExe -m classroom_publisher.cli context-menu remove
if ($LASTEXITCODE -ne 0) { throw 'Could not remove Explorer action.' }
Write-Host 'Explorer action removed. Saved profiles and config were kept.'
