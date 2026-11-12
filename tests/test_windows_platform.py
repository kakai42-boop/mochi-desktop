"""Portable contract tests; real HWND/GTK integration is covered on Windows."""
from types import SimpleNamespace

from mochi.windows.native import NativeDesktop, clamp_to_work_area, classify_executable
from mochi.windows.activity import WindowsAppCategoryMonitor, WindowsPresenceBackend, WindowsSessionMonitor
from mochi.windows.agent_ipc import decode_event
import pytest


def test_negative_monitor_origin_and_taskbar_are_preserved():
    assert clamp_to_work_area(-4000, 4000, 256, 256, (-1920, 0, 0, 1040)) == (-1912, 772)


def test_oversized_window_never_produces_inverted_bounds():
    assert clamp_to_work_area(100, 100, 500, 500, (0, 0, 200, 200)) == (8, 8)


def test_categories_use_only_executable_basename():
    assert classify_executable(r'C:\Program Files\Microsoft VS Code\Code.exe') == 'vscode'
    assert classify_executable(r'C:\Users\browser\private.exe') == 'unknown'
    assert classify_executable('WindowsTerminal.exe') == 'terminal'
    assert classify_executable('msedge.exe') == 'browser'


def test_native_move_preserves_large_handles_and_does_not_activate():
    calls = []
    api = SimpleNamespace(SetWindowPos=lambda *args: calls.append(args) or 1)
    desktop = NativeDesktop(user32=api)
    assert desktop.move(0x100000002, -1200, 40)
    hwnd, _, x, y, _, _, flags = calls[0]
    assert (hwnd, x, y) == (0x100000002, -1200, 40)
    assert flags & 0x10  # SWP_NOACTIVATE
    assert flags & 0x04  # SWP_NOZORDER


def test_failed_window_lookup_returns_none():
    desktop = NativeDesktop(user32=SimpleNamespace(GetWindowRect=lambda *args: 0))
    assert desktop.position(123) is None


@pytest.mark.parametrize('data', [b'', b'working:short', b'working:'+b'a'*200,
                                b'unknown:0123456789abcdef', b'working:0123456789abcdeg',
                                b'working:0123456789abcdef:extra', b'\xff'])
def test_agent_transport_rejects_malformed_input(data):
    assert decode_event(data) is None


def test_agent_transport_accepts_only_opaque_event():
    assert decode_event(b'working:0123456789abcdef') == ('working', '0123456789abcdef')


class Scheduler:
    def __init__(self):
        self.callbacks = {}
    def timeout_add(self, interval, callback):
        self.callbacks[42] = callback
        return 42
    def source_remove(self, source):
        self.callbacks.pop(source)


def test_app_context_baseline_is_not_a_focus_change_and_stop_releases_timer():
    signals = []
    values = iter([(100, 'editor', False), (101, 'vscode', False), (101, 'vscode', False)])
    scheduler = Scheduler()
    monitor = WindowsAppCategoryMonitor(
        api=SimpleNamespace(foreground=lambda: next(values)), glib=scheduler,
        on_category_snapshot=lambda c: signals.append(('snapshot', c)),
        on_category_changed=lambda c: signals.append(('category', c)),
        on_focus_changed=lambda c: signals.append(('focus', c)))
    assert monitor.start()
    assert signals == [('snapshot', 'editor')]
    monitor.sample()
    monitor.sample()
    assert signals == [('snapshot', 'editor'), ('focus', 'vscode'), ('category', 'vscode')]
    monitor.stop()
    monitor.stop()
    assert not scheduler.callbacks


def test_presence_only_emits_edges():
    events = []
    values = iter([0, 61, 62, 0])
    backend = WindowsPresenceBackend(api=SimpleNamespace(idle_seconds=lambda: next(values)), glib=Scheduler())
    assert backend.start(lambda: events.append('idle'), lambda: events.append('active'))
    for _ in range(3):
        backend.sample()
    backend.stop()
    assert events == ['active', 'idle', 'active']


def test_locked_session_coalesces_return():
    events = []
    values = iter([False, True, True, False, False])
    monitor = WindowsSessionMonitor(api=SimpleNamespace(session_blocked=lambda: next(values)), glib=Scheduler(),
                                    on_away=lambda: events.append('away'), on_returned=lambda: events.append('returned'))
    assert monitor.start()
    for _ in range(4):
        monitor.sample()
    monitor.stop()
    assert events == ['away', 'returned']


def test_windows_preferences_use_roaming_appdata(monkeypatch, tmp_path):
    from mochi import config
    monkeypatch.setattr(config, 'sys', SimpleNamespace(platform='win32'))
    monkeypatch.setenv('APPDATA', str(tmp_path / 'Préférences'))
    store = config.ConfigStore()
    store.save_position(config.Position(-400, 12))
    assert store.path == tmp_path / 'Préférences/mochi/config.json'
    assert store.load_position() == config.Position(-400, 12)


def test_windows_pocket_uses_local_appdata(monkeypatch, tmp_path):
    from mochi import pocket_store
    monkeypatch.setattr(pocket_store, 'sys', SimpleNamespace(platform='win32'))
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'Données'))
    store = pocket_store.PocketStore()
    assert store.path == tmp_path / 'Données/mochi-desktop/pocket/pocket.json'


def test_debug_without_posix_signal(monkeypatch):
    from mochi import main
    calls = []
    monkeypatch.setattr(main, 'signal', SimpleNamespace())
    monkeypatch.setattr(main, 'faulthandler', SimpleNamespace(enable=lambda **kw: calls.append(kw)))
    main.enable_debug_stack_dumps()
    assert calls == [{'all_threads': True}]


def test_overlay_recovers_dropped_topmost_flag_while_own_popup_has_focus():
    from unittest.mock import Mock

    api = SimpleNamespace(GetWindowLongPtrW=lambda *_: 0x08000080,
                          GetWindowThreadProcessId=lambda *_: 42)
    desktop = NativeDesktop(user32=api)
    desktop.keep_above = Mock()
    desktop.repair_overlay(10, 11, True)
    desktop.keep_above.assert_called_once_with(10, passive=True)
