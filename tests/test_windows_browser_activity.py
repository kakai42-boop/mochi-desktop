from types import SimpleNamespace

import pytest

from mochi.windows.browser_activity import tab_hint_allowed
from mochi.windows.activity import WindowsAppCategoryMonitor


@pytest.mark.parametrize('hwnd,foreground,category,idle,age,expected', [
    (10, 10, 'browser', 0.1, 0.1, True),
    (10, 11, 'browser', 0.1, 0.1, False),
    (10, 10, 'editor', 0.1, 0.1, False),
    (10, 10, 'browser', 3, 0.1, False),
    (10, 10, 'browser', None, 0.1, False),
    (10, 10, 'browser', 0.1, 3, False),
    (0, 0, 'browser', 0.1, 0.1, False),
])
def test_content_free_hint_gates(hwnd, foreground, category, idle, age, expected):
    assert tab_hint_allowed(hwnd, foreground, category, idle, age) is expected


def test_monitor_debounces_tab_hints_and_owns_hook(monkeypatch):
    events = []
    hooks = []
    source = SimpleNamespace(start=lambda cb: hooks.append(cb) or True,
                             stop=lambda: events.append('stopped'))
    api = SimpleNamespace(foreground=lambda: (10, 'browser', False), idle_seconds=lambda: 0.1)
    glib = SimpleNamespace(timeout_add=lambda *args: 1, source_remove=lambda source: None)
    monitor = WindowsAppCategoryMonitor(api=api, glib=glib, tab_backend=source,
        on_category_changed=lambda category: None, on_tab_changed=lambda: events.append('tab'))
    monkeypatch.setattr('mochi.windows.activity.time.monotonic', lambda: 5)
    assert monitor.start()
    hooks[0](10, 0.1)
    hooks[0](10, 0.1)
    hooks[0](11, 0.1)
    assert events == ['tab']
    monitor.stop()
    assert events == ['tab', 'stopped']


def test_new_foreground_browser_can_report_a_change_before_polling():
    state = SimpleNamespace(window=10, category='editor')
    api = SimpleNamespace(foreground=lambda: (state.window, state.category, False),
                          idle_seconds=lambda: 0.1)
    calls = []
    monitor = WindowsAppCategoryMonitor(api=api, on_category_changed=lambda _: None,
                                       on_tab_changed=lambda: calls.append('tab'))
    monitor.sample()
    state.window, state.category = 11, 'browser'
    monitor._on_tab_hint(11, 0.1)
    assert calls == ['tab']
