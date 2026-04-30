# tests/test_hustle_dedup.py
import sys, json, tempfile, os
sys.path.insert(0, ".")
from scripts.daily_hustle_scan import DedupTracker

def test_url_seen_within_90_days_is_skipped():
    td = tempfile.mkdtemp()
    tracker = DedupTracker(td)
    tracker.mark_seen("https://example.com/post1")
    assert tracker.is_new("https://example.com/post1") == False

def test_url_older_than_90_days_is_not_skipped():
    td = tempfile.mkdtemp()
    tracker = DedupTracker(td)
    # Manually add old entry
    old_entry = {"url": "https://example.com/old", "seen_date": "2025-01-01"}
    tracker._data["seen"] = [old_entry]
    tracker._save()
    assert tracker.is_new("https://example.com/old") == True

def test_new_url_is_processed():
    td = tempfile.mkdtemp()
    tracker = DedupTracker(td)
    assert tracker.is_new("https://example.com/fresh") == True
    tracker.mark_seen("https://example.com/fresh")
    assert tracker.is_new("https://example.com/fresh") == False
