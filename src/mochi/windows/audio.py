"""Short local sound cues using the bundled GStreamer runtime."""
import logging


class GStreamerCueBackend:
    def __init__(self, gst=None):
        if gst is None:
            import gi
            gi.require_version('Gst', '1.0')
            from gi.repository import Gst
            gst = Gst
        self.gst = gst
        gst.init(None)
        self._players = {}

    def play(self, path, volume):
        if len(self._players) >= 16:
            self._release(next(iter(self._players)))
        player = self.gst.ElementFactory.make('playbin', None)
        if player is None:
            raise OSError('Bundled GStreamer playbin is unavailable')
        player.set_property('uri', path.resolve().as_uri())
        player.set_property('volume', max(0.0, min(1.0, volume)))
        bus = player.get_bus()
        bus.add_signal_watch()
        handler = bus.connect('message', self._message, player)
        self._players[player] = (bus, handler)
        if player.set_state(self.gst.State.PLAYING) == self.gst.StateChangeReturn.FAILURE:
            self._release(player)
            raise OSError('Windows audio output could not start')

    def _message(self, bus, message, player):
        if message.type in (self.gst.MessageType.EOS, self.gst.MessageType.ERROR):
            if message.type == self.gst.MessageType.ERROR:
                logging.getLogger(__name__).debug('Audio cue unavailable')
            self._release(player)

    def _release(self, player):
        owned = self._players.pop(player, None)
        if owned is not None:
            bus, handler = owned
            bus.disconnect(handler)
            bus.remove_signal_watch()
            player.set_state(self.gst.State.NULL)

    def close(self):
        for player in tuple(self._players):
            self._release(player)
