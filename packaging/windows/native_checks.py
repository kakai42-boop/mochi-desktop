"""Normal-mode Windows GUI qualification, using an isolated configuration.

Tests real windows and lifecycle. Does not claim physical mouse/audio/DPI QA.
"""
import json
import os
from pathlib import Path
import sys
import tempfile
import traceback


def run(data):
    import gi
    gi.require_version('Gtk', '4.0')
    from gi.repository import GLib
    from mochi.app import MochiApplication
    from mochi.config import ConfigStore
    from mochi.windows.windowing import handle

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
        config.save_muted(True)  # Audio-device QA is a separate test.
        app = MochiApplication(config, preview_animations=False)
        steps = []
        buddy = None

        def fail():
            result['errors'].append(traceback.format_exc())
            app.quit()
            return False

        def inspect_window(name, get_window, close):
            try:
                window = get_window()
                assert window.get_visible() and handle(window), name + ' has no native surface'
                assert window.get_width() > 0 and window.get_height() > 0
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
                    app.quit()
                    return False
                name, show, get_window, close = steps.pop(0)
                show()
                GLib.timeout_add(600, inspect_window, name, get_window, close)
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
                assert buddy._typing_monitor.available, 'Typing hook not active'
                assert buddy._developer_shortcut_monitor.available, 'Developer shortcut not active'
                assert buddy._app_category_monitor._tab_backend.active, 'Browser hook not active'
                assert app._windows_agent_receiver is not None
                result['checks'].append('normal_mode_backends')
                for name, show, obj in [
                    ('context_menu', buddy._show_context_menu, lambda: buddy._context_menu),
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
            result['passed'] = not result['errors'] and len(result['checks']) == 8
            report.write_text(json.dumps(result, indent=2), encoding='utf-8')
    return 0 if result['passed'] else 1
