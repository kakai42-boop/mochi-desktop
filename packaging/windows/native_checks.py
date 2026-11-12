"""Normal-mode Windows GUI qualification, using an isolated configuration.

Tests real windows and lifecycle. Does not claim physical mouse/audio/DPI QA.
"""
import base64
import ctypes as c
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import tempfile
import traceback
from types import SimpleNamespace


class MouseInput(c.Structure):
    _fields_ = [('dx', c.c_int32), ('dy', c.c_int32), ('data', c.c_uint32),
                ('flags', c.c_uint32), ('time', c.c_uint32), ('extra', c.c_size_t)]


class KeyboardInput(c.Structure):
    _fields_ = [('key', c.c_ushort), ('scan', c.c_ushort), ('flags', c.c_uint32),
                ('time', c.c_uint32), ('extra', c.c_size_t)]


class InputData(c.Union):
    _fields_ = [('mouse', MouseInput), ('keyboard', KeyboardInput)]


class Input(c.Structure):
    _fields_ = [('kind', c.c_uint32), ('data', InputData)]


class TestInput:
    def __init__(self, user32):
        self.send = user32.SendInput
        self.send.argtypes = [c.c_uint, c.POINTER(Input), c.c_int]
        self.send.restype = c.c_uint
        self.move = user32.SetCursorPos
        self.move.argtypes = [c.c_int, c.c_int]
        self.move.restype = c.c_int

    def buttons(self, *flags):
        self._send([Input(0, InputData(mouse=MouseInput(flags=flag))) for flag in flags])

    def shortcut(self, *keys):
        pressed = [Input(1, InputData(keyboard=KeyboardInput(key=key))) for key in keys]
        released = [Input(1, InputData(keyboard=KeyboardInput(key=key, flags=2))) for key in reversed(keys)]
        self._send(pressed + released)

    def _send(self, inputs):
        events = (Input * len(inputs))(*inputs)
        if self.send(len(events), events, c.sizeof(Input)) != len(events):
            raise OSError('Windows rejected the test input')


def check_windows_media_flags():
    from mochi.windows.media import PLAYBACK_FLAGS_SCRIPT

    fixtures = r'''
$ErrorActionPreference = 'Stop'
function New-MediaSession($source, $status, $type) {
    $session = [pscustomobject]@{
        SourceAppUserModelId = $source
        Info = [pscustomobject]@{PlaybackStatus = $status; PlaybackType = $type}
    }
    $session | Add-Member ScriptMethod GetPlaybackInfo { $this.Info }
    return $session
}
$spotify = New-MediaSession 'Spotify.exe' 'Playing' $null
$store = New-MediaSession 'SpotifyAB.SpotifyMusic_zpdnekdrzrea0!Spotify' 'Playing' 'Unknown'
$paused = New-MediaSession 'Spotify.exe' 'Paused' $null
$stopped = New-MediaSession 'Spotify.exe' 'Stopped' 'Music'
$browser = New-MediaSession 'Chrome' 'Playing' $null
$other = New-MediaSession 'OtherSpotify.exe' 'Playing' $null
$video = New-MediaSession 'Chrome' 'Playing' 'Video'
$spotifyVideo = New-MediaSession 'Spotify.exe' 'Playing' 'Video'
$music = New-MediaSession 'Music Player' 'Playing' 'Music'
Get-MochiPlaybackFlags @($spotify)
Get-MochiPlaybackFlags @($store)
Get-MochiPlaybackFlags @($paused, $stopped, $browser, $other)
Get-MochiPlaybackFlags @($spotify, $video)
Get-MochiPlaybackFlags @($spotifyVideo)
Get-MochiPlaybackFlags @($music)
'''
    powershell = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    encoded = base64.b64encode((PLAYBACK_FLAGS_SCRIPT + fixtures).encode('utf-16-le')).decode('ascii')
    output = subprocess.run(
        [str(powershell), '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded],
        capture_output=True, text=True, check=True, timeout=15,
        creationflags=subprocess.CREATE_NO_WINDOW,
    ).stdout.splitlines()
    assert output == ['1,0', '1,0', '0,0', '1,1', '0,1', '1,0'], output


def run(data):
    import gi
    gi.require_version('Gtk', '4.0')
    from gi.repository import Gdk, Gio, GLib
    from mochi.app import MochiApplication
    from mochi.config import ConfigStore
    from mochi.focus import FocusPlan
    from mochi.pocket import PocketItemKind
    from mochi.pocket_store import PocketStore
    from mochi.state import MochiState
    from mochi.windows.browser_mood_transport import ORIGIN, read_message, write_message
    from mochi.windows.native import desktop, RECT
    from mochi.windows.windowing import handle

    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('Mouse qualification requires a disposable GitHub Actions desktop')
    mouse = TestInput(desktop().user32)

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
                assert area[1] <= rect.top < rect.bottom <= area[3], (
                    f'Menu overlaps the taskbar or monitor edge: {rect.top}:{rect.bottom} outside {area}'
                )
                menu.popdown()
                result['checks'].append('native_edge_menu_work_area')
                exercise_offscreen_recovery(hwnd=handle(buddy._window))

            later(600, positioned)

        def exercise_offscreen_recovery(hwnd):
            api = desktop()
            assert api.move(hwnd, -20000, -20000), 'Could not move the test window off-screen'
            assert not api.monitor_for_window(hwnd), 'Fixture still overlaps a monitor'

            def recovered():
                assert api.monitor_for_window(hwnd), 'Mochi remained outside all monitors'
                result['checks'].append('native_offscreen_recovery')
                exercise_agent()

            later(1650, recovered)

        def exercise_agent():
            exe = Path(__file__).with_name('Mochi.exe')
            payload = json.dumps({'session_id': 'windows-qa', 'prompt': 'fixture only'}).encode()

            def send(event):
                command = subprocess.run(
                    [str(exe), '--agent-signal', event, '--source', 'codex'], input=payload,
                    capture_output=True, check=True, timeout=8,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                assert command.stdout == command.stderr == b'', 'Agent hook wrote output'

            def stopped():
                assert not buddy._agent_tracker.working, 'Agent session did not end'
                result['checks'].append('native_agent_lifecycle')
                exercise_pocket()

            def working():
                assert buddy._agent_tracker and buddy._agent_tracker.working, 'Agent event did not arrive'
                send('ended')
                later(350, stopped)

            send('working')
            later(350, working)

        def exercise_pocket():
            folder = data / 'QA dossier été & projets'
            folder.mkdir(exist_ok=True)
            sample = folder / 'note témoin.txt'
            sample.write_text('Pocket smoke test', encoding='utf-8')
            files, text, image = buddy._pocket_drop.targets
            texture = Gdk.MemoryTexture.new(
                1, 1, Gdk.MemoryFormat.R8G8B8A8, GLib.Bytes.new(bytes((90, 210, 120, 255))), 4,
            )
            inputs = [
                (files, Gdk.FileList.new_from_list([Gio.File.new_for_path(str(sample))])),
                (text, 'Une note témoin'), (text, 'https://example.com/qa'), (image, texture),
            ]
            controller = buddy._pocket_controller

            def finish():
                stored = {item.kind: item for item in PocketStore().load()}
                assert set(stored) == set(PocketItemKind), 'A Pocket payload was not persisted'
                assert Path(stored[PocketItemKind.SAVED_IMAGE].value).is_file()
                buddy._show_pocket_window()
                pocket = buddy._pocket_window
                assert pocket.open_item(stored[PocketItemKind.TEXT].id)
                detail = pocket.detail_windows[-1]
                buf = detail.text_view.get_buffer()
                assert buf.get_text(*buf.get_bounds(), True) == 'Une note témoin'
                detail.close()
                assert pocket.open_containing_folder(stored[PocketItemKind.LOCAL_FILE].id)
                assert pocket.remove_item(stored[PocketItemKind.SAVED_IMAGE].id)
                assert sample.is_file(), 'Pocket changed the original file'
                pocket.hide()
                result['checks'].append('pocket_shell_folder')
                result['checks'].append('pocket_payloads_and_persistence')
                app.quit()

            def drop_next(retries=30):
                if not inputs:
                    finish()
                elif controller.can_receive():
                    target, value = inputs.pop(0)
                    assert target.emit('drop', value, 1.0, 1.0), 'Pocket rejected its registered drop type'
                    later(350, drop_next)
                else:
                    assert retries > 0, 'Pocket did not become ready for another drop'
                    later(200, lambda: drop_next(retries - 1))

            drop_next()

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

        def exercise_mood_bridge():
            import io
            from mochi.windows.browser_mood import Countdown

            app.set_browser_mood(True, 1)
            assert config.load_browser_mood() == (True, 1)
            controller = app._windows_mood
            foreground = desktop().user32.GetForegroundWindow()
            assert foreground, 'No foreground window for passive warning test'
            now = time.monotonic()
            controller.mood.countdown = Countdown('test', (foreground, 'chrome'), now + 10)
            controller._show_warning(now)
            assert controller.warning.get_mapped(), 'Countdown did not map'
            assert desktop().user32.GetForegroundWindow() == foreground, 'Countdown took focus'
            controller.reset()
            assert not controller.warning.get_visible(), 'Countdown did not hide'
            result['checks'].append('browser_mood_passive_countdown')

            def request(expected, complete):
                def run_host():
                    error = None
                    try:
                        payload = io.BytesIO()
                        write_message(payload, {'op': 'status'})
                        exe = Path(__file__).with_name('Mochi.exe')
                        host = subprocess.run(
                            [str(exe), ORIGIN, '--parent-window=0'], input=payload.getvalue(),
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
                            timeout=8, creationflags=subprocess.CREATE_NO_WINDOW,
                        )
                        response = read_message(io.BytesIO(host.stdout))
                        assert response == expected, f'Unexpected mood host response: {response}'
                    except Exception:
                        error = traceback.format_exc()

                    def on_complete():
                        if error:
                            result['errors'].append(error)
                            app.quit()
                        else:
                            try:
                                complete()
                            except Exception:
                                return fail()
                        return False

                    GLib.idle_add(on_complete)

                threading.Thread(target=run_host, daemon=True).start()

            def disabled():
                result['checks'].append('browser_mood_host_roundtrip')
                later(750, begin_clicks)

            def connected():
                app.set_browser_mood(False, 1)
                assert config.load_browser_mood() == (False, 1)
                request({}, disabled)

            request({'connected': True}, connected)

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
                    exercise_mood_bridge()
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
                gear = buddy._context_menu_rows['header'].get_last_child()
                assert gear.get_tooltip_text() == 'Windows settings'
                result['menu_rows'] = list(buddy._context_menu_row_order)
                result['virtual_desktop_manager_available'] = app._windows_desktop_follower.manager is not None
                assert buddy._typing_monitor.available, 'Typing hook not active'
                assert buddy._developer_shortcut_monitor.available, 'Developer shortcut not active'
                assert buddy._app_category_monitor._tab_backend.active, 'Browser hook not active'
                assert app._windows_agent_receiver is not None
                result['checks'].append('normal_mode_backends')
                check_windows_media_flags()
                result['checks'].append('windows_media_playback_flags')
                for name, show, obj in [
                    ('context_menu', right_click, lambda: buddy._context_menu),
                    ('developer_menu_hotkey', lambda: mouse.shortcut(0x11, 0x12, 0x10, ord('M')),
                     lambda: buddy._developer_menu),
                    ('focus_window', buddy._show_focus_window, lambda: buddy._focus_window),
                    ('quick_start', buddy._show_quick_start, lambda: buddy._quick_start_window),
                    ('emote_catalogue_hotkey', lambda: mouse.shortcut(0x11, 0x12, ord('E')),
                     lambda: buddy._emote_catalogue_window),
                ]:
                    steps.append((name, show, lambda obj=obj: obj().window,
                                  lambda obj=obj: obj().popdown() if hasattr(obj(), 'popdown') else obj().window.hide()))
                steps.append(('pocket_window', buddy._show_pocket_window,
                              lambda: buddy._pocket_window, lambda: buddy._pocket_window.hide()))
                settings = None

                def show_settings():
                    nonlocal settings
                    settings = app.show_windows_settings()

                steps.append(('windows_settings', show_settings, lambda: settings,
                              lambda: settings.close()))
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
            result['passed'] = not result['errors'] and len(result['checks']) == 23
            report.write_text(json.dumps(result, indent=2), encoding='utf-8')
    return 0 if result['passed'] else 1
