"""Observe Windows media playback without accessing media metadata.

One shared background Windows PowerShell process calls the built-in WinRT API.
It emits only two booleans (music/video). When a session omits its playback
type, the helper can recognize Spotify by its local app ID. It reads no
media metadata and does not emit or store the app ID.
"""
import base64
import os
from pathlib import Path
import subprocess
import threading
import time

PLAYBACK_FLAGS_SCRIPT = r'''
function Get-MochiPlaybackFlags($sessions) {
    $music = 0; $video = 0
    foreach ($session in $sessions) {
        try {
            $info = $session.GetPlaybackInfo()
            if ([string]$info.PlaybackStatus -ne 'Playing') { continue }
            $type = [string]$info.PlaybackType
            if ($type -eq 'Video') {
                $video = 1
            } elseif ($type -eq 'Music') {
                $music = 1
            } elseif ($type -in @('', 'Unknown') -and
                      $session.SourceAppUserModelId -match '^(Spotify|SpotifyAB\.SpotifyMusic_zpdnekdrzrea0(![^!]+)?)$|(^|[\\/])Spotify\.exe$') {
                $music = 1
            }
        } catch { }
    }
    return "$music,$video"
}
'''

SCRIPT = PLAYBACK_FLAGS_SCRIPT + r'''
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$managerType = [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager, Windows.Media.Control, ContentType=WindowsRuntime]
$asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
} | Select-Object -First 1
$task = $asTask.MakeGenericMethod($managerType).Invoke($null, @($managerType::RequestAsync()))
if (-not $task.Wait(10000)) { exit 1 }
$manager = $task.Result
while ($true) {
    [Console]::Out.WriteLine((Get-MochiPlaybackFlags ($manager.GetSessions())))
    [Console]::Out.Flush()
    Start-Sleep -Milliseconds 1000
}
'''


class PlaybackBroker:
    def __init__(self):
        self.clients = 0
        self.process = None
        self.thread = None
        self.state = (False, False)
        self.updated = 0.0

    def acquire(self):
        if self.clients == 0:
            powershell = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
            command = base64.b64encode(SCRIPT.encode('utf-16-le')).decode('ascii')
            self.process = subprocess.Popen(
                [str(powershell), '-NoLogo', '-NoProfile', '-NonInteractive', '-EncodedCommand', command],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            self.thread = threading.Thread(target=self._read, args=(self.process,), daemon=True, name='mochi-media')
            self.thread.start()
        self.clients += 1

    def _read(self, process):
        for line in iter(process.stdout.readline, b''):
            line = line.strip()
            if line in (b'0,0', b'0,1', b'1,0', b'1,1'):
                self.state = line[0] == 49, line[2] == 49
                self.updated = time.monotonic()
        self.state = (False, False)

    def sample(self, index):
        if self.process is None or self.process.poll() is not None or time.monotonic() - self.updated > 5:
            return False  # clear stale reactions if the helper stops or stalls
        return self.state[index]

    def release(self):
        self.clients = max(0, self.clients - 1)
        if self.clients == 0 and self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
            self.thread.join(timeout=2)
            self.process.stdout.close()
            self.process = self.thread = None
            self.state = (False, False)


_broker = PlaybackBroker()


class WindowsMediaBackend:
    name = 'Windows media playback status'
    watching_via_browser_focus = False
    watching_via_youtube_focus = False

    def __init__(self):
        self.last_error = None
        self.active = False

    def start(self):
        if self.active:
            return True
        try:
            _broker.acquire()
            self.active = True
            return True
        except OSError as exc:
            self.last_error = str(exc)
            return False

    def stop(self):
        if self.active:
            _broker.release()
            self.active = False

    def sample_music_playing(self):
        return _broker.sample(0)

    def sample_youtube_playing(self):
        # Existing monitor uses this legacy method name for all watchable video.
        return _broker.sample(1)
