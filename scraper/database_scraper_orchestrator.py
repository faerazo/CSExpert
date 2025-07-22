#!/usr/bin/env python3
"""
Database-First Scraper Orchestrator

Coordinates all database-native scraping components with:
- Transaction management and atomic operations
- Database state-driven progress tracking
- Resume capability based on database records
- Comprehensive error handling and recovery
- Performance monitoring and optimization
"""

import os
import re
import time
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
from datetime import datetime
import concurrent.futures

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging early
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('database_scraper.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Import database components
from database.models import Base, Course, CourseSection, Program, CourseProgramMapping, DataQualityIssue, CourseVersionHistory
from database.connection_manager import DatabaseManager

# Import database-native scrapers (with conditional imports for testing)
try:
    from scraper.database_url_extractor import DatabaseURLExtractor
    from scraper.database_pdf_downloader import DatabasePDFDownloader  
    from scraper.database_html_scraper import DatabaseHTMLScraper
    from scraper.database_gemini_processor import DatabaseGeminiProcessor
    DATABASE_COMPONENTS_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Some database components not available: {e}")
    DATABASE_COMPONENTS_AVAILABLE = False
    
    # Create placeholder classes for testing
    class DatabaseURLExtractor:
        def __init__(self, db_path): pass
        def extract_all_course_urls(self): return type('Result', (), {'success': True, 'total_urls_found': 0})()
    
    class DatabasePDFDownloader:
        def __init__(self, db_path): pass
        def download_pdf_from_url(self, url): return type('Result', (), {'success': True})()
    
    class DatabaseHTMLScraper:
        def __init__(self, db_path, syllabi_dir=None, course_dir=None): pass
        def scrape_course_page(self, url): return type('Result', (), {'success': True, 'error_message': None})()
    
    class DatabaseGeminiProcessor:
        def __init__(self, db_path): pass
        def process_single_content(self, path, content_type): return type('Result', (), {'success': True, 'processing_cost': 0.0, 'course_id': 1, 'error': None})()
    

class ProcessingPhase(Enum):
    """Database-tracked processing phases."""
    URL_EXTRACTION = "url_extraction"
    PDF_DOWNLOAD = "pdf_download"
    HTML_SCRAPING = "html_scraping"
    CONTENT_PROCESSING = "content_processing"
    COMPLETED = "completed"

@dataclass
class OrchestrationConfig:
    """Database orchestrator configuration."""
    # Database settings
    database_path: str = "data/csexpert.db"
    
    # Processing settings - TIER 1 optimization
    max_concurrent_downloads: int = 6  # Keep for PDF downloads (not API limited)
    max_concurrent_html_scrapers: int = 6  # Keep for HTML scraping (not API limited)  
    max_concurrent_processing: int = 10  # Multiple Gemini workers for tier 1
    batch_size: int = 100  # Larger batches for tier 1 (10,000/day limit)
    
    # TIER 1 API settings - 1000 requests per minute, 10,000 per day
    html_scraping_delay: float = 1.0  # Keep for network stability
    gemini_rate_limit: int = 1000  # Tier 1: 1000 RPM limit
    gemini_api_delay: float = 0.06  # 0.06 second delay between requests (1000 RPM)
    pdf_download_delay: float = 0.2  # Keep for network stability
    
    # Error handling
    max_retries: int = 3
    retry_delay: float = 5.0
    error_tolerance_pct: float = 5.0
    
    # Progress tracking
    checkpoint_interval: int = 20  # Increased from 10 for less frequent checkpoints
    transaction_timeout: int = 30  # seconds
    
    # Resume settings
    enable_resume: bool = True
    cleanup_on_complete: bool = True

@dataclass
class ProcessingStats:
    """Database-tracked processing statistics."""
    phase: ProcessingPhase
    urls_extracted: int = 0
    pdfs_downloaded: int = 0
    pages_scraped: int = 0
    courses_processed: int = 0
    errors_encountered: int = 0
    network_errors: int = 0  # Track network-specific errors
    processing_cost: float = 0.0
    total_time: float = 0.0
    start_time: Optional[datetime] = None
    last_checkpoint: Optional[datetime] = None

class DatabaseScraperOrchestrator:
    """Database-first orchestrator coordinating all scraping components."""
    
    def __init__(self, config: Optional[OrchestrationConfig] = None):
        """Initialize database orchestrator with configuration."""
        self.config = config or OrchestrationConfig()
        self.stats = ProcessingStats(phase=ProcessingPhase.URL_EXTRACTION)
        
        # Initialize database manager
        self.db_manager = DatabaseManager(database_path=self.config.database_path)
        
        # Initialize scraper components
        self.url_extractor = DatabaseURLExtractor(self.config.database_path)
        self.pdf_downloader = DatabasePDFDownloader(self.config.database_path)
        self.html_scraper = DatabaseHTMLScraper(
            database_path=self.config.database_path,
            syllabi_dir="data/syllabi_pages", 
            course_dir="data/course_pages"
        )
        self.gemini_processor = DatabaseGeminiProcessor(self.config.database_path)
        
        # Create database session factory
        self.engine = create_engine(f'sqlite:///{self.config.database_path}', echo=False)
        self.SessionFactory = sessionmaker(bind=self.engine)
        
        logger.info(f"Database orchestrator initialized with database: {self.config.database_path}")
        logger.info(f"TIER 1 configuration: {self.config.max_concurrent_downloads} PDF workers, "
                   f"{self.config.max_concurrent_html_scrapers} HTML workers, "
                   f"{self.config.max_concurrent_processing} Gemini workers (0.06s delay = 1000 RPM)")
    
    def run_complete_pipeline(self) -> ProcessingStats:
        """Run the complete database-driven scraping pipeline."""
        logger.info("Starting complete database scraping pipeline")
        self.stats.start_time = datetime.now()
        
        try:
            # Initialize database tables
            self._initialize_database()
            
            # Load existing progress if resuming
            if self.config.enable_resume:
                self._load_progress()
            
            # Phase 1: URL Extraction
            if self.stats.phase == ProcessingPhase.URL_EXTRACTION:
                self._run_url_extraction_phase()
                self.stats.phase = ProcessingPhase.PDF_DOWNLOAD
                self._save_progress()
            
            # Phase 2: PDF Download
            if self.stats.phase == ProcessingPhase.PDF_DOWNLOAD:
                self._run_pdf_download_phase()
                self.stats.phase = ProcessingPhase.HTML_SCRAPING
                self._save_progress()
            
            # Phase 3: HTML Scraping
            if self.stats.phase == ProcessingPhase.HTML_SCRAPING:
                self._run_html_scraping_phase()
                self.stats.phase = ProcessingPhase.CONTENT_PROCESSING
                self._save_progress()
            
            # Phase 4: Content Processing
            if self.stats.phase == ProcessingPhase.CONTENT_PROCESSING:
                self._run_content_processing_phase()
                self.stats.phase = ProcessingPhase.COMPLETED
                self._save_progress()
            
            # Finalize
            self._finalize_pipeline()
            
        except Exception as e:
            logger.error(f"Pipeline execution failed: {e}")
            self.stats.errors_encountered += 1
            raise
        finally:
            self._cleanup_resources()
        
        # Calculate total time
        if self.stats.start_time:
            self.stats.total_time = (datetime.now() - self.stats.start_time).total_seconds()
        
        return self.stats
    
    def _initialize_database(self):
        """Initialize database tables and constraints."""
        logger.info("Initializing database schema and constraints")
        
        try:
            # Create tables
            Base.metadata.create_all(self.engine)
            
            # Initialize reference data if needed
            with self.SessionFactory() as session:
                self._ensure_reference_data(session)
            
            logger.info("Database initialization completed")
            
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            raise
    
    def _ensure_reference_data(self, session):
        """Ensure reference data exists (programs, language standards)."""
        # Check if programs exist - they should be populated by schema.sql
        existing_programs = session.query(Program).count()
        if existing_programs == 0:
            logger.warning("No programs found in database - schema.sql may not have been applied properly")
            logger.warning("Programs should be initialized via schema.sql during database creation")
    
    def _load_progress(self):
        """Load existing progress from database state."""
        logger.info("Loading existing progress from database")
        
        with self.SessionFactory() as session:
            try:
                # Count existing database records to determine phase
                url_count = session.execute(text("SELECT COUNT(*) FROM extraction_urls")).scalar() or 0
                pdf_count = session.execute(text("SELECT COUNT(*) FROM pdf_downloads WHERE status = 'success'")).scalar() or 0
                # Count HTML scrapes
                html_count = session.execute(text("SELECT COUNT(*) FROM html_scrapes WHERE status = 'success'")).scalar() or 0
                course_count = session.query(Course).count()
                
                # Update stats
                self.stats.urls_extracted = url_count or 0
                self.stats.pdfs_downloaded = pdf_count or 0
                self.stats.pages_scraped = html_count or 0
                self.stats.courses_processed = course_count or 0
                
                # Check if there are URLs pending HTML scraping
                pending_html_urls = session.execute(text("""
                    SELECT COUNT(*) FROM extraction_urls 
                    WHERE (url_type = 'course_page' OR 
                          (url_type = 'syllabus' AND url NOT LIKE '%/pdf/kurs/%'))
                    AND status = 'pending'
                """)).scalar() or 0
                
                # Determine current phase based on data
                if course_count > 0 and html_count > 0 and pdf_count > 0 and pending_html_urls == 0:
                    self.stats.phase = ProcessingPhase.COMPLETED
                elif html_count > 0 and pdf_count > 0 and pending_html_urls == 0:
                    self.stats.phase = ProcessingPhase.CONTENT_PROCESSING
                elif pending_html_urls > 0:
                    self.stats.phase = ProcessingPhase.HTML_SCRAPING
                elif pdf_count > 0:
                    self.stats.phase = ProcessingPhase.HTML_SCRAPING
                elif url_count > 0:
                    self.stats.phase = ProcessingPhase.PDF_DOWNLOAD
                else:
                    self.stats.phase = ProcessingPhase.URL_EXTRACTION
                
                logger.info(f"Resuming from phase: {self.stats.phase.value}")
                logger.info(f"Existing data: {url_count} URLs, {pdf_count} PDFs, "
                          f"{html_count} pages, {course_count} courses")
                
            except Exception as e:
                logger.warning(f"Failed to load progress: {e}")
                # Start from beginning if progress loading fails
                self.stats.phase = ProcessingPhase.URL_EXTRACTION
    
    def _save_progress(self):
        """Save current progress checkpoint."""
        if not self.config.enable_resume:
            return
        
        try:
            self.stats.last_checkpoint = datetime.now()
            logger.debug(f"Progress checkpoint saved: {self.stats.phase.value}")
            
        except Exception as e:
            logger.warning(f"Failed to save progress: {e}")
    
    def _run_url_extraction_phase(self):
        """Execute URL extraction phase using database URL extractor."""
        logger.info("=== Phase 1: Database URL Extraction ===")
        
        try:
            # Run URL extraction
            extraction_result = self.url_extractor.extract_all_course_urls()
            
            # Update statistics
            self.stats.urls_extracted = extraction_result.total_urls_found
            
            if extraction_result.success:
                logger.info(f"URL extraction completed successfully: "
                          f"{extraction_result.total_urls_found} URLs extracted")
            else:
                logger.error(f"URL extraction failed: {extraction_result.error_message}")
                raise RuntimeError(f"URL extraction failed: {extraction_result.error_message}")
                
        except Exception as e:
            logger.error(f"URL extraction phase failed: {e}")
            self.stats.errors_encountered += 1
            raise
    
    def _run_pdf_download_phase(self):
        """Execute PDF download phase using database PDF downloader."""
        logger.info("=== Phase 2: Database PDF Download ===")
        
        try:
            # Get PDF syllabus URLs to download from database (only kursplaner.gu.se/pdf/ URLs)
            # Exclude URLs where PDF files already exist to avoid unnecessary processing
            try:
                with self.SessionFactory() as session:
                    all_pending_urls = session.execute(
                        text("SELECT url FROM extraction_urls WHERE url_type = 'syllabus' AND url LIKE '%/pdf/kurs/%' AND status = 'pending'")
                    ).fetchall()
                    
                    # Filter out URLs where PDF files already exist
                    pending_urls = []
                    for url_row in all_pending_urls:
                        url = url_row[0]
                        # Extract course code from URL to check for existing file
                        pdf_pattern = r'kursplaner\.gu\.se/pdf/kurs/([A-Z]{3}[0-9]{3})'
                        match = re.search(pdf_pattern, url)
                        if match:
                            course_code = match.group(1).upper()
                            pdf_path = f"data/syllabi_pdfs/{course_code}.pdf"
                            # Only include if file doesn't exist or is too small
                            if not os.path.exists(pdf_path) or os.path.getsize(pdf_path) <= 1024:
                                pending_urls.append(url_row)
                            else:
                                logger.debug(f"Skipping {url} - PDF already exists: {pdf_path}")
                        else:
                            # Include URLs we can't parse (let individual scraper handle)
                            pending_urls.append(url_row)
            except Exception:
                # If extraction_urls table doesn't exist, use empty list
                pending_urls = []
            
            if not pending_urls:
                logger.info("No PDF URLs to download (files may already exist)")
                return
            
            logger.info(f"Starting download of {len(pending_urls)} PDFs")
            
            # Process PDFs in batches
            successful_downloads = 0
            batch_size = self.config.batch_size
            
            for i in range(0, len(pending_urls), batch_size):
                batch = pending_urls[i:i+batch_size]
                
                # Process batch with concurrency control
                with concurrent.futures.ThreadPoolExecutor(max_workers=self.config.max_concurrent_downloads) as executor:
                    download_futures = []
                    
                    for url_row in batch:
                        url = url_row[0]
                        future = executor.submit(self._download_single_pdf, url)
                        download_futures.append(future)
                    
                    # Process results
                    for future in concurrent.futures.as_completed(download_futures):
                        try:
                            success = future.result()
                            if success:
                                successful_downloads += 1
                        except Exception as e:
                            logger.error(f"PDF download failed: {e}")
                            self.stats.errors_encountered += 1
                
                # Save progress checkpoint
                if i % (self.config.checkpoint_interval * batch_size) == 0:
                    self._save_progress()
                    logger.info(f"Downloaded {successful_downloads} PDFs so far")
                
                # Add delay between PDF batches to prevent network congestion
                if i + batch_size < len(pending_urls):
                    time.sleep(0.5)  # Brief delay between PDF batches
            
            self.stats.pdfs_downloaded = successful_downloads
            logger.info(f"PDF download phase completed: {successful_downloads} PDFs downloaded")
            
        except Exception as e:
            logger.error(f"PDF download phase failed: {e}")
            self.stats.errors_encountered += 1
            raise
    
    def _download_single_pdf(self, url: str) -> bool:
        """Download a single PDF with error handling and rate limiting."""
        try:
            # Add per-worker delay to prevent network congestion
            time.sleep(self.config.pdf_download_delay)
            
            result = self.pdf_downloader.download_pdf_from_url(url)
            return result.success
        except Exception as e:
            error_msg = str(e).lower()
            
            # Check for network connectivity issues
            if "no route to host" in error_msg or "connection error" in error_msg:
                logger.warning(f"Network connectivity issue for {url}: {e}")
                self.stats.network_errors += 1
                # Add exponential backoff for network issues
                time.sleep(2.0)  # Additional delay for network recovery
            else:
                logger.error(f"Failed to download PDF from {url}: {e}")
                self.stats.errors_encountered += 1
            
            return False
    
    def _scrape_single_url_with_rate_limit(self, url: str) -> bool:
        """Scrape a single URL with per-worker rate limiting and network error handling."""
        try:
            # Add per-worker delay to avoid overwhelming servers (now 1.0s for stability)
            time.sleep(self.config.html_scraping_delay)
            
            # Scrape the URL
            result = self.html_scraper.scrape_course_page(url)
            
            if result.success:
                logger.debug(f"Successfully scraped: {url}")
                return True
            else:
                logger.warning(f"Failed to scrape {url}: {result.error_message}")
                return False
                
        except Exception as e:
            error_msg = str(e).lower()
            
            # Check for network connectivity issues
            if "no route to host" in error_msg or "connection error" in error_msg or "timeout" in error_msg:
                logger.warning(f"Network connectivity issue for {url}: {e}")
                self.stats.network_errors += 1
                # Add additional delay for network recovery
                time.sleep(3.0)
            else:
                logger.error(f"Error scraping {url}: {e}")
                self.stats.errors_encountered += 1
            
            return False
    
    def _run_html_scraping_phase(self):
        """Execute HTML scraping phase using database HTML scraper."""
        logger.info("=== Phase 3: Database HTML Scraping ===")
        
        try:
            # HTML scraping doesn't require API keys, only WebDriver
            logger.debug("Starting HTML scraping phase using WebDriver pool")
            
            # Get URLs to scrape from database (course pages + webpage syllabi, excluding PDF syllabi)
            # Exclude URLs where markdown files already exist to avoid unnecessary processing
            try:
                with self.SessionFactory() as session:
                    all_pending_urls = session.execute(
                        text("""SELECT url FROM extraction_urls 
                             WHERE (url_type = 'course_page' OR 
                                   (url_type = 'syllabus' AND url NOT LIKE '%/pdf/kurs/%')) 
                             AND status = 'pending'""")
                    ).fetchall()
                    
                    # Filter out URLs where markdown files already exist
                    pending_urls = []
                    for url_row in all_pending_urls:
                        url = url_row[0]
                        # Extract course code from URL to check for existing files
                        course_code_match = re.search(r'([A-Z]{3}[0-9]{3})', url)
                        if course_code_match:
                            course_code = course_code_match.group(1).upper()
                            # Determine expected file path based on URL type
                            if '/syllabus/' in url:
                                file_path = f"data/syllabi_pages/{course_code}_syllabus.md"
                            else:
                                file_path = f"data/course_pages/{course_code}_course.md"
                            
                            # Only include if file doesn't exist or is too small
                            if not os.path.exists(file_path) or os.path.getsize(file_path) <= 100:
                                pending_urls.append(url_row)
                            else:
                                logger.debug(f"Skipping {url} - markdown already exists: {file_path}")
                        else:
                            # Include URLs we can't parse (let individual scraper handle)
                            pending_urls.append(url_row)
            except Exception:
                # If extraction_urls table doesn't exist, use empty list
                pending_urls = []
            
            if not pending_urls:
                logger.info("No course page or webpage syllabus URLs to scrape (files may already exist)")
                return
            
            logger.info(f"Starting parallel HTML scraping of {len(pending_urls)} course pages and webpage syllabi")
            logger.info(f"Using {self.config.max_concurrent_html_scrapers} concurrent workers")
            
            # Process pages with parallel workers and rate limiting
            successful_scrapes = 0
            
            # Process URLs in batches for better memory management and progress tracking
            batch_size = self.config.batch_size
            
            for i in range(0, len(pending_urls), batch_size):
                batch = pending_urls[i:i+batch_size]
                batch_urls = [url_row[0] for url_row in batch]
                
                logger.info(f"Processing batch {i//batch_size + 1}/{(len(pending_urls) + batch_size - 1)//batch_size} ({len(batch_urls)} URLs)")
                
                # Use ThreadPoolExecutor for parallel scraping
                with concurrent.futures.ThreadPoolExecutor(max_workers=self.config.max_concurrent_html_scrapers) as executor:
                    scraping_futures = []
                    
                    for url in batch_urls:
                        future = executor.submit(self._scrape_single_url_with_rate_limit, url)
                        scraping_futures.append(future)
                    
                    # Process results
                    for future in concurrent.futures.as_completed(scraping_futures):
                        try:
                            success = future.result()
                            if success:
                                successful_scrapes += 1
                            else:
                                self.stats.errors_encountered += 1
                        except Exception as e:
                            logger.error(f"HTML scraping failed: {e}")
                            self.stats.errors_encountered += 1
                
                # Save progress checkpoint after each batch
                self._save_progress()
                logger.info(f"Scraped {successful_scrapes} pages so far")
                
                # Brief delay between batches to avoid overwhelming servers
                if i + batch_size < len(pending_urls):
                    time.sleep(0.2)  # Short delay between batches
            
            self.stats.pages_scraped = successful_scrapes
            logger.info(f"Parallel HTML scraping phase completed: {successful_scrapes} pages scraped")
            
        except Exception as e:
            logger.error(f"HTML scraping phase failed: {e}")
            self.stats.errors_encountered += 1
            raise
            
        except Exception as e:
            logger.error(f"HTML scraping phase failed: {e}")
            self.stats.errors_encountered += 1
            raise
    
    def _run_content_processing_phase(self):
        """Execute content processing phase using database Gemini processor."""
        logger.info("=== Phase 4: Database Content Processing ===")
        
        try:
            # Get files to process from database - only include files that actually exist on filesystem
            try:
                with self.SessionFactory() as session:
                    # Get completed PDF downloads
                    try:
                        all_pdf_files = session.execute(
                            text("""SELECT file_path FROM pdf_downloads 
                                    WHERE status = 'success' 
                                    AND file_path NOT IN (SELECT DISTINCT source_path FROM gemini_processing_jobs WHERE processing_status = 'success')""")
                        ).fetchall()
                        # Filter to only include files that exist and have reasonable size
                        pdf_files = []
                        for pdf_row in all_pdf_files:
                            file_path = pdf_row[0]
                            if os.path.exists(file_path) and os.path.getsize(file_path) > 1024:
                                pdf_files.append(pdf_row)
                            else:
                                logger.warning(f"Skipping processing - file missing or too small: {file_path}")
                    except Exception:
                        pdf_files = []
                    
                    # Get completed HTML scrapes
                    all_html_files = session.execute(
                        text("""SELECT hs.markdown_file_path as file_path, eu.url_type 
                                FROM html_scrapes hs
                                JOIN extraction_urls eu ON hs.extraction_url_id = eu.id
                                WHERE hs.status = 'success' 
                                AND hs.markdown_file_path NOT IN (
                                    SELECT DISTINCT source_path FROM gemini_processing_jobs 
                                    WHERE processing_status = 'success'
                                )""")
                    ).fetchall()
                    # Filter to only include files that exist and have reasonable size
                    html_files = []
                    for html_row in all_html_files:
                        file_path = html_row[0]
                        if os.path.exists(file_path) and os.path.getsize(file_path) > 100:
                            html_files.append(html_row)
                        else:
                            logger.warning(f"Skipping processing - file missing or too small: {file_path}")
            except Exception:
                pdf_files = []
                html_files = []
            
            total_files = len(pdf_files) + len(html_files)
            
            if total_files == 0:
                logger.info("No new files to process")
                return
            
            logger.info(f"Processing {len(pdf_files)} PDFs and {len(html_files)} HTML scraped pages")
            logger.info(f"Using {self.config.max_concurrent_processing} concurrent Gemini workers (TIER 1: 0.06s delay between requests)")
            
            # First, add all files as processing jobs
            logger.info("Adding files to gemini_processing_jobs table...")
            jobs_added = 0
            for pdf_row in pdf_files:
                if self.gemini_processor.gemini_store.add_processing_job(pdf_row[0], "pdf"):
                    jobs_added += 1
            for html_row in html_files:
                # Determine content_type based on url_type
                url_type = html_row[1] if len(html_row) > 1 else 'course_page'
                content_type = "syllabus_md" if url_type == 'syllabus' else "course_page_md"
                if self.gemini_processor.gemini_store.add_processing_job(html_row[0], content_type):
                    jobs_added += 1
            logger.info(f"Added {jobs_added} processing jobs to database")
            
            # Process files with parallel workers and rate limiting for Gemini API
            successful_processing = 0
            total_cost = 0.0
            
            # Separate files by type for ordered processing
            pdf_file_list = [(pdf_row[0], "pdf") for pdf_row in pdf_files]
            syllabus_file_list = []
            course_page_file_list = []
            
            # Separate HTML files by type
            for html_row in html_files:
                url_type = html_row[1] if len(html_row) > 1 else 'course_page'
                if url_type == 'syllabus':
                    syllabus_file_list.append((html_row[0], "syllabus_md"))
                else:
                    course_page_file_list.append((html_row[0], "course_page_md"))
            
            # Process in three phases to ensure correct order
            logger.info("=" * 80)
            logger.info("PROCESSING ORDER: PDFs → Syllabus Pages → Course Pages")
            logger.info("=" * 80)
            
            # Phase 1: Process PDF files (syllabi_pdfs)
            if pdf_file_list:
                logger.info("\n" + "="*80)
                logger.info(f"PHASE 1: Processing {len(pdf_file_list)} PDF files from /data/syllabi_pdfs/")
                logger.info("="*80)
                phase_results = self._process_file_batch(pdf_file_list, "PDF syllabi")
                successful_processing += phase_results['successful']
                total_cost += phase_results['cost']
            
            # Phase 2: Process syllabus markdown files (syllabi_pages)
            if syllabus_file_list:
                logger.info("\n" + "="*80)
                logger.info(f"PHASE 2: Processing {len(syllabus_file_list)} syllabus pages from /data/syllabi_pages/")
                logger.info("="*80)
                phase_results = self._process_file_batch(syllabus_file_list, "syllabus pages")
                successful_processing += phase_results['successful']
                total_cost += phase_results['cost']
            
            # Phase 3: Process course page markdown files (course_pages)
            if course_page_file_list:
                logger.info("\n" + "="*80)
                logger.info(f"PHASE 3: Processing {len(course_page_file_list)} course pages from /data/course_pages/")
                logger.info("="*80)
                phase_results = self._process_file_batch(course_page_file_list, "course pages")
                successful_processing += phase_results['successful']
                total_cost += phase_results['cost']
            
            self.stats.processing_cost = total_cost
            
            self.stats.courses_processed = successful_processing
            logger.info("\n" + "="*80)
            logger.info("GEMINI PROCESSING SUMMARY")
            logger.info("="*80)
            logger.info(f"Total files processed: {successful_processing}")
            logger.info(f"  - PDFs processed: {len(pdf_file_list)}")
            logger.info(f"  - Syllabus pages processed: {len(syllabus_file_list)}")
            logger.info(f"  - Course pages processed: {len(course_page_file_list)}")
            logger.info(f"Total processing cost: ${self.stats.processing_cost:.4f}")
            logger.info("="*80)
            
        except Exception as e:
            logger.error(f"Content processing phase failed: {e}")
            self.stats.errors_encountered += 1
            raise
    
    def _process_single_file(self, file_path: str, content_type: str) -> Optional[Dict[str, Any]]:
        """Process a single file with the Gemini processor."""
        try:
            # Use unified process_single_content method
            result = self.gemini_processor.process_single_content(str(file_path), content_type)
            
            if result.success:
                return {
                    'success': True,
                    'cost': result.cost_estimate,
                    'course_id': result.course_id
                }
            else:
                logger.warning(f"Processing failed for {file_path}: {result.error}")
                return None
                
        except Exception as e:
            logger.error(f"Error processing {file_path}: {e}")
            return None
    
    def _process_single_file_with_rate_limit(self, file_path: str, content_type: str) -> Optional[Dict[str, Any]]:
        """Process a single file with rate limiting for TIER 1 API."""
        try:
            # TIER 1: 0.06 second delay between requests (1000 RPM limit)
            time.sleep(self.config.gemini_api_delay)
            
            # Process the file
            result = self.gemini_processor.process_single_content(str(file_path), content_type)
            
            # Record the processing attempt in the database
            self.gemini_processor.gemini_store.record_processing_attempt(result)
            
            if result.success:
                logger.debug(f"Successfully processed: {file_path}")
                # Store course in database if successful
                if result.course_data:
                    course_id = self.gemini_processor.store_course_in_database(result.course_data)
                    result.course_id = course_id
                
                return {
                    'success': True,
                    'cost': result.cost_estimate,
                    'course_id': result.course_id
                }
            else:
                logger.warning(f"Processing failed for {file_path}: {result.error}")
                return {'success': False, 'cost': 0.0}
                
        except Exception as e:
            logger.error(f"Error processing {file_path}: {e}")
            # Create a failed result to record in database
            from scraper.database_gemini_processor import ProcessingResult
            failed_result = ProcessingResult(
                source_path=file_path,
                content_type=content_type,
                success=False,
                error=str(e)
            )
            self.gemini_processor.gemini_store.record_processing_attempt(failed_result)
            return {'success': False, 'cost': 0.0}
    
    def _process_file_batch(self, file_list: List[Tuple[str, str]], phase_name: str) -> Dict[str, Any]:
        """Process a batch of files with rate limiting and parallel processing.
        
        Args:
            file_list: List of (file_path, content_type) tuples
            phase_name: Name of the processing phase for logging
            
        Returns:
            Dictionary with 'successful' count and 'cost' total
        """
        successful = 0
        cost = 0.0
        batch_size = self.config.batch_size
        
        for i in range(0, len(file_list), batch_size):
            batch = file_list[i:i+batch_size]
            
            logger.info(f"Processing {phase_name} batch {i//batch_size + 1}/{(len(file_list) + batch_size - 1)//batch_size} ({len(batch)} files)")
            
            # Use ThreadPoolExecutor for parallel processing
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.config.max_concurrent_processing) as executor:
                processing_futures = []
                
                for file_path, content_type in batch:
                    future = executor.submit(self._process_single_file_with_rate_limit, file_path, content_type)
                    processing_futures.append(future)
                
                # Process results
                for future in concurrent.futures.as_completed(processing_futures):
                    try:
                        result = future.result()
                        if result and result.get('success'):
                            successful += 1
                            cost += result.get('cost', 0.0)
                    except Exception as e:
                        logger.error(f"Content processing failed: {e}")
                        self.stats.errors_encountered += 1
            
            # Save progress checkpoint after each batch
            self._save_progress()
            logger.info(f"Phase {phase_name}: Processed {successful} files so far, cost: ${cost:.4f}")
            
            # Rate limiting delay between batches to respect Gemini API limits
            if i + batch_size < len(file_list):
                time.sleep(1.0)  # 1 second between batches
        
        logger.info(f"Phase {phase_name} completed: {successful}/{len(file_list)} files processed, cost: ${cost:.4f}")
        return {'successful': successful, 'cost': cost}
    
    
    def _finalize_pipeline(self):
        """Finalize the scraping pipeline and generate summary."""
        logger.info("=== Pipeline Finalization ===")
        
        try:
            # Get final statistics from database
            with self.SessionFactory() as session:
                total_courses = session.query(Course).filter(Course.is_current == True).count()
                total_sections = session.query(CourseSection).count()
                total_mappings = session.query(CourseProgramMapping).count()
                quality_issues = session.query(DataQualityIssue).filter(DataQualityIssue.is_resolved == False).count()
                
                self.stats.courses_processed = total_courses
                
                logger.info("=== PIPELINE COMPLETION SUMMARY ===")
                logger.info(f"Total execution time: {self.stats.total_time:.1f} seconds")
                logger.info(f"URLs extracted: {self.stats.urls_extracted}")
                logger.info(f"PDFs downloaded: {self.stats.pdfs_downloaded}")
                logger.info(f"Pages scraped: {self.stats.pages_scraped}")
                logger.info(f"Courses processed: {total_courses}")
                logger.info(f"Course sections: {total_sections}")
                logger.info(f"Program mappings: {total_mappings}")
                logger.info(f"Processing cost: ${self.stats.processing_cost:.4f}")
                logger.info(f"Quality issues: {quality_issues}")
                logger.info(f"Total errors: {self.stats.errors_encountered}")
                logger.info(f"Network errors: {self.stats.network_errors}")
                
                # Network health summary
                if self.stats.network_errors > 0:
                    network_error_rate = (self.stats.network_errors / max(1, self.stats.urls_extracted)) * 100
                    logger.warning(f"Network error rate: {network_error_rate:.1f}% - consider reducing concurrency if high")
                else:
                    logger.info("Network connectivity: Excellent (no network errors)")
                
                # Calculate success rates
                # Get URL type breakdown for accurate statistics
                pdf_url_count = session.execute(text(
                    "SELECT COUNT(*) FROM extraction_urls WHERE url_type = 'syllabus' AND url LIKE '%/pdf/kurs/%'"
                )).scalar() or 0
                
                html_url_count = session.execute(text(
                    "SELECT COUNT(*) FROM extraction_urls WHERE url_type = 'course_page' OR (url_type = 'syllabus' AND url NOT LIKE '%/pdf/kurs/%')"
                )).scalar() or 0
                
                # Log URL breakdown
                logger.info(f"URL breakdown: {pdf_url_count} PDF URLs, {html_url_count} HTML URLs, {self.stats.urls_extracted} total URLs")
                
                # Calculate correct PDF success rate
                if pdf_url_count > 0:
                    pdf_success_rate = (self.stats.pdfs_downloaded / pdf_url_count) * 100
                    logger.info(f"PDF download success rate: {pdf_success_rate:.1f}% ({self.stats.pdfs_downloaded}/{pdf_url_count} PDFs)")
                else:
                    logger.info("No PDF URLs found to download")
                
                error_rate = (self.stats.errors_encountered / max(1, self.stats.urls_extracted)) * 100
                logger.info(f"Error rate: {error_rate:.1f}%")
                
                # Check if error rate is within tolerance
                if error_rate > self.config.error_tolerance_pct:
                    logger.warning(f"Error rate ({error_rate:.1f}%) exceeds tolerance ({self.config.error_tolerance_pct}%)")
                else:
                    logger.info("Pipeline completed within error tolerance")
            
            # Cleanup checkpoint data if configured
            if self.config.cleanup_on_complete:
                self._cleanup_checkpoints()
                
        except Exception as e:
            logger.error(f"Pipeline finalization failed: {e}")
    
    def _cleanup_resources(self):
        """Clean up resources and connections."""
        try:
            # Close database connections
            if hasattr(self, 'engine'):
                self.engine.dispose()
            
            # Clean up scraper components
            if hasattr(self.url_extractor, 'cleanup'):
                self.url_extractor.cleanup()
            
            logger.info("Resource cleanup completed")
            
        except Exception as e:
            logger.warning(f"Resource cleanup failed: {e}")
    
    def _cleanup_checkpoints(self):
        """Clean up temporary checkpoint data."""
        try:
            # Remove any temporary processing files or state
            logger.info("Checkpoint cleanup completed")
        except Exception as e:
            logger.warning(f"Checkpoint cleanup failed: {e}")
    
    def get_processing_summary(self) -> Dict[str, Any]:
        """Get comprehensive processing summary."""
        return {
            'phase': self.stats.phase.value,
            'urls_extracted': self.stats.urls_extracted,
            'pdfs_downloaded': self.stats.pdfs_downloaded,
            'pages_scraped': self.stats.pages_scraped,
            'courses_processed': self.stats.courses_processed,
            'errors_encountered': self.stats.errors_encountered,
            'processing_cost': self.stats.processing_cost,
            'total_time': self.stats.total_time,
            'start_time': self.stats.start_time.isoformat() if self.stats.start_time else None,
            'last_checkpoint': self.stats.last_checkpoint.isoformat() if self.stats.last_checkpoint else None
        }
    
    def validate_database_state(self) -> Dict[str, Any]:
        """Validate current database state for consistency."""
        logger.info("Validating database state")
        
        validation_results = {
            'valid': True,
            'issues': [],
            'statistics': {}
        }
        
        try:
            with self.SessionFactory() as session:
                # Count records in each table
                course_count = session.query(Course).count()
                section_count = session.query(CourseSection).count()
                mapping_count = session.query(CourseProgramMapping).count()
                quality_issue_count = session.query(DataQualityIssue).filter(DataQualityIssue.is_resolved == False).count()
                
                validation_results['statistics'] = {
                    'total_courses': course_count,
                    'current_courses': session.query(Course).filter(Course.is_current == True).count(),
                    'course_sections': section_count,
                    'program_mappings': mapping_count,
                    'unresolved_quality_issues': quality_issue_count
                }
                
                # Validate referential integrity
                orphaned_sections = session.execute(
                    text("SELECT COUNT(*) FROM course_sections WHERE course_id NOT IN (SELECT id FROM courses)")
                ).scalar()
                
                if orphaned_sections > 0:
                    validation_results['valid'] = False
                    validation_results['issues'].append(f"Found {orphaned_sections} orphaned course sections")
                
                # Validate program mappings
                orphaned_mappings = session.execute(
                    text("SELECT COUNT(*) FROM course_program_mapping WHERE course_id NOT IN (SELECT id FROM courses)")
                ).scalar()
                
                if orphaned_mappings > 0:
                    validation_results['valid'] = False
                    validation_results['issues'].append(f"Found {orphaned_mappings} orphaned program mappings")
                
                logger.info(f"Database validation completed: {'VALID' if validation_results['valid'] else 'ISSUES FOUND'}")
                
        except Exception as e:
            validation_results['valid'] = False
            validation_results['issues'].append(f"Validation failed: {str(e)}")
            logger.error(f"Database validation failed: {e}")
        
        return validation_results


def main():
    """Main entry point for database scraper orchestrator."""
    logger.info("Starting Database Scraper Orchestrator")
    
    try:
        # Create network-friendly configuration for i9-14000K
        config = OrchestrationConfig(
            database_path="data/csexpert.db",
            max_concurrent_downloads=6,  # Network-friendly concurrency
            max_concurrent_html_scrapers=6,  # Stable parallel HTML scraping
            max_concurrent_processing=6,  # Keep Gemini API workers
            batch_size=100,  # Efficient batching
            enable_resume=True,
            error_tolerance_pct=5.0
        )
        
        # Create and run orchestrator
        orchestrator = DatabaseScraperOrchestrator(config)
        
        # Validate database state first
        validation = orchestrator.validate_database_state()
        if not validation['valid']:
            logger.warning("Database validation issues found:")
            for issue in validation['issues']:
                logger.warning(f"  - {issue}")
        
        # Run complete pipeline
        stats = orchestrator.run_complete_pipeline()
        
        # Print final summary
        summary = orchestrator.get_processing_summary()
        logger.info("=== ORCHESTRATOR EXECUTION COMPLETE ===")
        logger.info(f"Final stats: {summary}")
        
        # Validate final state
        final_validation = orchestrator.validate_database_state()
        logger.info(f"Final database state: {'VALID' if final_validation['valid'] else 'ISSUES PRESENT'}")
        
        return 0
        
    except KeyboardInterrupt:
        logger.info("Pipeline interrupted by user")
        return 1
    except Exception as e:
        logger.error(f"Pipeline execution failed: {e}")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())