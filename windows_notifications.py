"""
The app's spoken messages, raised as UIA notifications.

uia_notifier.py does the work: it raises each notification from a hidden child window
with its own UIA provider (a notification from UiaHostProviderFromHwnd never reaches a
screen reader). Until the app has handed over that window, or off Windows, a message
is quietly dropped. Nothing prints in its place: print is invisible in the windowed build.
"""

_notifier = None


def set_notifier_window(hwnd):
    """Serve notifications from this hidden window. The app calls this once at startup."""
    global _notifier
    from uia_notifier import UiaNotifier
    _notifier = UiaNotifier(hwnd, "Sports Scores announcements")


def _raise_uia_notification(message):
    """Say `message` through the screen reader, without moving focus. True if it was
    sent. Nothing listening, or no window yet, is not an error."""
    if not message or _notifier is None:
        return False
    return _notifier.notify(str(message), interrupt=False)


class WindowsNotificationHelper:
    """The same announcements, for code that holds a helper object. Every one goes
    through _raise_uia_notification; nothing here prints or beeps instead."""

    def announce(self, message):
        """
        Announce a message to screen readers.
        
        Args:
            message (str): The message to announce
        """
        _raise_uia_notification(message)

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
