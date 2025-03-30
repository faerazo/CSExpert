#!/usr/bin/env python3
"""
Program-Course Code Mapping Generator

This script scans filtered PDFs, extracts course codes and program codes (N2COS, N2ADS, etc.),
and generates a JSON file mapping each program code to all its associated course codes.
"""

import os
import re
import json
import argparse
from pathlib import Path
from typing import Dict, List, Set, Tuple

import PyPDF2
from tqdm import tqdm


# Default directories and files
DEFAULT_PDF_DIR = 'data/syllabi_pdfs'
DEFAULT_OUTPUT_FILE = 'data/json/program_course_mapping.json'

# Program codes to look for
PROGRAM_CODES = ['N2COS', 'N2ADS', 'N2SOF', 'N1SOF', 'N2GDT']


def setup_arguments() -> argparse.Namespace:
    """
    Parse command line arguments.
    
    Returns:
        argparse.Namespace: Parsed arguments
    """
    parser = argparse.ArgumentParser(description='Generate program-course code mapping from PDFs.')
    parser.add_argument('--pdf-dir', '-d',
                        default=DEFAULT_PDF_DIR,
                        help=f'Directory containing filtered PDFs (default: {DEFAULT_PDF_DIR})')
    parser.add_argument('--output-file', '-o',
                        default=DEFAULT_OUTPUT_FILE,
                        help=f'Output JSON file path (default: {DEFAULT_OUTPUT_FILE})')
    parser.add_argument('--verbose', '-v',
                        action='store_true',
                        help='Print detailed information during processing')
    return parser.parse_args()


def find_pdf_files(directory: str) -> List[str]:
    """
    Find all PDF files in a directory.
    
    Args:
        directory: Directory to search
        
    Returns:
        List[str]: List of PDF file paths
    """
    return [os.path.join(directory, f) for f in os.listdir(directory) 
            if f.lower().endswith('.pdf') and os.path.isfile(os.path.join(directory, f))]


def extract_course_code_from_filename(pdf_path: str) -> str:
    """
    Extract course code from PDF filename.
    
    Args:
        pdf_path: Path to the PDF file
        
    Returns:
        str: Course code
    """
    # Get filename without extension
    filename = os.path.basename(pdf_path)
    course_code = os.path.splitext(filename)[0]
    return course_code


def extract_text_from_pdf(pdf_path: str) -> str:
    """
    Extract text from a PDF file.
    
    Args:
        pdf_path: Path to the PDF file
        
    Returns:
        str: Extracted text
    """
    text = ""
    
    try:
        with open(pdf_path, 'rb') as f:
            pdf_reader = PyPDF2.PdfReader(f)
            for page_num in range(len(pdf_reader.pages)):
                page = pdf_reader.pages[page_num]
                text += page.extract_text()
    except Exception as e:
        print(f"Error extracting text from {pdf_path}: {e}")
    
    return text


def extract_program_codes(pdf_path: str, program_codes: List[str]) -> Set[str]:
    """
    Extract program codes from a PDF file.
    
    Args:
        pdf_path: Path to the PDF file
        program_codes: List of program codes to look for
        
    Returns:
        Set[str]: Set of found program codes
    """
    try:
        pdf_text = extract_text_from_pdf(pdf_path)
        
        # Convert to uppercase for case-insensitive matching
        pdf_text_upper = pdf_text.upper()
        
        # Check for program codes
        found_codes = set()
        for code in program_codes:
            if code.upper() in pdf_text_upper:
                found_codes.add(code)
        
        return found_codes
    
    except Exception as e:
        print(f"Error processing {pdf_path}: {e}")
        return set()


def process_pdfs(pdf_files: List[str], program_codes: List[str], verbose: bool = False) -> List[Dict]:
    """
    Process PDFs to extract course codes and program codes, then create inverse mapping.
    
    Args:
        pdf_files: List of PDF file paths
        program_codes: List of program codes to look for
        verbose: Whether to print detailed information
        
    Returns:
        List[Dict]: List of dictionaries with program_code and course_codes fields
    """
    # Initialize a dictionary to map program codes to course codes
    program_to_courses = {code: [] for code in program_codes}
    
    print(f"\nProcessing {len(pdf_files)} PDFs to extract program codes...")
    
    for pdf_file in tqdm(pdf_files, desc="Processing PDFs"):
        course_code = extract_course_code_from_filename(pdf_file)
        found_program_codes = extract_program_codes(pdf_file, program_codes)
        
        if found_program_codes:
            # Add this course to each program's list
            for program_code in found_program_codes:
                program_to_courses[program_code].append(course_code)
            
            if verbose:
                print(f"Found program codes in {course_code}: {', '.join(found_program_codes)}")
    
    # Convert mapping to list of entries with a single entry per program
    program_course_entries = []
    for program_code, courses in program_to_courses.items():
        if courses:  # Only include programs that have courses
            entry = {
                "program_code": program_code,
                "course_codes": sorted(courses)
            }
            program_course_entries.append(entry)
    
    return program_course_entries


def save_mapping_to_json(entries: List[Dict], output_file: str) -> None:
    """
    Save program-course mapping to JSON file.
    
    Args:
        entries: List of dictionaries with program_code and course_codes fields
        output_file: Output JSON file path
    """
    # Ensure directory exists
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    # Sort entries by program_code for readability
    sorted_entries = sorted(entries, key=lambda x: x["program_code"])
    
    with open(output_file, 'w') as f:
        json.dump(sorted_entries, f, indent=2)
    
    print(f"\nSaved mapping to {output_file}")


def main() -> None:
    """Main entry point of the script."""
    args = setup_arguments()
    
    print(f"Looking for PDF files in {args.pdf_dir}...")
    pdf_files = find_pdf_files(args.pdf_dir)
    
    if not pdf_files:
        print("No PDF files found. Exiting.")
        return
    
    print(f"Found {len(pdf_files)} PDF files.")
    
    # Process PDFs to create program-to-course mapping
    entries = process_pdfs(pdf_files, PROGRAM_CODES, args.verbose)
    
    # Save mapping to JSON file
    save_mapping_to_json(entries, args.output_file)
    
    # Print summary
    print("\n--- Summary ---")
    print(f"Total PDFs processed: {len(pdf_files)}")
    print(f"Total programs with courses: {len(entries)}")
    
    # Print sample stats of mapping if verbose
    if args.verbose and entries:
        print("\nProgram statistics:")
        for entry in entries:
            program = entry["program_code"]
            course_count = len(entry["course_codes"])
            print(f"  - {program}: {course_count} courses")


if __name__ == "__main__":
    main() 