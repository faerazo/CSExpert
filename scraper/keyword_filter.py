#!/usr/bin/env python3
"""
Keyword Filter for PDFs and URLs

This script filters both PDF files in a directory and URLs from a text file 
based on the presence of specified keywords.

PDF Filtering:
- Scans PDFs in a specified directory.
- Checks text content for keywords.
- Optionally backs up original PDFs.
- Removes PDFs that DO NOT contain keywords (unless --dry-run).

URL Filtering:
- Reads URLs from an input file.
- Filters out direct PDF links (containing '/pdf/').
- Optionally scrapes remaining URLs (--scrape-urls, default).
- If scraping, checks webpage content for keywords.
- Writes URLs that DO contain keywords (or all non-PDF URLs if --no-scrape-urls) 
  to an output file (unless --dry-run).
"""

import os
import re
import shutil
import argparse
import time
from pathlib import Path
from typing import List, Set, Tuple

import PyPDF2
import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

# --- Default Configuration ---
DEFAULT_PDF_DIR = 'data/syllabi_pdfs'
DEFAULT_BACKUP_DIR = 'data/syllabi_pdfs_backup'
DEFAULT_URLS_INPUT_FILE = 'data/urls/course_syllabi_urls.txt'
DEFAULT_URLS_OUTPUT_FILE = 'data/urls/filtered_syllabi_urls.txt'
DEFAULT_KEYWORDS = ['N2COS', 'N2ADS', 'N2SOF', 'N1SOF', 'N2GDT']

# --- Argument Parsing ---
def setup_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Filter PDFs and/or URLs based on keywords.')

    # General arguments
    parser.add_argument('--keywords', '-k',
                        nargs='+',
                        default=DEFAULT_KEYWORDS,
                        help=f'Keywords to search for in PDFs and URLs (default: {DEFAULT_KEYWORDS})')
    parser.add_argument('--dry-run',
                        action='store_true',
                        help='Perform a dry run: show actions without modifying files.')
    parser.add_argument('--verbose', '-v',
                        action='store_true',
                        help='Print detailed information during processing.')

    # PDF filtering arguments
    pdf_group = parser.add_argument_group('PDF Filtering Options')
    pdf_group.add_argument('--pdf-dir', '-pd',
                         default=None, # Default to None, indicating not to run PDF filtering unless specified
                         help=f'Directory containing PDFs to filter (default: {DEFAULT_PDF_DIR} if specified without value, otherwise disabled)')
    pdf_group.add_argument('--backup-dir', '-bd',
                         default=DEFAULT_BACKUP_DIR,
                         help=f'Directory to backup PDFs before filtering (default: {DEFAULT_BACKUP_DIR})')
    pdf_group.add_argument('--no-backup',
                         action='store_true',
                         help='Skip backup of original PDFs')

    # URL filtering arguments
    url_group = parser.add_argument_group('URL Filtering Options')
    url_group.add_argument('--urls-file', '-uf',
                         default=None, # Default to None, indicating not to run URL filtering unless specified
                         help=f'File containing URLs to filter (default: {DEFAULT_URLS_INPUT_FILE} if specified without value, otherwise disabled)')
    url_group.add_argument('--output-urls-file', '-ouf',
                         default=DEFAULT_URLS_OUTPUT_FILE,
                         help=f'File to write filtered URLs to (default: {DEFAULT_URLS_OUTPUT_FILE})')
    url_group.add_argument('--no-scrape-urls',
                         action='store_true',
                         help='Skip scraping URLs for keywords, just filter out PDF links.')
    url_group.add_argument('--url-delay', type=float, default=0.5,
                         help='Delay in seconds between URL requests (default: 0.5)')


    args = parser.parse_args()

    # If --pdf-dir is provided without a value, use the default. Otherwise, it stays None.
    if args.pdf_dir is None and ('-pd' in os.sys.argv or '--pdf-dir' in os.sys.argv):
         # Check if the arg was provided without a subsequent value or if it was the last arg
        try:
            pdf_dir_index = os.sys.argv.index('--pdf-dir') if '--pdf-dir' in os.sys.argv else os.sys.argv.index('-pd')
            if pdf_dir_index + 1 == len(os.sys.argv) or os.sys.argv[pdf_dir_index+1].startswith('-'):
                 args.pdf_dir = DEFAULT_PDF_DIR
            # else: it was provided with a value, keep that value (already parsed)
        except ValueError:
             pass # Arg not present at all

    # If --urls-file is provided without a value, use the default.
    if args.urls_file is None and ('-uf' in os.sys.argv or '--urls-file' in os.sys.argv):
        try:
            urls_file_index = os.sys.argv.index('--urls-file') if '--urls-file' in os.sys.argv else os.sys.argv.index('-uf')
            if urls_file_index + 1 == len(os.sys.argv) or os.sys.argv[urls_file_index+1].startswith('-'):
                 args.urls_file = DEFAULT_URLS_INPUT_FILE
        except ValueError:
            pass # Arg not present at all

    return args


# --- Text Processing Function ---
def check_keywords_in_text(text: str, keywords: List[str]) -> Tuple[bool, Set[str]]:
    """Check if any keywords are present in the given text (case-insensitive)."""
    found_keywords = set()
    if not text:
        return False, found_keywords

    text_upper = text.upper()
    for keyword in keywords:
        keyword_upper = keyword.upper()
        # Use word boundaries to avoid partial matches within other words
        pattern = r'\b' + re.escape(keyword_upper) + r'\b'
        if re.search(pattern, text_upper):
            found_keywords.add(keyword) # Store original case keyword

    return bool(found_keywords), found_keywords

# --- PDF Filtering Functions ---
def find_pdf_files(directory: str) -> List[str]:
    """Find all PDF files in a directory."""
    pdf_files = []
    if not os.path.isdir(directory):
        print(f"Error: PDF directory '{directory}' not found or not a directory.")
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

def backup_pdfs(pdf_files: List[str], pdf_dir: str, backup_dir: str) -> None:
    """Create a backup of all PDF files."""
    try:
        os.makedirs(backup_dir, exist_ok=True)
        print(f"\nBacking up {len(pdf_files)} PDFs from '{pdf_dir}' to '{backup_dir}'...")
        for pdf_file in tqdm(pdf_files, desc="Backing up PDFs"):
            try:
                # Maintain relative path structure in backup
                rel_path = os.path.relpath(pdf_file, pdf_dir)
                backup_path = os.path.join(backup_dir, rel_path)
                os.makedirs(os.path.dirname(backup_path), exist_ok=True)
                shutil.copy2(pdf_file, backup_path)
            except Exception as e:
                print(f"\nError backing up {os.path.basename(pdf_file)}: {e}")
        print("PDF backup complete.")
    except OSError as e:
        print(f"Error creating backup directory '{backup_dir}': {e}")

def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract text from a PDF file."""
    text = ""
    try:
        with open(pdf_path, 'rb') as f:
            pdf_reader = PyPDF2.PdfReader(f)
            for page in pdf_reader.pages:
                try:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n" # Add newline between pages
                except Exception as page_e:
                    print(f"\nWarning: Could not extract text from a page in {os.path.basename(pdf_path)}: {page_e}")
    except FileNotFoundError:
        print(f"\nError: PDF file not found at {pdf_path}")
    except PyPDF2.errors.PdfReadError as pdf_e:
        print(f"\nError reading PDF file {os.path.basename(pdf_path)}: {pdf_e}")
    except Exception as e:
        print(f"\nUnexpected error extracting text from {os.path.basename(pdf_path)}: {e}")
    return text

def filter_pdfs_by_keywords(pdf_files: List[str], keywords: List[str], dry_run: bool, verbose: bool) -> Tuple[List[str], List[str]]:
    """Filter PDFs based on keywords, removing non-matching ones if not dry_run."""
    kept_pdfs = []
    removed_pdfs = []
    print(f"\nScanning {len(pdf_files)} PDFs for keywords: {', '.join(keywords)}...")

    for pdf_file in tqdm(pdf_files, desc="Scanning PDFs"):
        pdf_text = extract_text_from_pdf(pdf_file)
        has_keywords, found_keywords = check_keywords_in_text(pdf_text, keywords)

        if has_keywords:
            kept_pdfs.append(pdf_file)
            if verbose:
                print(f"  [KEEP] {os.path.basename(pdf_file)} (found: {', '.join(found_keywords)})")
        else:
            removed_pdfs.append(pdf_file)
            if verbose:
                print(f"  [REMOVE] {os.path.basename(pdf_file)}")
            if not dry_run:
                try:
                    os.remove(pdf_file)
                except OSError as e:
                    print(f"\nError removing {pdf_file}: {e}")

    return kept_pdfs, removed_pdfs

# --- URL Filtering Functions ---
def read_urls(file_path: str) -> List[str]:
    """Read URLs from a file."""
    urls = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            urls = [line.strip() for line in f if line.strip() and line.startswith('http')]
    except FileNotFoundError:
        print(f"Error: URL file '{file_path}' not found.")
    except Exception as e:
        print(f"Error reading URL file '{file_path}': {e}")
    return urls

def filter_out_pdf_urls(urls: List[str]) -> List[str]:
    """Filter out URLs that contain '/pdf/'."""
    return [url for url in urls if '/pdf/' not in url.lower()]

def scrape_url_for_keywords(url: str, keywords: List[str], delay: float) -> Tuple[bool, Set[str]]:
    """Scrape a single URL and check its text content for keywords."""
    try:
        time.sleep(delay) # Politeness delay
        response = requests.get(url, timeout=15)
        response.raise_for_status() # Check for HTTP errors

        soup = BeautifulSoup(response.text, 'html.parser')
        page_text = soup.get_text()
        if not page_text:
             return False, set()

        return check_keywords_in_text(page_text, keywords)

    except requests.exceptions.RequestException as e:
        print(f"\nError fetching URL {url}: {e}")
    except Exception as e:
        print(f"\nUnexpected error scraping URL {url}: {e}")
    return False, set()

def filter_urls_by_keywords_scrape(urls: List[str], keywords: List[str], delay:float, verbose: bool) -> List[str]:
    """Filter URLs by scraping them and checking for keywords."""
    matched_urls = []
    print(f"\nScraping {len(urls)} URLs for keywords: {', '.join(keywords)}...")

    for url in tqdm(urls, desc="Scraping URLs"):
        has_keywords, found_keywords = scrape_url_for_keywords(url, keywords, delay)
        if has_keywords:
            matched_urls.append(url)
            if verbose:
                print(f"  [KEEP] {url} (found: {', '.join(found_keywords)})")
        elif verbose:
             print(f"  [REMOVE] {url}")

    return matched_urls

def save_urls_to_file(urls: List[str], output_file: str) -> None:
    """Save filtered URLs to a file."""
    try:
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, 'w', encoding='utf-8') as f:
            for url in urls:
                f.write(f"{url}\n")
        print(f"\nWrote {len(urls)} URLs to '{output_file}'.")
    except OSError as e:
        print(f"Error writing to URL output file '{output_file}': {e}")

# --- Main Execution ---
def main() -> None:
    """Main entry point of the script."""
    args = setup_arguments()
    keywords = args.keywords

    pdf_processed = False
    urls_processed = False

    # --- PDF Filtering --- 
    if args.pdf_dir:
        pdf_processed = True
        print(f"--- Starting PDF Filtering (Source: '{args.pdf_dir}') ---")
        pdf_files = find_pdf_files(args.pdf_dir)

        if not pdf_files:
            print("No PDF files found in the specified directory.")
        else:
            print(f"Found {len(pdf_files)} PDF files.")
            initial_pdf_count = len(pdf_files)

            # Backup PDFs if requested
            if not args.no_backup and not args.dry_run:
                backup_pdfs(pdf_files, args.pdf_dir, args.backup_dir)
            elif not args.no_backup and args.dry_run:
                 print("Dry run: Skipping PDF backup.")

            # Filter PDFs
            kept_pdfs, removed_pdfs = filter_pdfs_by_keywords(pdf_files, keywords, args.dry_run, args.verbose)

            # PDF Summary
            print("\n--- PDF Filtering Summary ---")
            print(f"Keywords Searched: {', '.join(keywords)}")
            print(f"Initial PDFs: {initial_pdf_count}")
            print(f"PDFs kept (containing keywords): {len(kept_pdfs)}")
            print(f"PDFs removed/to remove: {len(removed_pdfs)}")
            if args.dry_run:
                print("DRY RUN: No PDFs were actually removed.")
            else:
                print(f"Removed {len(removed_pdfs)} PDFs from '{args.pdf_dir}'.")
    else:
         if args.verbose: print("PDF filtering skipped (no --pdf-dir specified).")

    # --- URL Filtering --- 
    if args.urls_file:
        urls_processed = True
        print(f"\n--- Starting URL Filtering (Source: '{args.urls_file}') ---")
        initial_urls = read_urls(args.urls_file)

        if not initial_urls:
            print("No URLs found in the specified file.")
        else:
            print(f"Read {len(initial_urls)} URLs.")

            # Filter out PDF URLs first
            non_pdf_urls = filter_out_pdf_urls(initial_urls)
            pdf_url_count = len(initial_urls) - len(non_pdf_urls)
            print(f"Removed {pdf_url_count} direct PDF URLs.")
            print(f"{len(non_pdf_urls)} non-PDF URLs remaining for keyword check.")

            # Filter by keywords (scraping or not)
            if not non_pdf_urls:
                 filtered_urls = []
            elif args.no_scrape_urls:
                print("Skipping URL scraping for keywords (--no-scrape-urls specified).")
                filtered_urls = non_pdf_urls # Keep all non-PDF URLs
            else:
                filtered_urls = filter_urls_by_keywords_scrape(non_pdf_urls, keywords, args.url_delay, args.verbose)

            # Save filtered URLs
            if args.dry_run:
                print("\nDry run: Filtered URLs not written to file.")
                print(f"Would write {len(filtered_urls)} URLs to '{args.output_urls_file}'.")
            elif filtered_urls is not None: # Ensure saving only if processing happened
                save_urls_to_file(filtered_urls, args.output_urls_file)

            # URL Summary
            print("\n--- URL Filtering Summary ---")
            print(f"Keywords Searched: {', '.join(keywords)}")
            print(f"Initial URLs read: {len(initial_urls)}")
            print(f"Direct PDF URLs removed: {pdf_url_count}")
            print(f"Non-PDF URLs checked: {len(non_pdf_urls)}")
            if args.no_scrape_urls:
                 print(f"URLs kept (all non-PDF): {len(filtered_urls)}")
            else:
                 print(f"URLs kept (containing keywords): {len(filtered_urls)}")
            if args.dry_run:
                 print(f"DRY RUN: Output file '{args.output_urls_file}' not modified.")
            else:
                 print(f"Filtered URLs saved to '{args.output_urls_file}'.")
    else:
        if args.verbose: print("URL filtering skipped (no --urls-file specified).")

    if not pdf_processed and not urls_processed:
         print("\nNothing to do. Specify --pdf-dir and/or --urls-file to perform filtering.")
    else:
        print("\nFiltering process complete.")

if __name__ == "__main__":
    main() 