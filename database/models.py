#!/usr/bin/env python3
"""
SQLAlchemy ORM Models for CSExpert Database

Provides object-relational mapping for all database tables with business logic,
validation methods, and relationship management.
"""

import json
import re
from datetime import datetime, date
from typing import List, Dict, Any, Optional, Union
from decimal import Decimal

from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Date, Boolean, ForeignKey, Numeric, Index, UniqueConstraint, CheckConstraint, JSON
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import relationship, sessionmaker, validates
from sqlalchemy.sql import func
from sqlalchemy.ext.hybrid import hybrid_property

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

Base = declarative_base()


class Program(Base):
    """Academic program entity."""
    __tablename__ = 'programs'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    program_code = Column(String(10), unique=True, nullable=False)
    program_name = Column(Text, nullable=False)
    program_type = Column(String(20), CheckConstraint("program_type IN ('bachelor', 'master', 'phd', 'invalid')"), nullable=False)
    department = Column(String(100))
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    course_mappings = relationship("CourseProgramMapping", back_populates="program", cascade="all, delete-orphan")
    
    @validates('program_code')
    def validate_program_code(self, key, program_code):
        """Validate program code format."""
        if not program_code or len(program_code) > 10:
            raise ValueError("Program code must be 1-10 characters")
        return program_code.upper()
    
    @validates('program_type') 
    def validate_program_type(self, key, program_type):
        """Validate program type."""
        valid_types = {'bachelor', 'master', 'phd', 'invalid'}
        if program_type not in valid_types:
            raise ValueError(f"Program type must be one of: {valid_types}")
        return program_type
    
    @property
    def course_count(self) -> int:
        """Get number of courses in this program."""
        return len(self.course_mappings)
    
    def __repr__(self):
        return f"<Program(code='{self.program_code}', name='{self.program_name}')>"


class LanguageStandard(Base):
    """Language standardization lookup table."""
    __tablename__ = 'language_standards'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    standard_code = Column(String(10), nullable=False)
    display_name = Column(String(50), nullable=False)
    original_variations = Column(Text)  # JSON string of original variations
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    courses = relationship("Course", back_populates="language_standard")
    
    @property
    def variations_list(self) -> List[str]:
        """Get original variations as list."""
        if self.original_variations:
            try:
                return json.loads(self.original_variations)
            except json.JSONDecodeError:
                return []
        return []
    
    def __repr__(self):
        return f"<LanguageStandard(code='{self.standard_code}', name='{self.display_name}')>"


class Course(Base):
    """Main course entity with version support and optimized metadata for RAG/embeddings."""
    __tablename__ = 'courses'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    course_code = Column(String(10), nullable=False)
    version_id = Column(Integer, default=1)
    course_title = Column(Text, nullable=False)
    swedish_title = Column(Text)
    department = Column(String(100), nullable=False)
    credits = Column(Numeric(4,1), CheckConstraint('credits > 0'), nullable=False)
    cycle = Column(String(20), CheckConstraint("cycle IN ('First cycle', 'Second cycle', 'Third cycle')"), nullable=False)
    language_of_instruction_id = Column(Integer, ForeignKey('language_standards.id'))
    
    # True metadata fields (for RAG/embeddings)
    content_type = Column(String(20), CheckConstraint("content_type IN ('course', 'program')"), default='course')
    study_form = Column(String(50))  # Campus, Online, Distance, Hybrid
    field_of_education = Column(Text)  # Computer Science, Mathematics
    main_field_of_study = Column(Text)  # Software Engineering, Data Science
    specialization = Column(Text)  # Requirements Engineering, Machine Learning
    term = Column(String(50))  # Autumn 2025, Spring 2025 (parsed from valid_from_date)
    
    # Administrative fields (not for embeddings)
    confirmation_date = Column(Date)
    valid_from_date = Column(String(50))  # Mixed format: dates and terms
    is_current = Column(Boolean, default=True)
    is_replaced = Column(Boolean, default=False)
    replaced_by_course_id = Column(Integer, ForeignKey('courses.id'))
    replacing_course_code = Column(String(10))  # Course code that this course replaces
    content_completeness_score = Column(Numeric(3,2), default=0.0)
    data_quality_score = Column(Numeric(3,2), default=0.0)
    processing_method = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Constraints
    __table_args__ = (
        UniqueConstraint('course_code', 'version_id', name='uix_course_code_version'),
        Index('idx_courses_code', 'course_code'),
        Index('idx_courses_current', 'is_current', 'course_code'),
        Index('idx_courses_department', 'department'),
        Index('idx_courses_quality_score', 'data_quality_score'),
        Index('idx_courses_dates', 'confirmation_date', 'valid_from_date'),
        Index('idx_courses_updated', 'updated_at'),
        # Metadata indexes for RAG optimization
        Index('idx_courses_metadata', 'cycle', 'study_form'),
        Index('idx_courses_field', 'field_of_education', 'main_field_of_study'),
        Index('idx_courses_term', 'term'),
        Index('idx_courses_content_type', 'content_type'),
    )
    
    # Relationships
    language_standard = relationship("LanguageStandard", back_populates="courses")
    sections = relationship("CourseSection", back_populates="course", cascade="all, delete-orphan")
    program_mappings = relationship("CourseProgramMapping", back_populates="course", cascade="all, delete-orphan")
    course_details = relationship("CourseDetails", back_populates="course", uselist=False, cascade="all, delete-orphan")
    quality_issues = relationship("DataQualityIssue", back_populates="course", cascade="all, delete-orphan")
    version_history = relationship("CourseVersionHistory", back_populates="course", cascade="all, delete-orphan")
    
    # Self-referential relationship for replaced courses
    replaced_by = relationship("Course", remote_side=[id])
    
    @validates('course_code')
    def validate_course_code(self, key, course_code):
        """Validate course code format."""
        if not course_code or len(course_code) > 10:
            raise ValueError("Course code must be 1-10 characters")
        return course_code.upper()
    
    @validates('credits')
    def validate_credits(self, key, credits):
        """Validate credits is a valid float value."""
        credits = Decimal(str(credits))
        
        # Only validate that it's a positive number
        if credits <= 0:
            raise ValueError(f"Credits must be positive, got: {credits}")
        
        return credits
    
    
    @validates('content_completeness_score', 'data_quality_score')
    def validate_scores(self, key, score):
        """Validate score values between 0.0 and 1.0."""
        score = Decimal(str(score))
        if not (0 <= score <= 1):
            raise ValueError(f"{key} must be between 0.0 and 1.0")
        return score
    
    @hybrid_property
    def full_code(self):
        """Get full course identifier with version."""
        return f"{self.course_code}v{self.version_id}"
    
    @property
    def programs(self) -> List[Program]:
        """Get all programs this course belongs to."""
        return [mapping.program for mapping in self.program_mappings]
    
    @property
    def program_codes(self) -> List[str]:
        """Get list of program codes this course belongs to."""
        return [mapping.program.program_code for mapping in self.program_mappings]
    
    @property
    def metadata_dict(self) -> Dict[str, Any]:
        """Get course metadata as dictionary (optimized for RAG/embeddings)."""
        return {
            'course_code': self.course_code,
            'course_title': self.course_title,
            'swedish_title': self.swedish_title,
            'department': self.department,
            'cycle': self.cycle,
            'credits': float(self.credits) if self.credits else None,
            'content_type': self.content_type,
            'study_form': self.study_form,
            'field_of_education': self.field_of_education,
            'main_field_of_study': self.main_field_of_study,
            'specialization': self.specialization,
            'term': self.term,
            'language_of_instruction': self.language_standard.display_name if self.language_standard else None,
            'programs': self.program_codes
        }
    
    @property
    def section_count(self) -> int:
        """Get number of course sections."""
        return len(self.sections)
    
    @property
    def total_word_count(self) -> int:
        """Get total word count across all sections."""
        return sum(section.word_count or 0 for section in self.sections)
    
    def calculate_completeness_score(self) -> float:
        """Calculate content completeness score based on sections."""
        section_count = len(self.sections)
        if section_count >= 8:
            return 1.0
        elif section_count >= 5:
            return 0.8
        elif section_count >= 3:
            return 0.6
        elif section_count >= 1:
            return 0.4
        else:
            return 0.0
    
    def parse_term_from_valid_date(self):
        """Parse term/semester from valid_from_date field."""
        if not self.valid_from_date:
            return
            
        valid_text = str(self.valid_from_date).lower()
        
        # Extract year
        year_match = re.search(r'(20\d{2})', valid_text)
        year = year_match.group(1) if year_match else None
        
        # Extract term
        if 'autumn' in valid_text or 'fall' in valid_text or 'ht' in valid_text:
            term = 'Autumn'
        elif 'spring' in valid_text or 'vt' in valid_text:
            term = 'Spring'
        elif 'summer' in valid_text or 'st' in valid_text:
            term = 'Summer'
        else:
            term = None
            
        if term and year:
            self.term = f"{term} {year}"
    
    def update_completeness_score(self):
        """Update the completeness score based on current sections."""
        self.content_completeness_score = self.calculate_completeness_score()
    
    def is_standard_credits(self) -> bool:
        """Check if credits value is standard GU value."""
        standard_credits = {1.5, 3.0, 7.5, 15.0, 22.5, 30.0}
        return float(self.credits) in standard_credits
    
    def __repr__(self):
        return f"<Course(code='{self.course_code}', title='{self.course_title[:50]}')>"


class CourseSection(Base):
    """Course content sections for structured storage."""
    __tablename__ = 'course_sections'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    course_id = Column(Integer, ForeignKey('courses.id', ondelete='CASCADE'), nullable=False)
    section_name = Column(String(100), nullable=False)
    section_content = Column(Text, nullable=True)
    section_order = Column(Integer, default=0)
    word_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Constraints
    __table_args__ = (
        UniqueConstraint('course_id', 'section_name', name='uix_course_section'),
        Index('idx_course_sections_course', 'course_id'),
        Index('idx_course_sections_name', 'section_name'),
    )
    
    # Relationships
    course = relationship("Course", back_populates="sections")
    
    @validates('section_content')
    def validate_section_content(self, key, content):
        """Validate and calculate word count for section content."""
        if content is None:
            self.word_count = 0
            return None
        
        if not content.strip():
            self.word_count = 0
            return ""
        
        # Calculate word count
        word_count = len(content.split())
        self.word_count = word_count
        
        return content.strip()
    
    @property
    def content_preview(self) -> str:
        """Get preview of section content (first 100 characters)."""
        if self.section_content is None:
            return ""
        if len(self.section_content) <= 100:
            return self.section_content
        return self.section_content[:97] + "..."
    
    def __repr__(self):
        return f"<CourseSection(course_id={self.course_id}, name='{self.section_name}')>"


class CourseProgramMapping(Base):
    """Many-to-many relationship between courses and programs."""
    __tablename__ = 'course_program_mapping'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    course_id = Column(Integer, ForeignKey('courses.id', ondelete='CASCADE'), nullable=False)
    program_id = Column(Integer, ForeignKey('programs.id', ondelete='CASCADE'), nullable=False)
    is_primary = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Constraints
    __table_args__ = (
        UniqueConstraint('course_id', 'program_id', name='uix_course_program'),
        Index('idx_course_program_mapping_course', 'course_id'),
        Index('idx_course_program_mapping_program', 'program_id'),
    )
    
    # Relationships
    course = relationship("Course", back_populates="program_mappings")
    program = relationship("Program", back_populates="course_mappings")
    
    def __repr__(self):
        return f"<CourseProgramMapping(course_id={self.course_id}, program_id={self.program_id})>"


class CourseDetails(Base):
    """Course-specific details (not metadata - administrative/practical information)."""
    __tablename__ = 'course_details'
    
    course_id = Column(Integer, ForeignKey('courses.id', ondelete='CASCADE'), primary_key=True)
    
    # Financial information
    tuition_fee = Column(Numeric(10,2))
    
    # Temporal/scheduling details
    duration = Column(String(100))  # Specific date ranges like "24 Mar 2025 - 8 Jun 2025"
    application_period = Column(String(100))  # "15 October - 15 January"
    iteration = Column(String(50))  # Specific semester instance
    
    # Location/contact details
    location = Column(String(100))  # Specific campus/building information
    
    # Administrative codes/references
    application_code = Column(String(50))  # "GU-86092"
    
    # Additional flexible information
    additional_info = Column(JSON)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    course = relationship("Course", back_populates="course_details")
    
    def get_additional_field(self, field_name: str) -> Any:
        """Get value from additional_info JSON field."""
        if self.additional_info and isinstance(self.additional_info, dict):
            return self.additional_info.get(field_name)
        return None
    
    def set_additional_field(self, field_name: str, value: Any):
        """Set value in additional_info JSON field."""
        if self.additional_info is None:
            self.additional_info = {}
        self.additional_info[field_name] = value
    
    @property 
    def details_dict(self) -> Dict[str, Any]:
        """Get course details as dictionary (excluded from embeddings)."""
        details = {
            'tuition_fee': float(self.tuition_fee) if self.tuition_fee else None,
            'duration': self.duration,
            'application_period': self.application_period,
            'application_code': self.application_code,
            'location': self.location,
            'iteration': self.iteration
        }
        
        # Add additional info if available
        if self.additional_info:
            details.update(self.additional_info)
            
        return {k: v for k, v in details.items() if v is not None}
    
    def __repr__(self):
        return f"<CourseDetails(course_id={self.course_id})>"


class DataQualityIssue(Base):
    """Tracking data quality problems for ongoing maintenance."""
    __tablename__ = 'data_quality_issues'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    course_id = Column(Integer, ForeignKey('courses.id', ondelete='CASCADE'), nullable=False)
    issue_type = Column(String(50), nullable=False)
    issue_description = Column(Text, nullable=False)
    severity = Column(String(10), CheckConstraint("severity IN ('low', 'medium', 'high')"), nullable=False)
    is_resolved = Column(Boolean, default=False)
    resolution_notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    resolved_at = Column(DateTime)
    
    # Constraints
    __table_args__ = (
        Index('idx_data_quality_issues_severity', 'severity', 'is_resolved'),
    )
    
    # Relationships
    course = relationship("Course", back_populates="quality_issues")
    
    def resolve(self, resolution_notes: str = None):
        """Mark issue as resolved."""
        self.is_resolved = True
        self.resolved_at = datetime.utcnow()
        if resolution_notes:
            self.resolution_notes = resolution_notes
    
    @validates('issue_type')
    def validate_issue_type(self, key, issue_type):
        """Validate issue type."""
        valid_types = {
            'missing_critical_field', 'unusual_credits', 'minimal_content',
            'type_inconsistency', 'format_variation', 'missing_program_mapping'
        }
        if issue_type not in valid_types:
            logger.warning(f"Unknown issue type: {issue_type}")
        return issue_type
    
    def __repr__(self):
        return f"<DataQualityIssue(type='{self.issue_type}', severity='{self.severity}')>"


class CourseVersionHistory(Base):
    """Course version history for tracking changes."""
    __tablename__ = 'course_version_history'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    course_id = Column(Integer, ForeignKey('courses.id'), nullable=False)
    change_type = Column(String(20), nullable=False)
    previous_version_id = Column(Integer)
    changes_summary = Column(Text)
    changed_fields = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Constraints
    __table_args__ = (
        Index('idx_course_version_history_course', 'course_id'),
    )
    
    # Relationships
    course = relationship("Course", back_populates="version_history")
    
    @property
    def changed_fields_list(self) -> List[str]:
        """Get changed fields as list."""
        if self.changed_fields:
            try:
                return json.loads(self.changed_fields) if isinstance(self.changed_fields, str) else self.changed_fields
            except (json.JSONDecodeError, TypeError):
                return []
        return []
    
    def __repr__(self):
        return f"<CourseVersionHistory(course_id={self.course_id}, type='{self.change_type}')>"


# Business logic helper functions

def create_database_session(database_url: str = "sqlite:///data/csexpert.db") -> sessionmaker:
    """Create database session factory."""
    engine = create_engine(database_url, echo=False)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def find_course_by_code(session, course_code: str, current_only: bool = True) -> Optional[Course]:
    """Find course by code, optionally only current versions."""
    query = session.query(Course).filter(Course.course_code == course_code.upper())
    if current_only:
        query = query.filter(Course.is_current == True)
    return query.first()


def find_courses_by_program(session, program_code: str) -> List[Course]:
    """Find all courses belonging to a specific program."""
    return session.query(Course).join(CourseProgramMapping).join(Program).filter(
        Program.program_code == program_code.upper(),
        Course.is_current == True
    ).all()


def get_courses_with_quality_issues(session, severity: str = None) -> List[Course]:
    """Get courses with data quality issues."""
    query = session.query(Course).join(DataQualityIssue).filter(
        DataQualityIssue.is_resolved == False
    )
    if severity:
        query = query.filter(DataQualityIssue.severity == severity)
    return query.distinct().all()


def calculate_program_statistics(session, program_code: str) -> Dict[str, Any]:
    """Calculate statistics for a specific program."""
    program = session.query(Program).filter(Program.program_code == program_code.upper()).first()
    if not program:
        return {}
    
    courses = find_courses_by_program(session, program_code)
    
    return {
        'program_code': program.program_code,
        'program_name': program.program_name,
        'total_courses': len(courses),
        'total_credits': sum(float(course.credits) for course in courses),
        'avg_credits': sum(float(course.credits) for course in courses) / len(courses) if courses else 0,
        'first_cycle_courses': len([c for c in courses if c.cycle == 'First cycle']),
        'second_cycle_courses': len([c for c in courses if c.cycle == 'Second cycle']),
        'avg_completeness': sum(float(c.content_completeness_score) for c in courses) / len(courses) if courses else 0,
        'avg_quality': sum(float(c.data_quality_score) for c in courses) / len(courses) if courses else 0
    }


if __name__ == "__main__":
    # Test the ORM models
    logger.info("Testing SQLAlchemy ORM Models...")
    
    # Create test database session
    Session = create_database_session("sqlite:///data/test_orm.db")
    session = Session()
    
    try:
        # Test program creation
        program = Program(
            program_code="TEST",
            program_name="Test Program",
            program_type="master",
            department="Test Department"
        )
        session.add(program)
        session.commit()
        
        logger.info(f"Created program: {program}")
        
        # Test course creation
        course = Course(
            course_code="TEST001",
            course_title="Test Course",
            department="Test Department",
            credits=7.5,
            cycle="Second cycle"
        )
        session.add(course)
        session.commit()
        
        logger.info(f"Created course: {course}")
        
        # Test course section
        section = CourseSection(
            course_id=course.id,
            section_name="Course content",
            section_content="This is test content for the course section."
        )
        session.add(section)
        session.commit()
        
        logger.info(f"Created section: {section}")
        
        # Test course-program mapping
        mapping = CourseProgramMapping(
            course_id=course.id,
            program_id=program.id
        )
        session.add(mapping)
        session.commit()
        
        logger.info(f"Created mapping: {mapping}")
        
        # Test business logic
        found_course = find_course_by_code(session, "TEST001")
        logger.info(f"Found course: {found_course}")
        
        program_courses = find_courses_by_program(session, "TEST")
        logger.info(f"Program courses: {len(program_courses)}")
        
        stats = calculate_program_statistics(session, "TEST")
        logger.info(f"Program statistics: {stats}")
        
        logger.info("ORM models test completed successfully")
        
    except Exception as e:
        logger.error(f"ORM test failed: {e}")
        session.rollback()
    finally:
        session.close()