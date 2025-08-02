import os
import pandas as pd
import difflib

def normalize_name(name):
    return (
        name.strip()
        .lower()
        .replace("&", "and")
        .replace("–", "-")
        .replace("—", "-")
        .replace("’", "'")
        .replace("“", '"')
        .replace("”", '"')
    )

def rename_folders(folder_path, reference_csv_path):
    try:
        df = pd.read_csv(reference_csv_path)
        df.columns = [col.strip().upper() for col in df.columns]
        required_columns = {"ARTIST", "ALBUM", "CURRENT"}
        if not required_columns.issubset(df.columns):
            print(f"❌ CSV is missing required columns: {required_columns}")
            return
    except Exception as e:
        print(f"❌ Failed to load CSV: {e}")
        return

    references = []
    for _, row in df.iterrows():
        artist = normalize_name(row["ARTIST"])
        album = normalize_name(row["ALBUM"])
        current = row["CURRENT"]
        references.append({
            "artist": artist,
            "album": album,
            "current": current,
            "display_name": f"{artist} - {album}"
        })

    try:
        folders = os.listdir(folder_path)
    except FileNotFoundError:
        print(f"❌ Folder not found: {folder_path}")
        return

    renamed, skipped = 0, 0

    for folder in folders:
        old_path = os.path.join(folder_path, folder)
        if not os.path.isdir(old_path):
            continue

        folder_norm = normalize_name(folder)
        best_match = None
        best_ratio = 0

        for ref in references:
            ratio = difflib.SequenceMatcher(None, folder_norm, ref["display_name"]).ratio()
            print(f"🔍 Comparing '{folder}' with '{ref['display_name']}' → ratio: {ratio:.2f}")
            if ratio > best_ratio and ratio >= 0.5:
                best_ratio = ratio
                best_match = ref

        if best_match:
            new_name = f"{best_match['current']} - {folder}"
            new_path = os.path.join(folder_path, new_name)
            if old_path != new_path:
                try:
                    os.rename(old_path, new_path)
                    print(f"✅ Renamed: {folder} → {new_name}")
                    renamed += 1
                except Exception as e:
                    print(f"❌ Failed to rename '{folder}': {e}")
                    skipped += 1
        else:
            print(f"⚠️ No match for: {folder}")
            skipped += 1

    print(f"\nSummary: ✅ Renamed: {renamed} | ⚠️ Skipped: {skipped}")

# --- Prompt Section ---
folder_path = input("📁 Drag in the folder containing the release folders and press Enter: ").strip().strip("'\"")
csv_path = input("📄 Drag in your Airtable CSV file and press Enter: ").strip().strip("'\"")
rename_folders(folder_path, csv_path)