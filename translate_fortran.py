# translate_fortran.pyimport requests
import requests
import csv
import time
import argparse
import os
# --- Configuration ---
# Read API_URL from environment variable, default to localhost
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
external to use: An external <name> declaration (and its associated type declaration, e.g., integer fndbk) must be replaced with a USE statement (e.g., use :: fndbk_mod).
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

""" 



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
            {"role": "user", "content": f"Translate this legacy Fortran code to modern Fortran:(Give me only translated code without explanation like a text) \nLegacy Code:{code_snippet}"}
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

PHARO_URL = "http://localhost:8080/chrf"

def get_chrf_score(candidate, reference):
    """Calls the Pharo API to get the ChRF score."""
    if not candidate or not reference:
        return 0.0
    
    payload = {
        "candidates": [candidate],
        "references": [[reference]] # Pharo expects list of lists
    }
    try:
        # Timeout of 2 seconds to keep the loop moving
        response = requests.post(PHARO_URL, json=payload, timeout=2)
        if response.status_code == 200:
            return response.json().get('chrf_score', -1.0)
    except Exception as e:
        print(f"  [Scoring Error] Pharo not responding: {e}")
    return -1.0

def process_csv(input_file, output_file, legacy_col, translated_col):
    rows = []
    with open(input_file, 'r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter=';')
        fieldnames = list(reader.fieldnames)
        rows = list(reader)

    score_col = f"{translated_col}_score"
    if translated_col not in fieldnames: fieldnames.append(translated_col)
    if score_col not in fieldnames: fieldnames.append(score_col)

    for row in rows:
        legacy = row.get(legacy_col, '')
        ref = row.get('Reference', '') # Ensure column name matches exactly
        
        if legacy:
            print(f"Translating and Scoring...")
            # 1. Translate via vLLM
            translation = translate_code(legacy) 
            # 2. Score via Pharo
            score = get_chrf_score(translation, ref)
            
            row[translated_col] = translation
            row[score_col] = str(score)

    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=';')
        writer.writeheader()
        writer.writerows(rows)


#def process_csv(input_file, output_file, legacy_col='legacy_code', translated_col='translated_code'):
 #   print(f"Loading: {input_file} (Delimiter: ;)")
    
  #  rows = []
   # fieldnames = []
    
#    with open(input_file, 'r', newline='', encoding='utf-8') as infile:
#        # We specify delimiter=';' to match your file format
#        reader = csv.DictReader(infile, delimiter=';', restkey='extra_cols')
#        fieldnames = list(reader.fieldnames) if reader.fieldnames else []
#        rows = list(reader)

    # Define the new columns
#    score_col = f"{translated_col}_score"
    
    # Ensure new columns are in the fieldnames list
 #   if translated_col not in fieldnames:
#        fieldnames.append(translated_col)
#    if score_col not in fieldnames:
#        fieldnames.append(score_col)

#    for i, row in enumerate(rows):
        # Safety: Clean up any dictionary keys that aren't strings
        # This prevents the 'ValueError: ... None' crash
#        keys_to_fix = [k for k in row.keys() if k is None or k == 'extra_cols']
#        for k in keys_to_fix:
#            del row[k]

#        legacy_code = row.get(legacy_col, '')
        
#        if not legacy_code:
#            row[translated_col] = ''
#            row[score_col] = ''
#            continue

#        print(f"  [{i+1}/{len(rows)}] Translating for {translated_col}...")
#        translated_code = translate_code(legacy_code)
        
#        row[translated_col] = translated_code
#        row[score_col] = ""

    # Write back using the same semicolon delimiter
#    with open(output_file, 'w', newline='', encoding='utf-8') as outfile:
#        writer = csv.DictWriter(outfile, fieldnames=fieldnames, delimiter=';', extrasaction='ignore')
#        writer.writeheader()
#        writer.writerows(rows)
    
#    print(f"Successfully updated {output_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Translate Fortran code in a CSV file using a local vLLM API.')
    parser.add_argument('input_csv', help='Path to the input CSV file')
    parser.add_argument('output_csv', help='Path to the output CSV file')
    parser.add_argument('--legacy-col', default='legacy_code', help='Name of the column containing legacy code (default: legacy_code)')
    parser.add_argument('--translated-col', default='qwen_translated_code', help='Name of the column to store translated code (default: mistral_translated_code)')

    args = parser.parse_args()

    if not os.path.isfile(args.input_csv):
        print(f"Error: Input file '{args.input_csv}' does not exist.")
        exit(1)

    process_csv(args.input_csv, args.output_csv, args.legacy_col, args.translated_col)
