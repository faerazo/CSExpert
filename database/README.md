# CSExpert Database Module

## Overview

The CSExpert database module provides a SQLite database system for managing academic course information from the University of Gothenburg. It handles course metadata, program relationships, content sections, and data quality tracking, optimized for RAG (Retrieval-Augmented Generation) and vector embedding applications.

## Key Components

```
database/
├── connection_manager.py      # Database connection pooling and management
├── models.py                 # SQLAlchemy ORM models for all tables
├── database_initializer.py   # Schema creation and initial data setup
├── schema.sql               # Complete database schema definition
└── test_connection_manager.py # Connection manager test suite
```

## Database Schema

### Core Tables

#### 1. **language_standards**
Language normalization lookup table
- `standard_code` - EN, SV, EN,SV, etc.
- `display_name` - Human-readable language name
- `original_variations` - JSON array of original text variations

#### 2. **programs**
Academic program information
- `program_code` (UNIQUE) - N2COS, N1SOF, etc.
- `program_name`, `program_type`, `department`
- `description` - Program description

#### 3. **courses**
Main course entity
- **Identity**: `course_code` (UNIQUE)
- **Basic Info**: `course_title`, `swedish_title`, `department`, `credits`, `cycle`
- **Language**: `language_of_instruction_id` (FK to language_standards)
- **Metadata** (for RAG/search): 
  - `content_type`, `study_form`, `field_of_education`
  - `main_field_of_study`, `specialization`, `term`
- **Administrative**: 
  - `confirmation_date`, `valid_from_date`
  - `is_current`, `is_replaced`, `replaced_by_course_codes`
  - `replacing_course_code`
- **Quality**: `content_completeness_score`, `data_quality_score`
- **Processing**: `processing_method`

#### 4. **course_sections**
Structured course content for embeddings
- `course_id` (FK), `section_name`, `section_content`
- `character_count` - Automatically calculated (includes spaces)

#### 5. **course_program_mapping**
Many-to-many relationship between courses and programs
- `course_id`, `program_id`
- `is_primary` - Indicates primary program association

#### 6. **course_details**
Course-specific administrative information (not for embeddings)
- `course_id` (PK, FK to courses)
- `tuition_fee` - Fee amount as decimal
- `duration` - Date ranges like "24 Mar 2025 - 8 Jun 2025"
- `application_period` - "15 October - 15 January"
- `application_code` - Administrative codes like "GU-86092"
- `page_last_modified` - Last modification date from course page

#### 7. **data_quality_issues**
Data quality tracking and monitoring
- `course_id`, `issue_type`, `issue_description`
- `severity` - low, medium, high
- `is_resolved`, `resolution_notes`
- `created_at`, `resolved_at`

#### 8. **course_version_history**
Version control and change tracking
- `course_id`, `change_type`
- `previous_version_id`
- `changes_summary`, `changed_fields` (JSON)

### Processing Tables

These tables manage the scraping and AI processing workflow:

#### 9. **extraction_urls**
URL discovery and tracking
- `url`, `url_type` - Discovered URLs and their types (course_page, syllabus, program_syllabus)
- `course_code` - Associated course code
- `source_search_url` - Original search page
- `status` - Processing status (pending, success, failed)

#### 10. **pdf_downloads** 
PDF download tracking and management
- `extraction_url_id`, `course_code`, `original_url`
- `file_path` - Local storage path for downloaded PDF
- `file_size`, `checksum` - File validation data
- `status` - Download status with retry tracking
- `download_time` - Performance metrics

#### 11. **html_scrapes**
HTML scraping results and storage
- `extraction_url_id`, `course_code`, `original_url` 
- `markdown_file_path` - Converted markdown content location
- `content_length` - Content size for validation
- `status` - Scraping status with error handling
- `scraping_time`, `retry_count` - Performance and reliability tracking

#### 12. **gemini_processing_jobs**
AI processing queue and results
- `file_path`, `content_type` - Input file and processing type (pdf, syllabus_md, course_page_md)
- `course_code` - Extracted course identifier
- `processing_status` - Status tracking (pending, processing, success, failed)
- `error_message` - Detailed error information for debugging
- `retry_count`, `processing_time` - Reliability and performance metrics

### Key Indexes

**Course Lookups**
- `idx_courses_code` - Fast course code lookups
- `idx_courses_current` - Current courses filtering
- `idx_courses_department` - Department-based queries

**RAG/Search Optimization**
- `idx_courses_metadata` - Cycle and study form filtering
- `idx_courses_field` - Field of education searches
- `idx_courses_term` - Term-based queries
- `idx_courses_content_type` - Content type filtering

**Performance & Quality**
- `idx_courses_quality_score` - Quality monitoring
- `idx_courses_dates` - Date-based queries
- `idx_courses_updated` - Recent changes tracking
- `idx_course_sections_course` - Section lookups
- `idx_course_program_mapping_*` - Program relationships

**Processing Workflow**
- `idx_extraction_urls_status` - URL processing tracking
- `idx_gemini_processing_jobs_status` - AI processing queue management
- `idx_pdf_downloads_course_code` - Course-based PDF lookups
- `idx_html_scrapes_course_code` - Course-based content lookups

## Usage Examples

### Connection Manager
```python
from database.connection_manager import get_database_manager

db_manager = get_database_manager()

# Execute queries
with db_manager.get_connection() as conn:
    cursor = conn.execute("SELECT * FROM courses WHERE is_current = 1")
    courses = cursor.fetchall()
```

### ORM Models
```python
from database.models import Course, Program, CourseSection, CourseDetails
from database.models import create_database_session

# Create session
Session = create_database_session()
session = Session()

# Query current courses
current_courses = session.query(Course).filter(
    Course.is_current == True,
    Course.cycle == 'Second cycle'
).all()

# Create course with details
course = Course(
    course_code='DIT999',
    course_title='Advanced Topics in CS',
    department='Computer Science',
    credits=7.5,
    cycle='Second cycle',
    study_form='Campus'
)
session.add(course)
session.flush()

# Add course details
details = CourseDetails(
    course_id=course.id,
    tuition_fee=150000,
    duration='24 Mar 2025 - 8 Jun 2025',
    application_code='GU-86092'
)
session.add(details)
session.commit()
```

### Database Initialization
```python
from database.database_initializer import DatabaseInitializer

initializer = DatabaseInitializer("data/csexpert.db")
success = initializer.initialize_database(drop_existing=True)
```

## Active Programs

Only these program codes are valid in the system:
- **N2COS** - Computer Science Master's Programme
- **N2SOF** - Software Engineering and Management Master's Programme
- **N1SOF** - Software Engineering and Management Bachelor's Programme
- **N2GDT** - Game Design Technology Master's Programme

## Post-Processing Pipeline

After all content is processed, the system runs automatic post-processing to ensure data quality and consistency:

### 1. Course Replacement System
Tracks course replacements through automated processing:
- **During Import**: The `replacing_course_code` field is populated when a course indicates it replaces another
- **Post-Processing**: After all courses are imported, the system:
  - Builds a mapping of all replacements
  - Updates replaced courses with `is_current = FALSE` and `is_replaced = TRUE`
  - Populates `replaced_by_course_codes` with comma-separated list of new course codes
  - Handles multiple replacements (e.g., DIT002 replaced by both DIT003 and TIA009)

Example:
- DIT002 is replaced by DIT003
- DIT003 has `replacing_course_code = 'DIT002'`
- After processing, DIT002 has `replaced_by_course_codes = 'DIT003'` and `is_current = FALSE`

### 2. Data Quality Standardization
Automatic data cleanup ensures consistency:

#### Department Name Standardization
- Ensures all department names have "Department of" prefix
- Converts variations: "Dep of Applied Information Technology" → "Department of Applied Information Technology"
- Standardizes: "Computer Science and Engineering" → "Department of Computer Science and Engineering"

#### Specialization Code Cleaning  
- Extracts only 3-character specialization codes (AXX, G1F, A1E, etc.)
- Removes descriptive text: "AXX, Second cycle, in-depth level of the course cannot be classified" → "AXX"

#### Empty String Standardization
- Converts all empty strings ('') to NULL across the entire database
- Ensures consistent empty value representation for better data quality and query reliability
- Affects all nullable text and varchar columns in all tables

### 3. Processing Workflow
The complete processing pipeline follows this sequence:
1. **URL Extraction** → `extraction_urls` table populated
2. **PDF Downloads** → `pdf_downloads` table tracks file acquisition 
3. **HTML Scraping** → `html_scrapes` table stores converted content
4. **AI Processing** → `gemini_processing_jobs` manages content extraction
5. **Post-Processing** → Data standardization and course relationship processing
6. **Final Validation** → Quality scores updated, statistics generated

## Best Practices

### Data Integrity
- Always validate course codes and credits before insertion
- Use the language_standards table for consistent language values
- Trust the post-processing pipeline for data standardization
- Course replacement processing runs automatically after content import

### Performance
- Use indexed fields for queries when possible
- Batch section insertions for better performance
- Regular VACUUM for SQLite optimization

### Content Processing
- Keep metadata fields (in courses table) separate from details
- Store large text content in course_sections with automatic character_count
- Completeness scores update automatically via database triggers
- Processing status tracking prevents duplicate work and enables resume functionality

## Views

The database includes several helpful views:
- `v_current_courses` - All current courses with aggregated data and section counts
- `v_course_quality_summary` - Department-level quality metrics and completion scores
- `v_program_statistics` - Program course counts, credit averages, and cycle distribution

## Testing

Run the test suite:
```bash
python database/test_connection_manager.py
```