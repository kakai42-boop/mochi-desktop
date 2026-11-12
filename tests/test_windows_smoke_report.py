import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    'verify_smoke', Path(__file__).resolve().parents[1] / 'packaging/windows/verify_smoke.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def report():
    return dict(run_id='fresh', platform='win32', native_surface=True, audio_plugins=True)


def test_current_complete_windows_report_passes():
    module.verify(report(), 'fresh')


@pytest.mark.parametrize('key,value', [
    ('run_id', 'old'), ('run_id', ''), ('platform', 'linux'),
    ('native_surface', False), ('audio_plugins', False),
    ('audio_plugins', 'true'), ('error', 'failed to create HWND'),
])
def test_invalid_report_fails_closed(key, value):
    data = report()
    data[key] = value
    with pytest.raises(ValueError):
        module.verify(data, 'fresh')


def test_empty_expected_identity_is_rejected():
    with pytest.raises(ValueError):
        module.verify(report(), '')


def test_absent_native_result_is_rejected():
    data = report()
    del data['native_surface']
    with pytest.raises(ValueError):
        module.verify(data, 'fresh')
