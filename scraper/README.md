# CSExpert Scraper Module

## Quick Start

```bash
# From project root directory
source venv/bin/activate  # Required - scraper needs virtual environment
python -m scraper.database_scraper_orchestrator
```

## Overview

The CSExpert scraper is a database-driven pipeline that extracts academic course information from the University of Gothenburg. It discovers URLs, downloads PDFs, scrapes HTML content, and uses Google Gemini AI to extract structured course data.

**Pipeline**: URL Extraction → PDF Download → HTML Scraping → AI Processing → Duplicate Management

## Components

### 1. **database_scraper_orchestrator.py**
Main coordinator that runs all phases in sequence. Automatically resumes from last incomplete phase.

### 2. **database_url_extractor.py**
Discovers course URLs from the university website for prefixes: DIT, MSG, MSA, MMA, TIA, LT

### 3. **database_pdf_downloader.py**
Downloads PDF syllabi to `data/syllabi_pdfs/` with retry handling

### 4. **database_html_scraper.py**
Scrapes HTML content using WebDriver pool, converts to markdown, saves to:
- `data/syllabi_pages/` - Web-based syllabi
- `data/course_pages/` - Course overview pages

### 5. **database_gemini_processor.py**
AI-powered content extraction with three processing modes:
- `pdf` - PDF syllabi
- `syllabus_md` - Web syllabus pages
- `course_page_md` - Course overview pages

### 6. **database_duplicate_manager.py**
Detects and resolves duplicate courses, keeping highest quality version

### 7. **webdriver_pool.py**
Manages Chrome WebDriver instances for efficient web scraping

## Configuration

### Environment Variables (.env)
```bash
GEMINI_API_KEY=your-api-key-here
DATABASE_PATH=data/csexpert.db  # Optional
```

### Gemini API Limits (Tier 1)
- 1000 requests/minute
- 10,000 requests/day
- Configured delay: 0.06 seconds between requests

### Orchestrator Configuration
```python
config = OrchestrationConfig(
    max_concurrent_downloads=6,      # PDF downloads
    max_concurrent_html_scrapers=6,  # HTML scraping
    max_concurrent_processing=10,    # Gemini workers
    batch_size=100,                  # Tier 1 optimized
)
```

## Usage

### Prerequisites
1. Set up environment: `./setup.sh` (first time only)
2. Activate virtual environment: `source venv/bin/activate`
3. Ensure `.env` file exists with API key

### Running Individual Components
```python
from scraper.database_url_extractor import DatabaseURLExtractor
from scraper.database_gemini_processor import DatabaseGeminiProcessor

# Extract URLs only
extractor = DatabaseURLExtractor()
extractor.extract_all_course_urls()

# Process specific file
processor = DatabaseGeminiProcessor()
result = processor.process_single_content("path/to/file.pdf", "pdf")
```

### Resume from Specific Phase
```python
from scraper.database_scraper_orchestrator import DatabaseScraperOrchestrator, ProcessingPhase

orchestrator = DatabaseScraperOrchestrator()
orchestrator.run_pipeline(start_phase=ProcessingPhase.HTML_SCRAPING)
```

## Database Tables

- `extraction_urls` - Discovered URLs
- `pdf_downloads` - PDF download tracking
- `html_scrapes` - HTML content storage
- `gemini_processing_jobs` - Processing queue and results
- `courses` - Final course records
- `course_sections` - Course content
- `course_program_mapping` - Program relationships

## Processing Order

Files are processed in this specific order to ensure data quality:
1. **Phase 1**: PDF files from `/data/syllabi_pdfs/`
2. **Phase 2**: Syllabus pages from `/data/syllabi_pages/`
3. **Phase 3**: Course pages from `/data/course_pages/`

## Troubleshooting

### Import Errors
**Solution**: Activate virtual environment
```bash
source venv/bin/activate
which python  # Should show venv path
```

### Gemini API Errors
- Check API key in `.env` file
- Verify daily quota (10,000 requests)
- Check Google Cloud Console for usage

### WebDriver Issues
```bash
# Update Chrome
sudo apt update && sudo apt install google-chrome-stable
# Clear driver cache
rm -rf ~/.wdm/
```

### Database Locked
- Ensure only one orchestrator instance is running
- Check for zombie processes: `ps aux | grep python`

## Monitoring

Check progress:
```sql
-- Pipeline status
SELECT phase, COUNT(*) FROM pipeline_status GROUP BY phase;

-- Processing jobs
SELECT processing_status, COUNT(*) 
FROM gemini_processing_jobs 
GROUP BY processing_status;
```

Log file: `database_scraper.log`

## Best Practices

1. **Always use virtual environment** - Scraper will fail without it
2. **Monitor API costs** - Track usage in Google Cloud Console
3. **Regular backups** - Backup database before major runs
4. **Check disk space** - PDFs and content require ~1GB storage