# Windows functional parity

Authorized by the user's explicit request to continue all Linux functionality,
including menus. Reuse the existing menu hierarchy, state machine, persistence
and assets. Implement only OS adapters where the Linux service is unavailable.

First deliverable: browser title-change notifications without reading titles,
with foreground/recent-input/debounce gates; native feature tests running the
normal application and opening actual GTK menus/windows. All native hooks and
timers are owned and stopped. The existing preview smoke test is insufficient
for asserting normal-mode feature parity.

Subsequent gates: Windows update feed/installation transaction/rollback,
virtual desktop behavior, media and interactive DPI/audio/drag-drop validation.
Keep every incomplete gate explicit; do not label equivalent-looking menus as
proof that every integration works. No content inspection or telemetry.
