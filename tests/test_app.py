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
        self.app.session_gesture = "Shaka"
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

    def test_held_shaka_advances_once_until_released(self):
        gate = GestureGate()
        for index in range(80):
            now = index * 0.1
            name = "No hand" if index < 5 else "Shaka"
            if gate.update(name, 0.95, now):
                with patch("app.time.monotonic", return_value=now + 0.05):
                    self.app.handle_gesture(now)
        self.app.controller.try_next_slide.assert_called_once_with()

    def test_start_passes_dropdown_selection_to_camera(self):
        self.app.worker = None
        self.app.test_only = Mock()
        self.app.test_only.get.return_value = True
        self.app.action = Mock()
        self.app.action.get.return_value = ACTION_NEXT_SLIDE
        self.app.path = Mock()
        self.app.path.get.return_value = ""
        self.app.camera = Mock()
        self.app.camera.get.return_value = "0"
        self.app.confidence = Mock()
        self.app.confidence.get.return_value = "0.75"
        self.app.gesture_choice = Mock()
        self.app.gesture_choice.get.return_value = "Victory (V sign)"
        self.app.pause_button = Mock()
        self.app.set_controls = Mock()
        with patch("app.CameraWorker") as camera:
            self.app.start()
            camera.assert_called_once_with(0, 0.75, "Victory")
            camera.return_value.start.assert_called_once_with()
        self.assertEqual(self.app.session_gesture, "Victory")

    def test_gesture_dropdown_is_locked_while_running(self):
        for name in ("start_button", "browse_button", "path_entry", "camera_box", "confidence_box",
                     "test_checkbox", "action_box", "gesture_box", "stop_button", "pause_button"):
            setattr(self.app, name, Mock())
        self.app.set_controls(True)
        self.app.gesture_box.configure.assert_called_with(state="disabled")
        self.app.set_controls(False)
        self.app.gesture_box.configure.assert_called_with(state="readonly")

    def test_pose_hint_updates_for_victory(self):
        self.app.gesture_choice = Mock()
        self.app.gesture_choice.get.return_value = "Victory (V sign)"
        self.app.gesture_hint = Mock()
        self.app.update_gesture_help()
        self.assertIn("index and middle", self.app.gesture_hint.set.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
