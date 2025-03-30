#!/usr/bin/env python3
"""
GU Course Data Extractor

This script scrapes the University of Gothenburg website to extract:
1. Course syllabus URLs
2. Course information pages
3. A list of unique course codes

It uses Selenium WebDriver with Chrome in headless mode to navigate and extract data
from different search result pages.
"""

import os
import re
import time
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# ----- Configuration Constants -----

# Base URL for the university website
BASE_URL = "https://www.gu.se"

# Output file paths
OUTPUT_DIR = Path("data/urls")
SYLLABUS_URLS_FILE = OUTPUT_DIR / "course_syllabi_urls.txt"
COURSE_PAGES_FILE = OUTPUT_DIR / "course_pages_urls.txt"
COURSE_CODES_FILE = OUTPUT_DIR / "course_code_list.txt"

# Course code prefixes to search for
COURSE_PREFIXES = ["dit0", "dit1", "dit2", "dit3", "dit4", "dit5", "dit6", "dit7", "dit8", "dit9", 
                  "msg", "msa", "mma", "tia", "lt"]

# Pattern fragments for URL construction
SYLLABUS_SEARCH_URL = f"{BASE_URL}/en/study-gothenburg/study-options/find-syllabus-and-reading-list?hits=200&q="
COURSE_PAGE_SEARCH_URL = f"{BASE_URL}/en/study-gothenburg/study-options/find-courses?education_type.keyword=Course&hits=200&q="

# Regular expressions for course code extraction
PDF_URL_PATTERN = r"/pdf/kurs/[a-z]{2}/([A-Z]{2,3}\d{3})"
WEB_URL_PATTERN = r"-((?:dit|msg|msa|mma|tia|lt)\d{3})/syllabus"

# ----- Data Structures -----

@dataclass
class ScrapingResult:
    """Container for storing scraping results"""
    syllabus_urls: List[str] = None
    course_pages: List[str] = None
    course_codes: Set[str] = None
    
    def __post_init__(self):
        """Initialize empty collections if not provided"""
        self.syllabus_urls = self.syllabus_urls or []
        self.course_pages = self.course_pages or []
        self.course_codes = self.course_codes or set()

# ----- Browser Setup Functions -----

def setup_chrome_driver() -> webdriver.Chrome:
    """
    Configure and initialize a Chrome WebDriver instance with appropriate settings.
    
    Returns:
        webdriver.Chrome: Configured Chrome WebDriver instance
    """
    # Suppress deprecation warnings
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    
    # Configure Chrome options
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_experimental_option("excludeSwitches", ["enable-logging"])
    
    # Initialize the Chrome WebDriver with managed service
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)


def fetch_webpage_content(url: str) -> Optional[str]:
    """
    Fetch the HTML content of a webpage using Selenium WebDriver.
    
    Args:
        url: The URL to fetch
        
    Returns:
        str or None: HTML content of the page if successful, None otherwise
    """
    driver = None
    try:
        driver = setup_chrome_driver()
        driver.get(url)
        # Wait for the page to load dynamically
        time.sleep(5)
        return driver.page_source
    except Exception as e:
        print(f"Error fetching webpage: {e}")
        return None
    finally:
        if driver:
            driver.quit()

# ----- URL Processing Functions -----

def format_url(url: str) -> str:
    """
    Format a URL by adding the base URL if needed.
    
    Args:
        url: The URL to format
        
    Returns:
        str: Properly formatted URL
    """
    if url.startswith(("http://", "https://")):
        return url
    return f"{BASE_URL}{url}"


def extract_course_urls(html_content: str) -> List[str]:
    """
    Extract course URLs from the HTML content and filter out reading lists.
    
    Args:
        html_content: HTML content of the page
        
    Returns:
        List[str]: List of extracted URLs (excluding reading list URLs)
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    course_links = soup.find_all('a', class_='link link--large u-font-weight-700')
    urls = [link.get('href') for link in course_links]
    
    # Filter out reading list URLs
    filtered_urls = [url for url in urls if not _is_reading_list_url(url)]
    return filtered_urls


def _is_reading_list_url(url: str) -> bool:
    """
    Check if a URL is for a reading list.
    
    Args:
        url: URL to check
        
    Returns:
        bool: True if it's a reading list URL, False otherwise
    """
    return "reading-list" in url or "_Litteratur_" in url


def extract_course_code(url: str) -> Optional[str]:
    """
    Extract a course code (e.g., DIT123, MSG123) from a URL.
    
    Args:
        url: URL to extract course code from
        
    Returns:
        str or None: Course code if found, None otherwise
    """
    # Try to match PDF pattern
    pdf_match = re.search(PDF_URL_PATTERN, url, re.IGNORECASE)
    if pdf_match:
        return pdf_match.group(1).upper()
    
    # Try to match web pattern
    web_match = re.search(WEB_URL_PATTERN, url, re.IGNORECASE)
    if web_match:
        return web_match.group(1).upper()
    
    return None

# ----- File Operations -----

def ensure_output_directory() -> None:
    """Ensure that the output directory exists"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def save_urls_to_file(urls: List[str], filename: Path) -> None:
    """
    Save the formatted URLs to a text file.
    
    Args:
        urls: List of URLs to save
        filename: Path to the output file
    """
    with open(filename, 'w') as f:
        for url in urls:
            formatted_url = format_url(url)
            f.write(f"{formatted_url}\n")
    
    print(f"Saved {len(urls)} URLs to {filename}")


def save_course_codes(course_codes: Set[str], filename: Path) -> None:
    """
    Save course codes to a text file, sorted alphabetically.
    
    Args:
        course_codes: Set of course codes to save
        filename: Path to the output file
    """
    sorted_codes = sorted(list(course_codes))
    
    with open(filename, 'w') as f:
        for code in sorted_codes:
            f.write(f"{code}\n")
    
    print(f"Saved {len(sorted_codes)} unique course codes to {filename}")

# ----- Scraping Functions -----

def process_search_page(url: str) -> List[str]:
    """
    Process a search results page to extract course URLs.
    
    Args:
        url: URL of the search results page
        
    Returns:
        List[str]: List of extracted course URLs
    """
    print(f"\nProcessing URL: {url}")
    html_content = fetch_webpage_content(url)
    
    if not html_content:
        print("Failed to fetch webpage content")
        return []
    
    course_urls = extract_course_urls(html_content)
    print(f"Found {len(course_urls)} course URLs from this page")
    return course_urls


def build_search_urls() -> Dict[str, List[str]]:
    """
    Build all search URLs based on the configured prefixes.
    
    Returns:
        Dict[str, List[str]]: Dictionary with syllabus and course page search URLs
    """
    # Generate syllabus search URLs for each prefix
    syllabus_urls = [f"{SYLLABUS_SEARCH_URL}{prefix}" for prefix in COURSE_PREFIXES]
    
    # Generate course page search URLs (these don't need all the digit variations)
    unique_prefixes = set([prefix.rstrip('0123456789') for prefix in COURSE_PREFIXES])
    course_page_urls = [f"{COURSE_PAGE_SEARCH_URL}{prefix}" for prefix in unique_prefixes]
    
    return {
        "syllabus": syllabus_urls,
        "course_pages": course_page_urls
    }


def scrape_all_course_data() -> ScrapingResult:
    """
    Scrape all course data from the university website.
    
    Returns:
        ScrapingResult: Container with all scraped data
    """
    result = ScrapingResult()
    search_urls = build_search_urls()
    
    # Process syllabus search pages
    print("\n--- Scraping Course Syllabi ---")
    for url in search_urls["syllabus"]:
        course_urls = process_search_page(url)
        result.syllabus_urls.extend(course_urls)
        
        # Extract course codes as we go
        for course_url in course_urls:
            code = extract_course_code(course_url)
            if code:
                result.course_codes.add(code)
    
    # Process course information pages
    print("\n--- Scraping Course Information Pages ---")
    for url in search_urls["course_pages"]:
        course_urls = process_search_page(url)
        result.course_pages.extend(course_urls)
    
    return result


def save_all_data(result: ScrapingResult) -> None:
    """
    Save all scraped data to files.
    
    Args:
        result: ScrapingResult containing all data to save
    """
    ensure_output_directory()
    
    # Save syllabus URLs
    save_urls_to_file(result.syllabus_urls, SYLLABUS_URLS_FILE)
    
    # Save course page URLs
    save_urls_to_file(result.course_pages, COURSE_PAGES_FILE)
    
    # Save course codes
    save_course_codes(result.course_codes, COURSE_CODES_FILE)
    
    # Print summary
    print("\n--- Scraping Summary ---")
    print(f"Total syllabi found: {len(result.syllabus_urls)}")
    print(f"Total course pages found: {len(result.course_pages)}")
    print(f"Total unique course codes: {len(result.course_codes)}")
    
    if result.syllabus_urls:
        print("\nFirst few syllabus URLs:")
        for url in result.syllabus_urls[:3]:
            print(f"  {format_url(url)}")

# ----- Main Function -----

def main() -> None:
    """Main entry point of the script."""
    print("Starting GU Course Data Extractor")
    
    # Scrape all data
    result = scrape_all_course_data()
    
    # Save scraped data to files
    save_all_data(result)
    
    print("\nExtraction complete!")


if __name__ == "__main__":
    main()