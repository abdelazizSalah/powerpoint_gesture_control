"""Regression checks for repeat prevention and restricting mouse input to one deck."""

from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gesture import GESTURE_CHOICES, GestureGate, best_gesture
from powerpoint import PowerPointController, WindowsDesktop


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

    def test_starting_with_held_shaka_does_not_click(self):
        self.assertEqual(self.frames("Shaka", 30), 0)
        self.frames("Open_Palm", 5)
        self.assertEqual(self.frames("Shaka", 6), 1)

    def test_holding_shaka_produces_exactly_one_click(self):
        self.frames("No hand", 5)
        self.assertEqual(self.frames("Shaka", 100), 1)

    def test_brief_gesture_is_ignored(self):
        self.frames("No hand", 5)
        self.assertEqual(self.frames("Shaka", 3), 0)
        self.frames("Open_Palm", 5)
        self.assertEqual(self.frames("Shaka", 6), 1)

    def test_low_confidence_never_clicks(self):
        self.frames("No hand", 5)
        self.assertEqual(self.frames("Shaka", 30, score=0.6), 0)

    def test_detection_flicker_does_not_rearm(self):
        self.frames("No hand", 5)
        self.assertEqual(self.frames("Shaka", 6), 1)
        self.frames("No hand", 2)
        self.assertEqual(self.frames("Shaka", 30), 0)
        self.frames("Open_Palm", 5)
        self.assertEqual(self.frames("Shaka", 6), 1)

    def test_pause_and_resume_requires_release(self):
        self.frames("No hand", 5)
        self.frames("Shaka", 2)
        self.frames("Shaka", 1, enabled=False)
        self.assertEqual(self.frames("Shaka", 20), 0)
        self.frames("No hand", 5)
        self.assertEqual(self.frames("Shaka", 6), 1)

    def test_camera_stall_cannot_complete_pending_hold(self):
        self.frames("No hand", 5)
        self.frames("Shaka", 2)
        self.now += 5
        self.assertEqual(self.frames("Shaka", 20), 0)
        self.frames("No hand", 5)
        self.assertEqual(self.frames("Shaka", 6), 1)

    def test_cooldown_delays_second_click(self):
        self.gate = GestureGate(hold_seconds=0.1, release_seconds=0.1, cooldown_seconds=1)
        self.frames("No hand", 3)
        self.assertEqual(self.frames("Shaka", 3), 1)
        self.frames("No hand", 3)
        self.assertEqual(self.frames("Shaka", 3), 0)
        self.assertEqual(self.frames("Shaka", 10), 1)

    def test_lower_ranked_model_gesture_is_not_accepted(self):
        category = lambda name, score: SimpleNamespace(category_name=name, score=score)
        result = SimpleNamespace(gestures=[[category("Open_Palm", 0.9), category("Thumb_Up", 0.8)]])
        self.assertEqual(best_gesture(result), ("Open_Palm", 0.9))
        result.gestures.append([category("Thumb_Up", 0.85)])
        self.assertEqual(best_gesture(result), ("Open_Palm", 0.9))
        self.assertEqual(best_gesture(SimpleNamespace(gestures=[])), ("No hand", 0))

    def test_each_selected_gesture_triggers_once_and_ignores_other_options(self):
        for target in GESTURE_CHOICES.values():
            with self.subTest(target=target):
                self.gate = GestureGate(target_gesture=target)
                self.now = 0.0
                self.frames("No hand", 5)
                for other in GESTURE_CHOICES.values():
                    if other != target:
                        self.assertEqual(self.frames(other, 20), 0)
                self.assertEqual(self.frames(target, 30), 1)
                self.frames("No hand", 5)
                self.assertEqual(self.frames(target, 30), 1)

    def test_selected_model_gesture_on_second_hand_is_prioritized(self):
        for target in ("Thumb_Up", "Victory"):
            result = SimpleNamespace(gestures=[
                [SimpleNamespace(category_name="Open_Palm", score=0.99)],
                [SimpleNamespace(category_name=target, score=0.85)],
            ])
            self.assertEqual(best_gesture(result, target), (target, 0.85))

    def test_lower_ranked_selected_model_class_is_rejected(self):
        for target in ("Thumb_Up", "Victory"):
            result = SimpleNamespace(gestures=[[
                SimpleNamespace(category_name="Open_Palm", score=0.99),
                SimpleNamespace(category_name=target, score=0.85),
            ]])
            self.assertEqual(best_gesture(result, target), ("Open_Palm", 0.99))

    def test_invalid_gesture_is_rejected(self):
        with self.assertRaises(ValueError):
            GestureGate(target_gesture="Unknown")

    def test_camera_resume_reset_preserves_selected_gesture(self):
        from camera import CameraWorker
        for target in GESTURE_CHOICES.values():
            worker = CameraWorker(0, 0.8, target)
            worker.gate.armed = True
            worker.pause()
            worker.resume()
            worker.reset_gate()
            self.assertEqual(worker.gate.target_gesture, target)
            self.assertEqual(worker.gate.confidence, 0.8)
            self.assertFalse(worker.gate.armed)
            self.assertFalse(worker.reset_requested.is_set())


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

    def test_callable_window_handle_opens_and_clicks(self):
        self.show.HWND = Mock(return_value=10)
        controller = PowerPointController(self.presentation, self.show, self.desktop)
        self.assertEqual(controller.hwnd, 10)
        self.assertTrue(controller.try_click()[0])
        self.assertEqual(self.show.HWND.call_count, 2)
        self.desktop.left_click.assert_called_once_with()

    def test_changed_callable_window_handle_blocks_click(self):
        self.show.HWND = Mock(return_value=99)
        self.assert_skipped()

    def test_restricted_com_handle_uses_native_window(self):
        error = RuntimeError("Member not found")
        error.hresult = -2147352573
        self.show.HWND = Mock(side_effect=error)
        self.desktop.slideshow_handle.return_value = 10
        controller = PowerPointController(self.presentation, self.show, self.desktop)
        self.assertEqual(controller.hwnd, 10)
        self.desktop.slideshow_handle.assert_called_once_with(self.show, activate=True)
        self.assertTrue(controller.try_click()[0])
        self.desktop.slideshow_handle.assert_called_with(self.show, activate=False)

    def test_native_handle_change_blocks_click(self):
        error = RuntimeError("Member not found")
        error.hresult = -2147352573
        self.show.HWND = Mock(side_effect=error)
        self.desktop.slideshow_handle.return_value = 99
        self.assert_skipped()

    def test_unrelated_com_error_is_not_hidden(self):
        error = RuntimeError("PowerPoint disconnected")
        error.hresult = -2147417848
        self.show.HWND = Mock(side_effect=error)
        with self.assertRaisesRegex(RuntimeError, "disconnected"):
            PowerPointController(self.presentation, self.show, self.desktop)
        self.desktop.slideshow_handle.assert_not_called()

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

    def test_next_slide_works_with_preview_focused_and_cursor_outside(self):
        self.show.View = SimpleNamespace(Next=Mock())
        self.desktop.foreground.return_value = 99
        self.desktop.cursor_window.return_value = 99
        self.assertTrue(self.controller.try_next_slide()[0])
        self.show.View.Next.assert_called_once_with()
        self.desktop.left_click.assert_not_called()

    def test_next_slide_rejects_another_presentation(self):
        self.show.View = SimpleNamespace(Next=Mock())
        self.show.Presentation = SimpleNamespace(FullName=str(Path("other.pptx").resolve()))
        self.assertFalse(self.controller.try_next_slide()[0])
        self.show.View.Next.assert_not_called()

    def test_next_slide_rejects_ended_show(self):
        self.show.View = SimpleNamespace(Next=Mock())
        self.desktop.is_window.return_value = False
        self.assertFalse(self.controller.try_next_slide()[0])
        self.show.View.Next.assert_not_called()

    def test_next_slide_rejects_changed_window(self):
        self.show.View = SimpleNamespace(Next=Mock())
        self.show.HWND = 99
        self.assertFalse(self.controller.try_next_slide()[0])
        self.show.View.Next.assert_not_called()

    def test_next_slide_reports_com_failure(self):
        self.show.View = SimpleNamespace(Next=Mock(side_effect=RuntimeError("PowerPoint busy")))
        advanced, explanation = self.controller.try_next_slide()
        self.assertFalse(advanced)
        self.assertIn("PowerPoint busy", explanation)


class NativeWindowTests(unittest.TestCase):
    def setUp(self):
        self.desktop = WindowsDesktop.__new__(WindowsDesktop)
        self.desktop.slideshow_windows = Mock(return_value=[(10, "PowerPoint Slide Show - [selected.pptx]")])
        self.show = SimpleNamespace(
            Active=0, Activate=Mock(),
            Presentation=SimpleNamespace(FullName="selected.pptx"),
            Application=SimpleNamespace(SlideShowWindows=SimpleNamespace(Count=1)),
        )

    def test_binding_works_without_foreground_focus(self):
        self.assertEqual(self.desktop.slideshow_handle(self.show, activate=True), 10)
        self.show.Activate.assert_not_called()

    def test_validation_does_not_steal_focus(self):
        self.assertEqual(self.desktop.slideshow_handle(self.show), 10)
        self.show.Activate.assert_not_called()

    def test_selects_requested_deck_among_multiple_shows(self):
        self.show.Application.SlideShowWindows.Count = 2
        self.desktop.slideshow_windows.return_value.append((99, "PowerPoint Slide Show - [other.pptx]"))
        self.assertEqual(self.desktop.slideshow_handle(self.show), 10)

    def test_similarly_named_deck_is_not_matched(self):
        self.show.Application.SlideShowWindows.Count = 2
        self.desktop.slideshow_windows.return_value = [(99, "PowerPoint Slide Show - [selected-extra.pptx]")]
        with self.assertRaisesRegex(RuntimeError, "Cannot uniquely identify"):
            self.desktop.slideshow_handle(self.show)

    def test_screenshot_recovered_readonly_deck_and_presenter_view(self):
        name = "Master_Thesis_Initial_Talk_Abdelaziz_Nematallah_xx_10_26"
        self.show.Presentation.FullName = name + ".pptx"
        recovered = name + "[Auto_Recovered].pptx - Read-Only"
        self.desktop.slideshow_windows.return_value = [
            (99, recovered + " - PowerPoint Presenter View"),
            (10, "PowerPoint Slide Show - " + recovered),
        ]
        self.assertEqual(self.desktop.slideshow_handle(self.show), 10)

    def test_readonly_title_without_recovery_is_matched(self):
        self.desktop.slideshow_windows.return_value = [(10, "PowerPoint Slide Show - selected.pptx - Read-Only")]
        self.assertEqual(self.desktop.slideshow_handle(self.show), 10)

    def test_presenter_view_alone_is_never_used(self):
        self.desktop.slideshow_windows.return_value = [(99, "selected.pptx - PowerPoint Presenter View")]
        with self.assertRaisesRegex(RuntimeError, "Cannot uniquely identify"):
            self.desktop.slideshow_handle(self.show)

    def test_another_deck_alone_is_not_used(self):
        self.desktop.slideshow_windows.return_value = [(99, "PowerPoint Slide Show - other.pptx")]
        with self.assertRaisesRegex(RuntimeError, "Cannot uniquely identify"):
            self.desktop.slideshow_handle(self.show)

    def test_spaced_filename_suffix_is_not_matched(self):
        self.desktop.slideshow_windows.return_value = [(99, "PowerPoint Slide Show - selected - extra.pptx")]
        with self.assertRaisesRegex(RuntimeError, "Cannot uniquely identify"):
            self.desktop.slideshow_handle(self.show)

    def test_single_untitled_show_can_be_identified(self):
        self.desktop.slideshow_windows.return_value = [(10, "PowerPoint Slide Show")]
        self.assertEqual(self.desktop.slideshow_handle(self.show), 10)

    def test_ambiguous_windows_are_rejected(self):
        self.desktop.slideshow_windows.return_value = [(10, "PowerPoint"), (99, "PowerPoint")]
        with self.assertRaisesRegex(RuntimeError, "Cannot uniquely identify"):
            self.desktop.slideshow_handle(self.show)

    def test_delayed_window_creation_is_retried(self):
        self.desktop.slideshow_windows.side_effect = [[], [(10, "PowerPoint Slide Show - [selected.pptx]")]]
        with patch("powerpoint.time.sleep"):
            self.assertEqual(self.desktop.slideshow_handle(self.show, activate=True), 10)

    def test_child_slide_surface_is_resolved_to_parent(self):
        del self.desktop.slideshow_windows
        self.desktop.gui = Mock()
        self.desktop.api = Mock()
        self.desktop.process = Mock()
        self.desktop.gui.EnumWindows.side_effect = lambda callback, arg: callback(10, arg)
        self.desktop.gui.EnumChildWindows.side_effect = lambda hwnd, callback, arg: callback(11, arg)
        self.desktop.gui.IsWindowVisible.return_value = True
        self.desktop.gui.GetClassName.side_effect = lambda hwnd: "screenClass" if hwnd == 11 else "PodiumParent"
        self.desktop.gui.GetWindowText.return_value = "PowerPoint Slide Show - [selected.pptx]"
        self.desktop.process.GetWindowThreadProcessId.return_value = (1, 2)
        self.desktop.process.GetModuleFileNameEx.return_value = "C:/Office/POWERPNT.EXE"
        self.assertEqual(self.desktop.slideshow_handle(self.show), 10)
        self.desktop.api.CloseHandle.assert_called_once()
        self.desktop.process.GetModuleFileNameEx.return_value = "C:/Other/other.exe"
        self.assertEqual(self.desktop.slideshow_windows(), [])


if __name__ == "__main__":
    unittest.main()
