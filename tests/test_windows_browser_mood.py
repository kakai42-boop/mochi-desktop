import base64
import hashlib
import io
import json
from pathlib import Path

from mochi.windows import browser_mood_transport as transport
from mochi.windows.browser_mood import BrowserMood


def ready():
    mood = BrowserMood(interval=3)
    for now in range(4):
        mood.sample(now, (12, 'chrome'))
    return mood


def test_countdown_requires_one_use_token_and_ten_seconds():
    mood = ready()
    offer = mood.request(3, {'op': 'arm', 'browser': 'chrome'})
    token = offer['token']
    assert mood.request(12.9, {'op': 'finish', 'token': token}) == {}
    assert mood.request(13, {'op': 'finish', 'token': token}) == {'close': True}
    assert mood.request(13, {'op': 'finish', 'token': token}) == {}


def test_needs_matching_foreground_browser():
    mood = ready()
    assert mood.request(3, {'op': 'arm', 'browser': 'edge'}) == {}
    assert mood.request(3, {'op': 'arm', 'browser': 'chrome'})['token']


def test_focus_change_idle_and_attention_invalidate_countdown():
    for foreground in (None, (13, 'chrome'), (12, 'edge')):
        mood = ready()
        token = mood.request(3, {'op': 'arm', 'browser': 'chrome'})['token']
        mood.sample(4, foreground)
        mood.sample(13, (12, 'chrome'))
        assert mood.request(13, {'op': 'finish', 'token': token}) == {}
    mood = ready()
    token = mood.request(3, {'op': 'arm', 'browser': 'chrome'})['token']
    mood.reset()
    assert mood.request(13, {'op': 'finish', 'token': token}) == {}


def test_stale_countdown_and_suspend_gap_cannot_grant_close():
    mood = ready()
    token = mood.request(3, {'op': 'arm', 'browser': 'chrome'})['token']
    assert mood.request(17, {'op': 'finish', 'token': token}) == {}
    mood = BrowserMood(interval=3)
    mood.sample(1, (12, 'chrome'))
    mood.sample(100, (12, 'chrome'))
    assert mood.request(100, {'op': 'arm', 'browser': 'chrome'}) == {}


def test_suspend_cancels_an_armed_countdown_even_within_the_grace_window():
    mood = ready()
    token = mood.request(3, {'op': 'arm', 'browser': 'chrome'})['token']
    mood.sample(13, (12, 'chrome'))
    assert mood.request(13, {'op': 'finish', 'token': token}) == {}


def test_native_host_allowlist_matches_the_packaged_extension():
    manifest = Path(transport.__file__).with_name('browser_extension') / 'manifest.json'
    config = json.loads(manifest.read_text(encoding='utf-8'))
    digest = hashlib.sha256(base64.b64decode(config['key'])).hexdigest()[:32]
    extension_id = ''.join('abcdefghijklmnop'[int(char, 16)] for char in digest)
    assert transport.ORIGIN == f'chrome-extension://{extension_id}/'
    assert 'host_permissions' not in config
    assert 'tabs' not in config['permissions']
    assert config['incognito'] == 'not_allowed'


def test_native_message_framing_is_bounded():
    stream = io.BytesIO()
    transport.write_message(stream, {'op': 'status'})
    stream.seek(0)
    assert transport.read_message(stream) == {'op': 'status'}
    invalid = (transport.MAX_MESSAGE + 1).to_bytes(4, 'little') + b'{}'
    assert transport.read_message(io.BytesIO(invalid)) is None
    assert transport.read_message(io.BytesIO(b'\x04\x00\x00\x00{}')) is None
