import os
import re
import json
from pathlib import Path
import pandas as pd
from pypdf import PdfReader
from langchain.text_splitter import RecursiveCharacterTextSplitter
import matplotlib.pyplot as plt
from tqdm import tqdm

class CourseDocumentProcessor:
    """Process course PDFs to extract structured content and metadata."""
    
    def __init__(self, pdf_dir="data/courses/pdf/"):
        self.pdf_dir = pdf_dir
        self.section_patterns = [
            # Common section headers in course documents
            (r'Title|Course name|Course code', "Course Information"),
            (r'Confirmation', "Confirmation"),
            (r'Position in the educational system|Position in educational system', "Position in Educational System"),
            (r'Entry [Rr]equirements?', "Entry Requirements"),
            (r'Learning [Oo]utcomes?|On completion of the course', "Learning Outcomes"),
            (r'Course [Cc]ontent', "Course Content"),
            (r'Form[s]? of [Tt]eaching|Teaching [Ff]orms?', "Teaching Forms"),
            (r'Assessment|Examination|Forms of examination', "Assessment"),
            (r'Grades', "Grades"),
            (r'Course [Ee]valuation', "Course Evaluation"),
            (r'Additional [Ii]nformation', "Additional Information"),
            (r'About|Course description', "About"),
            (r'Prerequisites and selection', "Prerequisites and Selection"),
            (r'Literature', "Literature"),
            (r'Contact information', "Contact Information")
        ]
        
        # Regex patterns for metadata extraction
        self.metadata_patterns = {
            "course_code": r'([A-Z]{2,3}\d{3,4})',
            "credits": r'(\d+(?:\.\d+)?)\s*credits|hp|högskolepoäng',
            "level": r'([Ff]irst|[Ss]econd|[Tt]hird)\s*[Cc]ycle|([Bb]asic|[Aa]dvanced)\s*[Ll]evel|[Bb]achelor\'s\s*[Ll]evel|[Mm]aster\'s\s*[Ll]evel',
            "department": r'Department of ([^,\n]+)',
            "faculty": r'Faculty of ([^,\n]+)'
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
            sections = self.find_section_boundaries(text)
            for i, section in enumerate(sections):
                print(f"\n--- Section {i+1}: {section['section_name']} ---")
                print(f"Start line: {section['start_line']}, End line: {section['end_line']}")
                header_text = section['text'].split('\n')[0]
                print(f"Header: {header_text}")
                print(f"Preview: {section['text'][:200]}...")
            
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
            "credits": "Unknown",
            "level": "Unknown",
            "department": "Unknown",
            "faculty": "Unknown"
        }
        
        # Extract course code
        course_code_match = re.search(self.metadata_patterns["course_code"], text)
        if course_code_match:
            metadata["course_code"] = course_code_match.group(0)
        
        # Extract course title - Look for heading or title patterns
        title_patterns = [
            r'# (.*?)(?:\n|$)',                           # Markdown heading
            rf'{metadata["course_code"]}\s+(.*?)(?:\n|$)', # Title following code
            r'Course:\s+(.*?)(?:\n|$)',                   # Explicit course label
            r'^(.*?)(?:\n|$)'                             # First line as fallback
        ]
        
        for pattern in title_patterns:
            title_match = re.search(pattern, text, re.MULTILINE)
            if title_match:
                potential_title = title_match.group(1).strip()
                if len(potential_title) > 3 and len(potential_title) < 100 and metadata["course_code"] not in potential_title:
                    metadata["course_title"] = potential_title
                    break
        
        # Extract credits
        credits_match = re.search(self.metadata_patterns["credits"], text, re.IGNORECASE)
        if credits_match:
            metadata["credits"] = credits_match.group(1)
        
        # Extract level
        level_match = re.search(self.metadata_patterns["level"], text, re.IGNORECASE)
        if level_match:
            for group in level_match.groups():
                if group:
                    metadata["level"] = group.strip()
                    break
        
        # Extract department
        dept_match = re.search(self.metadata_patterns["department"], text, re.IGNORECASE)
        if dept_match:
            metadata["department"] = dept_match.group(1).strip()
        
        # Extract faculty
        faculty_match = re.search(self.metadata_patterns["faculty"], text, re.IGNORECASE)
        if faculty_match:
            metadata["faculty"] = faculty_match.group(1).strip()
        
        return metadata
    
    def find_section_boundaries(self, text):
        """Identify section boundaries in the text."""
        # Find potential section headers
        section_markers = []
        
        # Check each line for section-like patterns
        lines = text.split('\n')
        
        # First pass - identify clear section headers
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
                
            # Check if the line looks like a section header
            for pattern, section_name in self.section_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    section_markers.append({
                        "line_num": i,
                        "section_name": section_name,
                        "header_text": line
                    })
                    break
        
        # Sort sections by their position in the document
        section_markers.sort(key=lambda x: x["line_num"])
        
        # Now determine section content ranges
        sections = []
        for i, marker in enumerate(section_markers):
            start_line = marker["line_num"]
            
            # Set end_line to the start of the next section or end of document
            if i < len(section_markers) - 1:
                end_line = section_markers[i+1]["line_num"]
            else:
                end_line = len(lines)
            
            # Extract section text
            section_text = '\n'.join(lines[start_line:end_line]).strip()
            
            sections.append({
                "section_name": marker["section_name"],
                "section_id": marker["section_name"].lower().replace(' ', '_'),
                "text": section_text,
                "start_line": start_line,
                "end_line": end_line
            })
        
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
            
            # Find section boundaries
            sections = self.find_section_boundaries(text)
            
            # Create section chunks with metadata
            chunks = []
            for i, section in enumerate(sections):
                section_metadata = metadata.copy()
                section_metadata.update({
                    "section": section["section_name"],
                    "section_id": section["section_id"],
                    "chunk_type": "section_content",
                    "position": i
                })
                
                chunks.append({
                    "metadata": section_metadata,
                    "text": section["text"]
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
    
    def visualize_sections(self):
        """Visualize the distribution of identified sections."""
        if not self.chunks:
            print("No chunks available. Process PDFs first.")
            return
        
        # Count sections
        section_counts = {}
        for chunk in self.chunks:
            section = chunk["metadata"].get("section", "Unknown")
            section_counts[section] = section_counts.get(section, 0) + 1
        
        # Plot
        plt.figure(figsize=(12, 6))
        plt.bar(section_counts.keys(), section_counts.values())
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()
        plt.title("Section Distribution in Course Documents")
        plt.savefig("section_distribution.png")
        plt.close()
        
        print(f"Generated section distribution visualization (section_distribution.png)")
    
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
    parser.add_argument("--max_tokens", type=int, default=500, help="Maximum tokens per chunk")
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
    
    # Visualize section distribution
    processor.visualize_sections()
    
    # Display sample chunks
    if chunks:
        print("\nSample chunks:")
        for i, chunk in enumerate(chunks[:3]):
            print(f"\n--- Chunk {i+1} ---")
            print(f"Section: {chunk['metadata']['section']}")
            print(f"Course: {chunk['metadata']['course_code']} - {chunk['metadata']['course_title']}")
            print(f"Text preview: {chunk['text'][:100]}...")

if __name__ == "__main__":
    main()