"""Reject accidentally tracked runtime data; run before publishing."""
from pathlib import PurePosixPath
import subprocess


def forbidden(name):
    p = PurePosixPath(name)
    return (any(part in {'data', 'backups', '.radar-backups', '.venv', 'venv', '__pycache__'} for part in p.parts)
            or (p.name.startswith('.env') and p.name != '.env.example')
            or p.name == 'migration.json'
            or p.suffix in {'.db', '.sqlite', '.sqlite3', '.zip', '.pem', '.key'}
            or p.name in {'id_ed25519', 'id_rsa'})


if __name__ == '__main__':
    names = subprocess.check_output(['git', 'ls-files', '-z']).decode().split('\0')
    bad = [n for n in names if n and forbidden(n)]
    if bad:
        raise SystemExit('Runtime/private files must not be tracked: ' + ', '.join(bad))
    print('Tracked file privacy check passed.')
