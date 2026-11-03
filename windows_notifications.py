"""
Windows UIA Notification Helper for Screen Reader Accessibility

This module provides Windows UIA (User Interface Automation) notifications
for screen readers and other assistive technologies.
"""
import ctypes
import sys

_KIND_OTHER = 4
_PROCESSING_CURRENT_THEN_MOST_RECENT = 4

import sys
import platform

def announce(message):
    """Say `message` through the screen reader, without moving focus.

    Raises a UI Automation notification on the app's foreground window. True if it
    was sent. Nothing listening, or Windows older than 10 1709, is not an error."""
    if not message or sys.platform != "win32":
        return False
    try:
        core = ctypes.WinDLL("UIAutomationCore.dll")
        ole = ctypes.WinDLL("oleaut32.dll")
        user32 = ctypes.WinDLL("user32.dll")
        user32.GetForegroundWindow.restype = ctypes.c_void_p
        core.UiaHostProviderFromHwnd.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
        core.UiaHostProviderFromHwnd.restype = ctypes.c_long
        core.UiaRaiseNotificationEvent.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                                                   ctypes.c_void_p, ctypes.c_void_p]
        core.UiaRaiseNotificationEvent.restype = ctypes.c_long
        ole.SysAllocString.argtypes = [ctypes.c_wchar_p]
        ole.SysAllocString.restype = ctypes.c_void_p
        ole.SysFreeString.argtypes = [ctypes.c_void_p]
        ole.SysFreeString.restype = None

        provider = ctypes.c_void_p()
        hwnd = user32.GetForegroundWindow()
        if not hwnd or core.UiaHostProviderFromHwnd(hwnd, ctypes.byref(provider)) < 0 or not provider:
            return False
        text = ole.SysAllocString(str(message))
        activity = ole.SysAllocString("SportsScores")
        try:
            return core.UiaRaiseNotificationEvent(provider, _KIND_OTHER, _PROCESSING_CURRENT_THEN_MOST_RECENT,
                                                  text, activity) >= 0
        finally:
            ole.SysFreeString(text)
            ole.SysFreeString(activity)
            # IUnknown::Release, the third entry in the object's vtable.
            vtable = ctypes.cast(provider, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
            ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtable[2])(provider)
    except (OSError, AttributeError) as e:
        print(f"Notification error: {e}")
        return False


class WindowsNotificationHelper:
    """Helper class for Windows UIA notifications."""
    
    def __init__(self):
        """Initialize the notification helper."""
        self.enabled = False
        self._init_uia()
    
    def _init_uia(self):
        """Initialize Windows UIA if available."""
        if platform.system() != "Windows":
            print("Windows UIA notifications not available on this platform")
            return
            
        try:
            # Try to import Windows UIA components
            import ctypes
            from ctypes import wintypes
            
            # Load the required Windows libraries
            self.user32 = ctypes.windll.user32
            self.oleacc = ctypes.windll.oleacc
            
            # Define UIA notification types
            self.UIA_NOTIFICATION_KIND_ITEM_ADDED = 0
            self.UIA_NOTIFICATION_KIND_ITEM_REMOVED = 1
            self.UIA_NOTIFICATION_KIND_OTHER = 2
            
            self.UIA_NOTIFICATION_PROCESSING_IMPORT_AS_TRANSIENT = 0
            self.UIA_NOTIFICATION_PROCESSING_IMPORT_AS_PERSISTENT = 1
            self.UIA_NOTIFICATION_PROCESSING_CURRENT_THEN_MOST_RECENT = 2
            
            self.enabled = True
            
        except (ImportError, OSError, AttributeError) as e:
            print(f"Windows UIA initialization failed: {e}")
            self.enabled = False
    
    def announce(self, message):
        """
        Announce a message to screen readers.
        
        Args:
            message (str): The message to announce
        """
        announce(message)

    def announce_score_change(self, game_name, old_score, new_score):
        """
        Announce a score change.
        
        Args:
            game_name (str): Name of the game
            old_score (str): Previous score
            new_score (str): New score
        """
        message = f"Score update: {game_name} - {new_score}"
        self.announce(message)
    
    def announce_monitoring_change(self, game_name, is_monitoring):
        """
        Announce monitoring status change.
        
        Args:
            game_name (str): Name of the game
            is_monitoring (bool): Whether monitoring is now enabled
        """
        status = "enabled" if is_monitoring else "disabled"
        message = f"Monitoring {status} for {game_name}"
        self.announce(message)
    
    def announce_live_scores_status(self, game_count):
        """
        Announce Live Scores view status.
        
        Args:
            game_count (int): Number of live games
        """
        message = f"Live Scores: {game_count} live games displayed"
        self.announce(message)

# Global instance for easy access
notification_helper = WindowsNotificationHelper()

def announce(message):
    """Convenience function to announce a message."""
    notification_helper.announce(message)

def announce_score_change(game_name, old_score, new_score):
    """Convenience function to announce score changes."""
    notification_helper.announce_score_change(game_name, old_score, new_score)

def announce_monitoring_change(game_name, is_monitoring):
    """Convenience function to announce monitoring changes."""
    notification_helper.announce_monitoring_change(game_name, is_monitoring)

def announce_live_scores_status(game_count):
    """Convenience function to announce Live Scores status."""
    notification_helper.announce_live_scores_status(game_count)
