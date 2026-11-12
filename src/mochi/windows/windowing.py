"""GDK Win32 surfaces connected to native placement, in device pixels."""
import ctypes
from functools import lru_cache

from mochi.windows.native import desktop


def handle(window):
    surface = window.get_surface()
    if surface is None:
        return None
    import gi
    gi.require_version('GdkWin32', '4.0')
    from gi.repository import GdkWin32
    if not isinstance(surface, GdkWin32.Win32Surface):
        return None
    return native_surface_handle(surface)


@lru_cache(maxsize=1)
def _gtk_handle_function():
    # HWND is not introspectable in the bundled GI typelib. Call GTK's public
    # C ABI with the GObject pointer; never truncate pointers through c_int.
    gtk = ctypes.CDLL('libgtk-4-1.dll')
    function = gtk.gdk_win32_surface_get_handle
    function.argtypes = [ctypes.c_void_p]
    function.restype = ctypes.c_void_p
    return function


def native_surface_handle(surface, function=None):
    capsule_pointer = ctypes.pythonapi.PyCapsule_GetPointer
    capsule_pointer.argtypes = [ctypes.py_object, ctypes.c_char_p]
    capsule_pointer.restype = ctypes.c_void_p
    pointer = capsule_pointer(surface.__gpointer__, None)
    if not pointer:
        return None
    return (function or _gtk_handle_function())(pointer)


def move_window(window, x, y):
    hwnd = handle(window)
    return bool(hwnd and desktop().move(hwnd, x, y))


def get_window_position(window):
    hwnd = handle(window)
    return desktop().position(hwnd) if hwnd else None


def get_pointer_position(window):
    return desktop().pointer() if handle(window) else None


def primary_button_pressed(window):
    return bool(handle(window) and desktop().user32.GetAsyncKeyState(1) & 0x8000)


def request_keep_above(window):
    hwnd = handle(window)
    return bool(hwnd and desktop().keep_above(hwnd))


def apply_sticky_dock_properties(window):
    hwnd = handle(window)
    return bool(hwnd and desktop().keep_above(hwnd, passive=True))


def disable_frame_sync(window):
    return False  # Only X11 has the compositor handshake this workaround changes.
