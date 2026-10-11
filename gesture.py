"""Gesture filtering independent of the camera and Windows."""

from dataclasses import dataclass, field


def best_gesture(result):
    """Use the top class for each hand; do not accept a lower-ranked thumbs-up."""
    choices = [max(hand, key=lambda item: item.score) for hand in result.gestures if hand]
    if not choices:
        return "No hand", 0.0
    thumbs = [item for item in choices if item.category_name == "Thumb_Up"]
    best = max(thumbs or choices, key=lambda item: item.score)
    return best.category_name, float(best.score)


@dataclass
class GestureGate:
    """One pulse per held gesture, with a stable release required to rearm."""

    confidence: float = 0.75
    hold_seconds: float = 0.35
    release_seconds: float = 0.30
    cooldown_seconds: float = 1.0
    max_frame_gap: float = 0.25
    armed: bool = field(default=False, init=False)
    _hold_since: float | None = field(default=None, init=False)
    _release_since: float | None = field(default=None, init=False)
    _last_click: float = field(default=float("-inf"), init=False)
    _previous_time: float | None = field(default=None, init=False)

    def update(self, name: str, score: float, now: float, enabled: bool = True) -> bool:
        # Resuming, starting, or recovering from a stalled camera requires a release.
        if not enabled or (
            self._previous_time is not None
            and (now < self._previous_time or now - self._previous_time > self.max_frame_gap)
        ):
            self.armed = False
            self._hold_since = self._release_since = None
        self._previous_time = now
        if not enabled:
            return False

        is_thumb = name == "Thumb_Up" and score >= self.confidence
        if not is_thumb:
            self._hold_since = None
            if self._release_since is None:
                self._release_since = now
            if now - self._release_since >= self.release_seconds:
                self.armed = True
            return False

        self._release_since = None
        if not self.armed:
            return False
        if self._hold_since is None:
            self._hold_since = now
        if (
            now - self._hold_since >= self.hold_seconds
            and now - self._last_click >= self.cooldown_seconds
        ):
            self.armed = False
            self._hold_since = None
            self._last_click = now
            return True
        return False
