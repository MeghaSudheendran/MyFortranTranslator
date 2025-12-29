import requests
import csv
import time
import argparse
import os
import json
import re

# --- Configuration ---
API_URL = os.getenv("API_URL", "http://localhost:8000/v1/chat/completions")
MODEL = os.getenv("MODEL_ID", "")

SYSTEM_PROMPT = """
You are given Fortran 77 code that may contain ESOPE extensions.
ESOPE is an extension of Fortran designed for structured memory management, based on the concept of segments (SEGMENT, SEGINI, SEGACT, SEGDES, SEGSUP, SEGADJ, etc.) and pointers (POINTEUR).
The goal is to translate this legacy ESOPE-Fortran code into modern Fortran (Fortran 2008).
You must follow the strict translation rules and patterns demonstrated in the examples below.

Translation Rules
1. Module and Procedure Structure
Module Creation: A standalone SUBROUTINE or FUNCTION (e.g., subroutine newbk) must be converted into a MODULE(e.g., module newbk_mod).
Contains: The original procedure must be placed inside the CONTAINS section of the new module.
Implicit Typing: IMPLICIT NONE must be enforced in all modules and procedures.

2. Declarations and Dependencies
external to use: An external <n> declaration (and its associated type declaration, e.g., integer fndbk) must be replaced with a USE statement (e.g., use :: fndbk_mod).
POINTEUR:
pointeur lib.PSTR → type(str), pointer :: lib
pointeur <var>.<seg> → type(<seg>), pointer :: <var>
INTENT: All procedure arguments must be given an INTENT attribute (e.g., intent(in), intent(out), intent(inout)).
For POINTEUR arguments that are initialized or modified, intent(inout) is appropriate.
Includes:
#include "PSTR.inc" → ! [ooo] empty #include PSTR.inc
#include "tlib.seg" → Keep the include comments, but add local declarations for the segment's members (e.g., integer :: brcnt, integer :: urcnt).

3. ESOPE Command and Syntax Translation
Pointer Access: Convert ESOPE dot-notation to standard Fortran percent-notation.
lb.bref → lb % bref
Array Sizing: Convert ESOPE slash-notation to the SIZE intrinsic.
lb.bref(/1) → size(lb % bref, 1)
mypnt Function: Convert the generic mypnt call to a typed pointer assignment (=>) using the specific function for that type.
lb = mypnt(lib,1) → lb => tlib_mypnt(lib, 1)
ur = mypnt(lib, lb.uref(iur)) → ur => user_mypnt(lib, lb % uref(iur))
Memory Allocation (segini): The segini macro must be translated to a subroutine call that explicitly passes the segment's dimensioning variables.
segini, ur → call segini(ur, ubbcnt)
Memory Resizing (segadj): The segadj macro must also be translated to a call passing the new dimensioning variables.
segadj, ur → call segadj(ur, ubbcnt)
segadj, lb → call segadj(lb, brcnt, urcnt)

4. Obsolete and Unused Code
Obsolete Macros: All obsolete memory/state management macros must be commented out and tagged ! [ooo].obsolete:. This includes:
call oooeta(...)
call actstr(...)
segact ...
segdes ...
call desstr(...)
Unused Variables: If an ESOPE bookkeeping variable (like libeta) becomes unused after translation, mark its declaration with ! [ooo].not-used:.

Example 1 ESOPE+Fortran:
c arguments
      pointeur lib.pstr
      character*(*) title
c local variables
      pointeur bk.book

Example 1 Fortran 2008:
! arguments
type(str), pointer, intent(in) :: lib
character(len=*), intent(in) :: title
! local variables
type(book), pointer :: bk

Example 2 ESOPE+Fortran:
subroutine borbk(lib, name, title)
       implicit none
#include "PSTR.inc"
c external functions
       external fndbk 
       integer fndbk

Example 2 Fortran 2008:
module borbk_mod
  use :: str_mod
  use :: fndur_mod
  use :: fndbk_mod
  ...
  implicit none
contains
  subroutine borbk(lib, name, title)
    ! [ooo] empty #include PSTR.inc
    ! external functions

Example 3 ESOPE+Fortran:
bk = mypnt(lib, lb.bref(ibk2))
segact, bk

Example 3 Fortran 2008:
bk => book_mypnt(lib, lb % bref(ibk2))
! [ooo].obsolete: segact,bk

Example 4 ESOPE+Fortran:
brcnt = lb.bref(/1)

Example 4 Fortran 2008:
brcnt = size(lb % bref, 1)

Example 5 ESOPE+Fortran:
title2 = bk.btitle
segdes, bk*NOMOD

Example 5 Fortran 2008:
title2 = bk % btitle
! [ooo].obsolete: segdes,bk

Example 6 ESOPE+Fortran:
ubbcnt = ur.ubb(/1)
ubbcnt = ubbcnt + 1
segadj, ur
ur.ubb(ubbcnt) = ibk

Example 6 Fortran 2008:
ubbcnt = size(ur % ubb, 1)
ubbcnt = ubbcnt + 1
call segadj(ur, ubbcnt)
ur % ubb(ubbcnt) = ibk

Example 7 ESOPE+Fortran:
c local variables    
      integer libeta
...
      call oooeta(lib, libeta)
      call actstr(lib)
...
c deactivate the structure if activated on entry
      if(libeta.ne.1) call desstr(lib,'MOD')

Example 7 Fortran 2008:
! local variables    
    ! [ooo].not-used: integer :: libeta
...
    ! [ooo].obsolete: call oooeta(lib,libeta)
    ! [ooo].obsolete: call actstr(lib)
...
    ! deactivate the structure if activated on entry
    ! [ooo].empty-var: if (libeta /= 1) ! [ooo].obsolete: call desstr(lib,'MOD')

Example 8 ESOPE+Fortran:
if (title2 .eq. title1) then
Example 8 Fortran 2008:
if (title2 == title1) then

IMPORTANT: You must respond ONLY with valid JSON in this exact format:
{
  "translated_code": "the translated Fortran 2008 code here"
}

Do not include any text before or after the JSON. Do not wrap the JSON in markdown code blocks.
"""


def extract_code_from_json(response_text):
    """
    Extract translated code from LLM response by parsing JSON.
    """
    response_text = response_text.strip()
    
    # Method 1: Direct JSON parse
    try:
        data = json.loads(response_text)
        if 'translated_code' in data:
            return data['translated_code'].strip()
    except json.JSONDecodeError:
        pass
    
    # Method 2: JSON in markdown blocks
    json_pattern = r'```(?:json)?\s*(\{.*?\})\s*```'
    matches = re.findall(json_pattern, response_text, re.DOTALL)
    if matches:
        try:
            data = json.loads(matches[0])
            if 'translated_code' in data:
                return data['translated_code'].strip()
        except json.JSONDecodeError:
            pass
    
    # Method 3: Extract value using regex
    value_pattern = r'"translated_code"\s*:\s*"((?:[^"\\]|\\.)*)"'
    matches = re.findall(value_pattern, response_text, re.DOTALL)
    if matches:
        code = matches[0]
        code = code.replace('\\"', '"')
        code = code.replace('\\n', '\n')
        code = code.replace('\\t', '\t')
        return code.strip()
    
    # Method 4: Find JSON with brace matching
    if '"translated_code"' in response_text:
        brace_count = 0
        start_idx = -1
        
        for i, char in enumerate(response_text):
            if char == '{':
                if brace_count == 0:
                    start_idx = i
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0 and start_idx != -1:
                    try:
                        json_str = response_text[start_idx:i+1]
                        data = json.loads(json_str)
                        if 'translated_code' in data:
                            return data['translated_code'].strip()
                    except json.JSONDecodeError:
                        continue
    
    # Method 5: Extract from code blocks
    code_pattern = r'```(?:fortran)?\s*(.*?)\s*```'
    code_matches = re.findall(code_pattern, response_text, re.DOTALL | re.IGNORECASE)
    if code_matches:
        return code_matches[0].strip()
    
    # Method 6: Strip JSON wrapper manually
    if response_text.startswith('{'):
        cleaned = re.sub(r'^\s*\{\s*"translated_code"\s*:\s*"', '', response_text)
        cleaned = re.sub(r'"\s*\}\s*$', '', cleaned)
        cleaned = cleaned.replace('\\"', '"')
        cleaned = cleaned.replace('\\n', '\n')
        cleaned = cleaned.replace('\\t', '\t')
        if cleaned != response_text and len(cleaned) > 0:
            return cleaned.strip()
    
    # Last resort
    return response_text.strip()


def translate_code(code_snippet, temperature=0.1, max_tokens=2048, max_retries=3, delay=1):
    """
    Calls the vLLM API to translate a single code snippet.
    """
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user", 
                "content": f"Translate this legacy Fortran code to modern Fortran. Respond with JSON only.\n\nLegacy Code:\n{code_snippet}"
            }
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    for attempt in range(max_retries):
        try:
            response = requests.post(API_URL, json=payload, timeout=300)
            response.raise_for_status()
            data = response.json()
            
            full_response = data['choices'][0]['message']['content']
            translated_code = extract_code_from_json(full_response)
            
            return translated_code
            
        except requests.exceptions.RequestException as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(delay * (2 ** attempt))
            else:
                return f"Error translating: {str(e)}"
        except Exception as e:
            print(f"Unexpected error: {e}")
            return f"Error: {str(e)}"



def process_csv(input_file, output_file, legacy_col='legacy_code', 
                translated_col='translated_code', temperature=0.1, max_tokens=2048):
    """
    Process CSV file with code translation.
    """
    print(f"Loading: {input_file}")
    
    rows = []
    fieldnames = []
    
    with open(input_file, 'r', newline='', encoding='utf-8') as infile:
        reader = csv.DictReader(infile, delimiter=';', restkey='extra_cols')
        fieldnames = list(reader.fieldnames) if reader.fieldnames else []
        rows = list(reader)

    score_col = f"{translated_col}_score"
    
    if translated_col not in fieldnames:
        fieldnames.append(translated_col)
    if score_col not in fieldnames:
        fieldnames.append(score_col)

    for i, row in enumerate(rows):
        keys_to_fix = [k for k in row.keys() if k is None or k == 'extra_cols']
        for k in keys_to_fix:
            del row[k]

        legacy_code = row.get(legacy_col, '')
        
        if not legacy_code:
            row[translated_col] = ''
            row[score_col] = ''
            continue

        print(f"  [{i+1}/{len(rows)}] Translating for {translated_col}...")
        translated_code = translate_code(
            legacy_code, 
            temperature=temperature, 
            max_tokens=max_tokens
        )
        
        row[translated_col] = translated_code
        row[score_col] = ''

    with open(output_file, 'w', newline='', encoding='utf-8') as outfile:
        writer = csv.DictWriter(outfile, fieldnames=fieldnames, delimiter=';', extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
    
    print(f"Successfully updated {output_file}")






if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Translate Fortran code using vLLM API with JSON responses.'
    )
    parser.add_argument('input_csv', help='Path to the input CSV file')
    parser.add_argument('output_csv', help='Path to the output CSV file')
    parser.add_argument('--legacy-col', default='legacy_code', 
                        help='Column containing legacy code (default: legacy_code)')
    parser.add_argument('--translated-col', default='translated_code', 
                        help='Column for translated code (default: translated_code)')
    parser.add_argument('--temperature', type=float, default=0.1,
                        help='Temperature for generation (default: 0.1)')
    parser.add_argument('--max-tokens', type=int, default=2048,
                        help='Maximum tokens for generation (default: 2048)')

    args = parser.parse_args()

    if not os.path.isfile(args.input_csv):
        print(f"Error: Input file '{args.input_csv}' does not exist.")
        exit(1)

    process_csv(
        args.input_csv, 
        args.output_csv, 
        args.legacy_col, 
        args.translated_col,
        args.temperature,
        args.max_tokens
    )
