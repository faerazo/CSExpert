#!/usr/bin/env python3
"""
Combined Course/Program Mapping Generator

This script scans syllabus PDFs and scrapes syllabus URLs to extract course codes
and associated program codes (e.g., N2COS, N2ADS). It generates two JSON files:
1. course_program_mapping.json: Maps each course code to its associated program codes.
2. program_course_mapping.json: Maps each program code to its associated course codes.

The script combines findings from both PDF analysis and URL scraping.
"""

import os
import re
import json
import argparse
import time
from pathlib import Path
from typing import Dict, List, Set, Tuple, DefaultDict
from collections import defaultdict

import PyPDF2
import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

# --- Default Configuration ---
DEFAULT_PDF_DIR = 'data/syllabi_pdfs'
DEFAULT_URLS_FILE = 'data/urls/filtered_syllabi_urls.txt' # Assuming filtered URLs are preferred
DEFAULT_COURSE_PROG_OUTPUT = 'data/json/course_program_mapping.json'
DEFAULT_PROG_COURSE_OUTPUT = 'data/json/program_course_mapping.json'
DEFAULT_PROGRAM_CODES = ['N2COS', 'N2ADS', 'N2SOF', 'N1SOF', 'N2GDT']

# --- Argument Parsing ---
def setup_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Generate course-program and program-course mappings from PDFs and URLs.')
    parser.add_argument('--pdf-dir', '-d',
                        default=DEFAULT_PDF_DIR,
                        help=f'Directory containing syllabus PDFs (default: {DEFAULT_PDF_DIR})')
    parser.add_argument('--urls-file', '-u',
                        default=DEFAULT_URLS_FILE,
                        help=f'File containing syllabus URLs (default: {DEFAULT_URLS_FILE})')
    parser.add_argument('--course-prog-output', '-cpo',
                        default=DEFAULT_COURSE_PROG_OUTPUT,
                        help=f'Output JSON for course->program mapping (default: {DEFAULT_COURSE_PROG_OUTPUT})')
    parser.add_argument('--prog-course-output', '-pco',
                        default=DEFAULT_PROG_COURSE_OUTPUT,
                        help=f'Output JSON for program->course mapping (default: {DEFAULT_PROG_COURSE_OUTPUT})')
    parser.add_argument('--program-codes', '-p',
                        nargs='+',
                        default=DEFAULT_PROGRAM_CODES,
                        help=f'Program codes to search for (default: {DEFAULT_PROGRAM_CODES})')
    parser.add_argument('--verbose', '-v',
                        action='store_true',
                        help='Print detailed information during processing')
    parser.add_argument('--delay', type=float, default=0.5,
                        help='Delay in seconds between URL requests (default: 0.5)')
    return parser.parse_args()

# --- PDF Processing Functions ---
def find_pdf_files(directory: str) -> List[str]:
    """Find all PDF files in a directory."""
    pdf_files = []
    if not os.path.isdir(directory):
        print(f"Warning: PDF directory '{directory}' not found.")
        return []
    try:
        for f in os.listdir(directory):
            if f.lower().endswith('.pdf'):
                full_path = os.path.join(directory, f)
                if os.path.isfile(full_path):
                    pdf_files.append(full_path)
    except OSError as e:
        print(f"Error reading PDF directory '{directory}': {e}")
    return pdf_files

def extract_course_code_from_filename(pdf_path: str) -> str:
    """Extract course code from PDF filename (assuming filename is course_code.pdf)."""
    filename = os.path.basename(pdf_path)
    course_code, _ = os.path.splitext(filename)
    return course_code.upper() # Standardize to upper case

def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract all text from a PDF file."""
    text = ""
    try:
        with open(pdf_path, 'rb') as f:
            pdf_reader = PyPDF2.PdfReader(f)
            for page in pdf_reader.pages:
                try:
                    text += page.extract_text() or "" # Ensure None returns empty string
                except Exception as page_e:
                    print(f"Warning: Could not extract text from a page in {pdf_path}: {page_e}")
    except FileNotFoundError:
        print(f"Error: PDF file not found at {pdf_path}")
    except PyPDF2.errors.PdfReadError as pdf_e:
        print(f"Error reading PDF file {pdf_path}: {pdf_e}")
    except Exception as e:
        print(f"Unexpected error extracting text from {pdf_path}: {e}")
    return text

def find_program_codes_in_text(text: str, program_codes: List[str]) -> Set[str]:
    """Find occurrences of program codes within a larger text body."""
    found_codes = set()
    text_upper = text.upper() # Case-insensitive search
    for code in program_codes:
        # Use regex to find whole word matches to avoid partial matches (e.g., N2COS in N2COSMOS)
        # \b matches word boundaries
        pattern = r'\b' + re.escape(code.upper()) + r'\b'
        if re.search(pattern, text_upper):
            found_codes.add(code) # Store original case
    return found_codes

def process_pdfs_for_mapping(pdf_files: List[str], program_codes: List[str], verbose: bool) -> DefaultDict[str, Set[str]]:
    """Process PDFs to map course codes to found program codes."""
    course_to_programs: DefaultDict[str, Set[str]] = defaultdict(set)
    print(f"\nProcessing {len(pdf_files)} PDF files...")
    for pdf_file in tqdm(pdf_files, desc="Processing PDFs"):
        course_code = extract_course_code_from_filename(pdf_file)
        if not course_code:
            if verbose: print(f"Warning: Could not extract course code from filename: {pdf_file}")
            continue

        pdf_text = extract_text_from_pdf(pdf_file)
        if not pdf_text:
            if verbose: print(f"Warning: No text extracted from {pdf_file}")
            continue

        found_program_codes = find_program_codes_in_text(pdf_text, program_codes)
        if found_program_codes:
            course_to_programs[course_code].update(found_program_codes)
            if verbose:
                print(f"PDF {course_code}: Found programs {', '.join(sorted(found_program_codes))}")

    return course_to_programs

# --- URL Processing Functions ---
def read_urls(file_path: str) -> List[str]:
    """Read URLs from a file, one URL per line."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            urls = [line.strip() for line in f if line.strip() and line.startswith('http')]
        return urls
    except FileNotFoundError:
        print(f"Error: URL file '{file_path}' not found.")
        return []
    except Exception as e:
        print(f"Error reading URL file '{file_path}': {e}")
        return []

def extract_course_code_from_url(url: str) -> str:
    """Extract course code from known GU URL patterns."""
    # Pattern 1: .../study-options/find-syllabus.../...course-code/syllabus
    # Pattern 2: .../study-gothenburg/course-name-course-code/syllabus
    patterns = [
        r'/([A-Z0-9]{3,8})/syllabus', # Often near the end
        r'-([a-zA-Z]{2,4}\d{3,5})/?(?:$|syllabus|#)' # Common pattern like DIT123
    ]
    for pattern in patterns:
        match = re.search(pattern, url, re.IGNORECASE)
        if match:
            return match.group(1).upper() # Standardize to upper case
    return ""

def scrape_program_codes_from_url(url: str, program_codes: List[str], verbose: bool, delay: float) -> Set[str]:
    """Scrape a single URL to find program codes in its text content."""
    found_codes = set()
    try:
        time.sleep(delay) # Politeness delay
        response = requests.get(url, timeout=15)
        response.raise_for_status() # Check for HTTP errors

        soup = BeautifulSoup(response.text, 'html.parser')
        page_text = soup.get_text()
        if not page_text:
             if verbose: print(f"Warning: No text content found at {url}")
             return set()

        found_codes = find_program_codes_in_text(page_text, program_codes)
        if verbose and found_codes:
            print(f"URL {url}: Found programs {', '.join(sorted(found_codes))}")

    except requests.exceptions.RequestException as e:
        print(f"Error fetching URL {url}: {e}")
    except Exception as e:
        print(f"Unexpected error scraping URL {url}: {e}")
    return found_codes

def process_urls_for_mapping(urls: List[str], program_codes: List[str], verbose: bool, delay: float) -> DefaultDict[str, Set[str]]:
    """Process URLs to map course codes to found program codes."""
    course_to_programs: DefaultDict[str, Set[str]] = defaultdict(set)
    print(f"\nProcessing {len(urls)} URLs...")
    for url in tqdm(urls, desc="Processing URLs"):
        course_code = extract_course_code_from_url(url)
        if not course_code:
            if verbose: print(f"Warning: Could not extract course code from URL: {url}")
            continue

        found_program_codes = scrape_program_codes_from_url(url, program_codes, verbose, delay)
        if found_program_codes:
            course_to_programs[course_code].update(found_program_codes)

    return course_to_programs

# --- Merging and Saving Functions ---
def merge_mappings(map1: DefaultDict[str, Set[str]], map2: DefaultDict[str, Set[str]]) -> DefaultDict[str, Set[str]]:
    """Merge two course-to-program mappings."""
    merged = map1.copy()
    for course_code, programs in map2.items():
        merged[course_code].update(programs)
    return merged

def invert_mapping(course_to_programs: DefaultDict[str, Set[str]]) -> DefaultDict[str, Set[str]]:
    """Convert course->programs mapping to program->courses mapping."""
    program_to_courses: DefaultDict[str, Set[str]] = defaultdict(set)
    for course_code, programs in course_to_programs.items():
        for program_code in programs:
            program_to_courses[program_code].add(course_code)
    return program_to_courses

def save_mapping_to_json(mapping_data: Dict, output_file: str, key_name: str, value_name: str) -> None:
    """Save mapping data to a JSON file in a structured list format."""
    output_list = []
    for key, values in mapping_data.items():
        if values: # Only include entries with associated values
            output_list.append({
                key_name: key,
                value_name: sorted(list(values)) # Store values as sorted list
            })

    # Sort the final list by the key (e.g., course_code or program_code)
    output_list.sort(key=lambda x: x[key_name])

    try:
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_list, f, indent=2, ensure_ascii=False)
        print(f"\nSaved mapping to {output_file}")
    except OSError as e:
        print(f"Error saving file {output_file}: {e}")
    except Exception as e:
        print(f"Unexpected error saving JSON to {output_file}: {e}")


# --- Main Execution ---
def main() -> None:
    """Main script execution logic."""
    args = setup_arguments()

    # --- PDF Processing ---
    pdf_files = find_pdf_files(args.pdf_dir)
    pdf_course_to_programs = process_pdfs_for_mapping(pdf_files, args.program_codes, args.verbose)

    # --- URL Processing ---
    urls = read_urls(args.urls_file)
    url_course_to_programs = process_urls_for_mapping(urls, args.program_codes, args.verbose, args.delay)

    # --- Merging Mappings ---
    print("\nMerging PDF and URL findings...")
    combined_course_to_programs = merge_mappings(pdf_course_to_programs, url_course_to_programs)
    print(f"Total unique courses found with program associations: {len(combined_course_to_programs)}")

    # --- Inverting Mapping ---
    print("Generating program-to-course mapping...")
    combined_program_to_courses = invert_mapping(combined_course_to_programs)
    print(f"Total unique programs found with course associations: {len(combined_program_to_courses)}")


    # --- Saving Outputs ---
    # Save Course -> Program mapping
    save_mapping_to_json(combined_course_to_programs, args.course_prog_output,
                         key_name="course_code", value_name="program_codes")

    # Save Program -> Course mapping
    save_mapping_to_json(combined_program_to_courses, args.prog_course_output,
                         key_name="program_code", value_name="course_codes")

    # --- Summary ---
    print("\n--- Final Summary ---")
    print(f"Processed {len(pdf_files)} PDF files from '{args.pdf_dir}'.")
    print(f"Processed {len(urls)} URLs from '{args.urls_file}'.")
    print(f"Found {len(combined_course_to_programs)} courses mapped to programs.")
    print(f"Found {len(combined_program_to_courses)} programs mapped to courses.")
    print(f"Course->Program mapping saved to '{args.course_prog_output}'")
    print(f"Program->Course mapping saved to '{args.prog_course_output}'")
    print("\nMapping generation complete!")

if __name__ == "__main__":
    main() 