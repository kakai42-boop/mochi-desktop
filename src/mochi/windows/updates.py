"""Verified preparation and release discovery for the Windows package."""
from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import tempfile
from urllib.parse import quote
from urllib.request import Request, urlopen
import zipfile

from mochi.update.model import InstalledBuild, UpdateMetadata

REPOSITORY = 'kakai42-boop/mochi-desktop'
API = f'https://api.github.com/repos/{REPOSITORY}'
ASSET = 'Mochi-Windows11-Portable.zip'
MAX_DOWNLOAD = 512 * 1024 * 1024
MAX_EXPANDED = 2 * 1024 * 1024 * 1024
MANAGED = ('assets', 'runtime', 'src', 'bootstrap.py', 'native_checks.py',
           'LICENSE', 'LISEZ-MOI.txt', 'build-info.json', 'Mochi.exe')


@dataclass(frozen=True)
class WindowsRelease:
    commit: str
    tag: str
    url: str
    digest: str
    size: int


def _request(url):
    return Request(url, headers={'User-Agent': 'Mochi-Windows-Updater'})


def read_json(url):
    with urlopen(_request(url), timeout=15) as response:
        payload = response.read(2 * 1024 * 1024 + 1)
    if len(payload) > 2 * 1024 * 1024:
        raise ValueError('The Windows update metadata is too large.')
    return json.loads(payload)


class WindowsUpdateSource:
    def __init__(self, reader=read_json):
        self.reader = reader
        self._tags = {}

    def find(self, channel):
        prefix = 'windows-preview-' if channel == 'main' else 'windows-v'
        for release in self.reader(f'{API}/releases?per_page=30'):
            tag = release.get('tag_name', '')
            if (release.get('draft') or not tag.startswith(prefix)
                    or bool(release.get('prerelease')) != (channel == 'main')
                    or not re.fullmatch(r'[A-Za-z0-9._-]{1,120}', tag)):
                continue
            url = f'https://github.com/{REPOSITORY}/releases/download/{tag}/{ASSET}'
            for asset in release.get('assets', ()):
                digest = asset.get('digest') or ''
                size = asset.get('size')
                if (asset.get('name') != ASSET or asset.get('state') != 'uploaded'
                        or asset.get('browser_download_url') != url
                        or not re.fullmatch(r'sha256:[0-9a-f]{64}', digest)
                        or type(size) is not int or not 0 < size <= MAX_DOWNLOAD):
                    continue
                commit = self.reader(f'{API}/commits/{quote(tag, safe="")}').get('sha', '')
                if not re.fullmatch(r'[0-9a-f]{40}', commit):
                    raise ValueError('The Windows release commit is invalid.')
                self._tags[commit] = tag
                return WindowsRelease(commit, tag, url, digest[7:], size)
        raise ValueError('No Windows package has been published on this channel yet.')

    def resolve_latest_release(self):
        release = self.find('release')
        return release.tag, release.commit

    def resolve_main_sha(self):
        return self.find('main').commit

    def compare_commits(self, installed, target):
        if not all(re.fullmatch(r'[0-9a-f]{40}', commit) for commit in (installed, target)):
            raise ValueError('The Windows build identity is invalid.')
        status = self.reader(f'{API}/compare/{installed}...{target}').get('status')
        if status not in ('ahead', 'behind', 'identical', 'diverged'):
            raise ValueError('The release ancestry could not be verified.')
        return status

    def fetch_metadata(self, commit):
        return UpdateMetadata(self._tags[commit], 'release', ('Packaged Windows update',))


class WindowsInstallMetadata:
    def __init__(self, root=None):
        self.root = root or Path(__file__).resolve().parents[3]

    def load(self):
        try:
            info = json.loads((self.root / 'build-info.json').read_text(encoding='utf-8'))
            if not isinstance(info, dict):
                return None
            commit = info.get('source_commit', '')
            version = info.get('version')
            if not isinstance(version, str) or not version or not re.fullmatch(r'[0-9a-f]{40}', commit):
                return None
            return InstalledBuild(version, commit, 'release', 'bundled')
        except (OSError, TypeError, ValueError, KeyError):
            return None


def extract_verified(archive, workspace, package):
    if archive.stat().st_size != package.size:
        raise ValueError('The Windows package size differs from the release.')
    with archive.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    if digest != package.digest:
        raise ValueError('The Windows package SHA-256 differs from the release.')
    with zipfile.ZipFile(archive) as bundle:
        entries = bundle.infolist()
        if sum(entry.file_size for entry in entries) > MAX_EXPANDED:
            raise ValueError('The expanded Windows package is too large.')
        seen = set()
        for entry in entries:
            path = PurePosixPath(entry.filename)
            if (not path.parts or path.parts[0] != 'Mochi' or '..' in path.parts
                    or any(char in entry.filename for char in '\\<>:"|?*')
                    or any(part.endswith(('.', ' ')) for part in path.parts)
                    or (len(path.parts) == 1 and not entry.is_dir())
                    or (len(path.parts) > 1 and path.parts[1] not in MANAGED)
                    or stat.S_ISLNK(entry.external_attr >> 16)):
                raise ValueError('The Windows package contains an unsafe archive path.')
            name = str(path).casefold()
            if name in seen:
                raise ValueError('The Windows package contains duplicate paths.')
            seen.add(name)
        bundle.extractall(workspace)
    candidate = workspace / 'Mochi'
    metadata = WindowsInstallMetadata(candidate).load()
    if metadata is None or metadata.commit != package.commit:
        raise ValueError('The downloaded package does not contain the requested commit.')
    for name in MANAGED:
        if not (candidate / name).exists():
            raise ValueError('Incomplete Windows package: ' + name)
    if not (candidate / 'runtime/bin/pythonw.exe').is_file():
        raise ValueError('The Windows package runtime is missing.')
    return candidate


def prepare_update(target, cancel, *, root=None):
    root = (root or WindowsInstallMetadata().root).resolve()
    package = WindowsUpdateSource().find(target.metadata.channel)
    if package.commit != target.commit:
        raise ValueError('The Windows release changed. Check for updates again.')
    workspace = Path(tempfile.mkdtemp(prefix='.mochi-update-', dir=root.parent))
    try:
        archive = workspace / 'package.zip'
        with urlopen(_request(package.url), timeout=30) as response, archive.open('wb') as output:
            count = 0
            while chunk := response.read(1024 * 1024):
                count += len(chunk)
                if cancel.is_set():
                    raise InterruptedError('The update was cancelled.')
                if count > package.size:
                    raise ValueError('The download exceeded the release package size.')
                output.write(chunk)
        extract_verified(archive, workspace, package)
        archive.unlink()
        if cancel.is_set():
            raise InterruptedError('The update was cancelled.')
        (workspace / 'request.json').write_text(json.dumps({
            'root': str(root),
            'pid': os.getpid(), 'launcher_pid': os.getppid(),
        }), encoding='utf-8')
        return workspace
    except Exception:
        shutil.rmtree(workspace, ignore_errors=True)
        raise


def launch_update(workspace):
    script = Path(__file__).with_name('update_transaction.ps1').read_text(encoding='utf-8')
    command = base64.b64encode(script.encode('utf-16-le')).decode('ascii')
    powershell = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    environment = dict(os.environ, MOCHI_UPDATE_REQUEST=str(workspace / 'request.json'))
    return subprocess.Popen([str(powershell), '-NoProfile', '-NonInteractive', '-EncodedCommand', command],
                            cwd=workspace, env=environment, stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            creationflags=subprocess.CREATE_NO_WINDOW)
