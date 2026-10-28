"""Microphone levels for the floater's 12 dots (Windows, winmm, stdlib only).

Handy keeps its audio levels inside its own process, so the floater opens the
default microphone itself, in shared mode, only while recording. It reads 12
frequency bands with the Goertzel algorithm: no numpy, ~0.2 ms per buffer.
Nothing is stored; samples are dropped as soon as the levels are computed.
"""

import array
import ctypes
import math
import threading
import time
from ctypes import wintypes

RATE = 16000
CHUNK = 512  # 32 ms
# Band centres in Hz, low to high. Speech energy sits in the first eight.
BANDS = [120, 180, 260, 370, 520, 740, 1050, 1500, 2100, 2900, 3800, 5000]
# Dot order left to right: lows in the middle, so speech lifts the centre like Aqua's.
DISPLAY = [10, 8, 6, 4, 2, 0, 1, 3, 5, 7, 9, 11]
FLOOR_DB, TOP_DB = -62.0, -22.0


class WAVEFORMATEX(ctypes.Structure):
    _fields_ = [("wFormatTag", wintypes.WORD), ("nChannels", wintypes.WORD), ("nSamplesPerSec", wintypes.DWORD),
                ("nAvgBytesPerSec", wintypes.DWORD), ("nBlockAlign", wintypes.WORD), ("wBitsPerSample", wintypes.WORD),
                ("cbSize", wintypes.WORD)]


class WAVEHDR(ctypes.Structure):
    pass


WAVEHDR._fields_ = [("lpData", ctypes.c_void_p), ("dwBufferLength", wintypes.DWORD), ("dwBytesRecorded", wintypes.DWORD),
                    ("dwUser", ctypes.c_void_p), ("dwFlags", wintypes.DWORD), ("dwLoops", wintypes.DWORD),
                    ("lpNext", ctypes.c_void_p), ("reserved", ctypes.c_void_p)]

WHDR_DONE = 1
WAVE_MAPPER = 0xFFFFFFFF

# Where Windows records which desktop app is using the microphone; the taskbar
# mic icon follows the same record. LastUsedTimeStop is 0 while the app holds it.
MIC_USERS = r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone\NonPackaged"


def mic_in_use(exe_path: str) -> bool | None:
    """True while Windows shows `exe_path` using the mic; None if Windows has no record of it."""
    import winreg

    key = MIC_USERS + "\\" + exe_path.replace("/", "\\").replace("\\", "#")
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
            return winreg.QueryValueEx(k, "LastUsedTimeStop")[0] == 0
    except OSError:
        return None


def _coeffs():
    return [2 * math.cos(2 * math.pi * f / RATE) for f in BANDS]


def band_levels(samples, coeffs=None) -> list[float]:
    """0..1 per band, in BANDS order, from 16-bit samples."""
    coeffs = coeffs or _coeffs()
    n = len(samples) or 1
    out = []
    for c in coeffs:
        s1 = s2 = 0.0
        for x in samples:
            s0 = x + c * s1 - s2
            s2, s1 = s1, s0
        power = s1 * s1 + s2 * s2 - c * s1 * s2
        amp = math.sqrt(max(power, 0.0)) * 2 / n / 32768
        db = 20 * math.log10(amp + 1e-9)
        out.append(min(1.0, max(0.0, (db - FLOOR_DB) / (TOP_DB - FLOOR_DB))))
    return out


class Keepalive:
    """Inaudible hiss (about -80 dBFS) to the default output while recording.

    Bluetooth AirPods stop sending mic audio about 2.6 s into a Handy recording
    when nothing plays to them; music, or this hiss, keeps them going (tested
    2026-10-28: 2.61 s kept without, full length with). `stop` lets it run on
    `tail_s` more so Handy's 200 ms extra buffer is covered.
    """

    tail_s = 1.5

    def __init__(self) -> None:
        self._until = 0.0
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._until = float("inf")
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="hc-keepalive", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._until = time.monotonic() + self.tail_s

    def _run(self) -> None:
        try:
            self._play()
        except Exception:
            pass  # no output device: nothing to keep alive

    def _play(self) -> None:
        import random

        winmm = ctypes.windll.winmm
        H, P, U = ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT
        winmm.waveOutOpen.argtypes = [ctypes.POINTER(ctypes.c_void_p), U, P, P, P, wintypes.DWORD]
        for name in ("waveOutPrepareHeader", "waveOutWrite", "waveOutUnprepareHeader"):
            getattr(winmm, name).argtypes = [H, P, U]
        for name in ("waveOutReset", "waveOutClose"):
            getattr(winmm, name).argtypes = [H]
        fmt = WAVEFORMATEX(1, 1, RATE, RATE * 2, 2, 16, 0)
        handle = ctypes.c_void_p()
        if winmm.waveOutOpen(ctypes.byref(handle), WAVE_MAPPER, ctypes.byref(fmt), None, None, 0) != 0:
            return
        size = RATE // 10 * 2  # 100 ms per buffer
        bufs, hdrs = [], []
        try:
            for _ in range(3):
                noise = array.array("h", (random.randint(-3, 3) for _ in range(size // 2)))
                buf = ctypes.create_string_buffer(noise.tobytes(), size)
                hdr = WAVEHDR()
                hdr.lpData = ctypes.cast(buf, ctypes.c_void_p)
                hdr.dwBufferLength = size
                winmm.waveOutPrepareHeader(handle, ctypes.byref(hdr), ctypes.sizeof(hdr))
                winmm.waveOutWrite(handle, ctypes.byref(hdr), ctypes.sizeof(hdr))
                bufs.append(buf)
                hdrs.append(hdr)
            while time.monotonic() < self._until:
                for hdr in hdrs:
                    if hdr.dwFlags & WHDR_DONE:
                        hdr.dwFlags &= ~WHDR_DONE
                        winmm.waveOutWrite(handle, ctypes.byref(hdr), ctypes.sizeof(hdr))
                time.sleep(0.02)
        finally:
            winmm.waveOutReset(handle)
            for hdr in hdrs:
                winmm.waveOutUnprepareHeader(handle, ctypes.byref(hdr), ctypes.sizeof(hdr))
            winmm.waveOutClose(handle)


class Mic:
    """Start/stop from any thread; read `levels` (display order) from any thread."""

    def __init__(self) -> None:
        self.levels = [0.0] * len(BANDS)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="hc-mic", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self.levels = [0.0] * len(BANDS)

    def _run(self) -> None:
        try:
            self._capture()
        except Exception:
            pass  # no mic, or it is busy: the dots just stay at rest
        self.levels = [0.0] * len(BANDS)

    def _capture(self) -> None:
        winmm = ctypes.windll.winmm
        H, P, U = ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT
        winmm.waveInOpen.argtypes = [ctypes.POINTER(ctypes.c_void_p), U, P, P, P, wintypes.DWORD]
        for name in ("waveInPrepareHeader", "waveInAddBuffer", "waveInUnprepareHeader"):
            getattr(winmm, name).argtypes = [H, P, U]
        for name in ("waveInStart", "waveInReset", "waveInClose"):
            getattr(winmm, name).argtypes = [H]
        fmt = WAVEFORMATEX(1, 1, RATE, RATE * 2, 2, 16, 0)
        handle = ctypes.c_void_p()
        if winmm.waveInOpen(ctypes.byref(handle), WAVE_MAPPER, ctypes.byref(fmt), None, None, 0) != 0:
            return
        bufs, hdrs = [], []
        try:
            for _ in range(4):
                buf = ctypes.create_string_buffer(CHUNK * 2)
                hdr = WAVEHDR()
                hdr.lpData = ctypes.cast(buf, ctypes.c_void_p)
                hdr.dwBufferLength = CHUNK * 2
                winmm.waveInPrepareHeader(handle, ctypes.byref(hdr), ctypes.sizeof(hdr))
                winmm.waveInAddBuffer(handle, ctypes.byref(hdr), ctypes.sizeof(hdr))
                bufs.append(buf)
                hdrs.append(hdr)
            winmm.waveInStart(handle)
            coeffs = _coeffs()
            smooth = [0.0] * len(BANDS)
            while not self._stop.is_set():
                done = False
                for buf, hdr in zip(bufs, hdrs):
                    if hdr.dwFlags & WHDR_DONE:
                        done = True
                        samples = array.array("h", buf.raw[: hdr.dwBytesRecorded])
                        raw = band_levels(samples, coeffs)
                        # Fast rise, slow fall, like a meter.
                        smooth = [r if r > s else s * 0.82 + r * 0.18 for r, s in zip(raw, smooth)]
                        self.levels = [smooth[i] for i in DISPLAY]
                        hdr.dwFlags &= ~WHDR_DONE
                        winmm.waveInAddBuffer(handle, ctypes.byref(hdr), ctypes.sizeof(hdr))
                if not done:
                    time.sleep(0.008)
        finally:
            winmm.waveInReset(handle)
            for hdr in hdrs:
                winmm.waveInUnprepareHeader(handle, ctypes.byref(hdr), ctypes.sizeof(hdr))
            winmm.waveInClose(handle)
