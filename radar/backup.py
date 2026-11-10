"""Consistent SQLite snapshots of every workspace plus encrypted registry."""
import os
from pathlib import Path
import sqlite3
import sys
import tarfile
import tempfile


def backup_all(destination,data_dir=None):
    data=Path(data_dir or os.getenv('RADAR_DATA','./data'))
    registry=data/'workspaces.sqlite'
    destination=Path(destination)
    with tempfile.TemporaryDirectory(prefix='radar-backup-') as temp:
        # Block new workspace registrations while enumerating DBs. Existing requests
        # can continue; SQLite's backup API produces a consistent snapshot per DB.
        lock=sqlite3.connect(registry,timeout=30) if registry.exists() else None
        try:
            if lock:lock.execute('BEGIN IMMEDIATE')
            paths=[data/'radar.sqlite',registry,*sorted((data/'workspaces').glob('*.sqlite'))]
            for source in paths:
                if not source.is_file():continue
                relative=source.relative_to(data);target=Path(temp)/relative
                target.parent.mkdir(parents=True,exist_ok=True)
                with sqlite3.connect(source,timeout=30) as src,sqlite3.connect(target) as dest:src.backup(dest)
            with tarfile.open(destination,'w:gz') as archive:
                for path in sorted(Path(temp).rglob('*.sqlite')):archive.add(path,arcname=str(path.relative_to(temp)))
            os.chmod(destination,0o600)
        finally:
            if lock:lock.rollback();lock.close()
    return destination


if __name__=='__main__':
    backup_all(sys.argv[1])
    print('Saved consistent workspace database snapshots. Preserve .env separately for decryption.')
