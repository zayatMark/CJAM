import os
import re
import pandas as pd


def get_file_input(prompt: str) -> str:
    """Prompt user for a file path and gently handle accidental quotes."""
    return input(prompt).strip().strip("'\"")


def _normalize_colname(name: object) -> str:
    """Normalize column names: uppercase, collapse spaces, strip."""
    s = "" if pd.isna(name) else str(name)
    s = s.replace("\u00A0", " ").replace("\u200B", "")
    s = s.strip()
    s = re.sub(r"\s+", " ", s)
    return s.upper()


def _find_header_row(excel_path: str, required_cols_norm: set[str], max_scan_rows: int = 30) -> int:
    """
    Try reading the first N rows with no header and find the row that contains all required columns.
    Returns the header row index (0-based).
    """
    preview = pd.read_excel(excel_path, header=None, nrows=max_scan_rows)
    for i in range(len(preview)):
        row_vals = {_normalize_colname(v) for v in preview.iloc[i].tolist()}
        if required_cols_norm.issubset(row_vals):
            return i
    return 0  # fallback: assume row 0 is header


def _coerce_crtc(val: object):
    """Extract numeric CRTC code from messy cells like '21', '21.0', '21 (Pop)'."""
    if pd.isna(val):
        return None
    s = str(val).strip()
    m = re.search(r"\d+", s)
    return int(m.group()) if m else None


def _is_cancon_yes(val: object) -> bool:
    """Robust CANCON yes detection."""
    if pd.isna(val):
        return False
    s = str(val).strip().lower()
    return s in {"yes", "y", "true", "t", "1", "cancon", "c"}


def generate_cancon_report(input_file: str, output_file: str) -> str:
    # We will identify the header row automatically.
    required_norm = {"CRTC", "SHOW TITLE", "CANCON"}
    header_row = _find_header_row(input_file, required_norm)

    df = pd.read_excel(input_file, header=header_row)

    # Normalize column names
    df.columns = [_normalize_colname(c) for c in df.columns]

    # Verify required columns exist
    missing = required_norm - set(df.columns)
    if missing:
        raise ValueError(
            "Missing required column(s): "
            + ", ".join(sorted(missing))
            + f"\n\nDetected columns: {list(df.columns)}"
        )

    # Clean/normalize key fields
    df["SHOW TITLE"] = df["SHOW TITLE"].fillna("").map(lambda v: str(v).strip())
    df["CRTC"] = df["CRTC"].map(_coerce_crtc)
    df["CANCON"] = df["CANCON"].map(_is_cancon_yes)

    # Filter relevant CRTC codes
    relevant_crtc_codes = {21, 22, 23, 24, 31, 32, 33, 34, 35}
    df_filtered = df[df["CRTC"].isin(relevant_crtc_codes)].copy()

    # Exclude encore shows
    df_filtered = df_filtered[
        ~df_filtered["SHOW TITLE"].str.contains(r"\bencore\b", case=False, na=False)
    ]

    # If nothing remains, still produce an empty report (but don't crash)
    if df_filtered.empty:
        report = pd.DataFrame(columns=["SHOW TITLE", "Total Songs", "CANCON Songs", "CANCON (%)"])
    else:
        grouped = df_filtered.groupby("SHOW TITLE", dropna=False)

        total_songs = grouped.size()
        cancon_songs = grouped["CANCON"].sum()  # since CANCON is boolean now

        report = pd.DataFrame({
            "SHOW TITLE": total_songs.index,
            "Total Songs": total_songs.values,
            "CANCON Songs": cancon_songs.values,
        })

        report["CANCON (%)"] = (report["CANCON Songs"] / report["Total Songs"] * 100).round(2)

    # Save output
    out = output_file
    if os.path.isdir(out):
        out = os.path.join(out, "cancon_report.csv")

    out_dir = os.path.dirname(out)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    report.to_csv(out, index=False, encoding="utf-8-sig")
    return out


def main():
    input_file = get_file_input("Please enter the path to the Excel log file: ")
    output_file = get_file_input("Please enter the path to the output CSV file: ")

    if not os.path.isfile(input_file):
        raise FileNotFoundError(f"Input file not found: {input_file}")

    out_path = generate_cancon_report(input_file, output_file)
    print(f"✅ CANCON report saved to: {out_path}")


if __name__ == "__main__":
    main()