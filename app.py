"""Standalone Windows GUI: pick a deck, then control it with thumbs-up gestures."""

import ctypes
from pathlib import Path
from queue import Empty
import sys
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from camera import CameraWorker
from powerpoint import PowerPointController


PRESENTATION_EXTENSIONS = {".pptx", ".ppsx", ".ppt", ".pps", ".pptm", ".ppsm"}


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
        self.hotkey_states = {0x77: False, 0x78: False}  # F8, F9
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
        self.user32.GetAsyncKeyState.restype = ctypes.c_short

        root.title("Thumbs-up PowerPoint Controller")
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
        ttk.Label(content, text="Thumbs-up to click", style="Title.TLabel").pack(anchor="w")
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
        ttk.Label(options, text="Confidence:").pack(side="left")
        self.confidence = tk.StringVar(value="0.75")
        self.confidence_box = ttk.Spinbox(options, from_=0.5, to=0.99, increment=0.05, textvariable=self.confidence, width=5)
        self.confidence_box.pack(side="left", padx=(6, 20))
        self.test_only = tk.BooleanVar(value=False)
        self.test_checkbox = ttk.Checkbutton(options, text="Detection only (no clicks)", variable=self.test_only)
        self.test_checkbox.pack(side="left")

        buttons = ttk.Frame(content)
        buttons.pack(fill="x", pady=(0, 12))
        self.start_button = ttk.Button(buttons, text="Start slideshow & camera", command=self.start)
        self.start_button.pack(side="left")
        self.pause_button = ttk.Button(buttons, text="Pause clicks (F8)", command=self.toggle_pause, state="disabled")
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
        self.count_text = tk.StringVar(value="Clicks sent: 0")
        ttk.Label(content, textvariable=self.count_text).pack(anchor="w", pady=(4, 8))
        self.status = tk.StringVar(value="Select a PowerPoint file to begin.")
        ttk.Label(content, textvariable=self.status, style="Status.TLabel", wraplength=650).pack(before=preview_frame, anchor="w", fill="x", pady=(0, 8))
        ttk.Label(
            content,
            text="Lower your hand first. Hold a thumbs-up for 0.35 seconds, then lower it again.\n"
                 "Clicks use your current mouse position. Keep the selected slideshow active\n"
                 "and the mouse pointer on the slide. F8 pauses/resumes; F9 stops the camera.",
            wraplength=650,
        ).pack(before=preview_frame, anchor="w", pady=(0, 12))
        self.root.after(30, self.poll)
        if pick_on_start:
            self.root.after(150, self.browse)

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
        self.stop_button.configure(state="normal" if busy else "disabled")
        self.pause_button.configure(state="normal" if self.running else "disabled")

    def start(self):
        if self.worker is not None:
            return
        self.test_session = self.test_only.get()
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
            if camera_index < 0 or not 0.5 <= confidence <= 0.99:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid settings", "Use a non-negative camera number and confidence from 0.50 to 0.99.", parent=self.root)
            return
        self.paused = False
        self.running = False
        self.click_count = 0
        self.count_text.set("Clicks sent: 0")
        self.pause_button.configure(text="Pause clicks (F8)")
        self.status.set("Starting the camera and gesture recognizer...")
        self.worker = CameraWorker(camera_index, confidence)
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
            self.status.set("Detection only: lower your hand, then show a thumbs-up. No clicks will be sent.")
        else:
            self.status.set("Ready. Keep the slideshow active and the mouse pointer on the slide. Lower your hand to arm.")

    def toggle_pause(self):
        if not self.running or self.worker is None or self.worker.stopping.is_set():
            return
        self.paused = not self.paused
        if self.paused:
            self.worker.pause()
            self.pause_button.configure(text="Resume clicks (F8)")
            self.status.set("Paused. Press F8 to resume.")
        else:
            self.enabled_since = time.monotonic()
            self.worker.resume()
            self.pause_button.configure(text="Pause clicks (F8)")
            self.status.set("Resumed. Lower your hand before the next thumbs-up.")
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
            or captured_at <= self.enabled_since or time.monotonic() - captured_at > 0.5
        ):
            return
        if self.test_session:
            self.click_count += 1
            self.count_text.set(f"Test gestures: {self.click_count} (no clicks sent)")
            self.status.set("Thumbs-up detected. Lower your hand before testing again.")
        elif self.controller is not None:
            clicked, explanation = self.controller.try_click()
            self.status.set(explanation)
            if clicked:
                self.click_count += 1
                self.count_text.set(f"Clicks sent: {self.click_count}")

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
                state = "Paused" if self.paused else ("Ready" if armed else "Lower your hand to rearm")
                self.detection.set(f"Gesture: {name.replace('_', ' ')}  |  Confidence: {score:.0%}  |  {state}")
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
