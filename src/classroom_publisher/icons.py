"""Bundled assets work in an installed wheel as well as an editable checkout."""
from pathlib import Path


def icon_path(name='chalkboard-check', extension='ico'):
    if name not in ('chalkboard-check', 'chalkboard-book', 'chalkboard-pencil', 'google-classroom'):
        raise ValueError('Unknown bundled icon.')
    if extension not in ('ico', 'png'):
        raise ValueError('Unknown icon format.')
    path = Path(__file__).resolve().parent / 'assets' / (name + '.' + extension)
    if not path.is_file():
        raise FileNotFoundError('Bundled icon is missing; reinstall Classroom Publisher: ' + str(path))
    return path
