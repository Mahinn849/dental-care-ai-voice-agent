import re

MONTHS = {
    1: "January", 2: "February", 3: "March", 4: "April",
    5: "May", 6: "June", 7: "July", 8: "August",
    9: "September", 10: "October", 11: "November", 12: "December"
}

def _ordinal(n: int) -> str:
    if 11 <= (n % 100) <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"

def clean_text_for_speech(text: str) -> str:
    """Formats dates, times, and technical strings for natural, human-sounding speech pronunciation."""
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
    months_pattern = r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})\b(?!\s*st|\s*nd|\s*rd|\s*th)'
    def replace_month_day(match):
        month = match.group(1)
        day = int(match.group(2))
        if 1 <= day <= 31:
            return f"{month} {_ordinal(day)}"
        return match.group(0)

    text = re.sub(months_pattern, replace_month_day, text, flags=re.IGNORECASE)

    # 3. Convert "11:00 AM" or "09:00 AM" -> "11 AM" or "9 AM"
    text = re.sub(r'\b0?([1-9]|1[0-2]):00\s*(AM|PM|am|pm)\b', r'\1 \2', text)

    # 4. Convert "09:30 AM" -> "9:30 AM"
    text = re.sub(r'\b0([1-9]):([0-5]\d)\s*(AM|PM|am|pm)\b', r'\1:\2 \3', text)

    # 5. Convert standalone 24h or military times like "11:00" or "09:00" or "14:00"
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

    text = re.sub(r'\b([01]?\d|2[0-3]):([0-5]\d)\b(?!\s*(?:AM|PM|am|pm))', replace_standalone_time, text)

    return text

# Test cases
samples = [
    "Your appointment is on 2026-09-22 at 11:00 AM.",
    "I have 09:00 AM, 11:00 AM, and 14:00 available.",
    "Your appointment on 2026-09-23 at 11:00 is confirmed.",
    "We have September 22 at 9:00 AM available.",
    "Alright, 11:00 works best.",
]

for s in samples:
    print(f"INPUT : {s}")
    print(f"OUTPUT: {clean_text_for_speech(s)}\n")
