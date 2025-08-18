#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import csv
import sys
import unicodedata
from pathlib import Path

# Match dates like "5 Aug, 2025"
DATE_RE = re.compile(r"\b(\d{1,2})\s+([A-Za-z]{3}),\s+(\d{4})\b")

MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12
}

# Remove these tokens anywhere in a line (case-insensitive)
REMOVE_PATTERNS = [
    r"\bband\s+twitter\b",
    r"\blabel\s+website\b",
    r"\bband\s+website\b",
    r"\bwebsite\b",
]
REMOVE_RE = re.compile("|".join(f"(?:{p})" for p in REMOVE_PATTERNS), re.IGNORECASE)

def looks_like_header(line: str) -> bool:
    s = line.strip()
    if not s:
        return True
    if s in {"$", "&"}:
        return True
    if len(s) == 1 and (s.isalpha() or s.isdigit()):
        return True
    return False

def normalize_unicode(s: str) -> str:
    # Normalize to NFC so accented chars render correctly in Excel
    return unicodedata.normalize("NFC", s)

def sanitize_line(line: str) -> str:
    """Remove 'website'/'band twitter' mentions and tidy separators."""
    s = REMOVE_RE.sub("", line)
    # Normalize separators and whitespace
    s = re.sub(r"\s*[|]\s*", " - ", s)   # convert pipes to ' - '
    s = re.sub(r"\s+-\s+", " - ", s)     # tidy dash spacing
    s = re.sub(r"\s{2,}", " ", s)        # collapse multiple spaces
    s = s.strip(" -|, \t")
    return s

def clean_field(s: str) -> str:
    s = re.sub(r"\s+", " ", s.strip())
    return s.strip(" -|,")

def format_date(date_str: str) -> str:
    """Convert '5 Aug, 2025' → '2025-08-05'."""
    m = DATE_RE.search(date_str)
    if not m:
        return ""
    day, mon, year = m.groups()
    day = int(day)
    mon = MONTHS.get(mon, 0)
    year = int(year)
    if not mon:
        return ""
    return f"{year:04d}-{mon:02d}-{day:02d}"

def parse_line(line: str):
    # Find the last date in the line
    m = list(DATE_RE.finditer(line))
    if not m:
        return None
    date_raw = m[-1].group(0)
    date_fmt = format_date(date_raw)

    # Expect "Artist - Album - Label - Date"
    parts = line.split(" - ")
    if len(parts) < 2:
        return None

    artist = clean_field(parts[0])
    album = clean_field(parts[1])

    if not artist or not album or not date_fmt:
        return None
    return (artist, album, date_fmt)

def parse_text(text: str):
    rows = []
    for raw in text.splitlines():
        # Normalize early
        line = normalize_unicode(raw)

        # Skip section headers and blanks
        if looks_like_header(line):
            continue

        # Quick gate for obviously irrelevant lines
        if " - " not in line and " | " not in line:
            continue

        # Clean up mentions and separators
        line = sanitize_line(line)
        if " - " not in line:
            continue

        parsed = parse_line(line)
        if parsed:
            rows.append(parsed)
    return rows

def main():
    try:
        filepath = input("Enter the path to your releases text file: ").strip()
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(1)

    infile = Path(filepath)
    if not infile.exists():
        print("File not found:", infile)
        sys.exit(1)

    outfile = infile.with_suffix(".csv")

    text = infile.read_text(encoding="utf-8", errors="ignore")
    text = normalize_unicode(text)

    rows = parse_text(text)
    if not rows:
        print("No valid releases found. Check formatting / dates.")
        sys.exit(1)

    # NEW: sort by Date (ascending). Python sort is stable.
    rows.sort(key=lambda x: x[2])

    # Write CSV with UTF-8 BOM so Excel opens it cleanly
    with outfile.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["Artist", "Album", "Date"])
        w.writerows(rows)

    print(f"Done. Parsed {len(rows)} releases → {outfile.resolve()}")

if __name__ == "__main__":
    main()