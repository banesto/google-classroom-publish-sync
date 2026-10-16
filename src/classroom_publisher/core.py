import json
import os
import re
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from .config import class_id, profile_path, resolve_path, validate_config

MARKER = 'classroom-published.txt'
PENDING = '.classroom-pending.json'
SUPPORTED = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.pdf'}


def natural_key(name):
    return (tuple((1, int(s)) if s.isdigit() else (0, s.casefold())
                  for s in re.split(r'(\d+)', name)), name)


def classroom_url(url):
    try:
        class_id(url)
        return True
    except ValueError:
        return False


def attachment_snapshot(folder):
    files = [p for p in folder.iterdir() if p.suffix.casefold() in SUPPORTED]
    if any(p.is_symlink() or not p.is_file() for p in files):
        raise ValueError('Attachments must be regular files, not links or folders.')
    files.sort(key=lambda p: natural_key(p.name))
    if len(files) > 20:
        raise ValueError('Cannot publish: %d attachments; maximum 20. Excess files:\n%s\nNothing published.' %
                         (len(files), '\n'.join(p.name for p in files[20:])))
    if not files:
        raise ValueError('No supported attachments found.')
    snapshot = {}
    for p in files:
        stat = p.stat()
        if not stat.st_size:
            raise ValueError('Empty attachment: ' + p.name)
        snapshot[p.name] = [stat.st_size, stat.st_mtime_ns]
    return snapshot


@dataclass
class Publication:
    folder: Path
    child: str
    email: str
    profile: Path
    url: str
    text: str
    names: list
    drive_path: list = field(default_factory=list)
    snapshot: dict = field(default_factory=dict)


def prepare(folder, config, config_dir):
    validate_config(config, config_dir)
    folder = Path(folder).resolve(strict=True)
    if not folder.is_dir():
        raise ValueError('Select a publication folder.')
    if (folder / MARKER).exists():
        raise ValueError('Already published: classroom-published.txt exists.')
    if (folder / PENDING).exists():
        raise ValueError('Unresolved attempt. Inspect Classroom and use Recover; do not retry.')
    matches = []
    for c in config['classes']:
        root = resolve_path(c['root'], config_dir)
        if folder == root or root in folder.parents:
            matches.append((c, root))
    if len(matches) != 1:
        raise ValueError('Folder must be within exactly one configured class root. '
                         'Folders outside those roots or inside overlapping roots cannot be published.')
    c, root = matches[0]
    relative_parts = list(folder.relative_to(root).parts)
    child = config['children'][c['child']]
    snapshot = attachment_snapshot(folder)
    text = ' — '.join(relative_parts) if relative_parts else root.name
    description = folder / 'description.txt'
    if description.exists():
        extra = description.read_text(encoding='utf-8-sig').strip()
        if extra:
            text += '\n\n' + extra
    return Publication(folder, c['child'], child['email'].strip(),
                       profile_path(c['child'], config, config_dir), c['url'], text,
                       list(snapshot), c['drive_path'] + relative_parts, snapshot)


def exclusive_write(path, text):
    with path.open('x', encoding='utf-8', newline='\n') as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())


def begin(pub):
    if (pub.folder / MARKER).exists():
        raise ValueError('Success marker appeared; stopping.')
    record = {'started_at': datetime.now().astimezone().isoformat(), 'stage': 'preparing',
              'child': pub.child, 'email': pub.email, 'class_url': pub.url, 'text': pub.text,
              'names': pub.names, 'drive_path': pub.drive_path, 'snapshot': pub.snapshot}
    exclusive_write(pub.folder / PENDING, json.dumps(record, ensure_ascii=False, indent=2))


def update_pending(folder, **changes):
    path = Path(folder) / PENDING
    record = json.loads(path.read_text(encoding='utf-8'))
    record.update(changes)
    fd, temp = tempfile.mkstemp(prefix='.classroom-update-', dir=str(folder))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def recheck(pub):
    if (pub.folder / MARKER).exists():
        raise ValueError('Success marker appeared; stopping.')
    if attachment_snapshot(pub.folder) != pub.snapshot:
        raise ValueError('Files changed during review. Nothing further will be posted.')


def confirm(folder, post_url='', verification='operator verified text, author and all attachments after reload'):
    folder = Path(folder)
    record = json.loads((folder / PENDING).read_text(encoding='utf-8'))
    if post_url and (not classroom_url(post_url) or class_id(post_url) != class_id(record['class_url'])):
        raise ValueError('Post URL must belong to the configured Classroom class.')
    text = ('Google Classroom Publication\n============================\n'
            'Status: SUCCESS\nAttempt started at: %s\nConfirmed at: %s\nConfirmation: %s\n'
            'Student: %s (%s)\nClass: %s\nPost URL: %s\n\nPost text:\n%s\n\n'
            'Attachment count: %d\nAttached files (natural order):\n%s\n' %
            (record['started_at'], datetime.now().astimezone().isoformat(), verification,
             record['child'], record['email'], record['class_url'], post_url or 'Not retrieved',
             record['text'], len(record['names']), '\n'.join(record['names'])))
    if record.get('attachments'):
        text += '\nVerified Drive IDs:\n' + '\n'.join(a['name'] + ': ' + a['id'] for a in record['attachments']) + '\n'
    exclusive_write(folder / MARKER, text)
    (folder / PENDING).unlink()
