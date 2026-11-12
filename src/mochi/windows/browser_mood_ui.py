"""Windows settings and passive countdown UI for the browser mood option."""

import math
from pathlib import Path, PureWindowsPath
import time

from gi.repository import GLib, Gtk

from mochi.windows.browser_mood import BrowserMood
from mochi.windows.browser_mood_transport import MoodBridge, register_host
from mochi.windows.native import desktop
from mochi.windows.windowing import handle


BROWSERS = {'chrome.exe': 'chrome', 'msedge.exe': 'edge'}


def card(window):
    content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    for side in ('top', 'bottom', 'start', 'end'):
        getattr(content, 'set_margin_' + side)(16)
    window.set_child(content)
    return content


def label(text):
    return Gtk.Label(label=text, wrap=True, xalign=0)


def show_settings(app, owner):
    window = Gtk.Window(title="Paramètres Windows de Mochi", transient_for=owner,
                        default_width=430, resizable=False)
    content = card(window)
    follow = Gtk.CheckButton(label="Suivre l’écran actif")
    follow.set_active(app._follow_active_screen)
    content.append(follow)
    content.append(label("Mochi rejoint l’écran de la fenêtre que tu utilises. « Stay put » suspend ce suivi."))
    enabled, minutes = app.config.load_browser_mood()
    mood = Gtk.CheckButton(label="Activer l’humeur taquine")
    mood.set_active(enabled)
    content.append(mood)
    content.append(label(
        "Après le délai choisi, Mochi peut fermer l’onglet actif. Un avertissement de 10 secondes "
        "permet d’annuler. Une saisie non enregistrée peut être perdue."
    ))
    interval = Gtk.SpinButton.new_with_range(1, 240, 1)
    interval.set_value(minutes)
    row = Gtk.Box(spacing=10)
    row.append(label("Délai d’activité sans interaction (minutes)"))
    row.append(interval)
    content.append(row)
    extension = Path(__file__).with_name('browser_extension')
    content.append(label("Dans Chrome ou Edge, active le mode développeur sur la page des extensions, "
                         "puis choisis « Charger l’extension non empaquetée »."))
    folder = Gtk.Entry(text=str(extension), editable=False)
    content.append(folder)
    feedback = label("")
    content.append(feedback)
    apply = Gtk.Button(label="Enregistrer")
    content.append(apply)

    def save(_button):
        try:
            app.set_follow_active_screen(follow.get_active())
            app.set_browser_mood(mood.get_active(), interval.get_value_as_int())
        except OSError:
            feedback.set_text("Impossible d’enregistrer les réglages de l’humeur.")
        else:
            window.close()

    apply.connect('clicked', save)
    window.present()
    return window


class BrowserMoodController:
    def __init__(self, owner, allowed, minutes):
        self.owner = owner
        self.allowed = allowed
        self.mood = BrowserMood(minutes * 60)
        self.api = desktop()
        self.warning = None
        self.warning_label = None
        self.last_seconds = None
        register_host()
        self.bridge = MoodBridge(GLib, self._dispatch)
        self.source = GLib.timeout_add(350, self._tick)

    def _foreground(self):
        if not self.allowed():
            return None
        hwnd = self.api.user32.GetForegroundWindow()
        if not hwnd:
            return None
        idle = self.api.idle_seconds()
        if idle is None or idle >= 30:
            return None
        browser = BROWSERS.get(PureWindowsPath(self.api.executable(hwnd)).name.casefold())
        if browser and self.api.fullscreen(hwnd) is False:
            return hwnd, browser
        return None

    def _dispatch(self, message):
        if message.get('op') == 'status':
            return {'connected': True}
        if message.get('op') == 'finish' and (
            self.warning is None or not self.warning.get_mapped()
        ):
            self.reset()
            return {}
        now = time.monotonic()
        self.mood.sample(now, self._foreground())
        result = self.mood.request(now, message)
        self._show_warning(now)
        # A grant is useless if the warning couldn't be made visible.
        if 'token' in result and (self.warning is None or not self.warning.get_visible()):
            self.reset()
            return {}
        return result

    def _tick(self):
        now = time.monotonic()
        self.mood.sample(now, self._foreground())
        self._show_warning(now)
        return GLib.SOURCE_CONTINUE

    def _show_warning(self, now):
        countdown = self.mood.countdown
        if countdown is None:
            if self.warning is not None:
                self.warning.set_visible(False)
            self.last_seconds = None
            return

        seconds = max(1, math.ceil(countdown.due - now))
        if self.warning is None:
            self.warning = Gtk.Window(title="Mochi", transient_for=self.owner,
                                      decorated=False, focusable=False, resizable=False)
            content = card(self.warning)
            self.warning_label = label("")
            content.append(self.warning_label)
            cancel = Gtk.Button(label="Annuler")
            cancel.connect('clicked', lambda _button: self.reset())
            content.append(cancel)
            self.warning.realize()
        if seconds != self.last_seconds:
            self.warning_label.set_text(f"Mochi fermera cet onglet dans {seconds} s.")
            self.last_seconds = seconds
        if not self.warning.get_visible():
            monitor = self.api.monitor_for_window(countdown.foreground[0])
            area = self.api.monitor_work_area(monitor)
            hwnd = handle(self.warning)
            if area is None or not hwnd or not self.api.show_passive(hwnd, area[0] + 24, area[1] + 24):
                self.mood.reset()
                return
            # Show without activation before mapping GTK. GDK Win32 skips
            # ShowWindow(SW_SHOWNORMAL) for an already visible native surface.
            self.warning.set_visible(True)
            if self.api.user32.GetForegroundWindow() != countdown.foreground[0]:
                self.mood.reset()
                self.warning.set_visible(False)

    def reset(self):
        self.mood.reset()
        self._show_warning(time.monotonic())

    def close(self):
        GLib.source_remove(self.source)
        self.bridge.close()
        if self.warning is not None:
            self.warning.destroy()
