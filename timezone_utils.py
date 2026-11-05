"""
Timezone utilities for converting game times to user's local timezone
"""

import re
from datetime import datetime, timezone
from typing import Optional

try:
    import pytz
    PYTZ_AVAILABLE = True
except ImportError:
    PYTZ_AVAILABLE = False

def convert_espn_time_to_local(time_str: str) -> str:
    """
    Convert ESPN time string to user's local timezone
    
    Args:
        time_str: Time string from ESPN API (e.g., "7:00 PM EDT", "8/28 - 5:30 PM EDT")
        
    Returns:
        Converted time string in user's local timezone
    """
    if not PYTZ_AVAILABLE:
        return time_str  # Return unchanged if pytz not available
        
    if not time_str or time_str in ['TBD', 'N/A', 'Unknown']:
        return time_str
    
    # Handle formats like "8/28 - 5:30 PM EDT"
    if " - " in time_str and any(tz in time_str for tz in ['EDT', 'EST', 'CDT', 'CST', 'MDT', 'MST', 'PDT', 'PST', 'ET', 'CT', 'MT', 'PT']):
        date_part, time_part = time_str.split(" - ", 1)
        converted_time = _convert_time_with_timezone(time_part.strip())
        if converted_time != time_part.strip():
            return f"{date_part} - {converted_time}"
        else:
            return time_str
    
    # Handle standalone time formats like "7:00 PM EDT"
    elif any(tz in time_str for tz in ['EDT', 'EST', 'CDT', 'CST', 'MDT', 'MST', 'PDT', 'PST', 'ET', 'CT', 'MT', 'PT']):
        converted_time = _convert_time_with_timezone(time_str)
        return converted_time
    
    # Return unchanged if no timezone info found
    return time_str

def _convert_time_with_timezone(time_str: str) -> str:
    """
    Convert a time string with timezone to local time
    
    Args:
        time_str: Time string like "7:00 PM EDT" or "5:30 PM CST"
        
    Returns:
        Time string converted to local timezone
    """
    if not PYTZ_AVAILABLE:
        return time_str  # Return unchanged if pytz not available
    # Extract timezone abbreviation
    tz_pattern = r'\s+(EDT|EST|CDT|CST|MDT|MST|PDT|PST|ET|CT|MT|PT)$'
    tz_match = re.search(tz_pattern, time_str)
    
    if not tz_match:
        return time_str
    
    tz_abbrev = tz_match.group(1)
    time_without_tz = time_str[:tz_match.start()].strip()
    
    # Map timezone abbreviations to pytz timezone names
    tz_mapping = {
        'EDT': 'US/Eastern',      # Eastern Daylight Time
        'EST': 'US/Eastern',      # Eastern Standard Time
        'CDT': 'US/Central',      # Central Daylight Time
        'CST': 'US/Central',      # Central Standard Time
        'MDT': 'US/Mountain',     # Mountain Daylight Time
        'MST': 'US/Mountain',     # Mountain Standard Time
        'PDT': 'US/Pacific',      # Pacific Daylight Time
        'PST': 'US/Pacific',      # Pacific Standard Time
        'ET': 'US/Eastern',       # Eastern Time (generic)
        'CT': 'US/Central',       # Central Time (generic)
        'MT': 'US/Mountain',      # Mountain Time (generic)
        'PT': 'US/Pacific',       # Pacific Time (generic)
    }
    
    source_tz_name = tz_mapping.get(tz_abbrev)
    if not source_tz_name:
        return time_str
    
    try:
        # Parse the time
        time_formats = ['%I:%M %p', '%I:%M%p', '%H:%M']
        parsed_time = None
        
        for fmt in time_formats:
            try:
                parsed_time = datetime.strptime(time_without_tz, fmt).time()
                break
            except ValueError:
                continue
        
        if not parsed_time:
            return time_str
        
        # Create a datetime object for today with the parsed time
        today = datetime.now().date()
        dt_with_time = datetime.combine(today, parsed_time)
        
        # Localize to the source timezone
        source_tz = pytz.timezone(source_tz_name)
        localized_dt = source_tz.localize(dt_with_time)
        
        # Convert to user's local timezone
        local_tz_name = get_user_timezone()
        local_tz = pytz.timezone(local_tz_name)
        
        local_dt = localized_dt.astimezone(local_tz)
        
        # Format back to a readable string
        formatted_time = local_dt.strftime('%I:%M %p').lstrip('0')
        
        # Get the local timezone abbreviation
        local_tz_abbrev = local_dt.strftime('%Z')
        if not local_tz_abbrev:
            # Fallback to offset if abbreviation not available
            offset = local_dt.strftime('%z')
            if offset:
                hours = int(offset[:3])
                local_tz_abbrev = f"UTC{'+' if hours >= 0 else ''}{hours}"
            else:
                local_tz_abbrev = "Local"
        
        return f"{formatted_time} {local_tz_abbrev}"
        
    except Exception as e:
        # If conversion fails, return original string
        print(f"Time conversion failed for '{time_str}': {e}")
        return time_str

def _local_offset_and_dst() -> tuple:
    """This machine's UTC offset in hours, and whether daylight saving is on."""
    import time

    offset = datetime.now().astimezone().utcoffset().total_seconds() / 3600
    return offset, bool(time.daylight and time.localtime().tm_isdst)


def _zone_for_offset(offset_hours: float, is_dst: bool) -> str:
    """The US zone with this offset, by its standard-time offset.

    Daylight saving moves a clock an hour ahead, so New York at -4 in summer is
    the -5 zone: take the hour back off. Adding it instead sent all of summer's
    Eastern and Pacific users to the US/Central default, an hour or two out.
    """
    standard_offset = offset_hours - 1 if is_dst else offset_hours
    return {
        -5: 'US/Eastern',   # EST/EDT
        -6: 'US/Central',   # CST/CDT
        -7: 'US/Mountain',  # MST/MDT
        -8: 'US/Pacific',   # PST/PDT
    }.get(int(standard_offset), 'US/Central')


def get_user_timezone() -> str:
    """
    Detect the user's local timezone
    
    Returns:
        Timezone name (e.g., 'US/Central', 'US/Eastern')
    """
    if not PYTZ_AVAILABLE:
        return 'US/Central'  # Default if pytz not available
    try:
        return _zone_for_offset(*_local_offset_and_dst())
    except Exception:
        # Fallback: try using time module
        try:
            import time
            if hasattr(time, 'tzname') and time.tzname:
                # Get current timezone name
                tz_name = time.tzname[time.daylight] if time.daylight else time.tzname[0]
                
                # Map common abbreviations to pytz timezone names
                tz_mappings = {
                    'CST': 'US/Central',
                    'CDT': 'US/Central', 
                    'EST': 'US/Eastern',
                    'EDT': 'US/Eastern',
                    'MST': 'US/Mountain',
                    'MDT': 'US/Mountain',
                    'PST': 'US/Pacific',
                    'PDT': 'US/Pacific',
                }
                
                return tz_mappings.get(tz_name, 'US/Central')
        except:
            pass
    
    # Default fallback to Central Time
    return 'US/Central'
