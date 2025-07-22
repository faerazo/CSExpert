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

#### 1. **programs**
Academic program information
- `program_code` (UNIQUE) - N2COS, N1SOF, etc.
- `program_name`, `program_type`, `department`

#### 2. **courses**
Main course entity with version support
- `course_code` + `version_id` (UNIQUE together)
- `course_title`, `swedish_title`, `department`, `credits`, `cycle`
- Metadata fields: `study_form`, `field_of_education`, `main_field_of_study`, `term`
- Administrative: `is_current`, `is_replaced`, `replaced_by_course_id`, `replacing_course_code`
- Quality metrics: `content_completeness_score`, `data_quality_score`

#### 3. **course_sections**
Structured course content
- `course_id`, `section_name`, `section_content`
- `word_count`

#### 4. **course_program_mapping**
Links courses to programs (many-to-many)

#### 5. **course_details**
Administrative information (tuition fees, duration, application codes)

#### 6. **data_quality_issues**
Tracks data problems for maintenance

#### 7. **course_version_history**
Tracks course changes over time

### Key Indexes
- Course lookups: `idx_courses_code`, `idx_courses_current`
- RAG optimization: `idx_courses_metadata`, `idx_courses_field`
- Quality tracking: `idx_courses_quality_score`

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
from database.models import Course, Program, CourseSection

# Query courses
current_courses = session.query(Course).filter(
    Course.is_current == True,
    Course.cycle == 'Second cycle'
).all()

# Create new course
course = Course(
    course_code='DIT999',
    course_title='Advanced Topics in CS',
    department='Computer Science',
    credits=7.5,
    cycle='Second cycle'
)
session.add(course)
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

## Data Import Pipeline

1. URL extraction to database
2. PDF downloads with tracking
3. HTML scraping with storage
4. Gemini AI processing for content extraction
5. Automated duplicate management

## Best Practices

### Connection Management
- Always use context managers
- Use transactions for multi-statement operations

### Data Quality
- Validate before insertion
- Monitor data_quality_issues table
- Maintain high completeness scores

### Performance
- Use appropriate indexes
- Batch operations when possible
- Regular VACUUM for optimization

## Testing

Run the test suite:
```bash
python database/test_connection_manager.py
```