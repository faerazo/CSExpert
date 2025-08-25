#!/usr/bin/env python3
"""
Database-Connected GU Course URL Extractor

This refactored version of the URL extractor integrates with the CSExpert database
and uses the WebDriver pooling system for optimal performance. It stores extracted
URLs directly in the database rather than intermediate files.
"""

import logging
import re
import time
import requests
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from datetime import datetime

from bs4 import BeautifulSoup

# Import our improved components
from scraper.webdriver_pool import get_global_pool, close_global_pool
from database.connection_manager import get_database_manager, DatabaseManager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ----- Configuration Constants -----

# Base URL for the university website
BASE_URL = "https://www.gu.se"

# Course code prefixes to search for
COURSE_PREFIXES = ["dit0", "dit1", "dit2", "dit3", "dit4", "dit5", "dit6", "dit7", "dit8", "dit9", 
                  "msg", "msa", "mma", "tia", "lt"]

# Pattern fragments for URL construction
SYLLABUS_SEARCH_URL = f"{BASE_URL}/en/study-gothenburg/study-options/find-syllabus-and-reading-list?hits=200&q="
COURSE_PAGE_SEARCH_URL = f"{BASE_URL}/en/study-gothenburg/study-options/find-courses?education_type.keyword=Course&hits=200&q="

# Regular expressions for course code extraction
# Updated to handle LT courses with 4 digits (e.g., LT2813)
PDF_URL_PATTERN = r"/pdf/kurs/[a-z]{2}/([A-Z]{2,3}\d{3,4})"
WEB_URL_PATTERN = r"-((?:dit|msg|msa|mma|tia|lt)\d{3,4})/syllabus"

# Additional patterns for course page URLs and program codes  
# Updated to handle LT courses with 4 digits (e.g., LT2813)
COURSE_PAGE_PATTERN = r"study-gothenburg/[^/]+-([a-z]{2,3}\d{3,4})(?:/|$)"
PROGRAM_CODE_PATTERN = r"programme-([n][12][a-z]{3})(?:/|$)"

# Pattern for GUID-based syllabus URLs (to be filtered or handled specially)
GUID_SYLLABUS_PATTERN = r"/syllabus/[0-9a-f-]{36}"

# ----- Data Structures -----

@dataclass
class ExtractedURL:
    """Container for URL extraction results"""
    url: str
    url_type: str  # 'syllabus', 'course_page', 'program_page', or 'program_syllabus'
    course_code: Optional[str] = None
    source_search_url: Optional[str] = None
    extracted_at: Optional[datetime] = None
    
    def __post_init__(self):
        if self.extracted_at is None:
            self.extracted_at = datetime.utcnow()


@dataclass 
class ExtractionResult:
    """Container for storing complete extraction results"""
    syllabus_urls: List[ExtractedURL] = None
    course_page_urls: List[ExtractedURL] = None
    total_urls: int = 0
    unique_course_codes: Set[str] = None
    processing_time: float = 0.0
    
    def __post_init__(self):
        self.syllabus_urls = self.syllabus_urls or []
        self.course_page_urls = self.course_page_urls or []
        self.unique_course_codes = self.unique_course_codes or set()


# ----- Database Operations -----

class DatabaseURLStore:
    """Handles database operations for URL storage and retrieval"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.setup_tables()
    
    def setup_tables(self):
        """Ensure extraction tables exist in database"""
        try:
            with self.db_manager.transaction() as conn:
                # Create extraction_urls table for storing discovered URLs
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS extraction_urls (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        url TEXT NOT NULL,
                        url_type TEXT NOT NULL CHECK (url_type IN ('syllabus', 'course_page', 'program_page', 'program_syllabus')),
                        course_code VARCHAR(10),
                        source_search_url TEXT,
                        extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        status VARCHAR(20) DEFAULT 'pending',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        
                        UNIQUE(url, url_type)
                    )
                """)
                
                # Create indexes for performance
                conn.execute("CREATE INDEX IF NOT EXISTS idx_extraction_urls_course_code ON extraction_urls(course_code)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_extraction_urls_type ON extraction_urls(url_type)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_extraction_urls_status ON extraction_urls(status)")
                
                logger.info("URL extraction tables initialized")
                
        except Exception as e:
            logger.error(f"Failed to setup extraction tables: {e}")
            raise
    
    def store_extracted_url(self, extracted_url: ExtractedURL) -> bool:
        """Store a single extracted URL in database"""
        try:
            query = """
                INSERT OR REPLACE INTO extraction_urls 
                (url, url_type, course_code, source_search_url, extracted_at)
                VALUES (?, ?, ?, ?, ?)
            """
            
            self.db_manager.execute_update(query, (
                extracted_url.url,
                extracted_url.url_type,
                extracted_url.course_code,
                extracted_url.source_search_url,
                extracted_url.extracted_at
            ))
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to store URL {extracted_url.url}: {e}")
            return False
    
    def fix_missing_course_codes(self) -> int:
        """Fix existing database entries with NULL course codes, including GUID URL resolution."""
        try:
            # Get all URLs with NULL course codes
            null_code_urls = self.db_manager.execute_query(
                "SELECT id, url FROM extraction_urls WHERE course_code IS NULL"
            )
            
            fixed_count = 0
            resolved_count = 0
            
            for row in null_code_urls:
                url_id = row['id']
                url = row['url']
                
                # First try to extract course code with existing patterns
                course_code = extract_course_code(url)
                
                if course_code:
                    # Update the database entry with extracted course code
                    self.db_manager.execute_update(
                        "UPDATE extraction_urls SET course_code = ? WHERE id = ?",
                        (course_code, url_id)
                    )
                    fixed_count += 1
                    logger.info(f"Fixed course code: {course_code} for URL {url}")
                
                elif _is_guid_syllabus_url(url):
                    # Try to resolve GUID URL to full course URL
                    logger.info(f"Attempting to resolve GUID URL: {url}")
                    resolved_url = resolve_guid_url(url)
                    
                    if resolved_url:
                        # Extract course code from resolved URL
                        resolved_course_code = extract_course_code(resolved_url)
                        
                        if resolved_course_code:
                            # Update database with both resolved URL and course code
                            self.db_manager.execute_update(
                                "UPDATE extraction_urls SET url = ?, course_code = ? WHERE id = ?",
                                (resolved_url, resolved_course_code, url_id)
                            )
                            fixed_count += 1
                            resolved_count += 1
                            logger.info(f"Resolved GUID URL: {resolved_course_code} - {resolved_url}")
                        else:
                            logger.warning(f"Resolved URL but could not extract course code: {resolved_url}")
                    else:
                        logger.warning(f"Failed to resolve GUID URL: {url}")
                        
                    # Add small delay to avoid overwhelming the server
                    time.sleep(0.5)
                
                else:
                    logger.debug(f"Could not extract course code from: {url}")
            
            logger.info(f"Course code fixing complete: {fixed_count} fixed ({resolved_count} from GUID resolution)")
            return fixed_count
            
        except Exception as e:
            logger.error(f"Failed to fix missing course codes: {e}")
            return 0
    
    def insert_program_urls(self) -> int:
        """Insert specific program URLs manually into the database."""
        program_urls = [
            ("https://www.gu.se/en/study-gothenburg/computer-science-masters-programme-n2cos", "N2COS"),
            ("https://www.gu.se/en/study-gothenburg/game-design-technology-masters-programme-n2gdt", "N2GDT"),
            ("https://www.gu.se/en/study-gothenburg/software-engineering-and-management-masters-programme-n2sof", "N2SOF"),
            ("https://www.gu.se/en/study-gothenburg/data-science-big-data", "N2ADS"),  # Data Science Master's Programme
            ("https://www.gu.se/en/study-gothenburg/software-engineering-and-management-bachelors-programme-n1sof", "N1SOF"),
        ]
        
        inserted_count = 0
        for url, program_code in program_urls:
            try:
                # Check if already exists
                existing = self.db_manager.execute_query(
                    "SELECT id FROM extraction_urls WHERE url = ? AND url_type = 'program_page'",
                    (url,)
                )
                
                if not existing:
                    query = """
                        INSERT INTO extraction_urls 
                        (url, url_type, course_code, source_search_url, extracted_at)
                        VALUES (?, ?, ?, ?, ?)
                    """
                    
                    self.db_manager.execute_update(query, (
                        url, 'program_page', program_code, 'manual_insertion', datetime.now()
                    ))
                    inserted_count += 1
                    logger.info(f"Inserted program URL: {program_code} - {url}")
                else:
                    logger.debug(f"Program URL already exists: {program_code}")
                    
            except Exception as e:
                logger.error(f"Failed to insert program URL {url}: {e}")
        
        return inserted_count
    
    def insert_program_syllabus_urls(self) -> int:
        """Insert specific program syllabus URLs manually into the database."""
        program_syllabus_urls = [
            ("https://www.gu.se/sites/default/files/2023-09/GU2023-1727_faststa%CC%88lld_utbildningsplan_N1SOF_220616_eng%5B2%5D.pdf", "N1SOF"),
            ("https://www.gu.se/en/study-gothenburg/computer-science-masters-programme-n2cos/syllabus/f9915049-2d48-11ef-a2a0-4c1db4504bb5", "N2COS"),
            ("https://www.gu.se/sites/default/files/2022-09/GU2022-2361%20beslutad%20UP%20N2GDT%20eng%20220913.pdf", "N2GDT"),
            ("https://www.gu.se/sites/default/files/2023-10/N2SOF_Utbildningsplan%20%28en%29%5B50%5D.pdf", "N2SOF"),
        ]
        
        inserted_count = 0
        for url, program_code in program_syllabus_urls:
            try:
                # Check if already exists
                existing = self.db_manager.execute_query(
                    "SELECT id FROM extraction_urls WHERE url = ? AND url_type = 'program_syllabus'",
                    (url,)
                )
                
                if not existing:
                    query = """
                        INSERT INTO extraction_urls 
                        (url, url_type, course_code, source_search_url, extracted_at)
                        VALUES (?, ?, ?, ?, ?)
                    """
                    
                    self.db_manager.execute_update(query, (
                        url, 'program_syllabus', program_code, 'manual_insertion', datetime.now()
                    ))
                    inserted_count += 1
                    logger.info(f"Inserted program syllabus URL: {program_code} - {url}")
                else:
                    logger.debug(f"Program syllabus URL already exists: {program_code}")
                    
            except Exception as e:
                logger.error(f"Failed to insert program syllabus URL {url}: {e}")
        
        return inserted_count
    
    def store_batch_urls(self, extracted_urls: List[ExtractedURL]) -> int:
        """Store multiple URLs in a batch transaction"""
        if not extracted_urls:
            return 0
            
        successful_stores = 0
        try:
            queries = []
            for url in extracted_urls:
                queries.append((
                    """
                    INSERT OR REPLACE INTO extraction_urls 
                    (url, url_type, course_code, source_search_url, extracted_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (url.url, url.url_type, url.course_code, url.source_search_url, url.extracted_at)
                ))
            
            results = self.db_manager.execute_batch(queries)
            successful_stores = sum(results)
            
            logger.info(f"Stored {successful_stores} URLs in database")
            return successful_stores
            
        except Exception as e:
            logger.error(f"Batch URL storage failed: {e}")
            return 0
    
    def get_urls_by_type(self, url_type: str, status: str = None) -> List[Dict]:
        """Retrieve URLs by type from database"""
        try:
            base_query = "SELECT * FROM extraction_urls WHERE url_type = ?"
            params = [url_type]
            
            if status is not None:
                base_query += " AND status = ?"
                params.append(status)
            
            base_query += " ORDER BY extracted_at DESC"
            
            results = self.db_manager.execute_query(base_query, tuple(params))
            return [dict(row) for row in results]
            
        except Exception as e:
            logger.error(f"Failed to retrieve URLs by type {url_type}: {e}")
            return []
    
    def get_extraction_statistics(self) -> Dict:
        """Get statistics about extracted URLs"""
        try:
            with self.db_manager.get_connection() as conn:
                stats = {}
                
                # Total URLs by type
                cursor = conn.execute("""
                    SELECT url_type, COUNT(*) as count 
                    FROM extraction_urls 
                    GROUP BY url_type
                """)
                stats['by_type'] = {row['url_type']: row['count'] for row in cursor.fetchall()}
                
                # Processing status
                cursor = conn.execute("""
                    SELECT status, COUNT(*) as count 
                    FROM extraction_urls 
                    GROUP BY status
                """)
                stats['by_status'] = {row['status']: row['count'] for row in cursor.fetchall()}
                
                # Unique course codes
                cursor = conn.execute("""
                    SELECT COUNT(DISTINCT course_code) as unique_codes 
                    FROM extraction_urls 
                    WHERE course_code IS NOT NULL
                """)
                stats['unique_course_codes'] = cursor.fetchone()['unique_codes']
                
                # Latest extraction time
                cursor = conn.execute("""
                    SELECT MAX(extracted_at) as latest_extraction 
                    FROM extraction_urls
                """)
                latest = cursor.fetchone()['latest_extraction']
                stats['latest_extraction'] = latest
                
                return stats
                
        except Exception as e:
            logger.error(f"Failed to get extraction statistics: {e}")
            return {}
    
    def mark_urls_processed(self, url_ids: List[int]) -> int:
        """Mark URLs as processed"""
        if not url_ids:
            return 0
            
        try:
            placeholders = ','.join(['?'] * len(url_ids))
            query = f"UPDATE extraction_urls SET status = 'completed' WHERE id IN ({placeholders})"
            return self.db_manager.execute_update(query, tuple(url_ids))
            
        except Exception as e:
            logger.error(f"Failed to mark URLs as processed: {e}")
            return 0


# ----- URL Processing Functions -----

def format_url(url: str) -> str:
    """Format a URL by adding the base URL if needed."""
    if url.startswith(("http://", "https://")):
        return url
    return f"{BASE_URL}{url}"


def extract_course_code(url: str) -> Optional[str]:
    """Extract a course code (e.g., DIT123, MSG123, N2COS) from a URL."""
    # Try to match PDF pattern (e.g., /pdf/kurs/en/DIT123)
    pdf_match = re.search(PDF_URL_PATTERN, url, re.IGNORECASE)
    if pdf_match:
        return pdf_match.group(1).upper()
    
    # Try to match web syllabus pattern (e.g., course-title-dit123/syllabus)
    web_match = re.search(WEB_URL_PATTERN, url, re.IGNORECASE)
    if web_match:
        return web_match.group(1).upper()
    
    # Try to match course page pattern (e.g., study-gothenburg/course-title-dit123)
    course_page_match = re.search(COURSE_PAGE_PATTERN, url, re.IGNORECASE)
    if course_page_match:
        return course_page_match.group(1).upper()
    
    # Try to match program code pattern (e.g., programme-n2cos)
    program_match = re.search(PROGRAM_CODE_PATTERN, url, re.IGNORECASE)
    if program_match:
        return program_match.group(1).upper()
    
    # Check if this is a GUID-based syllabus URL that we should filter out
    guid_match = re.search(GUID_SYLLABUS_PATTERN, url, re.IGNORECASE)
    if guid_match:
        logger.warning(f"Found GUID-based syllabus URL without course code: {url}")
        return None  # Return None for GUID URLs as they don't contain course codes
    
    return None


def extract_course_urls(html_content: str) -> List[str]:
    """Extract course URLs from HTML content and filter out reading lists only."""
    soup = BeautifulSoup(html_content, 'html.parser')
    course_links = soup.find_all('a', class_='link link--large u-font-weight-700')
    urls = [link.get('href') for link in course_links if link.get('href')]
    
    # Filter out reading list URLs only (preserve GUID-based syllabus URLs for processing)
    filtered_urls = []
    for url in urls:
        if _is_reading_list_url(url):
            continue
        if _is_guid_syllabus_url(url):
            logger.debug(f"Found GUID-based syllabus URL for processing: {url}")
        filtered_urls.append(url)
    
    return filtered_urls


def _is_reading_list_url(url: str) -> bool:
    """Check if a URL is for a reading list."""
    return "reading-list" in url or "_Litteratur_" in url


def _is_guid_syllabus_url(url: str) -> bool:
    """Check if a URL is a GUID-based syllabus URL without course code."""
    return bool(re.search(GUID_SYLLABUS_PATTERN, url, re.IGNORECASE))


def _determine_url_type(url: str) -> str:
    """Determine the correct URL type based on URL structure."""
    # Check for PDF syllabus URLs (kursplaner.gu.se/pdf/)
    if '/pdf/kurs/' in url:
        return 'syllabus'  # PDF syllabus
    
    # Check for webpage syllabus URLs (study-gothenburg/.../syllabus/)
    if '/study-gothenburg/' in url and '/syllabus/' in url:
        return 'syllabus'  # Webpage syllabus (will be processed by Firecrawl)
    
    # Check for course pages (study-gothenburg/... but no /syllabus/)
    if '/study-gothenburg/' in url and '/syllabus/' not in url:
        return 'course_page'
    
    # Check for program pages
    if '/programme-' in url:
        return 'program_page'
    
    # Default to syllabus for any other patterns
    return 'syllabus'


def resolve_guid_url(guid_url: str, timeout: int = 5) -> Optional[str]:
    """
    Resolve a GUID-based URL to its full course URL by following redirects.
    
    Args:
        guid_url: GUID-based URL like https://www.gu.se/en/syllabus/5cced9dc-4ac8-11f0-8e50-d6e0442f447c
        timeout: Request timeout in seconds
        
    Returns:
        Full resolved URL with course code or None if resolution fails
    """
    if not _is_guid_syllabus_url(guid_url):
        return None
    
    try:
        # Use HEAD request to follow redirects without downloading content
        headers = {
            'User-Agent': 'Mozilla/5.0 (CSExpert URL Extractor) GU Course Scraper'
        }
        
        response = requests.head(
            guid_url, 
            allow_redirects=True, 
            timeout=timeout,
            headers=headers
        )
        
        # Check if we got a successful response
        if response.status_code == 200:
            resolved_url = response.url
            
            # Verify the resolved URL is different and contains course info
            if resolved_url != guid_url and 'study-gothenburg' in resolved_url:
                logger.debug(f"Resolved GUID URL: {guid_url} -> {resolved_url}")
                return resolved_url
            else:
                logger.warning(f"GUID URL resolved but no course info found: {resolved_url}")
                return None
        else:
            logger.warning(f"GUID URL resolution failed with status {response.status_code}: {guid_url}")
            return None
            
    except requests.exceptions.Timeout:
        logger.warning(f"Timeout resolving GUID URL: {guid_url}")
        return None
    except requests.exceptions.RequestException as e:
        logger.warning(f"Error resolving GUID URL {guid_url}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error resolving GUID URL {guid_url}: {e}")
        return None


# ----- Web Scraping Functions -----

class DatabaseURLExtractor:
    """Main URL extractor with database integration and WebDriver pooling"""
    
    def __init__(self, database_path: str = "data/csexpert.db", webdriver_pool_size: int = 3):
        self.db_manager = get_database_manager(database_path)
        self.url_store = DatabaseURLStore(self.db_manager)
        self.webdriver_pool = get_global_pool(webdriver_pool_size)
        
        # Initialize database if not already done
        if not self.db_manager.initialize_database():
            raise RuntimeError("Failed to initialize database")
        
        logger.info(f"Database URL Extractor initialized with pool size: {webdriver_pool_size}")
    
    def fetch_webpage_content(self, url: str) -> Optional[str]:
        """Fetch HTML content using pooled WebDriver"""
        try:
            with self.webdriver_pool.get_driver(timeout=30) as driver:
                driver.get(url)
                # Wait for dynamic content
                time.sleep(3)  # Reduced from 5s for better performance
                return driver.page_source
                
        except Exception as e:
            logger.error(f"Error fetching webpage {url}: {e}")
            return None
    
    def process_search_page(self, search_url: str, url_type: str) -> List[ExtractedURL]:
        """Process a search results page to extract course URLs"""
        logger.info(f"Processing {url_type} search: {search_url}")
        
        html_content = self.fetch_webpage_content(search_url)
        if not html_content:
            logger.warning(f"Failed to fetch content from: {search_url}")
            return []
        
        course_urls = extract_course_urls(html_content)
        logger.info(f"Found {len(course_urls)} URLs from search page")
        
        # Create ExtractedURL objects with GUID resolution and proper URL type detection
        extracted_urls = []
        for url in course_urls:
            formatted_url = format_url(url)
            course_code = extract_course_code(formatted_url)
            
            # If no course code and it's a GUID URL, try to resolve it
            if not course_code and _is_guid_syllabus_url(formatted_url):
                logger.debug(f"Attempting to resolve GUID URL during extraction: {formatted_url}")
                resolved_url = resolve_guid_url(formatted_url)
                
                if resolved_url:
                    resolved_course_code = extract_course_code(resolved_url)
                    if resolved_course_code:
                        formatted_url = resolved_url
                        course_code = resolved_course_code
                        logger.info(f"Resolved GUID during extraction: {course_code} - {resolved_url}")
                    
                # Small delay to avoid overwhelming server during batch processing
                time.sleep(0.3)
            
            # Determine the correct URL type based on URL structure
            detected_url_type = _determine_url_type(formatted_url)
            
            extracted_url = ExtractedURL(
                url=formatted_url,
                url_type=detected_url_type,
                course_code=course_code,
                source_search_url=search_url
            )
            extracted_urls.append(extracted_url)
        
        return extracted_urls
    
    def build_search_urls(self) -> Dict[str, List[str]]:
        """Build all search URLs based on configured prefixes"""
        # Generate syllabus search URLs for each prefix
        syllabus_urls = [f"{SYLLABUS_SEARCH_URL}{prefix}" for prefix in COURSE_PREFIXES]
        
        # Generate course page search URLs (unique prefixes only)
        unique_prefixes = set([prefix.rstrip('0123456789') for prefix in COURSE_PREFIXES])
        course_page_urls = [f"{COURSE_PAGE_SEARCH_URL}{prefix}" for prefix in unique_prefixes]
        
        return {
            "syllabus": syllabus_urls,
            "course_pages": course_page_urls
        }
    
    def extract_all_course_urls(self):
        """Extract all course URLs - interface method for orchestrator."""
        result = self.extract_all_urls(store_immediately=True)
        return type('Result', (), {
            'success': True, 
            'total_urls_found': result.total_urls,
            'error_message': None
        })()
    
    def extract_all_urls(self, store_immediately: bool = True) -> ExtractionResult:
        """Extract all course URLs and optionally store in database immediately"""
        start_time = time.time()
        result = ExtractionResult()
        search_urls = self.build_search_urls()
        
        logger.info("Starting comprehensive URL extraction...")
        
        try:
            # Process syllabus search pages
            logger.info("--- Extracting Course Syllabi URLs ---")
            for search_url in search_urls["syllabus"]:
                extracted_urls = self.process_search_page(search_url, "syllabus")
                result.syllabus_urls.extend(extracted_urls)
                
                # Extract course codes
                for url in extracted_urls:
                    if url.course_code:
                        result.unique_course_codes.add(url.course_code)
                
                if store_immediately and extracted_urls:
                    stored_count = self.url_store.store_batch_urls(extracted_urls)
                    logger.debug(f"Stored {stored_count} syllabus URLs from this search")
            
            # Process course page search URLs
            logger.info("--- Extracting Course Page URLs ---")
            for search_url in search_urls["course_pages"]:
                extracted_urls = self.process_search_page(search_url, "course_page")
                result.course_page_urls.extend(extracted_urls)
                
                if store_immediately and extracted_urls:
                    stored_count = self.url_store.store_batch_urls(extracted_urls)
                    logger.debug(f"Stored {stored_count} course page URLs from this search")
            
            # Store remaining URLs if not stored immediately
            if not store_immediately:
                all_urls = result.syllabus_urls + result.course_page_urls
                if all_urls:
                    stored_count = self.url_store.store_batch_urls(all_urls)
                    logger.info(f"Stored {stored_count} total URLs to database")
            
            # Fix existing NULL course codes
            logger.info("--- Fixing Missing Course Codes ---")
            fixed_codes = self.url_store.fix_missing_course_codes()
            logger.info(f"Course codes fixed: {fixed_codes}")
            
            # Insert program URLs
            logger.info("--- Inserting Program URLs ---")
            program_urls_inserted = self.url_store.insert_program_urls()
            logger.info(f"Program URLs inserted: {program_urls_inserted}")
            
            # Insert program syllabus URLs
            logger.info("--- Inserting Program Syllabus URLs ---")
            program_syllabus_urls_inserted = self.url_store.insert_program_syllabus_urls()
            logger.info(f"Program syllabus URLs inserted: {program_syllabus_urls_inserted}")
            
            # Calculate totals
            result.total_urls = len(result.syllabus_urls) + len(result.course_page_urls) + program_urls_inserted + program_syllabus_urls_inserted
            result.processing_time = time.time() - start_time
            
            # Log summary
            logger.info("--- URL Extraction Summary ---")
            logger.info(f"Syllabus URLs: {len(result.syllabus_urls)}")
            logger.info(f"Course page URLs: {len(result.course_page_urls)}")
            logger.info(f"Program URLs: {program_urls_inserted}")
            logger.info(f"Program syllabus URLs: {program_syllabus_urls_inserted}")
            logger.info(f"Total URLs: {result.total_urls}")
            logger.info(f"Unique course codes: {len(result.unique_course_codes)}")
            logger.info(f"Processing time: {result.processing_time:.2f} seconds")
            
            return result
            
        except Exception as e:
            logger.error(f"URL extraction failed: {e}")
            raise
    
    def get_extraction_statistics(self) -> Dict:
        """Get statistics about stored URLs"""
        return self.url_store.get_extraction_statistics()
    
    def get_unprocessed_urls(self, url_type: str = None) -> List[Dict]:
        """Get URLs that haven't been processed yet"""
        if url_type:
            return self.url_store.get_urls_by_type(url_type, status='pending')
        else:
            # Get all unprocessed URLs
            syllabus_urls = self.url_store.get_urls_by_type("syllabus", status='pending')
            course_urls = self.url_store.get_urls_by_type("course_page", status='pending')
            return syllabus_urls + course_urls
    
    def mark_urls_processed(self, url_ids: List[int]) -> int:
        """Mark URLs as processed after successful handling"""
        return self.url_store.mark_urls_processed(url_ids)
    
    def cleanup(self):
        """Clean up resources"""
        logger.info("Cleaning up URL extractor resources...")
        try:
            close_global_pool()
            logger.info("WebDriver pool closed")
        except Exception as e:
            logger.warning(f"Error closing WebDriver pool: {e}")


# ----- Main Functions -----

def main():
    """Main entry point for database URL extraction"""
    logger.info("Starting Database-Connected GU Course URL Extractor")
    
    extractor = None
    try:
        # Initialize extractor
        extractor = DatabaseURLExtractor()
        
        # Extract all URLs and store in database
        result = extractor.extract_all_urls(store_immediately=True)
        
        # Display results
        logger.info("\n=== EXTRACTION COMPLETE ===")
        logger.info(f"✓ Extracted {result.total_urls} URLs in {result.processing_time:.2f} seconds")
        logger.info(f"✓ Found {len(result.unique_course_codes)} unique course codes")
        
        # Show database statistics
        stats = extractor.get_extraction_statistics()
        logger.info(f"✓ Database contains: {stats}")
        
        # Show a few sample URLs
        if result.syllabus_urls:
            logger.info("\nSample syllabus URLs:")
            for url in result.syllabus_urls[:3]:
                logger.info(f"  {url.course_code}: {url.url}")
        
        return True
        
    except Exception as e:
        logger.error(f"URL extraction failed: {e}")
        return False
    
    finally:
        if extractor:
            extractor.cleanup()


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)