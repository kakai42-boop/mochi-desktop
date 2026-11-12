import ctypes
from types import SimpleNamespace

import pytest

from mochi.windows.windowing import native_surface_handle


def test_capsule_bridge_preserves_64_bit_gobject_and_hwnd():
    create = ctypes.pythonapi.PyCapsule_New
    create.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_void_p]
    create.restype = ctypes.py_object
    pointer = 0x123456789AB
    capsule = create(pointer, None, None)
    received = []

    def native_call(value):
        received.append(value)
        return 0x23456789ABC

    surface = SimpleNamespace(__gpointer__=capsule)
    assert native_surface_handle(surface, native_call) == 0x23456789ABC
    assert received == [pointer]


def test_invalid_capsule_never_reaches_native_function():
    def must_not_call(pointer):
        pytest.fail('Invalid pointer reached GTK')

    with pytest.raises(ValueError):
        native_surface_handle(SimpleNamespace(__gpointer__=object()), must_not_call)
