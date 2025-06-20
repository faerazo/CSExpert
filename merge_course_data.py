import argparse
import json
import os
import shutil
from pathlib import Path

def combine_json_data(syllabus_data, webpages_data):
    """
    Combine data from syllabus (base) and webpages JSON files.
    """
    # Start with syllabus data as the base
    combined = json.loads(json.dumps(syllabus_data))  # Deep copy
    
    # Metadata fields to move from webpages to syllabus
    metadata_fields_to_move = [
        'iteration', 'study_pace', 'time', 'location', 
        'study_form', 'duration', 'application_period', 'application_code'
    ]
    
    # Add metadata fields from webpages
    webpages_metadata = webpages_data.get('metadata', {})
    for field in metadata_fields_to_move:
        if field in webpages_metadata:
            combined['metadata'][field] = webpages_metadata[field]
    
    # Sections to move from webpages
    sections_to_move = ['Selection', 'Tuition']
    
    # Add sections from webpages
    webpages_sections = webpages_data.get('sections', {})
    for section in sections_to_move:
        if section in webpages_sections:
            combined['sections'][section] = webpages_sections[section]
    
    # Handle Additional information - append webpages to syllabus
    webpages_additional = webpages_sections.get('Additional information', '')
    if webpages_additional:
        if 'Additional information' in combined.get('sections', {}):
            # Append to existing additional information
            existing_additional = combined['sections']['Additional information']
            combined['sections']['Additional information'] = f"{existing_additional}\n\n{webpages_additional}"
        else:
            # Add new additional information section
            combined['sections']['Additional information'] = webpages_additional
    
    return combined

def merge_course_data(syllabus_folder, webpages_folder, output_folder, dry_run=False, verbose=False):
    """
    Complete merger: combine common files and copy unique files.
    """
    # Create output folder if it doesn't exist
    if not dry_run:
        Path(output_folder).mkdir(parents=True, exist_ok=True)
    
    # Get all JSON files in both folders
    syllabus_files = set(f for f in os.listdir(syllabus_folder) if f.endswith('.json'))
    webpages_files = set(f for f in os.listdir(webpages_folder) if f.endswith('.json'))
    
    # Categorize files
    common_files = syllabus_files.intersection(webpages_files)
    syllabus_only = syllabus_files - webpages_files
    webpages_only = webpages_files - syllabus_files
    
    print("File Analysis:")
    print(f"  Common files (will be combined): {len(common_files)}")
    print(f"  Syllabus-only files (will be copied): {len(syllabus_only)}")
    print(f"  Webpages-only files (will be copied): {len(webpages_only)}")
    print(f"  Total files to process: {len(common_files) + len(syllabus_only) + len(webpages_only)}")
    print()
    
    if verbose:
        if common_files:
            print(f"Common files: {', '.join(sorted(common_files))}")
        if syllabus_only:
            print(f"Syllabus-only: {', '.join(sorted(syllabus_only))}")
        if webpages_only:
            print(f"Webpages-only: {', '.join(sorted(webpages_only))}")
        print()
    
    if dry_run:
        print("DRY RUN - No files will be modified")
        return len(common_files), len(syllabus_only), len(webpages_only), 0
    
    combined_count = 0
    copied_count = 0
    error_count = 0
    
    # 1. COMBINE common files
    if common_files:
        print("Combining files that exist in both folders:")
        for filename in sorted(common_files):
            try:
                # Load both files
                syllabus_path = os.path.join(syllabus_folder, filename)
                webpages_path = os.path.join(webpages_folder, filename)
                
                with open(syllabus_path, 'r', encoding='utf-8') as f:
                    syllabus_data = json.load(f)
                
                with open(webpages_path, 'r', encoding='utf-8') as f:
                    webpages_data = json.load(f)
                
                # Combine the data
                combined_data = combine_json_data(syllabus_data, webpages_data)
                
                # Write to output folder
                output_path = os.path.join(output_folder, filename)
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(combined_data, f, indent=2, ensure_ascii=False)
                
                print(f"  Successfully combined {filename}")
                combined_count += 1
                
            except Exception as e:
                print(f"  Error combining {filename}: {str(e)}")
                error_count += 1
        print()
    
    # 2. COPY syllabus-only files
    if syllabus_only:
        print("Copying syllabus-only files:")
        for filename in sorted(syllabus_only):
            try:
                source_path = os.path.join(syllabus_folder, filename)
                dest_path = os.path.join(output_folder, filename)
                
                if os.path.exists(dest_path):
                    print(f"  Skipping {filename} (already exists)")
                    continue
                
                shutil.copy2(source_path, dest_path)
                print(f"  Successfully copied {filename}")
                copied_count += 1
                
            except Exception as e:
                print(f"  Error copying {filename}: {str(e)}")
                error_count += 1
        print()
    
    # 3. COPY webpages-only files
    if webpages_only:
        print("Copying webpages-only files:")
        for filename in sorted(webpages_only):
            try:
                source_path = os.path.join(webpages_folder, filename)
                dest_path = os.path.join(output_folder, filename)
                
                if os.path.exists(dest_path):
                    print(f"  Skipping {filename} (already exists)")
                    continue
                
                shutil.copy2(source_path, dest_path)
                print(f"  Successfully copied {filename}")
                copied_count += 1
                
            except Exception as e:
                print(f"  Error copying {filename}: {str(e)}")
                error_count += 1
    
    return combined_count, copied_count, error_count, len(common_files) + len(syllabus_only) + len(webpages_only)

def add_content_type_to_files(folder_path, verbose=False):
    """
    Add content_type: "course" to metadata of all JSON files in the folder.
    """
    json_files = [f for f in os.listdir(folder_path) if f.endswith('.json')]
    
    if not json_files:
        print("No JSON files found for content_type update")
        return 0, 0, 0
    
    print(f"\nAdding content_type metadata to {len(json_files)} files:")
    
    processed_count = 0
    error_count = 0
    skipped_count = 0
    
    for filename in sorted(json_files):
        file_path = os.path.join(folder_path, filename)
        
        try:
            # Load the JSON file
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Check if metadata exists
            if 'metadata' not in data:
                if verbose:
                    print(f"  Skipping {filename} (no metadata section)")
                skipped_count += 1
                continue
            
            # Check if content_type already exists
            if 'content_type' in data['metadata']:
                if verbose:
                    print(f"  Skipping {filename} (content_type already exists)")
                skipped_count += 1
                continue
            
            # Add content_type to metadata
            data['metadata']['content_type'] = 'course'
            
            # Write back to file
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            print(f"  Added content_type to {filename}")
            processed_count += 1
            
        except json.JSONDecodeError as e:
            print(f"  Error: Invalid JSON in {filename}: {str(e)}")
            error_count += 1
        except Exception as e:
            print(f"  Error processing {filename}: {str(e)}")
            error_count += 1
    
    return processed_count, error_count, skipped_count

def get_folder_summary(folder_path):
    """Get summary of JSON files in a folder."""
    if not os.path.exists(folder_path):
        return 0, []
    
    json_files = [f for f in os.listdir(folder_path) if f.endswith('.json')]
    return len(json_files), sorted(json_files)

def main():
    parser = argparse.ArgumentParser(
        description='Complete course data merger: combine common files and copy unique files for RAG system',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python merge_course_data.py data/json/courses_syllabus data/json/course_webpages data/json/courses_complete
  python merge_course_data.py data/json/courses_syllabus data/json/course_webpages data/json/courses_complete --dry-run -v
  python merge_course_data.py data/json/courses_syllabus data/json/course_webpages data/json/courses_complete --add-content-type
  
The script performs a complete merger:
1. COMBINES files that exist in both folders:
   - Uses syllabus as base structure
   - Adds metadata: iteration, study_pace, time, location, study_form, duration, application_period, application_code
   - Adds sections: Selection, Tuition
   - Appends webpages Additional information to syllabus Additional information

2. COPIES files that exist only in syllabus folder (preserves original structure)

3. COPIES files that exist only in webpages folder (preserves original structure)

4. OPTIONALLY adds "content_type": "course" to metadata (use --add-content-type)

Result: One complete folder with all available course data for your RAG system.
        """
    )
    
    parser.add_argument('syllabus_folder', 
                       help='Path to folder containing course syllabus JSON files')
    parser.add_argument('webpages_folder', 
                       help='Path to folder containing course webpages JSON files')
    parser.add_argument('output_folder', 
                       help='Path to output folder for complete course dataset')
    
    parser.add_argument('--dry-run', action='store_true',
                       help='Preview operations without making changes')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Show detailed file listings and operations')
    parser.add_argument('--add-content-type', action='store_true',
                       help='Add "content_type": "course" to metadata of all output files')
    
    args = parser.parse_args()
    
    # Validate input folders
    for folder, name in [(args.syllabus_folder, 'Syllabus'), (args.webpages_folder, 'Webpages')]:
        if not os.path.exists(folder):
            print(f"Error: {name} folder '{folder}' does not exist")
            return 1
        if not os.path.isdir(folder):
            print(f"Error: '{folder}' is not a directory")
            return 1
    
    print("Course Data Merger for RAG System")
    print("=" * 50)
    print(f"Syllabus folder: {args.syllabus_folder}")
    print(f"Webpages folder: {args.webpages_folder}")
    print(f"Output folder: {args.output_folder}")
    if args.dry_run:
        print("DRY RUN MODE - No files will be modified")
    print()
    
    # Get initial summaries
    syllabus_count, _ = get_folder_summary(args.syllabus_folder)
    webpages_count, _ = get_folder_summary(args.webpages_folder)
    output_count_before, _ = get_folder_summary(args.output_folder)
    
    print("Input Summary:")
    print(f"  Syllabus folder: {syllabus_count} JSON files")
    print(f"  Webpages folder: {webpages_count} JSON files")
    print(f"  Output folder: {output_count_before} JSON files (before operation)")
    print()
    
    try:
        combined_count, copied_count, error_count, total_processed = merge_course_data(
            args.syllabus_folder, 
            args.webpages_folder, 
            args.output_folder,
            dry_run=args.dry_run,
            verbose=args.verbose
        )
        
        if not args.dry_run:
            output_count_after, _ = get_folder_summary(args.output_folder)
            
            print("\nMerge Operation Complete!")
            print(f"  Files combined: {combined_count}")
            print(f"  Files copied: {copied_count}")
            print(f"  Errors encountered: {error_count}")
            print(f"  Total files processed: {total_processed}")
            print(f"  Final output folder: {output_count_after} JSON files")
            
            # Add content_type metadata if requested
            if args.add_content_type:
                content_processed, content_errors, content_skipped = add_content_type_to_files(
                    args.output_folder, verbose=args.verbose
                )
                print(f"\nContent Type Update Complete!")
                print(f"  Files updated with content_type: {content_processed}")
                print(f"  Files skipped: {content_skipped}")
                print(f"  Content type errors: {content_errors}")
                error_count += content_errors
            
            if error_count == 0:
                print(f"\nSuccess! Your RAG system now has complete course data in: {args.output_folder}")
                if args.add_content_type:
                    print("All files include content_type metadata for proper categorization.")
            else:
                print(f"\nCompleted with {error_count} errors. Check the output above for details.")
        else:
            print(f"\nDry run complete - {total_processed} files would be processed")
            if args.add_content_type:
                print("Content type metadata would also be added to all output files")
        
        return 0 if error_count == 0 else 1
        
    except Exception as e:
        print(f"\nFatal error during merge operation: {str(e)}")
        return 1

if __name__ == "__main__":
    exit(main()) 