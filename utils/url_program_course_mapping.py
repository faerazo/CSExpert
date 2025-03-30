#!/usr/bin/env python3
"""
URL Program-Course Mapping Generator

This script reads filtered syllabus URLs, scrapes them to find program codes,
and generates a JSON file mapping each program code to all its associated courses.
"""

import os
import re
import json
import argparse
from pathlib import Path
from typing import Dict, List, Set, Tuple
import requests
from bs4 import BeautifulSoup
from tqdm import tqdm


# Default files
DEFAULT_URLS_FILE = 'data/urls/filtered_syllabi_urls.txt'
DEFAULT_OUTPUT_FILE = 'data/json/url_program_course_mapping.json'

# Program codes to look for
DEFAULT_PROGRAM_CODES = ['N2COS', 'N2ADS', 'N2SOF', 'N1SOF', 'N2GDT']


def setup_arguments() -> argparse.Namespace:
    """
    Parse command line arguments.
    
    Returns:
        argparse.Namespace: Parsed arguments
    """
    parser = argparse.ArgumentParser(description='Generate program-course mapping from syllabus URLs.')
    parser.add_argument('--urls-file', '-u',
                        default=DEFAULT_URLS_FILE,
                        help=f'File containing filtered URLs (default: {DEFAULT_URLS_FILE})')
    parser.add_argument('--output-file', '-o',
                        default=DEFAULT_OUTPUT_FILE,
                        help=f'Output JSON file path (default: {DEFAULT_OUTPUT_FILE})')
    parser.add_argument('--program-codes', '-p',
                        nargs='+',
                        default=DEFAULT_PROGRAM_CODES,
                        help=f'Program codes to search for (default: {DEFAULT_PROGRAM_CODES})')
    parser.add_argument('--verbose', '-v',
                        action='store_true',
                        help='Print detailed information during processing')
    return parser.parse_args()


def read_urls(file_path: str) -> List[str]:
    """
    Read URLs from a file.
    
    Args:
        file_path: Path to the file containing URLs
        
    Returns:
        List[str]: List of URLs
    """
    try:
        with open(file_path, 'r') as f:
            urls = [line.strip() for line in f if line.strip()]
        return urls
    except FileNotFoundError:
        print(f"Error: File '{file_path}' not found.")
        return []


def extract_course_code_from_url(url: str) -> str:
    """
    Extract course code from URL.
    
    Args:
        url: URL of the syllabus page
        
    Returns:
        str: Course code or empty string if not found
    """
    # Extract the course code from the URL pattern
    # URL format: https://www.gu.se/en/study-gothenburg/[course-name]-[course-code]/syllabus/[id]
    pattern = r'https://www\.gu\.se/en/study-gothenburg/.*?-([a-zA-Z0-9]+)/syllabus/'
    match = re.search(pattern, url)
    
    if match:
        return match.group(1).upper()
    
    # Alternative pattern that might appear in some URLs
    alt_pattern = r'/([a-zA-Z0-9]{3,8})/syllabus/'
    alt_match = re.search(alt_pattern, url)
    
    if alt_match:
        return alt_match.group(1).upper()
    
    return ""


def scrape_program_codes(url: str, program_codes: List[str], verbose: bool) -> Set[str]:
    """
    Scrape the URL and extract program codes.
    
    Args:
        url: URL to scrape
        program_codes: List of program codes to look for
        verbose: Whether to print detailed information
        
    Returns:
        Set[str]: Set of found program codes
    """
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        # Get all text from the page
        page_text = soup.get_text()
        
        # Convert to uppercase for case-insensitive matching
        page_text_upper = page_text.upper()
        
        # Check for program codes
        found_codes = set()
        for code in program_codes:
            if code.upper() in page_text_upper:
                found_codes.add(code)
        
        if verbose and found_codes:
            print(f"Found program codes in {url}: {', '.join(found_codes)}")
        
        return found_codes
    
    except Exception as e:
        print(f"Error processing {url}: {e}")
        return set()


def process_urls(urls: List[str], program_codes: List[str], verbose: bool = False) -> Dict[str, List[str]]:
    """
    Process URLs to extract course codes and program codes.
    
    Args:
        urls: List of URLs to process
        program_codes: List of program codes to look for
        verbose: Whether to print detailed information
        
    Returns:
        Dict[str, List[str]]: Dictionary mapping program codes to course codes
    """
    # Initialize a dictionary to map program codes to course codes
    program_to_courses = {code: [] for code in program_codes}
    
    print(f"\nProcessing {len(urls)} URLs to extract program codes...")
    
    for url in tqdm(urls, desc="Processing URLs"):
        course_code = extract_course_code_from_url(url)
        
        if not course_code:
            if verbose:
                print(f"Could not extract course code from URL: {url}")
            continue
        
        found_program_codes = scrape_program_codes(url, program_codes, verbose)
        
        if found_program_codes:
            # Add this course to each program's list
            for program_code in found_program_codes:
                if course_code not in program_to_courses[program_code]:
                    program_to_courses[program_code].append(course_code)
    
    return program_to_courses


def save_mapping_to_json(program_to_courses: Dict[str, List[str]], output_file: str) -> None:
    """
    Save program-course mapping to JSON file.
    
    Args:
        program_to_courses: Dictionary mapping program codes to course codes
        output_file: Output JSON file path
    """
    # Ensure directory exists
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    # Convert to the desired format
    mapping_entries = []
    for program_code, courses in program_to_courses.items():
        if courses:  # Only include programs that have courses
            entry = {
                "program_code": program_code,
                "course_codes": sorted(courses)
            }
            mapping_entries.append(entry)
    
    # Sort entries by program_code
    sorted_entries = sorted(mapping_entries, key=lambda x: x["program_code"])
    
    with open(output_file, 'w') as f:
        json.dump(sorted_entries, f, indent=2)
    
    print(f"\nSaved mapping to {output_file}")


def main() -> None:
    """Main entry point of the script."""
    args = setup_arguments()
    
    print(f"Reading URLs from {args.urls_file}...")
    urls = read_urls(args.urls_file)
    
    if not urls:
        print("No URLs found. Exiting.")
        return
    
    print(f"Found {len(urls)} URLs.")
    
    # Process URLs to create program-to-course mapping
    program_to_courses = process_urls(urls, args.program_codes, args.verbose)
    
    # Save mapping to JSON file
    save_mapping_to_json(program_to_courses, args.output_file)
    
    # Print summary
    print("\n--- Summary ---")
    print(f"Total URLs processed: {len(urls)}")
    
    # Print program statistics
    print("\nProgram statistics:")
    for program_code, courses in program_to_courses.items():
        print(f"  - {program_code}: {len(courses)} courses")


if __name__ == "__main__":
    main() 