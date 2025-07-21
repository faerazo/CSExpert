-- CSExpert Database Schema
-- Production SQLite schema optimized for RAG/embeddings with proper metadata separation
-- Generated from comprehensive analysis and metadata optimization
-- Version: 2.0
-- Date: 2025-07-20

-- Enable foreign key constraints
PRAGMA foreign_keys = ON;

-- Migration: Remove old Firecrawl table (replaced by html_scrapes)
DROP TABLE IF EXISTS firecrawl_scrapes;

-- Core Programs table - must be created first for foreign key references
CREATE TABLE programs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    program_code VARCHAR(10) UNIQUE NOT NULL,
    program_name TEXT NOT NULL,
    program_type VARCHAR(20) CHECK (program_type IN ('bachelor', 'master', 'phd', 'invalid')) NOT NULL,
    department VARCHAR(100),
    description TEXT,
    created_at TIMESTAMP DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now')),
    updated_at TIMESTAMP DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now'))
);

-- Language standards lookup table for normalization
CREATE TABLE language_standards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    standard_code VARCHAR(10) NOT NULL, -- EN, SV, EN,SV etc.
    display_name VARCHAR(50) NOT NULL,
    original_variations TEXT, -- JSON array of original variations
    created_at TIMESTAMP DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now'))
);

-- Main courses table with version support and optimized metadata for RAG/embeddings
CREATE TABLE courses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_code VARCHAR(10) NOT NULL,
    version_id INTEGER DEFAULT 1,
    course_title TEXT NOT NULL,
    swedish_title TEXT NULL,
    department VARCHAR(100) NOT NULL,
    credits DECIMAL(4,1) NOT NULL CHECK (credits > 0),
    cycle VARCHAR(20) CHECK (cycle IN ('First cycle', 'Second cycle', 'Third cycle')) NOT NULL,
    language_of_instruction_id INTEGER REFERENCES language_standards(id),
    
    -- True metadata fields (for RAG/embeddings)
    content_type VARCHAR(20) CHECK (content_type IN ('course', 'program')) DEFAULT 'course',
    study_form VARCHAR(50), -- Campus, Online, Distance, Hybrid
    field_of_education TEXT, -- Computer Science, Mathematics
    main_field_of_study TEXT, -- Software Engineering, Data Science
    specialization TEXT, -- Requirements Engineering, Machine Learning
    term VARCHAR(50), -- Autumn 2025, Spring 2025 (parsed from valid_from_date)
    
    -- Administrative fields (not for embeddings)
    confirmation_date DATE NULL,
    valid_from_date VARCHAR(50) NULL, -- Mixed format: dates and terms like "Autumn term 2025"
    is_current BOOLEAN DEFAULT TRUE,
    is_replaced BOOLEAN DEFAULT FALSE,
    replaced_by_course_id INTEGER REFERENCES courses(id),
    replacing_course_code VARCHAR(10) NULL, -- Course code that this course replaces
    content_completeness_score DECIMAL(3,2) DEFAULT 0.0, -- 0.0 to 1.0
    data_quality_score DECIMAL(3,2) DEFAULT 0.0, -- 0.0 to 1.0
    processing_method VARCHAR(50),
    created_at TIMESTAMP DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now')),
    updated_at TIMESTAMP DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now')),
    
    -- Ensure unique course_code per version
    UNIQUE(course_code, version_id),
    
    -- Business rule: confirmation_date should be before or equal to valid_from_date (when both are dates)
    CHECK (
        confirmation_date IS NULL OR 
        valid_from_date IS NULL OR 
        NOT (confirmation_date LIKE '____-__-__' AND valid_from_date LIKE '____-__-__') OR
        confirmation_date <= DATE(SUBSTR(valid_from_date, 1, 10))
    )
);

-- Course sections for structured content storage
CREATE TABLE course_sections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    section_name VARCHAR(100) NOT NULL,
    section_content TEXT NOT NULL,
    section_order INTEGER DEFAULT 0,
    word_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now')),
    
    -- Ensure unique section names per course
    UNIQUE(course_id, section_name)
);

-- Many-to-many relationship between courses and programs
CREATE TABLE course_program_mapping (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    program_id INTEGER NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    is_primary BOOLEAN DEFAULT FALSE, -- Indicates primary program for course
    created_at TIMESTAMP DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now')),
    
    -- Prevent duplicate mappings
    UNIQUE(course_id, program_id)
);

-- Course details table for course-specific information (not metadata)
-- Separated from core course table to optimize RAG/embedding performance
CREATE TABLE course_details (
    course_id INTEGER PRIMARY KEY REFERENCES courses(id) ON DELETE CASCADE,
    
    -- Financial information
    tuition_fee DECIMAL(10,2) NULL,
    
    -- Temporal/scheduling details
    duration VARCHAR(100) NULL, -- Specific date ranges like "24 Mar 2025 - 8 Jun 2025"
    application_period VARCHAR(100) NULL, -- "15 October - 15 January"
    iteration VARCHAR(50) NULL, -- Specific semester instance
    
    -- Location/contact details
    location VARCHAR(100) NULL, -- Specific campus/building information
    
    -- Administrative codes/references
    application_code VARCHAR(50) NULL, -- "GU-86092"
    
    -- Additional flexible information
    additional_info JSON NULL, -- For truly rare/varying fields
    
    created_at TIMESTAMP DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now')),
    updated_at TIMESTAMP DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now'))
);

-- Data quality tracking
CREATE TABLE data_quality_issues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    issue_type VARCHAR(50) NOT NULL, -- 'missing_critical_field', 'unusual_credits', 'minimal_content', etc.
    issue_description TEXT NOT NULL,
    severity VARCHAR(10) CHECK (severity IN ('low', 'medium', 'high')) NOT NULL,
    is_resolved BOOLEAN DEFAULT FALSE,
    resolution_notes TEXT,
    created_at TIMESTAMP DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now')),
    resolved_at TIMESTAMP NULL
);

-- Course version history for tracking changes
CREATE TABLE course_version_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id INTEGER NOT NULL REFERENCES courses(id),
    change_type VARCHAR(20) NOT NULL, -- 'created', 'updated', 'replaced', 'archived'
    previous_version_id INTEGER,
    changes_summary TEXT,
    changed_fields JSON, -- Array of field names that changed
    created_at TIMESTAMP DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now'))
);

-- Performance indexes for common queries

-- Course lookups by code
CREATE INDEX idx_courses_code ON courses(course_code);
CREATE INDEX idx_courses_current ON courses(is_current, course_code);
CREATE INDEX idx_courses_department ON courses(department);

-- Metadata indexes for RAG optimization
CREATE INDEX idx_courses_metadata ON courses(cycle, study_form);
CREATE INDEX idx_courses_field ON courses(field_of_education, main_field_of_study);
CREATE INDEX idx_courses_term ON courses(term);
CREATE INDEX idx_courses_content_type ON courses(content_type);

-- Program relationships
CREATE INDEX idx_course_program_mapping_course ON course_program_mapping(course_id);
CREATE INDEX idx_course_program_mapping_program ON course_program_mapping(program_id);
CREATE INDEX idx_programs_code ON programs(program_code);

-- Section content searches
CREATE INDEX idx_course_sections_course ON course_sections(course_id);
CREATE INDEX idx_course_sections_name ON course_sections(section_name);

-- Quality and versioning
CREATE INDEX idx_courses_quality_score ON courses(data_quality_score);
CREATE INDEX idx_data_quality_issues_severity ON data_quality_issues(severity, is_resolved);
CREATE INDEX idx_course_version_history_course ON course_version_history(course_id);

-- Date-based queries for quarterly updates
CREATE INDEX idx_courses_dates ON courses(confirmation_date, valid_from_date);
CREATE INDEX idx_courses_updated ON courses(updated_at);

-- Full-text search index for course content (SQLite FTS5)
CREATE VIRTUAL TABLE course_content_fts USING fts5(
    course_code,
    course_title,
    section_name,
    section_content,
    content='course_sections',
    content_rowid='id'
);

-- Triggers for maintaining data integrity and automation

-- Trigger to update course completeness score when sections change
CREATE TRIGGER update_course_completeness_score
    AFTER INSERT ON course_sections
    BEGIN
        UPDATE courses 
        SET content_completeness_score = (
            SELECT CASE 
                WHEN COUNT(*) >= 8 THEN 1.0
                WHEN COUNT(*) >= 5 THEN 0.8
                WHEN COUNT(*) >= 3 THEN 0.6
                WHEN COUNT(*) >= 1 THEN 0.4
                ELSE 0.0
            END
            FROM course_sections 
            WHERE course_id = NEW.course_id
        ),
        updated_at = strftime('%Y-%m-%d %H:%M:%S', 'now')
        WHERE id = NEW.course_id;
    END;

-- Trigger to update word count when section content changes
CREATE TRIGGER update_section_word_count
    BEFORE INSERT ON course_sections
    BEGIN
        UPDATE course_sections 
        SET word_count = (
            LENGTH(NEW.section_content) - LENGTH(REPLACE(NEW.section_content, ' ', '')) + 1
        )
        WHERE ROWID = NEW.ROWID;
    END;

-- Trigger to maintain FTS index
CREATE TRIGGER course_sections_ai AFTER INSERT ON course_sections BEGIN
    INSERT INTO course_content_fts(rowid, course_code, course_title, section_name, section_content)
    SELECT 
        NEW.id,
        c.course_code,
        c.course_title,
        NEW.section_name,
        NEW.section_content
    FROM courses c WHERE c.id = NEW.course_id;
END;

-- Trigger to log version changes
CREATE TRIGGER log_course_changes
    AFTER UPDATE ON courses
    WHEN OLD.course_title != NEW.course_title 
      OR OLD.credits != NEW.credits
      OR OLD.confirmation_date != NEW.confirmation_date
    BEGIN
        INSERT INTO course_version_history (
            course_id, 
            change_type, 
            changes_summary,
            changed_fields
        ) VALUES (
            NEW.id,
            'updated',
            'Course metadata updated',
            json_array(
                CASE WHEN OLD.course_title != NEW.course_title THEN 'course_title' END,
                CASE WHEN OLD.credits != NEW.credits THEN 'credits' END,
                CASE WHEN OLD.confirmation_date != NEW.confirmation_date THEN 'confirmation_date' END
            )
        );
    END;

-- Validation triggers for data quality

-- Check for minimal content courses
CREATE TRIGGER check_minimal_content
    AFTER INSERT ON courses
    BEGIN
        -- Check after a delay to ensure sections are inserted
        INSERT INTO data_quality_issues (
            course_id,
            issue_type,
            issue_description,
            severity
        )
        SELECT 
            NEW.id,
            'minimal_content',
            'Course has only ' || COUNT(*) || ' sections (expected >= 3)',
            'high'
        FROM course_sections 
        WHERE course_id = NEW.id
        HAVING COUNT(*) < 3;
    END;

-- Initial data for language standards
INSERT INTO language_standards (standard_code, display_name, original_variations) VALUES
('EN', 'English', '["English"]'),
('SV', 'Swedish', '["Swedish"]'),
('EN,SV', 'English and Swedish', '["English and Swedish", "English, Swedish", "Swedish and English", "English,Swedish"]'),
('SV,EN', 'Swedish with English', '["The course is given in Swedish but English may occur."]');

-- Initial program data - only active programs
INSERT INTO programs (program_code, program_name, program_type, department) VALUES
('N2COS', 'Computer Science Master''s Programme', 'master', 'Computer Science and Engineering'),
('N2SOF', 'Software Engineering and Management Master''s Programme', 'master', 'Computer Science and Engineering'),
('N1SOF', 'Software Engineering and Management Bachelor''s Programme', 'bachelor', 'Computer Science and Engineering'),
('N2GDT', 'Game Design Technology Master''s Programme', 'master', 'Computer Science and Engineering');

-- Views for common queries

-- Current active courses view
CREATE VIEW v_current_courses AS
SELECT 
    c.id,
    c.course_code,
    c.course_title,
    c.swedish_title,
    c.department,
    c.credits,
    c.cycle,
    ls.display_name as language_of_instruction,
    c.confirmation_date,
    c.valid_from_date,
    c.content_completeness_score,
    c.data_quality_score,
    COUNT(cs.id) as section_count,
    GROUP_CONCAT(p.program_code) as programs
FROM courses c
LEFT JOIN course_sections cs ON c.id = cs.course_id
LEFT JOIN language_standards ls ON c.language_of_instruction_id = ls.id
LEFT JOIN course_program_mapping cpm ON c.id = cpm.course_id
LEFT JOIN programs p ON cpm.program_id = p.id
WHERE c.is_current = TRUE
GROUP BY c.id;

-- Course quality summary view
CREATE VIEW v_course_quality_summary AS
SELECT 
    department,
    COUNT(*) as total_courses,
    AVG(content_completeness_score) as avg_completeness,
    AVG(data_quality_score) as avg_quality,
    COUNT(CASE WHEN content_completeness_score < 0.6 THEN 1 END) as low_content_courses,
    COUNT(CASE WHEN data_quality_score < 0.7 THEN 1 END) as low_quality_courses
FROM courses 
WHERE is_current = TRUE
GROUP BY department;

-- Program course counts view
CREATE VIEW v_program_statistics AS
SELECT 
    p.program_code,
    p.program_name,
    p.program_type,
    COUNT(cpm.course_id) as course_count,
    AVG(c.credits) as avg_credits,
    COUNT(CASE WHEN c.cycle = 'First cycle' THEN 1 END) as bachelor_courses,
    COUNT(CASE WHEN c.cycle = 'Second cycle' THEN 1 END) as master_courses
FROM programs p
LEFT JOIN course_program_mapping cpm ON p.id = cpm.program_id
LEFT JOIN courses c ON cpm.course_id = c.id AND c.is_current = TRUE
GROUP BY p.id;

-- Schema documentation (SQLite doesn't support COMMENT ON TABLE)
-- courses: Main course entity with version support for handling course updates and replacements
-- course_sections: Normalized storage of course content sections for vector embedding generation  
-- programs: Master data for academic programs
-- course_program_mapping: Many-to-many relationship supporting courses in multiple programs
-- course_metadata: Extended metadata for rare/optional fields stored as structured data
-- data_quality_issues: Tracking of data quality problems for ongoing maintenance

-- Schema version tracking
CREATE TABLE schema_version (
    version VARCHAR(20) PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now')),
    description TEXT
);

INSERT INTO schema_version (version, description) VALUES 
('1.0', 'Initial schema based on 804-course analysis with comprehensive edge case handling');