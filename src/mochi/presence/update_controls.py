"""User-facing update discovery and notification controls for Mochi."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sys
import threading

from gi.repository import GLib, Gtk

from mochi.update.bootstrap import bootstrap_updater
from mochi.update.checker import GitHubUpdateSource, UpdateChecker
from mochi.update.model import UpdateCheckResult, UpdateStatus, UpdateTarget
from mochi.update.storage import InstallMetadataStore
from mochi.update.window import UpdateWindow


UPDATE_STARTUP_DELAY_MS = 5_000
UPDATE_BUBBLE_TEXT = "psst... i learned some new things! 🌱"
UPDATE_BUBBLE_SECONDS = 4.0


class UpdateControlsMixin:
    """Add quiet update discovery without owning Mochi behavior state."""

    def __init__(self, *args, **kwargs) -> None:
        self._update_checker = None
        self._update_install_store = None
        self._update_target: UpdateTarget | None = None
        self._update_window: UpdateWindow | None = None
        self._update_menu_button = None
        self._update_menu_label = None
        self._update_startup_source_id: int | None = None
        self._update_callback_generation = 0
        self._update_shutting_down = False
        self._windows_update_cancel = None
        self._update_announced_commits: set[str] = set()
        super().__init__(*args, **kwargs)

        if self._preview_mode:
            return

        if sys.platform == "win32":
            from mochi.windows.updates import WindowsInstallMetadata, WindowsUpdateSource

            self._update_install_store = WindowsInstallMetadata()
            source = WindowsUpdateSource()
        else:
            self._update_install_store = InstallMetadataStore()
            source = GitHubUpdateSource()
        self._update_checker = UpdateChecker(
            config=self._config,
            install_store=self._update_install_store,
            source=source,
        )
        self._schedule_update_startup_check()

    def _build_context_menu(self):
        menu = super()._build_context_menu()
        button, self._update_menu_label = self._make_menu_button(
            "Check for updates",
            "software-update-available-symbolic",
            self._on_update_menu_clicked,
        )
        self._update_menu_button = button
        self._register_context_menu_row(
            "update",
            button,
            after="quick-start",
        )
        return menu

    def _schedule_update_startup_check(self) -> None:
        if self._preview_mode or self._update_shutting_down:
            return
        self._update_startup_source_id = GLib.timeout_add(
            UPDATE_STARTUP_DELAY_MS,
            self._run_scheduled_update_check,
        )

    def _run_scheduled_update_check(self) -> bool:
        self._update_startup_source_id = None
        if sys.platform != "win32" or not self._report_windows_update_failure():
            self._start_update_check(manual=False)
        return False

    def _start_update_check(self, *, manual: bool) -> None:
        if self._update_shutting_down or self._update_checker is None:
            return

        generation = self._update_callback_generation
        checker = self._update_checker

        def check() -> None:
            result = checker.check(manual=manual)
            GLib.idle_add(
                self._apply_update_result_if_current,
                result,
                manual,
                generation,
            )

        threading.Thread(
            target=check,
            name="mochi-update-check",
            daemon=True,
        ).start()

    def _apply_update_result_if_current(
        self,
        result: UpdateCheckResult,
        manual: bool,
        generation: int,
    ) -> bool:
        if generation != self._update_callback_generation:
            return False
        return self._apply_update_check_result(result, manual=manual)

    def _apply_update_check_result(
        self,
        result: UpdateCheckResult,
        *,
        manual: bool,
    ) -> bool:
        if self._update_shutting_down:
            return False

        if result.status is UpdateStatus.UPDATE_AVAILABLE and result.target is not None:
            self._update_target = result.target
            if self._update_menu_label is not None:
                self._update_menu_label.set_text("Update available")

            if (
                result.announce
                and result.target.commit not in self._update_announced_commits
            ):
                self._update_announced_commits.add(result.target.commit)
                bubble = getattr(self, "_presence_bubble", None)
                if (
                    bubble is not None
                    and getattr(self.state, "dialogue_allowed", False)
                ):
                    bubble.show(
                        UPDATE_BUBBLE_TEXT,
                        duration_seconds=UPDATE_BUBBLE_SECONDS,
                    )

            if manual:
                self._show_update_window(result.target)
            return False

        if result.status is UpdateStatus.UP_TO_DATE:
            self._update_target = None
            if self._update_menu_label is not None:
                self._update_menu_label.set_text("Check for updates")
            if manual:
                window = self._get_update_window()
                window.show_success()
                window.present()
            return False

        if manual:
            window = self._get_update_window()
            window.show_failure(
                "Couldn’t check for updates.",
                result.error or "Update check failed without additional details.",
            )
            window.present()
        return False

    def _on_update_menu_clicked(self, _button=None) -> None:
        close_then = getattr(self, "_close_context_menu_then", None)
        if callable(close_then):
            close_then(self._handle_update_menu_action)
        else:
            self._handle_update_menu_action()

    def _current_update_target(self) -> UpdateTarget | None:
        """Return the known target only if it came from the channel now saved.

        ``mochi-update --channel`` runs in another process, so a target found
        on the previous channel can still be held here; drop it instead of
        offering or installing it.
        """
        target = self._update_target
        if target is None:
            return None
        if target.metadata.channel != self._config.load_update_channel():
            self._update_target = None
            if self._update_menu_label is not None:
                self._update_menu_label.set_text("Check for updates")
            return None
        return target

    def _handle_update_menu_action(self) -> None:
        target = self._current_update_target()
        if target is None:
            self._start_update_check(manual=True)
            return
        self._show_update_window(target)

    def _get_update_window(self) -> UpdateWindow:
        if self._update_window is None:
            self._update_window = UpdateWindow(
                on_later=self._dismiss_update_target,
                on_update_restart=self._begin_update_restart,
                on_retry=lambda: self._start_update_check(manual=True),
                on_close=self._destroy_update_window,
            )
            self._update_window.connect(
                "close-request",
                self._on_update_window_close_request,
            )
            if getattr(self, "_window", None) is not None:
                self._update_window.set_transient_for(self._window)
        return self._update_window

    def _on_update_window_close_request(self, _window: Gtk.Window) -> bool:
        self._destroy_update_window()
        return True

    def _show_update_window(self, target: UpdateTarget) -> None:
        window = self._get_update_window()
        installed = (
            self._update_install_store.load()
            if self._update_install_store is not None
            else None
        )
        window.show_available(installed, target)
        window.present()

    def _dismiss_update_target(self) -> None:
        target = self._update_target
        if target is not None:
            self._config.save_dismissed_update_commit(target.commit)
            self._update_announced_commits.add(target.commit)
        self._destroy_update_window()

    def _destroy_update_window(self) -> None:
        cancel = getattr(self, "_windows_update_cancel", None)
        if cancel is not None:
            cancel.set()
        if self._update_window is not None:
            self._update_window.destroy()
            self._update_window = None

    def _begin_update_restart(self) -> None:
        if self._update_target is None:
            return
        target = self._current_update_target()
        if target is None:
            # The channel changed while the update window was open.
            self._start_update_check(manual=True)
            return

        if sys.platform == "win32":
            self._begin_windows_update(target)
            return

        bootstrap_updater(
            target,
            gui=True,
            wait_pid=os.getpid(),
        )
        application = Gtk.Application.get_default()
        if application is not None:
            application.quit()

    def _report_windows_update_failure(self) -> bool:
        local = os.environ.get("LOCALAPPDATA")
        if not local:
            return False
        path = Path(local) / "mochi-desktop" / "update-result.json"
        try:
            result = json.loads(path.read_text(encoding="utf-8-sig"))
            path.unlink()
        except (OSError, ValueError):
            return False
        if not isinstance(result, dict) or result.get("status") != "failed":
            return False
        message = (
            "The update failed. Your previous Mochi was restored."
            if result.get("restored") is True else "The Windows update could not finish."
        )
        window = self._get_update_window()
        window.show_failure(message, str(result.get("error", "")))
        window.present()
        return True

    def _begin_windows_update(self, target: UpdateTarget) -> None:
        from mochi.update.worker import UpdateProgress, UpdateStage
        from mochi.windows.updates import launch_update, prepare_update

        if self._windows_update_cancel is not None:
            return
        cancel = threading.Event()
        self._windows_update_cancel = cancel
        self._get_update_window().show_progress(UpdateProgress(
            UpdateStage.DOWNLOADING, "Downloading and verifying the Windows package…",
        ))

        def finish(workspace, error) -> bool:
            self._windows_update_cancel = None
            if cancel.is_set():
                if workspace is not None:
                    shutil.rmtree(workspace, ignore_errors=True)
                return False
            if error is None and self._config.load_update_channel() != target.metadata.channel:
                shutil.rmtree(workspace, ignore_errors=True)
                error = "The update channel changed. Check for updates again."
            if error is None:
                try:
                    launch_update(workspace)
                except OSError as exc:
                    shutil.rmtree(workspace, ignore_errors=True)
                    error = str(exc)
            if error is not None:
                window = self._get_update_window()
                window.show_failure("Couldn’t prepare the Windows update.", error)
                window.present()
                return False
            application = Gtk.Application.get_default()
            if application is not None:
                application.quit()
            return False

        def prepare() -> None:
            try:
                workspace = prepare_update(target, cancel)
            except Exception as exc:
                if not cancel.is_set():
                    GLib.idle_add(finish, None, str(exc))
                return
            if cancel.is_set():
                shutil.rmtree(workspace, ignore_errors=True)
                return
            GLib.idle_add(finish, workspace, None)

        threading.Thread(target=prepare, name="mochi-windows-update", daemon=True).start()

    def shutdown_presence(self) -> None:
        self._update_shutting_down = True
        cancel = getattr(self, "_windows_update_cancel", None)
        if cancel is not None:
            cancel.set()
        self._update_callback_generation += 1

        source_id = self._update_startup_source_id
        self._update_startup_source_id = None
        if source_id is not None:
            GLib.source_remove(source_id)

        self._destroy_update_window()
        super().shutdown_presence()
