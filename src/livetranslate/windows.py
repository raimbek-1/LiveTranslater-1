"""Small typed wrappers around Windows APIs; no capture exclusion guarantee."""
import ctypes
import sys
from ctypes import wintypes

WDA_EXCLUDEFROMCAPTURE = 0x11


def user32():
    return ctypes.WinDLL("user32", use_last_error=True)


def display_affinity(hwnd, enabled):
    if sys.platform != "win32":
        return False, "Private Overlay доступен только в Windows"
    if enabled and sys.getwindowsversion().build < 19041:
        return False, "Для исключения из захвата требуется Windows 10 2004+"
    api = user32()
    api.SetWindowDisplayAffinity.argtypes = [wintypes.HWND, wintypes.DWORD]
    api.SetWindowDisplayAffinity.restype = wintypes.BOOL
    api.GetWindowDisplayAffinity.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    api.GetWindowDisplayAffinity.restype = wintypes.BOOL
    value = WDA_EXCLUDEFROMCAPTURE if enabled else 0
    if not api.SetWindowDisplayAffinity(hwnd, value):
        return False, f"SetWindowDisplayAffinity: ошибка {ctypes.get_last_error()}"
    actual = wintypes.DWORD()
    if not api.GetWindowDisplayAffinity(hwnd, ctypes.byref(actual)) or actual.value != value:
        return False, "Windows не подтвердил display affinity"
    return True, ("Private Overlay включён — проверьте в используемой программе захвата"
                  if enabled else "Private Overlay выключен")


class Hotkeys:
    def __init__(self, hwnd):
        self.hwnd = hwnd
        self.registered = []

    def register(self):
        if sys.platform != "win32":
            return ["Глобальные горячие клавиши доступны только в Windows"]
        api = user32()
        api.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
        api.RegisterHotKey.restype = wintypes.BOOL
        errors = []
        # Ctrl+Alt+S / O / P. MOD_NOREPEAT prevents toggling while held.
        for identifier, letter in ((1, "S"), (2, "O"), (3, "P")):
            if api.RegisterHotKey(self.hwnd, identifier, 0x4003, ord(letter)):
                self.registered.append(identifier)
            else:
                errors.append(f"Ctrl+Alt+{letter} занята или недоступна")
        return errors

    def close(self):
        if sys.platform == "win32":
            api = user32()
            api.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
            for identifier in self.registered:
                api.UnregisterHotKey(self.hwnd, identifier)
            self.registered.clear()
