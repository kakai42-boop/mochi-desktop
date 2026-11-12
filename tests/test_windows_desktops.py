from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from mochi.windows.desktops import DesktopFollower, GUID


def test_shell_guid_layout():
    assert bytes(GUID.parse('00112233-4455-6677-8899-aabbccddeeff')).hex() == '33221100554477668899aabbccddeeff'


@pytest.mark.parametrize('own_current,foreground_current,expected', [
    (False, True, True),
    (True, True, False),
    (None, True, False),
    (False, False, False),
])
def test_follows_only_to_a_confirmed_active_desktop(own_current, foreground_current, expected):
    manager = SimpleNamespace(
        current=lambda hwnd: own_current if hwnd == 12 else foreground_current,
        desktop_id=lambda hwnd: 'active-desktop', move=Mock(), close=Mock(),
    )
    scheduler = SimpleNamespace(timeout_add=Mock(return_value=42), source_remove=Mock())
    follower = DesktopFollower(lambda: 12, lambda: 99, manager=manager, scheduler=scheduler)
    assert follower.sample()
    if expected:
        manager.move.assert_called_once_with(12, 'active-desktop')
    else:
        manager.move.assert_not_called()
    follower.stop()
    follower.stop()
    scheduler.source_remove.assert_called_once_with(42)
    manager.close.assert_called_once_with()


def test_empty_desktop_uses_the_shell_hint_only_for_an_inactive_window():
    original = GUID.parse('00112233-4455-6677-8899-aabbccddeeff')
    target = GUID.parse('11112233-4455-6677-8899-aabbccddeeff')
    manager = SimpleNamespace(current=Mock(return_value=False),
                              desktop_id=Mock(return_value=original), move=Mock(return_value=True))
    scheduler = SimpleNamespace(timeout_add=Mock(return_value=42))
    hint = Mock(return_value=target)
    follower = DesktopFollower(lambda: 12, lambda: None, manager=manager,
                               scheduler=scheduler, desktop_hint=hint)
    follower.sample()
    manager.move.assert_called_once_with(12, target)
    manager.current.return_value = True
    follower.sample()
    hint.assert_called_once_with()


def test_stale_shell_hint_does_not_move_the_window_back_to_its_old_desktop():
    original = GUID.parse('00112233-4455-6677-8899-aabbccddeeff')
    manager = SimpleNamespace(current=Mock(return_value=False),
                              desktop_id=Mock(return_value=original), move=Mock())
    scheduler = SimpleNamespace(timeout_add=Mock(return_value=42))
    follower = DesktopFollower(lambda: 12, lambda: None, manager=manager,
                               scheduler=scheduler, desktop_hint=lambda: original)
    follower.sample()
    manager.move.assert_not_called()
