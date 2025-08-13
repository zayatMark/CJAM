import os
import re
import time
import pandas as pd
import musicbrainzngs

# -------- Config --------
musicbrainzngs.set_useragent("LabelFiller", "1.0", "your@email.com")
RATE_LIMIT_SLEEP_SEC = 1  # be nice to the API

# Major labels to detect
MAJORS = [
    "universal", "sony", "warner", "columbia", "atlantic",
    "interscope", "def jam", "rca", "epic", "virgin", "emi"
]

# Values to treat as "no label" and blank out
NO_LABEL_PATTERNS = {
    "[no label]", "no label", "none", "n/a", "na", "[none]", "[n/a]",
    "[unknown]", "unknown", "(no label)", "-", "—"
}

# -------- Helpers --------
def clean_label(val: object) -> str:
    """Normalize LABEL cell to a clean string; convert any 'no label' placeholder to a true blank."""
    if pd.isna(val):
        return ""
    s = str(val)

    # Remove common hidden whitespace chars
    s = s.replace("\u00A0", " ")  # non-breaking space
    s = s.replace("\u200B", "")   # zero-width space
    s = s.strip()

    # Lowercased, single-spaced version for comparison
    low = re.sub(r"\s+", " ", s).lower()
    # Strip *single* surrounding brackets/parentheses (e.g., "[no label]" or "(no label)")
    low = re.sub(r"^[\[\(]\s*|\s*[\]\)]$", "", low)

    if low in NO_LABEL_PATTERNS:
        return ""  # true blank
    return s

def classify_label_type(label: str) -> str:
    """Classify non-empty labels as major or independent."""
    if not label.strip():
        return "self-released"
    ll = label.lower()
    return "major" if any(m in ll for m in MAJORS) else "independent"

lookup_cache = {}

def get_label_from_musicbrainz(artist: str, album: str):
    """Return a label string or None if not found."""
    key = (artist.lower(), album.lower())
    if key in lookup_cache:
        return lookup_cache[key]

    try:
        print(f"  🔍 Querying: {artist} — {album}")
        res = musicbrainzngs.search_releases(artist=artist, release=album, limit=1)
        releases = res.get("release-list", [])
        if releases:
            label_info_list = releases[0].get("label-info-list", [])
            if label_info_list and isinstance(label_info_list, list):
                first = label_info_list[0]
                if isinstance(first, dict) and "label" in first and "name" in first["label"]:
                    label_name = first["label"]["name"]
                    print(f"     🎯 Found label: {label_name}")
                    lookup_cache[key] = label_name
                    return label_name
            print("     ⚠️ No label info found")
        else:
            print("     ❌ No releases found")
    except Exception as e:
        print(f"     ❌ Error: {e}")

    lookup_cache[key] = None
    return None

# -------- Main --------
def main():
    file_path = input("📁 Paste the full path to your CSV file: ").strip()
    if not os.path.isfile(file_path):
        print(f"❌ File not found: {file_path}")
        raise SystemExit(1)

    df = pd.read_csv(file_path)
    df.columns = df.columns.str.strip()

    # Ensure columns exist
    if "LABEL" not in df.columns:
        df["LABEL"] = ""
    if "LABEL TYPE" not in df.columns:
        df["LABEL TYPE"] = ""

    # Clean existing LABEL values first
    df["LABEL"] = df["LABEL"].apply(clean_label)
    df["LABEL TYPE"] = df["LABEL TYPE"].astype(str).where(df["LABEL TYPE"].notna(), "").str.strip()

    total_rows = len(df)
    updated_from_mb = 0
    defaulted_self_released = 0
    already_classified = 0

    print(f"\n🔍 Starting label lookup for {total_rows} rows...\n")

    for idx, row in df.iterrows():
        artist = str(row.get("ARTIST") or "").strip()
        album  = str(row.get("ALBUM")  or "").strip()
        label  = str(row.get("LABEL")  or "").strip()

        print(f"[{idx + 1}/{total_rows}] {artist} – {album}", end="")

        if not artist or not album:
            print(" ❌ Skipped (missing artist or album)")
            continue

        if label:
            # Label present -> classify major/independent
            df.at[idx, "LABEL TYPE"] = classify_label_type(label)
            already_classified += 1
            print(" ✅ Already filled")
            continue

        # LABEL is blank -> try MusicBrainz
        found = get_label_from_musicbrainz(artist, album)
        if found:
            df.at[idx, "LABEL"] = found
            df.at[idx, "LABEL TYPE"] = classify_label_type(found)
            updated_from_mb += 1
            print(" ✅ Updated")
        else:
            # No label found -> blank + self-released
            df.at[idx, "LABEL"] = ""
            df.at[idx, "LABEL TYPE"] = "self-released"
            defaulted_self_released += 1
            print(" ⚠️  No label found — defaulting to self-released")

        time.sleep(RATE_LIMIT_SLEEP_SEC)

    # Safety pass: enforce your rules one last time
    df["LABEL"] = df["LABEL"].apply(clean_label)
    df.loc[df["LABEL"] == "", "LABEL TYPE"] = "self-released"

    # Save
    base, ext = os.path.splitext(file_path)
    output_path = f"{base}_filled{ext}"
    df.to_csv(output_path, index=False)

    # Summary
    print("\n✅ Done!")
    print(f"📄 Saved: {output_path}\n")
    print("Summary:")
    print(f"  • Rows with label already present and classified: {already_classified}")
    print(f"  • Rows updated from MusicBrainz:                {updated_from_mb}")
    print(f"  • Rows defaulted to self-released (no label):   {defaulted_self_released}")

if __name__ == "__main__":
    main()