"""Reference-pose geometry, wrong poses, and classification-to-gate checks."""

import math
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gesture import DEFAULT_GESTURE, GestureGate, best_gesture, shaka_score


# Approximate positions of the 21 visible joints in the user's annotated pose.
REFERENCE = (
    (162, 181), (170, 146), (175, 93), (180, 58), (198, 38),
    (172, 86), (121, 59), (123, 80), (135, 90),
    (155, 101), (106, 77), (106, 94), (119, 103),
    (134, 118), (87, 88), (91, 104), (106, 112),
    (114, 134), (77, 104), (53, 85), (31, 65),
)


def reference_hand():
    return [SimpleNamespace(x=x / 200, y=y / 200, z=0.0) for x, y in REFERENCE]


class ShakaTests(unittest.TestCase):
    def test_reference_pose_passes_default_threshold(self):
        self.assertGreaterEqual(shaka_score(reference_hand()), GestureGate().confidence)

    def test_mirroring_rotation_and_scale_preserve_detection(self):
        hand = reference_hand()
        expected = shaka_score(hand)
        for direction in (-1, 1):
            for theta in (0.0, 0.7, 2.5):
                transformed = [SimpleNamespace(
                    x=direction * (p.x * math.cos(theta) - p.y * math.sin(theta)) * 1.7 + 3,
                    y=(p.x * math.sin(theta) + p.y * math.cos(theta)) * 1.7 - 2,
                    z=p.z * 1.7 + 0.5,
                ) for p in hand]
                self.assertAlmostEqual(shaka_score(transformed), expected)

    def test_extended_index_middle_or_ring_is_rejected(self):
        for base in (5, 9, 13):
            hand = reference_hand()
            for step in (1, 2, 3):
                hand[base + step] = SimpleNamespace(
                    x=hand[base].x - step * 0.1, y=hand[base].y - step * 0.12, z=0.0,
                )
            self.assertLess(shaka_score(hand), 0.5)

    def test_folded_thumb_or_pinky_is_rejected(self):
        for tip, near in ((4, 5), (20, 17)):
            hand = reference_hand()
            hand[tip] = hand[near]
            self.assertLess(shaka_score(hand), 0.5)

    def test_missing_degenerate_or_nonfinite_landmarks_are_rejected(self):
        self.assertEqual(shaka_score([]), 0)
        self.assertEqual(shaka_score([SimpleNamespace(x=0, y=0, z=0)] * 21), 0)
        hand = reference_hand()
        hand[4].x = float("nan")
        self.assertEqual(shaka_score(hand), 0)

    def test_shaka_landmarks_override_canned_none_label(self):
        result = SimpleNamespace(
            hand_landmarks=[reference_hand()],
            gestures=[[SimpleNamespace(category_name="None", score=0.99)]],
        )
        name, score = best_gesture(result)
        self.assertEqual(name, DEFAULT_GESTURE)
        self.assertGreaterEqual(score, 0.75)

    def test_shaka_on_other_hand_does_not_mask_selected_model_gesture(self):
        for target in ("Thumb_Up", "Victory"):
            result = SimpleNamespace(
                hand_landmarks=[reference_hand()],
                gestures=[[SimpleNamespace(category_name=target, score=0.9)]],
            )
            self.assertEqual(best_gesture(result, target), (target, 0.9))

    def test_world_landmarks_are_used_when_available(self):
        result = SimpleNamespace(hand_world_landmarks=[reference_hand()], hand_landmarks=[], gestures=[])
        self.assertEqual(best_gesture(result)[0], DEFAULT_GESTURE)

    def test_either_hand_can_trigger(self):
        result = SimpleNamespace(hand_landmarks=[[], reference_hand()], gestures=[])
        self.assertEqual(best_gesture(result)[0], DEFAULT_GESTURE)

    def test_held_reference_pose_emits_one_action(self):
        gate = GestureGate()
        result = SimpleNamespace(hand_landmarks=[reference_hand()], gestures=[])
        for index in range(5):
            gate.update("No hand", 0, index * 0.1)
        name, score = best_gesture(result)
        pulses = sum(gate.update(name, score, 0.5 + index * 0.1) for index in range(50))
        self.assertEqual(pulses, 1)

    def test_thumbs_up_does_not_trigger_selected_shaka(self):
        gate = GestureGate()
        for index in range(5):
            gate.update("No hand", 0, index * 0.1)
        self.assertFalse(any(gate.update("Thumb_Up", 0.99, 0.5 + index * 0.1) for index in range(50)))


if __name__ == "__main__":
    unittest.main()
