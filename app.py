"""Standalone Windows GUI: pick a deck and the gesture used to control it."""

import ctypes
from pathlib import Path
from queue import Empty
import sys
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from camera import CameraWorker
from gesture import DEFAULT_GESTURE, GESTURE_CHOICES, GESTURE_HINTS, gesture_label
from powerpoint import PowerPointController


PRESENTATION_EXTENSIONS = {".pptx", ".ppsx", ".ppt", ".pps", ".pptm", ".ppsm"}
ACTION_NEXT_SLIDE = "Next slide"
ACTION_MOUSE_CLICK = "Mouse click"


class GestureApp:
    def __init__(self, root, pick_on_start=True):
        self.root = root
        self.worker = None
        self.controller = None
        self.running = False
        self.paused = False
        self.test_session = False
        self.enabled_since = float("inf")
        self.closing = False
        self.close_started = None
        self.click_count = 0
        self.session_action = ACTION_NEXT_SLIDE
        self.session_gesture = DEFAULT_GESTURE
        self.hotkey_states = {0x77: False, 0x78: False}  # F8, F9
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
        self.user32.GetAsyncKeyState.restype = ctypes.c_short

        root.title("PowerPoint Gesture Controller")
        root.geometry("760x830")
        root.minsize(700, 760)
        root.protocol("WM_DELETE_WINDOW", self.close)
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TButton", padding=(12, 8))
        style.configure("Title.TLabel", font=("Segoe UI", 19, "bold"))
        style.configure("Status.TLabel", font=("Segoe UI", 11))

        content = ttk.Frame(root, padding=20)
        content.pack(fill="both", expand=True)
        ttk.Label(content, text="Choose your gesture to advance", style="Title.TLabel").pack(anchor="w")
        ttk.Label(content, text="Choose a presentation, start its slideshow, and use your webcam.").pack(anchor="w", pady=(4, 14))

        files = ttk.LabelFrame(content, text="PowerPoint presentation", padding=10)
        files.pack(fill="x")
        self.path = tk.StringVar()
        self.path_entry = ttk.Entry(files, textvariable=self.path)
        self.path_entry.pack(side="left", fill="x", expand=True)
        self.browse_button = ttk.Button(files, text="Browse...", command=self.browse)
        self.browse_button.pack(side="right", padx=(8, 0))

        options = ttk.Frame(content)
        options.pack(fill="x", pady=12)
        ttk.Label(options, text="Camera:").pack(side="left")
        self.camera = tk.StringVar(value="0")
        self.camera_box = ttk.Spinbox(options, from_=0, to=9, textvariable=self.camera, width=4)
        self.camera_box.pack(side="left", padx=(6, 20))
        ttk.Label(options, text="Match threshold:").pack(side="left")
        self.confidence = tk.StringVar(value="0.75")
        self.confidence_box = ttk.Spinbox(options, from_=0.5, to=0.99, increment=0.05, textvariable=self.confidence, width=5)
        self.confidence_box.pack(side="left", padx=(6, 20))
        self.test_only = tk.BooleanVar(value=False)
        self.test_checkbox = ttk.Checkbutton(options, text="Detection only (no actions)", variable=self.test_only)
        self.test_checkbox.pack(side="left")

        gestures = ttk.Frame(content)
        gestures.pack(fill="x", pady=(0, 12))
        ttk.Label(gestures, text="Gesture:").pack(side="left")
        self.gesture_choice = tk.StringVar(value=gesture_label(DEFAULT_GESTURE))
        self.gesture_box = ttk.Combobox(
            gestures, textvariable=self.gesture_choice, values=tuple(GESTURE_CHOICES),
            state="readonly", width=18,
        )
        self.gesture_box.pack(side="left", padx=(8, 12))
        self.gesture_hint = tk.StringVar(value=GESTURE_HINTS[DEFAULT_GESTURE])
        ttk.Label(gestures, textvariable=self.gesture_hint, wraplength=350).pack(side="left")
        self.gesture_box.bind("<<ComboboxSelected>>", self.update_gesture_help)

        actions = ttk.Frame(content)
        actions.pack(fill="x", pady=(0, 12))
        ttk.Label(actions, text="Action:").pack(side="left")
        self.action = tk.StringVar(value=ACTION_NEXT_SLIDE)
        self.action_box = ttk.Combobox(
            actions, textvariable=self.action, values=(ACTION_NEXT_SLIDE, ACTION_MOUSE_CLICK),
            state="readonly", width=14,
        )
        self.action_box.pack(side="left", padx=(8, 12))
        ttk.Label(actions, text="Next slide works with the preview or Presenter View focused.", wraplength=390).pack(side="left")

        buttons = ttk.Frame(content)
        buttons.pack(fill="x", pady=(0, 12))
        self.start_button = ttk.Button(buttons, text="Start slideshow & camera", command=self.start)
        self.start_button.pack(side="left")
        self.pause_button = ttk.Button(buttons, text="Pause actions (F8)", command=self.toggle_pause, state="disabled")
        self.pause_button.pack(side="left", padx=8)
        self.stop_button = ttk.Button(buttons, text="Stop (F9)", command=self.stop, state="disabled")
        self.stop_button.pack(side="left")

        preview_frame = ttk.Frame(content, width=640, height=300)
        preview_frame.pack(fill="both", expand=True, pady=(0, 8))
        preview_frame.pack_propagate(False)
        self.preview = tk.Label(preview_frame, text="Camera preview appears here", bg="#18202b", fg="#dce4ee")
        self.preview.pack(fill="both", expand=True)
        self.detection = tk.StringVar(value="Gesture: waiting for camera")
        ttk.Label(content, textvariable=self.detection).pack(anchor="w")
        self.count_text = tk.StringVar(value="Actions sent: 0")
        ttk.Label(content, textvariable=self.count_text).pack(anchor="w", pady=(4, 8))
        self.status = tk.StringVar(value="Select a PowerPoint file to begin.")
        ttk.Label(content, textvariable=self.status, style="Status.TLabel", wraplength=650).pack(before=preview_frame, anchor="w", fill="x", pady=(0, 8))
        ttk.Label(
            content,
            text="Lower your hand first. Hold the selected gesture for 0.35 seconds, then lower it again.\n"
                 "Next slide advances the selected deck without needing mouse focus.\n"
                 "Mouse click requires the slide focused and the pointer on it. F8 pauses; F9 stops.",
            wraplength=650,
        ).pack(before=preview_frame, anchor="w", pady=(0, 12))
        self.root.after(30, self.poll)
        if pick_on_start:
            self.root.after(150, self.browse)

    def update_gesture_help(self, event=None):
        self.gesture_hint.set(GESTURE_HINTS[GESTURE_CHOICES[self.gesture_choice.get()]])

    def browse(self):
        path = filedialog.askopenfilename(
            parent=self.root,
            title="Choose the PowerPoint presentation to control",
            filetypes=[("PowerPoint presentations", "*.pptx *.ppsx *.ppt *.pps *.pptm *.ppsm")],
        )
        if path:
            self.path.set(path)
            self.status.set(f"Selected: {Path(path).name}")

    def set_controls(self, busy):
        state = "disabled" if busy else "normal"
        for widget in (self.start_button, self.browse_button, self.path_entry, self.camera_box, self.confidence_box, self.test_checkbox):
            widget.configure(state=state)
        self.action_box.configure(state="disabled" if busy else "readonly")
        self.gesture_box.configure(state="disabled" if busy else "readonly")
        self.stop_button.configure(state="normal" if busy else "disabled")
        self.pause_button.configure(state="normal" if self.running else "disabled")

    def start(self):
        if self.worker is not None:
            return
        self.test_session = self.test_only.get()
        self.session_action = self.action.get()
        self.selected_path = Path(self.path.get()).expanduser()
        if not self.test_session and (
            not self.path.get() or not self.selected_path.is_file()
            or self.selected_path.suffix.lower() not in PRESENTATION_EXTENSIONS
        ):
            messagebox.showerror("Choose a presentation", "Select an existing PowerPoint presentation file.", parent=self.root)
            return
        try:
            camera_index = int(self.camera.get())
            confidence = float(self.confidence.get())
            self.session_gesture = GESTURE_CHOICES[self.gesture_choice.get()]
            if camera_index < 0 or not 0.5 <= confidence <= 0.99:
                raise ValueError
        except (ValueError, KeyError):
            messagebox.showerror("Invalid settings", "Use a non-negative camera number and match threshold from 0.50 to 0.99.", parent=self.root)
            return
        self.paused = False
        self.running = False
        self.click_count = 0
        self.count_text.set("Actions sent: 0")
        self.pause_button.configure(text="Pause actions (F8)")
        self.status.set("Starting the camera and gesture recognizer...")
        self.worker = CameraWorker(camera_index, confidence, self.session_gesture)
        self.set_controls(True)
        self.worker.start()

    def camera_ready(self):
        if self.worker.stopping.is_set():
            return
        if not self.test_session:
            self.status.set("Opening the selected PowerPoint slideshow...")
            try:
                self.controller = PowerPointController.open(self.selected_path)
            except Exception as error:
                self.stop()
                self.status.set("PowerPoint could not start. Check the file and try again.")
                messagebox.showerror("PowerPoint could not start", str(error), parent=self.root)
                return
        self.running = True
        self.enabled_since = time.monotonic()
        self.worker.resume()
        self.set_controls(True)
        if self.test_session:
            self.status.set(f"Detection only: lower your hand, then show {gesture_label(self.session_gesture)}. No actions will be sent.")
        elif self.session_action == ACTION_NEXT_SLIDE:
            self.status.set(f"Ready for next slide. Lower your hand to arm, then hold {gesture_label(self.session_gesture)}. Mouse position does not matter.")
        else:
            self.status.set("Ready. Keep the slideshow active and the mouse pointer on the slide. Lower your hand to arm.")

    def toggle_pause(self):
        if not self.running or self.worker is None or self.worker.stopping.is_set():
            return
        self.paused = not self.paused
        if self.paused:
            self.worker.pause()
            self.pause_button.configure(text="Resume actions (F8)")
            self.status.set("Paused. Press F8 to resume.")
        else:
            self.enabled_since = time.monotonic()
            self.worker.resume()
            self.pause_button.configure(text="Pause actions (F8)")
            self.status.set(f"Resumed. Lower your hand before showing {gesture_label(self.session_gesture)} again.")
            if self.controller is not None:
                try:
                    self.controller.activate()
                except Exception:
                    self.status.set("Switch to the selected slideshow, then lower your hand to arm.")

    def stop(self):
        self.running = False
        self.controller = None
        if self.worker is not None:
            self.worker.stop()
        self.pause_button.configure(state="disabled")
        self.stop_button.configure(state="disabled")
        self.status.set("Stopping the camera...")

    def handle_gesture(self, captured_at):
        if (
            not self.running or self.paused or self.worker.stopping.is_set()
            or captured_at <= self.enabled_since
        ):
            return
        if time.monotonic() - captured_at > 0.5:
            self.status.set("Gesture skipped: camera processing was delayed. Lower your hand and try again.")
            return
        if self.test_session:
            self.click_count += 1
            self.count_text.set(f"Test gestures: {self.click_count} (no actions sent)")
            self.status.set(f"{gesture_label(self.session_gesture)} detected. Lower your hand before testing again.")
        elif self.controller is not None:
            if self.session_action == ACTION_NEXT_SLIDE:
                clicked, explanation = self.controller.try_next_slide()
            else:
                clicked, explanation = self.controller.try_click()
            self.status.set(explanation)
            if clicked:
                self.click_count += 1
                label = "Next slide commands sent" if self.session_action == ACTION_NEXT_SLIDE else "Clicks sent"
                self.count_text.set(f"{label}: {self.click_count}")

    def poll(self):
        for key, action in ((0x77, self.toggle_pause), (0x78, self.stop)):
            pressed = bool(self.user32.GetAsyncKeyState(key) & 0x8000)
            if pressed and not self.hotkey_states[key] and self.worker is not None:
                action()
            self.hotkey_states[key] = pressed
        worker = self.worker
        if worker is not None:
            while True:
                try:
                    kind, value = worker.events.get_nowait()
                except Empty:
                    break
                if self.closing or worker.stopping.is_set():
                    continue
                if kind == "status":
                    self.status.set(value)
                elif kind == "ready":
                    self.camera_ready()
                elif kind == "gesture":
                    self.handle_gesture(value)
                elif kind == "error":
                    self.stop()
                    self.status.set(value)
                    if not self.closing:
                        messagebox.showerror("Camera / recognition error", value, parent=self.root)
            try:
                rgb, name, score, armed = worker.frames.get_nowait()
                picture = Image.fromarray(rgb)
                picture.thumbnail(
                    (max(1, min(640, self.preview.winfo_width())), max(1, min(480, self.preview.winfo_height()))),
                    Image.Resampling.LANCZOS,
                )
                self.preview_image = ImageTk.PhotoImage(picture)
                self.preview.configure(image=self.preview_image, text="")
                if self.paused:
                    state = "Paused"
                elif not armed:
                    state = "Lower your hand to arm/rearm"
                elif name == worker.gate.target_gesture and score >= worker.gate.confidence:
                    state = "Hold the selected gesture steady for 0.35 seconds"
                else:
                    state = f"Ready for {gesture_label(worker.gate.target_gesture)}"
                score_label = "Match score" if name == "Shaka" else "Model confidence"
                self.detection.set(f"Gesture: {gesture_label(name)}  |  {score_label}: {score:.0%}  |  {state}")
            except Empty:
                pass
            if not worker.is_alive():
                self.worker = None
                self.controller = None
                self.running = False
                self.set_controls(False)
                self.preview.configure(image="", text="Camera stopped")
                self.preview_image = None
                self.detection.set("Gesture: camera stopped")
                if self.status.get() == "Stopping the camera...":
                    self.status.set("Camera stopped. The presentation stays open in PowerPoint.")
        if self.closing:
            # Remain responsive while capture releases. OS cleanup handles a stuck camera driver.
            if self.worker is None or time.monotonic() - self.close_started > 5:
                self.root.destroy()
                return
        self.root.after(30, self.poll)

    def close(self):
        if not self.closing:
            self.closing = True
            self.close_started = time.monotonic()
            self.stop()


def main():
    if sys.platform != "win32":
        raise SystemExit("This tool requires Windows and Microsoft PowerPoint desktop.")
    import pythoncom

    pythoncom.CoInitialize()
    try:
        root = tk.Tk()
        GestureApp(root)
        root.mainloop()
    finally:
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    main()
