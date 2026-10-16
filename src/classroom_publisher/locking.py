"""OS-held lock: releases on process exit, including crashes. No stale-lock deletion."""
from contextlib import contextmanager
import os


@contextmanager
def single_instance(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    f = path.open('a+b')
    try:
        if f.tell() == 0:
            f.write(b'0')
            f.flush()
        f.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise ValueError('Classroom Publisher is already running. Finish or close its window first.') from exc
        yield
    finally:
        f.close()
