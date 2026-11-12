# Windows parity implementation plan

1. Inventory shared menus and platform-specific integrations.
2. Implement and unit-test content-free browser change pulses.
3. Run normal-mode native integration tests for menus and feature windows.
4. Correct failures using Windows CI, preserving Linux regression coverage.
5. Complete update/virtual desktop adapters and qualify their failure recovery.
6. Record actual evidence and remaining Windows 11 interactive checks.

The user has authorized implementation; no additional design approval is needed.

Follow-up from the Quick Start screenshot: exercise the right-click menu through
Win32 input on the disposable runner. Cover single/double-click reactions and the
Focus start/pause/resume/cancel path. Restore the documented double-click heart
through the shared click handling, preserving drag release and Fedora click counts.

Windows 11 feedback: exercise grow/shrink of the mapped companion, recover
its no-activate topmost style after native demotion, and open Pocket's local
folder via the Windows shell. Keep the existing browser signal content-free.
Check window sizing in device pixels and retain the existing work-area clamp.
