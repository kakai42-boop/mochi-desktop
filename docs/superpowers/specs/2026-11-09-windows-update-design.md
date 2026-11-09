# Windows package updates

Use the existing update menu, preferences and ancestry checks. Windows consumes
only packaged Windows releases from the port's repository. Release and Main
select stable Windows releases and Windows previews, respectively. Download a
bounded ZIP, verify the GitHub asset SHA-256 and check the bundled commit before
handing off. No installation happens until Update & Restart is selected.

The external Windows worker waits for the launcher and app to exit and swaps
only the app's managed entries. It retains the old entries until the new
launcher reaches the existing readiness handshake. A startup failure restores
them and relaunches the previous app. Preferences and Pocket stay outside the
transaction. A failed restoration preserves the backup for recovery.
