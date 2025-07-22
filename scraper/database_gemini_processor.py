#!/usr/bin/env python3
"""
Database-Connected Gemini Content Processor

Enhanced version of gemini_parser.py that integrates with the CSExpert database.
Processes PDFs and markdown files using Gemini API and stores structured content
directly in the database using SQLAlchemy ORM models.
"""

import logging
import os
import json
import base64
import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from decimal import Decimal

from dotenv import load_dotenv
from tqdm import tqdm

# Conditional import for Gemini API
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    genai = None
    GEMINI_AVAILABLE = False

# Import database components
from database.connection_manager import get_database_manager, DatabaseManager
from database.models import (
    Course, CourseSection, Program, CourseProgramMapping, 
    CourseDetails, LanguageStandard, DataQualityIssue,
    find_course_by_code
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# ----- Configuration Constants -----

# Gemini model configuration
DEFAULT_MODEL_NAME = "gemini-2.5-flash"  # Dont change this, it is the best model for this task
API_RETRY_ATTEMPTS = 3
API_DELAY = 0.06  # TIER 1
REQUEST_TIMEOUT = 60

# Processing settings - TIER 1 optimized
DEFAULT_BATCH_SIZE = 100  # Larger batches for 10,000/day limit
CONTENT_PREVIEW_LENGTH = 100

# Valid program codes - only these should be created automatically
# Valid program codes - only active programs
VALID_PROGRAM_CODES = {
    'N2COS', 'N2SOF', 'N1SOF', 'N2GDT'
}


# ----- Data Structures -----

class ProcessingResult:
    """Container for Gemini processing results"""
    
    def __init__(self, source_path: str, content_type: str, 
                 success: bool = False, course_data: Optional[Dict] = None,
                 error: Optional[str] = None, processing_time: float = 0.0,
                 cost_estimate: float = 0.0):
        self.source_path = source_path
        self.content_type = content_type  # 'pdf', 'syllabus_md', 'course_page_md'
        self.success = success
        self.course_data = course_data
        self.error = error
        self.processing_time = processing_time
        self.cost_estimate = cost_estimate
        self.processed_at = datetime.utcnow()


# ----- Database Operations -----

class DatabaseGeminiStore:
    """Handles database operations for Gemini processing tracking"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.setup_tables()
    
    def setup_tables(self):
        """Ensure Gemini processing tracking tables exist"""
        try:
            with self.db_manager.transaction() as conn:
                # Create gemini_processing_jobs table
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS gemini_processing_jobs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        source_path TEXT NOT NULL,
                        content_type VARCHAR(20) CHECK (content_type IN ('pdf', 'syllabus_md', 'course_page_md')) NOT NULL,
                        course_code VARCHAR(10),
                        processing_status VARCHAR(20) CHECK (processing_status IN ('pending', 'processing', 'success', 'failed')) DEFAULT 'pending',
                        error_message TEXT,
                        processing_time REAL DEFAULT 0.0,
                        cost_estimate REAL DEFAULT 0.0,
                        retry_count INTEGER DEFAULT 0,
                        gemini_response TEXT,
                        processed_at TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(source_path, content_type)
                    )
                """)
                
                # Create indexes for performance
                conn.execute("CREATE INDEX IF NOT EXISTS idx_gemini_jobs_status ON gemini_processing_jobs(processing_status)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_gemini_jobs_course_code ON gemini_processing_jobs(course_code)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_gemini_jobs_content_type ON gemini_processing_jobs(content_type)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_gemini_jobs_processed_at ON gemini_processing_jobs(processed_at)")
                
                # Add migration for existing databases that might be missing the gemini_response column
                try:
                    conn.execute("ALTER TABLE gemini_processing_jobs ADD COLUMN gemini_response TEXT")
                    logger.info("Added missing gemini_response column to existing table")
                except Exception as e:
                    # Column already exists or other error - this is expected for new databases
                    logger.debug(f"Gemini response column migration: {e}")
                
                logger.info("Gemini processing tracking tables initialized")
                
        except Exception as e:
            logger.error(f"Failed to setup Gemini processing tables: {e}")
            raise
    
    def get_pending_processing_items(self, content_type: str = None) -> List[Dict]:
        """Get items that need Gemini processing"""
        try:
            base_query = """
                SELECT * FROM gemini_processing_jobs 
                WHERE processing_status IN ('pending', 'failed') 
                  AND retry_count < ?
            """
            params = [API_RETRY_ATTEMPTS]
            
            if content_type:
                base_query += " AND content_type = ?"
                params.append(content_type)
            
            base_query += " ORDER BY created_at ASC"
            
            results = self.db_manager.execute_query(base_query, tuple(params))
            return [dict(row) for row in results]
            
        except Exception as e:
            logger.error(f"Failed to get pending processing items: {e}")
            return []
    
    def record_processing_attempt(self, result: ProcessingResult) -> bool:
        """Record a Gemini processing attempt"""
        try:
            # Get current retry count
            existing_query = "SELECT retry_count FROM gemini_processing_jobs WHERE source_path = ? AND content_type = ?"
            existing_results = self.db_manager.execute_query(existing_query, (result.source_path, result.content_type))
            
            retry_count = 1
            if existing_results:
                retry_count = existing_results[0]['retry_count'] + 1
            
            query = """
                INSERT OR REPLACE INTO gemini_processing_jobs 
                (source_path, content_type, course_code, processing_status, 
                 error_message, processing_time, cost_estimate, retry_count, gemini_response, processed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            
            # Extract course code from path
            course_code = self._extract_course_code_from_path(result.source_path)
            status = 'success' if result.success else 'failed'
            
            # Convert course_data to JSON string for storage
            import json
            gemini_response_json = json.dumps(result.course_data) if result.course_data else None
            
            self.db_manager.execute_update(query, (
                result.source_path,
                result.content_type,
                course_code,
                status,
                result.error,
                result.processing_time,
                result.cost_estimate,
                retry_count,
                gemini_response_json,
                result.processed_at
            ))
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to record processing attempt: {e}")
            return False
    
    def _extract_course_code_from_path(self, path: str) -> Optional[str]:
        """Extract course code from file path"""
        try:
            filename = os.path.basename(path)
            base_name = os.path.splitext(filename)[0].upper()
            
            # Handle files with suffixes like "DIT007_course" or "DIT007_syllabus"
            # Extract just the course code part before any underscore
            if '_' in base_name:
                course_code = base_name.split('_')[0]
            else:
                course_code = base_name
                
            # Validate course code format (2-3 letters followed by 3-4 digits)
            if re.match(r'^[A-Z]{2,3}\d{3,4}$', course_code):
                return course_code
            return None
        except Exception:
            return None
    
    def get_processing_statistics(self) -> Dict:
        """Get statistics about Gemini processing"""
        try:
            with self.db_manager.get_connection() as conn:
                stats = {}
                
                # Processing status counts
                cursor = conn.execute("""
                    SELECT processing_status, COUNT(*) as count 
                    FROM gemini_processing_jobs 
                    GROUP BY processing_status
                """)
                stats['by_status'] = {row['processing_status']: row['count'] for row in cursor.fetchall()}
                
                # Content type counts
                cursor = conn.execute("""
                    SELECT content_type, COUNT(*) as count 
                    FROM gemini_processing_jobs 
                    GROUP BY content_type
                """)
                stats['by_content_type'] = {row['content_type']: row['count'] for row in cursor.fetchall()}
                
                # Cost analysis
                cursor = conn.execute("""
                    SELECT SUM(cost_estimate) as total_cost, AVG(cost_estimate) as avg_cost,
                           COUNT(*) as successful_jobs, AVG(processing_time) as avg_time
                    FROM gemini_processing_jobs 
                    WHERE processing_status = 'success'
                """)
                result = cursor.fetchone()
                stats['cost_analysis'] = {
                    'total_cost': result['total_cost'] or 0.0,
                    'average_cost': result['avg_cost'] or 0.0,
                    'successful_jobs': result['successful_jobs'] or 0,
                    'average_processing_time': result['avg_time'] or 0.0
                }
                
                # Latest processing
                cursor = conn.execute("""
                    SELECT MAX(processed_at) as latest_processing 
                    FROM gemini_processing_jobs
                """)
                latest = cursor.fetchone()['latest_processing']
                stats['latest_processing'] = latest
                
                return stats
                
        except Exception as e:
            logger.error(f"Failed to get processing statistics: {e}")
            return {}
    
    def add_processing_job(self, source_path: str, content_type: str) -> bool:
        """Add a new processing job"""
        try:
            course_code = self._extract_course_code_from_path(source_path)
            
            query = """
                INSERT OR IGNORE INTO gemini_processing_jobs 
                (source_path, content_type, course_code, processing_status)
                VALUES (?, ?, ?, 'pending')
            """
            
            result = self.db_manager.execute_update(query, (source_path, content_type, course_code))
            return result > 0
            
        except Exception as e:
            logger.error(f"Failed to add processing job: {e}")
            return False


# ----- Content Processing Functions -----

def extract_program_codes(programmes_field: Any) -> List[str]:
    """Extract program codes from various programme field formats"""
    program_codes = []
    
    if not programmes_field:
        return program_codes
    
    try:
        # Handle list format
        if isinstance(programmes_field, list):
            for prog in programmes_field:
                codes = _extract_codes_from_string(str(prog))
                program_codes.extend(codes)
        
        # Handle string format
        elif isinstance(programmes_field, str):
            codes = _extract_codes_from_string(programmes_field)
            program_codes.extend(codes)
        
        # Remove duplicates and return
        return list(set(program_codes))
        
    except Exception as e:
        logger.warning(f"Error extracting program codes from {programmes_field}: {e}")
        return []


def _extract_codes_from_string(text: str) -> List[str]:
    """Extract program codes from a text string"""
    codes = []
    
    # Pattern for codes in parentheses like (N2COS)
    parentheses_matches = re.findall(r'\(([A-Z0-9]{5,6})\)', text)
    codes.extend(parentheses_matches)
    
    # Pattern for standalone codes
    if not codes:
        standalone_matches = re.findall(r'\b([A-Z]\d[A-Z]{3})\b', text)
        codes.extend(standalone_matches)
    
    return codes


def normalize_language_instruction(language: str) -> Optional[str]:
    """Normalize language instruction to standard format"""
    if not language:
        return None
    
    # Ensure we have a string to work with
    try:
        language_str = str(language).strip()
        if not language_str:
            return None
            
        language_lower = language_str.lower()
        
        # Language mapping
        if 'english' in language_lower and 'swedish' in language_lower:
            return 'EN,SV'
        elif 'english' in language_lower:
            return 'EN'
        elif 'swedish' in language_lower:
            return 'SV'
        
        return language_str  # Return cleaned string if no match
    except Exception as e:
        logger.warning(f"Error normalizing language '{language}': {e}")
        return None


def validate_credits(credits: Any) -> Optional[Decimal]:
    """Validate and normalize credits value"""
    if not credits:
        return None
    
    try:
        # Convert to string and clean
        credits_str = str(credits).strip()
        
        # Remove common text
        credits_str = re.sub(r'\s*(credits?|hp|högskolepoäng)\s*', '', credits_str, flags=re.IGNORECASE)
        
        # Replace comma with dot
        credits_str = credits_str.replace(',', '.')
        
        # Extract number
        match = re.search(r'(\d+(?:\.\d+)?)', credits_str)
        if match:
            credits_value = Decimal(match.group(1))
            
            # Only validate that credits is positive
            if credits_value <= 0:
                logger.warning(f"Invalid credits value (must be positive): {credits_value}")
                return None
            
            return credits_value
        
        return None
        
    except Exception as e:
        logger.warning(f"Error validating credits {credits}: {e}")
        return None


# ----- Main Gemini Processor Class -----

class DatabaseGeminiProcessor:
    """Main Gemini processor with database integration"""
    
    def __init__(self, database_path: str = "data/csexpert.db", 
                 model_name: str = DEFAULT_MODEL_NAME,
                 api_key: Optional[str] = None):
        
        self.db_manager = get_database_manager(database_path)
        self.gemini_store = DatabaseGeminiStore(self.db_manager)
        
        # Initialize Gemini API
        if not GEMINI_AVAILABLE:
            logger.warning("Google Generative AI not available. Processing will be limited to testing mode.")
            self.api_key = None
            self.model = None
        else:
            # Force loading from .env file only, ignore environment variables
            if api_key:
                self.api_key = api_key
            else:
                # Load from .env file directly
                from dotenv import dotenv_values
                env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
                config = dotenv_values(env_path)
                self.api_key = config.get("GEMINI_API_KEY")
                
                if not self.api_key:
                    raise ValueError(f"Gemini API key is required. Please set GEMINI_API_KEY in {env_path}")
            
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel(model_name)
            logger.info(f"Gemini API configured with key from {'parameter' if api_key else env_path} (key: {self.api_key[:10]}...)")
        
        # Initialize database if not already done
        if not self.db_manager.initialize_database():
            raise RuntimeError("Failed to initialize database")
        
        logger.info(f"Database Gemini Processor initialized with model: {model_name}")
    
    def encode_pdf(self, pdf_path: str) -> str:
        """Encode PDF file to base64 for Gemini API"""
        try:
            with open(pdf_path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            logger.error(f"Failed to encode PDF {pdf_path}: {e}")
            raise
    
    def read_markdown(self, md_path: str) -> str:
        """Read markdown file content"""
        try:
            with open(md_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            logger.error(f"Failed to read markdown {md_path}: {e}")
            raise
    
    def get_pdf_prompt(self) -> str:
        """Get the prompt for PDF extraction (from original gemini_parser.py)"""
        return """
        You are an expert at extracting structured information from course syllabus PDFs.
        
        Extract the following information from the PDF:
        1. Metadata: 
           - course_code (e.g. DIT231, LT343, TIA335, MSA341, MMA341, etc.)
           - course_title (e.g. "Mathematical Foundations for Software Engineering", it is possible that you find other information in the title e.g. 7.5, don't consider this)
           - swedish_title (e.g. "Grundläggande matematik för mjukvarutekniker", it is possible that you find other information in the title e.g. 7.5, don't consider this)
           - department (e.g. Department of Computer Science and Engineering, Department of Mathematics, Department of Applied Information Technology, etc.)
           - field_of_education (e.g. Science 100%, Technology 100%, etc.)
           - credits (only the number, not the text) (e.g. 7.5, 6.0, 15.0, etc.)
           - cycle (e.g. First cycle, Second cycle, etc.)
           - main_field_of_study (e.g. Computer Science, Communication, Mathematics, etc. if there is no main field of study, return an empty string)
           - specialization (e.g. G1N, A1N, G2F, G1F, etc.  if there is no specialization, return an empty string)
           - language_of_instruction (e.g. English, Swedish, English and Swedish, etc.)
           - confirmation_date (e.g. 2025-01-01)
           - revision_date (e.g. 2025-01-01, some courses have this, some don't)
           - valid_from_date (e.g. 2025-01-01)
           - programmes (as a list of strings look in the "Position in the educational system" section, only retrieve the program codes e.g "N2COS", "N2SOF", "N1SOF", "N2GDT", if there is no programme or program code, return an empty list, never return a program name e.g. "Software Engineering and Management", "Computer Science and Engineering", etc.)
        
        2. Sections: 
           - Confirmation
           - Entry requirements
           - Learning outcomes
           - Course content
           - Sub-courses or Course modules (some courses have this, some don't)
           - Form of teaching
           - Assessment
           - Grades
           - Course evaluation
           - Additional information (some courses have this, some don't)
           - Replacing course code (only retrieve the course code this course is replacing, e.g. "DIT231", "DIT6132", the information is in the "Additional information" section, some courses have this, some don't)
        
        Return the information in the following JSON format:
        {
          "metadata": {
            "course_code": "[code]",
            "course_title": "[title]",
            "swedish_title": "[swedish title]",
            "department": "[department]",
            "field_of_education": "[field]",
            "credits": "[credits]",
            "cycle": "[cycle]",
            "main_field_of_study": "[main field]",
            "specialization": "[specialization]",
            "language_of_instruction": "[language]",
            "confirmation_date": "[date]",
            "valid_from_date": "[date]",
            "programmes": [
              "[programme codes as list items]"
            ]
          },
          "sections": {
            "Confirmation": "[text]",
            "Entry requirements": "[text]",
            "Learning outcomes": "[text]",
            "Course content": "[text]",
            "Sub-courses": "[text]",
            "Form of teaching": "[text]",
            "Assessment": "[text]",
            "Grades": "[text]",
            "Course evaluation": "[text]",
            "Additional information": "[text]",
            "Replacing course code": "[text]"
          }
        }
        
        Only return valid JSON, no explanations or other text.
        """
    
    def get_markdown_prompt(self) -> str:
        """Get the prompt for Markdown extraction (from original gemini_parser.py)"""
        return """
        You are an expert at extracting structured information from course syllabus markdown files.
        
        Extract the following information from the markdown:
        1. Metadata: 
           - course_code (e.g. DIT231, LT343, TIA335, MSA341, MMA341, etc.)
           - course_title (e.g. "Mathematical Foundations for Software Engineering", it is possible that you find other information in the title e.g. 7.5, don't consider this)
           - swedish_title (e.g. "Grundläggande matematik för mjukvarutekniker", it is possible that you find other information in the title e.g. 7.5, don't consider this)
           - department (e.g. Department of Computer Science and Engineering, Department of Mathematics, Department of Applied Information Technology, etc.)
           - credits (only the number, not the text) (e.g. 7.5, 6.0, 15.0, etc.)
           - cycle (e.g. First cycle, Second cycle, etc.)
           - language_of_instruction (e.g. English, Swedish, English and Swedish, etc.)
           - confirmation_date (may be called "Decision date")
           - valid_from_date (may be called "Date of entry into force")
           - programmes (as a list of strings, look in the "Position" section, only retrieve the program codes e.g "N2COS", "N2SOF", "N1SOF", "N2GDT", if there is no programme or program code, return an empty list, never return a program name e.g. "Software Engineering and Management", "Computer Science and Engineering", etc.)
        
        2. COURSE DETAILS (specific information, not for search):
           - confirmation_date (may be called "Decision date")
           - valid_from_date (may be called "Date of entry into force" or similar - original text)
        
        3. SECTIONS (content - map to these exact keys in the output): 
           - Entry requirements
           - Course content (may be just "Content")
           - Sub-courses (may be called "Modules")
           - Learning outcomes (may be "Objectives")
           - Form of teaching
           - Assessment (from "Examination formats")
           - Grades
           - Course evaluation
           - Additional information (from "Other regulations")
        
        Return the information in the following JSON format:
        {
          "metadata": {
            "course_code": "[code]",
            "course_title": "[title]",
            "swedish_title": "[swedish title]",
            "department": "[department]",
            "credits": "[credits]",
            "cycle": "[cycle]",
            "language_of_instruction": "[language]",
            "confirmation_date": "[date]",
            "valid_from_date": "[date]",
            "programmes": [
              "[programme codes as list items]"
            ]
          },
          "sections": {
            "Position in the educational system": "[text]",
            "Entry requirements": "[text]",
            "Learning outcomes": "[text]",
            "Course content": "[text]",
            "Sub-courses": "[text]",
            "Form of teaching": "[text]",
            "Assessment": "[text]",
            "Grades": "[text]",
            "Course evaluation": "[text]",
            "Additional information": "[text]"
          }
        }
        
        Only return valid JSON, no explanations or other text. Be sure to map the section names correctly even if they have different names in the original markdown.
        """
    
    def get_course_page_markdown_prompt(self) -> str:
        """Get the prompt for course page Markdown extraction (optimized for RAG metadata separation)"""
        return """
        You are an expert at extracting structured information from course page markdown files.
        
        IMPORTANT: Separate true metadata (for search/filtering) from course-specific details.
        
        Extract the following information from the markdown:
        
        1. METADATA (searchable attributes): 
           - course_code (e.g. DIT231, LT343, TIA335, MSA341, MMA341, etc.)
           - course_title (main course title)
           - department (offering department) (e.g. Department of Computer Science and Engineering, Department of Mathematics, Department of Applied Information Technology, etc.)
           - credits (only the number as string, e.g. "7.5", "6.0", "15.0", etc.)
           - study_form ("Campus", "Online", "Distance", "Hybrid")
           - language_of_instruction ("English", "Swedish", "English and Swedish")
           - term (parsed from dates like "Autumn 2025", "Spring 2025", "Summer 2025", "Autumn 2026")
        
        2. COURSE DETAILS (specific information, not for search):
           - tuition_fee (specific amount without spaces or special characters, e.g. "17753", "150000", etc.)
           - application_period (specific application dates, e.g. "24 Mar 2025 - 8 Jun 2025")
           - duration (specific date ranges like "24 Mar 2025 - 8 Jun 2025")
           - application_code (administrative codes like "GU-86092")
           - page_last_modified (date of last modification e.g. "19 June 2025", "June 19, 2025", "2025-06-19")
        
        3. SECTIONS (content):
           - About
           - Entry requirements  
           - Selection
           - Tuition (full text including full education cost, first payment, no fee are charged for EU and EEA citizens...)
        
        Return the information in the following JSON format:
        {
          "metadata": {
            "course_code": "[code]",
            "course_title": "[title]",
            "department": "[department]",
            "credits": "[credits]",
            "study_form": "[study_form]",
            "language_of_instruction": "[language]",
            "field_of_education": "[field]",
            "main_field_of_study": "[main_field]",
            "term": "[term]",
            "programmes": ["[programme names as list items]"]
          },
          "course_details": {
            "tuition_fee": "[amount]",
            "application_period": "[application_dates]",
            "duration": "[date_range]",
            "application_code": "[code]",
            "page_last_modified": "[date]"
          },
          "sections": {
            "About": "[text]",
            "Entry requirements": "[text]",
            "Selection": "[text]",
            "Tuition": "[text]",
            "Additional information": "[text]"
          }
        }
        
        Only return valid JSON, no explanations or other text. If information is not available, return an empty string.
        """
    
    def process_single_content(self, source_path: str, content_type: str) -> ProcessingResult:
        """Process a single content file using Gemini API"""
        start_time = time.time()
        
        result = ProcessingResult(
            source_path=source_path,
            content_type=content_type
        )
        
        try:
            # Prepare content for Gemini based on type
            if content_type == "pdf":
                prompt = self.get_pdf_prompt()
                pdf_base64 = self.encode_pdf(source_path)
                
                content_parts = [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": "application/pdf",
                            "data": pdf_base64
                        }
                    }
                ]
                
            elif content_type in ["syllabus_md", "course_page_md"]:
                md_content = self.read_markdown(source_path)
                
                if content_type == "syllabus_md":
                    prompt = self.get_markdown_prompt()
                else:  # course_page_md
                    prompt = self.get_course_page_markdown_prompt()
                
                content_parts = [
                    {"text": prompt + "\n\nHere is the markdown content:\n\n" + md_content}
                ]
                
            else:
                result.error = f"Unsupported content type: {content_type}"
                return result
            
            # Process with Gemini API with retry logic
            if not GEMINI_AVAILABLE or not self.model:
                result.error = "Gemini API not available"
                return result
                
            for attempt in range(API_RETRY_ATTEMPTS):
                try:
                    time.sleep(API_DELAY)  # Rate limiting
                    
                    response = self.model.generate_content(content_parts)
                    
                    if not response or not response.text:
                        result.error = "Empty response from Gemini API"
                        continue
                    
                    # Parse JSON response
                    json_str = response.text.replace("```json", "").replace("```", "").strip()
                    course_data = json.loads(json_str)
                    
                    # Validate required fields
                    if not self._validate_course_data(course_data):
                        result.error = "Invalid course data structure"
                        continue
                    
                    # Success!
                    result.success = True
                    result.course_data = course_data
                    result.processing_time = time.time() - start_time
                    result.cost_estimate = self._estimate_processing_cost(content_type, response.text)
                    
                    break
                    
                except json.JSONDecodeError as e:
                    result.error = f"JSON parsing error: {str(e)}"
                    if attempt == API_RETRY_ATTEMPTS - 1:
                        logger.error(f"Failed to parse JSON after {API_RETRY_ATTEMPTS} attempts: {result.error}")
                
                except Exception as e:
                    result.error = f"Gemini API error: {str(e)}"
                    if attempt == API_RETRY_ATTEMPTS - 1:
                        logger.error(f"Gemini API failed after {API_RETRY_ATTEMPTS} attempts: {result.error}")
                    time.sleep(2 ** attempt)  # Exponential backoff
            
            return result
            
        except Exception as e:
            result.error = f"Processing error: {str(e)}"
            result.processing_time = time.time() - start_time
            logger.error(f"Error processing {source_path}: {result.error}")
            return result
    
    def _validate_course_data(self, data: Dict) -> bool:
        """Validate that course data has required structure"""
        try:
            # Check required top-level keys
            if not isinstance(data, dict) or 'metadata' not in data or 'sections' not in data:
                return False
            
            metadata = data['metadata']
            sections = data['sections']
            
            # Check required metadata
            if not isinstance(metadata, dict) or not metadata.get('course_code'):
                return False
            
            # Check sections
            if not isinstance(sections, dict) or len(sections) == 0:
                return False
            
            # Optional: validate course_details if present (for course page content)
            if 'course_details' in data:
                course_details = data['course_details']
                if not isinstance(course_details, dict):
                    return False
            
            return True
            
        except Exception:
            return False
    
    def _estimate_processing_cost(self, content_type: str, response_text: str) -> float:
        """Estimate processing cost for Gemini API usage"""
        try:
            # Gemini Flash pricing (approximate):
            # Input: $0.075 per 1M tokens
            # Output: $0.30 per 1M tokens
            
            # Rough token estimates
            if content_type == "pdf":
                input_tokens = 2000  # PDF + prompt
            else:  # markdown
                input_tokens = 1500  # Markdown + prompt
            
            output_tokens = len(response_text.split()) * 1.3  # ~1.3 tokens per word
            
            cost = (input_tokens * 0.075 + output_tokens * 0.30) / 1000000
            return round(cost, 6)
            
        except Exception:
            return 0.002  # Default estimate
    
    def store_course_in_database(self, course_data: Dict, content_type: str) -> Optional[int]:
        """Store parsed course data in database using ORM models
        
        Args:
            course_data: Parsed course data from Gemini
            content_type: Type of content being processed ('pdf', 'syllabus_md', 'course_page_md')
        """
        try:
            from sqlalchemy.orm import sessionmaker
            
            # Create session
            from sqlalchemy import create_engine
            engine = create_engine(f"sqlite:///{self.db_manager.database_path}")
            Session = sessionmaker(bind=engine)
            session = Session()
            
            try:
                metadata = course_data.get('metadata', {})
                sections = course_data.get('sections', {})
                
                # Extract and validate basic course info
                course_code = metadata.get('course_code', '').upper()
                if not course_code:
                    raise ValueError("Missing course code")
                
                # Check if course already exists
                existing_course = find_course_by_code(session, course_code, current_only=True)
                
                if existing_course:
                    logger.info(f"Course {course_code} already exists, updating...")
                    course = existing_course
                else:
                    logger.info(f"Creating new course: {course_code}")
                    course = Course()
                
                # Update course metadata with safe field handling
                course.course_code = course_code
                
                # For course_page_md, only update specific fields
                if content_type == 'course_page_md':
                    logger.info(f"Updating only specific fields for course page: {course_code}")
                    # Only update study_form and term from metadata
                    if 'study_form' in metadata:
                        course.study_form = metadata['study_form']
                    if 'term' in metadata:
                        course.term = metadata['term']
                else:
                    # For PDF and syllabus_md, update all fields as before
                    # Safely handle course title
                    try:
                        title = metadata.get('course_title', '')
                        course.course_title = str(title)[:500] if title else ''
                    except Exception as e:
                        logger.warning(f"Error setting course_title for {course_code}: {e}")
                        course.course_title = f"Course {course_code}"  # Fallback title
                    
                    # Safely handle swedish title
                    try:
                        swedish_title = metadata.get('swedish_title')
                        course.swedish_title = str(swedish_title) if swedish_title else None
                    except Exception as e:
                        logger.warning(f"Error setting swedish_title for {course_code}: {e}")
                        course.swedish_title = None
                    
                    # Safely handle department
                    try:
                        dept = metadata.get('department', 'Unknown')
                        course.department = str(dept)[:100] if dept else 'Unknown'
                    except Exception as e:
                        logger.warning(f"Error setting department for {course_code}: {e}")
                        course.department = 'Unknown'
                    
                    # Handle credits
                    credits = validate_credits(metadata.get('credits'))
                    if credits:
                        course.credits = credits
                    else:
                        course.credits = Decimal('7.5')  # Default
                        logger.warning(f"Using default credits for {course_code}")
                    
                    # Handle cycle with normalization
                    cycle = metadata.get('cycle')
                    if cycle:
                        # Convert to string and normalize cycle capitalization
                        cycle_str = str(cycle).lower()
                        if 'first' in cycle_str:
                            course.cycle = 'First cycle'
                        elif 'second' in cycle_str:
                            course.cycle = 'Second cycle'
                        elif 'third' in cycle_str:
                            course.cycle = 'Third cycle'
                        else:
                            course.cycle = 'Second cycle'  # Default
                    else:
                        course.cycle = 'Second cycle'  # Default for graduate courses
                    
                    # Handle language
                    language = normalize_language_instruction(metadata.get('language_of_instruction'))
                    if language:
                        # Find or create language standard
                        lang_standard = session.query(LanguageStandard).filter_by(standard_code=language).first()
                        if not lang_standard:
                            lang_standard = LanguageStandard(
                                standard_code=language,
                                display_name=language.replace(',', ' and '),
                                original_variations=json.dumps([metadata.get('language_of_instruction')])
                            )
                            session.add(lang_standard)
                            session.flush()
                        
                        course.language_of_instruction_id = lang_standard.id
                    
                    # Handle dates
                    if metadata.get('confirmation_date'):
                        try:
                            import re
                            from datetime import datetime
                            # Try to parse date
                            date_str = metadata['confirmation_date']
                            if re.match(r'\d{4}-\d{2}-\d{2}', date_str):
                                course.confirmation_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                        except Exception as e:
                            logger.warning(f"Failed to parse confirmation_date: {e}")
                    
                    course.valid_from_date = metadata.get('valid_from_date')
                    course.processing_method = 'gemini_ai'
                
                # Add to session if new
                if not existing_course:
                    session.add(course)
                
                session.flush()  # Get the course ID
                
                # Handle "Replacing course code" section specially
                if 'Replacing course code' in sections:
                    try:
                        replacing_code_raw = sections.get('Replacing course code', '')
                        replacing_code = str(replacing_code_raw).strip() if replacing_code_raw else ''
                    except Exception as e:
                        logger.warning(f"Error processing replacing course code: {e}")
                        replacing_code = ''
                    
                    if replacing_code:
                        # Extract just the course code (e.g., "DIT231" from any surrounding text)
                        code_match = re.search(r'\b([A-Z]{2,3}\d{3,4})\b', replacing_code)
                        if code_match:
                            course.replacing_course_code = code_match.group(1)
                            logger.info(f"Course {course.course_code} replaces {course.replacing_course_code}")
                
                # Handle course sections
                if content_type == 'course_page_md':
                    # For course pages, only update Selection and Tuition sections
                    allowed_sections = {'Selection', 'Tuition'}
                    for section_name, section_content in sections.items():
                        if section_name not in allowed_sections:
                            continue
                        if section_content is None or (isinstance(section_content, str) and not section_content.strip()):
                            continue
                        
                        # Check if section already exists
                        existing_section = session.query(CourseSection).filter_by(
                            course_id=course.id, section_name=section_name
                        ).first()
                        
                        if existing_section:
                            # Safe handling - convert to string first
                            content_str = str(section_content) if section_content is not None else ""
                            existing_section.section_content = content_str.strip() if content_str else ""
                            existing_section.character_count = len(content_str) if content_str else 0
                        else:
                            # Safe handling - convert to string first
                            content_str = str(section_content) if section_content is not None else ""
                            section = CourseSection(
                                course_id=course.id,
                                section_name=section_name,
                                section_content=content_str.strip() if content_str else "",
                                character_count=len(content_str) if content_str else 0
                            )
                            session.add(section)
                else:
                    # For PDF and syllabus_md, update all sections as before
                    for section_name, section_content in sections.items():
                        if section_content is None or (isinstance(section_content, str) and not section_content.strip()):
                            continue
                        
                        # Check if section already exists
                        existing_section = session.query(CourseSection).filter_by(
                            course_id=course.id, section_name=section_name
                        ).first()
                        
                        if existing_section:
                            # Safe handling - convert to string first
                            content_str = str(section_content) if section_content is not None else ""
                            existing_section.section_content = content_str.strip() if content_str else ""
                            existing_section.character_count = len(content_str) if content_str else 0
                        else:
                            # Safe handling - convert to string first
                            content_str = str(section_content) if section_content is not None else ""
                            section = CourseSection(
                                course_id=course.id,
                                section_name=section_name,
                                section_content=content_str.strip() if content_str else "",
                                character_count=len(content_str) if content_str else 0
                            )
                            session.add(section)
                
                # Handle program mappings (skip for course_page_md)
                if content_type != 'course_page_md':
                    programs = extract_program_codes(metadata.get('programmes'))
                    if programs:
                        # Clear existing mappings
                        session.query(CourseProgramMapping).filter_by(course_id=course.id).delete()
                        
                        for program_code in programs:
                            # Validate program code against expanded whitelist
                            if program_code not in VALID_PROGRAM_CODES:
                                logger.warning(f"Unknown program code '{program_code}' for course {course.course_code}. Currently allowed: {VALID_PROGRAM_CODES}")
                                continue
                            
                            # Find or create program (only for valid codes)
                            program = session.query(Program).filter_by(program_code=program_code).first()
                            if not program:
                                program = Program(
                                    program_code=program_code,
                                    program_name=f"Program {program_code}",
                                    program_type='master',  # Default
                                    department=course.department
                                )
                                session.add(program)
                                session.flush()
                            
                            # Create mapping
                            mapping = CourseProgramMapping(
                                course_id=course.id,
                                program_id=program.id
                            )
                            session.add(mapping)
                
                # Handle course details and additional metadata fields
                course_details_data = course_data.get('course_details', {})
                
                # Store metadata fields directly in course table (skip most for course_page_md)
                if content_type != 'course_page_md':
                    metadata_fields = {
                        'field_of_education', 'main_field_of_study', 'specialization', 
                        'study_form', 'term'
                    }
                    
                    for field in metadata_fields:
                        if field in metadata:
                            setattr(course, field, metadata[field])
                
                # Handle course details in separate table
                if content_type == 'course_page_md':
                    # For course pages, only update specific course details fields
                    allowed_details_fields = {'tuition_fee', 'duration', 'application_period', 'application_code', 'page_last_modified'}
                    
                    # Check if we have any allowed fields to update
                    if any(key in course_details_data for key in allowed_details_fields) or any(key in metadata for key in allowed_details_fields):
                        # Get existing course details or create new
                        existing_details = session.query(CourseDetails).filter_by(course_id=course.id).first()
                        if not existing_details:
                            course_details = CourseDetails(course_id=course.id)
                        else:
                            course_details = existing_details
                        
                        # Only update allowed fields
                        for details_key in allowed_details_fields:
                            if details_key in course_details_data:
                                value = course_details_data[details_key]
                                if details_key == 'tuition_fee' and value:
                                    try:
                                        # Try to parse tuition fee as decimal
                                        import re
                                        fee_str = re.sub(r'[^\d.]', '', str(value))
                                        setattr(course_details, details_key, Decimal(fee_str) if fee_str else None)
                                    except:
                                        setattr(course_details, details_key, None)
                                elif details_key == 'page_last_modified' and value:
                                    try:
                                        # Parse last modified date
                                        from datetime import datetime
                                        import re
                                        date_str = str(value).strip()
                                        # Try different date formats
                                        for fmt in ['%Y-%m-%d', '%d %B %Y', '%d %b %Y', '%B %d, %Y', '%b %d, %Y']:
                                            try:
                                                parsed_date = datetime.strptime(date_str, fmt).date()
                                                setattr(course_details, details_key, parsed_date)
                                                break
                                            except ValueError:
                                                continue
                                        else:
                                            # If no format matched, try extracting date components
                                            logger.warning(f"Could not parse page_last_modified date: {date_str}")
                                            setattr(course_details, details_key, None)
                                    except Exception as e:
                                        logger.warning(f"Error parsing page_last_modified: {e}")
                                        setattr(course_details, details_key, None)
                                else:
                                    # Convert empty strings to None for all fields
                                    setattr(course_details, details_key, value if value and str(value).strip() else None)
                            elif details_key in metadata:  # Fallback for legacy data
                                value = metadata[details_key]
                                if details_key == 'tuition_fee':
                                    if value is not None and str(value).strip():
                                        try:
                                            import re
                                            fee_str = re.sub(r'[^\d.]', '', str(value))
                                            setattr(course_details, details_key, Decimal(fee_str) if fee_str else None)
                                        except:
                                            setattr(course_details, details_key, None)
                                    else:
                                        setattr(course_details, details_key, None)
                                else:
                                    setattr(course_details, details_key, value if value else None)
                        
                        if not existing_details:
                            session.add(course_details)
                else:
                    # For PDF and syllabus_md, update all fields as before
                    if course_details_data or any(key in metadata for key in ['duration', 'application_period', 'application_code', 'tuition_fee']):
                        # Delete existing course details
                        session.query(CourseDetails).filter_by(course_id=course.id).delete()
                        
                        course_details = CourseDetails(course_id=course.id)
                        
                        # Store course details
                        details_mapping = {
                            'tuition_fee': 'tuition_fee',
                            'duration': 'duration',
                            'application_period': 'application_period',
                            'application_code': 'application_code'
                        }
                        
                        for details_key, db_field in details_mapping.items():
                            if details_key in course_details_data:
                                value = course_details_data[details_key]
                                if details_key == 'tuition_fee' and value:
                                    try:
                                        # Try to parse tuition fee as decimal
                                        import re
                                        fee_str = re.sub(r'[^\d.]', '', str(value))
                                        setattr(course_details, db_field, Decimal(fee_str) if fee_str else None)
                                    except:
                                        setattr(course_details, db_field, None)
                                else:
                                    # Convert empty strings to None for all fields
                                    setattr(course_details, db_field, value if value and str(value).strip() else None)
                            elif details_key in metadata:  # Fallback for legacy data
                                value = metadata[details_key]
                                # Apply same tuition_fee handling for metadata fallback
                                if details_key == 'tuition_fee':
                                    if value is not None and str(value).strip():  # Check if value is not empty
                                        try:
                                            import re
                                            fee_str = re.sub(r'[^\d.]', '', str(value))
                                            setattr(course_details, db_field, Decimal(fee_str) if fee_str else None)
                                        except:
                                            setattr(course_details, db_field, None)
                                    else:
                                        setattr(course_details, db_field, None)  # Convert empty string to None
                                else:
                                    # For non-numeric fields, convert empty strings to None
                                    setattr(course_details, db_field, value if value else None)
                        
                        # Handle confirmation_date and valid_from_date from course_details
                        if 'confirmation_date' in course_details_data:
                            try:
                                import re
                                from datetime import datetime
                                date_str = course_details_data['confirmation_date']
                                if re.match(r'\d{4}-\d{2}-\d{2}', date_str):
                                    course.confirmation_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                            except Exception as e:
                                logger.warning(f"Failed to parse confirmation_date from details: {e}")
                        
                        if 'valid_from_date' in course_details_data:
                            course.valid_from_date = course_details_data['valid_from_date']
                        
                        session.add(course_details)
                
                # Update completeness score
                course.update_completeness_score()
                
                session.commit()
                
                logger.info(f"Successfully stored course {course_code} in database")
                return course.id
                
            except Exception as e:
                session.rollback()
                logger.error(f"Database transaction failed: {e}")
                raise
            
            finally:
                session.close()
                
        except Exception as e:
            logger.error(f"Failed to store course in database: {e}")
            return None
    
    def process_pending_content(self, content_type: str = None, batch_size: int = DEFAULT_BATCH_SIZE) -> Dict:
        """Process all pending content items"""
        logger.info(f"Processing pending content items (type: {content_type or 'all'})")
        
        pending_items = self.gemini_store.get_pending_processing_items(content_type)
        
        if not pending_items:
            logger.info("No pending processing items found")
            return {'total': 0, 'successful': 0, 'failed': 0}
        
        logger.info(f"Found {len(pending_items)} pending items to process")
        
        successful = 0
        failed = 0
        
        # Process in batches
        for i in range(0, len(pending_items), batch_size):
            batch = pending_items[i:i + batch_size]
            logger.info(f"Processing batch {i//batch_size + 1} ({len(batch)} items)")
            
            for item in tqdm(batch, desc=f"Processing {content_type or 'mixed'} content"):
                try:
                    result = self.process_single_content(item['source_path'], item['content_type'])
                    
                    # Store in database if successful
                    if result.success and result.course_data:
                        course_id = self.store_course_in_database(result.course_data, item['content_type'])
                        
                        if course_id:
                            successful += 1
                        else:
                            result.success = False
                            result.error = "Failed to store in database"
                            failed += 1
                    else:
                        failed += 1
                    
                    # Record processing attempt
                    self.gemini_store.record_processing_attempt(result)
                    
                except Exception as e:
                    failed += 1
                    logger.error(f"Error processing {item['source_path']}: {e}")
        
        total_processed = successful + failed
        success_rate = (successful / total_processed * 100) if total_processed > 0 else 0
        
        logger.info(f"Processing complete: {successful} successful, {failed} failed")
        logger.info(f"Success rate: {success_rate:.1f}%")
        
        return {
            'total': total_processed,
            'successful': successful, 
            'failed': failed,
            'success_rate': success_rate
        }
    
    def add_processing_jobs_from_files(self, pdf_dir: str = None, syllabus_md_dir: str = None, 
                                     course_page_md_dir: str = None) -> int:
        """Add processing jobs from file directories"""
        jobs_added = 0
        
        # Add PDF jobs
        if pdf_dir and Path(pdf_dir).exists():
            pdf_files = list(Path(pdf_dir).glob("*.pdf"))
            for pdf_file in pdf_files:
                if self.gemini_store.add_processing_job(str(pdf_file), "pdf"):
                    jobs_added += 1
            logger.info(f"Added {len(pdf_files)} PDF processing jobs")
        
        # Add syllabus markdown jobs
        if syllabus_md_dir and Path(syllabus_md_dir).exists():
            md_files = list(Path(syllabus_md_dir).glob("*.md"))
            for md_file in md_files:
                if self.gemini_store.add_processing_job(str(md_file), "syllabus_md"):
                    jobs_added += 1
            logger.info(f"Added {len(md_files)} syllabus markdown processing jobs")
        
        # Add course page markdown jobs
        if course_page_md_dir and Path(course_page_md_dir).exists():
            md_files = list(Path(course_page_md_dir).glob("*.md"))
            for md_file in md_files:
                if self.gemini_store.add_processing_job(str(md_file), "course_page_md"):
                    jobs_added += 1
            logger.info(f"Added {len(md_files)} course page markdown processing jobs")
        
        return jobs_added
    
    def get_processing_statistics(self) -> Dict:
        """Get comprehensive processing statistics"""
        return self.gemini_store.get_processing_statistics()


# ----- Main Function -----

def main():
    """Main entry point for database Gemini processor"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Process course content using database-integrated Gemini API')
    parser.add_argument('--database', default="data/csexpert.db",
                       help='Database file path (default: data/csexpert.db)')
    parser.add_argument('--api-key', help='Gemini API key (default: from GEMINI_API_KEY env var)')
    parser.add_argument('--model', default=DEFAULT_MODEL_NAME, help=f'Gemini model name (default: {DEFAULT_MODEL_NAME})')
    
    # Content directories
    parser.add_argument('--pdf-dir', default="data/syllabi_pdfs",
                       help='Directory containing PDF files')
    parser.add_argument('--syllabus-md-dir', default="data/firecrawl_courses_syllabus",
                       help='Directory containing syllabus markdown files')
    parser.add_argument('--course-page-md-dir', default="data/course_pages",
                       help='Directory containing course page markdown files')
    
    # Processing options
    parser.add_argument('--content-type', choices=['pdf', 'syllabus_md', 'course_page_md'],
                       help='Process only specific content type')
    parser.add_argument('--batch-size', type=int, default=DEFAULT_BATCH_SIZE,
                       help=f'Processing batch size (default: {DEFAULT_BATCH_SIZE})')
    parser.add_argument('--add-jobs', action='store_true',
                       help='Add processing jobs from directories')
    parser.add_argument('--stats', action='store_true',
                       help='Show processing statistics only')
    
    args = parser.parse_args()
    
    try:
        logger.info("Starting Database Gemini Processor")
        
        # Initialize processor
        processor = DatabaseGeminiProcessor(
            database_path=args.database,
            model_name=args.model,
            api_key=args.api_key
        )
        
        if args.stats:
            # Show statistics only
            stats = processor.get_processing_statistics()
            logger.info(f"Processing statistics: {json.dumps(stats, indent=2, default=str)}")
            return
        
        if args.add_jobs:
            # Add processing jobs from directories
            jobs_added = processor.add_processing_jobs_from_files(
                pdf_dir=args.pdf_dir if Path(args.pdf_dir).exists() else None,
                syllabus_md_dir=args.syllabus_md_dir if Path(args.syllabus_md_dir).exists() else None,
                course_page_md_dir=getattr(args, 'course_page_md_dir', None) if hasattr(args, 'course_page_md_dir') and Path(getattr(args, 'course_page_md_dir')).exists() else None
            )
            logger.info(f"Added {jobs_added} processing jobs to database")
        
        # Process pending content
        results = processor.process_pending_content(
            content_type=args.content_type,
            batch_size=args.batch_size
        )
        
        logger.info("\n=== PROCESSING COMPLETE ===")
        logger.info(f"✓ Total: {results['total']} items processed")
        logger.info(f"✓ Successful: {results['successful']} courses")
        logger.info(f"✓ Failed: {results['failed']} items")
        logger.info(f"✓ Success rate: {results['success_rate']:.1f}%")
        
        # Show final statistics
        final_stats = processor.get_processing_statistics()
        logger.info(f"✓ Final statistics: {json.dumps(final_stats['cost_analysis'], indent=2, default=str)}")
        
    except Exception as e:
        logger.error(f"Processing failed: {e}")
        return False
    
    return True


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)