#!/usr/bin/env python3
"""
URL Keyword Filter

This script filters URLs from a text file, keeping only those that don't contain
"/pdf/" and checks if they contain any of the specified keywords using web scraping.
"""

import os
import re
import argparse
from pathlib import Path
from typing import List, Set, Tuple
import requests
from bs4 import BeautifulSoup
from tqdm import tqdm


# Default files
DEFAULT_URLS_FILE = 'data/urls/course_syllabi_urls.txt'
DEFAULT_OUTPUT_FILE = 'data/urls/filtered_syllabi_urls.txt'

# Keywords to search for
DEFAULT_KEYWORDS = ['N2COS', 'N2ADS', 'N2SOF', 'N1SOF', 'N2GDT']


def setup_arguments() -> argparse.Namespace:
    """
    Parse command line arguments.
    
    Returns:
        argparse.Namespace: Parsed arguments
    """
    parser = argparse.ArgumentParser(description='Filter URLs based on keywords.')
    parser.add_argument('--urls-file', '-u',
                        default=DEFAULT_URLS_FILE,
                        help=f'File containing URLs to filter (default: {DEFAULT_URLS_FILE})')
    parser.add_argument('--output-file', '-o',
                        default=DEFAULT_OUTPUT_FILE,
                        help=f'File to write filtered URLs to (default: {DEFAULT_OUTPUT_FILE})')
    parser.add_argument('--keywords', '-k',
                        nargs='+',
                        default=DEFAULT_KEYWORDS,
                        help=f'Keywords to search for (default: {DEFAULT_KEYWORDS})')
    parser.add_argument('--no-scrape', 
                        action='store_true',
                        help='Skip scraping the URLs, just filter out PDF links')
    parser.add_argument('--dry-run',
                        action='store_true',
                        help='Only show what would be done without actually writing to file')
    parser.add_argument('--verbose', '-v',
                        action='store_true',
                        help='Print detailed information about matches')
    return parser.parse_args()


def read_urls(file_path: str) -> List[str]:
    """
    Read URLs from a file.
    
    Args:
        file_path: Path to the file containing URLs
        
    Returns:
        List[str]: List of URLs
    """
    with open(file_path, 'r') as f:
        urls = [line.strip() for line in f if line.strip()]
    return urls


def filter_pdf_urls(urls: List[str]) -> List[str]:
    """
    Filter out URLs that contain '/pdf/'.
    
    Args:
        urls: List of URLs
        
    Returns:
        List[str]: List of filtered URLs
    """
    return [url for url in urls if '/pdf/' not in url]


def check_keywords_in_url(url: str, keywords: List[str], verbose: bool = False) -> Tuple[bool, Set[str]]:
    """
    Check if any of the keywords appear in the content of the URL.
    
    Args:
        url: URL to check
        keywords: List of keywords to search for
        verbose: Whether to print detailed information
        
    Returns:
        Tuple[bool, Set[str]]: (Whether any keyword was found, Set of found keywords)
    """
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        # Get all text from the page
        page_text = soup.get_text()
        
        # Convert to uppercase for case-insensitive matching
        page_text_upper = page_text.upper()
        
        # Check for keywords
        found_keywords = set()
        for keyword in keywords:
            keyword_upper = keyword.upper()
            if keyword_upper in page_text_upper:
                found_keywords.add(keyword)
        
        if verbose and found_keywords:
            print(f"Found keywords in {url}: {', '.join(found_keywords)}")
        
        return bool(found_keywords), found_keywords
    
    except Exception as e:
        print(f"Error processing {url}: {e}")
        return False, set()


def filter_urls_by_keywords(urls: List[str], keywords: List[str], no_scrape: bool = False, verbose: bool = False) -> List[str]:
    """
    Filter URLs based on keywords.
    
    Args:
        urls: List of URLs
        keywords: List of keywords to search for
        no_scrape: Whether to skip scraping
        verbose: Whether to print detailed information
        
    Returns:
        List[str]: List of URLs that contain at least one keyword
    """
    if no_scrape:
        # If scraping is disabled, just return all non-PDF URLs
        return urls
    
    matched_urls = []
    
    print(f"\nScraping {len(urls)} URLs for keywords: {', '.join(keywords)}...")
    
    for url in tqdm(urls, desc="Scraping URLs"):
        has_keywords, found_keywords = check_keywords_in_url(url, keywords, verbose)
        
        if has_keywords:
            matched_urls.append(url)
    
    return matched_urls


def save_urls_to_file(urls: List[str], output_file: str) -> None:
    """
    Save filtered URLs to a file.
    
    Args:
        urls: List of URLs to save
        output_file: Path to output file
    """
    # Ensure directory exists
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    with open(output_file, 'w') as f:
        for url in urls:
            f.write(f"{url}\n")


def main() -> None:
    """Main entry point of the script."""
    args = setup_arguments()
    
    print(f"Reading URLs from {args.urls_file}...")
    all_urls = read_urls(args.urls_file)
    
    if not all_urls:
        print("No URLs found. Exiting.")
        return
    
    print(f"Found {len(all_urls)} URLs.")
    
    # Filter out PDF URLs
    print("Filtering out PDF URLs...")
    non_pdf_urls = filter_pdf_urls(all_urls)
    
    print(f"Found {len(non_pdf_urls)} non-PDF URLs.")
    
    # Filter URLs by keywords (if scraping is enabled)
    if not args.no_scrape:
        non_pdf_urls = filter_urls_by_keywords(non_pdf_urls, args.keywords, args.no_scrape, args.verbose)
    
    # Save filtered URLs
    if args.dry_run:
        print("\nThis was a dry run. URLs were not written to file.")
        print(f"Would have written {len(non_pdf_urls)} URLs to {args.output_file}.")
        
        if args.verbose:
            print("\nSample of filtered URLs:")
            for url in non_pdf_urls[:5]:
                print(f"  - {url}")
    else:
        save_urls_to_file(non_pdf_urls, args.output_file)
        print(f"\nWrote {len(non_pdf_urls)} URLs to {args.output_file}.")
    
    # Print summary
    print("\n--- Summary ---")
    print(f"Total URLs: {len(all_urls)}")
    print(f"Non-PDF URLs: {len(filter_pdf_urls(all_urls))}")
    print(f"Filtered URLs: {len(non_pdf_urls)}")


if __name__ == "__main__":
    main() 