"""Best-effort, non-focusing OS notifications; never change publication outcome."""
import base64
import json
import os
import shutil
import subprocess
import sys


WINDOWS_SCRIPT = r'''
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$data = $env:CLASSROOM_NOTIFICATION | ConvertFrom-Json
$icon = New-Object System.Windows.Forms.NotifyIcon
$icon.Icon = [System.Drawing.SystemIcons]::Information
$icon.Text = 'Classroom Publisher'
$icon.Visible = $true
$context = New-Object System.Windows.Forms.ApplicationContext
$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 12000
$timer.Add_Tick({ $timer.Stop(); $icon.Dispose(); $context.ExitThread() })
$timer.Start()
$icon.ShowBalloonTip(10000, $data.title, $data.text, [System.Windows.Forms.ToolTipIcon]::Info)
[System.Windows.Forms.Application]::Run($context)
'''

MAC_SCRIPT = '''on run argv
display notification (item 2 of argv) with title (item 1 of argv)
end run'''


def notify(title, text):
    """Launch a short-lived notification helper without waiting or opening a console.

    Notification text is data, never interpolated into executable script source.
    OS notification settings may suppress delivery.
    """
    try:
        kwargs = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if sys.platform == 'win32':
            env = os.environ.copy()
            env['CLASSROOM_NOTIFICATION'] = json.dumps({'title': title[:63], 'text': text[:255]}, ensure_ascii=False)
            script = base64.b64encode(WINDOWS_SCRIPT.encode('utf-16-le')).decode('ascii')
            command = ['powershell.exe', '-NoProfile', '-NonInteractive', '-STA', '-EncodedCommand', script]
            kwargs.update(env=env, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000))
        elif sys.platform == 'darwin':
            command = ['/usr/bin/osascript', '-e', MAC_SCRIPT, title, text]
        elif shutil.which('notify-send'):
            command = ['notify-send', '--app-name=Classroom Publisher', '--', title, text]
        else:
            return False
        subprocess.Popen(command, **kwargs)
        return True
    except OSError:
        return False
