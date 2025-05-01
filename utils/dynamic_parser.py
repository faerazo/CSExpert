import os
import re
import json
from pathlib import Path
import pandas as pd
from pypdf import PdfReader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from tqdm import tqdm

class CourseDocumentProcessor:
    """Process course PDFs to extract structured content and metadata."""
    
    def __init__(self, pdf_dir="data/courses/pdf/"):
        self.pdf_dir = pdf_dir
        self.section_patterns = [
            # Precise section headers in course documents
            (r'^Confirmation$', "Confirmation"),
            (r'^Field\s+of\s+education', "Field of education"),
            (r'^Department', "Department"),
            (r'^Position\s+in\s+the\s+educational\s+system', "Position in the educational system"),
            (r'^Entry\s+[Rr]equirements', "Entry requirements"),
            (r'^Learning\s+[Oo]utcomes', "Learning outcomes"),
            (r'^Course\s+[Cc]ontent', "Course content"),
            (r'^Sub-courses', "Sub-courses"),
            (r'^Form\s+of\s+[Tt]eaching|^Teaching\s+[Ff]orms', "Form of teaching"),
            (r'^Assessment|^Examination', "Assessment"),
            (r'^Grades', "Grades"),
            (r'^Course\s+[Ee]valuation', "Course evaluation"),
            (r'^Additional\s+[Ii]nformation', "Additional information")
        ]
        
        # Learning outcomes subsection patterns (now handled differently)
        self.learning_outcome_subsections = [
            "Knowledge and understanding",
            "Competence and skills",
            "Judgement and approach"
        ]
        
        # Regex patterns for metadata extraction
        self.metadata_patterns = {
            "course_code": r'([A-Z]{2,3}\d{3,4})',
            "credits": r'(\d+(?:\.\d+)?)\s*(?:credits|hp|högskolepoäng)',
            "level": r'([Ff]irst|[Ss]econd|[Tt]hird)\s*[Cc]ycle|([Bb]asic|[Aa]dvanced)\s*[Ll]evel|[Bb]achelor\'s\s*[Ll]evel|[Mm]aster\'s\s*[Ll]evel',
            "department": r'Department\s+of\s+([^,\n]+)',
            "faculty": r'Faculty\s+of\s+([^,\n]+)',
            "field_of_education": r'Field\s+of\s+education:\s*([^,\n]+)',
        }
        
        self.chunks = []
    
    def extract_text_from_pdf(self, pdf_path):
        """Extract all text from a PDF file."""
        try:
            reader = PdfReader(pdf_path)
            text = ""
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
            
            # Remove bullet points
            text = text.replace('•', '')
            
            return text
        except Exception as e:
            print(f"Error extracting text from {pdf_path}: {e}")
            return ""
    
    def debug_pdf_extraction(self, max_files=1):
        """Debug function to print the raw text extraction from PDFs."""
        pdf_files = list(Path(self.pdf_dir).glob("*.pdf"))
        
        if max_files:
            pdf_files = pdf_files[:max_files]
        
        for pdf_file in pdf_files:
            print(f"\n{'='*80}")
            print(f"DEBUG: Raw text extraction from {pdf_file}")
            print(f"{'='*80}")
            
            text = self.extract_text_from_pdf(pdf_file)
            print(text)
            
            print(f"\n{'='*80}")
            print(f"DEBUG: Attempted section extraction")
            print(f"{'='*80}")
            
            # Display identified sections
            sections = self.extract_structured_sections(text)
            for section_name, section_text in sections.items():
                print(f"\n--- Section: {section_name} ---")
                print(f"Content: {section_text[:150]}...")
            
            # Display identified metadata
            print(f"\n{'='*80}")
            print(f"DEBUG: Extracted metadata")
            print(f"{'='*80}")
            
            metadata = self.extract_metadata(text, os.path.basename(pdf_file))
            for key, value in metadata.items():
                print(f"{key}: {value}")
    
    def extract_metadata(self, text, filename):
        """Extract course metadata from the text."""
        metadata = {
            "source_document": filename,
            "course_code": "Unknown",
            "course_title": "Unknown",
            "department": "Unknown",
            "field_of_education": "Unknown",
            "credits": "Unknown",
            "programmes": None
        }
        
        # Extract course information from the footer line that contains both English and Swedish information
        # Look for a line like: "DIT930    Advanced databases, 7.5 credits / Avancerade databaser, 7,5 högskolepoäng"
        course_info_pattern = r'([A-Z]{2,3}\d{3,4})\s+([^,]+),\s*(\d+(?:\.\d+)?)\s*credits\s*/\s*([^,]+),\s*(\d+(?:,\d+)?)\s*högskolepoäng'
        course_info_match = re.search(course_info_pattern, text)
        
        if course_info_match:
            metadata["course_code"] = course_info_match.group(1).strip()
            metadata["course_title"] = course_info_match.group(2).strip()
            metadata["credits"] = course_info_match.group(3).strip()
            print(f"Extracted course info: {metadata['course_code']} - {metadata['course_title']} ({metadata['credits']} credits)")
        else:
            # Fallback to looking for just the English version
            simple_pattern = r'([A-Z]{2,3}\d{3,4})\s+([^,]+),\s*(\d+(?:\.\d+)?)\s*credits'
            simple_match = re.search(simple_pattern, text)
            if simple_match:
                metadata["course_code"] = simple_match.group(1).strip()
                metadata["course_title"] = simple_match.group(2).strip()
                metadata["credits"] = simple_match.group(3).strip()
                print(f"Extracted course info (simple): {metadata['course_code']} - {metadata['course_title']} ({metadata['credits']} credits)")
        
        # Extract field of education
        field_match = re.search(r'Field\s+of\s+education:\s*([^\n]+)', text, re.IGNORECASE)
        if field_match:
            metadata["field_of_education"] = field_match.group(1).strip()
        
        # Extract department
        dept_match = re.search(r'Department:\s*Department\s+of\s+([^,\n]+)', text, re.IGNORECASE)
        if dept_match:
            metadata["department"] = dept_match.group(1).strip()
        else:
            # Try alternative pattern
            alt_dept_match = re.search(r'Department\s+of\s+([^,\n]+)', text, re.IGNORECASE)
            if alt_dept_match:
                metadata["department"] = alt_dept_match.group(1).strip()
        
        # Extract programme information as a single text string - only the numbered list
        position_section = re.search(r'Position in the educational system.*?(?=\n\n|\Z)', text, re.DOTALL | re.IGNORECASE)
        if position_section:
            position_text = position_section.group(0)
            
            # Then extract just the programme list
            programme_list_match = re.search(r'following\s+programmes:\s*((?:\d\).*?)+)(?=\n\n|\Z)', position_text, re.DOTALL)
            if programme_list_match:
                programmes = programme_list_match.group(1).strip()
                programmes = re.sub(r'\n\s*\n', '\n', programmes)
                metadata["programmes"] = programmes
                print(f"Extracted programmes: {metadata['programmes']}")
        
        return metadata
    
    def extract_structured_sections(self, text):
        """Extract sections following the user's desired structure."""
        # Split text into lines for processing
        lines = text.split('\n')
        
        # Initialize sections dictionary with empty values for all desired sections
        sections = {
            "Confirmation": "",
            "Position in the educational system": "",
            "Entry requirements": "",
            "Learning outcomes": "",
            "Course content": "",
            "Sub-courses": "",
            "Form of teaching": "",
            "Assessment": "",
            "Grades": "",
            "Course evaluation": "",
            "Additional information": ""
        }
        
        # Find section boundaries for other sections
        section_boundaries = []
        for i, line in enumerate(lines):
            for pattern, section_name in self.section_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    section_boundaries.append((i, section_name))
                    break
        
        # Sort boundaries by line number
        section_boundaries.sort(key=lambda x: x[0])
        
        # Extract content for each section
        for i, (start_line, section_name) in enumerate(section_boundaries):
            # Skip if not in our target sections
            if section_name not in sections:
                continue
                
            # Determine end line (next section or end of document)
            if i < len(section_boundaries) - 1:
                end_line = section_boundaries[i+1][0]
            else:
                end_line = len(lines)
            
            # Extract and clean section content
            content = '\n'.join(lines[start_line:end_line]).strip()
            
            # Store in sections dictionary
            sections[section_name] = content
        
        return sections
    
    def extract_sections(self, pdf_path):
        """Extract structured sections from a PDF."""
        try:
            filename = os.path.basename(pdf_path)
            
            # Extract text
            text = self.extract_text_from_pdf(pdf_path)
            if not text:
                return []
                
            # Extract metadata
            metadata = self.extract_metadata(text, filename)
            
            # Extract structured sections
            sections_dict = self.extract_structured_sections(text)
            
            # Create section chunks with metadata
            chunks = []
            for i, (section_name, section_text) in enumerate(sections_dict.items()):
                if not section_text:  # Skip empty sections
                    continue
                
                section_metadata = metadata.copy()
                section_metadata.update({
                    "section": section_name,
                    "section_id": section_name.lower().replace(' ', '_'),
                    "chunk_type": "section_content",
                    "position": i
                })
                
                chunks.append({
                    "metadata": section_metadata,
                    "text": section_text
                })
            
            return chunks
            
        except Exception as e:
            print(f"Error processing {pdf_path}: {e}")
            return []
    
    def split_dense_sections(self, sections, max_tokens=500):
        """Split long sections into smaller chunks."""
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=max_tokens,
            chunk_overlap=50,
            separators=["\n\n", "\n", ". ", " ", ""]
        )
        
        result = []
        for section in sections:
            if len(section["text"].split()) > max_tokens:
                # Split text while preserving context
                texts = text_splitter.split_text(section["text"])
                
                # Create chunks with consistent metadata but added sub-positions
                for i, chunk in enumerate(texts):
                    new_metadata = section["metadata"].copy()
                    new_metadata.update({
                        "sub_position": i,
                        "is_split": True,
                        "total_splits": len(texts)
                    })
                    
                    result.append({
                        "metadata": new_metadata,
                        "text": chunk
                    })
            else:
                result.append(section)
        
        return result
    
    def process_directory(self, max_files=None, max_tokens=500):
        """Process all PDFs in the directory."""
        pdf_files = list(Path(self.pdf_dir).glob("*.pdf"))
        
        if max_files:
            pdf_files = pdf_files[:max_files]
        
        self.chunks = []
        
        for pdf_file in tqdm(pdf_files, desc="Processing PDFs"):
            sections = self.extract_sections(pdf_file)
            chunked_sections = self.split_dense_sections(sections, max_tokens)
            self.chunks.extend(chunked_sections)
        
        return self.chunks
    
    def export_to_csv(self, filename="course_chunks.csv"):
        """Export chunks to CSV for review."""
        if not self.chunks:
            print("No chunks available. Process PDFs first.")
            return
            
        # Flatten the data structure for CSV export
        rows = []
        for chunk in self.chunks:
            row = chunk["metadata"].copy()
            row["text"] = chunk["text"]
            rows.append(row)
        
        df = pd.DataFrame(rows)
        df.to_csv(filename, index=False)
        print(f"Exported {len(rows)} chunks to {filename}")
    
    def export_to_json(self, filename="course_chunks.json"):
        """Export chunks to JSON for review."""
        if not self.chunks:
            print("No chunks available. Process PDFs first.")
            return
            
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.chunks, f, indent=2, ensure_ascii=False)
        
        print(f"Exported {len(self.chunks)} chunks to {filename}")

def main():
    """Main execution function."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Process course PDFs to extract structured content")
    parser.add_argument("--pdf_dir", default="data/courses/pdf/", help="Directory containing PDF files")
    parser.add_argument("--max_files", type=int, default=None, help="Maximum number of files to process")
    parser.add_argument("--max_tokens", type=int, default=1000, help="Maximum tokens per chunk")
    parser.add_argument("--output_format", choices=["csv", "json", "both"], default="both", 
                        help="Output format for results")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode to print raw PDF extraction")
    parser.add_argument("--debug_files", type=int, default=1, help="Number of files to debug (when debug mode is enabled)")
    
    args = parser.parse_args()
    
    processor = CourseDocumentProcessor(pdf_dir=args.pdf_dir)
    
    # If debug mode is enabled, run the debug extraction and exit
    if args.debug:
        processor.debug_pdf_extraction(max_files=args.debug_files)
        return
    
    chunks = processor.process_directory(max_files=args.max_files, max_tokens=args.max_tokens)
    
    print(f"Processed {len(chunks)} chunks from PDFs in {args.pdf_dir}")
    
    # Export results
    if args.output_format in ["csv", "both"]:
        processor.export_to_csv()
    
    if args.output_format in ["json", "both"]:
        processor.export_to_json()
    
    # Display sample chunks
    if chunks:
        print("\nSample chunks:")
        for i, chunk in enumerate(chunks[:3]):
            print(f"\n--- Chunk {i+1} ---")
            print(f"Section: {chunk['metadata']['section']}")
            print(f"Course: {chunk['metadata']['course_code']} - {chunk['metadata']['course_title']}")
            print(f"Text preview: {chunk['text']}")

if __name__ == "__main__":
    main()