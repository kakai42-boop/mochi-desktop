"""Private bootstrap for the self-contained Windows build."""
import ctypes
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import traceback

ROOT = Path(__file__).resolve().parent
RUNTIME = ROOT / 'runtime'
DATA = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local')) / 'mochi-desktop'
DLL_HANDLES = []


def configure():
    DATA.mkdir(parents=True, exist_ok=True)
    # Isolated Python (-I) ignores inherited PYTHONPATH/PYTHONHOME and user packages.
    sys.path.insert(0, str(ROOT / 'src'))
    os.environ['PATH'] = str(RUNTIME / 'bin') + os.pathsep + os.environ.get('PATH', '')
    os.environ['PYGI_DLL_PATH'] = str(RUNTIME / 'bin')
    os.environ['GI_TYPELIB_PATH'] = str(RUNTIME / 'lib/girepository-1.0')
    os.environ['GSETTINGS_SCHEMA_DIR'] = str(RUNTIME / 'share/glib-2.0/schemas')
    os.environ['XDG_DATA_DIRS'] = str(RUNTIME / 'share')
    os.environ['GTK_DATA_PREFIX'] = str(RUNTIME)
    os.environ['GTK_EXE_PREFIX'] = str(RUNTIME)
    os.environ['GST_PLUGIN_PATH'] = str(RUNTIME / 'lib/gstreamer-1.0')
    os.environ['GST_PLUGIN_SYSTEM_PATH'] = str(RUNTIME / 'lib/gstreamer-1.0')
    os.environ['GST_PLUGIN_SCANNER'] = str(RUNTIME / 'libexec/gstreamer-1.0/gst-plugin-scanner.exe')
    os.environ['GST_REGISTRY'] = str(DATA / 'gstreamer-registry.bin')
    os.environ['GDK_BACKEND'] = 'win32'
    DLL_HANDLES.append(os.add_dll_directory(str(RUNTIME / 'bin')))
    logger = logging.getLogger()
    handler = RotatingFileHandler(DATA / 'mochi.log', maxBytes=2_000_000, backupCount=2, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG if '--debug' in sys.argv else logging.INFO)
    # pythonw has no stderr; faulthandler and uncaught tracebacks need a real sink.
    sys.stderr = open(DATA / 'startup.log', 'w', encoding='utf-8', buffering=1)
    sys.stdout = sys.stderr
    schemas = RUNTIME / 'share/glib-2.0/schemas'
    if not (schemas / 'gschemas.compiled').exists():
        subprocess.run([str(RUNTIME / 'bin/glib-compile-schemas.exe'), str(schemas)],
                       check=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
    loaders = RUNTIME / 'lib/gdk-pixbuf-2.0/2.10.0/loaders'
    os.environ['GDK_PIXBUF_MODULEDIR'] = str(loaders)
    os.environ['GDK_PIXBUF_MODULE_FILE'] = str(DATA / 'loaders.cache')
    query = RUNTIME / 'bin/gdk-pixbuf-query-loaders.exe'
    if query.exists():
        with open(DATA / 'loaders.cache', 'wb') as cache:
            subprocess.run([str(query)], stdout=cache, stderr=subprocess.DEVNULL,
                           check=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)


def smoke_test():
    import gi
    gi.require_version('Gtk', '4.0')
    gi.require_version('Gst', '1.0')
    from gi.repository import GLib, Gst
    from mochi.app import MochiApplication
    from mochi.config import ConfigStore
    from mochi.windows.windowing import handle, get_window_position
    from mochi.windows.native import desktop
    Gst.init(None)
    for element in ('playbin', 'audioconvert', 'vorbisdec', 'wavparse', 'autoaudiosink'):
        if Gst.ElementFactory.find(element) is None:
            raise RuntimeError('Missing audio element: ' + element)
    with tempfile.TemporaryDirectory(prefix='mochi-smoke-') as temporary:
        application = MochiApplication(ConfigStore(Path(temporary) / 'config.json'), preview_animations=True)
        results = {
            'run_id': os.environ.get('MOCHI_SMOKE_RUN_ID', ''),
            'package_root': str(ROOT),
            'platform': sys.platform,
        }

        def inspect():
            try:
                window = application.get_active_window()
                hwnd = handle(window)
                if not hwnd or get_window_position(window) is None:
                    raise RuntimeError('No native Windows surface')
                if desktop().work_area(0, 0) is None:
                    raise RuntimeError('No Windows monitor work area')
                results['native_surface'] = True
                results['audio_plugins'] = True
            except Exception:
                results['error'] = traceback.format_exc()
            finally:
                application.quit()
            return False

        application.connect('activate', lambda app: GLib.timeout_add(2000, inspect))
        application.run(['Mochi'])
        (DATA / 'smoke-test.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
        return 0 if results.get('native_surface') else 1


def main():
    try:
        if '--agent-signal' in sys.argv:
            sys.path.insert(0, str(ROOT / 'src'))
            from mochi.agent_signal import main as agent_main
            return agent_main(sys.argv[sys.argv.index('--agent-signal') + 1:])
        if '--smoke-test' in sys.argv:
            # Never leave an old success report behind after startup failure.
            (DATA / 'smoke-test.json').unlink(missing_ok=True)
        configure()
        if '--smoke-test' in sys.argv:
            return smoke_test()
        from mochi.main import main as mochi_main
        return mochi_main(sys.argv[1:])
    except Exception:
        logging.exception('Mochi startup failed')
        if '--agent-signal' not in sys.argv and '--smoke-test' not in sys.argv:
            ctypes.windll.user32.MessageBoxW(None, f'Mochi ne peut pas démarrer.\nJournal : {DATA / "mochi.log"}', 'Mochi', 0x10)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
