#!/usr/bin/env python3
"""
Database-Connected HTML Scraper

Direct HTML scraping for GU course pages and syllabus webpages.
Uses WebDriver pool and BeautifulSoup to parse course content,
extracting comprehensive course information that can be processed by the Gemini processor.
"""

import logging
import os
import re
import time
from pathlib import Path
from typing import List, Optional, Dict
from datetime import datetime

from bs4 import BeautifulSoup

# Import database components
from database.connection_manager import get_database_manager, DatabaseManager
from scraper.webdriver_pool import get_global_pool, close_global_pool

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ----- Configuration Constants -----

# Rate limiting
RATE_LIMIT_DELAY = 2.0  # seconds between requests (faster than Firecrawl)
MAX_RETRY_ATTEMPTS = 3
REQUEST_TIMEOUT = 30  # seconds

# Default settings  
DEFAULT_SYLLABI_DIR = 'data/syllabi_pages'
DEFAULT_COURSE_DIR = 'data/course_pages'

# Course code pattern extraction (reuse from firecrawl scraper)
COURSE_CODE_PATTERNS = [
    r'-(dit\d+|msg\d+|mma\d+|msa\d+|tia\d+|lt\d+)/syllabus/',
    r'-(dit\d+|msg\d+|mma\d+|msa\d+|tia\d+|lt\d+)$',
    r'-(dit\d+|msg\d+|mma\d+|msa\d+|tia\d+|lt\d+)/',
    r'\b([A-Z]{2,3}\d{3,4})\b',  # Direct course code pattern
]

# ----- Data Structures -----

class HTMLScrapingResult:
    """Container for HTML scraping results"""
    
    def __init__(self, url_id: int, url: str, course_code: str,
                 success: bool = False, markdown_content: str = "",
                 file_path: Optional[str] = None, error: Optional[str] = None,
                 scraping_time: float = 0.0, content_length: int = 0):
        self.url_id = url_id
        self.url = url
        self.course_code = course_code
        self.success = success
        self.markdown_content = markdown_content
        self.file_path = file_path
        self.error = error
        self.scraping_time = scraping_time
        self.content_length = content_length
        self.scraped_at = datetime.utcnow()


# ----- Database Operations -----

class DatabaseHTMLStore:
    """Handles database operations for HTML scraping tracking"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.setup_tables()
    
    def setup_tables(self):
        """Ensure HTML scraping tracking tables exist"""
        try:
            with self.db_manager.transaction() as conn:
                # Create html_scrapes table for tracking HTML scraping results
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS html_scrapes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        extraction_url_id INTEGER NOT NULL,
                        course_code VARCHAR(10) NOT NULL,
                        original_url TEXT NOT NULL,
                        markdown_file_path TEXT,
                        content_length INTEGER DEFAULT 0,
                        status VARCHAR(20) CHECK (status IN ('pending', 'success', 'failed', 'skipped')) DEFAULT 'pending',
                        error_message TEXT,
                        scraping_time REAL DEFAULT 0.0,
                        retry_count INTEGER DEFAULT 0,
                        scraped_at TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        
                        FOREIGN KEY (extraction_url_id) REFERENCES extraction_urls(id),
                        UNIQUE(extraction_url_id)
                    )
                """)
                
                # Migrate data from old firecrawl_scrapes table if it exists
                try:
                    # Check if old table exists first
                    result = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='firecrawl_scrapes'").fetchone()
                    if result:
                        conn.execute("""
                            INSERT OR IGNORE INTO html_scrapes 
                            SELECT * FROM firecrawl_scrapes
                        """)
                        logger.info("Migrated data from old firecrawl_scrapes table")
                except Exception as e:
                    # Migration is optional - continue if it fails
                    logger.debug(f"No migration needed from firecrawl_scrapes: {e}")
                
                # Create index for performance
                conn.execute("CREATE INDEX IF NOT EXISTS idx_html_scrapes_course_code ON html_scrapes(course_code)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_html_scrapes_status ON html_scrapes(status)")
                
                logger.info("HTML scraping tracking tables initialized")
                
        except Exception as e:
            logger.error(f"Failed to setup HTML scraping tables: {e}")
            raise
    
    def store_scraping_result(self, result: HTMLScrapingResult) -> bool:
        """Store HTML scraping result in database"""
        try:
            query = """
                INSERT OR REPLACE INTO html_scrapes 
                (extraction_url_id, course_code, original_url, markdown_file_path,
                 content_length, status, error_message, scraping_time, scraped_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            
            status = 'success' if result.success else 'failed'
            
            self.db_manager.execute_update(query, (
                result.url_id,
                result.course_code,
                result.url,
                result.file_path,
                result.content_length,
                status,
                result.error,
                result.scraping_time,
                result.scraped_at
            ))
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to store HTML scraping result for {result.url}: {e}")
            return False


# ----- HTML Parsing Functions -----

def extract_course_code_from_url(url: str) -> Optional[str]:
    """Extract course code from URL using multiple patterns"""
    for pattern in COURSE_CODE_PATTERNS:
        match = re.search(pattern, url, re.IGNORECASE)
        if match:
            return match.group(1).upper()
    
    logger.warning(f"Could not extract course code from URL: {url}")
    return None


def safe_filename(text: str) -> str:
    """Convert text to safe filename by removing/replacing invalid characters"""
    safe_text = re.sub(r'[<>:"/\\|?*]', '', text)
    safe_text = re.sub(r'\s+', '_', safe_text)
    return safe_text[:100]  # Limit length


def remove_noise_elements(soup: BeautifulSoup) -> BeautifulSoup:
    """Remove navigation, headers, footers, and other noise elements from the page"""
    
    # Elements to remove completely (common noise)
    noise_selectors = [
        'nav', 'header', 'footer',  # Main navigation and layout elements
        '.navigation', '.nav', '.navbar',  # Navigation classes
        '.sidebar', '.aside', '.menu',  # Sidebar and menu elements
        '.breadcrumb', '.breadcrumbs',  # Breadcrumb navigation
        '.social-media', '.social-links', '.share-buttons',  # Social media
        '.cookie-notice', '.cookie-banner',  # Cookie notices
        '.advertisement', '.ads', '.banner',  # Advertisements
        '.search-box', '.search-form',  # Search functionality
        '.pagination', '.pager',  # Pagination controls
        '.back-to-top', '.top-link',  # Back to top links
        '.skip-links', '.accessibility-nav',  # Accessibility links
        '.print-page', '.print-button',  # Print functionality
        'script', 'style', 'noscript',  # Scripts and styles
        '.hidden', '.sr-only',  # Hidden elements
        '[role="banner"]', '[role="navigation"]', '[role="complementary"]'  # ARIA roles
    ]
    
    # Remove noise elements
    for selector in noise_selectors:
        elements = soup.select(selector)
        for element in elements:
            element.decompose()
    
    # Remove elements with specific text content that indicates navigation/noise
    noise_text_patterns = [
        r'skip to main content',
        r'use of cookies',
        r'shortcuts',
        r'share content',
        r'print page',
        r'back to top',
        r'study at the university',
        r'contact information',
        r'follow us',
        r'subscribe to',
        r'newsletter'
    ]
    
    # Find and remove elements with noise text
    for element in soup.find_all(text=True):
        if element.parent and element.strip():
            text_lower = element.strip().lower()
            for pattern in noise_text_patterns:
                if re.search(pattern, text_lower):
                    # Try to remove the containing element
                    parent = element.parent
                    if parent and parent.name not in ['html', 'body']:
                        parent.decompose()
                    break
    
    return soup


def extract_main_content_area(soup: BeautifulSoup) -> BeautifulSoup:
    """Extract the main content area, typically containing course information"""
    
    # Common selectors for main content areas
    main_content_selectors = [
        'main',
        '[role="main"]',
        '.main-content',
        '.content',
        '.course-content',
        '.syllabus-content',
        '.page-content',
        '#content',
        '#main-content',
        '.container .row',  # Bootstrap-style layouts
        '.wrapper .content'
    ]
    
    # Try to find the main content area
    main_content = None
    for selector in main_content_selectors:
        elements = soup.select(selector)
        if elements:
            # Use the first match that contains substantial content
            for element in elements:
                text_content = element.get_text().strip()
                if len(text_content) > 200:  # Ensure it has substantial content
                    main_content = element
                    break
            if main_content:
                break
    
    # If no specific main content area found, use the body content
    if not main_content:
        main_content = soup.find('body') or soup
    
    return main_content


def html_to_markdown(element) -> str:
    """Convert HTML element to clean markdown while preserving structure"""
    
    if not element:
        return ""
    
    markdown_lines = []
    
    # Process all child elements
    for child in element.children:
        if hasattr(child, 'name') and child.name:  # It's a tag with a name
            tag_name = child.name.lower()
            text_content = child.get_text().strip()
            
            if not text_content:  # Skip empty elements
                continue
                
            # Convert HTML tags to markdown equivalents
            if tag_name == 'h1':
                markdown_lines.append(f"# {text_content}")
            elif tag_name == 'h2':
                markdown_lines.append(f"## {text_content}")
            elif tag_name == 'h3':
                markdown_lines.append(f"### {text_content}")
            elif tag_name == 'h4':
                markdown_lines.append(f"#### {text_content}")
            elif tag_name == 'h5':
                markdown_lines.append(f"##### {text_content}")
            elif tag_name == 'h6':
                markdown_lines.append(f"###### {text_content}")
            elif tag_name == 'p':
                # Clean up paragraph text
                clean_text = re.sub(r'\s+', ' ', text_content).strip()
                if clean_text:
                    markdown_lines.append(clean_text)
            elif tag_name in ['ul', 'ol']:
                # Process lists
                list_items = child.find_all('li')
                for li in list_items:
                    item_text = li.get_text().strip()
                    if item_text:
                        clean_item = re.sub(r'\s+', ' ', item_text).strip()
                        markdown_lines.append(f"- {clean_item}")
            elif tag_name == 'table':
                # Process tables
                markdown_lines.append("\n**Table:**")
                rows = child.find_all('tr')
                for row in rows:
                    cells = row.find_all(['td', 'th'])
                    if cells:
                        row_text = ' | '.join([cell.get_text().strip() for cell in cells])
                        if row_text.strip():
                            markdown_lines.append(f"| {row_text} |")
            elif tag_name in ['strong', 'b']:
                markdown_lines.append(f"**{text_content}**")
            elif tag_name in ['em', 'i']:
                markdown_lines.append(f"*{text_content}*")
            elif tag_name in ['div', 'section', 'article']:
                # For container elements, process their content recursively
                nested_content = html_to_markdown(child)
                if nested_content.strip():
                    markdown_lines.append(nested_content)
            else:
                # For other elements, just include the text content
                clean_text = re.sub(r'\s+', ' ', text_content).strip()
                if clean_text and len(clean_text) > 3:
                    markdown_lines.append(clean_text)
                    
        elif hasattr(child, 'strip'):  # It's text content
            text_content = child.strip()
            if text_content:
                clean_text = re.sub(r'\s+', ' ', text_content).strip()
                if clean_text and len(clean_text) > 3:
                    markdown_lines.append(clean_text)
    
    # Join lines and clean up excessive whitespace
    markdown_content = '\n\n'.join([line for line in markdown_lines if line.strip()])
    
    # Clean up multiple consecutive newlines
    markdown_content = re.sub(r'\n{3,}', '\n\n', markdown_content)
    
    return markdown_content.strip()


def parse_syllabus_page(soup: BeautifulSoup, url: str) -> str:
    """Parse a syllabus webpage comprehensively, preserving all course content"""
    
    logger.debug(f"Starting comprehensive syllabus parsing for: {url}")
    
    # Step 1: Remove noise elements
    cleaned_soup = remove_noise_elements(soup)
    
    # Step 2: Extract main content area
    main_content = extract_main_content_area(cleaned_soup)
    
    # Step 3: Convert to markdown while preserving all content
    markdown_content = html_to_markdown(main_content)
    
    # Step 4: Add URL reference for debugging
    if markdown_content:
        final_content = f"# Course Syllabus\n\nSource: {url}\n\n{markdown_content}"
    else:
        final_content = f"# Course Syllabus\n\nSource: {url}\n\nNo content could be extracted from this page."
    
    logger.debug(f"Syllabus parsing completed. Content length: {len(final_content)} characters")
    return final_content


def parse_course_page(soup: BeautifulSoup, url: str) -> str:
    """Parse a course page comprehensively, preserving all enrollment and course information"""
    
    logger.debug(f"Starting comprehensive course page parsing for: {url}")
    
    # Step 1: Remove noise elements
    cleaned_soup = remove_noise_elements(soup)
    
    # Step 2: Extract main content area
    main_content = extract_main_content_area(cleaned_soup)
    
    # Step 3: Convert to markdown while preserving all content
    markdown_content = html_to_markdown(main_content)
    
    # Step 4: Add URL reference for debugging
    if markdown_content:
        final_content = f"# Course Information\n\nSource: {url}\n\n{markdown_content}"
    else:
        final_content = f"# Course Information\n\nSource: {url}\n\nNo content could be extracted from this page."
    
    logger.debug(f"Course page parsing completed. Content length: {len(final_content)} characters")
    return final_content


# ----- Main HTML Scraper Class -----

class DatabaseHTMLScraper:
    """Main HTML scraper with WebDriver pool and database integration"""
    
    def __init__(self, database_path: str = "data/csexpert.db", 
                 syllabi_dir: str = DEFAULT_SYLLABI_DIR,
                 course_dir: str = DEFAULT_COURSE_DIR,
                 webdriver_pool_size: int = 1):
        
        self.db_manager = get_database_manager(database_path)
        self.html_store = DatabaseHTMLStore(self.db_manager)
        
        # Create separate directories for different content types
        self.syllabi_dir = Path(syllabi_dir)
        self.course_dir = Path(course_dir)
        self.syllabi_dir.mkdir(parents=True, exist_ok=True)
        self.course_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize WebDriver pool
        self.webdriver_pool = get_global_pool(webdriver_pool_size)
        
        logger.info(f"Database HTML Scraper initialized: syllabi={syllabi_dir}, courses={course_dir}")
    
    def scrape_single_url(self, url_info: Dict) -> HTMLScrapingResult:
        """
        Scrape a single URL using WebDriver and BeautifulSoup
        
        Args:
            url_info: Dictionary with id, url, course_code
            
        Returns:
            HTMLScrapingResult: Result of the scraping attempt
        """
        url_id = url_info['id']
        url = url_info['url']
        course_code = url_info['course_code']
        
        start_time = time.time()
        
        result = HTMLScrapingResult(
            url_id=url_id,
            url=url,
            course_code=course_code
        )
        
        # Determine output directory based on URL type
        if '/syllabus/' in url:
            output_dir = self.syllabi_dir
            file_suffix = "_syllabus"
        else:
            output_dir = self.course_dir
            file_suffix = "_course"
        
        # Generate output filename
        safe_course_code = safe_filename(course_code)
        output_file = output_dir / f"{safe_course_code}{file_suffix}.md"
        
        # Check if file already exists
        if output_file.exists():
            file_size = output_file.stat().st_size
            if file_size > 100:  # At least 100 bytes
                try:
                    with open(output_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    result.success = True
                    result.markdown_content = content
                    result.file_path = str(output_file)
                    result.content_length = len(content)
                    result.scraping_time = 0.0  # Already existed
                    
                    logger.debug(f"File already exists: {safe_course_code}.md ({file_size} bytes)")
                    return result
                except Exception as e:
                    logger.warning(f"Error reading existing file {output_file}: {e}")
        
        # Attempt scraping with retry logic
        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                logger.debug(f"Scraping {course_code} (attempt {attempt + 1}): {url}")
                
                # Add rate limiting delay
                if attempt > 0:
                    time.sleep(RATE_LIMIT_DELAY)
                
                # Fetch HTML using WebDriver pool
                with self.webdriver_pool.get_driver(timeout=REQUEST_TIMEOUT) as driver:
                    driver.get(url)
                    time.sleep(3)  # Wait for page load
                    html_content = driver.page_source
                
                # Parse HTML with BeautifulSoup
                soup = BeautifulSoup(html_content, 'html.parser')
                
                # Check for 404 or other error pages
                title = soup.find('title')
                if title and '404' in title.get_text():
                    result.error = f"Page not found (404): {url}"
                    logger.warning(result.error)
                    break
                
                # Determine page type and parse accordingly
                if '/syllabus/' in url:
                    markdown_content = parse_syllabus_page(soup, url)
                else:
                    markdown_content = parse_course_page(soup, url)
                
                if markdown_content and len(markdown_content.strip()) > 50:
                    # Save to file
                    with open(output_file, 'w', encoding='utf-8') as f:
                        f.write(markdown_content)
                    
                    result.success = True
                    result.markdown_content = markdown_content
                    result.file_path = str(output_file)
                    result.content_length = len(markdown_content)
                    result.scraping_time = time.time() - start_time
                    
                    logger.debug(f"HTML scraping successful: {safe_course_code}.md ({len(markdown_content)} chars)")
                    break
                else:
                    result.error = f"No meaningful content extracted from {url}"
                    logger.warning(result.error)
                
            except Exception as e:
                error_msg = f"HTML scraping error (attempt {attempt + 1}): {str(e)}"
                result.error = error_msg
                logger.warning(error_msg)
                
                if attempt == MAX_RETRY_ATTEMPTS - 1:
                    logger.error(f"Max retry attempts reached for {course_code}: {url}")
                else:
                    time.sleep(RATE_LIMIT_DELAY * (attempt + 1))  # Exponential backoff
        
        result.scraping_time = time.time() - start_time
        return result
    
    def scrape_course_page(self, url: str):
        """Interface method for orchestrator - scrape a single course page URL."""
        try:
            # Extract course code from URL
            course_code = extract_course_code_from_url(url)
            if not course_code:
                logger.error(f"Could not extract course code from URL: {url}")
                return type('Result', (), {'success': False, 'error_message': 'Could not extract course code'})()
            
            # Look up the correct extraction_url_id from database
            try:
                query = "SELECT id FROM extraction_urls WHERE url = ? LIMIT 1"
                extraction_url_id_result = self.db_manager.execute_query(query, (url,))
                extraction_url_id = extraction_url_id_result[0][0] if extraction_url_id_result else None
            except Exception as e:
                logger.warning(f"Could not look up extraction_url_id for {url}: {e}")
                extraction_url_id = None
            
            # Create URL info dict (mimicking orchestrator format)
            url_info = {'id': extraction_url_id or 0, 'url': url, 'course_code': course_code}
            
            # Scrape the URL
            result = self.scrape_single_url(url_info)
            
            # Store result in database (only if we have a valid extraction_url_id)
            if extraction_url_id:
                self.html_store.store_scraping_result(result)
            else:
                logger.debug(f"Skipping database storage for {url} - no matching extraction_url_id")
            
            # Return orchestrator-compatible result
            return type('Result', (), {
                'success': result.success,
                'error_message': result.error
            })()
            
        except Exception as e:
            logger.error(f"Error in scrape_course_page for {url}: {e}")
            return type('Result', (), {'success': False, 'error_message': str(e)})()
    
    def cleanup(self):
        """Clean up resources"""
        logger.info("Cleaning up HTML scraper resources...")
        try:
            close_global_pool()
            logger.info("WebDriver pool closed")
        except Exception as e:
            logger.warning(f"Error closing WebDriver pool: {e}")


# ----- Main Function for Testing -----

def main():
    """Main entry point for testing HTML scraper"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Database HTML Scraper')
    parser.add_argument('--url', help='Test single URL')
    parser.add_argument('--database', default='data/csexpert.db', help='Database path')
    parser.add_argument('--output', default=DEFAULT_OUTPUT_DIR, help='Output directory')
    
    args = parser.parse_args()
    
    scraper = None
    try:
        scraper = DatabaseHTMLScraper(
            database_path=args.database,
            output_dir=args.output
        )
        
        if args.url:
            # Test single URL
            logger.info(f"Testing single URL: {args.url}")
            result = scraper.scrape_course_page(args.url)
            logger.info(f"Scraping result: Success={result.success}, Error={result.error_message}")
        else:
            logger.info("No URL provided for testing")
            
    except Exception as e:
        logger.error(f"HTML scraper test failed: {e}")
    
    finally:
        if scraper:
            scraper.cleanup()


if __name__ == "__main__":
    main()