from types import SimpleNamespace
from unittest.mock import Mock

from mochi.windows.monitor_follow import MonitorFollower


def test_moves_only_after_stable_foreground_on_another_monitor():
    area = (-1920, 0, 0, 1040)
    placement = SimpleNamespace(move_to=Mock())
    api = SimpleNamespace(
        same_thread=lambda _a, b: b == 3,
        shell_window=lambda hwnd: hwnd == 4,
        monitor_for_window=lambda hwnd: 10 if hwnd == 1 else 20,
        monitor_work_area=lambda monitor: area if monitor == 20 else None,
    )
    follower = MonitorFollower(api, placement, allowed=lambda: True)
    for foreground in (2, 3, 3, 4, 4, 2):
        follower.sample(1, foreground)
    placement.move_to.assert_not_called()
    follower.sample(1, 2)
    placement.move_to.assert_called_once_with(-1920 + 24, 24)


def test_pause_resets_debounce_and_same_screen_does_not_move():
    placement = SimpleNamespace(move_to=Mock())
    api = SimpleNamespace(
        same_thread=lambda *_: False,
        shell_window=lambda _: False,
        monitor_for_window=lambda _: 10,
    )
    allowed = True
    follower = MonitorFollower(api, placement, allowed=lambda: allowed)
    follower.sample(1, 2)
    allowed = False
    follower.sample(1, 2)
    allowed = True
    follower.sample(1, 2)
    follower.sample(1, 2)
    placement.move_to.assert_not_called()
