# translate_fortran.py
import requests
import csv
import time
import argparse
import os
import os

# --- Configuration ---
# Read API_URL from environment variable, default to localhost
API_URL = os.getenv("API_URL", "http://localhost:8000/v1/chat/completions")
MODEL = os.getenv("MODEL_ID", "codellama/CodeLlama-13b-Instruct-hf")

SYSTEM_PROMPT = """You are a Fortran code translator. Convert legacy Fortran code to modern Fortran standards. 
         Return ONLY the translated code without any explanations, comments, or wrapper text. 
         Use modules, explicit typing with IMPLICIT NONE, modern array syntax, and modern control structures. 
         Maintain the original functionality while making the code more readable and maintainable.
         Do not include any markdown formatting, backticks, or introductory text. 
         Output only the Fortran code itself."""
# --- End Configuration ---

def extract_code_from_response(response_text):
    """
    Simple function to extract code from the LLM response.
    Tries to find content between ``` markers, otherwise returns the whole response.
    """
    start_marker = response_text.find("```")
    if start_marker != -1:
        end_marker = response_text.find("```", start_marker + 3)
        if end_marker != -1:
            return response_text[start_marker + 3:end_marker].strip()
    # If no markers found, return the response as is (it might be pure code)
    return response_text.strip()

def translate_code(code_snippet, max_retries=3, delay=1):
    """
    Calls the vLLM API to translate a single code snippet.
    Includes basic retry logic.
    """
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Translate this legacy Fortran code to modern Fortran:\n{code_snippet}"}
        ],
        "temperature": 0.1,
        "max_tokens": 2048
    }

    for attempt in range(max_retries):
        try:
            response = requests.post(API_URL, json=payload, timeout=300) # 5 minute timeout
            response.raise_for_status() # Raises an HTTPError for bad responses
            data = response.json()
            full_response = data['choices'][0]['message']['content']
            extracted_code = extract_code_from_response(full_response)
            return extracted_code
        except requests.exceptions.RequestException as e:
            print(f"Attempt {attempt + 1} failed for a row: {e}")
            if attempt < max_retries - 1:
                time.sleep(delay * (2 ** attempt)) # Exponential backoff
            else:
                print("All attempts failed for this row, returning error message.")
                return f"Error translating: {str(e)}"
        except KeyError:
            print(f"Unexpected response format: {response.text}")
            return f"Error: Unexpected response format"

def process_csv(input_file, output_file, legacy_col='legacy_code', translated_col='mistral_translated_code'):
    """
    Reads the input CSV, translates the legacy_code column,
    and writes the result to the output CSV with updated translated_code column.
    """
    print(f"Reading input CSV: {input_file}")
    print(f"Writing output CSV: {output_file}")
    print(f"Legacy code column: {legacy_col}")
    print(f"Translated code column: {translated_col}")
    print("-" * 40)

    rows = []
    with open(input_file, 'r', newline='', encoding='utf-8') as infile:
        # Detect if the first line looks like headers or data
        sample = infile.read(1024)
        infile.seek(0)
        sniffer = csv.Sniffer()
        delimiter = sniffer.sniff(sample).delimiter

        reader = csv.DictReader(infile, delimiter=delimiter)
        rows = list(reader)

    print(f"Found {len(rows)} data rows to process.")
    print("-" * 40)

    processed_count = 0
    for i, row in enumerate(rows):
        print(f"Processing row {i+1}/{len(rows)}...")

        legacy_code = row.get(legacy_col, '')
        if not legacy_code:
            print(f"  Warning: Empty '{legacy_col}' in row {i+1}, skipping translation.")
            row[translated_col] = '' # Set translated column to empty if input is empty
            continue

        translated_code = translate_code(legacy_code)
        row[translated_col] = translated_code # Update the specific column

        processed_count += 1
        print(f"  Translated row {i+1}/{len(rows)} (processed {processed_count})")

        # Optional: Add a small delay to be nice to the API
        time.sleep(0.1) # Adjust as needed

    print("-" * 40)
    print(f"Finished processing {processed_count} rows.")

    print(f"Writing results to {output_file}...")
    with open(output_file, 'w', newline='', encoding='utf-8') as outfile:
        if rows:
            writer = csv.DictWriter(outfile, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
    print("Done writing output file.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Translate Fortran code in a CSV file using a local vLLM API.')
    parser.add_argument('input_csv', help='Path to the input CSV file')
    parser.add_argument('output_csv', help='Path to the output CSV file')
    parser.add_argument('--legacy-col', default='legacy_code', help='Name of the column containing legacy code (default: legacy_code)')
    parser.add_argument('--translated-col', default='mistral_translated_code', help='Name of the column to store translated code (default: mistral_translated_code)')

    args = parser.parse_args()

    if not os.path.isfile(args.input_csv):
        print(f"Error: Input file '{args.input_csv}' does not exist.")
        exit(1)

    process_csv(args.input_csv, args.output_csv, args.legacy_col, args.translated_col)
