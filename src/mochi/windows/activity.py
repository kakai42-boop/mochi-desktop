"""Content-blind Windows activity sources with explicit lifecycle ownership."""
from __future__ import annotations

import ctypes as c
import logging
import threading
import time
from collections import deque

from mochi.windows.native import BOOL, DWORD, HANDLE, POINT, bind, desktop


class MSG(c.Structure):
    _fields_ = [('hwnd', HANDLE), ('message', c.c_uint32), ('wParam', c.c_size_t),
                ('lParam', c.c_ssize_t), ('time', DWORD), ('pt', POINT), ('private', DWORD)]


class WindowsInputBackend:
    """A dedicated message pump emits pulses, never keyboard identity/content.

    The hook forwards lParam to Windows without dereferencing it. Only the
    fact that a key-down occurred is reduced to a bounded, in-memory pulse.
    GTK callbacks run on the GTK thread, not inside the system hook.
    """
    name = 'Windows anonymous input'

    def __init__(self, hotkey=None):
        self.hotkey = hotkey
        self.last_error = None
        self.active = False
        self._thread = None
        self._thread_id = None
        self._source = None
        self._callback = None
        self._pending = deque(maxlen=128)
        self._ready = threading.Event()
        self._cancel = threading.Event()

    def start(self, callback):
        if self.active:
            return True
        from gi.repository import GLib
        self._callback = callback
        self._ready.clear()
        self._cancel.clear()
        self.last_error = None
        self._thread = threading.Thread(target=self._run, name='mochi-windows-input', daemon=True)
        self._thread.start()
        if not self._ready.wait(2) or not self.active:
            self.stop()
            return False
        self._source = GLib.timeout_add(50, self._drain)
        return True

    def _run(self):
        hook = None
        registered = False
        try:
            u = c.WinDLL('user32', use_last_error=True)
            k = c.WinDLL('kernel32', use_last_error=True)
            bind(k, 'GetCurrentThreadId', DWORD)
            bind(k, 'GetModuleHandleW', HANDLE, c.c_wchar_p)
            bind(u, 'PeekMessageW', BOOL, c.POINTER(MSG), HANDLE, c.c_uint, c.c_uint, c.c_uint)
            bind(u, 'GetMessageW', c.c_int, c.POINTER(MSG), HANDLE, c.c_uint, c.c_uint)
            bind(u, 'TranslateMessage', BOOL, c.POINTER(MSG))
            bind(u, 'DispatchMessageW', c.c_ssize_t, c.POINTER(MSG))
            bind(u, 'RegisterHotKey', BOOL, HANDLE, c.c_int, c.c_uint, c.c_uint)
            bind(u, 'UnregisterHotKey', BOOL, HANDLE, c.c_int)
            self._thread_id = k.GetCurrentThreadId()
            message = MSG()
            u.PeekMessageW(c.byref(message), None, 0, 0, 0)  # create message queue
            if self.hotkey is None:
                callback_type = c.WINFUNCTYPE(c.c_ssize_t, c.c_int, c.c_size_t, c.c_ssize_t)
                bind(u, 'SetWindowsHookExW', HANDLE, c.c_int, callback_type, HANDLE, DWORD)
                bind(u, 'CallNextHookEx', c.c_ssize_t, HANDLE, c.c_int, c.c_size_t, c.c_ssize_t)
                bind(u, 'UnhookWindowsHookEx', BOOL, HANDLE)

                @callback_type
                def hook_callback(code, message_kind, opaque_payload):
                    if code >= 0 and message_kind in (0x100, 0x104):
                        self._pending.append(None)
                    return u.CallNextHookEx(None, code, message_kind, opaque_payload)

                hook = u.SetWindowsHookExW(13, hook_callback, k.GetModuleHandleW(None), 0)
                if not hook:
                    raise OSError('Windows input hook unavailable')
            else:
                modifiers, key = self.hotkey
                registered = bool(u.RegisterHotKey(None, 1, modifiers | 0x4000, key))
                if not registered:
                    raise OSError('Windows shortcut already registered by another application')
            self.active = True
            self._ready.set()
            while not self._cancel.is_set():
                status = u.GetMessageW(c.byref(message), None, 0, 0)
                if status <= 0:
                    break
                if message.message == 0x312 and message.wParam == 1:
                    self._pending.append(None)
                u.TranslateMessage(c.byref(message))
                u.DispatchMessageW(c.byref(message))
        except Exception as exc:
            self.last_error = str(exc)
        finally:
            if hook:
                u.UnhookWindowsHookEx(hook)
            if registered:
                u.UnregisterHotKey(None, 1)
            self.active = False
            self._ready.set()

    def _drain(self):
        if not self.active:
            self._source = None
            return False
        for _ in range(min(len(self._pending), 64)):
            self._pending.popleft()
            if self._callback:
                self._callback()
        return True

    def stop(self):
        self._cancel.set()
        self._callback = None
        if self._source is not None:
            from gi.repository import GLib
            GLib.source_remove(self._source)
            self._source = None
        if self._thread_id is not None:
            u = c.WinDLL('user32', use_last_error=True)
            bind(u, 'PostThreadMessageW', BOOL, DWORD, c.c_uint, c.c_size_t, c.c_ssize_t)
            u.PostThreadMessageW(self._thread_id, 0x12, 0, 0)
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._thread = None
        self._thread_id = None
        self.active = False
        self._pending.clear()


class PollMonitor:
    name = 'Windows desktop signals'

    def __init__(self, *, api=None, glib=None, logger=None):
        self.api = api
        self.glib = glib
        self._logger = logger or logging.getLogger(__name__)
        self._source = None
        self.available = False
        self.last_error = None

    def start(self):
        if self.available:
            return True
        try:
            if self.api is None:
                self.api = desktop()
            if self.glib is None:
                from gi.repository import GLib
                self.glib = GLib
            self.sample()
            self._source = self.glib.timeout_add(1000, self._poll)
            self.available = True
            return True
        except Exception as exc:
            self.last_error = str(exc)
            self.stop()
            return False

    def _poll(self):
        try:
            self.sample()
        except Exception as exc:
            self.last_error = str(exc)
        return self.available

    def stop(self):
        self.available = False
        if self._source is not None:
            self.glib.source_remove(self._source)
            self._source = None


class WindowsPresenceBackend(PollMonitor):
    def start(self, on_user_idle, on_user_active):
        self._idle_callback, self._active_callback = on_user_idle, on_user_active
        self._idle = None
        return super().start()

    def sample(self):
        seconds = self.api.idle_seconds()
        if seconds is None:
            return
        idle = seconds >= 60
        if idle != self._idle:
            self._idle = idle
            (self._idle_callback if idle else self._active_callback)()


class WindowsFileContextBackend(PollMonitor):
    def start(self, on_started, on_stopped):
        self._started, self._stopped = on_started, on_stopped
        self._browsing = False
        return super().start()

    def sample(self):
        _, _, browsing = self.api.foreground()
        if browsing != self._browsing:
            self._browsing = browsing
            (self._started if browsing else self._stopped)()


class WindowsAppCategoryMonitor(PollMonitor):
    def __init__(self, *, on_category_changed, on_category_snapshot=None,
                 on_focus_changed=None, on_tab_changed=None, tab_backend=None, **kwargs):
        super().__init__(**kwargs)
        self.changed = on_category_changed
        self.snapshot = on_category_snapshot
        self.focus = on_focus_changed
        self.tab_changed = on_tab_changed
        self._tab_backend = tab_backend
        self._last_tab = float('-inf')
        self.category = 'unknown'
        self._window = None
        self._baseline = False

    def start(self):
        if not super().start():
            return False
        if self.tab_changed is not None:
            if self._tab_backend is None:
                from mochi.windows.browser_activity import BrowserChangeBackend
                self._tab_backend = BrowserChangeBackend()
            if not self._tab_backend.start(self._on_tab_hint):
                self._logger.debug('Browser changes unavailable: %s', self._tab_backend.last_error)
        return True

    def _on_tab_hint(self, hwnd, age):
        from mochi.windows.browser_activity import tab_hint_allowed
        foreground, category, _ = self.api.foreground()
        if foreground != self._window:
            return  # A focus switch is already handled by the focus signal.
        if not tab_hint_allowed(hwnd, foreground, category, self.api.idle_seconds(), age):
            return
        now = time.monotonic()
        if now - self._last_tab < 0.5:
            return
        self._last_tab = now
        if self.tab_changed:
            self.tab_changed()

    def sample(self):
        hwnd, category, _ = self.api.foreground()
        if not self._baseline:
            self._baseline = True
            self._window, self.category = hwnd, category
            if self.snapshot:
                self.snapshot(category)
            return
        if hwnd != self._window:
            self._window = hwnd
            if self.focus:
                self.focus(category)
        if category != self.category:
            self.category = category
            self.changed(category)

    def stop(self):
        if self._tab_backend is not None:
            self._tab_backend.stop()
        self._last_tab = float('-inf')
        super().stop()
        self._baseline = False
        self._window = None


class WindowsSessionMonitor(PollMonitor):
    def __init__(self, *, on_away, on_returned, **kwargs):
        super().__init__(**kwargs)
        self._away, self._returned = on_away, on_returned
        self.blocked = False
        self._last_tick = None

    def sample(self):
        now = time.monotonic()
        blocked = self.api.session_blocked()
        # A long gap in polling can be suspend. Coalesce with any lock state.
        if self._last_tick is not None and now - self._last_tick > 15 and not self.blocked:
            self.blocked = True
            self._away()
        self._last_tick = now
        if blocked != self.blocked:
            self.blocked = blocked
            (self._away if blocked else self._returned)()


class WindowsSystemMonitor(PollMonitor):
    def __init__(self, *, on_battery_low, on_charging_started,
                 on_network_lost, on_network_restored, **kwargs):
        super().__init__(**kwargs)
        self.low, self.charging = on_battery_low, on_charging_started
        self.lost, self.restored = on_network_lost, on_network_restored
        self._battery = None
        self._network = None

    def sample(self):
        battery = self.api.battery()
        if battery is not None and self._battery is not None:
            percentage, ac = battery
            old_percentage, old_ac = self._battery
            if percentage is not None and ac is False and percentage <= 20 and (old_percentage is None or old_percentage > 20):
                self.low(percentage)
            if ac is True and old_ac is False:
                self.charging(percentage)
        if battery is not None:
            self._battery = battery
        # Gio's Windows network monitor observes local OS connectivity only.
        from gi.repository import Gio
        connected = Gio.NetworkMonitor.get_default().get_network_available()
        if self._network is not None and connected != self._network:
            (self.restored if connected else self.lost)()
        self._network = connected
