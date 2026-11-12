"""Capture the game window directly (no snipping), on Windows.

Uses PrintWindow, which renders the window's own content: it works even when
other windows cover the game, and always captures the full window at its
native resolution, so no score rows are cut off by a hand-drawn selection.
"""

from __future__ import annotations

import ctypes
import logging
import sys

from PIL import Image

logger = logging.getLogger(__name__)

if sys.platform == "win32":
    import ctypes.wintypes as wt

    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    kernel32 = ctypes.windll.kernel32

    class _BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG),
            ("biPlanes", wt.WORD), ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
            ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", wt.LONG),
            ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD), ("biClrImportant", wt.DWORD),
        ]

_PW_CLIENTONLY_RENDERFULL = 1 | 2  # PW_CLIENTONLY | PW_RENDERFULLCONTENT


class CaptureError(Exception):
    pass


def _process_name(hwnd) -> str:
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    handle = kernel32.OpenProcess(0x1000, False, pid.value)  # QUERY_LIMITED_INFORMATION
    if not handle:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wt.DWORD(len(buf))
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return ""
        return buf.value.rsplit("\\", 1)[-1].lower()
    finally:
        kernel32.CloseHandle(handle)


def find_window(process_name: str):
    """Handle of the largest visible window of a process, or None."""
    if sys.platform != "win32":
        return None
    target = process_name.lower()
    found = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def callback(hwnd, _):
        if user32.IsWindowVisible(hwnd) and not user32.IsIconic(hwnd) and _process_name(hwnd) == target:
            rect = wt.RECT()
            user32.GetClientRect(hwnd, ctypes.byref(rect))
            found.append((rect.right * rect.bottom, hwnd))
        return True

    user32.EnumWindows(callback, 0)
    return max(found)[1] if found else None


def capture_window(hwnd) -> Image.Image:
    """The window's client area as an RGB image."""
    rect = wt.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rect))
    w, h = rect.right, rect.bottom
    if w <= 0 or h <= 0:
        raise CaptureError("The game window is minimized")
    hdc = user32.GetDC(hwnd)
    mdc = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    old = gdi32.SelectObject(mdc, bmp)
    try:
        if not user32.PrintWindow(hwnd, mdc, _PW_CLIENTONLY_RENDERFULL):
            raise CaptureError("Windows couldn't capture the game window")
        header = _BITMAPINFOHEADER(ctypes.sizeof(_BITMAPINFOHEADER), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
        buf = ctypes.create_string_buffer(w * h * 4)
        if not gdi32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(header), 0):
            raise CaptureError("Windows couldn't read the captured image")
        return Image.frombuffer("RGB", (w, h), buf, "raw", "BGRX", 0, 1).copy()
    finally:
        gdi32.SelectObject(mdc, old)
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(mdc)
        user32.ReleaseDC(hwnd, hdc)


def capture_game(process_name: str) -> Image.Image:
    """Capture the game window, or raise CaptureError with a readable message."""
    if sys.platform != "win32":
        raise CaptureError("Window capture is only available on Windows")
    hwnd = find_window(process_name)
    if hwnd is None:
        raise CaptureError(f"The game isn't running (looked for {process_name})")
    return capture_window(hwnd)
