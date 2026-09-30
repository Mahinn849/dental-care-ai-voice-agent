import sys
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from backend.utils.text_speech import clean_text_for_speech


def test_iso_date_normalization():
    res = clean_text_for_speech("Your appointment is on 2026-09-22 at 11:00 AM.")
    assert "September 22nd" in res
    assert "11 AM" in res
    print("PASS: test_iso_date_normalization passed.")


def test_standalone_times():
    res = clean_text_for_speech("We have openings at 09:00, 11:00, and 14:00.")
    assert "9 AM" in res
    assert "11 AM" in res
    assert "2 PM" in res
    print("PASS: test_standalone_times passed.")


def test_month_day_ordinals():
    res = clean_text_for_speech("We are open September 22 and October 5.")
    assert "September 22nd" in res
    assert "October 5th" in res
    print("PASS: test_month_day_ordinals passed.")


if __name__ == "__main__":
    test_iso_date_normalization()
    test_standalone_times()
    test_month_day_ordinals()
    print("\nALL TEXT SPEECH NORMALIZATION TESTS PASSED!")
