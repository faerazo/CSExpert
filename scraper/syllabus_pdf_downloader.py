#!/usr/bin/env python3
"""
Syllabus PDF Downloader

This script downloads PDF syllabi from the University of Gothenburg website.
It reads URLs from a course_syllabi_urls.txt file, filters for PDF URLs,
and saves the PDFs in a specified output directory.
"""

import os
import re
import time
import random
import argparse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Tuple

import requests
from tqdm import tqdm


# Default file paths
DEFAULT_URL_FILE = 'data/urls/course_syllabi_urls.txt'
DEFAULT_OUTPUT_DIR = 'data/syllabi_pdfs'

# PDF URL pattern to match
PDF_URL_PATTERN = r'kursplaner\.gu\.se/pdf/kurs/en/([A-Za-z0-9]+)'


def setup_arguments() -> argparse.Namespace:
    """
    Parse command line arguments.
    
    Returns:
        argparse.Namespace: Parsed arguments
    """
    parser = argparse.ArgumentParser(description='Download PDF syllabi from University of Gothenburg.')
    parser.add_argument('--url-file', '-f', 
                        default=DEFAULT_URL_FILE,
                        help=f'Path to the file containing URLs (default: {DEFAULT_URL_FILE})')
    parser.add_argument('--output-dir', '-o', 
                        default=DEFAULT_OUTPUT_DIR,
                        help=f'Directory to save PDFs (default: {DEFAULT_OUTPUT_DIR})')
    parser.add_argument('--max-workers', '-w', 
                        type=int, default=5,
                        help='Maximum number of concurrent downloads (default: 5)')
    parser.add_argument('--delay', '-d', 
                        type=float, default=0.5,
                        help='Delay between downloads in seconds (default: 0.5)')
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
            return [line.strip() for line in f if line.strip()]
    except Exception as e:
        print(f"Error reading URL file: {e}")
        return []


def filter_pdf_urls(urls: List[str]) -> List[Tuple[str, str]]:
    """
    Filter URLs to include only PDF syllabus URLs.
    
    Args:
        urls: List of URLs to filter
        
    Returns:
        List[Tuple[str, str]]: List of (URL, course_code) pairs
    """
    pdf_urls = []
    for url in urls:
        match = re.search(PDF_URL_PATTERN, url)
        if match:
            course_code = match.group(1)
            pdf_urls.append((url, course_code))
    
    return pdf_urls


def download_pdf(url_info: Tuple[str, str], output_dir: str, delay: float) -> Optional[str]:
    """
    Download a PDF from a URL.
    
    Args:
        url_info: Tuple containing (URL, course_code)
        output_dir: Directory to save the PDF
        delay: Delay in seconds before downloading (to avoid hammering the server)
        
    Returns:
        Optional[str]: Path to the downloaded file if successful, None otherwise
    """
    url, course_code = url_info
    output_path = os.path.join(output_dir, f"{course_code}.pdf")
    
    # Introduce a small delay to avoid hammering the server
    time.sleep(delay + random.uniform(0, 0.5))
    
    try:
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()  # Raise an exception for HTTP errors
        
        # Check if it's actually a PDF
        content_type = response.headers.get('Content-Type', '')
        if 'application/pdf' not in content_type and 'pdf' not in content_type.lower():
            print(f"Warning: URL {url} does not seem to be a PDF (Content-Type: {content_type})")
        
        # Save the PDF
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        return output_path
    
    except requests.exceptions.RequestException as e:
        print(f"Error downloading {url}: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error for {url}: {e}")
        return None


def download_all_pdfs(pdf_urls: List[Tuple[str, str]], output_dir: str, max_workers: int, delay: float) -> int:
    """
    Download all PDFs in parallel.
    
    Args:
        pdf_urls: List of (URL, course_code) pairs
        output_dir: Directory to save PDFs
        max_workers: Maximum number of concurrent downloads
        delay: Delay between downloads in seconds
        
    Returns:
        int: Number of successfully downloaded PDFs
    """
    os.makedirs(output_dir, exist_ok=True)
    
    successful_downloads = 0
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all download tasks
        future_to_url = {
            executor.submit(download_pdf, url_info, output_dir, delay): url_info
            for url_info in pdf_urls
        }
        
        # Process the results with a progress bar
        with tqdm(total=len(pdf_urls), desc="Downloading PDFs") as pbar:
            for future in future_to_url:
                url_info = future_to_url[future]
                try:
                    path = future.result()
                    if path:
                        successful_downloads += 1
                except Exception as e:
                    print(f"Error processing {url_info[0]}: {e}")
                finally:
                    pbar.update(1)
    
    return successful_downloads


def main() -> None:
    """Main entry point of the script."""
    args = setup_arguments()
    
    print(f"Reading URLs from {args.url_file}")
    urls = read_urls(args.url_file)
    
    if not urls:
        print("No URLs found. Exiting.")
        return
    
    print(f"Found {len(urls)} total URLs")
    
    pdf_urls = filter_pdf_urls(urls)
    print(f"Found {len(pdf_urls)} PDF URLs to download")
    
    if not pdf_urls:
        print("No PDF URLs found. Exiting.")
        return
    
    print(f"\nDownloading PDFs to {args.output_dir}")
    successful = download_all_pdfs(pdf_urls, args.output_dir, args.max_workers, args.delay)
    
    print(f"\nDownload complete. Successfully downloaded {successful} out of {len(pdf_urls)} PDFs.")
    
    if successful < len(pdf_urls):
        print(f"Failed to download {len(pdf_urls) - successful} PDFs.")


if __name__ == "__main__":
    main() 