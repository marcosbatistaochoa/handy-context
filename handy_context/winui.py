"""Windows UI thread: the floater window and the Right Alt keyboard hook.

Both live on one thread with one message loop, because a low-level keyboard
hook is called on the thread that installed it. The hook only decides and
posts; the work (sending F13, calling Handy, starting the mic) runs from the
message loop, so the hook always returns well inside Windows' time limit.
"""

import ctypes
import subprocess
import threading
import time
from ctypes import wintypes

from . import floater as fl
from .keys import CANCEL, HOLD, LOCKED, PRESS, RELEASE, RightAlt
from .mic import Keepalive, Mic, mic_in_use

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32")
kernel32 = ctypes.WinDLL("kernel32")
shcore = ctypes.WinDLL("shcore")

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

WS_POPUP = 0x80000000
WS_EX_LAYERED, WS_EX_TRANSPARENT, WS_EX_TOPMOST = 0x80000, 0x20, 0x8
WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE = 0x80, 0x08000000
GWL_EXSTYLE = -20
WM_DESTROY, WM_TIMER, WM_LBUTTONDOWN, WM_MOUSEACTIVATE = 0x2, 0x113, 0x201, 0x21
WM_APP = 0x8000
MSG_DONE, MSG_ACTION = WM_APP + 1, WM_APP + 2
MA_NOACTIVATE = 3
WH_KEYBOARD_LL, LLKHF_INJECTED = 13, 0x10
WM_KEYDOWN, WM_SYSKEYDOWN = 0x100, 0x104
VK_RMENU, VK_SPACE, VK_ESCAPE, VK_F13 = 0xA5, 0x20, 0x1B, 0x7C
VK_LCONTROL, VK_LMENU, VK_LSHIFT, VK_RSHIFT, VK_LWIN, VK_RWIN, VK_RCONTROL = 0xA2, 0xA4, 0xA0, 0xA1, 0x5B, 0x5C, 0xA3
SWP_NOACTIVATE, SWP_NOZORDER = 0x10, 0x4
HWND_TOPMOST = -1
SW_SHOWNOACTIVATE = 4
ULW_ALPHA = 2
INPUT_KEYBOARD, KEYEVENTF_KEYUP = 1, 2
ACTIONS = [PRESS, RELEASE, CANCEL, "stop_click", "cancel_click"]


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("pad", ctypes.c_byte * 32)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH), ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("op", ctypes.c_byte), ("flags", ctypes.c_byte), ("alpha", ctypes.c_ubyte), ("fmt", ctypes.c_byte)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]


user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = LRESULT
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.HMENU,
                                   wintypes.HINSTANCE, wintypes.LPVOID]
user32.CreateWindowExW.restype = wintypes.HWND
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
user32.MonitorFromWindow.restype = wintypes.HMONITOR
user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
user32.MonitorFromPoint.restype = wintypes.HMONITOR
user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFO)]
user32.GetForegroundWindow.restype = wintypes.HWND
user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.UpdateLayeredWindow.argtypes = [wintypes.HWND, wintypes.HDC, ctypes.POINTER(wintypes.POINT), ctypes.POINTER(wintypes.SIZE),
                                       wintypes.HDC, ctypes.POINTER(wintypes.POINT), wintypes.DWORD,
                                       ctypes.POINTER(BLENDFUNCTION), wintypes.DWORD]
user32.SetTimer.argtypes = [wintypes.HWND, ctypes.c_size_t, wintypes.UINT, ctypes.c_void_p]
user32.GetDC.restype = wintypes.HDC
user32.GetDC.argtypes = [wintypes.HWND]
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.POINTER(BITMAPINFOHEADER), wintypes.UINT,
                                   ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD]
gdi32.CreateDIBSection.restype = wintypes.HBITMAP
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE


NO_WINDOW = 0x08000000
TEST_MARK = 0x48433130  # dwExtraInfo on test key events: the hook treats them as real keys


def handy_running() -> bool:
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq handy.exe", "/NH"], capture_output=True, text=True,
                         timeout=3, creationflags=NO_WINDOW).stdout
    return "handy.exe" in out.lower()


def send_key(vk: int, up: bool) -> None:
    inp = INPUT(INPUT_KEYBOARD)
    inp.u.ki = KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP if up else 0, 0, 0)
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


VK_SHIFT, VK_LEFT, VK_RIGHT = 0x10, 0x25, 0x27
KEYEVENTF_EXTENDEDKEY = 0x0001


def select_left(presses: int) -> None:
    """Shift+Left `presses` times, as one SendInput batch so nothing interleaves.

    Arrow keys carry KEYEVENTF_EXTENDEDKEY, or some apps read them as numpad keys.
    """
    events = [(VK_SHIFT, 0)]
    for _ in range(presses):
        events += [(VK_LEFT, KEYEVENTF_EXTENDEDKEY), (VK_LEFT, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP)]
    events.append((VK_SHIFT, KEYEVENTF_KEYUP))
    _send_batch(events)


def collapse_right() -> None:
    """Right arrow: drops a selection, caret at its end."""
    _send_batch([(VK_RIGHT, KEYEVENTF_EXTENDEDKEY), (VK_RIGHT, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP)])


def _send_batch(events: list[tuple[int, int]]) -> None:
    arr = (INPUT * len(events))()
    for i, (vk, flags) in enumerate(events):
        arr[i].type = INPUT_KEYBOARD
        arr[i].u.ki = KEYBDINPUT(vk, 0, flags, 0, 0)
    user32.SendInput(len(events), arr, ctypes.sizeof(INPUT))


def monitor_of_foreground():
    """(work-area RECT, scale) for the monitor the user is typing on."""
    hmon = user32.MonitorFromWindow(user32.GetForegroundWindow(), 2)  # MONITOR_DEFAULTTONEAREST
    mi = MONITORINFO()
    mi.cbSize = ctypes.sizeof(mi)
    user32.GetMonitorInfoW(hmon, ctypes.byref(mi))
    dx, dy = wintypes.UINT(), wintypes.UINT()
    if shcore.GetDpiForMonitor(hmon, 0, ctypes.byref(dx), ctypes.byref(dy)) != 0:
        dx.value = 96
    return mi.rcWork, dx.value / 96


class App:
    def __init__(self, handy_exe: str, right_alt: bool = True, show_floater: bool = True, demo: bool = False):
        self.handy_exe = handy_exe
        self.right_alt = right_alt
        self.show_floater = show_floater
        self.demo = demo
        self.on_release = None  # called when the talk key goes up (the helper reads the screen then)
        self.keys = RightAlt()
        self.floater = fl.Floater()
        self.mic = Mic()
        self.keepalive = Keepalive()
        self.finalize_until = 0.0
        self.finalize_max_s = 12.0
        # The pill stays small after the key goes down until Windows shows Handy on
        # the mic: 130 ms to 1.2 s measured (2026-10-07, longest after a quiet spell).
        self.mic_wait_since: float | None = None
        self.mic_wait_max_s = 2.0
        self.hwnd = None
        self.scale = 0.0
        self.size = (0, 0)
        self._last = time.monotonic()
        self._fast = False
        self._clickable = False
        self._dib = None
        self.dx = 0  # horizontal offset in device px (demo screenshots only)

    # ---- called from other threads ----
    def post_done(self) -> None:
        if self.hwnd:
            user32.PostMessageW(self.hwnd, MSG_DONE, 0, 0)

    # ---- setup ----
    def run(self) -> None:
        from . import gdip

        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # per-monitor v2
        gdip.startup()
        self._gdip = gdip
        hinst = kernel32.GetModuleHandleW(None)
        self._wndproc = WNDPROC(self._on_message)
        wc = WNDCLASSW(0, self._wndproc, 0, 0, hinst, None, None, None, None, "HandyContextFloater")
        user32.RegisterClassW(ctypes.byref(wc))
        ex = WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
        self.hwnd = user32.CreateWindowExW(ex, "HandyContextFloater", "handy-context", WS_POPUP,
                                           0, 0, 10, 10, None, None, hinst, None)
        self._screen_dc = user32.GetDC(None)
        self._mem_dc = gdi32.CreateCompatibleDC(self._screen_dc)
        self._place()
        if self.show_floater:
            self._render()
            user32.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
        if self.right_alt:
            self._hookproc = HOOKPROC(self._on_key)
            self._hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._hookproc, hinst, 0)
        user32.SetTimer(self.hwnd, 1, 120, None)
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def _place(self) -> None:
        work, scale = monitor_of_foreground()
        if scale != self.scale:
            self.scale = scale
            w, h = int(fl.CANVAS_W * scale), int(fl.CANVAS_H * scale)
            self.size = (w, h)
            self._make_dib(w, h)
        w, h = self.size
        x = work.left + (work.right - work.left - w) // 2 + self.dx
        pill_bottom = work.bottom - round(fl.BOTTOM_GAP * scale)
        y = pill_bottom + round(2 * scale) - h
        self.pos = (x, y)
        user32.SetWindowPos(self.hwnd, wintypes.HWND(HWND_TOPMOST), x, y, w, h, SWP_NOACTIVATE)

    def _make_dib(self, w: int, h: int) -> None:
        if self._dib:
            self._canvas.close()
            gdi32.DeleteObject(self._dib)
        bmi = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
        bits = ctypes.c_void_p()
        self._dib = gdi32.CreateDIBSection(self._mem_dc, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
        gdi32.SelectObject(self._mem_dc, self._dib)
        self._canvas = self._gdip.Canvas(bits.value, w, h)

    def _render(self) -> None:
        if not self.show_floater:
            return
        w, h = self.size
        self._canvas.clear()
        self.floater.paint(self._canvas, self.scale, w, h)
        pt, size, src = wintypes.POINT(*self.pos), wintypes.SIZE(w, h), wintypes.POINT(0, 0)
        blend = BLENDFUNCTION(0, 0, 255, 1)
        user32.UpdateLayeredWindow(self.hwnd, self._screen_dc, ctypes.byref(pt), ctypes.byref(size),
                                   self._mem_dc, ctypes.byref(src), 0, ctypes.byref(blend), ULW_ALPHA)

    # ---- state ----
    def _waiting_for_mic(self) -> bool:
        if self.mic_wait_since is None:
            return False
        if mic_in_use(self.handy_exe) is not False or time.monotonic() - self.mic_wait_since > self.mic_wait_max_s:
            self.mic_wait_since = None  # on, unknown, or waited long enough: expand
            return False
        return True

    def _visual_state(self) -> str:
        if self.keys.state in (HOLD, LOCKED) and self._waiting_for_mic():
            return fl.IDLE
        if self.keys.state == HOLD:
            return fl.HOLD
        if self.keys.state == LOCKED:
            return fl.LOCKED
        if time.monotonic() < self.finalize_until:
            return fl.FINALIZING
        if self._hovering():
            return fl.HOVER
        return fl.IDLE

    def _hovering(self) -> bool:
        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        x, y, w, h = self.floater.pill_rect(self.scale, *self.size)
        px, py = pt.x - self.pos[0], pt.y - self.pos[1]
        return x - 4 <= px <= x + w + 4 and y - 4 <= py <= y + h + 4

    def _tick(self) -> None:
        now = time.monotonic()
        dt, self._last = min(now - self._last, 0.1), now
        if not self.demo:
            self.floater.set_state(self._visual_state())
        self.floater.levels = self.mic.levels
        moving = self.floater.step(dt)
        clickable = self.floater.state == fl.LOCKED
        if clickable != self._clickable:
            self._clickable = clickable
            ex = user32.GetWindowLongPtrW(self.hwnd, GWL_EXSTYLE)
            ex = ex & ~WS_EX_TRANSPARENT if clickable else ex | WS_EX_TRANSPARENT
            user32.SetWindowLongPtrW(self.hwnd, GWL_EXSTYLE, ex)
        self._render()
        moving = moving or self.mic_wait_since is not None  # check the mic every frame while waiting
        if moving != self._fast:
            self._fast = moving
            user32.SetTimer(self.hwnd, 1, 16 if moving else 120, None)

    def _do(self, action: str) -> None:
        if action == "stop_click":
            for a in self.keys.click_stop():
                self._do(a)
            return
        if action == "cancel_click":
            for a in self.keys.click_cancel():
                self._do(a)
            return
        if action == PRESS:
            self._place()
            self.finalize_until = 0.0
            self.mic_wait_since = time.monotonic()
            self.keepalive.start()
            send_key(VK_F13, up=False)
            if self.show_floater:
                self.mic.start()
        elif action == RELEASE:
            send_key(VK_F13, up=True)
            if self.on_release:
                self.on_release()
            self.keepalive.stop()
            self.mic.stop()
            self.mic_wait_since = None
            self.finalize_until = time.monotonic() + self.finalize_max_s
        elif action == CANCEL:
            self.keepalive.stop()
            self.mic.stop()
            self.mic_wait_since = None
            self.finalize_until = 0.0
            threading.Thread(target=self._cancel_then_release, daemon=True).start()
        self._tick()

    def _cancel_then_release(self) -> None:
        # Cancel first, then let go of F13, so Handy throws the audio away instead of pasting it.
        # Only when Handy is running: started cold, `handy --cancel` would launch the app instead.
        try:
            if handy_running():
                subprocess.run([self.handy_exe, "--cancel"], timeout=3, creationflags=NO_WINDOW)
        except (OSError, subprocess.SubprocessError):
            pass
        send_key(VK_F13, up=True)

    # ---- Windows callbacks ----
    def _on_key(self, code: int, wparam: int, lparam: int) -> int:
        if code == 0:
            kb = KBDLLHOOKSTRUCT.from_address(lparam)
            if not kb.flags & LLKHF_INJECTED or kb.dwExtraInfo == TEST_MARK:
                down = wparam in (WM_KEYDOWN, WM_SYSKEYDOWN)
                vk = kb.vkCode
                if vk == VK_RMENU:
                    r = self.keys.ralt(down)
                elif vk == VK_SPACE:
                    r = self.keys.space(down)
                elif vk == VK_ESCAPE:
                    r = self.keys.escape(down)
                else:
                    r = self.keys.other(down)
                for a in r.actions:
                    user32.PostMessageW(self.hwnd, MSG_ACTION, ACTIONS.index(a), 0)
                if r.swallow:
                    if not r.actions:
                        user32.PostMessageW(self.hwnd, WM_TIMER, 1, 0)  # redraw for the locked state
                    return 1
        return user32.CallNextHookEx(None, code, wparam, lparam)

    def _on_message(self, hwnd, msg, wparam, lparam):
        if msg == WM_TIMER:
            self._tick()
            return 0
        if msg == MSG_ACTION:
            self._do(ACTIONS[wparam])
            return 0
        if msg == MSG_DONE:
            self.finalize_until = 0.0
            self._tick()
            return 0
        if msg == WM_MOUSEACTIVATE:
            return MA_NOACTIVATE
        if msg == WM_LBUTTONDOWN:
            x = ctypes.c_short(lparam & 0xFFFF).value
            hit = self.floater.hit(x, self.scale, *self.size)
            if hit:
                self._do("stop_click" if hit == "stop" else "cancel_click")
            return 0
        if msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)
