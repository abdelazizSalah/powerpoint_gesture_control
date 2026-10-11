"""Gesture filtering independent of the camera and Windows."""

from dataclasses import dataclass, field
import math


DEFAULT_GESTURE = "Shaka"
GESTURE_CHOICES = {"Thumbs-up": "Thumb_Up", "Shaka": "Shaka", "Victory (V sign)": "Victory"}
GESTURE_HINTS = {
    "Thumb_Up": "Extend your thumb upward and fold the other fingers.",
    "Shaka": "Extend thumb and little finger; fold index, middle, and ring fingers.",
    "Victory": "Extend index and middle fingers in a V; fold the other fingers.",
}


def gesture_label(name):
    return next((label for label, value in GESTURE_CHOICES.items() if value == name), name.replace("_", " "))


def shaka_score(landmarks):
    """Geometry match for thumb/pinky extended and index/middle/ring folded.

    Use world landmarks when available. Angles and length ratios make the rule
    independent of hand size, handedness, and rotation. This is a match score,
    not a probability from MediaPipe's canned gesture classifier.
    """
    if len(landmarks) != 21:
        return 0.0
    points = [(p.x, p.y, getattr(p, "z", 0.0)) for p in landmarks]
    if not all(math.isfinite(value) for point in points for value in point):
        return 0.0

    def distance(a, b):
        return math.dist(points[a], points[b])

    def angle(a, b, c):
        u = [points[a][i] - points[b][i] for i in range(3)]
        v = [points[c][i] - points[b][i] for i in range(3)]
        length = math.sqrt(sum(x * x for x in u) * sum(x * x for x in v))
        if length < 1e-12:
            return 0.0
        cosine = max(-1.0, min(1.0, sum(x * y for x, y in zip(u, v)) / length))
        return math.degrees(math.acos(cosine))

    palm = distance(0, 9)
    thumb_ip_radius = distance(0, 3)
    pinky_pip_radius = distance(0, 18)
    if min(palm, thumb_ip_radius, pinky_pip_radius) < 1e-9:
        return 0.0
    scores = [
        (angle(2, 3, 4) - 100.0) / 55.0,
        (angle(17, 18, 19) - 100.0) / 60.0,
        (angle(18, 19, 20) - 100.0) / 60.0,
        (distance(4, 5) / palm - 0.20) / 0.45,
        (distance(0, 4) / thumb_ip_radius - 1.0) / 0.15,
        (distance(0, 20) / pinky_pip_radius - 1.0) / 0.30,
    ]
    for mcp, pip, dip in ((5, 6, 7), (9, 10, 11), (13, 14, 15)):
        scores.append((140.0 - angle(mcp, pip, dip)) / 60.0)
    return max(0.0, min(1.0, min(scores)))


def best_gesture(result, target_gesture=DEFAULT_GESTURE):
    """Prefer the selected gesture on either hand, using only top model classes."""
    if target_gesture == "Shaka":
        hands = getattr(result, "hand_world_landmarks", None) or getattr(result, "hand_landmarks", [])
        match = max((shaka_score(hand) for hand in hands), default=0.0)
        if match >= 0.5:
            return "Shaka", match
    choices = [max(hand, key=lambda item: item.score) for hand in result.gestures if hand]
    if not choices:
        return "No hand", 0.0
    targets = [item for item in choices if item.category_name == target_gesture]
    best = max(targets or choices, key=lambda item: item.score)
    return best.category_name, float(best.score)


@dataclass
class GestureGate:
    """One pulse per held gesture, with a stable release required to rearm."""

    confidence: float = 0.75
    hold_seconds: float = 0.35
    release_seconds: float = 0.30
    cooldown_seconds: float = 1.0
    max_frame_gap: float = 0.25
    target_gesture: str = DEFAULT_GESTURE
    armed: bool = field(default=False, init=False)
    _hold_since: float | None = field(default=None, init=False)
    _release_since: float | None = field(default=None, init=False)
    _last_click: float = field(default=float("-inf"), init=False)
    _previous_time: float | None = field(default=None, init=False)

    def __post_init__(self):
        if self.target_gesture not in GESTURE_CHOICES.values():
            raise ValueError("Choose Thumbs-up, Shaka, or Victory (V sign).")

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

        is_target = name == self.target_gesture and score >= self.confidence
        if not is_target:
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
