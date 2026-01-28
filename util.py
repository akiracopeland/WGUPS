# Utility helpers for time and pretty printing
from datetime import datetime, timedelta, time

def parse_deadline(s: str):
    s = (s or '').strip().upper()
    if s == 'EOD' or s == 'END OF DAY':
        return None
    try:
        # support '10:30' or '10:30 AM'
        if 'AM' in s or 'PM' in s:
            return datetime.strptime(s, '%I:%M %p').time()
        return datetime.strptime(s, '%H:%M').time()
    except:
        return None

def hhmm(t: datetime) -> str:
    return t.strftime('%H:%M')

def miles_to_minutes(miles: float, mph: float) -> int:
    return int(round((miles / mph) * 60.0))

def add_minutes(dt: datetime, mins: int) -> datetime:
    return dt + timedelta(minutes=mins)

def time_to_minutes(t: time) -> int:
    return t.hour*60 + t.minute
