# Windows active monitor and browser mood plan

1. Review the two settings, trigger and protections before runtime changes.
2. Add monitor selection from the foreground HWND and use the Windows
   work area with existing placement and non-activation behavior.
   Reuse the owned Windows desktop timer. Test enable/disable, debounce,
   own windows, drag/menu/sleep suspension and negative-coordinate monitors.
3. Test the normal Windows package. On a two-monitor Windows 11 setup,
   switch foreground apps in both directions, verify scaling/taskbars and
   confirm that drag, click and menus still work.
4. Add the separately enabled browser setting and in-memory countdown
   policy. Test timing and cancellation before integrating the host.
5. Implement extension and per-user native messaging registration. Test
   exact tab identity, no close when the extension or option is absent,
   fullscreen and video fullscreen, lost focus, navigation, pinning,
   private windows, last tab and disconnect. Validate browser behavior in
   Chrome and Edge before distributing the browser option.
