"""Small file-system primitives that fail closed rather than overwrite outputs."""
from contextlib import contextmanager
import os
from pathlib import Path
import time


def publish_file(source, destination):
    # Same-filesystem hard link is an atomic create-if-absent, including dangling links.
    os.link(source, destination)


def publish_directory(source, destination):
    """Reserve a new directory exclusively, then publish its flat, staged files."""
    destination = Path(destination)
    destination.mkdir()  # atomic reservation; never replace an existing empty directory
    original = destination.stat()
    created = []
    try:
        for item in Path(source).iterdir():
            target = destination / item.name
            publish_file(item, target)
            created.append(target)
    except BaseException:
        # Only clean up the directory we reserved, never a replacement by another actor.
        if destination.exists() and os.path.samestat(original, destination.stat()):
            for target in created:
                target.unlink(missing_ok=True)
            try:
                destination.rmdir()
            except OSError:
                pass
        raise


@contextmanager
def project_lock(path, timeout=5.0):
    lock = str(path) + '.lock'
    deadline = time.monotonic() + timeout
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise RuntimeError('项目正在保存或遗留了锁文件；请核实后重试。')
            time.sleep(0.02)
    try:
        yield
    finally:
        os.close(fd)
        os.unlink(lock)
