"""Fetch the locked MSYS2 UCRT64 runtime; build-time only, never run by Mochi.

Requires Python 3.12+ and the `zstd` command, on Linux or MSYS2.
Archives are SHA256 checked against runtime-lock.json before extraction.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tarfile
import urllib.request

BASE = 'https://repo.msys2.org/mingw/ucrt64/'


def fetch(package, cache):
    name = package['file']
    if PurePosixPath(name).name != name:
        raise ValueError('Invalid package filename')
    path = cache / name
    if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != package['sha256']:
        temporary = path.with_suffix('.download')
        with urllib.request.urlopen(BASE + name, timeout=120) as response, temporary.open('wb') as target:
            shutil.copyfileobj(response, target)
        if hashlib.sha256(temporary.read_bytes()).hexdigest() != package['sha256']:
            temporary.unlink()
            raise ValueError(f'Checksum mismatch: {name}')
        temporary.replace(path)
    return path


def unpack(path, destination):
    # Only runtime files are shipped; preserve licenses, DLLs, typelibs,
    # Python, schemas, fonts and icons. All linked libraries remain replaceable.
    process = subprocess.Popen(['zstd', '-dc', str(path)], stdout=subprocess.PIPE)
    try:
        with tarfile.open(fileobj=process.stdout, mode='r|') as archive:
            for member in archive:
                parts = PurePosixPath(member.name).parts
                if not parts or parts[0] != 'ucrt64' or '..' in parts:
                    continue
                if len(parts) < 3 or parts[1] not in {'bin', 'lib', 'libexec', 'share', 'etc'}:
                    continue
                if member.name.endswith(('.a', '.h', '.pc', '.gir')):
                    continue
                if parts[1] == 'share' and parts[2] in {'doc', 'man', 'gtk-doc', 'locale', 'vala'}:
                    continue
                if not member.isfile():
                    continue
                target = destination.joinpath(*parts[1:])
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as source, target.open('wb') as output:
                    shutil.copyfileobj(source, output)
        if process.wait() != 0:
            raise RuntimeError(f'Decompression failed: {path.name}')
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        process.stdout.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    lock = json.loads(Path(__file__).with_name('runtime-lock.json').read_text())
    with ThreadPoolExecutor(max_workers=6) as pool:
        paths = list(pool.map(lambda p: fetch(p, args.cache), lock))
    for path in paths:
        unpack(path, args.out)
    shutil.copy2(Path(__file__).with_name('runtime-lock.json'), args.out / 'runtime-lock.json')
    print(f'Verified and extracted {len(paths)} runtime packages to {args.out}')


if __name__ == '__main__':
    main()
