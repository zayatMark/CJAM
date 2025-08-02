import pandas as pd

def get_file_input(prompt):
    """Prompt user for a file path."""
    return input(prompt)

def generate_cancon_report(input_file, output_file):
    # Load the Excel file
    df = pd.read_excel(input_file)
    
    # Filter the dataframe to only include rows with relevant CRTC codes
    relevant_crtc_codes = [21, 22, 23, 24, 31, 32, 33, 34, 35]
    df_filtered = df[df['CRTC'].isin(relevant_crtc_codes)]
    
    # Exclude rows where the show title contains the word "encore" (case insensitive)
    df_filtered = df_filtered[~df_filtered['SHOW TITLE'].str.contains('encore', case=False, na=False)]
    
    # Group by 'SHOW TITLE' and calculate the required metrics
    grouped = df_filtered.groupby('SHOW TITLE')
    
    # Calculate Total Songs and CANCON Songs
    total_songs = grouped.size()
    
    # Ensure CANCON values are stripped of any whitespace before counting 'yes'
    cancon_songs = grouped['CANCON'].apply(lambda x: x.str.strip().str.lower().eq('yes').sum())
    
    # Create the report DataFrame
    report = pd.DataFrame({
        'Total Songs': total_songs,
        'CANCON Songs': cancon_songs
    }).reset_index()
    
    # Calculate the CANCON percentage correctly
    report['CANCON (%)'] = (report['CANCON Songs'] / report['Total Songs']) * 100
    
    # Ensure the CANCON percentage is rounded to two decimal places
    report['CANCON (%)'] = report['CANCON (%)'].round(2)
    
    # Exclude shows with no relevant CRTC codes (though this should already be filtered)
    report = report[report['Total Songs'] > 0]
    
    # Save the report to a CSV file
    report.to_csv(output_file, index=False)

def main():
    # Get the input and output file paths from the user
    input_file = get_file_input("Please enter the path to the Excel log file: ")
    output_file = get_file_input("Please enter the path to the output CSV file: ")

    # Generate the CANCON report
    generate_cancon_report(input_file, output_file)
    print(f"CANCON report has been saved to '{output_file}'.")

if __name__ == "__main__":
    main()
