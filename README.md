# PowerPoint Gesture Control

Control your PowerPoint presentation with a gesture you choose from the **Gesture** dropdown:

- **Thumbs-up:** thumb upward, with the other fingers folded.
- **Shaka** (default): thumb and little finger extended, with the other three fingers folded.
- **Victory (V sign):** index and middle fingers extended in a V, with the other fingers folded.

Only the selected gesture triggers an action. Stop the camera before changing it,
then start again. Your choice is kept when pausing and resuming.

PowerPoint Gesture Control is a standalone Windows application that uses your
webcam to recognize hand gestures and turn the selected pose into a next-slide
command. Choose a presentation from your computer, start its slideshow, and
advance it with either hand. An optional mouse-click mode controls animations and buttons.

The application combines MediaPipe gesture recognition, OpenCV camera capture,
and a Tkinter interface. Recognition runs locally on your computer.
Thumbs-up and Victory use MediaPipe's pretrained gesture classifier.
Shaka recognition uses joint angles and distance ratios from MediaPipe hand
landmarks. Its displayed match score measures pose geometry rather than a trained
classifier probability. Keep your palm visible to the camera.

## Features

- **Local presentation picker:** choose the PowerPoint file you want to control.
- **Gesture selection:** choose Thumbs-up, Shaka, or Victory (V sign).
- **Gesture to advance:** advance the selected deck directly, regardless of mouse position or which window has focus.
- **Optional mouse click:** send one real left click at the current mouse position.
- **Live camera preview:** see hand landmarks, the detected gesture, and its match score.
- **Repeat prevention:** hold the gesture without repeatedly clicking; lower your hand to rearm.
- **Presentation targeting:** next-slide commands target only the selected show; mouse clicks require slideshow focus and the pointer on it.
- **Keyboard controls:** pause/resume with F8 and stop the camera with F9.
- **Detection-only mode:** test recognition without opening PowerPoint or sending clicks.
- **Camera and threshold settings:** select your webcam and adjust the minimum pose match.
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
4. Choose a pose from **Gesture**, then leave **Action** set to **Next slide** (the default). You can keep
   the controller preview or PowerPoint Presenter View focused. Mouse position does not matter.
5. Lower your hand for at least **0.30 seconds** to arm recognition.
6. Hold the selected gesture clearly for at least **0.35 seconds**. One next-slide command is sent.
7. Lower your hand again before making the next gesture.

Holding the selected gesture continuously produces one action. A minimum **one-second
interval** also separates accepted gestures. Either hand can be used.

Next slide uses PowerPoint's `SlideShowView.Next` command to display the following
slide. On the final slide it may end the slideshow (or restart it in kiosk mode).
It does not click buttons or step through click-triggered animations.

For animations or slide buttons, stop the camera and choose **Mouse click**.
Keep the selected slideshow in the foreground and the pointer on its slide.
The app keeps the pointer in place and sends a normal left click, so the result
depends on the slide's animations, transitions, and interactive elements.

## Controls

| Control | Action |
| --- | --- |
| **Browse...** | Choose a local presentation file. |
| **Start slideshow & camera** | Start recognition and open the selected slideshow. |
| **Gesture** | Choose Thumbs-up, Shaka (default), or Victory (V sign) before starting. |
| **Action** | Choose Next slide (default) or Mouse click before starting. |
| **F8 / Pause actions** | Pause or resume gesture actions. |
| **F9 / Stop** | Stop recognition and release the camera. |
| **Detection only (no actions)** | Test recognition without controlling PowerPoint. |
| **Camera** | Select the webcam by its device number. |
| **Match threshold** | Set the minimum model confidence (Thumbs-up/Victory) or pose match score (Shaka); default `0.75`, allowed range `0.50`–`0.99`. |

F8 and F9 work while PowerPoint has focus. After resuming, lower your hand before
making another gesture. Stopping the controller leaves your presentation open.

In Mouse click mode, gestures are skipped when another application has focus or
the pointer is outside the selected slideshow. Next slide mode can advance the
selected show while another window has focus. Pause with F8 when you want to work
in another app without advancing the presentation. Skipped gestures are never replayed.

## Test recognition first

Enable **Detection only (no actions)** before starting. A presentation file is
optional in this mode. The preview shows the detected gesture and the count of
accepted test gestures.

Keep your entire hand visible with even lighting. Start with the default match threshold
of `0.75`. Raise it if recognition triggers too easily, or lower it slightly if a
clear selected gesture is missed. Stop the camera before changing settings.

## Troubleshooting

| Problem | What to check |
| --- | --- |
| Python cannot be found | Install 64-bit Python with Tkinter and make sure `python --version` works in PowerShell. |
| Camera will not open | Close other camera apps, try another camera number, and enable desktop-app camera access in Windows Settings. |
| Hand landmarks appear but no action occurs | Check which Gesture is selected, the detected name and score, then lower your hand to arm and hold that pose for 0.35 seconds. Check that detection-only mode and pause are off. |
| A gesture is accepted but no slide advances | Choose Next slide before starting and check the status message. In Mouse click mode, focus the slideshow and put the pointer on it; a click may run an animation instead of changing slides. |
| Recognition is inconsistent | Improve lighting, keep the whole hand in view, and adjust the match threshold. |
| PowerPoint cannot open the file | Confirm PowerPoint desktop is installed and resolve any password or Protected View prompt in PowerPoint. |
| Windows blocks clicks | Run PowerPoint and the controller at the same permission level; use normal non-administrator mode for both. |
| The slideshow has ended | Stop the controller, then start again to reopen the slideshow. |
| Setup fails | Check your internet connection and Python installation, then run the launcher again. |

With multiple monitors, Next slide works while Presenter View is focused.
Mouse click mode requires the actual slideshow window and the pointer on that slide.

## Project structure

```text
.
├── app.py                        # File picker, preview, settings, and controls
├── camera.py                     # Webcam capture and gesture inference worker
├── gesture.py                    # Confidence, hold, release, and cooldown logic
├── model.py                      # Gesture-model download and local cache
├── powerpoint.py                 # Next-slide commands and Windows mouse input
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

The suite tests gesture filtering, application action dispatch, and presentation
targeting, plus optional vision tests using the real recognition model.
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
- [SlideShowView.Next](https://learn.microsoft.com/en-us/office/vba/api/powerpoint.slideshowview.next) — direct next-slide commands.
- [Windows SendInput](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput) — left mouse-button events.
