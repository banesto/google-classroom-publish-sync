"""Configuration contains paths and UI labels, never passwords or OAuth tokens."""
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse


def data_dir():
    if sys.platform == 'win32':
        return Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local')) / 'ClassroomPublisher'
    if sys.platform == 'darwin':
        return Path.home() / 'Library/Application Support/ClassroomPublisher'
    return Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'classroom-publisher'


def resolve_path(value, base):
    return (base / Path(os.path.expandvars(value)).expanduser()).resolve()


def class_id(url):
    parsed = urlparse(url)
    match = re.fullmatch(r'/(?:u/\d+/)?c/([A-Za-z0-9_-]+)(?:/.*)?', parsed.path)
    if parsed.scheme != 'https' or parsed.netloc != 'classroom.google.com' or not match:
        raise ValueError('Use an HTTPS classroom.google.com/c/... class URL.')
    return match[1]


def profile_path(key, config, base):
    child = config['children'][key]
    return resolve_path(child['profile'], base) if child.get('profile') else data_dir() / 'profiles' / key


def validate_config(config, base):
    children = config.get('children', {})
    if not children or not config.get('classes'):
        raise ValueError('Configure children and at least one class in config.json.')
    profiles = []
    emails = []
    for key, child in children.items():
        if not re.fullmatch(r'[A-Za-z0-9_-]+', key):
            raise ValueError('Child keys must contain only letters, numbers, underscores or hyphens.')
        email = child.get('email', '').strip().casefold()
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
            raise ValueError('Configure a valid email for ' + key)
        emails.append(email)
        profiles.append(profile_path(key, config, base).resolve())
    if len(set(emails)) != len(emails):
        raise ValueError('Each child needs a different email.')
    for i, p in enumerate(profiles):
        if any(p == q or p in q.parents or q in p.parents for q in profiles[i + 1:]):
            raise ValueError('Each child needs a different browser profile, without nested directories.')
    roots = []
    for c in config['classes']:
        if c.get('child') not in children:
            raise ValueError('Unknown child in class configuration.')
        class_id(c.get('url', ''))
        root = resolve_path(c['root'], base)
        if root in roots:
            raise ValueError('Each local class root must be unique.')
        roots.append(root)
        drive_path = c.get('drive_path')
        if not isinstance(drive_path, list) or not drive_path or any(
                not isinstance(n, str) or not n.strip() or n in ('.', '..') or '/' in n or '\\' in n
                for n in drive_path):
            raise ValueError('drive_path must list exact folder names from My Drive to the class root.')
    if any(p == r or r in p.parents or p in r.parents for p in profiles for r in roots):
        raise ValueError('Keep browser profiles separate from synced class roots.')
    return config


def load_config(path):
    path = Path(path).resolve()
    with path.open(encoding='utf-8-sig') as f:
        config = json.load(f)
    return validate_config(config, path.parent), path.parent
