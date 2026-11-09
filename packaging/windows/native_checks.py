"""Normal-mode Windows GUI qualification, using an isolated configuration.

Tests real windows and lifecycle. Does not claim physical mouse/audio/DPI QA.
"""
import ctypes as c
import json
import os
from pathlib import Path
import sys
import tempfile
import traceback
from types import SimpleNamespace


class MouseInput(c.Structure):
    _fields_ = [('dx', c.c_int32), ('dy', c.c_int32), ('data', c.c_uint32),
                ('flags', c.c_uint32), ('time', c.c_uint32), ('extra', c.c_size_t)]


class Input(c.Structure):
    # MouseInput is the largest member of the Win32 INPUT union.
    _fields_ = [('kind', c.c_uint32), ('mouse', MouseInput)]


class TestMouse:
    def __init__(self, user32):
        self.send = user32.SendInput
        self.send.argtypes = [c.c_uint, c.POINTER(Input), c.c_int]
        self.send.restype = c.c_uint
        self.move = user32.SetCursorPos
        self.move.argtypes = [c.c_int, c.c_int]
        self.move.restype = c.c_int

    def buttons(self, *flags):
        events = (Input * len(flags))(*(Input(0, MouseInput(flags=flag)) for flag in flags))
        if self.send(len(events), events, c.sizeof(Input)) != len(events):
            raise OSError('Windows rejected the test mouse input')


def run(data):
    import gi
    gi.require_version('Gtk', '4.0')
    from gi.repository import GLib
    from mochi.app import MochiApplication
    from mochi.config import ConfigStore
    from mochi.focus import FocusPlan
    from mochi.pocket import make_local_file_item
    from mochi.pocket_window import PocketWindow
    from mochi.state import MochiState
    from mochi.windows.native import desktop, RECT
    from mochi.windows.windowing import handle

    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('Mouse qualification requires a disposable GitHub Actions desktop')
    mouse = TestMouse(desktop().user32)

    result = {'run_id': os.environ.get('MOCHI_SMOKE_RUN_ID', ''), 'checks': [], 'errors': []}
    report = data / 'integration-test.json'
    report.unlink(missing_ok=True)
    old_hook = sys.excepthook

    def record_error(kind, error, tb):
        result['errors'].append(''.join(traceback.format_exception(kind, error, tb)))
        old_hook(kind, error, tb)

    sys.excepthook = record_error
    with tempfile.TemporaryDirectory(prefix='mochi-features-') as temporary:
        config = ConfigStore(Path(temporary) / 'config.json')
        config.save_stay_put(True)
        config.save_update_checks_enabled(False)
        config.save_muted(True)  # Audio-device QA is a separate test.
        app = MochiApplication(config, preview_animations=False)
        steps = []
        buddy = None
        dragging = False

        def fail():
            result['errors'].append(traceback.format_exc())
            try:
                if dragging:
                    mouse.buttons(0x0004)  # LEFTUP after a failed assertion
            finally:
                app.quit()
            return False

        def later(delay, callback):
            def invoke():
                try:
                    callback()
                except Exception:
                    return fail()
                return False
            GLib.timeout_add(delay, invoke)

        def point_at_buddy():
            rect = RECT()
            assert desktop().user32.GetWindowRect(handle(buddy._window), c.byref(rect))
            point = ((rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2)
            assert mouse.move(*point), 'Could not move the cursor onto Mochi'
            return point

        def right_click():
            point_at_buddy()
            mouse.buttons(0x0008, 0x0010)  # RIGHTDOWN, RIGHTUP

        def begin_clicks():
            point_at_buddy()
            prior = buddy._recent_click_reactions
            mouse.buttons(0x0002, 0x0004)  # LEFTDOWN, LEFTUP

            def single_complete():
                assert buddy._recent_click_reactions != prior, 'Left click did not start a reaction'
                result['checks'].append('left_click')
                later(900, double_click)

            later(200, single_complete)

        def double_click():
            point_at_buddy()
            mouse.buttons(0x0002, 0x0004)

            def second_click():
                mouse.buttons(0x0002, 0x0004)
                later(150, double_complete)

            later(100, second_click)

        def double_complete():
            assert buddy.state.current is MochiState.HEART, (
                f'Double-click ended in {buddy.state.current.name}/{buddy._current_animation}'
            )
            result['checks'].append('double_click_heart')
            later(900, begin_drag)

        def begin_drag():
            nonlocal dragging
            hwnd = handle(buddy._window)
            origin = desktop().position(hwnd)
            assert origin is not None
            x, y = point_at_buddy()
            mouse.buttons(0x0002)
            dragging = True

            def move():
                assert mouse.move(x + 64, y + 40), 'Could not move the drag cursor'
                later(250, release)

            def release():
                nonlocal dragging
                position = desktop().position(hwnd)
                assert position != origin, 'Dragging did not move the native window'
                mouse.buttons(0x0004)
                dragging = False
                later(200, drag_complete)

            later(100, move)

        def drag_complete():
            assert not buddy._drag_started, 'Mochi stayed held after release'
            result['checks'].append('drag_and_release')
            exercise_resize()

        def exercise_resize():
            hwnd = handle(buddy._window)
            user32 = desktop().user32

            def client_size():
                rect = RECT()
                assert user32.GetClientRect(hwnd, c.byref(rect))
                return rect.right - rect.left, rect.bottom - rect.top

            def set_size(size):
                buddy._change_size(SimpleNamespace(get_value=lambda: size))

            before = client_size()
            set_size(ConfigStore.MAX_SIZE)

            def grown():
                largest = client_size()
                assert largest[0] > before[0] and largest[1] > before[1], (before, largest)
                set_size(ConfigStore.MIN_SIZE)

                def shrunk():
                    smallest = client_size()
                    assert smallest[0] < before[0] and smallest[1] < before[1], (before, largest, smallest)
                    assert config.load_size() == ConfigStore.MIN_SIZE
                    result['checks'].append('native_grow_and_shrink')
                    exercise_topmost(hwnd)

                later(450, shrunk)

            later(450, grown)

        def exercise_topmost(hwnd):
            user32 = desktop().user32
            foreground = user32.GetForegroundWindow()
            # Simulate the demotion a GTK re-presentation can cause.
            assert user32.SetWindowPos(hwnd, -2, 0, 0, 0, 0, 0x01 | 0x02 | 0x10)
            assert not user32.GetWindowLongPtrW(hwnd, -20) & 0x08

            def repaired():
                assert user32.GetWindowLongPtrW(hwnd, -20) & 0x08, 'Mochi stayed demoted'
                if foreground != hwnd:
                    assert user32.GetForegroundWindow() != hwnd, 'Overlay repair stole focus'
                result['checks'].append('native_topmost_recovery')
                exercise_edge_menu()

            later(1600, repaired)

        def exercise_edge_menu():
            user32 = desktop().user32
            x, y = desktop().position(handle(buddy._window))
            area = desktop().work_area(x, y)
            assert area is not None
            buddy._placement.move_to(area[2] - 65, area[3] - 65)
            right_click()

            def positioned():
                menu = buddy._context_menu
                rect = RECT()
                assert menu.get_visible() and user32.GetWindowRect(handle(menu.window), c.byref(rect))
                assert area[0] <= rect.left < rect.right <= area[2], 'Menu extends outside the monitor'
                assert area[1] <= rect.top < rect.bottom <= area[3], 'Menu overlaps the taskbar or monitor edge'
                menu.popdown()
                result['checks'].append('native_edge_menu_work_area')
                exercise_pocket_folder()

            later(600, positioned)

        def exercise_pocket_folder():
            folder = data / 'QA dossier été & projets'
            folder.mkdir(exist_ok=True)
            sample = folder / 'note témoin.txt'
            sample.write_text('Pocket smoke test', encoding='utf-8')
            item = make_local_file_item(sample)
            pocket = PocketWindow(SimpleNamespace(items=(item,)))
            try:
                assert pocket.open_containing_folder(item.id), 'Windows could not open the Pocket folder'
            finally:
                pocket.destroy()
            result['checks'].append('pocket_shell_folder')
            app.quit()

        def exercise_focus():
            buddy._start_focus_session(FocusPlan(focus_minutes=1, break_minutes=1, rounds=1))
            assert buddy._focus_session.active
            buddy._toggle_focus_pause()
            assert buddy._focus_session.paused
            buddy._toggle_focus_pause()
            assert not buddy._focus_session.paused
            buddy._cancel_focus_session()
            assert buddy._focus_session is None or not buddy._focus_session.active
            if buddy._focus_window:
                buddy._focus_window.window.hide()
            result['checks'].append('focus_session_controls')

        def inspect_window(name, get_window, close):
            try:
                window = get_window()
                assert window.get_visible() and handle(window), name + ' has no native surface'
                assert window.get_width() > 0 and window.get_height() > 0, (
                    f'{name}: GTK size {window.get_width()}x{window.get_height()}'
                )
                result['checks'].append(name)
                close()
                GLib.timeout_add(400, next_step)
            except Exception:
                return fail()
            return False

        def next_step():
            try:
                if not steps:
                    # Persist a menu preference through the actual menu handler.
                    before = config.load_stay_put()
                    buddy._toggle_stay_put(None)
                    assert config.load_stay_put() is not before
                    buddy._toggle_stay_put(None)
                    assert config.load_stay_put() is before
                    result['checks'].append('preference_roundtrip')
                    exercise_focus()
                    later(750, begin_clicks)
                    return False
                name, show, get_window, close = steps.pop(0)
                show()
                GLib.timeout_add(900, inspect_window, name, get_window, close)
            except Exception:
                return fail()
            return False

        def start():
            nonlocal buddy
            try:
                buddy = app._buddy
                assert buddy is not None, 'Normal-mode initialization failed'
                required = {'header', 'sleep', 'close', 'focus', 'feed', 'bond', 'pocket',
                            'status', 'stay-put', 'edge-roam', 'quick-start', 'update'}
                missing = required.difference(buddy._context_menu_rows)
                assert not missing, 'Missing Linux menu entries: ' + repr(missing)
                result['menu_rows'] = list(buddy._context_menu_row_order)
                result['virtual_desktop_manager_available'] = app._windows_desktop_follower.manager is not None
                assert buddy._typing_monitor.available, 'Typing hook not active'
                assert buddy._developer_shortcut_monitor.available, 'Developer shortcut not active'
                assert buddy._app_category_monitor._tab_backend.active, 'Browser hook not active'
                assert app._windows_agent_receiver is not None
                result['checks'].append('normal_mode_backends')
                for name, show, obj in [
                    ('context_menu', right_click, lambda: buddy._context_menu),
                    ('developer_menu', buddy._show_developer_menu, lambda: buddy._developer_menu),
                    ('focus_window', buddy._show_focus_window, lambda: buddy._focus_window),
                    ('quick_start', buddy._show_quick_start, lambda: buddy._quick_start_window),
                    ('emote_catalogue', buddy._show_emote_catalogue, lambda: buddy._emote_catalogue_window),
                ]:
                    steps.append((name, show, lambda obj=obj: obj().window,
                                  lambda obj=obj: obj().popdown() if hasattr(obj(), 'popdown') else obj().window.hide()))
                steps.append(('pocket_window', buddy._show_pocket_window,
                              lambda: buddy._pocket_window, lambda: buddy._pocket_window.hide()))
                next_step()
            except Exception:
                return fail()
            return False

        app.connect('activate', lambda *_: GLib.timeout_add(2500, start))
        try:
            app.run(['Mochi'])
        except Exception:
            result['errors'].append(traceback.format_exc())
        finally:
            sys.excepthook = old_hook
            result['passed'] = not result['errors'] and len(result['checks']) == 16
            report.write_text(json.dumps(result, indent=2), encoding='utf-8')
    return 0 if result['passed'] else 1
