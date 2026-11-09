"""Follow the active desktop using the public Windows Shell interface."""

import ctypes as c
import uuid

from mochi.windows.native import BOOL, HANDLE, bind


class GUID(c.Structure):
    _fields_ = [('data', c.c_ubyte * 16)]

    @classmethod
    def parse(cls, value):
        return cls.from_buffer_copy(uuid.UUID(value).bytes_le)


def shell_desktop_hint():
    """Read Explorer's active desktop hint when no app window can identify it."""
    import winreg

    path = r'Software\Microsoft\Windows\CurrentVersion\Explorer\VirtualDesktops'
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
            active, kind = winreg.QueryValueEx(key, 'CurrentVirtualDesktop')
            desktops, ids_kind = winreg.QueryValueEx(key, 'VirtualDesktopIDs')
    except OSError:
        return None
    if kind != winreg.REG_BINARY or ids_kind != winreg.REG_BINARY:
        return None
    if len(active) != 16 or not any(active) or len(desktops) % 16:
        return None
    if any(active == desktops[i:i + 16] for i in range(0, len(desktops), 16)):
        return GUID.from_buffer_copy(active)
    return None


class VirtualDesktopManager:
    def __init__(self):
        self.ole = c.WinDLL('ole32')
        self.pointer = c.c_void_p()
        init = bind(self.ole, 'CoInitializeEx', c.c_int32, HANDLE, c.c_uint32)
        bind(self.ole, 'CoUninitialize', None)
        status = init(None, 2)
        # GTK or another Windows component may already have initialized COM.
        if status < 0 and status != -2147417850:
            raise OSError('COM initialization failed')
        self.owns_com = status >= 0
        create = bind(self.ole, 'CoCreateInstance', c.c_int32, c.POINTER(GUID), HANDLE,
                      c.c_uint32, c.POINTER(GUID), c.POINTER(c.c_void_p))
        clsid = GUID.parse('aa509086-5ca9-4c25-8f95-589d3c07b48a')
        iid = GUID.parse('a5cd92ff-29be-454c-8d04-d82879fb3f1b')
        if create(c.byref(clsid), None, 1, c.byref(iid), c.byref(self.pointer)) < 0:
            self.close()
            raise OSError('Windows virtual desktop manager unavailable')

    def _call(self, slot, result, types, *args):
        table = c.cast(self.pointer, c.POINTER(c.POINTER(c.c_void_p))).contents
        method = c.WINFUNCTYPE(result, c.c_void_p, *types)(table[slot])
        return method(self.pointer, *args)

    def current(self, hwnd):
        current = BOOL()
        status = self._call(3, c.c_int32, (HANDLE, c.POINTER(BOOL)), hwnd, c.byref(current))
        return None if status < 0 else bool(current.value)

    def desktop_id(self, hwnd):
        desktop = GUID()
        status = self._call(4, c.c_int32, (HANDLE, c.POINTER(GUID)), hwnd, c.byref(desktop))
        return desktop if status >= 0 and any(desktop.data) else None

    def move(self, hwnd, desktop):
        return self._call(5, c.c_int32, (HANDLE, c.POINTER(GUID)), hwnd, c.byref(desktop)) >= 0

    def close(self):
        if self.pointer:
            self._call(2, c.c_uint32, ())
            self.pointer = c.c_void_p()
        if self.owns_com:
            self.ole.CoUninitialize()
            self.owns_com = False


class DesktopFollower:
    """Move Mochi's window after an active-desktop switch, with no activation."""

    def __init__(self, window, foreground, *, manager, scheduler, repair_overlay=None,
                 desktop_hint=None):
        self.window = window
        self.foreground = foreground
        self.manager = manager
        self.scheduler = scheduler
        self.repair_overlay = repair_overlay
        self.desktop_hint = desktop_hint
        self._foreground = None
        self.source = scheduler.timeout_add(750, self.sample)

    def sample(self):
        hwnd = self.window()
        if not hwnd:
            return True
        foreground = self.foreground()
        if self.manager is not None and self.manager.current(hwnd) is False:
            target = None
            if foreground and foreground != hwnd and self.manager.current(foreground):
                target = self.manager.desktop_id(foreground)
            if target is None and self.desktop_hint is not None:
                target = self.desktop_hint()
                origin = self.manager.desktop_id(hwnd)
                if origin is not None and target is not None and bytes(origin) == bytes(target):
                    return True
            if target is None or not self.manager.move(hwnd, target):
                return True
        if self.repair_overlay is not None:
            self.repair_overlay(hwnd, foreground, foreground != self._foreground)
        self._foreground = foreground
        return True

    def stop(self):
        if self.source is not None:
            self.scheduler.source_remove(self.source)
            self.source = None
            if self.manager is not None:
                self.manager.close()
