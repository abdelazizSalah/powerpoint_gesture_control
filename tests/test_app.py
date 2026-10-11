"""Gesture-to-action dispatch without opening Tk, a webcam, or PowerPoint."""

from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import ACTION_MOUSE_CLICK, ACTION_NEXT_SLIDE, GestureApp
from gesture import GestureGate


class ActionDispatchTests(unittest.TestCase):
    def setUp(self):
        self.app = GestureApp.__new__(GestureApp)
        self.app.running = True
        self.app.paused = False
        self.app.worker = SimpleNamespace(stopping=Mock())
        self.app.worker.stopping.is_set.return_value = False
        self.app.enabled_since = 0.0
        self.app.test_session = False
        self.app.session_action = ACTION_NEXT_SLIDE
        self.app.click_count = 0
        self.app.status = Mock()
        self.app.count_text = Mock()
        self.app.controller = Mock()
        self.app.controller.try_next_slide.return_value = (True, "Next slide command sent")
        self.app.controller.try_click.return_value = (True, "Left click sent")
        self.clock = patch("app.time.monotonic", return_value=2.0)
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def test_next_slide_dispatch(self):
        self.app.handle_gesture(1.9)
        self.app.controller.try_next_slide.assert_called_once_with()
        self.app.controller.try_click.assert_not_called()
        self.app.count_text.set.assert_called_once_with("Next slide commands sent: 1")

    def test_mouse_click_dispatch(self):
        self.app.session_action = ACTION_MOUSE_CLICK
        self.app.handle_gesture(1.9)
        self.app.controller.try_click.assert_called_once_with()
        self.app.controller.try_next_slide.assert_not_called()

    def test_paused_and_stopped_sessions_do_not_advance(self):
        self.app.paused = True
        self.app.handle_gesture(1.9)
        self.app.paused = False
        self.app.worker.stopping.is_set.return_value = True
        self.app.handle_gesture(1.9)
        self.app.controller.try_next_slide.assert_not_called()

    def test_stale_gesture_is_reported_without_advancing(self):
        self.app.handle_gesture(1.0)
        self.app.controller.try_next_slide.assert_not_called()
        self.assertIn("delayed", self.app.status.set.call_args.args[0])

    def test_failed_command_does_not_increment_counter(self):
        self.app.controller.try_next_slide.return_value = (False, "Slideshow ended")
        self.app.handle_gesture(1.9)
        self.assertEqual(self.app.click_count, 0)
        self.app.status.set.assert_called_once_with("Slideshow ended")

    def test_detection_only_does_not_control_powerpoint(self):
        self.app.test_session = True
        self.app.handle_gesture(1.9)
        self.app.controller.try_next_slide.assert_not_called()
        self.app.controller.try_click.assert_not_called()
        self.assertEqual(self.app.click_count, 1)

    def test_held_thumb_advances_once_until_released(self):
        gate = GestureGate()
        for index in range(80):
            now = index * 0.1
            name = "No hand" if index < 5 else "Thumb_Up"
            if gate.update(name, 0.95, now):
                with patch("app.time.monotonic", return_value=now + 0.05):
                    self.app.handle_gesture(now)
        self.app.controller.try_next_slide.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
