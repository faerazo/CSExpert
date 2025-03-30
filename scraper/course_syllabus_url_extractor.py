#!/usr/bin/env python3
"""
Course Syllabus URL Extractor

This script scrapes the University of Gothenburg website to extract URLs for course syllabi
and saves them to a text file with proper formatting.
"""

import time
import warnings
from typing import List, Optional

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager


# # List of search URLs for different course prefixes
SEARCH_URLS = [
    "https://www.gu.se/en/study-gothenburg/study-options/find-syllabus-and-reading-list?hits=200&q=dit0",
    "https://www.gu.se/en/study-gothenburg/study-options/find-syllabus-and-reading-list?hits=200&q=dit1",
    "https://www.gu.se/en/study-gothenburg/study-options/find-syllabus-and-reading-list?hits=200&q=dit2",
    "https://www.gu.se/en/study-gothenburg/study-options/find-syllabus-and-reading-list?hits=200&q=dit3",
    "https://www.gu.se/en/study-gothenburg/study-options/find-syllabus-and-reading-list?hits=200&q=dit4",
    "https://www.gu.se/en/study-gothenburg/study-options/find-syllabus-and-reading-list?hits=200&q=dit5",
    "https://www.gu.se/en/study-gothenburg/study-options/find-syllabus-and-reading-list?hits=200&q=dit6",
    "https://www.gu.se/en/study-gothenburg/study-options/find-syllabus-and-reading-list?hits=200&q=dit7",
    "https://www.gu.se/en/study-gothenburg/study-options/find-syllabus-and-reading-list?hits=200&q=dit8",
    "https://www.gu.se/en/study-gothenburg/study-options/find-syllabus-and-reading-list?hits=200&q=dit9",
    "https://www.gu.se/en/study-gothenburg/study-options/find-syllabus-and-reading-list?hits=200&q=msg",
    "https://www.gu.se/en/study-gothenburg/study-options/find-syllabus-and-reading-list?hits=200&q=msa",
    "https://www.gu.se/en/study-gothenburg/study-options/find-syllabus-and-reading-list?hits=200&q=mma",
    "https://www.gu.se/en/study-gothenburg/study-options/find-syllabus-and-reading-list?hits=200&q=tia",
    "https://www.gu.se/en/study-gothenburg/study-options/find-syllabus-and-reading-list?hits=200&q=lt"
]

# Base URL for the university website
BASE_URL = "https://www.gu.se"


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
        # Wait for the page to load
        time.sleep(5)
        return driver.page_source
    except Exception as e:
        print(f"Error fetching webpage: {e}")
        return None
    finally:
        if driver:
            driver.quit()


def extract_course_urls(html_content: str) -> List[str]:
    """
    Extract course URLs from the HTML content using BeautifulSoup.
    Filter out URLs containing "reading-list".
    
    Args:
        html_content: HTML content of the page
        
    Returns:
        List[str]: List of extracted URLs (excluding reading list URLs)
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    course_links = soup.find_all('a', class_='link link--large u-font-weight-700')
    urls = [link.get('href') for link in course_links]
    
    # Filter out reading list URLs
    filtered_urls = [url for url in urls if "reading-list" not in url]
    return filtered_urls


def format_url(url: str, base_url: str = BASE_URL) -> str:
    """
    Format a URL by adding the base URL if needed.
    
    Args:
        url: The URL to format
        base_url: The base URL to prepend if necessary
        
    Returns:
        str: Properly formatted URL
    """
    if url.startswith(("http://", "https://")):
        return url
    return f"{base_url}{url}"


def save_urls_to_file(urls: List[str], filename: str = 'data/urls/course_syllabus_urls.txt') -> None:
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


def main() -> None:
    """Main entry point of the script."""
    # Collect all course URLs
    all_course_urls = []
    for url in SEARCH_URLS:
        course_urls = process_search_page(url)
        all_course_urls.extend(course_urls)
    
    # Save all URLs to file
    save_urls_to_file(all_course_urls)
    
    # Print summary
    print(f"\nTotal courses found: {len(all_course_urls)}")
    print("\nFirst few formatted URLs:")
    for url in all_course_urls[:5]:
        print(format_url(url))


if __name__ == "__main__":
    main()