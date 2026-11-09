"""Content-free browser navigation hints from Windows accessibility events.

Only a window handle and event time cross the hook boundary. Neither window
titles nor accessibility objects/text are queried.
"""
import ctypes as c
import time

from mochi.windows.activity import MSG, WindowsInputBackend
from mochi.windows.native import BOOL, DWORD, HANDLE, bind


def tab_hint_allowed(hwnd, foreground, category, idle_seconds, age):
    return bool(hwnd and hwnd == foreground and category == 'browser'
                and idle_seconds is not None and 0 <= idle_seconds <= 2
                and 0 <= age <= 2)


class BrowserChangeBackend(WindowsInputBackend):
    name = 'Windows content-free browser changes'

    def _run(self):
        hook = None
        try:
            u = c.WinDLL('user32', use_last_error=True)
            k = c.WinDLL('kernel32', use_last_error=True)
            bind(k, 'GetCurrentThreadId', DWORD)
            bind(u, 'PeekMessageW', BOOL, c.POINTER(MSG), HANDLE, c.c_uint, c.c_uint, c.c_uint)
            bind(u, 'GetMessageW', c.c_int, c.POINTER(MSG), HANDLE, c.c_uint, c.c_uint)
            bind(u, 'UnhookWinEvent', BOOL, HANDLE)
            callback_type = c.WINFUNCTYPE(None, HANDLE, DWORD, HANDLE, c.c_int32,
                                         c.c_int32, DWORD, DWORD)
            bind(u, 'SetWinEventHook', HANDLE, DWORD, DWORD, HANDLE, callback_type,
                 DWORD, DWORD, DWORD)
            self._thread_id = k.GetCurrentThreadId()
            message = MSG()
            u.PeekMessageW(c.byref(message), None, 0, 0, 0)

            @callback_type
            def changed(_hook, event, hwnd, object_id, child_id, _thread, _time):
                if event == 0x800C and hwnd and object_id == 0 and child_id == 0:
                    self._pending.append((hwnd, time.monotonic()))

            # OUTOFCONTEXT | SKIPOWNPROCESS: no injection, own menu/title ignored.
            hook = u.SetWinEventHook(0x800C, 0x800C, None, changed, 0, 0, 2)
            if not hook:
                raise OSError('Windows browser event hook unavailable')
            self.active = True
            self._ready.set()
            while not self._cancel.is_set():
                if u.GetMessageW(c.byref(message), None, 0, 0) <= 0:
                    break
        except Exception as exc:
            self.last_error = str(exc)
        finally:
            if hook:
                u.UnhookWinEvent(hook)
            self.active = False
            self._ready.set()

    def _drain(self):
        if not self.active:
            self._source = None
            return False
        for _ in range(min(len(self._pending), 64)):
            hwnd, timestamp = self._pending.popleft()
            if self._callback:
                self._callback(hwnd, time.monotonic() - timestamp)
        return True
