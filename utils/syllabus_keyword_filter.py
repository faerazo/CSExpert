#!/usr/bin/env python3
"""
Syllabus Keyword Filter

This script scans PDFs in a specified directory, checks if they contain
any of the specified keywords, and keeps only those that match.
"""

import os
import re
import shutil
import argparse
from pathlib import Path
from typing import List, Set, Tuple

import PyPDF2
from tqdm import tqdm


# Default directories
DEFAULT_PDF_DIR = 'data/syllabi_pdfs'
DEFAULT_BACKUP_DIR = 'data/syllabi_pdfs_backup'

# Keywords to search for
DEFAULT_KEYWORDS = ['N2COS', 'N2ADS', 'N2SOF', 'N1SOF', 'N2GDT']


def setup_arguments() -> argparse.Namespace:
    """
    Parse command line arguments.
    
    Returns:
        argparse.Namespace: Parsed arguments
    """
    parser = argparse.ArgumentParser(description='Filter PDF syllabi based on keywords.')
    parser.add_argument('--pdf-dir', '-d',
                        default=DEFAULT_PDF_DIR,
                        help=f'Directory containing PDFs to filter (default: {DEFAULT_PDF_DIR})')
    parser.add_argument('--backup-dir', '-b',
                        default=DEFAULT_BACKUP_DIR,
                        help=f'Directory to backup PDFs before filtering (default: {DEFAULT_BACKUP_DIR})')
    parser.add_argument('--keywords', '-k',
                        nargs='+',
                        default=DEFAULT_KEYWORDS,
                        help=f'Keywords to search for (default: {DEFAULT_KEYWORDS})')
    parser.add_argument('--no-backup',
                        action='store_true',
                        help='Skip backup of original PDFs')
    parser.add_argument('--dry-run',
                        action='store_true',
                        help='Only show what would be done without actually removing files')
    parser.add_argument('--verbose', '-v',
                        action='store_true',
                        help='Print detailed information about matches')
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


def backup_pdfs(pdf_files: List[str], pdf_dir: str, backup_dir: str) -> None:
    """
    Create a backup of all PDF files.
    
    Args:
        pdf_files: List of PDF file paths
        pdf_dir: Source directory
        backup_dir: Backup directory
    """
    os.makedirs(backup_dir, exist_ok=True)
    
    print(f"\nBacking up {len(pdf_files)} PDFs to {backup_dir}...")
    
    for pdf_file in tqdm(pdf_files, desc="Backing up PDFs"):
        rel_path = os.path.relpath(pdf_file, pdf_dir)
        backup_path = os.path.join(backup_dir, rel_path)
        os.makedirs(os.path.dirname(backup_path), exist_ok=True)
        shutil.copy2(pdf_file, backup_path)
    
    print("Backup complete.")


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


def check_keywords_in_pdf(pdf_path: str, keywords: List[str], verbose: bool = False) -> Tuple[bool, Set[str]]:
    """
    Check if any of the keywords appear in the PDF.
    
    Args:
        pdf_path: Path to the PDF file
        keywords: List of keywords to search for
        verbose: Whether to print detailed information
        
    Returns:
        Tuple[bool, Set[str]]: (Whether any keyword was found, Set of found keywords)
    """
    try:
        pdf_text = extract_text_from_pdf(pdf_path)
        
        # Convert to uppercase for case-insensitive matching
        pdf_text_upper = pdf_text.upper()
        
        # Check for keywords
        found_keywords = set()
        for keyword in keywords:
            keyword_upper = keyword.upper()
            if keyword_upper in pdf_text_upper:
                found_keywords.add(keyword)
        
        if verbose and found_keywords:
            print(f"Found keywords in {os.path.basename(pdf_path)}: {', '.join(found_keywords)}")
        
        return bool(found_keywords), found_keywords
    
    except Exception as e:
        print(f"Error processing {pdf_path}: {e}")
        return False, set()


def filter_pdfs(pdf_files: List[str], keywords: List[str], dry_run: bool = False, verbose: bool = False) -> Tuple[List[str], List[str]]:
    """
    Filter PDFs based on keywords.
    
    Args:
        pdf_files: List of PDF file paths
        keywords: List of keywords to search for
        dry_run: Whether to perform a dry run
        verbose: Whether to print detailed information
        
    Returns:
        Tuple[List[str], List[str]]: (Kept PDFs, Removed PDFs)
    """
    kept_pdfs = []
    removed_pdfs = []
    
    print(f"\nScanning {len(pdf_files)} PDFs for keywords: {', '.join(keywords)}...")
    
    for pdf_file in tqdm(pdf_files, desc="Scanning PDFs"):
        has_keywords, found_keywords = check_keywords_in_pdf(pdf_file, keywords, verbose)
        
        if has_keywords:
            kept_pdfs.append(pdf_file)
        else:
            removed_pdfs.append(pdf_file)
            if not dry_run:
                try:
                    os.remove(pdf_file)
                except Exception as e:
                    print(f"Error removing {pdf_file}: {e}")
    
    return kept_pdfs, removed_pdfs


def main() -> None:
    """Main entry point of the script."""
    args = setup_arguments()
    
    print(f"Looking for PDF files in {args.pdf_dir}...")
    pdf_files = find_pdf_files(args.pdf_dir)
    
    if not pdf_files:
        print("No PDF files found. Exiting.")
        return
    
    print(f"Found {len(pdf_files)} PDF files.")
    
    # Backup PDFs if requested
    if not args.no_backup:
        backup_pdfs(pdf_files, args.pdf_dir, args.backup_dir)
    
    # Filter PDFs
    kept_pdfs, removed_pdfs = filter_pdfs(pdf_files, args.keywords, args.dry_run, args.verbose)
    
    # Print summary
    print("\n--- Summary ---")
    print(f"Total PDFs: {len(pdf_files)}")
    print(f"PDFs with keywords: {len(kept_pdfs)}")
    print(f"PDFs without keywords: {len(removed_pdfs)}")
    
    if args.dry_run:
        print("\nThis was a dry run. No files were actually removed.")
    else:
        print(f"\n{len(removed_pdfs)} PDFs were removed from {args.pdf_dir}.")
    
    # Print sample of kept files if verbose
    if args.verbose and kept_pdfs:
        print("\nSample of kept PDFs:")
        for pdf in kept_pdfs[:5]:
            print(f"  - {os.path.basename(pdf)}")


if __name__ == "__main__":
    main() 