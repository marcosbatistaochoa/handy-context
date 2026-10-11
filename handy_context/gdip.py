"""The little of GDI+ the floater needs, through ctypes (ships with Windows)."""

import ctypes
from ctypes import wintypes

_g = ctypes.windll.gdiplus
F = ctypes.c_float
P = ctypes.c_void_p
PARGB = 0x000E200B  # PixelFormat32bppPARGB
ANTIALIAS = 4  # SmoothingModeAntiAlias
UNIT_PIXEL = 2
CAP_ROUND = 2
PIXEL_OFFSET_HALF = 4


class PointF(ctypes.Structure):
    _fields_ = [("x", F), ("y", F)]


class _StartupInput(ctypes.Structure):
    _fields_ = [("version", ctypes.c_uint32), ("callback", P), ("no_thread", wintypes.BOOL), ("no_codecs", wintypes.BOOL)]


_SIGS = {
    "GdiplusStartup": [ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(_StartupInput), P],
    "GdipCreateBitmapFromScan0": [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, P, ctypes.POINTER(P)],
    "GdipGetImageGraphicsContext": [P, ctypes.POINTER(P)],
    "GdipDisposeImage": [P],
    "GdipDeleteGraphics": [P],
    "GdipSetSmoothingMode": [P, ctypes.c_int],
    "GdipSetPixelOffsetMode": [P, ctypes.c_int],
    "GdipGraphicsClear": [P, ctypes.c_uint32],
    "GdipCreateSolidFill": [ctypes.c_uint32, ctypes.POINTER(P)],
    "GdipCreateLineBrush": [ctypes.POINTER(PointF), ctypes.POINTER(PointF), ctypes.c_uint32, ctypes.c_uint32, ctypes.c_int, ctypes.POINTER(P)],
    "GdipDeleteBrush": [P],
    "GdipCreatePen1": [ctypes.c_uint32, F, ctypes.c_int, ctypes.POINTER(P)],
    "GdipSetPenStartCap": [P, ctypes.c_int],
    "GdipSetPenEndCap": [P, ctypes.c_int],
    "GdipDeletePen": [P],
    "GdipCreatePath": [ctypes.c_int, ctypes.POINTER(P)],
    "GdipAddPathArc": [P, F, F, F, F, F, F],
    "GdipClosePathFigure": [P],
    "GdipAddPathPath": [P, P, wintypes.BOOL],
    "GdipDeletePath": [P],
    "GdipFillPath": [P, P, P],
    "GdipDrawPath": [P, P, P],
    "GdipFillEllipse": [P, P, F, F, F, F],
    "GdipFillRectangle": [P, P, F, F, F, F],
    "GdipDrawLine": [P, P, F, F, F, F],
}
for _name, _args in _SIGS.items():
    getattr(_g, _name).argtypes = _args
    getattr(_g, _name).restype = ctypes.c_int

_token = ctypes.c_size_t()


def startup() -> None:
    if not _token.value:
        _g.GdiplusStartup(ctypes.byref(_token), ctypes.byref(_StartupInput(1, None, False, False)), None)


def argb(rgb: int, alpha: float = 1.0) -> int:
    return (int(max(0.0, min(1.0, alpha)) * 255) << 24) | (rgb & 0xFFFFFF)


class Canvas:
    """Draws into a premultiplied-ARGB buffer owned by the caller (a DIB section)."""

    def __init__(self, bits: int, width: int, height: int) -> None:
        self._bmp, self._gfx = P(), P()
        _g.GdipCreateBitmapFromScan0(width, height, width * 4, PARGB, P(bits), ctypes.byref(self._bmp))
        _g.GdipGetImageGraphicsContext(self._bmp, ctypes.byref(self._gfx))
        _g.GdipSetSmoothingMode(self._gfx, ANTIALIAS)
        _g.GdipSetPixelOffsetMode(self._gfx, PIXEL_OFFSET_HALF)  # whole coordinates land on pixel edges

    def close(self) -> None:
        _g.GdipDeleteGraphics(self._gfx)
        _g.GdipDisposeImage(self._bmp)

    def clear(self) -> None:
        _g.GdipGraphicsClear(self._gfx, 0)

    def _brush(self, color: int) -> P:
        b = P()
        _g.GdipCreateSolidFill(color, ctypes.byref(b))
        return b

    def _pill_path(self, x: float, y: float, w: float, h: float, r: float) -> P:
        path = P()
        _g.GdipCreatePath(0, ctypes.byref(path))
        r = min(r, h / 2, w / 2)
        d = 2 * r
        _g.GdipAddPathArc(path, x, y, d, d, 180, 90)
        _g.GdipAddPathArc(path, x + w - d, y, d, d, 270, 90)
        _g.GdipAddPathArc(path, x + w - d, y + h - d, d, d, 0, 90)
        _g.GdipAddPathArc(path, x, y + h - d, d, d, 90, 90)
        _g.GdipClosePathFigure(path)
        return path

    def ring(self, x, y, w, h, r, width: float, color: int) -> None:
        """A border drawn inside the rectangle, so it stays crisp on whole pixels."""
        path = self._pill_path(x, y, w, h, r)
        inner = self._pill_path(x + width, y + width, w - 2 * width, h - 2 * width, max(0.0, r - width))
        _g.GdipAddPathPath(path, inner, False)
        b = self._brush(color)
        _g.GdipFillPath(self._gfx, b, path)  # alternate fill mode: only the ring
        _g.GdipDeleteBrush(b)
        _g.GdipDeletePath(inner)
        _g.GdipDeletePath(path)

    def rounded(self, x, y, w, h, r, fill: int | None = None, stroke: int | None = None, stroke_w: float = 1.0) -> None:
        path = self._pill_path(x, y, w, h, r)
        if fill is not None:
            b = self._brush(fill)
            _g.GdipFillPath(self._gfx, b, path)
            _g.GdipDeleteBrush(b)
        if stroke is not None:
            pen = P()
            _g.GdipCreatePen1(stroke, stroke_w, UNIT_PIXEL, ctypes.byref(pen))
            _g.GdipDrawPath(self._gfx, pen, path)
            _g.GdipDeletePen(pen)
        _g.GdipDeletePath(path)

    def circle(self, cx, cy, d, color: int) -> None:
        b = self._brush(color)
        _g.GdipFillEllipse(self._gfx, b, cx - d / 2, cy - d / 2, d, d)
        _g.GdipDeleteBrush(b)

    def gradient_circle(self, cx, cy, d, left: int, right: int) -> None:
        b = P()
        p1, p2 = PointF(cx - d / 2 - 0.5, cy), PointF(cx + d / 2 + 0.5, cy)
        _g.GdipCreateLineBrush(ctypes.byref(p1), ctypes.byref(p2), left, right, 0, ctypes.byref(b))
        _g.GdipFillEllipse(self._gfx, b, cx - d / 2, cy - d / 2, d, d)
        _g.GdipDeleteBrush(b)

    def line(self, x1, y1, x2, y2, color: int, width: float, round_caps: bool = True) -> None:
        pen = P()
        _g.GdipCreatePen1(color, width, UNIT_PIXEL, ctypes.byref(pen))
        if round_caps:
            _g.GdipSetPenStartCap(pen, CAP_ROUND)
            _g.GdipSetPenEndCap(pen, CAP_ROUND)
        _g.GdipDrawLine(self._gfx, pen, x1, y1, x2, y2)
        _g.GdipDeletePen(pen)

    def rect(self, x, y, w, h, color: int) -> None:
        b = self._brush(color)
        _g.GdipFillRectangle(self._gfx, b, x, y, w, h)
        _g.GdipDeleteBrush(b)
