"""Small, typed Win32 boundary, independent of GTK and the behavior engine."""
from __future__ import annotations

import ctypes as c
from functools import lru_cache
from pathlib import PureWindowsPath

# Explicit widths also make structure/layout tests meaningful on Linux.
DWORD = c.c_uint32
BOOL = c.c_int32
HANDLE = c.c_void_p
LONG = c.c_int32


class POINT(c.Structure):
    _fields_ = [('x', LONG), ('y', LONG)]


class RECT(c.Structure):
    _fields_ = [('left', LONG), ('top', LONG), ('right', LONG), ('bottom', LONG)]


class MONITORINFO(c.Structure):
    _fields_ = [('cbSize', DWORD), ('rcMonitor', RECT), ('rcWork', RECT), ('dwFlags', DWORD)]


class LASTINPUTINFO(c.Structure):
    _fields_ = [('cbSize', DWORD), ('dwTime', DWORD)]


class POWERSTATUS(c.Structure):
    _fields_ = [('ac', c.c_ubyte), ('flags', c.c_ubyte), ('percent', c.c_ubyte),
                ('saver', c.c_ubyte), ('life', DWORD), ('full_life', DWORD)]


def bind(dll, name, result, *args):
    fn = getattr(dll, name)
    fn.restype, fn.argtypes = result, list(args)
    return fn


def clamp_to_work_area(x, y, width, height, area, padding=8, bottom_padding=12):
    left, top, right, bottom = area
    return (round(max(left + padding, min(x, max(left + padding, right - width - padding)))),
            round(max(top + padding, min(y, max(top + padding, bottom - height - bottom_padding)))))


def classify_executable(path):
    name = PureWindowsPath(path).name.casefold()
    groups = {
        'vscode': {'code.exe', 'code - insiders.exe', 'cursor.exe', 'windsurf.exe'},
        'terminal': {'windowsterminal.exe', 'powershell.exe', 'pwsh.exe', 'cmd.exe', 'wezterm-gui.exe', 'alacritty.exe'},
        'browser': {'chrome.exe', 'msedge.exe', 'firefox.exe', 'brave.exe', 'opera.exe', 'vivaldi.exe'},
        'editor': {'notepad.exe', 'notepad++.exe', 'sublime_text.exe', 'idea64.exe', 'pycharm64.exe'},
        'pixel_art': {'aseprite.exe', 'libresprite.exe', 'pixelorama.exe'},
        'media': {'spotify.exe', 'vlc.exe', 'wmplayer.exe', 'music.ui.exe'},
    }
    return next((category for category, names in groups.items() if name in names), 'unknown')


class NativeDesktop:
    def __init__(self, user32=None):
        self.user32 = user32
        if user32 is not None:  # dependency injection for contract tests
            return
        self.user32 = u = c.WinDLL('user32', use_last_error=True)
        self.kernel32 = k = c.WinDLL('kernel32', use_last_error=True)
        bind(u, 'SetWindowPos', BOOL, HANDLE, HANDLE, c.c_int, c.c_int, c.c_int, c.c_int, c.c_uint)
        bind(u, 'GetWindowRect', BOOL, HANDLE, c.POINTER(RECT))
        bind(u, 'GetCursorPos', BOOL, c.POINTER(POINT))
        bind(u, 'GetAsyncKeyState', c.c_short, c.c_int)
        bind(u, 'GetWindowLongPtrW', c.c_ssize_t, HANDLE, c.c_int)
        bind(u, 'SetWindowLongPtrW', c.c_ssize_t, HANDLE, c.c_int, c.c_ssize_t)
        bind(u, 'MonitorFromPoint', HANDLE, POINT, DWORD)
        bind(u, 'GetMonitorInfoW', BOOL, HANDLE, c.POINTER(MONITORINFO))
        bind(u, 'GetLastInputInfo', BOOL, c.POINTER(LASTINPUTINFO))
        bind(u, 'GetForegroundWindow', HANDLE)
        bind(u, 'GetWindowThreadProcessId', DWORD, HANDLE, c.POINTER(DWORD))
        bind(u, 'OpenInputDesktop', HANDLE, DWORD, BOOL, DWORD)
        bind(u, 'GetUserObjectInformationW', BOOL, HANDLE, c.c_int, c.c_void_p, DWORD, c.POINTER(DWORD))
        bind(u, 'CloseDesktop', BOOL, HANDLE)
        bind(k, 'GetTickCount', DWORD)
        bind(k, 'GetSystemPowerStatus', BOOL, c.POINTER(POWERSTATUS))
        bind(k, 'OpenProcess', HANDLE, DWORD, BOOL, DWORD)
        bind(k, 'QueryFullProcessImageNameW', BOOL, HANDLE, DWORD, c.c_wchar_p, c.POINTER(DWORD))
        bind(k, 'CloseHandle', BOOL, HANDLE)

    def move(self, hwnd, x, y):
        return bool(self.user32.SetWindowPos(hwnd, None, round(x), round(y), 0, 0, 0x01 | 0x04 | 0x10))

    def position(self, hwnd):
        rect = RECT()
        return (rect.left, rect.top) if self.user32.GetWindowRect(hwnd, c.byref(rect)) else None

    def pointer(self):
        point = POINT()
        return (point.x, point.y) if self.user32.GetCursorPos(c.byref(point)) else None

    def keep_above(self, hwnd, *, passive=False):
        style = self.user32.GetWindowLongPtrW(hwnd, -20)
        # The pet must not activate; menus must remain keyboard accessible.
        style = (style | 0x80) & ~0x40000  # TOOLWINDOW, not APPWINDOW
        if passive:
            style |= 0x08000000  # NOACTIVATE
        self.user32.SetWindowLongPtrW(hwnd, -20, style)
        return bool(self.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x01 | 0x02 | 0x10 | 0x20))

    def work_area(self, x, y):
        monitor = self.user32.MonitorFromPoint(POINT(round(x), round(y)), 2)
        info = MONITORINFO()
        info.cbSize = c.sizeof(info)
        if not monitor or not self.user32.GetMonitorInfoW(monitor, c.byref(info)):
            return None
        r = info.rcWork
        return r.left, r.top, r.right, r.bottom

    def idle_seconds(self):
        info = LASTINPUTINFO(c.sizeof(LASTINPUTINFO), 0)
        if not self.user32.GetLastInputInfo(c.byref(info)):
            return None
        return ((self.kernel32.GetTickCount() - info.dwTime) & 0xffffffff) / 1000

    def foreground(self):
        hwnd = self.user32.GetForegroundWindow()
        pid = DWORD()
        self.user32.GetWindowThreadProcessId(hwnd, c.byref(pid))
        process = self.kernel32.OpenProcess(0x1000, False, pid.value)
        if not process:
            return hwnd, 'unknown', False
        try:
            buffer = c.create_unicode_buffer(32768)
            size = DWORD(len(buffer))
            if not self.kernel32.QueryFullProcessImageNameW(process, 0, buffer, c.byref(size)):
                return hwnd, 'unknown', False
            # Discard the executable path immediately; never inspect window titles.
            return hwnd, classify_executable(buffer.value), PureWindowsPath(buffer.value).name.casefold() == 'explorer.exe'
        finally:
            self.kernel32.CloseHandle(process)

    def battery(self):
        status = POWERSTATUS()
        if not self.kernel32.GetSystemPowerStatus(c.byref(status)):
            return None
        return (None if status.percent == 255 or status.flags & 128 else status.percent,
                None if status.ac == 255 else bool(status.ac))

    def session_blocked(self):
        # Read only the input desktop's system name; never switch desktops.
        desktop = self.user32.OpenInputDesktop(0, False, 0x0001)
        if not desktop:
            return True
        try:
            name = c.create_unicode_buffer(256)
            needed = DWORD()
            if not self.user32.GetUserObjectInformationW(desktop, 2, name, c.sizeof(name), c.byref(needed)):
                return True
            return name.value.casefold() != 'default'
        finally:
            self.user32.CloseDesktop(desktop)


@lru_cache(maxsize=1)
def desktop():
    return NativeDesktop()
