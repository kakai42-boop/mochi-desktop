from dataclasses import replace
import hashlib
import json
import zipfile

import pytest

from mochi.windows.updates import (API, ASSET, MANAGED, REPOSITORY, WindowsRelease,
                                   WindowsUpdateSource, extract_verified)

COMMIT = '1' * 40


def test_release_discovery_selects_only_a_windows_asset_from_the_requested_channel():
    def release(tag, prerelease=False, digest=True):
        asset = {'name': ASSET, 'state': 'uploaded', 'size': 100,
                 'browser_download_url': f'https://github.com/{REPOSITORY}/releases/download/{tag}/{ASSET}'}
        if digest:
            asset['digest'] = 'sha256:' + 'a' * 64
        return {'tag_name': tag, 'prerelease': prerelease, 'assets': [asset]}

    def read(url):
        if url == f'{API}/releases?per_page=30':
            return [release('v9.0.0'), release('windows-v9.0.0', digest=False),
                    release('windows-preview-42', prerelease=True), release('windows-v0.4.2')]
        return {'sha': COMMIT}

    source = WindowsUpdateSource(read)
    assert source.find('main').tag == 'windows-preview-42'
    assert source.find('release').tag == 'windows-v0.4.2'


def archive_fixture(path, unsafe=None):
    with zipfile.ZipFile(path, 'w') as bundle:
        for name in MANAGED:
            if name in ('assets', 'runtime', 'src'):
                bundle.writestr(f'Mochi/{name}/', '')
            elif name == 'build-info.json':
                bundle.writestr('Mochi/build-info.json', json.dumps({'source_commit': COMMIT, 'version': '1'}))
            else:
                bundle.writestr(f'Mochi/{name}', 'fixture')
        bundle.writestr('Mochi/runtime/bin/pythonw.exe', 'fixture')
        if unsafe:
            bundle.writestr(unsafe, 'unsafe')
    payload = path.read_bytes()
    return WindowsRelease(COMMIT, 'windows-preview-1', '', hashlib.sha256(payload).hexdigest(), len(payload))


def test_verified_archive_is_staged_with_its_exact_identity(tmp_path):
    archive = tmp_path / 'package.zip'
    package = archive_fixture(archive)
    candidate = extract_verified(archive, tmp_path, package)
    assert (candidate / 'Mochi.exe').read_text() == 'fixture'


@pytest.mark.parametrize('field,value,match', [
    ('size', 1, 'size'), ('digest', '0' * 64, 'SHA-256'), ('commit', '0' * 40, 'requested commit'),
])
def test_wrong_package_identity_is_rejected(tmp_path, field, value, match):
    archive = tmp_path / 'package.zip'
    package = replace(archive_fixture(archive), **{field: value})
    with pytest.raises(ValueError, match=match):
        extract_verified(archive, tmp_path, package)


@pytest.mark.parametrize('unsafe', ['Mochi/../outside', 'Mochi/src\\outside', 'Mochi/other.exe', 'Mochi/src/note.'])
def test_unsafe_archive_is_rejected_before_extraction(tmp_path, unsafe):
    archive = tmp_path / 'package.zip'
    package = archive_fixture(archive, unsafe)
    with pytest.raises(ValueError, match='unsafe archive path'):
        extract_verified(archive, tmp_path, package)
    assert not (tmp_path / 'Mochi').exists()
