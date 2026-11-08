"""Assemble a Windows folder after fetch_runtime.py and native launcher build."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def assemble(destination):
    root = Path(__file__).resolve().parents[2]
    if not (destination / 'runtime/bin/pythonw.exe').is_file():
        raise RuntimeError('Fetch the locked Windows runtime first')
    if not (destination / 'Mochi.exe').is_file():
        raise RuntimeError('Compile the native launcher first')
    for name in ('src', 'assets'):
        shutil.copytree(root / name, destination / name, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.egg-info'))
    shutil.copy2(root / 'LICENSE', destination / 'LICENSE')
    shutil.copy2(Path(__file__).with_name('bootstrap.py'), destination / 'bootstrap.py')
    shutil.copy2(root / 'docs/WINDOWS11.txt', destination / 'LISEZ-MOI.txt')
    files = {}
    for path in sorted((destination / 'src').rglob('*.py')):
        files[path.relative_to(destination).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    info = {'version': '0.4.1-win-preview1', 'upstream_commit': '471342631206c40d56bbba016578926e16ca8d0b',
            'target': 'Windows 11 x64', 'windows11_manual_qa': False, 'source_sha256': files}
    (destination / 'build-info.json').write_text(json.dumps(info, indent=2), encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('destination', type=Path)
    assemble(parser.parse_args().destination)
