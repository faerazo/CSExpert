#!/usr/bin/env python3
"""
Database-Connected PDF Downloader

Enhanced PDF downloader that integrates with the CSExpert database.
Downloads PDFs based on URLs stored in the database and tracks download status.
"""

import logging
import os
import re
import time
import hashlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional, Dict, Tuple
from datetime import datetime

import requests
from tqdm import tqdm

# Import database components
from database.connection_manager import get_database_manager, DatabaseManager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ----- Configuration Constants -----

# PDF URL pattern to match
PDF_URL_PATTERN = r'kursplaner\.gu\.se/pdf/kurs/en/([A-Za-z0-9]+)'

# Default settings
DEFAULT_OUTPUT_DIR = 'data/syllabi_pdfs'
DEFAULT_MAX_WORKERS = 5
DEFAULT_DELAY = 0.5
DEFAULT_TIMEOUT = 30
DEFAULT_CHUNK_SIZE = 8192

# ----- Data Structures -----

class PDFDownloadResult:
    """Container for PDF download results"""
    
    def __init__(self, url_id: int, url: str, course_code: str, 
                 success: bool = False, file_path: Optional[str] = None,
                 error: Optional[str] = None, file_size: int = 0,
                 checksum: Optional[str] = None, download_time: float = 0.0):
        self.url_id = url_id
        self.url = url
        self.course_code = course_code
        self.success = success
        self.file_path = file_path
        self.error = error
        self.file_size = file_size
        self.checksum = checksum
        self.download_time = download_time
        self.downloaded_at = datetime.utcnow()


# ----- Database Operations -----

class DatabasePDFStore:
    """Handles database operations for PDF download tracking"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.setup_tables()
    
    def setup_tables(self):
        """Ensure PDF download tracking tables exist"""
        try:
            with self.db_manager.transaction() as conn:
                # Create pdf_downloads table for tracking download status
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS pdf_downloads (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        extraction_url_id INTEGER NOT NULL,
                        course_code VARCHAR(10) NOT NULL,
                        original_url TEXT NOT NULL,
                        file_path TEXT,
                        file_size INTEGER DEFAULT 0,
                        checksum VARCHAR(64),
                        status VARCHAR(20) CHECK (status IN ('pending', 'success', 'failed', 'skipped')) DEFAULT 'pending',
                        error_message TEXT,
                        download_time REAL DEFAULT 0.0,
                        downloaded_at TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        
                        FOREIGN KEY (extraction_url_id) REFERENCES extraction_urls(id),
                        UNIQUE(extraction_url_id)
                    )
                """)
                
                # Create indexes for performance
                conn.execute("CREATE INDEX IF NOT EXISTS idx_pdf_downloads_course_code ON pdf_downloads(course_code)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_pdf_downloads_status ON pdf_downloads(status)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_pdf_downloads_downloaded_at ON pdf_downloads(downloaded_at)")
                
                logger.info("PDF download tracking tables initialized")
                
        except Exception as e:
            logger.error(f"Failed to setup PDF download tables: {e}")
            raise
    
    def get_pending_pdf_urls(self) -> List[Dict]:
        """Get syllabus URLs that need PDF downloads"""
        try:
            query = """
                SELECT eu.id, eu.url, eu.course_code 
                FROM extraction_urls eu
                LEFT JOIN pdf_downloads pd ON eu.id = pd.extraction_url_id
                WHERE eu.url_type = 'syllabus' 
                  AND eu.url LIKE '%kursplaner.gu.se/pdf%'
                  AND (pd.status IS NULL OR pd.status = 'failed')
                ORDER BY eu.extracted_at DESC
            """
            
            results = self.db_manager.execute_query(query)
            return [dict(row) for row in results]
            
        except Exception as e:
            logger.error(f"Failed to get pending PDF URLs: {e}")
            return []
    
    def record_download_attempt(self, result: PDFDownloadResult) -> bool:
        """Record a PDF download attempt in database"""
        try:
            query = """
                INSERT OR REPLACE INTO pdf_downloads 
                (extraction_url_id, course_code, original_url, file_path, file_size, 
                 checksum, status, error_message, download_time, downloaded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            
            status = 'success' if result.success else 'failed'
            
            self.db_manager.execute_update(query, (
                result.url_id,
                result.course_code,
                result.url,
                result.file_path,
                result.file_size,
                result.checksum,
                status,
                result.error,
                result.download_time,
                result.downloaded_at
            ))
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to record download for {result.course_code}: {e}")
            return False
    
    def get_download_statistics(self) -> Dict:
        """Get statistics about PDF downloads"""
        try:
            with self.db_manager.get_connection() as conn:
                stats = {}
                
                # Download status counts
                cursor = conn.execute("""
                    SELECT status, COUNT(*) as count 
                    FROM pdf_downloads 
                    GROUP BY status
                """)
                stats['by_status'] = {row['status']: row['count'] for row in cursor.fetchall()}
                
                # Total file size
                cursor = conn.execute("""
                    SELECT SUM(file_size) as total_size, COUNT(*) as successful_count
                    FROM pdf_downloads 
                    WHERE status = 'success'
                """)
                result = cursor.fetchone()
                stats['total_size_bytes'] = result['total_size'] or 0
                stats['successful_downloads'] = result['successful_count'] or 0
                
                # Average download time
                cursor = conn.execute("""
                    SELECT AVG(download_time) as avg_time 
                    FROM pdf_downloads 
                    WHERE status = 'success'
                """)
                avg_time = cursor.fetchone()['avg_time']
                stats['average_download_time'] = avg_time or 0.0
                
                # Latest download
                cursor = conn.execute("""
                    SELECT MAX(downloaded_at) as latest_download 
                    FROM pdf_downloads
                """)
                latest = cursor.fetchone()['latest_download']
                stats['latest_download'] = latest
                
                return stats
                
        except Exception as e:
            logger.error(f"Failed to get download statistics: {e}")
            return {}
    
    def get_existing_downloads(self, course_codes: List[str] = None) -> Dict[str, Dict]:
        """Get existing successful downloads, optionally filtered by course codes"""
        try:
            base_query = """
                SELECT course_code, file_path, file_size, checksum, downloaded_at
                FROM pdf_downloads 
                WHERE status = 'success'
            """
            
            params = []
            if course_codes:
                placeholders = ','.join(['?'] * len(course_codes))
                base_query += f" AND course_code IN ({placeholders})"
                params.extend(course_codes)
            
            results = self.db_manager.execute_query(base_query, tuple(params))
            
            return {
                row['course_code']: {
                    'file_path': row['file_path'],
                    'file_size': row['file_size'],
                    'checksum': row['checksum'],
                    'downloaded_at': row['downloaded_at']
                } for row in results
            }
            
        except Exception as e:
            logger.error(f"Failed to get existing downloads: {e}")
            return {}


# ----- PDF Download Functions -----

def calculate_file_checksum(file_path: str) -> str:
    """Calculate SHA-256 checksum of a file"""
    try:
        hasher = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception as e:
        logger.error(f"Failed to calculate checksum for {file_path}: {e}")
        return ""


def download_single_pdf(url_info: Dict, output_dir: str, delay: float, 
                       timeout: int = DEFAULT_TIMEOUT) -> PDFDownloadResult:
    """
    Download a single PDF from a URL.
    
    Args:
        url_info: Dictionary with url_id, url, course_code
        output_dir: Directory to save the PDF
        delay: Delay in seconds before downloading
        timeout: Request timeout in seconds
        
    Returns:
        PDFDownloadResult: Result of the download attempt
    """
    url_id = url_info['id']
    url = url_info['url']
    course_code = url_info['course_code']
    
    output_path = os.path.join(output_dir, f"{course_code}.pdf")
    start_time = time.time()
    
    # Add delay to avoid overwhelming the server
    time.sleep(delay)
    
    result = PDFDownloadResult(
        url_id=url_id,
        url=url,
        course_code=course_code
    )
    
    try:
        # Check if file already exists
        if os.path.exists(output_path):
            existing_size = os.path.getsize(output_path)
            if existing_size > 1024:  # File exists and is reasonably sized
                result.success = True
                result.file_path = output_path
                result.file_size = existing_size
                result.checksum = calculate_file_checksum(output_path)
                result.download_time = 0.0  # Already existed
                logger.debug(f"File already exists: {course_code}.pdf ({existing_size} bytes)")
                return result
        
        # Download the PDF
        logger.debug(f"Downloading {course_code}: {url}")
        response = requests.get(url, stream=True, timeout=timeout)
        response.raise_for_status()
        
        # Verify content type
        content_type = response.headers.get('Content-Type', '').lower()
        if 'application/pdf' not in content_type and 'pdf' not in content_type:
            logger.warning(f"Unexpected content type for {course_code}: {content_type}")
        
        # Save the PDF
        os.makedirs(output_dir, exist_ok=True)
        
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=DEFAULT_CHUNK_SIZE):
                if chunk:  # Filter out keep-alive chunks
                    f.write(chunk)
        
        # Verify download and calculate stats
        if os.path.exists(output_path):
            file_size = os.path.getsize(output_path)
            if file_size > 0:
                result.success = True
                result.file_path = output_path
                result.file_size = file_size
                result.checksum = calculate_file_checksum(output_path)
                result.download_time = time.time() - start_time
                logger.debug(f"Successfully downloaded {course_code}: {file_size} bytes")
            else:
                result.error = "Downloaded file is empty"
                os.remove(output_path)  # Remove empty file
        else:
            result.error = "File was not created"
    
    except requests.exceptions.RequestException as e:
        result.error = f"Request error: {str(e)}"
        logger.error(f"Download failed for {course_code}: {result.error}")
    
    except Exception as e:
        result.error = f"Unexpected error: {str(e)}"
        logger.error(f"Unexpected error downloading {course_code}: {result.error}")
    
    result.download_time = time.time() - start_time
    return result


# ----- Main PDF Downloader Class -----

class DatabasePDFDownloader:
    """Main PDF downloader with database integration"""
    
    def __init__(self, database_path: str = "data/csexpert.db", 
                 output_dir: str = DEFAULT_OUTPUT_DIR,
                 max_workers: int = DEFAULT_MAX_WORKERS,
                 delay: float = DEFAULT_DELAY):
        
        self.db_manager = get_database_manager(database_path)
        self.pdf_store = DatabasePDFStore(self.db_manager)
        self.output_dir = Path(output_dir)
        self.max_workers = max_workers
        self.delay = delay
        
        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Database PDF Downloader initialized: {output_dir} (workers: {max_workers})")
    
    def download_pdf_from_url(self, url: str):
        """Interface method for orchestrator - download a single PDF URL."""
        # Extract course code from URL
        match = re.search(PDF_URL_PATTERN, url)
        if not match:
            return type('Result', (), {
                'success': False, 
                'error_message': f'Could not extract course code from URL: {url}'
            })()
        
        course_code = match.group(1).upper()
        
        # Create URL info dict
        url_info = {'id': 0, 'url': url, 'course_code': course_code}
        
        # Download the PDF
        result = download_single_pdf(url_info, str(self.output_dir), self.delay)
        
        # Record in database if we can find the extraction URL ID
        try:
            with self.db_manager.get_connection() as conn:
                cursor = conn.execute("SELECT id FROM extraction_urls WHERE url = ?", (url,))
                row = cursor.fetchone()
                if row:
                    result.url_id = row['id']
                    self.pdf_store.record_download_attempt(result)
        except Exception as e:
            logger.warning(f"Could not record download attempt: {e}")
        
        return type('Result', (), {
            'success': result.success, 
            'error_message': result.error if not result.success else None
        })()
    
    def download_all_pdfs(self, force_redownload: bool = False) -> Dict:
        """Download all pending PDFs from database"""
        
        # Get pending PDF URLs
        pending_urls = self.pdf_store.get_pending_pdf_urls()
        
        if not pending_urls:
            logger.info("No pending PDF downloads found")
            return {'total': 0, 'successful': 0, 'failed': 0}
        
        logger.info(f"Found {len(pending_urls)} PDF URLs to download")
        
        # Check for existing downloads if not forcing redownload
        if not force_redownload:
            course_codes = [url['course_code'] for url in pending_urls]
            existing = self.pdf_store.get_existing_downloads(course_codes)
            
            # Filter out already downloaded PDFs
            pending_urls = [
                url for url in pending_urls 
                if url['course_code'] not in existing or 
                   not os.path.exists(existing.get(url['course_code'], {}).get('file_path', ''))
            ]
            
            if existing:
                logger.info(f"Skipping {len(existing)} already downloaded PDFs")
        
        if not pending_urls:
            logger.info("All PDFs already downloaded")
            return {'total': len(existing), 'successful': len(existing), 'failed': 0}
        
        logger.info(f"Downloading {len(pending_urls)} PDFs...")
        
        # Download PDFs in parallel
        successful_downloads = 0
        failed_downloads = 0
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit download tasks
            future_to_url = {
                executor.submit(
                    download_single_pdf, 
                    url_info, 
                    str(self.output_dir), 
                    self.delay
                ): url_info
                for url_info in pending_urls
            }
            
            # Process results with progress bar
            with tqdm(total=len(pending_urls), desc="Downloading PDFs") as pbar:
                for future in as_completed(future_to_url):
                    url_info = future_to_url[future]
                    
                    try:
                        result = future.result()
                        
                        # Record result in database
                        self.pdf_store.record_download_attempt(result)
                        
                        if result.success:
                            successful_downloads += 1
                            pbar.set_postfix(success=successful_downloads, failed=failed_downloads)
                        else:
                            failed_downloads += 1
                            logger.warning(f"Failed to download {result.course_code}: {result.error}")
                            pbar.set_postfix(success=successful_downloads, failed=failed_downloads)
                    
                    except Exception as e:
                        failed_downloads += 1
                        logger.error(f"Error processing download for {url_info['course_code']}: {e}")
                        pbar.set_postfix(success=successful_downloads, failed=failed_downloads)
                    
                    finally:
                        pbar.update(1)
        
        # Final results
        total_downloads = successful_downloads + failed_downloads
        logger.info(f"Download complete: {successful_downloads} successful, {failed_downloads} failed")
        
        return {
            'total': total_downloads,
            'successful': successful_downloads,
            'failed': failed_downloads,
            'success_rate': (successful_downloads / total_downloads * 100) if total_downloads > 0 else 0
        }
    
    def get_download_statistics(self) -> Dict:
        """Get comprehensive download statistics"""
        stats = self.pdf_store.get_download_statistics()
        
        # Add file system statistics
        if self.output_dir.exists():
            pdf_files = list(self.output_dir.glob("*.pdf"))
            stats['filesystem'] = {
                'pdf_files_on_disk': len(pdf_files),
                'output_directory': str(self.output_dir),
                'directory_exists': True
            }
        else:
            stats['filesystem'] = {
                'pdf_files_on_disk': 0,
                'output_directory': str(self.output_dir),
                'directory_exists': False
            }
        
        return stats
    
    def validate_downloads(self) -> Dict:
        """Validate downloaded PDFs against database records"""
        stats = {'validated': 0, 'missing': 0, 'corrupted': 0, 'issues': []}
        
        try:
            # Get successful downloads from database
            successful_downloads = self.pdf_store.get_existing_downloads()
            
            for course_code, download_info in successful_downloads.items():
                file_path = download_info['file_path']
                expected_checksum = download_info['checksum']
                
                if not os.path.exists(file_path):
                    stats['missing'] += 1
                    stats['issues'].append(f"Missing file: {course_code} - {file_path}")
                    continue
                
                # Verify checksum if available
                if expected_checksum:
                    actual_checksum = calculate_file_checksum(file_path)
                    if actual_checksum != expected_checksum:
                        stats['corrupted'] += 1
                        stats['issues'].append(f"Checksum mismatch: {course_code}")
                        continue
                
                stats['validated'] += 1
            
            logger.info(f"Validation complete: {stats['validated']} valid, {stats['missing']} missing, {stats['corrupted']} corrupted")
            
        except Exception as e:
            logger.error(f"Validation failed: {e}")
            stats['error'] = str(e)
        
        return stats


# ----- Main Function -----

def main():
    """Main entry point for database PDF downloader"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Download PDFs using database-stored URLs')
    parser.add_argument('--output-dir', '-o', default=DEFAULT_OUTPUT_DIR,
                       help=f'Directory to save PDFs (default: {DEFAULT_OUTPUT_DIR})')
    parser.add_argument('--max-workers', '-w', type=int, default=DEFAULT_MAX_WORKERS,
                       help=f'Maximum concurrent downloads (default: {DEFAULT_MAX_WORKERS})')
    parser.add_argument('--delay', '-d', type=float, default=DEFAULT_DELAY,
                       help=f'Delay between downloads (default: {DEFAULT_DELAY})')
    parser.add_argument('--database', default="data/csexpert.db",
                       help='Database file path (default: data/csexpert.db)')
    parser.add_argument('--force', action='store_true',
                       help='Force redownload of existing files')
    parser.add_argument('--validate', action='store_true',
                       help='Validate existing downloads only')
    parser.add_argument('--stats', action='store_true',
                       help='Show download statistics only')
    
    args = parser.parse_args()
    
    try:
        logger.info("Starting Database PDF Downloader")
        
        # Initialize downloader
        downloader = DatabasePDFDownloader(
            database_path=args.database,
            output_dir=args.output_dir,
            max_workers=args.max_workers,
            delay=args.delay
        )
        
        if args.stats:
            # Show statistics only
            stats = downloader.get_download_statistics()
            logger.info(f"Download statistics: {stats}")
            return
        
        if args.validate:
            # Validate downloads only
            validation_results = downloader.validate_downloads()
            logger.info(f"Validation results: {validation_results}")
            return
        
        # Perform downloads
        results = downloader.download_all_pdfs(force_redownload=args.force)
        
        logger.info("\n=== DOWNLOAD COMPLETE ===")
        logger.info(f"✓ Total: {results['total']} downloads")
        logger.info(f"✓ Successful: {results['successful']} PDFs")
        logger.info(f"✓ Failed: {results['failed']} PDFs")
        logger.info(f"✓ Success rate: {results['success_rate']:.1f}%")
        
        # Show final statistics
        final_stats = downloader.get_download_statistics()
        logger.info(f"✓ Final statistics: {final_stats}")
        
    except Exception as e:
        logger.error(f"PDF download failed: {e}")
        return False
    
    return True


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)