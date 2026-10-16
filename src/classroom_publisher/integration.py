"""Per-user Windows integration, without administrator rights or a shell intermediary."""
import os
import sys
from pathlib import Path

KEYS = (r'Software\Classes\Directory\shell\ClassroomPublisher',
        r'Software\Classes\Directory\Background\shell\ClassroomPublisher')


def windows_command(executable, config, token):
    # Windows paths cannot contain literal double quotes; validate rather than escape them.
    if any('"' in str(v) for v in (executable, config)) or token not in ('%1', '%V'):
        raise ValueError('Invalid context-menu path.')
    return f'"{executable}" -m classroom_publisher.cli publish "{token}" --config "{config}" --gui'


def context_menu(mode, config):
    if sys.platform != 'win32':
        raise ValueError('Explorer integration can only be installed or removed on Windows.')
    import winreg
    executable = Path(sys.executable).with_name('pythonw.exe')
    if mode == 'install' and not executable.exists():
        raise ValueError('Run this command using the installed virtual environment on Windows.')
    for key_path, token in zip(KEYS, ('%1', '%V')):
        if mode == 'install':
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                winreg.SetValueEx(key, '', 0, winreg.REG_SZ, 'Publish to Classroom')
                winreg.SetValueEx(key, 'Icon', 0, winreg.REG_SZ, str(executable))
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path + r'\command') as key:
                winreg.SetValueEx(key, '', 0, winreg.REG_SZ, windows_command(executable, config.resolve(), token))
        else:
            for suffix in (r'\command', ''):
                try:
                    winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key_path + suffix)
                except FileNotFoundError:
                    pass


def open_file(path):
    if sys.platform == 'win32':
        os.startfile(str(path))
    else:
        import subprocess
        subprocess.Popen(['open' if sys.platform == 'darwin' else 'xdg-open', str(path)])
