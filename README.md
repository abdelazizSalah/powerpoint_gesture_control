# PowerPoint Gesture Control

Control your PowerPoint presentation with a thumbs-up.

PowerPoint Gesture Control is a standalone Windows application that uses your
webcam to recognize hand gestures and turn a deliberate thumbs-up into a left
mouse click. Choose a presentation from your computer, start its slideshow, and
control click-triggered animations, slide transitions, or buttons with either hand.

The application combines MediaPipe gesture recognition, OpenCV camera capture,
and a Tkinter interface. Recognition runs locally on your computer.

## Features

- **Local presentation picker:** choose the PowerPoint file you want to control.
- **Thumbs-up to click:** send one real left click at the current mouse position.
- **Live camera preview:** see hand landmarks, the detected gesture, and its confidence.
- **Repeat prevention:** hold the gesture without repeatedly clicking; lower your hand to rearm.
- **Presentation targeting:** clicks are sent only when the selected slideshow is active and the pointer is on it.
- **Keyboard controls:** pause/resume with F8 and stop the camera with F9.
- **Detection-only mode:** test recognition without opening PowerPoint or sending clicks.
- **Camera and confidence settings:** select your webcam and adjust the recognition threshold.
- **Automatic setup:** the launcher creates a local Python environment, installs dependencies, and downloads the model.

## Requirements

- Windows with **Microsoft PowerPoint desktop** installed.
- **64-bit Python 3.10 or newer**, including Tkinter, available through the `python` command.
- A webcam with permission to run in Windows desktop applications.
- Internet access for the initial dependency installation and gesture-model download.

An Ollama installation or AI service account is not required. Once the dependencies
and model are installed, gesture recognition can run offline.

## Quick start

1. Clone or download this repository and open its folder.
2. Double-click **Start Gesture Controller.cmd**.
3. Allow the first-run setup to finish.
4. Choose your presentation in the file picker.
5. Click **Start slideshow & camera**.

You can also launch it from PowerShell in the repository folder:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\run.ps1
```

The launcher stores dependencies in `.venv` and the downloaded model in `models`.
These generated files are excluded from Git by the included `.gitignore`.

Supported presentation formats: `.pptx`, `.ppsx`, `.ppt`, `.pps`, `.pptm`, and `.ppsm`.

## Presenting with gestures

1. Select a presentation using **Browse...**, or paste its full local path.
2. Select your camera. Camera `0` is the default; try `1` or `2` if needed.
3. Click **Start slideshow & camera**. The selected deck opens in PowerPoint. An
   existing slideshow for that presentation is reused when available.
4. Keep the selected slideshow in the foreground and put the mouse pointer on
   the slide. Use blank space for normal presentation advancement, or position
   the pointer over a button or hyperlink to click it.
5. Lower your hand for at least **0.30 seconds** to arm recognition.
6. Hold a clear thumbs-up for at least **0.35 seconds**. One left click is sent.
7. Lower your hand again before making the next thumbs-up.

Holding a thumbs-up continuously produces one click. A minimum **one-second
interval** also separates accepted gestures. Either hand can be used.

The application keeps the pointer in place. A gesture produces the same action
as a left mouse click at that position, so the result depends on the slide's
animations, transitions, and interactive elements.

## Controls

| Control | Action |
| --- | --- |
| **Browse...** | Choose a local presentation file. |
| **Start slideshow & camera** | Start recognition and open the selected slideshow. |
| **F8 / Pause clicks** | Pause or resume gesture actions. |
| **F9 / Stop** | Stop recognition and release the camera. |
| **Detection only (no clicks)** | Test recognition without sending mouse input. |
| **Camera** | Select the webcam by its device number. |
| **Confidence** | Set the minimum thumbs-up confidence; default `0.75`, allowed range `0.50`–`0.99`. |

F8 and F9 work while PowerPoint has focus. After resuming, lower your hand before
making another gesture. Stopping the controller leaves your presentation open.

Gestures are skipped when another application has focus or the pointer is outside
the selected slideshow. Skipped gestures are not replayed when you return.

## Test recognition first

Enable **Detection only (no clicks)** before starting. A presentation file is
optional in this mode. The preview shows the detected gesture and the count of
accepted test gestures.

Keep your entire hand visible with even lighting. Start with the default confidence
of `0.75`. Raise it if recognition triggers too easily, or lower it slightly if a
clear thumbs-up is missed. Stop the camera before changing settings.

## Troubleshooting

| Problem | What to check |
| --- | --- |
| Python cannot be found | Install 64-bit Python with Tkinter and make sure `python --version` works in PowerShell. |
| Camera will not open | Close other camera apps, try another camera number, and enable desktop-app camera access in Windows Settings. |
| A gesture is detected but no click occurs | Activate the selected slideshow and move the pointer onto its slide. Clicking the controller preview gives focus to the controller. |
| Recognition is inconsistent | Improve lighting, keep the whole hand in view, and adjust the confidence threshold. |
| PowerPoint cannot open the file | Confirm PowerPoint desktop is installed and resolve any password or Protected View prompt in PowerPoint. |
| Windows blocks clicks | Run PowerPoint and the controller at the same permission level; use normal non-administrator mode for both. |
| The slideshow has ended | Stop the controller, then start again to reopen the slideshow. |
| Setup fails | Check your internet connection and Python installation, then run the launcher again. |

With multiple monitors, use the actual slideshow window and place the pointer on
that slide. PowerPoint's presenter-notes window is a separate window.

## Project structure

```text
.
├── app.py                        # File picker, preview, settings, and controls
├── camera.py                     # Webcam capture and gesture inference worker
├── gesture.py                    # Confidence, hold, release, and cooldown logic
├── model.py                      # Gesture-model download and local cache
├── powerpoint.py                 # PowerPoint automation and Windows mouse input
├── requirements.txt              # Python dependencies
├── run.ps1                       # Setup and launch script
├── Start Gesture Controller.cmd  # Double-click launcher
├── tests/                        # Unit tests and optional vision checks
└── .gitignore
```

## Development and testing

Set up dependencies and the model without opening the application:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\run.ps1 -SetupOnly
```

Run the test suite:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s .\tests -v
```

The suite contains **16 unit tests** for gesture filtering and presentation
targeting, plus **two optional vision tests** using the real recognition model.
These tests use simulated camera input and mocked mouse operations; they do not
open your webcam or send desktop clicks.

To enable the optional vision tests, download the sample images:

```powershell
New-Item -ItemType Directory -Path .\_test_artifacts -Force | Out-Null
Invoke-WebRequest -Uri 'https://storage.googleapis.com/mediapipe-tasks/gesture_recognizer/thumbs_up.jpg' -OutFile .\_test_artifacts\thumbs_up.jpg
Invoke-WebRequest -Uri 'https://storage.googleapis.com/mediapipe-tasks/gesture_recognizer/thumbs_down.jpg' -OutFile .\_test_artifacts\thumbs_down.jpg
```

Rerun the suite after downloading the images. The vision tests are skipped when
the model or sample images are unavailable. Use detection-only mode and a practice
presentation to check live operation with your own webcam and PowerPoint setup.

Camera inference runs in a worker thread. Tkinter updates and PowerPoint COM
operations run on the main thread. Stale gesture events are discarded, and camera
stalls reset pending gesture holds.

## Built with

- [MediaPipe Gesture Recognizer](https://developers.google.com/edge/mediapipe/solutions/vision/gesture_recognizer/python) — pretrained hand-gesture recognition.
- [OpenCV](https://opencv.org/) — webcam capture and image processing.
- [Tkinter](https://docs.python.org/3/library/tkinter.html) and [Pillow](https://python-pillow.github.io/) — desktop interface and preview rendering.
- [pywin32](https://github.com/mhammond/pywin32) — access to PowerPoint's COM automation interface.
- [Windows SendInput](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput) — left mouse-button events.
