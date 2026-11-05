"""UI Automation notifications: how the app speaks without moving focus.

From GHManage's speech.py, where this was measured in the test VM: NVDA 2026.2 and
Narrator both speak these, from the main window and while a modal dialog has focus.
A notification raised from the stand-in provider UiaHostProviderFromHwnd gives a plain
window is never delivered. What works is a real provider served by a window of our
own: a hidden child of the main window, which answers WM_GETOBJECT with a minimal
IRawElementProviderSimple written here with ctypes. No PyQt import.
"""

from __future__ import annotations

import ctypes
import sys
import uuid
from ctypes import POINTER, byref, c_int, c_long, c_ulong, c_void_p

IS_WINDOWS = sys.platform == "win32"

# NotificationKind and NotificationProcessing (UIAutomationCore.h). NVDA
# cancels what it is saying for either MostRecent kind, and queues
# CurrentThenMostRecent behind it.
KIND_OTHER = 4
PROCESSING_IMPORTANT_MOST_RECENT = 1
PROCESSING_CURRENT_THEN_MOST_RECENT = 4
# One activity per category: a screen reader may keep only the newest
# pending notification of an activity, and a status mustn't replace a result.
ACTIVITY_PREFIX = "SportsScores."

WM_GETOBJECT = 0x003D
WM_NCDESTROY = 0x0082
UIA_ROOT_OBJECT_ID = -25
S_OK = 0
E_NOINTERFACE = c_long(0x80004002).value
PROVIDER_OPTIONS = 0x2 | 0x20  # ServerSideProvider | UseComThreading

UIA_CONTROL_TYPE = 30003
UIA_NAME = 30005
UIA_IS_CONTROL_ELEMENT = 30016
UIA_IS_CONTENT_ELEMENT = 30017
UIA_PROVIDER_DESCRIPTION = 30107
UIA_CUSTOM_CONTROL_TYPE = 50025
VT_EMPTY, VT_I4, VT_BSTR, VT_BOOL = 0, 3, 8, 11


class _GUID(ctypes.Structure):
    _fields_ = [("data", ctypes.c_ubyte * 16)]

    @classmethod
    def of(cls, text: str) -> "_GUID":
        g = cls()
        ctypes.memmove(byref(g), uuid.UUID(text).bytes_le, 16)
        return g


class _VARIANT(ctypes.Structure):
    # vt, three reserved words, then the value: 16 bytes on 32-bit, 24 on 64.
    _fields_ = [("vt", ctypes.c_ushort), ("r1", ctypes.c_ushort), ("r2", ctypes.c_ushort),
                ("r3", ctypes.c_ushort), ("value", c_void_p), ("pad", c_void_p)]


_IIDS = {bytes(_GUID.of(i).data) for i in (
    "00000000-0000-0000-C000-000000000046",   # IUnknown
    "d6dd68d1-86fd-4332-8666-9abedea2d24c",   # IRawElementProviderSimple
)}

_api = None  # the loaded functions, or False once loading failed


def _windows_api():
    """(UIAutomationCore, oleaut32, comctl32, SUBCLASSPROC), or None."""
    global _api
    if _api is None:
        _api = False
        if IS_WINDOWS:
            try:
                from ctypes import wintypes as w
                core = ctypes.WinDLL("UIAutomationCore.dll")
                ole = ctypes.WinDLL("oleaut32.dll")
                comctl = ctypes.WinDLL("comctl32.dll")
                lresult = ctypes.c_ssize_t
                # AttributeError here means Windows older than 10 1709.
                core.UiaRaiseNotificationEvent.argtypes = [c_void_p, c_int, c_int,
                                                           c_void_p, c_void_p]
                core.UiaRaiseNotificationEvent.restype = c_long
                core.UiaReturnRawElementProvider.argtypes = [w.HWND, w.WPARAM, w.LPARAM,
                                                             c_void_p]
                core.UiaReturnRawElementProvider.restype = lresult
                core.UiaHostProviderFromHwnd.argtypes = [w.HWND, POINTER(c_void_p)]
                core.UiaHostProviderFromHwnd.restype = c_long
                core.UiaDisconnectProvider.argtypes = [c_void_p]
                core.UiaDisconnectProvider.restype = c_long
                core.UiaClientsAreListening.restype = w.BOOL
                ole.SysAllocString.argtypes = [ctypes.c_wchar_p]
                ole.SysAllocString.restype = c_void_p
                ole.SysFreeString.argtypes = [c_void_p]
                ole.SysFreeString.restype = None
                subclass_proc = ctypes.WINFUNCTYPE(lresult, w.HWND, w.UINT, w.WPARAM,
                                                   w.LPARAM, ctypes.c_size_t, ctypes.c_size_t)
                comctl.SetWindowSubclass.argtypes = [w.HWND, subclass_proc, ctypes.c_size_t,
                                                     ctypes.c_size_t]
                comctl.SetWindowSubclass.restype = w.BOOL
                comctl.RemoveWindowSubclass.argtypes = [w.HWND, subclass_proc, ctypes.c_size_t]
                comctl.RemoveWindowSubclass.restype = w.BOOL
                comctl.DefSubclassProc.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
                comctl.DefSubclassProc.restype = lresult
                _api = (core, ole, comctl, subclass_proc)
            except (OSError, AttributeError):
                _api = False
    return _api or None


if IS_WINDOWS:
    _QI = ctypes.WINFUNCTYPE(c_long, c_void_p, POINTER(_GUID), POINTER(c_void_p))
    _REF = ctypes.WINFUNCTYPE(c_ulong, c_void_p)
    _OPTIONS = ctypes.WINFUNCTYPE(c_long, c_void_p, POINTER(c_int))
    _PATTERN = ctypes.WINFUNCTYPE(c_long, c_void_p, c_int, POINTER(c_void_p))
    _PROPERTY = ctypes.WINFUNCTYPE(c_long, c_void_p, c_int, POINTER(_VARIANT))
    _HOST = ctypes.WINFUNCTYPE(c_long, c_void_p, POINTER(c_void_p))


class _Provider:
    """IRawElementProviderSimple for the helper window, built by hand as a
    vtable of ctypes callbacks. Python owns its lifetime (the
    ``UiaNotifier`` keeps it), so the reference count is only reported.
    """

    def __init__(self, hwnd: int, name: str) -> None:
        self.hwnd = hwnd
        self.name = name
        self._refs = 1
        self._callbacks = [_QI(self._query), _REF(self._add_ref), _REF(self._release),
                           _OPTIONS(self._options), _PATTERN(self._pattern),
                           _PROPERTY(self._property), _HOST(self._host)]
        self._vtable = (c_void_p * 7)(*[ctypes.cast(f, c_void_p) for f in self._callbacks])
        self._object = (c_void_p * 1)(ctypes.addressof(self._vtable))
        self.pointer = ctypes.addressof(self._object)

    def _query(self, this, iid, out):
        if bytes(iid[0].data) in _IIDS:
            out[0] = self.pointer
            self._refs += 1
            return S_OK
        out[0] = None
        return E_NOINTERFACE

    def _add_ref(self, this):
        self._refs += 1
        return self._refs

    def _release(self, this):
        self._refs = max(self._refs - 1, 1)
        return self._refs

    def _options(self, this, out):
        out[0] = PROVIDER_OPTIONS
        return S_OK

    def _pattern(self, this, pattern_id, out):
        out[0] = None
        return S_OK

    def _property(self, this, property_id, out):
        v = out[0]
        v.vt = VT_EMPTY
        if property_id in (UIA_NAME, UIA_PROVIDER_DESCRIPTION):
            # The caller frees the BSTR.
            v.vt, v.value = VT_BSTR, _windows_api()[1].SysAllocString(self.name)
        elif property_id == UIA_CONTROL_TYPE:
            v.vt, v.value = VT_I4, UIA_CUSTOM_CONTROL_TYPE
        elif property_id in (UIA_IS_CONTROL_ELEMENT, UIA_IS_CONTENT_ELEMENT):
            v.vt, v.value = VT_BOOL, 0  # out of the control and content views
        return S_OK

    def _host(self, this, out):
        host = c_void_p()
        result = _windows_api()[0].UiaHostProviderFromHwnd(self.hwnd, byref(host))
        out[0] = host.value
        return result


class UiaNotifier:
    """Raises UIA notifications from a window the app sets aside for them:
    hidden, never focused, a child of the main window."""

    def __init__(self, hwnd: int, name: str = "Sports Scores announcements") -> None:
        self.hwnd = hwnd
        self.provider: _Provider | None = None
        self._retired: list[_Provider] = []
        api = _windows_api()
        if api is None or not hwnd:
            return
        core, _ole, comctl, subclass_proc = api
        provider = _Provider(hwnd, name)

        def window_proc(h, msg, wparam, lparam, _id, _data):
            if (msg == WM_GETOBJECT and c_long(lparam).value == UIA_ROOT_OBJECT_ID
                    and self.provider is not None):
                return core.UiaReturnRawElementProvider(h, wparam, lparam,
                                                        self.provider.pointer)
            if msg == WM_NCDESTROY:
                self.close()
            return comctl.DefSubclassProc(h, msg, wparam, lparam)

        self._proc = subclass_proc(window_proc)
        if comctl.SetWindowSubclass(hwnd, self._proc, 1, 0):
            self.provider = provider

    def close(self) -> None:
        """Have UIA let go of the provider, for when the window goes."""
        api = _windows_api()
        if api is None or self.provider is None:
            return
        core, _ole, comctl, _ = api
        provider, self.provider = self.provider, None
        self._retired.append(provider)  # a call from UIA may still be on its way
        core.UiaReturnRawElementProvider(self.hwnd, 0, 0, None)
        core.UiaDisconnectProvider(provider.pointer)
        comctl.RemoveWindowSubclass(self.hwnd, self._proc, 1)

    def notify(self, text: str, interrupt: bool, category: str = "result") -> bool:
        """Raise ``text`` as a notification. True if a listening client was
        sent it. ``interrupt`` cuts off what the screen reader is saying;
        otherwise it follows what is being said."""
        api = _windows_api()
        if api is None or self.provider is None or not text:
            return False
        core, ole, _, _ = api
        if not core.UiaClientsAreListening():
            return False
        message = ole.SysAllocString(text)
        activity = ole.SysAllocString(ACTIVITY_PREFIX + category)
        try:
            processing = (PROCESSING_IMPORTANT_MOST_RECENT if interrupt
                          else PROCESSING_CURRENT_THEN_MOST_RECENT)
            return core.UiaRaiseNotificationEvent(self.provider.pointer, KIND_OTHER,
                                                  processing, message, activity) >= 0
        finally:
            ole.SysFreeString(message)
            ole.SysFreeString(activity)
