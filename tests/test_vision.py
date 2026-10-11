"""Optional real-model checks using Google's sample photos and a simulated camera.

No webcam is opened and no mouse input is sent. To enable these checks, place
thumbs_up.jpg and thumbs_down.jpg from Google's MediaPipe sample in _test_artifacts.
"""

from pathlib import Path
from queue import Empty
import sys
import time
import unittest
from unittest.mock import patch

TOOL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL))
from model import MODEL_PATH


@unittest.skipUnless(
    MODEL_PATH.is_file()
    and all((TOOL / "_test_artifacts" / name).is_file() for name in ("thumbs_up.jpg", "thumbs_down.jpg")),
    "Optional model/sample images are not installed",
)
class VisionTests(unittest.TestCase):
    def test_mirrored_thumbs_up_and_down(self):
        import cv2
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions
        from mediapipe.tasks.python.vision import GestureRecognizer, GestureRecognizerOptions
        from gesture import best_gesture

        options = GestureRecognizerOptions(base_options=BaseOptions(model_asset_buffer=MODEL_PATH.read_bytes()))
        with GestureRecognizer.create_from_options(options) as recognizer:
            for filename, expected in (("thumbs_up.jpg", "Thumb_Up"), ("thumbs_down.jpg", "Thumb_Down")):
                frame = cv2.imread(str(TOOL / "_test_artifacts" / filename))
                rgb = cv2.cvtColor(cv2.flip(frame, 1), cv2.COLOR_BGR2RGB)
                gesture, score = best_gesture(recognizer.recognize(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)))
                self.assertEqual(gesture, expected)
                self.assertGreaterEqual(score, 0.75)

    def test_real_video_pipeline_held_thumbs_do_not_trigger(self):
        self.check_video_pipeline("Shaka", 0)

    def test_real_video_pipeline_selected_thumbs_trigger_twice(self):
        self.check_video_pipeline("Thumb_Up", 2)

    def test_real_video_pipeline_thumbs_do_not_trigger_selected_victory(self):
        self.check_video_pipeline("Victory", 0)

    def check_video_pipeline(self, target_gesture, expected_pulses):
        import cv2
        import numpy as np
        from camera import CameraWorker

        thumb = cv2.imread(str(TOOL / "_test_artifacts" / "thumbs_up.jpg"))
        blank = np.zeros_like(thumb)
        source_frames = [blank] * 16 + [thumb] * 35 + [blank] * 16 + [thumb] * 35
        worker = CameraWorker(0, 0.75, target_gesture)

        class FakeCamera:
            index = 0
            released = False

            def isOpened(self):
                return True

            def set(self, *args):
                return True

            def read(self):
                time.sleep(0.03)
                if self.index == len(source_frames):
                    worker.stop()
                    return False, None
                frame = source_frames[self.index].copy()
                self.index += 1
                return True, frame

            def release(self):
                self.released = True

        fake_camera = FakeCamera()
        pulses = 0
        errors = []
        with patch.object(cv2, "VideoCapture", return_value=fake_camera):
            worker.start()
            try:
                while True:
                    kind, value = worker.events.get(timeout=15)
                    if kind == "ready":
                        worker.resume()
                    elif kind == "gesture":
                        pulses += 1
                    elif kind == "error":
                        errors.append(value)
                    elif kind == "done":
                        break
            except Empty:
                self.fail("Video inference worker did not finish")
            finally:
                worker.stop()
                worker.join(timeout=2)
        self.assertFalse(worker.is_alive())
        self.assertTrue(fake_camera.released)
        self.assertEqual(errors, [])
        self.assertEqual(pulses, expected_pulses, "Only the selected gesture may trigger the controller")
