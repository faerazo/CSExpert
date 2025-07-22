# CSExpert Database Module

## Overview

The CSExpert database module provides a SQLite database system for managing academic course information from the University of Gothenburg. It handles course metadata, program relationships, content sections, and data quality tracking, optimized for RAG (Retrieval-Augmented Generation) and vector embedding applications.

## Key Components

```
database/
├── connection_manager.py      # Database connection pooling
├── models.py                 # SQLAlchemy ORM models
├── database_initializer.py   # Schema creation and setup
└── schema.sql               # Database schema definition
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

## Course Replacement System

The database tracks course replacements through a post-processing system:

1. **During Import**: The `replacing_course_code` field is populated when a course indicates it replaces another
2. **Post-Processing**: After all courses are imported, the system:
   - Builds a mapping of all replacements
   - Updates replaced courses with `is_current = FALSE` and `is_replaced = TRUE`
   - Populates `replaced_by_course_codes` with comma-separated list of new course codes
   - Handles multiple replacements (e.g., DIT002 replaced by both DIT003 and TIA009)

Example:
- DIT002 is replaced by DIT003
- DIT003 has `replacing_course_code = 'DIT002'`
- After processing, DIT002 has `replaced_by_course_codes = 'DIT003'` and `is_current = FALSE`

## Best Practices

### Data Integrity
- Always validate course codes and credits before insertion
- Use the language_standards table for consistent language values
- Run course replacement processing after all courses are imported

### Performance
- Use indexed fields for queries when possible
- Batch section insertions for better performance
- Regular VACUUM for SQLite optimization

### Content Processing
- Keep metadata fields (in courses table) separate from details
- Store large text content in course_sections
- Update completeness scores after adding sections

## Views

The database includes several helpful views:
- `v_current_courses` - All current courses with aggregated data
- `v_course_quality_summary` - Department-level quality metrics
- `v_program_statistics` - Program course counts and statistics

## Testing

Run the test suite:
```bash
python database/test_connection_manager.py
```