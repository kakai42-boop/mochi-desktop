# Windows active monitor and browser mood

## Active monitor

Add a Windows-only "Follow active screen" toggle in Mochi's user menu.
Persist the choice and default it to off for existing and new installs.
Use the work area of the monitor that contains most of the foreground
application window. Wait for a stable foreground sample before moving.
A pointer crossing alone does not move the pet. Ignore Mochi's own
windows and shell surfaces. Pause during interaction, a menu, a lock,
sleep or Stay put. Keep Mochi fully in bounds, including after a DPI
change, and do not activate his window. Save positions on manual drop;
automatic following does not replace the user's saved position.

## Browser mood

Add an independent opt-in setting, off by default, with an adjustable
attention interval (suggested default 60 minutes of eligible activity),
a visible ten-second countdown and a cancel action. Eligible time is
time spent actively using a supported browser without interacting with
Mochi. Leaving the computer, sleeping, quiet mode, Focus and fullscreen
suppress the feature. Picking up, petting or feeding Mochi resets the
interval. A cancellation or a close starts a fresh interval.

Use a small optional Chrome/Edge extension and a local native messaging
host registered for the current user. Use opaque window/tab IDs, focus,
fullscreen and tab state only. The extension requests no host permissions
and never reads titles, URLs, page text, keystrokes or history. Use a fixed
extension identity and an allowlisted host. There is no network access and
no global input simulation. The close path is unavailable without the
extension and an enabled user preference.

At the start of the countdown, capture one tab in a focused browser
window. Never select a different tab at the end of a countdown. Cancel
on focus, active-tab, navigation or fullscreen changes and if the app
disconnects. At dispatch, recheck the same window and tab, current focus,
fullscreen (including video fullscreen), pin state and tab count. Skip
private windows, pinned tabs, the last tab, and any window whose
fullscreen state cannot be determined reliably. Use the browser's exact
tab close operation. A browser page can contain unsaved work. The
setting states this before opt-in, and ordinary browser close protections
and restore behavior are left to the browser.

Two distinct changes will be reviewed and tested independently. The
Windows installer continues to install Mochi. Users enable the optional
browser feature after separately installing its extension once.
