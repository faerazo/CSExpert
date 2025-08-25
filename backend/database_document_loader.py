#!/usr/bin/env python3
"""
Database Document Loader for RAG System

Loads current courses and programs from the database and converts them 
into documents suitable for vector embeddings. Only includes courses 
where is_current=TRUE and is_replaced=FALSE.
"""

import os
import json
import logging
import sqlite3
from pathlib import Path
from typing import List, Dict, Optional, Any
from datetime import datetime

from langchain_core.documents import Document

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DatabaseDocumentLoader:
    """Loads documents from the CSExpert database for RAG processing."""
    
    def __init__(self, db_path: str = None, programs_dir: str = None):
        """
        Initialize the database document loader.
        
        Args:
            db_path: Path to the SQLite database (default: data/csexpert.db)
            programs_dir: Path to programs JSON directory (default: data/programs)
        """
        # Use default paths if not provided
        base_dir = Path(__file__).parent.parent  # Go up to project root
        self.db_path = db_path or str(base_dir / "data" / "csexpert.db")
        self.programs_dir = programs_dir or str(base_dir / "data" / "programs")
        
        # Verify database exists
        if not os.path.exists(self.db_path):
            raise FileNotFoundError(f"Database not found at {self.db_path}")
        
        # Cache program names
        self._program_names_cache = None
        
        logger.info(f"Initialized DatabaseDocumentLoader with database: {self.db_path}")
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection with row factory for dict-like access."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _get_program_names(self) -> Dict[str, str]:
        """Get mapping of program codes to program names."""
        if self._program_names_cache is None:
            with self._get_connection() as conn:
                cursor = conn.execute("SELECT program_code, program_name FROM programs")
                self._program_names_cache = {row['program_code']: row['program_name'] for row in cursor.fetchall()}
        return self._program_names_cache
    
    def _get_program_name(self, program_code: str) -> str:
        """Get program name for a given program code."""
        return self._get_program_names().get(program_code, program_code)
    
    def load_all_documents(self) -> List[Document]:
        """
        Load all documents from database and program files.
        
        Returns:
            List of Document objects suitable for vector embeddings
        """
        all_documents = []
        
        # Load current courses
        course_docs = self.load_course_documents()
        all_documents.extend(course_docs)
        logger.info(f"Loaded {len(course_docs)} course-related documents")
        
        # Load course sections
        section_docs = self.load_section_documents()
        all_documents.extend(section_docs)
        logger.info(f"Loaded {len(section_docs)} section documents")
        
        # Load course details (tuition, application info)
        detail_docs = self.load_course_detail_documents()
        all_documents.extend(detail_docs)
        logger.info(f"Loaded {len(detail_docs)} course detail documents")
        
        # Load program documents
        program_docs = self.load_program_documents()
        all_documents.extend(program_docs)
        logger.info(f"Loaded {len(program_docs)} program documents")
        
        # Load program course lists
        course_list_docs = self.load_program_course_lists()
        all_documents.extend(course_list_docs)
        logger.info(f"Loaded {len(course_list_docs)} program course list documents")
        
        logger.info(f"Total documents loaded: {len(all_documents)}")
        return all_documents
    
    def load_course_documents(self) -> List[Document]:
        """Load course overview documents for current courses only."""
        documents = []
        
        query = """
        SELECT 
            c.*,
            ls.display_name as language_name,
            GROUP_CONCAT(DISTINCT p.program_code) as program_codes,
            GROUP_CONCAT(DISTINCT p.program_name) as program_names,
            MAX(CASE WHEN eu1.url_type = 'syllabus' THEN eu1.url END) as syllabus_url,
            MAX(CASE WHEN eu2.url_type = 'course_page' THEN eu2.url END) as course_page_url
        FROM courses c
        LEFT JOIN language_standards ls ON c.language_of_instruction_id = ls.id
        LEFT JOIN course_program_mapping cpm ON c.id = cpm.course_id
        LEFT JOIN programs p ON cpm.program_id = p.id
        LEFT JOIN extraction_urls eu1 ON c.course_code = eu1.course_code AND eu1.url_type = 'syllabus'
        LEFT JOIN extraction_urls eu2 ON c.course_code = eu2.course_code AND eu2.url_type = 'course_page'
        WHERE c.is_current = 1 AND c.is_replaced = 0
        GROUP BY c.id
        """
        
        with self._get_connection() as conn:
            cursor = conn.execute(query)
            courses = cursor.fetchall()
            
            for course in courses:
                # Create course overview content
                content_parts = [
                    f"Course: {course['course_code']} - {course['course_title']}",
                    f"Department: {course['department']}",
                    f"Credits: {course['credits']} HP",
                    f"Cycle: {course['cycle']}",
                ]
                
                if course['swedish_title']:
                    content_parts.append(f"Swedish Title: {course['swedish_title']}")
                
                if course['language_name']:
                    content_parts.append(f"Language of Instruction: {course['language_name']}")
                
                if course['study_form']:
                    content_parts.append(f"Study Form: {course['study_form']}")
                
                if course['term']:
                    content_parts.append(f"Term: {course['term']}")
                
                if course['field_of_education']:
                    content_parts.append(f"Field of Education: {course['field_of_education']}")
                
                if course['main_field_of_study']:
                    content_parts.append(f"Main Field of Study: {course['main_field_of_study']}")
                
                if course['specialization']:
                    content_parts.append(f"Specialization: {course['specialization']}")
                
                if course['program_codes']:
                    content_parts.append(f"Part of Programs: {course['program_codes']}")
                
                if course['program_names']:
                    content_parts.append(f"Program Names: {course['program_names']}")
                
                # Add URLs to content
                if course['syllabus_url']:
                    content_parts.append(f"Syllabus: {course['syllabus_url']}")
                
                if course['course_page_url']:
                    content_parts.append(f"Course Page: {course['course_page_url']}")
                
                content = "\n".join(content_parts)
                
                # Create metadata
                metadata = {
                    "doc_type": "course_overview",
                    "course_code": course['course_code'],
                    "course_title": course['course_title'],
                    "department": course['department'],
                    "credits": str(course['credits']),
                    "cycle": course['cycle'],
                    "language": course['language_name'] or "",
                    "study_form": course['study_form'] or "",
                    "term": course['term'] or "",
                    "field_of_education": course['field_of_education'] or "",
                    "main_field_of_study": course['main_field_of_study'] or "",
                    "specialization": course['specialization'] or "",
                    "programs": course['program_codes'] or "",
                    "program_names": course['program_names'] or "",
                    "is_current": True,
                    "source": f"database:courses:{course['course_code']}",
                    "syllabus_url": course['syllabus_url'] or "",
                    "course_page_url": course['course_page_url'] or ""
                }
                
                # Remove empty metadata fields
                metadata = {k: v for k, v in metadata.items() if v}
                
                doc = Document(page_content=content, metadata=metadata)
                documents.append(doc)
        
        logger.info(f"Created {len(documents)} course overview documents")
        return documents
    
    def load_section_documents(self) -> List[Document]:
        """Load course section documents for current courses only."""
        documents = []
        
        query = """
        SELECT 
            cs.*,
            c.course_code,
            c.course_title,
            c.department,
            c.credits,
            c.cycle,
            GROUP_CONCAT(DISTINCT p.program_code) as program_codes,
            GROUP_CONCAT(DISTINCT p.program_name) as program_names
        FROM course_sections cs
        JOIN courses c ON cs.course_id = c.id
        LEFT JOIN course_program_mapping cpm ON c.id = cpm.course_id
        LEFT JOIN programs p ON cpm.program_id = p.id
        WHERE c.is_current = 1 AND c.is_replaced = 0
        GROUP BY cs.id
        """
        
        with self._get_connection() as conn:
            cursor = conn.execute(query)
            sections = cursor.fetchall()
            
            for section in sections:
                # Skip empty sections
                if not section['section_content'] or not section['section_content'].strip():
                    continue
                
                # Create section content
                content = f"""Course: {section['course_code']} - {section['course_title']}
Section: {section['section_name']}

{section['section_content']}"""
                
                # Create metadata
                section_type = section['section_name'].lower().replace(" ", "_").replace("/", "_")
                metadata = {
                    "doc_type": "course_section",
                    "section_type": section_type,
                    "section_name": section['section_name'],
                    "course_code": section['course_code'],
                    "course_title": section['course_title'],
                    "department": section['department'],
                    "credits": str(section['credits']),
                    "cycle": section['cycle'],
                    "programs": section['program_codes'] or "",
                    "is_current": True,
                    "character_count": section['character_count'],
                    "source": f"database:sections:{section['course_code']}:{section_type}"
                }
                
                # Remove empty metadata fields
                metadata = {k: v for k, v in metadata.items() if v}
                
                doc = Document(page_content=content, metadata=metadata)
                documents.append(doc)
        
        logger.info(f"Created {len(documents)} section documents")
        return documents
    
    def load_course_detail_documents(self) -> List[Document]:
        """Load course detail documents (tuition, application info) for current courses only."""
        documents = []
        
        query = """
        SELECT 
            cd.*,
            c.course_code,
            c.course_title,
            c.department,
            c.credits,
            c.cycle,
            c.study_form,
            c.term,
            GROUP_CONCAT(p.program_code) as program_codes
        FROM course_details cd
        JOIN courses c ON cd.course_id = c.id
        LEFT JOIN course_program_mapping cpm ON c.id = cpm.course_id
        LEFT JOIN programs p ON cpm.program_id = p.id
        WHERE c.is_current = 1 AND c.is_replaced = 0
        GROUP BY cd.course_id
        """
        
        with self._get_connection() as conn:
            cursor = conn.execute(query)
            details = cursor.fetchall()
            
            for detail in details:
                # Only create document if there's meaningful detail information
                has_tuition = detail['tuition_fee'] is not None
                has_duration = detail['duration'] is not None
                has_application = detail['application_period'] is not None or detail['application_code'] is not None
                
                if not (has_tuition or has_duration or has_application):
                    continue
                
                # Create detail content
                content_parts = [
                    f"Course: {detail['course_code']} - {detail['course_title']}",
                    "Application and Practical Information:"
                ]
                
                if has_tuition:
                    content_parts.append(f"Tuition Fee: {detail['tuition_fee']} SEK")
                
                if detail['duration']:
                    content_parts.append(f"Duration: {detail['duration']}")
                
                if detail['application_period']:
                    content_parts.append(f"Application Period: {detail['application_period']}")
                
                if detail['application_code']:
                    content_parts.append(f"Application Code: {detail['application_code']}")
                
                if detail['study_form']:
                    content_parts.append(f"Study Form: {detail['study_form']}")
                
                if detail['term']:
                    content_parts.append(f"Term: {detail['term']}")
                
                content = "\n".join(content_parts)
                
                # Create metadata
                metadata = {
                    "doc_type": "course_details",
                    "course_code": detail['course_code'],
                    "course_title": detail['course_title'],
                    "department": detail['department'],
                    "credits": str(detail['credits']),
                    "cycle": detail['cycle'],
                    "has_tuition": has_tuition,
                    "tuition_fee": str(detail['tuition_fee']) if has_tuition else "",
                    "study_form": detail['study_form'] or "",
                    "term": detail['term'] or "",
                    "application_code": detail['application_code'] or "",
                    "programs": detail['program_codes'] or "",
                    "is_current": True,
                    "source": f"database:details:{detail['course_code']}"
                }
                
                # Remove empty metadata fields
                metadata = {k: v for k, v in metadata.items() if v}
                
                doc = Document(page_content=content, metadata=metadata)
                documents.append(doc)
        
        logger.info(f"Created {len(documents)} course detail documents")
        return documents
    
    def load_program_documents(self) -> List[Document]:
        """Load program documents from JSON files."""
        documents = []
        
        if not os.path.exists(self.programs_dir):
            logger.warning(f"Programs directory not found: {self.programs_dir}")
            return documents
        
        program_files = list(Path(self.programs_dir).glob("*.json"))
        logger.info(f"Found {len(program_files)} program files")
        
        for program_file in program_files:
            try:
                with open(program_file, 'r', encoding='utf-8') as f:
                    program_data = json.load(f)
                
                # Create program overview document
                overview_doc = self._create_program_overview_document(program_data)
                if overview_doc:
                    documents.append(overview_doc)
                
                # Create program section documents
                section_docs = self._create_program_section_documents(program_data)
                documents.extend(section_docs)
                
            except Exception as e:
                logger.error(f"Error loading program file {program_file}: {e}")
        
        logger.info(f"Created {len(documents)} program documents")
        return documents
    
    def _create_program_overview_document(self, program_data: Dict) -> Optional[Document]:
        """Create overview document for a program."""
        try:
            program_code = program_data.get('program_code', '')
            
            # Get program name from the database
            program_name = self._get_program_name(program_code)
            
            # Extract key information
            content_parts = [
                f"Program: {program_name} ({program_code})",
                f"Program Code: {program_code}",
                f"Program Name: {program_name}",
                f"Credits: {program_data.get('number_of_credits', '')} HP",
                f"Main Field of Study: {program_data.get('main_field_of_study', '')}",
                "",
                "Purpose:",
                program_data.get('purpose', ''),
                "",
                "Entry Requirements:",
                program_data.get('entry_requirements', {}).get('general_requirements', ''),
            ]
            
            # Add program page information if available
            if 'program_page' in program_data:
                app_info = program_data['program_page'].get('application_information', {})
                if 'autumn_2025' in app_info:
                    autumn = app_info['autumn_2025']
                    content_parts.extend([
                        "",
                        "Study Information:",
                        f"Study Pace: {autumn.get('study_pace', '')}",
                        f"Location: {autumn.get('location', '')}",
                        f"Language: {autumn.get('language', '')}",
                        f"Duration: {autumn.get('duration', '')}",
                    ])
            
            content = "\n".join(str(part) for part in content_parts)
            
            # Create metadata
            metadata = {
                "doc_type": "program_overview",
                "program_code": program_code,
                "program_name": program_name,
                "credits": str(program_data.get('number_of_credits', '')),
                "main_field_of_study": program_data.get('main_field_of_study', ''),
                "source": f"programs:{program_code}"
            }
            
            return Document(page_content=content, metadata=metadata)
            
        except Exception as e:
            logger.error(f"Error creating program overview document: {e}")
            return None
    
    def _create_program_section_documents(self, program_data: Dict) -> List[Document]:
        """Create section documents for a program."""
        documents = []
        program_code = program_data.get('program_code', '')
        program_name = self._get_program_name(program_code)
        
        # Define sections to extract
        sections = {
            'outcomes': program_data.get('outcomes', {}),
            'content_and_structure': program_data.get('content_and_structure', {}),
            'guaranteed_admission': program_data.get('guaranteed_admission', ''),
            'other_information': program_data.get('other_information', {}),
        }
        
        for section_name, section_data in sections.items():
            if not section_data:
                continue
            
            # Handle different data types
            if isinstance(section_data, dict):
                # Flatten nested dictionaries
                content_parts = [f"Program: {program_name} ({program_code})", f"Section: {section_name.replace('_', ' ').title()}", ""]
                for key, value in section_data.items():
                    if isinstance(value, dict):
                        content_parts.append(f"{key.replace('_', ' ').title()}:")
                        for sub_key, sub_value in value.items():
                            if sub_value:
                                content_parts.append(f"  {sub_key.replace('_', ' ').title()}: {sub_value}")
                    elif value:
                        content_parts.append(f"{key.replace('_', ' ').title()}: {value}")
                content = "\n".join(str(part) for part in content_parts)
            else:
                # Simple string content
                content = f"""Program: {program_name} ({program_code})
Section: {section_name.replace('_', ' ').title()}

{section_data}"""
            
            # Create metadata
            metadata = {
                "doc_type": "program_section",
                "section_type": section_name,
                "section_name": section_name.replace('_', ' ').title(),
                "program_code": program_code,
                "program_name": program_name,
                "source": f"programs:{program_code}:{section_name}"
            }
            
            doc = Document(page_content=content, metadata=metadata)
            documents.append(doc)
        
        return documents
    
    def load_program_course_lists(self) -> List[Document]:
        """Create comprehensive course list documents for each program."""
        documents = []
        
        query = """
        SELECT 
            p.program_code,
            p.program_name,
            c.course_code,
            c.course_title,
            c.credits,
            c.cycle,
            c.department,
            c.term,
            c.study_form,
            eu1.url as syllabus_url,
            eu2.url as course_page_url
        FROM programs p
        JOIN course_program_mapping cpm ON p.id = cpm.program_id
        JOIN courses c ON cpm.course_id = c.id
        LEFT JOIN extraction_urls eu1 ON c.course_code = eu1.course_code AND eu1.url_type = 'syllabus'
        LEFT JOIN extraction_urls eu2 ON c.course_code = eu2.course_code AND eu2.url_type = 'course_page'
        WHERE c.is_current = 1 AND c.is_replaced = 0
        ORDER BY p.program_code, c.cycle DESC, c.course_code
        """
        
        with self._get_connection() as conn:
            cursor = conn.execute(query)
            rows = cursor.fetchall()
            
            # Group courses by program
            program_courses = {}
            for row in rows:
                prog_code = row['program_code']
                if prog_code not in program_courses:
                    program_courses[prog_code] = {
                        'program_name': row['program_name'],
                        'courses': []
                    }
                program_courses[prog_code]['courses'].append(row)
            
            # Create document for each program
            for prog_code, prog_data in program_courses.items():
                content_parts = [
                    f"Complete Course List for {prog_data['program_name']} ({prog_code})",
                    f"Total Courses Available: {len(prog_data['courses'])}",
                    "",
                    "COURSE LIST:",
                    ""
                ]
                
                # Group by cycle
                first_cycle = [c for c in prog_data['courses'] if c['cycle'] == 'First cycle']
                second_cycle = [c for c in prog_data['courses'] if c['cycle'] == 'Second cycle']
                third_cycle = [c for c in prog_data['courses'] if c['cycle'] == 'Third cycle']
                
                if second_cycle:
                    content_parts.append("=== SECOND CYCLE (MASTER'S LEVEL) COURSES ===")
                    for course in second_cycle:
                        course_line = f"• {course['course_code']}: {course['course_title']} ({course['credits']} HP)"
                        if course['department']:
                            course_line += f" - {course['department']}"
                        if course['term']:
                            course_line += f" - {course['term']}"
                        content_parts.append(course_line)
                    content_parts.append("")
                
                if first_cycle:
                    content_parts.append("=== FIRST CYCLE (BACHELOR'S LEVEL) COURSES ===")
                    for course in first_cycle:
                        course_line = f"• {course['course_code']}: {course['course_title']} ({course['credits']} HP)"
                        if course['department']:
                            course_line += f" - {course['department']}"
                        if course['term']:
                            course_line += f" - {course['term']}"
                        content_parts.append(course_line)
                    content_parts.append("")
                
                if third_cycle:
                    content_parts.append("=== THIRD CYCLE (PHD LEVEL) COURSES ===")
                    for course in third_cycle:
                        course_line = f"• {course['course_code']}: {course['course_title']} ({course['credits']} HP)"
                        if course['department']:
                            course_line += f" - {course['department']}"
                        if course['term']:
                            course_line += f" - {course['term']}"
                        content_parts.append(course_line)
                    content_parts.append("")
                
                # Add summary statistics
                content_parts.extend([
                    "SUMMARY:",
                    f"- Second Cycle Courses: {len(second_cycle)}",
                    f"- First Cycle Courses: {len(first_cycle)}",
                    f"- Third Cycle Courses: {len(third_cycle)}",
                    f"- Total Credits Available: {sum(c['credits'] for c in prog_data['courses'])} HP"
                ])
                
                content = "\n".join(content_parts)
                
                # Create metadata
                metadata = {
                    "doc_type": "program_course_list",
                    "program_code": prog_code,
                    "program_name": prog_data['program_name'],
                    "total_courses": len(prog_data['courses']),
                    "source": f"database:program_courses:{prog_code}"
                }
                
                doc = Document(page_content=content, metadata=metadata)
                documents.append(doc)
        
        logger.info(f"Created {len(documents)} program course list documents")
        return documents
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about the available data."""
        stats = {
            "current_courses": 0,
            "replaced_courses": 0,
            "total_sections": 0,
            "courses_with_tuition": 0,
            "departments": set(),
            "programs": set(),
            "cycles": set(),
        }
        
        with self._get_connection() as conn:
            # Count current vs replaced courses
            cursor = conn.execute("SELECT COUNT(*) FROM courses WHERE is_current = 1 AND is_replaced = 0")
            stats["current_courses"] = cursor.fetchone()[0]
            
            cursor = conn.execute("SELECT COUNT(*) FROM courses WHERE is_replaced = 1")
            stats["replaced_courses"] = cursor.fetchone()[0]
            
            # Count sections for current courses
            cursor = conn.execute("""
                SELECT COUNT(*) FROM course_sections cs
                JOIN courses c ON cs.course_id = c.id
                WHERE c.is_current = 1 AND c.is_replaced = 0
            """)
            stats["total_sections"] = cursor.fetchone()[0]
            
            # Count courses with tuition
            cursor = conn.execute("""
                SELECT COUNT(DISTINCT c.id) FROM courses c
                JOIN course_details cd ON c.id = cd.course_id
                WHERE c.is_current = 1 AND c.is_replaced = 0 AND cd.tuition_fee IS NOT NULL
            """)
            stats["courses_with_tuition"] = cursor.fetchone()[0]
            
            # Get unique departments
            cursor = conn.execute("SELECT DISTINCT department FROM courses WHERE is_current = 1 AND is_replaced = 0")
            stats["departments"] = {row[0] for row in cursor.fetchall() if row[0]}
            
            # Get unique programs
            cursor = conn.execute("SELECT DISTINCT program_code FROM programs")
            stats["programs"] = {row[0] for row in cursor.fetchall() if row[0]}
            
            # Get unique cycles
            cursor = conn.execute("SELECT DISTINCT cycle FROM courses WHERE is_current = 1 AND is_replaced = 0")
            stats["cycles"] = {row[0] for row in cursor.fetchall() if row[0]}
        
        # Convert sets to lists for JSON serialization
        stats["departments"] = sorted(list(stats["departments"]))
        stats["programs"] = sorted(list(stats["programs"]))
        stats["cycles"] = sorted(list(stats["cycles"]))
        
        return stats