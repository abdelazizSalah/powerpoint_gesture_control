"""Download Google's pretrained model once; camera frames stay on this computer."""

from pathlib import Path
import urllib.request
import zipfile


MODEL_URL = "https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/1/gesture_recognizer.task"
MODEL_PATH = Path(__file__).resolve().parent / "models" / "gesture_recognizer.task"


def ensure_model(status=lambda message: None):
    if MODEL_PATH.is_file() and zipfile.is_zipfile(MODEL_PATH):
        return MODEL_PATH
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = MODEL_PATH.with_suffix(".download")
    status("Downloading the gesture model (first run only)...")
    try:
        with urllib.request.urlopen(MODEL_URL, timeout=30) as response, temporary.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
        if not zipfile.is_zipfile(temporary):
            raise RuntimeError("The downloaded gesture model is invalid.")
        temporary.replace(MODEL_PATH)
    except Exception as error:
        temporary.unlink(missing_ok=True)
        raise RuntimeError("Could not download the gesture model. Check your internet connection and try again.") from error
    return MODEL_PATH


if __name__ == "__main__":
    print(ensure_model(print))
