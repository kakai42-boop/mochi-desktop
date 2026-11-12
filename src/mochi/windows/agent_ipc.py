"""Bounded, non-blocking local agent events via a random Windows mailslot.

Only an allow-listed event and a 16-character opaque token are accepted.
No pickle/deserialization of executable objects and no network listener.
"""
import ctypes as c
import json
import os
from pathlib import Path
import uuid

from mochi.agent_activity import AGENT_EVENTS, AGENT_TOKEN_PATTERN
from mochi.windows.native import BOOL, DWORD, HANDLE, bind


def endpoint_file():
    root = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local'))
    return root / 'mochi-desktop' / 'agent-endpoint.json'


def decode_event(data):
    if len(data) > 128:
        return None
    try:
        event, token = data.decode('ascii').split(':')
    except (ValueError, UnicodeError):
        return None
    if event not in AGENT_EVENTS or AGENT_TOKEN_PATTERN.fullmatch(token) is None:
        return None
    return event, token


def kernel():
    k = c.WinDLL('kernel32', use_last_error=True)
    bind(k, 'CreateMailslotW', HANDLE, c.c_wchar_p, DWORD, DWORD, c.c_void_p)
    bind(k, 'GetMailslotInfo', BOOL, HANDLE, c.POINTER(DWORD), c.POINTER(DWORD), c.POINTER(DWORD), c.POINTER(DWORD))
    bind(k, 'ReadFile', BOOL, HANDLE, c.c_void_p, DWORD, c.POINTER(DWORD), c.c_void_p)
    bind(k, 'CreateFileW', HANDLE, c.c_wchar_p, DWORD, DWORD, c.c_void_p, DWORD, DWORD, HANDLE)
    bind(k, 'WriteFile', BOOL, HANDLE, c.c_void_p, DWORD, c.POINTER(DWORD), c.c_void_p)
    bind(k, 'CloseHandle', BOOL, HANDLE)
    return k


class AgentReceiver:
    def __init__(self, callback):
        self.callback = callback
        self.handle = None
        self.source = None
        self.name = r'\\.\mailslot\mochi-' + uuid.uuid4().hex

    def start(self):
        from gi.repository import GLib
        self.k = kernel()
        self.handle = self.k.CreateMailslotW(self.name, 128, 0, None)
        if self.handle in (None, c.c_void_p(-1).value):
            self.handle = None
            return False
        path = endpoint_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps({'name': self.name}), encoding='utf-8')
        temporary.replace(path)
        self.source = GLib.timeout_add(100, self._poll)
        return True

    def _poll(self):
        for _ in range(32):
            size, count = DWORD(), DWORD()
            if not self.k.GetMailslotInfo(self.handle, None, c.byref(size), c.byref(count), None) or not count.value:
                break
            data = c.create_string_buffer(128)
            read = DWORD()
            if not self.k.ReadFile(self.handle, data, 128, c.byref(read), None):
                break
            event = decode_event(data.raw[:read.value])
            if event is not None:
                self.callback(*event)
        return True

    def stop(self):
        if self.source is not None:
            from gi.repository import GLib
            GLib.source_remove(self.source)
            self.source = None
        if self.handle is not None:
            self.k.CloseHandle(self.handle)
            self.handle = None
        path = endpoint_file()
        try:
            if json.loads(path.read_text(encoding='utf-8')).get('name') == self.name:
                path.unlink()
        except (OSError, ValueError):
            pass


def send_event(event, token):
    payload = f'{event}:{token}'.encode('ascii')
    if decode_event(payload) is None:
        return
    path = endpoint_file()
    if path.stat().st_size > 1024:
        return
    name = json.loads(path.read_text(encoding='utf-8')).get('name', '')
    prefix = r'\\.\mailslot\mochi-'
    if not isinstance(name, str) or not name.startswith(prefix) or len(name) != len(prefix) + 32:
        return
    if any(ch not in '0123456789abcdef' for ch in name[len(prefix):]):
        return
    k = kernel()
    handle = k.CreateFileW(name, 0x40000000, 1, None, 3, 0x80, None)
    if handle in (None, c.c_void_p(-1).value):
        return
    try:
        written = DWORD()
        k.WriteFile(handle, payload, len(payload), c.byref(written), None)
    finally:
        k.CloseHandle(handle)


def read_windows_payload(stream, deadline_seconds, maximum):
    """Windows selectors do not support pipes; PeekNamedPipe bounds stdin waits."""
    import msvcrt
    import time
    k = kernel()
    bind(k, 'GetFileType', DWORD, HANDLE)
    bind(k, 'PeekNamedPipe', BOOL, HANDLE, c.c_void_p, DWORD, c.POINTER(DWORD), c.POINTER(DWORD), c.POINTER(DWORD))
    if stream is None or stream.isatty():
        return b''
    fd = stream.fileno()
    handle = msvcrt.get_osfhandle(fd)
    if k.GetFileType(handle) == 1:  # regular file, a bounded read cannot wait on input
        return os.read(fd, maximum)
    chunks = []
    total = 0
    deadline = time.monotonic() + deadline_seconds
    while total < maximum and time.monotonic() < deadline:
        available = DWORD()
        if not k.PeekNamedPipe(handle, None, 0, None, c.byref(available), None):
            break
        if not available.value:
            time.sleep(0.01)
            continue
        data = os.read(fd, min(available.value, 65536, maximum - total))
        if not data:
            break
        chunks.append(data)
        total += len(data)
    return b''.join(chunks)
