"""Follow a stable foreground application between physical Windows monitors."""


class MonitorFollower:
    def __init__(self, desktop, placement, *, allowed, can_recover=None):
        self.desktop = desktop
        self.placement = placement
        self.allowed = allowed
        self.can_recover = can_recover
        self._candidate = None

    def reset(self):
        self._candidate = None

    def sample(self, hwnd, foreground):
        current_monitor = self.desktop.monitor_for_window(hwnd)
        if not current_monitor and self.can_recover is not None and self.can_recover():
            self._candidate = None
            self.placement.restore()
            return
        if (not foreground or not self.allowed() or self.desktop.same_thread(hwnd, foreground)
                or self.desktop.shell_window(foreground)):
            self._candidate = None
            return
        monitor = self.desktop.monitor_for_window(foreground)
        if not monitor or monitor == current_monitor:
            self._candidate = None
            return
        candidate = (foreground, monitor)
        if candidate != self._candidate:
            self._candidate = candidate
            return
        area = self.desktop.monitor_work_area(monitor)
        if area is not None:
            # Leave room for the companion after the native DPI transition.
            self.placement.move_to(area[0] + 24, area[1] + 24)
