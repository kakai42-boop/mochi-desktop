"""Follow the user's Windows app theme without a Linux settings portal."""
class WindowsColorSchemeSync:
    def __init__(self, settings):
        self.settings = settings
        self.source = None

    def start(self):
        from gi.repository import GLib
        self._poll()
        self.source = GLib.timeout_add_seconds(3, self._poll)
        return True

    def _poll(self):
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize') as key:
                light, _ = winreg.QueryValueEx(key, 'AppsUseLightTheme')
            self.settings.props.gtk_application_prefer_dark_theme = not bool(light)
        except OSError:
            pass
        return True

    def stop(self):
        if self.source is not None:
            from gi.repository import GLib
            GLib.source_remove(self.source)
            self.source = None
