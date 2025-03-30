#!/usr/bin/env python3
"""
Course-Program Code Mapping Generator

This script scans filtered PDFs, extracts course codes and program codes (N2COS, N2ADS, etc.),
and generates a JSON file mapping each course code to its associated program codes.
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
DEFAULT_OUTPUT_FILE = 'data/json/course_program_mapping.json'

# Program codes to look for
PROGRAM_CODES = ['N2COS', 'N2ADS', 'N2SOF', 'N1SOF', 'N2GDT']


def setup_arguments() -> argparse.Namespace:
    """
    Parse command line arguments.
    
    Returns:
        argparse.Namespace: Parsed arguments
    """
    parser = argparse.ArgumentParser(description='Generate course-program code mapping from PDFs.')
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
    Process PDFs to extract course codes and program codes.
    
    Args:
        pdf_files: List of PDF file paths
        program_codes: List of program codes to look for
        verbose: Whether to print detailed information
        
    Returns:
        List[Dict]: List of dictionaries with course_code and program_code fields
    """
    course_program_entries = []
    course_program_mapping = {}
    
    print(f"\nProcessing {len(pdf_files)} PDFs to extract program codes...")
    
    for pdf_file in tqdm(pdf_files, desc="Processing PDFs"):
        course_code = extract_course_code_from_filename(pdf_file)
        found_program_codes = extract_program_codes(pdf_file, program_codes)
        
        if found_program_codes:
            # Store found program codes for each course
            course_program_mapping[course_code] = found_program_codes
            
            if verbose:
                print(f"Found program codes in {course_code}: {', '.join(found_program_codes)}")
    
    # Convert mapping to list of entries with a single entry per course
    for course_code, found_codes in course_program_mapping.items():
        entry = {
            "course_code": course_code,
            "program_code": ", ".join(sorted(found_codes))
        }
        course_program_entries.append(entry)
    
    return course_program_entries


def save_mapping_to_json(entries: List[Dict], output_file: str) -> None:
    """
    Save course-program mapping to JSON file.
    
    Args:
        entries: List of dictionaries with course_code and program_code fields
        output_file: Output JSON file path
    """
    # Ensure directory exists
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    # Sort entries by course_code for readability
    sorted_entries = sorted(entries, key=lambda x: x["course_code"])
    
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
    
    # Process PDFs to extract course codes and program codes
    entries = process_pdfs(pdf_files, PROGRAM_CODES, args.verbose)
    
    # Save mapping to JSON file
    save_mapping_to_json(entries, args.output_file)
    
    # Print summary
    print("\n--- Summary ---")
    print(f"Total PDFs processed: {len(pdf_files)}")
    
    # Calculate unique courses
    unique_courses = len(set(entry["course_code"] for entry in entries))
    print(f"Total unique courses: {unique_courses}")
    print(f"Total course-program mappings: {len(entries)}")
    
    # Print sample of mapping if verbose
    if args.verbose and entries:
        print("\nSample of mapping:")
        seen_courses = set()
        sample_entries = []
        
        for entry in entries:
            if entry["course_code"] not in seen_courses and len(sample_entries) < 5:
                sample_entries.append(entry)
                seen_courses.add(entry["course_code"])
        
        for entry in sample_entries:
            print(f"  - {entry['course_code']}: {entry['program_code']}")


if __name__ == "__main__":
    main() 