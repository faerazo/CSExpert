import os
from pathlib import Path
import re

def extract_course_code(filename):
    # Try different patterns in order:
    patterns = [
        r'[-_]([a-zA-Z]+\d+[a-zA-Z0-9]*)$',  # Handles: EN2D04, AF1212
        r'[-_]([A-Z]+(?:ECD|CD|POL)?)$',      # Handles: FKAECD, VFSPOL
        r'[-_]([A-Z0-9]+)$'                    # Fallback for any remaining alphanumeric codes
    ]
    
    for pattern in patterns:
        match = re.search(pattern, filename)
        if match:
            return match.group(1)
    
    # If no pattern matches, try to find the code in the filename
    parts = filename.split('-')
    if parts:
        last_part = parts[-1].upper()
        if any(char.isdigit() for char in last_part) or len(last_part) >= 4:
            return last_part
    
    return None

def rename_pdf_files(md_dir, pdf_dir):
    # Get all MD files and create a mapping of course codes to full names
    code_to_name = {}
    
    # Convert paths to Path objects
    md_path = Path(md_dir)
    pdf_path = Path(pdf_dir)
    
    # Debug: Print all MD files first
    print("Processing MD files:")
    for md_file in md_path.glob('*.md'):
        course_code = extract_course_code(md_file.stem)
        if course_code:
            print(f"MD file: {md_file.stem} -> Code: {course_code}")
            # Store both uppercase and lowercase versions
            code_to_name[course_code.lower()] = md_file.stem
            code_to_name[course_code.upper()] = md_file.stem
        else:
            print(f"Warning: Could not extract code from {md_file.stem}")
    
    # Debug: Print all PDF files
    print("\nProcessing PDF files:")
    for pdf_file in pdf_path.glob('*.pdf'):
        print(f"Found PDF: {pdf_file.stem}")
        current_name = pdf_file.stem
        
        # Try both the original name and uppercase version
        if current_name in code_to_name:
            new_name = code_to_name[current_name] + '.pdf'
        elif current_name.upper() in code_to_name:
            new_name = code_to_name[current_name.upper()] + '.pdf'
        else:
            print(f"Warning: No matching MD file found for {current_name}")
            continue
            
        new_path = pdf_file.parent / new_name
        
        try:
            pdf_file.rename(new_path)
            print(f"Successfully renamed: {pdf_file.name} -> {new_name}")
        except Exception as e:
            print(f"Error renaming {pdf_file.name}: {e}")

# Example usage
md_directory = "data/courses/md"
pdf_directory = "data/courses/pdf"

rename_pdf_files(md_directory, pdf_directory)