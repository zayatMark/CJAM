import pandas as pd
import musicbrainzngs
import time
import os

# --- Setup MusicBrainz API ---
musicbrainzngs.set_useragent("LabelFiller", "1.0", "your@email.com")

# --- Ask for File Path ---
file_path = input("📁 Paste the full path to your CSV file: ").strip()
if not os.path.isfile(file_path):
    print(f"❌ File not found: {file_path}")
    exit(1)

# --- Load CSV ---
df = pd.read_csv(file_path)
total_rows = len(df)

# --- Cache to avoid duplicate lookups ---
lookup_cache = {}

# --- Helper: Determine label type ---
def determine_label_type(label, artist):
    if not label or label.strip().lower() in ["", "none", "self-released"]:
        return "self-released"
    if artist.lower() in label.lower():
        return "self-released"

    major_labels = ["universal", "sony", "warner", "columbia", "atlantic",
                    "interscope", "def jam", "rca", "epic", "virgin", "emi"]
    if any(major in label.lower() for major in major_labels):
        return "major"

    return "independent"

# --- Helper: Query MusicBrainz for label ---
def get_label(artist, album):
    key = (artist.lower(), album.lower())
    if key in lookup_cache:
        return lookup_cache[key]

    try:
        print(f"  🔍 Querying: {artist} — {album}")
        result = musicbrainzngs.search_releases(artist=artist, release=album, limit=1)
        releases = result.get("release-list", [])
        if releases:
            label_info = releases[0].get("label-info-list", [])
            if label_info and "label" in label_info[0]:
                label = label_info[0]["label"]["name"]
                print(f"     🎯 Found label: {label}")
                lookup_cache[key] = label
                return label
            else:
                print("     ⚠️ No label info found")
        else:
            print("     ❌ No releases found")
    except Exception as e:
        print(f"     ❌ Error: {e}")

    lookup_cache[key] = None
    return None

# --- Process Each Row ---
print(f"\n🔍 Starting label lookup for {total_rows} rows...\n")

for idx, row in df.iterrows():
    artist = str(row.get("ARTIST") or "").strip()
    album = str(row.get("ALBUM") or "").strip()
    label = row.get("LABEL")

    print(f"[{idx + 1}/{total_rows}] {artist} – {album}", end="")

    if not artist or not album:
        print(" ❌ Skipped (missing artist or album)")
        continue

    if pd.notna(label) and str(label).strip() != "":
        print(" ✅ Already filled")
        continue

    found_label = get_label(artist, album)
    if found_label:
        df.at[idx, "LABEL"] = found_label
        df.at[idx, "LABEL TYPE"] = determine_label_type(found_label, artist)
        print(" ✅ Updated")
    else:
        # Leave LABEL blank and set LABEL TYPE to self-released
        df.at[idx, "LABEL"] = ""
        df.at[idx, "LABEL TYPE"] = "self-released"
        print(" ⚠️  No label found — defaulting to self-released")

    time.sleep(1)  # prevent rate limits

# --- Save Updated File ---
base, ext = os.path.splitext(file_path)
output_path = f"{base}_filled{ext}"
df.to_csv(output_path, index=False)
print(f"\n✅ Done! File saved as:\n{output_path}")