import os
import re
import time
import ssl
import urllib.error
import pandas as pd
import musicbrainzngs

# -------- Config --------
musicbrainzngs.set_useragent("LabelFiller", "1.0", "your@email.com")

RATE_LIMIT_SLEEP_SEC = 1   # be nice to the API
RETRY_ATTEMPTS = 3         # retry transient SSL/URL failures
RETRY_BACKOFF_SEC = 2      # base seconds for backoff between retries

# Major labels to detect
MAJORS = [
    "universal", "sony", "warner", "columbia", "atlantic",
    "interscope", "def jam", "rca", "epic", "virgin", "emi"
]

# Values to treat as "no label" and blank out (normalized)
NO_LABEL_PATTERNS = {
    "no label", "none", "n/a", "na", "unknown",
    "-", "—"
}

# -------- Helpers --------
def _normalize_label_for_compare(s: str) -> str:
    """
    Normalize label strings for comparison:
    - trim, collapse whitespace
    - lower
    - strip ONE layer of surrounding (), [], {} if present
    """
    s = s.replace("\u00A0", " ").replace("\u200B", "")
    s = s.strip()
    s = re.sub(r"\s+", " ", s).lower()
    # strip one layer of surrounding brackets/parens/braces
    s = re.sub(r"^[\(\[\{]\s*", "", s)
    s = re.sub(r"\s*[\)\]\}]$", "", s)
    s = s.strip()
    return s


def clean_label(val: object) -> str:
    """Normalize LABEL cell to a clean string; convert any 'no label' placeholder to a true blank."""
    if pd.isna(val):
        return ""

    s = str(val)

    # Remove hidden whitespace chars
    s = s.replace("\u00A0", " ")   # non-breaking space
    s = s.replace("\u200B", "")    # zero-width space
    s = s.strip()

    low = _normalize_label_for_compare(s)

    # Treat "(no label)", "[no label]", "{no label}" etc. all as blank
    if low in NO_LABEL_PATTERNS or low == "no label":
        return ""

    return s


def classify_label_type(label: str) -> str:
    """Classify non-empty labels as major or independent."""
    if not label.strip():
        return "self-released"

    ll = label.lower()
    return "major" if any(m in ll for m in MAJORS) else "independent"


lookup_cache = {}


def get_label_from_musicbrainz(artist: str, album: str):
    """
    Return a label string or None if not found.

    Changes:
    - Retries transient SSL/URL errors (UNEXPECTED_EOF, connection resets, etc.)
    - Prints attempt numbers so you can verify retries are happening
    - Does NOT cache None when the failure was a network/SSL error
      (so reruns can succeed later)
    - Treats MusicBrainz "[no label]" as blank via clean_label() later
    """
    key = (artist.lower(), album.lower())
    if key in lookup_cache:
        return lookup_cache[key]

    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            print(f"\n  🔍 Querying: {artist} — {album} (attempt {attempt}/{RETRY_ATTEMPTS})")

            res = musicbrainzngs.search_releases(
                artist=artist,
                release=album,
                limit=1
            )

            releases = res.get("release-list", [])
            if not releases:
                print("     ❌ No releases found")
                lookup_cache[key] = None  # valid response, no releases
                return None

            label_info = releases[0].get("label-info-list", [])
            if label_info and isinstance(label_info, list):
                first = label_info[0]
                if isinstance(first, dict):
                    label = first.get("label", {})
                    if isinstance(label, dict) and "name" in label:
                        label_name = label["name"]
                        print(f"     🎯 Found label: {label_name}")
                        lookup_cache[key] = label_name
                        return label_name

            print("     ⚠️ No label info found")
            lookup_cache[key] = None  # valid response, just no label info
            return None

        except (ssl.SSLError, urllib.error.URLError) as e:
            # Transient network issue: retry with backoff
            print(f"     🔁 Network/SSL error: {e}")
            if attempt < RETRY_ATTEMPTS:
                sleep_for = RETRY_BACKOFF_SEC * attempt
                print(f"     ⏳ Retrying in {sleep_for}s...")
                time.sleep(sleep_for)
                continue
            else:
                # Final attempt failed: do NOT cache, so reruns can try again later
                print("     ⚠️ Giving up after retries (not caching this failure).")
                return None

        except Exception as e:
            # Non-network error: cache None to avoid repeated hard failures
            print(f"     ❌ Error: {e}")
            lookup_cache[key] = None
            return None

    # Safety fallback
    return None


# -------- Main --------
def main():
    file_path = input("📁 Paste the full path to your CSV or Excel file: ").strip()
    if not os.path.isfile(file_path):
        print(f"❌ File not found: {file_path}")
        raise SystemExit(1)

    ext = os.path.splitext(file_path)[1].lower()

    # --- Load file ---
    if ext in [".xlsx", ".xls"]:
        df = pd.read_excel(file_path)
    else:
        try:
            df = pd.read_csv(file_path, encoding="utf-8")
        except UnicodeDecodeError:
            df = pd.read_csv(file_path, encoding="utf-8-sig")

    df.columns = df.columns.str.strip()

    # Ensure columns exist
    if "LABEL" not in df.columns:
        df["LABEL"] = ""
    if "LABEL TYPE" not in df.columns:
        df["LABEL TYPE"] = ""

    # Clean existing LABEL values (this will blank out [no label] etc.)
    df["LABEL"] = df["LABEL"].apply(clean_label)
    df["LABEL TYPE"] = df["LABEL TYPE"].fillna("").astype(str).str.strip()

    total_rows = len(df)
    updated_from_mb = 0
    defaulted_self_released = 0
    already_classified = 0
    skipped_missing_fields = 0

    print(f"\n🔍 Starting label lookup for {total_rows} rows...\n")

    for idx, row in df.iterrows():
        artist = str(row.get("ARTIST") or "").strip()
        album = str(row.get("ALBUM") or "").strip()
        label = str(row.get("LABEL") or "").strip()

        print(f"[{idx + 1}/{total_rows}] {artist} – {album}", end="")

        if not artist or not album:
            print(" ❌ Skipped (missing artist or album)")
            skipped_missing_fields += 1
            continue

        if label:
            # label already filled; just classify it
            df.at[idx, "LABEL TYPE"] = classify_label_type(label)
            already_classified += 1
            print(" ✅ Already filled")
            continue

        found = get_label_from_musicbrainz(artist, album)

        # Normalize any returned label (handles "[no label]" etc.)
        found_clean = clean_label(found) if found else ""

        if found_clean:
            df.at[idx, "LABEL"] = found_clean
            df.at[idx, "LABEL TYPE"] = classify_label_type(found_clean)
            updated_from_mb += 1
            print(" ✅ Updated")
        else:
            df.at[idx, "LABEL"] = ""
            df.at[idx, "LABEL TYPE"] = "self-released"
            defaulted_self_released += 1
            print(" ⚠️  No label found — defaulting to self-released")

        time.sleep(RATE_LIMIT_SLEEP_SEC)

    # Final enforcement
    df["LABEL"] = df["LABEL"].apply(clean_label)
    df.loc[df["LABEL"] == "", "LABEL TYPE"] = "self-released"

    # --- Save output ---
    base, _ = os.path.splitext(file_path)
    output_path = f"{base}_filled{ext if ext in ['.xlsx', '.xls'] else '.csv'}"

    if ext in [".xlsx", ".xls"]:
        df.to_excel(output_path, index=False)
    else:
        df.to_csv(output_path, index=False, encoding="utf-8-sig")

    # Summary
    print("\n✅ Done!")
    print(f"📄 Saved: {output_path}\n")
    print("Summary:")
    print(f"  • Rows already classified:            {already_classified}")
    print(f"  • Rows updated from MusicBrainz:       {updated_from_mb}")
    print(f"  • Rows defaulted to self-released:     {defaulted_self_released}")
    print(f"  • Rows skipped (missing fields):       {skipped_missing_fields}")


if __name__ == "__main__":
    main()