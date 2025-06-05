#!/usr/bin/env python3
"""
Course Syllabus Duplicate Cleaner

This script automatically identifies and removes outdated course syllabi,
keeping only the most recent version of each course based on dates.

Usage: python clean_duplicate_courses.py [--dry-run]
"""

import json
import os
import shutil
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import argparse
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def parse_date(date_str):
    """Parse various date formats found in course syllabi."""
    if not date_str or date_str.strip() == "":
        return datetime.min
    
    date_str = date_str.strip()
    
    # Try different date formats
    formats = [
        '%Y-%m-%d',  # 2024-11-11
        '%Y-%m',     # 2024-11
        '%Y',        # 2024
    ]
    
    # Handle special cases like "Autumn term 2025", "Autumn Semester 2024", "HT 2025"
    if any(keyword in date_str.lower() for keyword in ['term', 'semester', 'ht', 'vt']):
        import re
        year_match = re.search(r'(\d{4})', date_str)
        if year_match:
            year = int(year_match.group(1))
            # Assume autumn/HT starts in August, spring/VT in January
            if any(keyword in date_str.lower() for keyword in ['autumn', 'ht']):
                return datetime(year, 8, 1)
            elif any(keyword in date_str.lower() for keyword in ['spring', 'vt']):
                return datetime(year, 1, 1)
            else:
                return datetime(year, 1, 1)
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    
    logger.warning(f"Could not parse date: '{date_str}', using minimum date")
    return datetime.min

def get_course_priority_date(metadata):
    """Determine the priority date for a course (confirmation_date or valid_from_date)."""
    confirmation_date = parse_date(metadata.get('confirmation_date', ''))
    valid_from_date = parse_date(metadata.get('valid_from_date', ''))
    
    # Use the more recent date as priority
    priority_date = max(confirmation_date, valid_from_date)
    
    return priority_date, confirmation_date, valid_from_date

def extract_replaced_courses(metadata):
    """Extract course codes that this course officially replaces."""
    import re
    
    replaced_courses = []
    
    # Check sections for replacement information
    sections = metadata.get('sections', {})
    additional_info = sections.get('Additional information', '') or ''
    
    # Look for patterns like "replaces the course DIT126" or "replaces DIT126"
    patterns = [
        r'replaces\s+the\s+course\s+([A-Z]+\d+)',
        r'replaces\s+([A-Z]+\d+)',
        r'replaced\s+the\s+course\s+([A-Z]+\d+)',
        r'replaced\s+([A-Z]+\d+)',
    ]
    
    if additional_info:  # Only process if we have text
        for pattern in patterns:
            matches = re.findall(pattern, additional_info, re.IGNORECASE)
            replaced_courses.extend(matches)
    
    return list(set(replaced_courses))  # Remove duplicates

def follow_replacement_chain(course_code, replacement_map):
    """Follow the replacement chain to find the final replacing course."""
    current = course_code
    visited = set()
    
    while current in replacement_map:
        if current in visited:
            # Circular reference detected, break the loop
            logger.warning(f"⚠️  Circular replacement detected involving {current}")
            break
        visited.add(current)
        current = replacement_map[current]
    
    return current

def load_course_metadata(file_path):
    """Load and return both course metadata and sections from JSON file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # Include both metadata and sections for replacement detection
            metadata = data.get('metadata', {})
            metadata['sections'] = data.get('sections', {})
            return metadata
    except Exception as e:
        logger.error(f"Error loading {file_path}: {e}")
        return {}



def build_complete_replacement_map(course_directory):
    """Phase 1: Build complete replacement map from all courses."""
    course_directory = Path(course_directory)
    replacement_map = {}  # {replaced_course_code: replacing_course_code}
    
    logger.info("🔍 Phase 1: Building complete replacement map...")
    
    # Process files in sorted order for consistent results
    for file_path in sorted(course_directory.glob("*.json")):
        metadata = load_course_metadata(file_path)
        
        if not metadata:
            continue
            
        course_code = metadata.get('course_code', file_path.stem)
        
        # Check if this course replaces others
        replaced_courses = extract_replaced_courses(metadata)
        for replaced_code in replaced_courses:
            replacement_map[replaced_code] = course_code
            logger.info(f"📋 Detected replacement: {course_code} replaces {replaced_code}")
    
    logger.info(f"✅ Phase 1 complete: Found {len(replacement_map)} replacement relationships")
    return replacement_map

def find_duplicate_courses(course_directory):
    """Find courses with duplicate titles and group them by title."""
    course_directory = Path(course_directory)
    
    # Phase 1: Build complete replacement map from ALL courses
    replacement_map = build_complete_replacement_map(course_directory)
    
    logger.info("🔍 Phase 2: Processing course duplicates with complete replacement information...")
    
    # Phase 2: Group courses by title with complete replacement context
    courses_by_title = defaultdict(list)
    
    for file_path in course_directory.glob("*.json"):
        metadata = load_course_metadata(file_path)
        
        if not metadata:
            continue
            
        course_title = metadata.get('course_title', '').strip()
        course_code = metadata.get('course_code', file_path.stem)
        
        if course_title:
            priority_date, confirmation_date, valid_from_date = get_course_priority_date(metadata)
            replaced_courses = extract_replaced_courses(metadata)
            
            courses_by_title[course_title].append({
                'file_path': file_path,
                'course_code': course_code,
                'course_title': course_title,
                'priority_date': priority_date,
                'confirmation_date': confirmation_date,
                'valid_from_date': valid_from_date,
                'metadata': metadata,
                'replaced_courses': replaced_courses
            })
    
    # Find only titles with duplicates, but be more conservative
    duplicate_groups = {}
    potential_issues = []
    
    for title, courses in courses_by_title.items():
        if len(courses) > 1:
            # Sort by priority date (most recent first)
            courses.sort(key=lambda x: x['priority_date'], reverse=True)
            
            # Check if courses seem to be legitimate versions
            latest_course = courses[0]
            potential_duplicates = []
            
            for course in courses[1:]:
                is_officially_replaced = False
                reason = ""
                
                # Check 1: Official replacement relationship (follow the chain)
                if course['course_code'] in replacement_map:
                    final_replacing_course = follow_replacement_chain(course['course_code'], replacement_map)
                    if final_replacing_course == latest_course['course_code']:
                        is_officially_replaced = True
                        direct_replacement = replacement_map[course['course_code']]
                        if direct_replacement == final_replacing_course:
                            reason = f"officially replaced by {final_replacing_course}"
                        else:
                            reason = f"officially replaced by {direct_replacement} → {final_replacing_course}"
                
                # Check 2: This course officially replaces the other
                if course['course_code'] in latest_course['replaced_courses']:
                    is_officially_replaced = True
                    reason = f"officially replaced by {latest_course['course_code']}"
                
                # Only process courses with official replacement relationships
                if is_officially_replaced:
                    course['replacement_reason'] = reason
                    potential_duplicates.append(course)
                else:
                    # Flag as potential issue - no official replacement found
                    potential_issues.append({
                        'title': title,
                        'courses': [latest_course['course_code'], course['course_code']],
                        'reason': 'No official replacement relationship detected - manual review required'
                    })
            
            if potential_duplicates:
                duplicate_groups[title] = [latest_course] + potential_duplicates
    
    # Report potential issues
    if potential_issues:
        logger.warning(f"\n⚠️  POTENTIAL ISSUES DETECTED:")
        for issue in potential_issues:
            logger.warning(f"   🚨 '{issue['title']}' has courses {issue['courses']} - {issue['reason']}")
        logger.warning(f"   💡 These were NOT processed automatically. Review manually if needed.\n")
    
    return duplicate_groups

def clean_duplicate_courses(course_directory, backup_directory=None, dry_run=False):
    """Clean duplicate courses, keeping only the most recent version."""
    
    if backup_directory is None:
        backup_directory = Path(course_directory).parent / "backup_old_courses"
    
    backup_directory = Path(backup_directory)
    
    if not dry_run:
        backup_directory.mkdir(exist_ok=True)
    
    duplicate_groups = find_duplicate_courses(course_directory)
    
    if not duplicate_groups:
        logger.info("✅ No duplicate course titles found!")
        return
    
    total_removed = 0
    total_kept = 0
    
    logger.info(f"🔍 Found {len(duplicate_groups)} course titles with duplicates:")
    
    for title, courses in duplicate_groups.items():
        logger.info(f"\n📚 Course: '{title}'")
        
        # Keep the most recent (first in sorted list)
        latest_course = courses[0]
        outdated_courses = courses[1:]
        
        logger.info(f"   ✅ KEEPING: {latest_course['course_code']} (confirmed: {latest_course['metadata'].get('confirmation_date', 'N/A')}, valid: {latest_course['metadata'].get('valid_from_date', 'N/A')})")
        total_kept += 1
        
        for course in outdated_courses:
            action = "WOULD MOVE" if dry_run else "MOVING"
            reason = course.get('replacement_reason', 'unknown reason')
            logger.info(f"   🗂️  {action}: {course['course_code']} (confirmed: {course['metadata'].get('confirmation_date', 'N/A')}, valid: {course['metadata'].get('valid_from_date', 'N/A')}) - {reason}")
            
            if not dry_run:
                try:
                    backup_path = backup_directory / course['file_path'].name
                    shutil.move(str(course['file_path']), str(backup_path))
                    logger.info(f"      → Moved to: {backup_path}")
                except Exception as e:
                    logger.error(f"      ❌ Error moving file: {e}")
                    continue
            
            total_removed += 1
    
    logger.info(f"\n📊 SUMMARY:")
    logger.info(f"   ✅ Courses kept (latest versions): {total_kept}")
    logger.info(f"   🗂️  Courses {'would be moved' if dry_run else 'moved'} to backup: {total_removed}")
    
    if dry_run:
        logger.info(f"\n💡 This was a dry run. To actually move files, run without --dry-run")
    else:
        logger.info(f"   📁 Backup location: {backup_directory}")
        logger.info(f"\n✅ Course cleanup completed!")

def main():
    parser = argparse.ArgumentParser(description="Clean duplicate course syllabi")
    parser.add_argument("--course-dir", default="data/json/courses_syllabus", 
                       help="Directory containing course JSON files")
    parser.add_argument("--backup-dir", default=None,
                       help="Directory to move outdated files to (default: backup_old_courses)")
    parser.add_argument("--dry-run", action="store_true",
                       help="Show what would be done without actually moving files")
    
    args = parser.parse_args()
    
    course_dir = Path(args.course_dir)
    
    if not course_dir.exists():
        logger.error(f"Course directory does not exist: {course_dir}")
        return 1
    
    logger.info(f"🔍 Scanning for duplicate courses in: {course_dir}")
    if args.dry_run:
        logger.info("🔍 DRY RUN MODE - No files will be moved")
    
    clean_duplicate_courses(
        course_directory=course_dir,
        backup_directory=args.backup_dir,
        dry_run=args.dry_run
    )
    
    return 0

if __name__ == "__main__":
    exit(main()) 