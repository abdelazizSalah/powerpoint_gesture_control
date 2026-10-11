"""Open one selected deck and send a real left click to its active slideshow."""

import ctypes
from ctypes import wintypes
from pathlib import Path


class MouseInput(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG), ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t),
    ]


class KeyboardInput(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class HardwareInput(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class InputUnion(ctypes.Union):
    _fields_ = [("mi", MouseInput), ("ki", KeyboardInput), ("hi", HardwareInput)]


class Input(ctypes.Structure):
    _anonymous_ = ("data",)
    _fields_ = [("type", wintypes.DWORD), ("data", InputUnion)]


class WindowsDesktop:
    def __init__(self):
        import win32api
        import win32gui

        self.api = win32api
        self.gui = win32gui
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(Input), ctypes.c_int)
        self.user32.SendInput.restype = wintypes.UINT

    def root(self, hwnd):
        return self.gui.GetAncestor(hwnd, 2)  # GA_ROOT

    def foreground(self):
        return self.root(self.gui.GetForegroundWindow())

    def cursor_window(self):
        return self.root(self.gui.WindowFromPoint(self.api.GetCursorPos()))

    def is_window(self, hwnd):
        return bool(self.gui.IsWindow(hwnd))

    def left_click(self):
        # Keep the cursor in place: this is the same left click as using the mouse.
        inputs = (Input * 2)(
            Input(type=0, mi=MouseInput(dwFlags=0x0002)),  # LEFTDOWN
            Input(type=0, mi=MouseInput(dwFlags=0x0004)),  # LEFTUP
        )
        sent = self.user32.SendInput(2, inputs, ctypes.sizeof(Input))
        if sent != 2:
            # A partial injection must not leave the left button held down.
            if sent == 1:
                self.user32.SendInput(1, ctypes.byref(inputs[1]), ctypes.sizeof(Input))
            raise RuntimeError("Windows could not send the mouse click. Run PowerPoint and this tool at the same permission level.")


class PowerPointController:
    def __init__(self, presentation, show, desktop):
        self.presentation = presentation
        self.show = show
        self.desktop = desktop
        self.path = Path(presentation.FullName).resolve()
        # PowerPoint exposes HWND as a hidden member of SlideShowWindow.
        self.hwnd = desktop.root(int(show.HWND) & 0xFFFFFFFF)

    @classmethod
    def open(cls, path: Path):
        import pywintypes
        import win32com.client

        try:
            application = win32com.client.GetActiveObject("PowerPoint.Application")
        except pywintypes.com_error:
            try:
                application = win32com.client.Dispatch("PowerPoint.Application")
            except pywintypes.com_error as error:
                raise RuntimeError("Microsoft PowerPoint desktop must be installed on this Windows computer.") from error
        application.Visible = -1
        presentation = None
        for index in range(1, application.Presentations.Count + 1):
            candidate = application.Presentations.Item(index)
            if Path(candidate.FullName).resolve() == path.resolve():
                presentation = candidate
                break
        if presentation is None:
            presentation = application.Presentations.Open(str(path.resolve()), -1, 0, -1)

        # Reuse a show of this deck when one is already running.
        show = None
        for index in range(1, application.SlideShowWindows.Count + 1):
            candidate = application.SlideShowWindows.Item(index)
            if Path(candidate.Presentation.FullName).resolve() == path.resolve():
                show = candidate
                break
        if show is None:
            show = presentation.SlideShowSettings.Run()
        controller = cls(presentation, show, WindowsDesktop())
        controller.activate()
        return controller

    def activate(self):
        self.show.Activate()

    def try_click(self):
        """Return (clicked, explanation). A skipped gesture is consumed, never queued."""
        try:
            if not self.desktop.is_window(self.hwnd):
                return False, "Slideshow ended. Stop and start again to reopen it."
            if Path(self.show.Presentation.FullName).resolve() != self.path:
                return False, "The selected presentation is no longer in this slideshow."
            if self.desktop.root(int(self.show.HWND) & 0xFFFFFFFF) != self.hwnd:
                return False, "Slideshow changed. Stop and start again."
            if self.desktop.foreground() != self.hwnd:
                return False, "Click skipped: switch back to the selected slideshow."
            if self.desktop.cursor_window() != self.hwnd:
                return False, "Click skipped: move the mouse pointer onto the slide."
            # Check focus again immediately before injecting mouse input.
            if self.desktop.foreground() != self.hwnd:
                return False, "Click skipped: slideshow lost focus."
            self.desktop.left_click()
            return True, "Left click sent. Lower your hand before the next thumbs-up."
        except Exception as error:
            return False, f"Click skipped: {error}"
