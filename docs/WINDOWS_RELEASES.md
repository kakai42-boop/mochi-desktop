# Windows release channels

Windows uses the port repository's GitHub releases. The existing `Release`
channel selects published stable tags starting with `windows-v`. The `Main`
channel selects published prerelease tags starting with `windows-preview-`.
An eligible release contains `Mochi-Windows11-Portable.zip` with the SHA-256
provided by GitHub. Drafts and Linux artifacts are ignored.

Run the Windows workflow from the commit intended for publication. Use the
**push or manually dispatched run for that commit**, which embeds its source
identity, rather than the pull request run, which builds a synthetic merge.
After the Windows job passes, upload its unmodified portable ZIP and setup EXE
to a release tagged at that exact commit. Mark a preview as a prerelease. Keep
release assets immutable once published. The setup EXE serves first installs.
The portable ZIP serves the in-app updater.

On the first migration from older Windows builds, use the setup EXE. Those
builds lack the source identity needed for update ancestry checks. The new
app uses the existing update-check preference and only installs after
`Update & Restart`. A later build must descend from the installed commit.

The updater stages the archive before closing Mochi and verifies its size,
SHA-256 and source commit. Only the managed program entries are replaced.
It restores the previous entries when the replacement fails to launch.
On an interrupted or unsuccessful recovery, keep the sibling
`.mochi-update-*` folder: it contains the recovery files and `result.json`.
The app shows the recorded update error on the next successful start.
