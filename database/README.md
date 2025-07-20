# CSExpert Database Module

## Overview

The CSExpert database module provides a robust, production-ready SQLite database system for managing academic course information from the University of Gothenburg. This module handles course metadata, program relationships, content sections, and data quality tracking with optimized schema design for RAG (Retrieval-Augmented Generation) and vector embedding applications.

## Architecture

### Design Philosophy

- **Separation of Concerns**: Core metadata separated from administrative details
- **Version Support**: Built-in course versioning for historical tracking
- **Data Quality Focus**: Automated quality scoring and issue tracking
- **Performance Optimized**: Strategic indexes, connection pooling, and query optimization
- **RAG/Embedding Ready**: Schema designed for efficient vector embedding generation

### Key Components

```
database/
├── connection_manager.py      # Database connection pooling and management
├── models.py                 # SQLAlchemy ORM models with business logic
├── database_initializer.py   # Schema creation and initial data setup
├── test_connection_manager.py # Comprehensive test suite
└── schema.sql               # Complete database schema definition
```

## Database Schema

### Core Tables

#### 1. **programs**
Stores academic program information.
```sql
- id (PRIMARY KEY)
- program_code (UNIQUE) - e.g., 'N2COS', 'N1SOF'
- program_name - Full program name
- program_type - 'bachelor', 'master', 'phd', 'invalid'
- department
- description
```

#### 2. **language_standards**
Normalized language instruction options.
```sql
- id (PRIMARY KEY)
- standard_code - 'EN', 'SV', 'EN,SV'
- display_name - Human-readable format
- original_variations - JSON array of original text variations
```

#### 3. **courses**
Main course entity with version support.
```sql
- id (PRIMARY KEY)
- course_code + version_id (UNIQUE together)
- course_title, swedish_title
- department, credits, cycle
- language_of_instruction_id (FK → language_standards)

# Metadata fields (for RAG/embeddings):
- content_type, study_pace, study_form
- time_schedule, field_of_education
- main_field_of_study, specialization, term

# Administrative fields:
- confirmation_date, valid_from_date, valid_to_date
- is_current, is_replaced, replaced_by_course_id
- content_completeness_score, data_quality_score
- source_document, processing_method
```

#### 4. **course_sections**
Structured course content storage.
```sql
- id (PRIMARY KEY)
- course_id (FK → courses)
- section_name + course_id (UNIQUE together)
- section_content
- section_order, word_count
```

#### 5. **course_program_mapping**
Many-to-many relationship between courses and programs.
```sql
- id (PRIMARY KEY)
- course_id + program_id (UNIQUE together)
- is_primary - Indicates primary program
```

#### 6. **course_details**
Administrative/practical information (excluded from embeddings).
```sql
- course_id (PRIMARY KEY, FK → courses)
- tuition_fee, duration, application_period
- iteration, location, application_code
- additional_info (JSON) - Flexible storage
```

#### 7. **data_quality_issues**
Tracks data quality problems for maintenance.
```sql
- id (PRIMARY KEY)
- course_id (FK → courses)
- issue_type, issue_description
- severity ('low', 'medium', 'high')
- is_resolved, resolution_notes
- created_at, resolved_at
```

#### 8. **course_version_history**
Tracks course changes over time.
```sql
- id (PRIMARY KEY)
- course_id (FK → courses)
- change_type, previous_version_id
- changes_summary, changed_fields (JSON)
```

### Indexes for Performance

```sql
# Course lookups
idx_courses_code, idx_courses_current, idx_courses_department

# RAG optimization
idx_courses_metadata, idx_courses_field, idx_courses_term

# Relationships
idx_course_program_mapping_course/program

# Quality tracking
idx_courses_quality_score, idx_data_quality_issues_severity
```

### Automated Triggers

1. **update_course_completeness_score** - Automatically calculates content completeness
2. **validate_credits** - Validates against standard GU credit values
3. **log_course_changes** - Tracks course modifications
4. **update_section_word_count** - Maintains word count statistics

### Views for Common Queries

- **v_current_courses** - Active courses with all relationships
- **v_course_quality_summary** - Department-level quality metrics
- **v_program_statistics** - Program course counts and statistics

## Usage Examples

### Connection Manager

```python
from database.connection_manager import get_database_manager

# Get database manager (singleton)
db_manager = get_database_manager()

# Execute queries
with db_manager.get_connection() as conn:
    cursor = conn.execute("SELECT * FROM courses WHERE is_current = 1")
    courses = cursor.fetchall()

# Use transaction context
with db_manager.transaction() as conn:
    conn.execute("INSERT INTO programs ...")
    # Automatically commits on success, rolls back on error
```

### ORM Models

```python
from database.models import Course, Program, CourseSection
from sqlalchemy.orm import sessionmaker

# Create session
Session = sessionmaker(bind=engine)
session = Session()

# Query courses
current_courses = session.query(Course).filter(
    Course.is_current == True,
    Course.cycle == 'Second cycle'
).all()

# Create new course with sections
course = Course(
    course_code='DIT999',
    course_title='Advanced Topics in CS',
    department='Computer Science',
    credits=7.5,
    cycle='Second cycle'
)

section = CourseSection(
    course=course,
    section_name='Course content',
    section_content='This course covers...'
)

session.add(course)
session.commit()
```

### Database Initialization

```python
from database.database_initializer import DatabaseInitializer

# Initialize new database
initializer = DatabaseInitializer("data/csexpert.db")
success = initializer.initialize_database(drop_existing=True)

# Get database info
db_info = initializer.get_database_info()
print(f"Tables: {db_info['table_count']}")
print(f"Schema version: {db_info['schema_version']}")
```

## Data Quality

The database system includes built-in data quality tracking through the `data_quality_issues` table, which automatically records:

- Missing required fields
- Format violations
- Non-standard values
- Content completeness issues

Quality scores are maintained at the course level through `content_completeness_score` and `data_quality_score` fields.

## Testing

Run the comprehensive test suite:

```bash
python database/test_connection_manager.py
```

Tests include:
- Basic connection functionality
- Connection pooling behavior
- Concurrent access handling
- Transaction management
- Error recovery
- Performance benchmarks
- Data integrity verification

## Best Practices

### 1. Connection Management
- Always use context managers for connections
- Let the pool handle connection lifecycle
- Use transactions for multi-statement operations

### 2. Data Quality
- Validate data before insertion
- Use the ORM validation methods
- Monitor data_quality_issues table
- Maintain high completeness scores

### 3. Performance
- Use appropriate indexes for queries
- Batch operations when possible
- Monitor connection pool statistics
- Regular VACUUM for optimization

### 4. Schema Evolution
- Version courses instead of updating
- Track changes in version_history
- Maintain backward compatibility
- Document schema changes

## Database Pragmas

The system uses optimized SQLite settings:
```sql
PRAGMA foreign_keys = ON        # Enforce referential integrity
PRAGMA journal_mode = WAL       # Write-Ahead Logging
PRAGMA synchronous = NORMAL     # Balanced performance/safety
PRAGMA cache_size = 10000       # 10MB cache
PRAGMA temp_store = MEMORY      # Memory for temp tables
PRAGMA mmap_size = 268435456    # 256MB memory-mapped I/O
```

## Data Import

All data import is handled through the database scraper orchestrator pipeline:
1. URL extraction to database
2. PDF downloads with tracking
3. HTML scraping with storage
4. Gemini AI processing for content extraction
5. Automated duplicate management

## Future Enhancements

- Full-text search optimization
- Graph-based program relationships
- Time-series course evolution tracking
- Advanced analytics views
- Backup and recovery automation