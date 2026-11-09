"""GTK application and transparent top-level buddy window."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib, Gtk  # noqa: E402

from mochi.agent_activity import AGENT_EVENTS, AGENT_TOKEN_PATTERN
from mochi.color_scheme import SystemColorSchemeSync
if sys.platform == "win32":
    from mochi.windows.theme import WindowsColorSchemeSync as SystemColorSchemeSync
from mochi.config import ConfigStore
from mochi.presence.click_dialogue import PresenceBuddy, PresenceX11Buddy
from mochi.sound import SoundEvent, SoundManager
from mochi.state import MochiState, PresentationState
from mochi.windowing import WindowPlacement
from mochi.x11 import request_keep_above


AGENT_EVENT_ACTION = "agent-event"


def signal_update_ready(path: Path) -> None:
    """Atomically report that the updated Mochi reached normal activation."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text("ready\n", encoding="utf-8")
    temporary.replace(path)


class MochiApplication(Gtk.Application):
    def __init__(
        self,
        config: ConfigStore,
        preview_animations: bool = False,
        update_ready_file: Path | None = None,
    ) -> None:
        super().__init__(
            application_id=(
                "io.github.mochi_desktop.Mochi.Preview"
                if preview_animations
                else "io.github.mochi_desktop.Mochi"
            ),
            flags=(Gio.ApplicationFlags.NON_UNIQUE if sys.platform == "win32" else Gio.ApplicationFlags.DEFAULT_FLAGS),
        )
        self._windows_agent_receiver = None
        self._windows_desktop_follower = None
        self._windows_mood = None
        self._follow_active_screen = sys.platform == "win32" and config.load_follow_active_screen()
        self.config = config
        self.preview_animations = preview_animations
        self.update_ready_file = update_ready_file
        self._logger = logging.getLogger(__name__)
        self._buddy: PresenceBuddy | PresenceX11Buddy | None = None
        self._color_scheme_sync: SystemColorSchemeSync | None = None
        self.sound = SoundManager(
            volume=config.load_volume(),
            muted=config.load_muted(),
        )
        if not preview_animations:
            # GApplication already exports app actions over org.gtk.Actions, so
            # `mochi-agent-signal` needs no new bus name, socket, or teardown.
            agent_action = Gio.SimpleAction.new(
                AGENT_EVENT_ACTION, GLib.VariantType.new("(ss)")
            )
            agent_action.connect("activate", self._on_agent_event_action)
            self.add_action(agent_action)

    def _on_agent_event_action(self, _action, parameter) -> None:
        """Forward a validated coding-agent lifecycle event to the buddy."""
        if parameter is None:
            return
        event, token = parameter.unpack()
        if event not in AGENT_EVENTS or AGENT_TOKEN_PATTERN.fullmatch(token) is None:
            self._logger.debug("Ignored a malformed agent event")
            return
        buddy = self._buddy
        if buddy is not None:
            buddy.receive_agent_event(event, token)

    def do_activate(self) -> None:
        existing = self.get_active_window()
        if existing is not None:
            existing.present()
            return

        # Plain GTK does not track the desktop's light/dark switch on its own.
        self._color_scheme_sync = SystemColorSchemeSync(Gtk.Settings.get_default())
        self._color_scheme_sync.start()

        window = Gtk.ApplicationWindow(application=self)
        window.add_css_class("mochi-buddy-window")
        window.set_title("Mochi Animation Preview" if self.preview_animations else "Mochi")
        window.set_decorated(False)
        window.set_resizable(False)
        window.set_focusable(False)
        size = self.config.load_size()
        window.set_default_size(size, size)

        placement = WindowPlacement(window, self.config.load_position())
        window.connect("map", self._configure_mapped_window, placement)
        buddy_class = PresenceBuddy if placement.layer_shell_enabled else PresenceX11Buddy
        buddy = buddy_class(
            window,
            placement,
            self.config,
            self.sound,
            preview_mode=self.preview_animations,
        )
        self._buddy = buddy
        if sys.platform == "win32" and not self.preview_animations:
            from mochi.windows.agent_ipc import AgentReceiver
            self._windows_agent_receiver = AgentReceiver(buddy.receive_agent_event)
            try:
                self._windows_agent_receiver.start()
            except OSError:
                self._windows_agent_receiver.stop()
                self._logger.exception("Windows agent bridge unavailable")
        window.set_child(buddy)

        css = Gtk.CssProvider()
        css.load_from_string(
            """
            /* Only the buddy surface should be transparent. Menu windows are
             * separate toplevels and must retain an opaque GTK background. */
            window.mochi-buddy-window {
                background-color: transparent;
            }

            window.mochi-menu-window {
                background-color: @theme_bg_color;
                color: @theme_fg_color;
                border: 1px solid alpha(@theme_fg_color, 0.12);
                border-radius: 18px;
                box-shadow: 0 12px 34px alpha(black, 0.28);
            }

            .mochi-menu-card {
                background-color: transparent;
            }

            .mochi-menu-title {
                font-size: 16px;
                font-weight: 700;
            }

            .mochi-menu-subtitle,
            .mochi-menu-hint,
            .mochi-menu-value,
            .mochi-menu-section {
                color: alpha(@theme_fg_color, 0.58);
            }

            .mochi-menu-subtitle,
            .mochi-menu-hint {
                font-size: 11px;
            }

            .mochi-menu-section {
                font-size: 11px;
                font-weight: 600;
                letter-spacing: 0.04em;
            }

            .mochi-menu-value {
                font-size: 11px;
            }

            .mochi-menu-sprout {
                font-size: 20px;
            }

            button.mochi-menu-row {
                min-height: 36px;
                padding: 4px 9px;
                border-radius: 10px;
                border: none;
                box-shadow: none;
                background-color: transparent;
            }

            button.mochi-menu-row:hover {
                background-color: alpha(@theme_fg_color, 0.07);
            }

            button.mochi-menu-row:active {
                background-color: alpha(@theme_fg_color, 0.12);
            }

            button.mochi-menu-danger {
                color: #c01c28;
            }

            .mochi-setting-row {
                min-height: 30px;
                padding: 0 8px;
            }

            /*
             * Some third-party GTK themes make the checked Gtk.Switch track
             * effectively transparent inside undecorated windows. Keep
             * Mochi's menu controls self-contained so an enabled setting never
             * looks like the control disappeared.
             */
            window.mochi-menu-window switch {
                min-width: 38px;
                min-height: 20px;
                padding: 2px;
                background-image: none;
                background-color: alpha(@theme_fg_color, 0.16);
                border: 1px solid alpha(@theme_fg_color, 0.18);
                border-radius: 999px;
                box-shadow: none;
            }

            window.mochi-menu-window switch:checked {
                background-image: none;
                background-color: #79c98b;
                border-color: #79c98b;
            }

            window.mochi-menu-window switch slider {
                min-width: 16px;
                min-height: 16px;
                background-image: none;
                background-color: @theme_bg_color;
                border: 1px solid alpha(@theme_fg_color, 0.18);
                border-radius: 999px;
                box-shadow: 0 1px 2px alpha(black, 0.22);
            }

            window.mochi-menu-window switch:checked slider {
                background-color: white;
                border-color: alpha(black, 0.08);
            }

            window.mochi-menu-window switch:disabled {
                opacity: 0.45;
            }

            scale.mochi-menu-scale {
                margin: 0 6px 2px 6px;
            }

            .mochi-tuning-grid spinbutton {
                min-width: 92px;
            }

            separator {
                background-color: alpha(@theme_fg_color, 0.09);
                min-height: 1px;
            }

            /* Speech bubbles live on transparent toplevels, so the capsule
             * must paint its own theme-safe surface and foreground. */
            .mochi-speech-bubble {
                background-color: @theme_bg_color;
                color: @theme_fg_color;
                border-color: alpha(#79c98b, 0.42);
            }

            .mochi-speech-text {
                color: @theme_fg_color;
            }

            .mochi-speech-text.mochi-speech-typing {
                color: alpha(@theme_fg_color, 0.78);
            }

            popover.mochi-speech-popover > arrow {
                background-color: @theme_bg_color;
                border-color: alpha(#79c98b, 0.42);
            }
            """
        )
        Gtk.StyleContext.add_provider_for_display(
            window.get_display(), css, Gtk.STYLE_PROVIDER_PRIORITY_USER
        )

        window.present()
        if sys.platform == "win32" and not self.preview_animations:
            self._start_windows_desktop_follower(window)
            mood_enabled, minutes = self.config.load_browser_mood()
            if mood_enabled:
                try:
                    self._start_windows_mood(minutes)
                except OSError as error:
                    self._logger.warning("Browser mood unavailable: %s", error)
        if self.update_ready_file is not None:
            signal_update_ready(self.update_ready_file)
        if not self.preview_animations:
            self.sound.play(SoundEvent.SPAWN)

    def _start_windows_desktop_follower(self, window) -> None:
        from mochi.windows.desktops import DesktopFollower, VirtualDesktopManager, shell_desktop_hint
        from mochi.windows.monitor_follow import MonitorFollower
        from mochi.windows.native import desktop
        from mochi.windows.windowing import handle

        try:
            manager = VirtualDesktopManager()
        except OSError as error:
            self._logger.debug("Virtual desktop following unavailable: %s", error)
            manager = None
        self._windows_desktop_follower = DesktopFollower(
            lambda: handle(window), desktop().user32.GetForegroundWindow,
            manager=manager, scheduler=GLib, repair_overlay=desktop().repair_overlay,
            desktop_hint=shell_desktop_hint,
            monitor_follower=MonitorFollower(
                desktop(), self._buddy._placement, allowed=self._can_follow_active_screen,
            ),
        )

    def _can_follow_active_screen(self) -> bool:
        buddy = self._buddy
        return (
            self._follow_active_screen and buddy is not None and not buddy._stay_put
            and not self._windows_interaction_busy()
            and buddy.state.current is not MochiState.WALKING
        )

    def _windows_interaction_busy(self) -> bool:
        buddy = self._buddy
        return (
            buddy is None or buddy._presence_shutting_down
            or buddy._press is not None or buddy._drag_started
            or buddy._context_menu_open or buddy._developer_menu.get_visible()
            or buddy._session_blocked()
            or buddy.state.presentation is not PresentationState.NORMAL
            or buddy.state.current in (
                MochiState.SLEEPING, MochiState.WAKING, MochiState.PICKUP,
                MochiState.DRAGGED, MochiState.DROPPING,
            )
        )

    def set_follow_active_screen(self, enabled: bool) -> None:
        self.config.save_follow_active_screen(enabled)
        self._follow_active_screen = enabled

    def show_windows_settings(self) -> Gtk.Window:
        from mochi.windows.browser_mood_ui import show_settings

        return show_settings(self, self._buddy._window)

    def _can_arm_browser_mood(self) -> bool:
        if self._windows_interaction_busy():
            return False
        buddy = self._buddy
        focus = buddy._focus_session
        return not buddy._ambient_presence_engine.tuning.quiet_mode and not (
            focus is not None and focus.active
        )

    def _start_windows_mood(self, minutes: int) -> None:
        from mochi.windows.browser_mood_ui import BrowserMoodController

        self._windows_mood = BrowserMoodController(
            self._buddy._window, self._can_arm_browser_mood, minutes,
        )

    def set_browser_mood(self, enabled: bool, minutes: int) -> None:
        if self._windows_mood is not None:
            self._windows_mood.close()
            self._windows_mood = None
        self.config.save_browser_mood(False, minutes)
        if not enabled:
            from mochi.windows.browser_mood_transport import unregister_host

            unregister_host()
            return
        self._start_windows_mood(minutes)
        try:
            self.config.save_browser_mood(True, minutes)
        except OSError:
            self._windows_mood.close()
            self._windows_mood = None
            raise

    def note_windows_attention(self) -> None:
        if self._windows_mood is not None:
            self._windows_mood.reset()

    def do_shutdown(self) -> None:
        if self._windows_mood is not None:
            self._windows_mood.close()
            self._windows_mood = None
        if self._windows_desktop_follower is not None:
            self._windows_desktop_follower.stop()
            self._windows_desktop_follower = None
        stop_theme = getattr(self._color_scheme_sync, "stop", None)
        if callable(stop_theme):
            stop_theme()
        if self._windows_agent_receiver is not None:
            self._windows_agent_receiver.stop()
            self._windows_agent_receiver = None
        if self._buddy is not None:
            self._buddy.shutdown_presence()
            self._buddy = None
        if not self.preview_animations:
            self.sound.play(SoundEvent.EXIT)
        close_audio = getattr(self.sound.backend, "close", None)
        if callable(close_audio):
            close_audio()
        Gtk.Application.do_shutdown(self)

    def _configure_mapped_window(
        self, window: Gtk.Window, placement: WindowPlacement
    ) -> None:
        placement.restore()
        if request_keep_above(window):
            self._logger.info("Requested always-on-top from the X11 window manager")
