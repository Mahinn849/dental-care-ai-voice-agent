"""
CareVoice AI - Text-to-Speech Formatting Utilities
Converts ISO dates, military times, and technical strings into natural, human-sounding English
so ElevenLabs and TTS engines pronounce dates and times accurately without robotic glitches
(e.g., "11:00 AM" -> "11 AM", "2026-09-22" -> "September 22nd", "14:00" -> "2 PM").
"""

import re

MONTHS = {
    1: "January", 2: "February", 3: "March", 4: "April",
    5: "May", 6: "June", 7: "July", 8: "August",
    9: "September", 10: "October", 11: "November", 12: "December"
}

def _ordinal(n: int) -> str:
    """Returns ordinal string for an integer, e.g. 1 -> '1st', 22 -> '22nd'."""
    if 11 <= (n % 100) <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"

def clean_text_for_speech(text: str) -> str:
    """
    Transforms text to ensure natural spoken pronunciation for ElevenLabs:
    - 2026-09-22 -> September 22nd
    - September 22 -> September 22nd
    - 11:00 AM -> 11 AM
    - 09:00 AM -> 9 AM
    - 09:30 AM -> 9:30 AM
    - 11:00 -> 11 AM
    - 14:00 -> 2 PM
    """
    if not text:
        return text

    # 1. Convert ISO dates: 2026-09-22 or 2026/09/22 -> September 22nd
    def replace_iso_date(match):
        year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
        month_name = MONTHS.get(month, "")
        if month_name:
            return f"{month_name} {_ordinal(day)}"
        return match.group(0)

    text = re.sub(r'\b(\d{4})[-/](0?[1-9]|1[0-2])[-/](0?[1-9]|[12]\d|3[01])\b', replace_iso_date, text)

    # 2. Convert Month Day without ordinal (e.g. "September 22" -> "September 22nd")
    months_pattern = r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})\b(?!\s*(?:st|nd|rd|th))'
    def replace_month_day(match):
        month = match.group(1)
        day = int(match.group(2))
        if 1 <= day <= 31:
            return f"{month} {_ordinal(day)}"
        return match.group(0)

    text = re.sub(months_pattern, replace_month_day, text, flags=re.IGNORECASE)

    # 3. Convert on-the-hour times with AM/PM (e.g. "2:00 PM", "2:00 Pm", "02:00 PM", "11:00 AM", "2:00pm") -> "2 PM", "11 AM"
    def replace_hour_ampm(match):
        h = int(match.group(1))
        ampm_raw = match.group(2).lower()
        ampm = "AM" if "a" in ampm_raw else "PM"
        disp_h = h if 1 <= h <= 12 else (h - 12 if h > 12 else 12)
        return f"{disp_h} {ampm}"

    text = re.sub(
        r'\b0?([0-9]|1[0-2]|2[0-3]):00\s*(a\.?m\.?|p\.?m\.?)\b',
        replace_hour_ampm,
        text,
        flags=re.IGNORECASE
    )

    # 4. Normalize minute times with AM/PM (e.g. "09:30 AM", "6:56 Pm") -> "9:30 AM", "6:56 PM"
    def replace_minute_ampm(match):
        h = int(match.group(1))
        m = match.group(2)
        ampm_raw = match.group(3).lower()
        ampm = "AM" if "a" in ampm_raw else "PM"
        disp_h = h if 1 <= h <= 12 else (h - 12 if h > 12 else 12)
        return f"{disp_h}:{m} {ampm}"

    text = re.sub(
        r'\b0?([0-9]|1[0-2]|2[0-3]):([0-5]\d)\s*(a\.?m\.?|p\.?m\.?)\b',
        replace_minute_ampm,
        text,
        flags=re.IGNORECASE
    )

    # 5. Convert standalone 24h or bare times without AM/PM like "11:00", "14:00", "02:00", "2:00"
    def replace_standalone_time(match):
        h = int(match.group(1))
        m = match.group(2)
        if m == "00":
            if 8 <= h <= 11:
                return f"{h} AM"
            elif h == 12:
                return "12 PM"
            elif 13 <= h <= 18:
                return f"{h - 12} PM"
            elif 1 <= h <= 6:
                return f"{h} PM"
            elif h == 0:
                return "midnight"
            else:
                return f"{h} AM"
        else:
            if 8 <= h <= 11:
                return f"{h}:{m} AM"
            elif h == 12:
                return f"12:{m} PM"
            elif 13 <= h <= 18:
                return f"{h - 12}:{m} PM"
            elif 1 <= h <= 6:
                return f"{h}:{m} PM"
            else:
                return f"{h}:{m}"

    text = re.sub(
        r'\b([01]?\d|2[0-3]):([0-5]\d)\b(?!\s*(?:a\.?m\.?|p\.?m\.?))',
        replace_standalone_time,
        text,
        flags=re.IGNORECASE
    )

    return text
