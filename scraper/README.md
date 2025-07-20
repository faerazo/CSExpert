# CSExpert Scraper Module

## ⚠️ IMPORTANT: Virtual Environment Required

**This module MUST be run within the CSExpert virtual environment.** The scraper depends on many Python packages that are installed in the project's virtual environment.

### Quick Start
```bash
# From project root directory
source venv/bin/activate  # or use ./activate.sh
python -m scraper.database_scraper_orchestrator
```

## Overview

The CSExpert scraper module implements a sophisticated, database-driven web scraping pipeline for extracting academic course information from the University of Gothenburg. This module coordinates multiple specialized components to discover, download, scrape, and process course data using AI, storing everything directly in the database with full tracking and resume capabilities.

## Architecture

### Design Principles

- **Database-First**: All state and data stored in database, no intermediate files
- **Resumable Pipeline**: Can restart from any phase based on database state
- **Resource Pooling**: Shared WebDriver instances for efficiency
- **AI-Powered Extraction**: Uses Google Gemini for intelligent content parsing
- **Tier 1 Optimization**: Configured for high-throughput API usage
- **Comprehensive Tracking**: Every operation logged in database

### Pipeline Phases

1. **URL Extraction** → 2. **PDF Download** → 3. **HTML Scraping** → 4. **AI Processing** → 5. **Duplicate Management**

## Components

### Core Pipeline Components

#### 1. **database_scraper_orchestrator.py**
Main pipeline coordinator that manages the entire scraping workflow.

**Key Features:**
- Orchestrates all phases in sequence
- Database state-driven progress tracking
- Automatic resume from last successful phase
- Concurrent processing with configurable workers
- Performance monitoring and statistics
- Tier 1 API rate limit management

**Configuration:**
```python
config = OrchestrationConfig(
    database_path="data/csexpert.db",
    max_concurrent_downloads=6,      # PDF downloads
    max_concurrent_html_scrapers=6,  # HTML scraping
    max_concurrent_processing=10,    # Gemini workers
    batch_size=100,                  # Tier 1 optimized
    gemini_delay=0.06               # 1000 RPM for Tier 1
)
```

#### 2. **database_url_extractor.py**
Discovers and extracts course URLs from the university website.

**Functionality:**
- Searches for courses by prefix (DIT, MSG, MSA, MMA, TIA, LT)
- Extracts syllabus PDF URLs
- Extracts course webpage URLs
- Extracts program URLs
- Resolves GUID-based URLs to course codes
- Stores all URLs in `extraction_urls` table

**URL Types:**
- `syllabus` - PDF syllabus documents
- `course_page` - HTML course information pages
- `program` - Program overview pages

#### 3. **database_pdf_downloader.py**
Downloads PDF syllabi with tracking and error handling.

**Features:**
- Downloads PDFs to `data/syllabi_pdfs/`
- Tracks download status in `pdf_downloads` table
- Handles retries and failures
- Validates PDF integrity
- Skips already downloaded files
- Concurrent downloads with rate limiting

#### 4. **database_html_scraper.py**
Scrapes HTML content from course and syllabus webpages.

**Capabilities:**
- Uses WebDriver pool for JavaScript rendering
- Extracts markdown content from HTML
- Handles both course pages and web-based syllabi
- Stores content in `html_scrapes` table
- Manages directories: `data/syllabi_pages/` and `data/course_pages/`

#### 5. **database_gemini_processor.py**
AI-powered content extraction using Google Gemini.

**Processing Types:**
- PDF syllabi parsing (`pdf`)
- Markdown course page extraction (`course_page_md`)
- Markdown syllabus page extraction (`syllabus_md`)

**Content Type Mapping:**
- PDFs → `pdf` → uses PDF-specific prompt
- Web syllabus pages (`url_type='syllabus'`) → `syllabus_md` → uses syllabus prompt
- Course overview pages (`url_type='course_page'`) → `course_page_md` → uses course page prompt

**Extracted Data:**
- Course metadata (title, credits, cycle, etc.)
- Course sections (content, outcomes, assessment, etc.)
- Program relationships
- Language of instruction
- Administrative details

**Features:**
- Structured prompt engineering
- JSON response parsing
- Database record creation
- Quality tracking
- Cost estimation
- Job tracking in `gemini_processing_jobs` table

#### 6. **database_duplicate_manager.py**
Detects and resolves duplicate courses in the database.

**Resolution Strategy:**
- Groups courses by code
- Compares content completeness
- Keeps highest quality version
- Archives duplicates
- Creates quality issue records
- Maintains data integrity

### Utility Components

#### 7. **webdriver_pool.py**
Manages a pool of Chrome WebDriver instances for efficient web scraping.

**Features:**
- Connection pooling pattern
- Headless Chrome configuration
- Context manager support
- Automatic driver lifecycle management
- Error recovery
- Thread-safe operations

**Usage:**
```python
from scraper.webdriver_pool import get_global_pool

pool = get_global_pool()
with pool.get_driver() as driver:
    driver.get("https://example.com")
    # Use driver...
```

## Pipeline Workflow

### 1. URL Extraction Phase
```
Search GU website → Extract URLs → Store in extraction_urls table
```

### 2. PDF Download Phase
```
Read syllabus URLs → Download PDFs → Track in pdf_downloads table
```

### 3. HTML Scraping Phase
```
Read webpage URLs → Scrape with WebDriver → Convert to Markdown → Store in html_scrapes table
```

### 4. AI Processing Phase
```
Read PDFs/Markdown → Send to Gemini API → Parse response → Create database records
```

### 5. Duplicate Management Phase
```
Analyze courses → Detect duplicates → Resolve conflicts → Update database
```

## Configuration

### Environment Variables (.env)
```bash
# Google Gemini API
GEMINI_API_KEY=your-api-key-here

# Optional overrides
DATABASE_PATH=data/csexpert.db
LOG_LEVEL=INFO
```

### Tier 1 API Limits
- **Requests Per Minute (RPM)**: 1000
- **Requests Per Day (RPD)**: 10,000  
- **Tokens Per Minute (TPM)**: 1,000,000
- **Configured Delay**: 0.06 seconds between requests

## Usage

### Prerequisites
1. **Set up the environment first:**
   ```bash
   # If not already done, run from project root:
   ./setup.sh  # Complete setup including virtual environment
   # OR
   ./dev-setup.sh  # Just Python packages if you have Chrome installed
   ```

2. **Activate the virtual environment:**
   ```bash
   # From project root directory
   source venv/bin/activate
   # OR use the helper script:
   ./activate.sh
   ```

3. **Verify environment is active:**
   ```bash
   which python  # Should show: /path/to/CSExpert/venv/bin/python
   python -c "import selenium, sqlalchemy, google.generativeai; print('✓ All packages available')"
   ```

### Running the Complete Pipeline
```bash
# ALWAYS from within activated virtual environment
cd /path/to/CSExpert  # Go to project root
source venv/bin/activate  # Activate environment
python -m scraper.database_scraper_orchestrator
```

### Running Individual Components
```python
# Make sure virtual environment is activated first!
from scraper.database_url_extractor import DatabaseURLExtractor
from scraper.database_gemini_processor import DatabaseGeminiProcessor

# Extract URLs only
extractor = DatabaseURLExtractor()
result = extractor.extract_all_course_urls()

# Process specific content
processor = DatabaseGeminiProcessor()
result = processor.process_single_content("path/to/file.pdf", "pdf")
```

### Monitoring Progress
```sql
-- Check pipeline status
SELECT phase, COUNT(*) FROM pipeline_status GROUP BY phase;

-- Monitor URL extraction
SELECT url_type, COUNT(*) FROM extraction_urls GROUP BY url_type;

-- Track processing jobs
SELECT processing_status, COUNT(*) 
FROM gemini_processing_jobs 
GROUP BY processing_status;

-- View courses created
SELECT COUNT(*) FROM courses WHERE created_at > date('now', '-1 day');
```

## Error Handling and Recovery

### Automatic Resume
The orchestrator automatically resumes from the last incomplete phase:
```python
# Checks database state on startup
current_phase = self._get_current_phase()
logger.info(f"Resuming from phase: {current_phase}")
```

### Error Recovery
- Failed downloads are retried up to 3 times
- HTML scraping failures are logged and skipped
- Gemini API errors trigger exponential backoff
- Database transactions ensure data consistency

### Manual Recovery
```python
# Resume from specific phase
orchestrator = DatabaseScraperOrchestrator(config)
orchestrator.run_pipeline(start_phase=ProcessingPhase.HTML_SCRAPING)
```

## Database Integration

### Tables Used
- `extraction_urls` - Discovered URLs with type classification
- `pdf_downloads` - PDF download tracking
- `html_scrapes` - HTML content storage
- `gemini_processing_jobs` - AI processing queue and source tracking
- `courses` - Final course records (no longer contains source_document)
- `course_sections` - Course content sections
- `course_details` - Administrative details (tuition, dates, location)
- `course_program_mapping` - Program relationships
- `data_quality_issues` - Quality tracking

### Data Flow
```
Web → extraction_urls → pdf_downloads/html_scrapes → gemini_processing_jobs → courses
```

**Note**: Source document tracking is maintained through `gemini_processing_jobs.source_path`, not in the courses table.

## Monitoring and Logging

### Log Files
- `database_scraper.log` - Main orchestrator logs
- Console output for real-time monitoring

### Log Levels
```python
logging.basicConfig(level=logging.INFO)  # Normal operation
logging.basicConfig(level=logging.DEBUG) # Detailed debugging
```

### Key Metrics
- URLs extracted per type
- Download success rates
- Processing times per phase
- Gemini API costs
- Duplicate resolution stats

## Best Practices

1. **Always use venv**: 
   - Never run the scraper without activating the virtual environment
   - The scraper will fail with import errors if venv is not active
   - Use `./activate.sh` for quick activation

2. **Monitor API usage**: Track Gemini API costs and limits
3. **Regular backups**: Backup database before major runs
4. **Check disk space**: PDFs and scraped content require storage
5. **Review quality issues**: Check `data_quality_issues` table regularly

### Virtual Environment Checklist
- [ ] Virtual environment is activated (`source venv/bin/activate`)
- [ ] Running from project root directory
- [ ] Python shows venv path (`which python`)
- [ ] All packages import successfully
- [ ] .env file exists with API keys

## Troubleshooting

### Common Issues

1. **Import Errors (ModuleNotFoundError)**
   - **Cause**: Virtual environment not activated
   - **Solution**: 
     ```bash
     cd /path/to/CSExpert
     source venv/bin/activate  # or ./activate.sh
     ```
   - **Verify**: `which python` should show venv path

2. **Gemini API quota exceeded**
   - Check API usage in Google Cloud Console
   - Verify Tier 1 limits are configured
   - Ensure API key is loaded from .env

3. **WebDriver failures**
   - Update Chrome: `sudo apt update && sudo apt install google-chrome-stable`
   - Clear driver cache: `rm -rf ~/.wdm/`
   - Ensure venv is active (webdriver-manager is installed there)

4. **Database locked errors**
   - Ensure only one orchestrator instance runs
   - Check for zombie processes: `ps aux | grep python`

5. **Memory issues**
   - Reduce concurrent workers in config
   - Monitor with: `watch -n 1 free -h`

6. **"Command not found" errors**
   - Ensure running from project root
   - Activate virtual environment first
   - Use `python -m` for module execution

7. **Unknown Program Code Warnings**
   - **Cause**: Course belongs to program not in VALID_PROGRAM_CODES
   - **Current valid codes**: N2COS, N2SOF, N1SOF, N2ADS, N2GDT, N1COS, N2MAT, N1SEM, N1SOB, N2SOM, N1MAT, ISOFK, N2SEM, N2CMN, H2MLT, H2LTG
   - **Solution**: Add legitimate codes to VALID_PROGRAM_CODES in database_gemini_processor.py

8. **Empty String to Float Conversion Errors**
   - **Cause**: Empty strings passed to numeric database fields
   - **Solution**: Already handled - empty strings are converted to NULL
   - **Note**: Formatted numbers are parsed (e.g., "SEK 15,000" → 15000)

## Performance Optimization

- **Concurrent Processing**: Adjust worker counts based on system resources
- **Batch Sizes**: Larger batches reduce overhead but increase memory usage  
- **Database Indexes**: Ensure all indexes are present (check schema.sql)
- **Connection Pooling**: Both database and WebDriver connections are pooled

## Recent Improvements

- **Content Type Alignment**: Orchestrator now correctly maps URL types to processing prompts
- **Source Tracking**: Moved from courses table to gemini_processing_jobs for better tracking
- **Program Validation**: Expanded support for 16 program codes with proper validation
- **Data Handling**: Improved parsing of empty strings and formatted numbers
- **Credits Validation**: Removed restrictive validation, now accepts any positive value
- **Cleanup**: Removed all obsolete firecrawl references

## Future Enhancements

- Incremental updates (only new/changed courses)
- Multi-university support
- Advanced duplicate detection algorithms
- Real-time monitoring dashboard
- Webhook notifications for completion