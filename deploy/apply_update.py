#!/usr/bin/env python3
"""Copy reviewed application code into an existing install, keeping private data."""
import ast
import datetime
import os
from pathlib import Path
import shutil
import sys
import tempfile

ROOT_FILES = {'Dockerfile','compose.yaml','requirements.txt','requirements.lock','package.json','README.md','MAPS.md','BETA.md','CONTRIBUTING.md','requirements-dev.txt','VERIFICATION.md','APPLICATION_SOURCES.md','.dockerignore','.gitignore','.env.example'}
ROOT_DIRS = {'radar','deploy','tests','templates','extension'}

def apply(source, target):
    source, target = Path(source).resolve(), Path(target).expanduser().resolve()
    if source == target or source in target.parents or target in source.parents:
        raise ValueError('Extract the update outside the existing installation.')
    if not (target / 'compose.yaml').is_file():
        raise ValueError('Target must be the existing jobradar installation.')
    files = []
    for path in source.rglob('*'):
        rel = path.relative_to(source)
        if any(p in {'__pycache__','.pytest_cache'} for p in rel.parts) or path.suffix == '.pyc':
            continue
        if rel.parts[0] not in ROOT_DIRS and str(rel) not in ROOT_FILES:
            continue
        if path.is_symlink():
            raise ValueError(f'Symlink in update: {rel}')
        if not path.is_file():
            continue
        dest = target / rel
        if any(p.is_symlink() for p in [dest, *dest.parents] if p != target.parent):
            raise ValueError(f'Symlink in target: {rel}')
        if path.suffix == '.py':
            ast.parse(path.read_text(), filename=str(rel))
        if not dest.exists() or path.read_bytes() != dest.read_bytes():
            files.append((path, rel, dest))
    if not files:
        print('Already up to date. Private settings and data were preserved.')
        return
    backup = target / '.radar-backups' / datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup.mkdir(parents=True, mode=0o700)
    os.chmod(backup.parent, 0o700)
    applied = []
    try:
        for path, rel, dest in files:
            old = backup / rel
            existed = dest.exists()
            if existed:
                old.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(dest, old)
            dest.parent.mkdir(parents=True, exist_ok=True)
            applied.append((dest, old, existed))
            fd, name = tempfile.mkstemp(prefix='.radar-update-', dir=dest.parent)
            os.close(fd)
            try:
                shutil.copy2(path, name)
                os.replace(name, dest)
            finally:
                if os.path.exists(name): os.unlink(name)
    except Exception:
        for dest, old, existed in reversed(applied):
            if existed: shutil.copy2(old, dest)
            elif dest.exists(): dest.unlink()
        raise
    print(f'Updated {len(files)} code files. Backup: {backup}')
    print('Existing .env, documents, database, and Docker data volume were preserved.')
    print('Next: cd to the installation and run sudo docker compose up -d --build')

if __name__ == '__main__':
    try:
        if len(sys.argv) != 2: raise ValueError('Usage: python3 deploy/apply_update.py ~/jobradar')
        apply(Path(__file__).resolve().parents[1], sys.argv[1])
    except Exception as error:
        sys.exit(f'Update stopped: {error}')
