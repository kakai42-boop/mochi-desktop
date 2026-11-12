"""In-memory timing and one-use grants for the optional browser prank."""

from dataclasses import dataclass
from secrets import token_urlsafe

WARNING_SECONDS = 10
GRANT_GRACE_SECONDS = 3


@dataclass(frozen=True)
class Countdown:
    token: str
    foreground: tuple[int, str]
    due: float


class BrowserMood:
    def __init__(self, interval):
        self.interval = interval
        self.foreground = None
        self.last_sample = None
        self.active_seconds = 0
        self.countdown = None

    def reset(self):
        self.last_sample = None
        self.active_seconds = 0
        self.countdown = None

    def sample(self, now, foreground):
        gap = self.last_sample is not None and now - self.last_sample > 2
        if self.countdown is not None and (
            gap or foreground != self.countdown.foreground
            or now > self.countdown.due + GRANT_GRACE_SECONDS
        ):
            self.reset()
        if (not gap and foreground is not None and self.foreground == foreground
                and self.last_sample is not None):
            self.active_seconds += min(1, max(0, now - self.last_sample))
        self.foreground = foreground
        self.last_sample = now

    def request(self, now, message):
        action = message.get('op')
        if action == 'arm':
            if (self.countdown is not None or self.foreground is None
                    or self.foreground[1] != message.get('browser')
                    or self.active_seconds < self.interval):
                return {}
            self.countdown = Countdown(token_urlsafe(24), self.foreground, now + WARNING_SECONDS)
            return {'token': self.countdown.token, 'seconds': WARNING_SECONDS}
        if self.countdown is None or message.get('token') != self.countdown.token:
            return {}
        if action == 'cancel':
            self.reset()
        elif action == 'finish':
            if now > self.countdown.due + GRANT_GRACE_SECONDS:
                self.reset()
            elif now >= self.countdown.due and self.foreground == self.countdown.foreground:
                self.reset()
                return {'close': True}
        return {}
