import pandas as pd

def get_file_input(prompt):
    return input(prompt)

def read_logs_file(logs_file):
    logs_data = pd.read_excel(logs_file)

    # Clean CURRENT safely (avoid index misalignment)
    logs_data['CURRENT'] = pd.to_numeric(logs_data['CURRENT'], errors='coerce')
    logs_data = logs_data.dropna(subset=['SHOW TITLE', 'CURRENT'])
    logs_data['CURRENT'] = logs_data['CURRENT'].astype(int)

    return logs_data

def read_airtable_file(airtable_file):
    airtable_data = pd.read_csv(airtable_file)

    airtable_data['CURRENT'] = pd.to_numeric(airtable_data['CURRENT'], errors='coerce')
    airtable_data = airtable_data.dropna(subset=['CURRENT'])
    airtable_data['CURRENT'] = airtable_data['CURRENT'].astype(int)

    return airtable_data

def process_data(logs_data, airtable_data):
    """
    Count plays per CURRENT with a cap of 2 spins per show per week.
    """
    # Plays per (show, current)
    plays_per_show = (
        logs_data
        .groupby(['SHOW TITLE', 'CURRENT'])
        .size()
        .reset_index(name='PLAYS_PER_SHOW')
    )

    # Cap at 2 plays per show per current
    plays_per_show['PLAYS_PER_SHOW'] = plays_per_show['PLAYS_PER_SHOW'].clip(upper=2)

    # Sum capped plays across all shows → weekly total per current
    current_counts = (
        plays_per_show
        .groupby('CURRENT')['PLAYS_PER_SHOW']
        .sum()
        .reset_index(name='COUNT')
    )

    # Filter against Airtable CURRENTs
    valid_currents = current_counts[current_counts['CURRENT'].isin(airtable_data['CURRENT'])]
    skipped_currents = current_counts[~current_counts['CURRENT'].isin(airtable_data['CURRENT'])]

    return valid_currents, skipped_currents

def get_weeks_in_studio_from_workbook(workbook_file, airtable_data):
    """
    Estimate 'Number of Weeks in Studio':
    - Each sheet = one week.
    - If a CURRENT appears at least once in a sheet, that counts as 1 week.
    """
    workbook = pd.read_excel(workbook_file, sheet_name=None)
    valid_currents = set(airtable_data['CURRENT'])
    all_weeks = []

    for sheet_name, sheet_data in workbook.items():
        if 'CURRENT' not in sheet_data.columns:
            continue

        sheet_data['CURRENT'] = pd.to_numeric(sheet_data['CURRENT'], errors='coerce')
        sheet_data = sheet_data.dropna(subset=['CURRENT'])
        sheet_data['CURRENT'] = sheet_data['CURRENT'].astype(int)

        # Keep only valid currents
        sheet_data = sheet_data[sheet_data['CURRENT'].isin(valid_currents)]

        # Unique currents in this week
        unique_in_week = sheet_data['CURRENT'].drop_duplicates()
        if not unique_in_week.empty:
            week_df = pd.DataFrame({
                'CURRENT': unique_in_week,
                'WEEK_COUNT': 1
            })
            all_weeks.append(week_df)

    if not all_weeks:
        return pd.DataFrame(columns=['CURRENT', 'WEEKS_IN_STUDIO'])

    weeks_in_studio = (
        pd.concat(all_weeks, ignore_index=True)
        .groupby('CURRENT')['WEEK_COUNT']
        .sum()
        .reset_index(name='WEEKS_IN_STUDIO')
    )

    return weeks_in_studio

def merge_and_score_data(valid_currents, airtable_data, weeks_in_studio):
    """
    Merge spin counts with Airtable metadata and compute priority fields.
    Returns a DataFrame with:
      - COUNT
      - GENRE
      - LOCAL_PRIORITY
      - LABEL_PRIORITY
      - WEEKS_IN_STUDIO
      plus ARTIST / ALBUM / CONTENT TAGS / LABEL TYPE / CURRENT.
    """

    # Ensure LABEL TYPE exists and default as needed
    if 'LABEL TYPE' not in airtable_data.columns:
        airtable_data['LABEL TYPE'] = 'self-released'
        print("⚠️ 'LABEL TYPE' column missing in Airtable CSV. Defaulting all entries to 'self-released'.")
    else:
        airtable_data['LABEL TYPE'] = (
            airtable_data['LABEL TYPE']
            .fillna('self-released')
            .replace('', 'self-released')
        )

    # GENRE required for this script
    required_columns = ['CURRENT', 'CONTENT TAGS', 'ARTIST', 'ALBUM', 'LABEL TYPE', 'GENRE']
    for col in required_columns:
        if col not in airtable_data.columns:
            raise ValueError(f"Missing required column in Airtable CSV: {col}")

    airtable_tags = airtable_data[required_columns].copy()

    # Merge counts with Airtable metadata
    merged_data = pd.merge(valid_currents, airtable_tags, on='CURRENT', how='left')
    merged_data = pd.merge(merged_data, weeks_in_studio, on='CURRENT', how='left')
    merged_data['WEEKS_IN_STUDIO'] = merged_data['WEEKS_IN_STUDIO'].fillna(0)

    # LOCAL PRIORITY: local → detroit → cancon → everything else
    def get_local_priority(tags):
        if pd.isnull(tags):
            return 4
        tags = str(tags).lower()

        if 'local' in tags:
            return 1
        elif 'detroit' in tags:
            return 2
        elif 'cancon' in tags:
            return 3
        else:
            return 4

    merged_data['LOCAL_PRIORITY'] = merged_data['CONTENT TAGS'].apply(get_local_priority)

    # LABEL PRIORITY: self-released → independent → major
    label_priority_map = {
        'self-released': 1,
        'independent': 2,
        'major': 3
    }

    def get_label_priority(label_type):
        if pd.isnull(label_type):
            return 1
        return label_priority_map.get(str(label_type).strip().lower(), 1)

    merged_data['LABEL_PRIORITY'] = merged_data['LABEL TYPE'].apply(get_label_priority)

    return merged_data

def get_top_by_genre(scored_data, genres, top_n=10):
    """
    For each genre in `genres`, select the top `top_n` releases according to:
      a. Highest COUNT (spins, capped at 2 per show)
      b. Local priority (local → detroit → cancon → other)
      c. Label priority (self → indie → major)
      d. Fewer weeks in studio first (newer titles win ties)
    """
    # Filter to the genres we care about
    filtered = scored_data[scored_data['GENRE'].isin(genres)].copy()

    # Sort within genres using the priority rules
    filtered = filtered.sort_values(
        by=['GENRE', 'COUNT', 'LOCAL_PRIORITY', 'LABEL_PRIORITY', 'WEEKS_IN_STUDIO'],
        ascending=[True, False, True, True, True]
    )

    # Rank within each genre
    filtered['GENRE_RANK'] = filtered.groupby('GENRE').cumcount() + 1

    # Keep only top N per genre
    top_by_genre = filtered[filtered['GENRE_RANK'] <= top_n]

    return top_by_genre

def save_top_10_by_genre(top_by_genre, output_file):
    output_columns = [
        'GENRE',
        'GENRE_RANK',
        'CURRENT',
        'COUNT',
        'ARTIST',
        'ALBUM',
        'CONTENT TAGS',
        'LABEL TYPE',
        'WEEKS_IN_STUDIO'
    ]
    top_by_genre.to_csv(
        output_file,
        columns=output_columns,
        index=False,
        encoding='utf-8',
        errors='replace'
    )
    print(f"\n✅ Top 10-by-genre list has been saved to: {output_file}")

def main():
    logs_file = get_file_input("Please enter the logs file path (Excel): ")
    airtable_file = get_file_input("Please enter the Airtable file path (CSV): ")
    workbook_file = get_file_input("Please enter the workbook file path for studio weeks (Excel): ")
    output_file = get_file_input("Please enter the output file path (CSV): ")

    logs_data = read_logs_file(logs_file)
    airtable_data = read_airtable_file(airtable_file)

    valid_currents, skipped_currents = process_data(logs_data, airtable_data)

    if not skipped_currents.empty:
        print(
            "\n⚠️ Skipped CURRENT numbers not found in Airtable: "
            + ", ".join(map(str, skipped_currents['CURRENT'].values))
        )
        print(f"Total skipped: {len(skipped_currents)}")

    weeks_in_studio = get_weeks_in_studio_from_workbook(workbook_file, airtable_data)

    scored_data = merge_and_score_data(valid_currents, airtable_data, weeks_in_studio)

    # Your genre buckets
    genres = [
        "indie/rock/alt",
        "folk/blues",
        "electronic",
        "hip-hop",
        "funk/soul/r&b",
        "loud",
        "world",
        "jazz"
    ]

    top_by_genre = get_top_by_genre(scored_data, genres, top_n=10)
    save_top_10_by_genre(top_by_genre, output_file)

if __name__ == "__main__":
    main()