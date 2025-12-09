import pandas as pd

def get_file_input(prompt):
    return input(prompt)

def read_logs_file(logs_file):
    logs_data = pd.read_excel(logs_file)
    logs_data['CURRENT'] = pd.to_numeric(logs_data['CURRENT'], errors='coerce').dropna().astype(int)
    logs_data = logs_data.dropna(subset=['SHOW TITLE', 'CURRENT'])
    return logs_data

def read_airtable_file(airtable_file):
    airtable_data = pd.read_csv(airtable_file)
    airtable_data['CURRENT'] = pd.to_numeric(airtable_data['CURRENT'], errors='coerce').dropna().astype(int)
    return airtable_data

def process_data(logs_data, airtable_data):
    unique_currents = logs_data.drop_duplicates(subset=['SHOW TITLE', 'CURRENT'])
    current_counts = unique_currents['CURRENT'].value_counts().reset_index()
    current_counts.columns = ['CURRENT', 'COUNT']
    current_counts['CURRENT'] = current_counts['CURRENT'].astype(int)
    
    valid_currents = current_counts[current_counts['CURRENT'].isin(airtable_data['CURRENT'])]
    skipped_currents = current_counts[~current_counts['CURRENT'].isin(airtable_data['CURRENT'])]
    
    return valid_currents, skipped_currents

def get_total_plays_from_workbook(workbook_file, airtable_data):
    workbook = pd.read_excel(workbook_file, sheet_name=None)
    total_plays = pd.DataFrame()
    valid_currents = set(airtable_data['CURRENT'])

    for sheet_name, sheet_data in workbook.items():
        sheet_data['CURRENT'] = pd.to_numeric(sheet_data['CURRENT'], errors='coerce').dropna().astype(int)
        sheet_data = sheet_data[sheet_data['CURRENT'].isin(valid_currents)]
        current_plays = sheet_data.groupby('CURRENT')['CURRENT'].count().reset_index(name='COUNT')
        total_plays = pd.concat([total_plays, current_plays])

    total_plays = total_plays.groupby('CURRENT')['COUNT'].sum().reset_index()
    total_plays.rename(columns={'COUNT': 'COUNT_WORKBOOK'}, inplace=True)
    return total_plays

def merge_and_sort_data(valid_currents, airtable_data, workbook_plays):
    # Ensure LABEL TYPE exists and default as needed
    if 'LABEL TYPE' not in airtable_data.columns:
        airtable_data['LABEL TYPE'] = 'self-released'
        print("⚠️ 'LABEL TYPE' column missing in Airtable CSV. Defaulting all entries to 'self-released'.")
    else:
        airtable_data['LABEL TYPE'] = airtable_data['LABEL TYPE'].fillna('self-released').replace('', 'self-released')

    required_columns = ['CURRENT', 'CONTENT TAGS', 'ARTIST', 'ALBUM', 'LABEL TYPE']
    for col in required_columns:
        if col not in airtable_data.columns:
            raise ValueError(f"Missing required column in Airtable CSV: {col}")

    airtable_tags = airtable_data[required_columns]
    merged_data = pd.merge(valid_currents, airtable_tags, on='CURRENT', how='left')
    merged_data = pd.merge(merged_data, workbook_plays, on='CURRENT', how='left')
    merged_data['COUNT_WORKBOOK'] = merged_data['COUNT_WORKBOOK'].fillna(0)

    # LOCAL PRIORITY
    def get_local_priority(tags):
        if pd.isnull(tags):
            return 4
        tags = tags.lower()
        if 'windsor' in tags or 'essex' in tags:
            return 1
        elif 'detroit' in tags:
            return 2
        elif 'cancon' in tags:
            return 3
        else:
            return 4

    merged_data['LOCAL_PRIORITY'] = merged_data['CONTENT TAGS'].apply(get_local_priority)

    # LABEL PRIORITY
    label_priority_map = {
        'self-released': 1,
        'independent': 2,
        'major': 3
    }

    def get_label_priority(label_type):
        if pd.isnull(label_type):
            return 1
        return label_priority_map.get(label_type.strip().lower(), 1)

    merged_data['LABEL_PRIORITY'] = merged_data['LABEL TYPE'].apply(get_label_priority)

    # Final sort
    sorted_data = merged_data.sort_values(
        by=['COUNT', 'LOCAL_PRIORITY', 'LABEL_PRIORITY', 'COUNT_WORKBOOK'],
        ascending=[False, True, True, True]
    )

    return sorted_data

def save_top_30(sorted_data, output_file):
    top_30 = sorted_data.head(30)
    output_columns = ['CURRENT', 'COUNT', 'ARTIST', 'ALBUM', 'CONTENT TAGS', 'LABEL TYPE', 'COUNT_WORKBOOK']
    top_30.to_csv(output_file, columns=output_columns, index=False, encoding='utf-8', errors='replace')
    print(f"\n✅ Top 30 currents list has been saved to: {output_file}")

def main():
    logs_file = get_file_input("Please enter the logs file path (Excel): ")
    airtable_file = get_file_input("Please enter the Airtable file path (CSV): ")
    workbook_file = get_file_input("Please enter the workbook file path for total plays (Excel): ")
    output_file = get_file_input("Please enter the output file path (CSV): ")

    logs_data = read_logs_file(logs_file)
    airtable_data = read_airtable_file(airtable_file)

    valid_currents, skipped_currents = process_data(logs_data, airtable_data)

    if not skipped_currents.empty:
        print(f"\n⚠️ Skipped CURRENT numbers not found in Airtable: {', '.join(map(str, skipped_currents['CURRENT'].values))}")
        print(f"Total skipped: {len(skipped_currents)}")

    workbook_plays = get_total_plays_from_workbook(workbook_file, airtable_data)

    sorted_data = merge_and_sort_data(valid_currents, airtable_data, workbook_plays)
    save_top_30(sorted_data, output_file)

if __name__ == "__main__":
    main()