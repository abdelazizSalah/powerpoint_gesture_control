"""Open one selected deck and advance its slideshow or send a real left click."""

import ctypes
from ctypes import wintypes
from pathlib import Path
import re
import time


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
        import win32process

        self.api = win32api
        self.gui = win32gui
        self.process = win32process
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

    def slideshow_windows(self):
        """Find slide surfaces, including those inside a different top-level class."""
        candidates = []

        def inspect(hwnd, unused):
            if not self.gui.IsWindowVisible(hwnd):
                return
            slide_surfaces = []
            if self.gui.GetClassName(hwnd).casefold() == "screenclass":
                slide_surfaces.append(hwnd)
            else:
                self.gui.EnumChildWindows(
                    hwnd,
                    lambda child, _: slide_surfaces.append(child)
                    if self.gui.GetClassName(child).casefold() == "screenclass" else None,
                    None,
                )
            if not slide_surfaces:
                return
            # Do not trust a title or class alone: the window must belong to PowerPoint.
            handle = None
            try:
                _, pid = self.process.GetWindowThreadProcessId(hwnd)
                handle = self.api.OpenProcess(0x0410, False, pid)
                executable = self.process.GetModuleFileNameEx(handle, 0)
                if Path(executable).name.casefold() == "powerpnt.exe":
                    candidates.append((hwnd, self.gui.GetWindowText(hwnd)))
            except Exception:
                pass  # Inaccessible windows cannot be safely used as click targets.
            finally:
                if handle is not None:
                    self.api.CloseHandle(handle)

        self.gui.EnumWindows(inspect, None)
        return candidates

    def slideshow_handle(self, show, activate=False):
        """Find the selected show independently of foreground focus."""
        path = Path(show.Presentation.FullName)
        pattern = re.compile(
            r"(?<![\w.])" + re.escape(path.stem)
            + r"(?:\[Auto_Recovered\])?(?:" + re.escape(path.suffix) + r")?"
            + r"(?=$|[\]\)]|\s+-\s+Read-Only(?:$|\s+-\s+))",
            re.IGNORECASE,
        )
        # Run() can return before PowerPoint has finished creating the slide window.
        deadline = time.monotonic() + (2.0 if activate else 0.0)
        while True:
            candidates = self.slideshow_windows()
            # Presenter View also contains screenClass child windows. It must
            # never be a click target, even when its title names the same deck.
            slide_candidates = [
                (hwnd, title) for hwnd, title in candidates
                if "powerpoint presenter view" not in title.casefold()
            ]
            matches = [hwnd for hwnd, title in slide_candidates if pattern.search(title)]
            if len(matches) == 1:
                return matches[0]
            if (
                not matches and len(slide_candidates) == 1
                and slide_candidates[0][1].strip().casefold() == "powerpoint slide show"
                and show.Application.SlideShowWindows.Count == 1
            ):
                return slide_candidates[0][0]
            if time.monotonic() >= deadline:
                details = "; ".join(title for _, title in candidates) or "no PowerPoint slide surfaces found"
                raise RuntimeError(f"Cannot uniquely identify the selected slideshow: {details}.")
            time.sleep(0.05)

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
    @staticmethod
    def window_handle(show, desktop=None, activate=False):
        try:
            # HWND is restricted in PowerPoint's type library. Some COM wrappers
            # expose a method that still fails with DISP_E_MEMBERNOTFOUND.
            handle = show.HWND
            if callable(handle):
                handle = handle()
            return int(handle) & 0xFFFFFFFF
        except Exception as error:
            missing_member = isinstance(error, AttributeError) or getattr(error, "hresult", None) in (
                -2147352573, -2147352570,  # DISP_E_MEMBERNOTFOUND, DISP_E_UNKNOWNNAME
            )
            if not missing_member or desktop is None:
                raise
            return desktop.slideshow_handle(show, activate=activate)

    def __init__(self, presentation, show, desktop):
        self.presentation = presentation
        self.show = show
        self.desktop = desktop
        self.path = Path(presentation.FullName).resolve()
        self.hwnd = desktop.root(self.window_handle(show, desktop, activate=True))

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

    def show_problem(self):
        """Validate the bound show before either action; focus is checked only for clicks."""
        if not self.desktop.is_window(self.hwnd):
            return "Slideshow ended. Stop and start again to reopen it."
        if Path(self.show.Presentation.FullName).resolve() != self.path:
            return "The selected presentation is no longer in this slideshow."
        if self.desktop.root(self.window_handle(self.show, self.desktop)) != self.hwnd:
            return "Slideshow changed. Stop and start again."
        return None

    def try_next_slide(self):
        """Advance the selected show without injecting input into the foreground app."""
        try:
            problem = self.show_problem()
            if problem:
                return False, problem
            self.show.View.Next()
            return True, "Next slide command sent. Lower your hand before the next gesture."
        except Exception as error:
            return False, f"Next slide skipped: {error}"

    def try_click(self):
        """Return (clicked, explanation). A skipped gesture is consumed, never queued."""
        try:
            problem = self.show_problem()
            if problem:
                return False, problem
            if self.desktop.foreground() != self.hwnd:
                return False, "Click skipped: switch back to the selected slideshow."
            if self.desktop.cursor_window() != self.hwnd:
                return False, "Click skipped: move the mouse pointer onto the slide."
            # Check focus again immediately before injecting mouse input.
            if self.desktop.foreground() != self.hwnd:
                return False, "Click skipped: slideshow lost focus."
            self.desktop.left_click()
            return True, "Left click sent. Lower your hand before the next gesture."
        except Exception as error:
            return False, f"Click skipped: {error}"
