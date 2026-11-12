"""Per-user native messaging bridge for the allowlisted browser extension."""

import json
import logging
from multiprocessing.connection import Client, Listener
import os
from pathlib import Path
from secrets import compare_digest, token_hex
import struct
import sys
import threading


HOST = 'com.mochidesktop.browser_mood'
ORIGIN = 'chrome-extension://kganbpeoodlcjbgcdieagaiihdckfene/'
REGISTRY_PATHS = (
    r'Software\Google\Chrome\NativeMessagingHosts',
    r'Software\Microsoft\Edge\NativeMessagingHosts',
)
MAX_MESSAGE = 2048


def data_folder():
    return Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local')) / 'mochi-desktop'


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value), encoding='utf-8')
    temporary.replace(path)


def register_host():
    import winreg

    manifest = data_folder() / 'browser-mood-host.json'
    write_json(manifest, {
        'name': HOST,
        'description': 'Mochi desktop browser mood bridge',
        'path': str(Path(__file__).resolve().parents[3] / 'Mochi.exe'),
        'type': 'stdio',
        'allowed_origins': [ORIGIN],
    })
    for path in REGISTRY_PATHS:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, path + '\\' + HOST) as key:
            winreg.SetValueEx(key, '', 0, winreg.REG_SZ, str(manifest))


def unregister_host():
    import winreg

    for path in REGISTRY_PATHS:
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path + '\\' + HOST)
        except FileNotFoundError:
            pass
    (data_folder() / 'browser-mood-host.json').unlink(missing_ok=True)


class MoodBridge:
    def __init__(self, scheduler, dispatch):
        self.scheduler = scheduler
        self.dispatch = dispatch
        self.secret = token_hex(32)
        self.address = r'\\.\pipe\mochi-browser-mood-' + token_hex(16)
        self.endpoint = data_folder() / 'browser-mood-endpoint.json'
        self.stopped = threading.Event()
        self.listener = Listener(self.address, family='AF_PIPE')
        try:
            write_json(self.endpoint, {'address': self.address, 'secret': self.secret})
        except OSError:
            self.listener.close()
            raise
        self.thread = threading.Thread(target=self._serve, name='mochi-browser-mood', daemon=True)
        self.thread.start()

    def _serve(self):
        while not self.stopped.is_set():
            try:
                with self.listener.accept() as client:
                    if self.stopped.is_set() or not client.poll(1):
                        continue
                    message = json.loads(client.recv_bytes(MAX_MESSAGE))
                    if not isinstance(message, dict):
                        continue
                    secret = message.pop('secret', '')
                    if not isinstance(secret, str) or not compare_digest(self.secret, secret):
                        continue
                    result = {}
                    ready = threading.Event()

                    def respond(message=message, result=result, ready=ready):
                        try:
                            if not (ready.is_set() or self.stopped.is_set()):
                                result.update(self.dispatch(message))
                        finally:
                            ready.set()
                        return False

                    self.scheduler.idle_add(respond)
                    if ready.wait(1.5):
                        client.send_bytes(json.dumps(result).encode('utf-8'))
                    else:
                        ready.set()
            except (OSError, EOFError, ValueError):
                if not self.stopped.is_set():
                    logging.getLogger(__name__).debug('Browser mood bridge request ended')

    def close(self):
        self.stopped.set()
        try:
            self.endpoint.unlink(missing_ok=True)
        except OSError:
            logging.getLogger(__name__).debug('Could not remove browser mood endpoint')
        # Wake a blocked Accept on the private pipe before closing its handles.
        try:
            with Client(self.address, family='AF_PIPE'):
                pass
        except OSError:
            pass
        self.listener.close()


def read_message(stream):
    header = stream.read(4)
    if len(header) != 4:
        return None
    size = struct.unpack('<I', header)[0]
    if not 0 < size <= MAX_MESSAGE:
        return None
    payload = stream.read(size)
    if len(payload) != size:
        return None
    value = json.loads(payload)
    return value if isinstance(value, dict) else None


def write_message(stream, message):
    payload = json.dumps(message).encode('utf-8')
    stream.write(struct.pack('<I', len(payload)))
    stream.write(payload)
    stream.flush()


def host_main(origin):
    if origin != ORIGIN:
        return 1
    result = {}
    try:
        message = read_message(sys.stdin.buffer)
        if message is not None:
            endpoint = json.loads((data_folder() / 'browser-mood-endpoint.json').read_text(encoding='utf-8'))
            message['secret'] = endpoint['secret']
            with Client(endpoint['address'], family='AF_PIPE') as client:
                client.send_bytes(json.dumps(message).encode('utf-8'))
                if client.poll(2):
                    result = json.loads(client.recv_bytes(MAX_MESSAGE))
    except (OSError, EOFError, KeyError, TypeError, ValueError):
        pass
    write_message(sys.stdout.buffer, result)
    return 0
