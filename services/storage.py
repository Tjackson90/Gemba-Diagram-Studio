"""Validated JSON storage with atomic replacement and a last-good backup."""
import json
import os
from pathlib import Path
import shutil
import tempfile
import threading

_lock = threading.RLock()


class StorageError(ValueError):
    pass


def read_json(path, default, validate=None):
    path = Path(path)
    if not path.exists():
        return default
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        if validate:
            validate(value)
        return value
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise StorageError(f'Cannot read {path}. Original preserved; check {path.name}.bak: {exc}') from exc


def write_json(path, value, validate=None):
    path = Path(path)
    if validate:
        validate(value)
    payload = json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            read_json(path, None, validate)  # Never overwrite a damaged file silently.
        fd, name = tempfile.mkstemp(prefix=path.name+'.', suffix='.tmp', dir=path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            if path.exists():
                shutil.copy2(path, path.with_name(path.name+'.bak'))
            os.replace(name, path)
        finally:
            if os.path.exists(name):
                os.unlink(name)


def safe_filename(name):
    import re
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '-', str(name)).strip(' .')[:120] or 'untitled'
    if name.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))}:
        name = '_' + name
    return name


def unique_path(path):
    path = Path(path)
    candidate = path
    counter = 2
    while candidate.exists():
        candidate = path.with_name(f'{path.stem}_{counter}{path.suffix}')
        counter += 1
    return candidate
