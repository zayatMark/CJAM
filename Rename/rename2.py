import re
import sys
from pathlib import Path

import pandas as pd


def sanitize_name(s: str) -> str:
    s = str(s).strip()
    s = s.replace("/", "-")
    s = s.replace("\0", "")
    s = re.sub(r"\s+", " ", s)
    return s.strip(" .")


def normalize_key(s: str) -> str:
    s = str(s).strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def make_unique_path(parent: Path, desired_name: str) -> Path:
    candidate = parent / desired_name
    if not candidate.exists():
        return candidate

    n = 2
    while True:
        candidate = parent / f"{desired_name} ({n})"
        if not candidate.exists():
            return candidate
        n += 1


def load_sheet(sheet_path: Path) -> pd.DataFrame:
    if sheet_path.suffix.lower() in [".xlsx", ".xls"]:
        df = pd.read_excel(sheet_path)
    elif sheet_path.suffix.lower() == ".csv":
        df = pd.read_csv(sheet_path)
    else:
        raise ValueError("Sheet must be .xlsx/.xls or .csv")

    required = ["CURRENT", "ARTIST", "ALBUM"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns: {missing}")

    df = df.dropna(subset=required).copy()

    # 🔒 Enforce CURRENT as integer
    def parse_current(val):
        try:
            if pd.isna(val):
                return None
            f = float(val)
            if not f.is_integer():
                return None
            return int(f)
        except Exception:
            return None

    df["CURRENT_INT"] = df["CURRENT"].apply(parse_current)
    bad_rows = df["CURRENT_INT"].isna()

    if bad_rows.any():
        print("\n⚠️ Rows skipped due to non-integer CURRENT values:")
        for _, row in df[bad_rows].iterrows():
            print(f"  ALBUM='{row['ALBUM']}', CURRENT='{row['CURRENT']}'")

    df = df[~bad_rows].copy()

    return df


def prompt_path(prompt_text: str) -> Path:
    while True:
        raw = input(prompt_text).strip().strip('"').strip("'")
        path = Path(raw).expanduser()

        if path.exists():
            return path.resolve()

        print("❌ Path does not exist. Please try again.\n")


def main():
    print("\n📀 Album Folder Renamer (Spreadsheet-Driven)\n")

    try:
        sheet_path = prompt_path("Enter path to spreadsheet (.xlsx or .csv): ")
        parent_folder = prompt_path("Enter path to folder containing album subfolders: ")

        if not parent_folder.is_dir():
            print("❌ The album path must be a folder.")
            sys.exit(1)

        df = load_sheet(sheet_path)

        lookup = {}
        for _, row in df.iterrows():
            key = normalize_key(row["ALBUM"])
            lookup.setdefault(key, row)

        planned = []
        skipped = []

        for folder in parent_folder.iterdir():
            if not folder.is_dir():
                continue

            key = normalize_key(folder.name)
            if key not in lookup:
                skipped.append(folder.name)
                continue

            row = lookup[key]
            current = row["CURRENT_INT"]  # guaranteed int
            artist = sanitize_name(row["ARTIST"])
            album = sanitize_name(row["ALBUM"])

            new_name = f"{current} - {artist} - {album}"
            new_path = make_unique_path(parent_folder, new_name)
            planned.append((folder, new_path))

        if not planned:
            print("\nNo matching folders found.")
            return

        print(f"\n🧪 DRY RUN — {len(planned)} folder(s) will be renamed:\n")
        for old, new in planned:
            print(f"{old.name}  →  {new.name}")

        if skipped:
            print("\n⚠️ Skipped (no ALBUM match):")
            for name in skipped:
                print(f"  - {name}")

        confirm = input("\nApply these changes? (y/n): ").strip().lower()
        if confirm != "y":
            print("\n❎ No changes made.")
            return

        for old, new in planned:
            old.rename(new)

        print("\n✅ Renaming complete.")

    except KeyboardInterrupt:
        print("\n\n❎ Cancelled.")
        sys.exit(1)


if __name__ == "__main__":
    main()