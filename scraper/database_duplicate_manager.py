#!/usr/bin/env python3
"""
Database Duplicate Manager

Replaces the file-based clean_duplicate_courses.py with database-native duplicate 
detection and version tracking using the existing Course versioning system.

This module leverages the database's built-in version tracking capabilities:
- course.version_id for version numbering
- course.is_current for active version marking
- course.is_replaced for replacement status
- course.replaced_by_course_id for replacement chains
- CourseVersionHistory for change tracking
"""

import logging
import re
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple
from decimal import Decimal

from sqlalchemy.orm import sessionmaker
from sqlalchemy import func, and_, or_, create_engine

# Import database components
from database.connection_manager import get_database_manager, DatabaseManager
from database.models import (
    Course, CourseSection, CourseVersionHistory, DataQualityIssue,
    find_course_by_code, Base
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ----- Configuration Constants -----

# Date parsing patterns (from original clean_duplicate_courses.py)
DATE_FORMATS = [
    '%Y-%m-%d',  # 2024-11-11
    '%Y-%m',     # 2024-11
    '%Y',        # 2024
]

TERM_KEYWORDS = {
    'autumn': (8, 1),   # August 1st
    'ht': (8, 1),       # Autumn term (Swedish)
    'spring': (1, 1),   # January 1st
    'vt': (1, 1),       # Spring term (Swedish)
}

# Replacement detection patterns
REPLACEMENT_PATTERNS = [
    r'replaces\s+the\s+course\s+([A-Z]+\d+)',
    r'replaces\s+([A-Z]+\d+)',
    r'replaced\s+the\s+course\s+([A-Z]+\d+)',
    r'replaced\s+([A-Z]+\d+)',
]

# ----- Data Structures -----

class DuplicateResolution:
    """Result of duplicate course resolution"""
    
    def __init__(self, course_code: str, action: str, reason: str, 
                 kept_version: Optional[int] = None, 
                 replaced_versions: Optional[List[int]] = None):
        self.course_code = course_code
        self.action = action  # 'kept', 'version_updated', 'marked_replaced', 'no_action'
        self.reason = reason
        self.kept_version = kept_version
        self.replaced_versions = replaced_versions or []
        self.timestamp = datetime.utcnow()

class CourseVersionInfo:
    """Information about a course version for duplicate analysis"""
    
    def __init__(self, course: Course):
        self.course = course
        self.course_id = course.id
        self.course_code = course.course_code
        self.version_id = course.version_id
        self.priority_date = self._calculate_priority_date()
        self.replacement_info = self._extract_replacement_info()
        self.quality_score = float(course.content_completeness_score or 0.0)
        
    def _calculate_priority_date(self) -> datetime:
        """Calculate priority date using same logic as original cleaner"""
        confirmation_date = self._parse_date(str(self.course.confirmation_date) if self.course.confirmation_date else '')
        valid_from_date = self._parse_date(self.course.valid_from_date or '')
        
        # Use the more recent date as priority
        return max(confirmation_date, valid_from_date)
    
    def _parse_date(self, date_str: str) -> datetime:
        """Parse various date formats (from original cleaner logic)"""
        if not date_str or date_str.strip() == "":
            return datetime.min
        
        date_str = date_str.strip()
        
        # Handle term keywords
        for keyword, (month, day) in TERM_KEYWORDS.items():
            if keyword in date_str.lower():
                year_match = re.search(r'(\d{4})', date_str)
                if year_match:
                    return datetime(int(year_match.group(1)), month, day)
        
        # Try standard formats
        for fmt in DATE_FORMATS:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        
        return datetime.min
    
    def _extract_replacement_info(self) -> List[str]:
        """Extract course codes that this course replaces"""
        replaced_courses = []
        
        # Look in course sections for replacement information
        for section in self.course.sections:
            if section.section_name == 'Additional information' and section.section_content:
                for pattern in REPLACEMENT_PATTERNS:
                    matches = re.findall(pattern, section.section_content, re.IGNORECASE)
                    replaced_courses.extend(matches)
        
        return list(set(replaced_courses))  # Remove duplicates

# ----- Main Database Duplicate Manager -----

class DatabaseDuplicateManager:
    """Database-native duplicate course detection and version management"""
    
    def __init__(self, database_path: str = "data/csexpert.db"):
        self.db_manager = get_database_manager(database_path)
        
        # Create SQLAlchemy engine for ORM operations
        self.engine = create_engine(f'sqlite:///{database_path}', echo=False)
        Base.metadata.create_all(self.engine)  # Ensure tables exist
        self.SessionFactory = sessionmaker(bind=self.engine)
        
        # Statistics tracking
        self.stats = {
            'courses_analyzed': 0,
            'duplicates_found': 0,
            'versions_updated': 0,
            'courses_marked_replaced': 0,
            'replacement_chains_followed': 0,
            'quality_issues_created': 0
        }
        
        logger.info("Database Duplicate Manager initialized")
    
    def detect_and_resolve_duplicates(self):
        """Interface method for orchestrator - detect and resolve duplicates."""
        try:
            resolutions = self.find_duplicate_courses(dry_run=False)
            
            return type('Result', (), {
                'success': True, 
                'resolved_count': len([r for r in resolutions if r.action == 'marked_replaced']),
                'quality_issues_created': len([r for r in resolutions if r.action == 'quality_issue_created']),
                'error_message': None
            })()
            
        except Exception as e:
            logger.error(f"Duplicate detection failed: {e}")
            return type('Result', (), {
                'success': False, 
                'resolved_count': 0,
                'quality_issues_created': 0,
                'error_message': str(e)
            })()
    
    def find_duplicate_courses(self, dry_run: bool = False) -> List[DuplicateResolution]:
        """Find and resolve duplicate courses using database-native approach"""
        session = self.SessionFactory()
        try:
            logger.info("🔍 Phase 1: Building replacement map from database...")
            replacement_map = self._build_replacement_map(session)
            
            logger.info("🔍 Phase 2: Finding duplicate course titles...")
            duplicate_groups = self._group_courses_by_title(session)
            
            logger.info("🔍 Phase 3: Resolving duplicates with version tracking...")
            resolutions = self._resolve_duplicates(session, duplicate_groups, replacement_map, dry_run)
            
            if not dry_run:
                session.commit()
                logger.info("✅ Database changes committed")
            else:
                session.rollback()
                logger.info("🔍 Dry run mode - no changes made to database")
            
            return resolutions
            
        except Exception as e:
            session.rollback()
            logger.error(f"Error in duplicate detection: {e}")
            raise
        finally:
            session.close()
    
    def _build_replacement_map(self, session) -> Dict[str, str]:
        """Build replacement map from database course content"""
        replacement_map = {}
        
        # Query all courses with their sections
        courses = session.query(Course).filter(Course.is_current == True).all()
        
        for course in courses:
            version_info = CourseVersionInfo(course)
            
            # Record replacement relationships
            for replaced_code in version_info.replacement_info:
                replacement_map[replaced_code] = course.course_code
                logger.debug(f"📋 Detected replacement: {course.course_code} replaces {replaced_code}")
        
        logger.info(f"✅ Found {len(replacement_map)} replacement relationships in database")
        return replacement_map
    
    def _group_courses_by_title(self, session) -> Dict[str, List[CourseVersionInfo]]:
        """Group courses by title to find potential duplicates"""
        courses_by_title = {}
        
        # Get all current courses
        courses = session.query(Course).filter(Course.is_current == True).all()
        
        for course in courses:
            title = course.course_title.strip() if course.course_title else ''
            if title:
                if title not in courses_by_title:
                    courses_by_title[title] = []
                courses_by_title[title].append(CourseVersionInfo(course))
        
        # Filter to only titles with duplicates
        duplicate_groups = {
            title: versions for title, versions in courses_by_title.items()
            if len(versions) > 1
        }
        
        logger.info(f"✅ Found {len(duplicate_groups)} course titles with duplicates")
        return duplicate_groups
    
    def _resolve_duplicates(self, session, duplicate_groups: Dict[str, List[CourseVersionInfo]], 
                           replacement_map: Dict[str, str], dry_run: bool) -> List[DuplicateResolution]:
        """Resolve duplicate courses using database version tracking"""
        resolutions = []
        
        for title, versions in duplicate_groups.items():
            logger.info(f"\n📚 Processing: '{title}' ({len(versions)} versions)")
            
            # Sort by priority date (most recent first)
            versions.sort(key=lambda v: v.priority_date, reverse=True)
            
            latest_version = versions[0]
            older_versions = versions[1:]
            
            logger.info(f"   ✅ Latest version: {latest_version.course_code} (v{latest_version.version_id})")
            
            # Check each older version
            for older_version in older_versions:
                resolution = self._resolve_single_duplicate(
                    session, latest_version, older_version, replacement_map, dry_run
                )
                resolutions.append(resolution)
                
                logger.info(f"   🔄 {resolution.action}: {resolution.course_code} - {resolution.reason}")
        
        return resolutions
    
    def _resolve_single_duplicate(self, session, latest: CourseVersionInfo, older: CourseVersionInfo,
                                 replacement_map: Dict[str, str], dry_run: bool) -> DuplicateResolution:
        """Resolve a single duplicate course pair"""
        
        # Check if there's an official replacement relationship
        is_officially_replaced = False
        reason = ""
        
        # Check 1: Official replacement chain
        if older.course_code in replacement_map:
            final_replacing = self._follow_replacement_chain(older.course_code, replacement_map)
            if final_replacing == latest.course_code:
                is_officially_replaced = True
                reason = f"officially replaced by {latest.course_code}"
        
        # Check 2: Latest course declares it replaces the older one
        if older.course_code in latest.replacement_info:
            is_officially_replaced = True
            reason = f"officially replaced by {latest.course_code}"
        
        # Resolve based on official replacement status
        if is_officially_replaced:
            return self._mark_course_replaced(session, older, latest, reason, dry_run)
        else:
            # No official replacement - create quality issue for manual review
            return self._create_quality_issue(session, older, latest, dry_run)
    
    def _mark_course_replaced(self, session, older_version: CourseVersionInfo, 
                             newer_version: CourseVersionInfo, reason: str, dry_run: bool) -> DuplicateResolution:
        """Mark an older course version as replaced"""
        
        if not dry_run:
            # Update the older course
            older_course = older_version.course
            older_course.is_current = False
            older_course.is_replaced = True
            older_course.replaced_by_course_id = newer_version.course_id
            older_course.updated_at = datetime.utcnow()
            
            # Create version history entry
            version_history = CourseVersionHistory(
                course_id=older_course.id,
                change_type='replacement',
                previous_version_id=older_course.version_id,
                changes_summary=f"Course marked as replaced: {reason}",
                changed_fields=['is_current', 'is_replaced', 'replaced_by_course_id']
            )
            session.add(version_history)
            
            self.stats['courses_marked_replaced'] += 1
        
        return DuplicateResolution(
            course_code=older_version.course_code,
            action='marked_replaced',
            reason=reason,
            kept_version=newer_version.version_id,
            replaced_versions=[older_version.version_id]
        )
    
    def _create_quality_issue(self, session, older_version: CourseVersionInfo,
                             newer_version: CourseVersionInfo, dry_run: bool) -> DuplicateResolution:
        """Create a quality issue for manual review of ambiguous duplicates"""
        
        reason = f"No official replacement relationship found - requires manual review"
        
        if not dry_run:
            # Create quality issue for the older course
            quality_issue = DataQualityIssue(
                course_id=older_version.course_id,
                issue_type='missing_program_mapping',  # Closest existing type
                issue_description=f"Potential duplicate course detected. Same title as {newer_version.course_code} but no official replacement relationship found.",
                severity='medium'
            )
            session.add(quality_issue)
            self.stats['quality_issues_created'] += 1
        
        return DuplicateResolution(
            course_code=older_version.course_code,
            action='quality_issue_created',
            reason=reason
        )
    
    def _follow_replacement_chain(self, course_code: str, replacement_map: Dict[str, str]) -> str:
        """Follow replacement chain to find final replacing course"""
        current = course_code
        visited = set()
        
        while current in replacement_map:
            if current in visited:
                logger.warning(f"⚠️ Circular replacement detected involving {current}")
                break
            visited.add(current)
            current = replacement_map[current]
            self.stats['replacement_chains_followed'] += 1
        
        return current
    
    def get_duplicate_statistics(self) -> Dict:
        """Get comprehensive statistics about duplicate processing"""
        session = self.SessionFactory()
        try:
            stats = self.stats.copy()
            
            # Add database statistics
            stats.update({
                'total_courses': session.query(Course).count(),
                'current_courses': session.query(Course).filter(Course.is_current == True).count(),
                'replaced_courses': session.query(Course).filter(Course.is_replaced == True).count(),
                'courses_with_replacements': session.query(Course).filter(
                    Course.replaced_by_course_id.isnot(None)
                ).count(),
                'quality_issues_open': session.query(DataQualityIssue).filter(
                    DataQualityIssue.is_resolved == False
                ).count()
            })
            
            return stats
            
        finally:
            session.close()
    
    def validate_version_consistency(self) -> List[Dict]:
        """Validate database version consistency and report issues"""
        session = self.SessionFactory()
        try:
            issues = []
            
            # Check 1: Multiple current versions of same course
            duplicates = session.query(Course.course_code, func.count(Course.id).label('count')).filter(
                Course.is_current == True
            ).group_by(Course.course_code).having(func.count(Course.id) > 1).all()
            
            for course_code, count in duplicates:
                issues.append({
                    'type': 'multiple_current_versions',
                    'course_code': course_code,
                    'count': count,
                    'description': f'Course {course_code} has {count} current versions'
                })
            
            # Check 2: Replaced courses that are still marked current
            invalid_replaced = session.query(Course).filter(
                and_(Course.is_replaced == True, Course.is_current == True)
            ).all()
            
            for course in invalid_replaced:
                issues.append({
                    'type': 'replaced_but_current',
                    'course_code': course.course_code,
                    'course_id': course.id,
                    'description': f'Course {course.course_code} is marked as replaced but still current'
                })
            
            # Check 3: Circular replacement chains
            # This would require more complex graph traversal - placeholder for now
            
            logger.info(f"✅ Version consistency check complete: {len(issues)} issues found")
            return issues
            
        finally:
            session.close()

# ----- CLI Interface -----

def main():
    """Command line interface for database duplicate manager"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Database-native duplicate course manager')
    parser.add_argument('--database', default="data/csexpert.db", help='Database file path')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without making changes')
    parser.add_argument('--validate', action='store_true', help='Validate version consistency only')
    parser.add_argument('--stats', action='store_true', help='Show duplicate statistics only')
    
    args = parser.parse_args()
    
    try:
        logger.info("Starting Database Duplicate Manager")
        
        manager = DatabaseDuplicateManager(database_path=args.database)
        
        if args.stats:
            stats = manager.get_duplicate_statistics()
            logger.info(f"Duplicate statistics: {stats}")
            return True
        
        if args.validate:
            issues = manager.validate_version_consistency()
            if issues:
                logger.warning(f"Version consistency issues found:")
                for issue in issues:
                    logger.warning(f"  - {issue['type']}: {issue['description']}")
            else:
                logger.info("✅ No version consistency issues found")
            return True
        
        # Run duplicate detection and resolution
        resolutions = manager.find_duplicate_courses(dry_run=args.dry_run)
        
        # Summary
        action_counts = {}
        for resolution in resolutions:
            action_counts[resolution.action] = action_counts.get(resolution.action, 0) + 1
        
        logger.info("\n📊 DUPLICATE RESOLUTION SUMMARY:")
        for action, count in action_counts.items():
            logger.info(f"   {action}: {count} courses")
        
        # Final statistics
        stats = manager.get_duplicate_statistics()
        logger.info(f"📊 Final statistics: {stats}")
        
        if args.dry_run:
            logger.info("\n💡 This was a dry run. Run without --dry-run to apply changes.")
        
        return True
        
    except Exception as e:
        logger.error(f"Duplicate management failed: {e}")
        return False


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)