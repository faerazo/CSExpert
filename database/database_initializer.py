#!/usr/bin/env python3
"""
Database Initialization and Setup

Creates and initializes the CSExpert SQLite database with production schema,
indexes, triggers, and initial data setup.
"""

import sqlite3
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
import json
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DatabaseInitializer:
    """Handles database creation, schema setup, and initial configuration."""
    
    def __init__(self, database_path: str = "data/csexpert.db"):
        """Initialize database initializer with path."""
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        
        # SQL schema components
        self.schema_components = {
            'tables': self._get_table_definitions(),
            'indexes': self._get_index_definitions(), 
            'triggers': self._get_trigger_definitions(),
            'views': self._get_view_definitions(),
            'initial_data': self._get_initial_data()
        }
        
        logger.info(f"Database initializer configured for {self.database_path}")
    
    def initialize_database(self, drop_existing: bool = False) -> bool:
        """
        Initialize the complete database with production schema.
        
        Args:
            drop_existing: Whether to drop existing database first
            
        Returns:
            True if initialization successful
        """
        try:
            logger.info("Starting database initialization...")
            
            # Drop existing database if requested
            if drop_existing and self.database_path.exists():
                logger.warning(f"Dropping existing database: {self.database_path}")
                self.database_path.unlink()
            
            # Create database connection
            with sqlite3.connect(str(self.database_path)) as conn:
                conn.execute("PRAGMA foreign_keys = ON")
                conn.execute("PRAGMA journal_mode = WAL")
                conn.execute("PRAGMA synchronous = NORMAL")
                conn.execute("PRAGMA cache_size = 10000")
                conn.execute("PRAGMA temp_store = MEMORY")
                conn.execute("PRAGMA mmap_size = 268435456")  # 256MB
                
                # Create tables
                logger.info("Creating database tables...")
                for table_name, table_sql in self.schema_components['tables'].items():
                    logger.info(f"Creating table: {table_name}")
                    conn.execute(table_sql)
                
                # Create indexes
                logger.info("Creating database indexes...")
                for index_name, index_sql in self.schema_components['indexes'].items():
                    logger.info(f"Creating index: {index_name}")
                    conn.execute(index_sql)
                
                # Create triggers
                logger.info("Creating database triggers...")
                for trigger_name, trigger_sql in self.schema_components['triggers'].items():
                    logger.info(f"Creating trigger: {trigger_name}")
                    conn.execute(trigger_sql)
                
                # Create views
                logger.info("Creating database views...")
                for view_name, view_sql in self.schema_components['views'].items():
                    logger.info(f"Creating view: {view_name}")
                    conn.execute(view_sql)
                
                # Insert initial data
                logger.info("Inserting initial data...")
                for table_name, data_list in self.schema_components['initial_data'].items():
                    if data_list:
                        logger.info(f"Inserting {len(data_list)} records into {table_name}")
                        self._insert_initial_data(conn, table_name, data_list)
                
                # Create schema version tracking
                self._create_schema_version(conn)
                
                conn.commit()
                logger.info("Database initialization completed successfully!")
                
            # Verify database integrity
            return self.verify_database_integrity()
            
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            return False
    
    def _get_table_definitions(self) -> Dict[str, str]:
        """Get all table creation SQL statements."""
        return {
            'language_standards': """
                CREATE TABLE language_standards (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    standard_code VARCHAR(10) UNIQUE NOT NULL,
                    display_name VARCHAR(50) NOT NULL,
                    original_variations TEXT,
                    created_at TIMESTAMP DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now'))
                )
            """,
            
            'programs': """
                CREATE TABLE programs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    program_code VARCHAR(10) UNIQUE NOT NULL,
                    program_name TEXT NOT NULL,
                    program_type VARCHAR(20) CHECK (program_type IN ('bachelor', 'master', 'phd')) NOT NULL,
                    department VARCHAR(100),
                    description TEXT,
                    created_at TIMESTAMP DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now')),
                    updated_at TIMESTAMP DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now'))
                )
            """,
            
            'courses': """
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
                    confirmation_date DATE NULL,
                    valid_from_date VARCHAR(50) NULL,
                    is_current BOOLEAN DEFAULT TRUE,
                    is_replaced BOOLEAN DEFAULT FALSE,
                    replaced_by_course_id INTEGER REFERENCES courses(id),
                    content_completeness_score DECIMAL(3,2) DEFAULT 0.0 CHECK (content_completeness_score >= 0.0 AND content_completeness_score <= 1.0),
                    data_quality_score DECIMAL(3,2) DEFAULT 0.0 CHECK (data_quality_score >= 0.0 AND data_quality_score <= 1.0),
                    processing_method VARCHAR(50),
                    created_at TIMESTAMP DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now')),
                    updated_at TIMESTAMP DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now')),
                    
                    UNIQUE(course_code, version_id)
                )
            """,
            
            'course_sections': """
                CREATE TABLE course_sections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
                    section_name VARCHAR(100) NOT NULL,
                    section_content TEXT,
                    section_order INTEGER DEFAULT 0,
                    word_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now')),
                    
                    UNIQUE(course_id, section_name)
                )
            """,
            
            'course_program_mapping': """
                CREATE TABLE course_program_mapping (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
                    program_id INTEGER NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
                    is_primary BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now')),
                    
                    UNIQUE(course_id, program_id)
                )
            """,
            
            'course_metadata': """
                CREATE TABLE course_metadata (
                    course_id INTEGER PRIMARY KEY REFERENCES courses(id) ON DELETE CASCADE,
                    field_of_education TEXT,
                    main_field_of_study TEXT,
                    specialization TEXT,
                    location VARCHAR(100),
                    study_form VARCHAR(50),
                    duration VARCHAR(100),
                    application_period VARCHAR(100),
                    application_code VARCHAR(50),
                    iteration VARCHAR(50),
                    tuition_fee DECIMAL(10,2),
                    additional_info TEXT,
                    created_at TIMESTAMP DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now')),
                    updated_at TIMESTAMP DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now'))
                )
            """,
            
            'data_quality_issues': """
                CREATE TABLE data_quality_issues (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
                    issue_type VARCHAR(50) NOT NULL,
                    issue_description TEXT NOT NULL,
                    severity VARCHAR(10) CHECK (severity IN ('low', 'medium', 'high')) NOT NULL,
                    is_resolved BOOLEAN DEFAULT FALSE,
                    resolution_notes TEXT,
                    created_at TIMESTAMP DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now')),
                    resolved_at TIMESTAMP NULL
                )
            """,
            
            'course_version_history': """
                CREATE TABLE course_version_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    course_id INTEGER NOT NULL REFERENCES courses(id),
                    change_type VARCHAR(20) NOT NULL,
                    previous_version_id INTEGER,
                    changes_summary TEXT,
                    changed_fields TEXT,
                    created_at TIMESTAMP DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now'))
                )
            """,
            
            'schema_version': """
                CREATE TABLE schema_version (
                    version VARCHAR(20) PRIMARY KEY,
                    applied_at TIMESTAMP DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now')),
                    description TEXT,
                    migration_script TEXT
                )
            """
        }
    
    def _get_index_definitions(self) -> Dict[str, str]:
        """Get all index creation SQL statements."""
        return {
            'idx_courses_code': 'CREATE INDEX idx_courses_code ON courses(course_code)',
            'idx_courses_current': 'CREATE INDEX idx_courses_current ON courses(is_current, course_code)',
            'idx_courses_department': 'CREATE INDEX idx_courses_department ON courses(department)',
            'idx_courses_quality_score': 'CREATE INDEX idx_courses_quality_score ON courses(data_quality_score)',
            'idx_courses_dates': 'CREATE INDEX idx_courses_dates ON courses(confirmation_date, valid_from_date)',
            'idx_courses_updated': 'CREATE INDEX idx_courses_updated ON courses(updated_at)',
            
            'idx_course_sections_course': 'CREATE INDEX idx_course_sections_course ON course_sections(course_id)',
            'idx_course_sections_name': 'CREATE INDEX idx_course_sections_name ON course_sections(section_name)',
            
            'idx_course_program_mapping_course': 'CREATE INDEX idx_course_program_mapping_course ON course_program_mapping(course_id)',
            'idx_course_program_mapping_program': 'CREATE INDEX idx_course_program_mapping_program ON course_program_mapping(program_id)',
            
            'idx_data_quality_issues_severity': 'CREATE INDEX idx_data_quality_issues_severity ON data_quality_issues(severity, is_resolved)',
            
            'idx_programs_code': 'CREATE INDEX idx_programs_code ON programs(program_code)',
            'idx_programs_type': 'CREATE INDEX idx_programs_type ON programs(program_type)'
        }
    
    def _get_trigger_definitions(self) -> Dict[str, str]:
        """Get all trigger creation SQL statements."""
        return {
            'update_course_updated_at': """
                CREATE TRIGGER update_course_updated_at
                    AFTER UPDATE ON courses
                    BEGIN
                        UPDATE courses SET updated_at = strftime('%Y-%m-%d %H:%M:%S', 'now') WHERE id = NEW.id;
                    END
            """,
            
            'update_program_updated_at': """
                CREATE TRIGGER update_program_updated_at
                    AFTER UPDATE ON programs
                    BEGIN
                        UPDATE programs SET updated_at = strftime('%Y-%m-%d %H:%M:%S', 'now') WHERE id = NEW.id;
                    END
            """,
            
            'update_course_metadata_updated_at': """
                CREATE TRIGGER update_course_metadata_updated_at
                    AFTER UPDATE ON course_metadata
                    BEGIN
                        UPDATE course_metadata SET updated_at = strftime('%Y-%m-%d %H:%M:%S', 'now') WHERE course_id = NEW.course_id;
                    END
            """,
            
            
            'update_course_completeness_score': """
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
                    END
            """,
            
            'log_course_changes': """
                CREATE TRIGGER log_course_changes
                    AFTER UPDATE ON courses
                    BEGIN
                        INSERT INTO course_version_history (
                            course_id, change_type, changes_summary, changed_fields
                        ) VALUES (
                            NEW.id, 'updated',
                            'Course updated via trigger',
                            'Multiple fields updated'
                        );
                    END
            """
        }
    
    def _get_view_definitions(self) -> Dict[str, str]:
        """Get all view creation SQL statements."""
        return {
            'v_course_quality_summary': """
                CREATE VIEW v_course_quality_summary AS
                SELECT 
                    department,
                    COUNT(*) as total_courses,
                    AVG(content_completeness_score) as avg_completeness,
                    AVG(data_quality_score) as avg_quality,
                    COUNT(CASE WHEN content_completeness_score < 0.6 THEN 1 END) as low_content_courses,
                    COUNT(CASE WHEN data_quality_score < 0.7 THEN 1 END) as low_quality_courses,
                    COUNT(CASE WHEN is_current = FALSE THEN 1 END) as archived_courses
                FROM courses 
                GROUP BY department
                ORDER BY avg_quality DESC
            """,
            
            'v_course_with_programs': """
                CREATE VIEW v_course_with_programs AS
                SELECT 
                    c.id,
                    c.course_code,
                    c.course_title,
                    c.department,
                    c.credits,
                    c.cycle,
                    c.is_current,
                    GROUP_CONCAT(p.program_code, ', ') as program_codes,
                    GROUP_CONCAT(p.program_name, '; ') as program_names,
                    COUNT(cs.id) as section_count,
                    c.content_completeness_score,
                    c.data_quality_score
                FROM courses c
                LEFT JOIN course_program_mapping cpm ON c.id = cpm.course_id
                LEFT JOIN programs p ON cpm.program_id = p.id
                LEFT JOIN course_sections cs ON c.id = cs.course_id
                GROUP BY c.id
                ORDER BY c.course_code
            """,
            
            'v_program_course_counts': """
                CREATE VIEW v_program_course_counts AS
                SELECT 
                    p.program_code,
                    p.program_name,
                    p.program_type,
                    COUNT(cpm.course_id) as total_courses,
                    COUNT(CASE WHEN c.is_current = TRUE THEN 1 END) as current_courses,
                    AVG(c.content_completeness_score) as avg_completeness,
                    AVG(c.data_quality_score) as avg_quality
                FROM programs p
                LEFT JOIN course_program_mapping cpm ON p.id = cpm.program_id
                LEFT JOIN courses c ON cpm.course_id = c.id
                GROUP BY p.id
                ORDER BY total_courses DESC
            """
        }
    
    def _get_initial_data(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get initial data to populate tables."""
        return {
            'language_standards': [
                {'standard_code': 'EN', 'display_name': 'English', 'original_variations': '["English"]'},
                {'standard_code': 'SV', 'display_name': 'Swedish', 'original_variations': '["Swedish"]'},
                {'standard_code': 'EN,SV', 'display_name': 'English and Swedish', 
                 'original_variations': '["English and Swedish", "English, Swedish", "Swedish and English"]'},
                {'standard_code': 'SV,EN', 'display_name': 'Swedish with English', 
                 'original_variations': '["The course is given in Swedish but English may occur."]'}
            ],
            
            'programs': [
                {'program_code': 'N2COS', 'program_name': 'Computer Science Masters Programme', 
                 'program_type': 'master', 'department': 'Computer Science and Engineering',
                 'description': 'Advanced computer science education with focus on algorithms, software engineering, and system design'},
                {'program_code': 'N2SOF', 'program_name': 'Software Engineering and Management Masters Programme',
                 'program_type': 'master', 'department': 'Computer Science and Engineering',
                 'description': 'Master programme combining software engineering with management and entrepreneurship'},
                {'program_code': 'N1SOF', 'program_name': 'Software Engineering and Management Bachelors Programme',
                 'program_type': 'bachelor', 'department': 'Computer Science and Engineering',
                 'description': 'Bachelor programme in software engineering with management perspective'},
                {'program_code': 'N2GDT', 'program_name': 'Game Design Technology Masters Programme',
                 'program_type': 'master', 'department': 'Computer Science and Engineering',
                 'description': 'Master programme specializing in game development and interactive media'}
            ]
        }
    
    def _insert_initial_data(self, conn: sqlite3.Connection, table_name: str, data_list: List[Dict[str, Any]]):
        """Insert initial data into a table."""
        if not data_list:
            return
        
        # Get column names from first record
        columns = list(data_list[0].keys())
        placeholders = ', '.join(['?' for _ in columns])
        
        sql = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders})"
        
        for record in data_list:
            values = [record[col] for col in columns]
            conn.execute(sql, values)
    
    def _create_schema_version(self, conn: sqlite3.Connection):
        """Create initial schema version entry."""
        conn.execute("""
            INSERT INTO schema_version (version, description, migration_script) 
            VALUES (?, ?, ?)
        """, (
            '1.0', 
            'Initial schema based on 804-course analysis and comprehensive scenario taxonomy',
            'database_initializer.py'
        ))
    
    def verify_database_integrity(self) -> bool:
        """Verify database was created correctly and has integrity."""
        try:
            with sqlite3.connect(str(self.database_path)) as conn:
                conn.execute("PRAGMA foreign_keys = ON")
                
                # Check table existence
                tables = conn.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name NOT LIKE 'sqlite_%'
                    ORDER BY name
                """).fetchall()
                
                expected_tables = set(self.schema_components['tables'].keys())
                actual_tables = {table[0] for table in tables}
                
                if not expected_tables.issubset(actual_tables):
                    missing = expected_tables - actual_tables
                    logger.error(f"Missing tables: {missing}")
                    return False
                
                # Check indexes
                indexes = conn.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='index' AND name NOT LIKE 'sqlite_%'
                """).fetchall()
                
                expected_indexes = set(self.schema_components['indexes'].keys())
                actual_indexes = {idx[0] for idx in indexes}
                
                if not expected_indexes.issubset(actual_indexes):
                    missing_indexes = expected_indexes - actual_indexes
                    logger.warning(f"Missing indexes: {missing_indexes}")
                
                # Check triggers
                triggers = conn.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='trigger'
                """).fetchall()
                
                expected_triggers = set(self.schema_components['triggers'].keys())
                actual_triggers = {trig[0] for trig in triggers}
                
                if not expected_triggers.issubset(actual_triggers):
                    missing_triggers = expected_triggers - actual_triggers
                    logger.warning(f"Missing triggers: {missing_triggers}")
                
                # Run integrity check
                integrity_result = conn.execute("PRAGMA integrity_check").fetchone()
                if integrity_result[0] != "ok":
                    logger.error(f"Database integrity check failed: {integrity_result[0]}")
                    return False
                
                # Check initial data
                for table_name in ['language_standards', 'programs']:
                    count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
                    expected_count = len(self.schema_components['initial_data'][table_name])
                    if count != expected_count:
                        logger.error(f"Initial data mismatch in {table_name}: expected {expected_count}, got {count}")
                        return False
                
                logger.info("Database integrity verification passed!")
                return True
                
        except Exception as e:
            logger.error(f"Database integrity verification failed: {e}")
            return False
    
    def get_database_info(self) -> Dict[str, Any]:
        """Get comprehensive database information."""
        try:
            with sqlite3.connect(str(self.database_path)) as conn:
                # Basic info
                tables = conn.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name NOT LIKE 'sqlite_%'
                    ORDER BY name
                """).fetchall()
                
                indexes = conn.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='index' AND name NOT LIKE 'sqlite_%'
                """).fetchall()
                
                triggers = conn.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='trigger'
                """).fetchall()
                
                views = conn.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='view'
                """).fetchall()
                
                # Database size
                page_count = conn.execute("PRAGMA page_count").fetchone()[0]
                page_size = conn.execute("PRAGMA page_size").fetchone()[0] 
                db_size_mb = (page_count * page_size) / (1024 * 1024)
                
                # Schema version
                schema_version = conn.execute("""
                    SELECT version, applied_at, description 
                    FROM schema_version 
                    ORDER BY applied_at DESC 
                    LIMIT 1
                """).fetchone()
                
                return {
                    'database_path': str(self.database_path),
                    'database_size_mb': round(db_size_mb, 2),
                    'tables': [t[0] for t in tables],
                    'table_count': len(tables),
                    'indexes': [i[0] for i in indexes],
                    'index_count': len(indexes),
                    'triggers': [t[0] for t in triggers],
                    'trigger_count': len(triggers),
                    'views': [v[0] for v in views],
                    'view_count': len(views),
                    'schema_version': schema_version[0] if schema_version else None,
                    'schema_applied_at': schema_version[1] if schema_version else None,
                    'schema_description': schema_version[2] if schema_version else None
                }
                
        except Exception as e:
            logger.error(f"Failed to get database info: {e}")
            return {}


def main():
    """Main function to initialize database."""
    logger.info("Starting database initialization...")
    
    # Initialize the database
    initializer = DatabaseInitializer()
    
    success = initializer.initialize_database(drop_existing=True)
    
    if success:
        logger.info("Database initialization completed successfully!")
        
        # Print database information
        db_info = initializer.get_database_info()
        print("\n" + "="*80)
        print("DATABASE INITIALIZATION SUMMARY")
        print("="*80)
        print(f"Database Path: {db_info['database_path']}")
        print(f"Database Size: {db_info['database_size_mb']} MB")
        print(f"Schema Version: {db_info['schema_version']}")
        print(f"Applied At: {db_info['schema_applied_at']}")
        print(f"\nComponents Created:")
        print(f"  • Tables: {db_info['table_count']} ({', '.join(db_info['tables'])})")
        print(f"  • Indexes: {db_info['index_count']}")
        print(f"  • Triggers: {db_info['trigger_count']}")
        print(f"  • Views: {db_info['view_count']}")
        print("="*80)
        
    else:
        logger.error("Database initialization failed!")
        exit(1)


if __name__ == "__main__":
    main()