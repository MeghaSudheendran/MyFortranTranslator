import requests
import csv
import time
import argparse
import os
import json
import re

# --- Configuration ---
API_URL = os.getenv("API_URL", "http://localhost:8000/v1/chat/completions")
MODEL = os.getenv("MODEL_ID", "gpt-3.5-turbo")

SYSTEM_PROMPT = """
You are an expert Fortran programmer. You are given Fortran 77 code that contains ESOPE extensions.
The goal is to translate this legacy ESOPE-Fortran code into modern Fortran (Fortran 2008).

Translation Rules:
1. Module/Procedure: Standalone SUBROUTINE/FUNCTION -> MODULE containing the procedure. IMPLICIT NONE is required.
2. Dependencies: external <name> -> use :: <name>_mod
3. Syntax: lb.bref -> lb % bref, segini -> call segini, etc.
4. Obsolete: segact, segdes -> Comment out with ! [ooo].obsolete:

Output Format:
You must return a JSON object with the key "translated_code".
IMPORTANT: Because the value is a code string, you MUST escape all double quotes (\") and newlines (\\n) inside the string.
"""


def calculate_dynamic_max_tokens(code_snippet):
    input_len = len(code_snippet)
    # Give plenty of space to avoid cut-off JSON
    estimated_output_tokens = int((input_len / 4) * 1.5) + 500
    return min(estimated_output_tokens, 4096)


def robust_json_extractor(raw_text):
    """
    Tries to parse JSON. If strict parsing fails, it uses Regex
    to grab the content of "translated_code" even if syntax is slightly broken.
    """
    text = raw_text.strip()

    # 1. Try Standard JSON Parsing
    # Clean markdown wrappers first
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"): text = text[:-3]
    text = text.strip()

    try:
        data = json.loads(text)
        return data.get("translated_code", "")
    except json.JSONDecodeError:
        pass  # Fall through to regex method

    # 2. Regex Fallback (The "dirty" fix)
    # This looks for: "translated_code": " ... "
    # It handles cases where the model used real newlines instead of \n
    match = re.search(r'"translated_code"\s*:\s*"(.*?)"\s*}', text, re.DOTALL)
    if match:
        code_content = match.group(1)
        # Attempt to unescape standard JSON escapes manually if needed
        code_content = code_content.replace('\\"', '"').replace('\\n', '\n')
        return code_content

    # 3. Last Resort: It might just be raw code
    # If the output looks like a module or program, just take it.
    if "module " in text.lower() or "program " in text.lower() or "subroutine " in text.lower():
        return text

    # If all else fails
    raise ValueError("Could not extract code from response.")


def translate_code(code_snippet, max_retries=3, delay=1):
    max_tok = calculate_dynamic_max_tokens(code_snippet)

    user_content = f"""
Translate this legacy code to modern Fortran.
Return JSON format: {{ "translated_code": "YOUR_CODE_HERE" }}

Legacy Code:
{code_snippet}
"""

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content}
        ],
        "temperature": 0.1,
        "max_tokens": max_tok,
        # Note: I removed 'response_format' because it causes errors on some
        # non-OpenAI models if they can't perfectly guarantee JSON.
    }

    for attempt in range(max_retries):
        try:
            response = requests.post(API_URL, json=payload, timeout=300)
            response.raise_for_status()

            data = response.json()
            raw_content = data['choices'][0]['message']['content']

            # USE THE ROBUST EXTRACTOR
            translated_code = robust_json_extractor(raw_content)

            if not translated_code:
                raise ValueError("Extracted code was empty")

            return translated_code

        except (ValueError, json.JSONDecodeError) as e:
            print(f"  Attempt {attempt + 1}: Parsing failed ({str(e)}). Retrying...")
            if attempt == max_retries - 1:
                return f"! Error: Failed to parse response. Raw: {raw_content[:50]}..."
        except requests.exceptions.RequestException as e:
            print(f"  Attempt {attempt + 1} network error: {e}")
            if attempt < max_retries - 1:
                time.sleep(delay * (2 ** attempt))
            else:
                return f"! Error: Network Request Failed: {str(e)}"
        except Exception as e:
            return f"! Error: Unexpected: {str(e)}"


def process_csv(input_file, output_file, legacy_col, translated_col):
    print(f"Reading: {input_file}")
    print(f"Writing: {output_file}")

    rows = []
    with open(input_file, 'r', newline='', encoding='utf-8') as infile:
        sample = infile.read(1024)
        infile.seek(0)
        sniffer = csv.Sniffer()
        try:
            delimiter = sniffer.sniff(sample).delimiter
        except:
            delimiter = ','

        reader = csv.DictReader(infile, delimiter=delimiter)
        rows = list(reader)

    fieldnames = list(rows[0].keys())
    if translated_col not in fieldnames:
        fieldnames.append(translated_col)

    processed_count = 0
    with open(output_file, 'w', newline='', encoding='utf-8') as outfile:
        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        writer.writeheader()

        for i, row in enumerate(rows):
            print(f"Processing row {i + 1}/{len(rows)}...")

            legacy_code = row.get(legacy_col, '')

            if not legacy_code or len(legacy_code.strip()) == 0:
                row[translated_col] = ''
            else:
                row[translated_col] = translate_code(legacy_code)
                processed_count += 1

            writer.writerow(row)
            # time.sleep(0.1) # Uncomment if you need rate limiting

    print("-" * 40)
    print(f"Done. Processed {processed_count} rows.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Translate Fortran CSV (Robust).')
    parser.add_argument('input_csv', help='Path to input CSV')
    parser.add_argument('output_csv', help='Path to output CSV')
    parser.add_argument('--legacy-col', default='legacy_code', help='Column name for input code')
    parser.add_argument('--translated-col', default='translated_code', help='Column name for output code')

    args = parser.parse_args()

    if not os.path.isfile(args.input_csv):
        print(f"Error: Input file '{args.input_csv}' not found.")
        exit(1)

    process_csv(args.input_csv, args.output_csv, args.legacy_col, args.translated_col)