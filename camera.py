"""Run camera capture and inference off the Tk main thread."""

from queue import Empty, Queue
from threading import Event, Thread
import time

from gesture import DEFAULT_GESTURE, GestureGate, best_gesture
from model import ensure_model


CONNECTIONS = (
    (0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12), (9, 13), (13, 14), (14, 15),
    (15, 16), (13, 17), (0, 17), (17, 18), (18, 19), (19, 20),
)


class CameraWorker(Thread):
    def __init__(self, camera_index, confidence, target_gesture=DEFAULT_GESTURE):
        super().__init__(daemon=True, name="gesture-camera")
        self.camera_index = camera_index
        self.gate = GestureGate(confidence=confidence, target_gesture=target_gesture)
        self.enabled = Event()
        self.reset_requested = Event()
        self.stopping = Event()
        self.events = Queue()
        self.frames = Queue(maxsize=1)

    def stop(self):
        self.enabled.clear()
        self.stopping.set()

    def pause(self):
        self.enabled.clear()
        self.reset_requested.set()

    def resume(self):
        self.reset_requested.set()
        self.enabled.set()

    def reset_gate(self):
        self.gate = GestureGate(confidence=self.gate.confidence, target_gesture=self.gate.target_gesture)
        self.reset_requested.clear()

    def run(self):
        capture = None
        try:
            import cv2
            import mediapipe as mp
            from mediapipe.tasks.python import BaseOptions
            from mediapipe.tasks.python.vision import GestureRecognizer, GestureRecognizerOptions, RunningMode

            path = ensure_model(lambda message: self.events.put(("status", message)))
            if self.stopping.is_set():
                return
            capture = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
            if not capture.isOpened():
                capture.release()
                capture = cv2.VideoCapture(self.camera_index)
            if not capture.isOpened():
                raise RuntimeError("Cannot open the camera. Try another camera number, close other camera apps, and allow camera access in Windows Settings.")
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            options = GestureRecognizerOptions(
                base_options=BaseOptions(model_asset_buffer=path.read_bytes()),
                running_mode=RunningMode.VIDEO,
                num_hands=2,
                min_hand_detection_confidence=0.6,
                min_hand_presence_confidence=0.6,
                min_tracking_confidence=0.6,
            )
            timestamp = -1
            ready = False
            with GestureRecognizer.create_from_options(options) as recognizer:
                while not self.stopping.is_set():
                    success, frame = capture.read()
                    if not success:
                        raise RuntimeError("The camera stopped delivering frames. Reconnect it and start again.")
                    # Date-independent, strictly increasing timestamps for MediaPipe video tracking.
                    captured_at = time.monotonic()
                    timestamp = max(timestamp + 1, int(captured_at * 1000))
                    frame = cv2.flip(frame, 1)
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    result = recognizer.recognize_for_video(
                        mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), timestamp
                    )
                    name, score = best_gesture(result, self.gate.target_gesture)
                    if self.reset_requested.is_set():
                        self.reset_gate()
                    # Use capture time, so an old frame cannot produce a fresh click.
                    if self.gate.update(name, score, captured_at, self.enabled.is_set()):
                        self.events.put(("gesture", captured_at))
                    if not ready:
                        self.events.put(("ready", None))
                        ready = True

                    height, width = frame.shape[:2]
                    for landmarks in result.hand_landmarks:
                        points = [(int(point.x * width), int(point.y * height)) for point in landmarks]
                        for a, b in CONNECTIONS:
                            cv2.line(frame, points[a], points[b], (75, 210, 100), 2)
                        for point in points:
                            cv2.circle(frame, point, 4, (20, 170, 255), -1)
                    snapshot = (cv2.cvtColor(frame, cv2.COLOR_BGR2RGB), name, score, self.gate.armed)
                    try:
                        self.frames.get_nowait()
                    except Empty:
                        pass
                    self.frames.put_nowait(snapshot)
        except Exception as error:
            if not self.stopping.is_set():
                self.events.put(("error", str(error)))
        finally:
            if capture is not None:
                capture.release()
            self.events.put(("done", None))
