"""Regression checks for repeat prevention and restricting mouse input to one deck."""

from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gesture import GestureGate, best_gesture
from powerpoint import PowerPointController


class GateTests(unittest.TestCase):
    def setUp(self):
        self.gate = GestureGate()
        self.now = 0.0

    def frames(self, name, count, score=0.95, enabled=True):
        pulses = 0
        for _ in range(count):
            pulses += self.gate.update(name, score, self.now, enabled)
            self.now = round(self.now + 0.1, 5)
        return pulses

    def test_starting_with_held_thumb_does_not_click(self):
        self.assertEqual(self.frames("Thumb_Up", 30), 0)
        self.frames("Open_Palm", 5)
        self.assertEqual(self.frames("Thumb_Up", 6), 1)

    def test_holding_thumb_produces_exactly_one_click(self):
        self.frames("No hand", 5)
        self.assertEqual(self.frames("Thumb_Up", 100), 1)

    def test_brief_gesture_is_ignored(self):
        self.frames("No hand", 5)
        self.assertEqual(self.frames("Thumb_Up", 3), 0)
        self.frames("Open_Palm", 5)
        self.assertEqual(self.frames("Thumb_Up", 6), 1)

    def test_low_confidence_never_clicks(self):
        self.frames("No hand", 5)
        self.assertEqual(self.frames("Thumb_Up", 30, score=0.6), 0)

    def test_detection_flicker_does_not_rearm(self):
        self.frames("No hand", 5)
        self.assertEqual(self.frames("Thumb_Up", 6), 1)
        self.frames("No hand", 2)
        self.assertEqual(self.frames("Thumb_Up", 30), 0)
        self.frames("Open_Palm", 5)
        self.assertEqual(self.frames("Thumb_Up", 6), 1)

    def test_pause_and_resume_requires_release(self):
        self.frames("No hand", 5)
        self.frames("Thumb_Up", 2)
        self.frames("Thumb_Up", 1, enabled=False)
        self.assertEqual(self.frames("Thumb_Up", 20), 0)
        self.frames("No hand", 5)
        self.assertEqual(self.frames("Thumb_Up", 6), 1)

    def test_camera_stall_cannot_complete_pending_hold(self):
        self.frames("No hand", 5)
        self.frames("Thumb_Up", 2)
        self.now += 5
        self.assertEqual(self.frames("Thumb_Up", 20), 0)
        self.frames("No hand", 5)
        self.assertEqual(self.frames("Thumb_Up", 6), 1)

    def test_cooldown_delays_second_click(self):
        self.gate = GestureGate(hold_seconds=0.1, release_seconds=0.1, cooldown_seconds=1)
        self.frames("No hand", 3)
        self.assertEqual(self.frames("Thumb_Up", 3), 1)
        self.frames("No hand", 3)
        self.assertEqual(self.frames("Thumb_Up", 3), 0)
        self.assertEqual(self.frames("Thumb_Up", 10), 1)

    def test_lower_ranked_thumb_is_not_accepted(self):
        category = lambda name, score: SimpleNamespace(category_name=name, score=score)
        result = SimpleNamespace(gestures=[[category("Open_Palm", 0.9), category("Thumb_Up", 0.8)]])
        self.assertEqual(best_gesture(result), ("Open_Palm", 0.9))
        result.gestures.append([category("Thumb_Up", 0.85)])
        self.assertEqual(best_gesture(result), ("Thumb_Up", 0.85))
        self.assertEqual(best_gesture(SimpleNamespace(gestures=[])), ("No hand", 0))


class TargetTests(unittest.TestCase):
    def setUp(self):
        self.presentation = SimpleNamespace(FullName=str(Path("selected.pptx").resolve()))
        self.show = SimpleNamespace(Presentation=self.presentation, HWND=10)
        self.desktop = Mock()
        self.desktop.root.side_effect = lambda hwnd: hwnd
        self.desktop.is_window.return_value = True
        self.desktop.foreground.return_value = 10
        self.desktop.cursor_window.return_value = 10
        self.controller = PowerPointController(self.presentation, self.show, self.desktop)

    def assert_skipped(self):
        clicked, explanation = self.controller.try_click()
        self.assertFalse(clicked, explanation)
        self.desktop.left_click.assert_not_called()

    def test_clicks_selected_active_show(self):
        self.assertTrue(self.controller.try_click()[0])
        self.desktop.left_click.assert_called_once_with()

    def test_different_foreground_app_blocks_click(self):
        self.desktop.foreground.return_value = 99
        self.assert_skipped()

    def test_pointer_outside_show_blocks_click(self):
        self.desktop.cursor_window.return_value = 99
        self.assert_skipped()

    def test_ended_show_blocks_click(self):
        self.desktop.is_window.return_value = False
        self.assert_skipped()

    def test_changed_presentation_blocks_click(self):
        self.show.Presentation = SimpleNamespace(FullName=str(Path("other.pptx").resolve()))
        self.assert_skipped()

    def test_focus_change_before_injection_blocks_click(self):
        self.desktop.foreground.side_effect = [10, 99]
        self.assert_skipped()

    def test_windows_input_failure_is_reported(self):
        self.desktop.left_click.side_effect = RuntimeError("Input blocked")
        clicked, explanation = self.controller.try_click()
        self.assertFalse(clicked)
        self.assertIn("Input blocked", explanation)


if __name__ == "__main__":
    unittest.main()
