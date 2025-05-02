import os
import json
import base64
from pathlib import Path
import google.generativeai as genai
from tqdm import tqdm
import argparse
from dotenv import load_dotenv

class GeminiParser:
    """Process course documents (PDF or Markdown) using Gemini API to extract structured content."""
    
    def __init__(self, pdf_dir=None, md_dir=None, output_dir="data/courses/json/", api_key=None):
        self.pdf_dir = pdf_dir
        self.md_dir = md_dir
        self.output_dir = output_dir
        self.model_name = "gemini-2.5-pro-preview-03-25"
        
        # Get API key from parameter or environment variable
        api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("API key is required. Either provide it as a parameter or set GEMINI_API_KEY in your .env file")
        
        # Initialize Gemini API
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(self.model_name)
        
        # Ensure output directory exists
        os.makedirs(self.output_dir, exist_ok=True)
    
    def encode_pdf(self, pdf_path):
        """Encode PDF file to base64 for API submission."""
        with open(pdf_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    
    def read_markdown(self, md_path):
        """Read markdown file content."""
        with open(md_path, "r", encoding="utf-8") as f:
            return f.read()
    
    def get_pdf_prompt(self):
        """Get the prompt for PDF extraction."""
        return """
        You are an expert at extracting structured information from course syllabus PDFs.
        
        Extract the following information from the PDF:
        1. Metadata: 
           - course_code (from the filename which is always course_code.pdf)
           - course_title
           - swedish_title
           - department
           - field_of_education
           - credits (only the number, not the text)
           - cycle
           - main_field_of_study
           - specialization 
           - language_of_instruction
           - confirmation_date
           - valid_from_date
           - programmes (as a list of strings)
        
        2. Sections: 
           - Confirmation
           - Position in the educational system
           - Entry requirements
           - Learning outcomes
           - Course content
           - Sub-courses
           - Form of teaching
           - Assessment
           - Grades
           - Course evaluation
           - Additional information
        
        Return the information in the following JSON format:
        {
          "metadata": {
            "source_document": "[filename]",
            "course_code": "[code]",
            "course_title": "[title]",
            "swedish_title": "[swedish title]",
            "department": "[department]",
            "field_of_education": "[field]",
            "credits": "[credits]",
            "cycle": "[cycle]",
            "main_field_of_study": "[main field]",
            "specialization": "[specialization]",
            "language_of_instruction": "[language]",
            "confirmation_date": "[date]",
            "valid_from_date": "[date]",
            "programmes": [
              "[programme names as list items]"
            ]
          },
          "sections": {
            "Confirmation": "[text]",
            "Position in the educational system": "[text]",
            "Entry requirements": "[text]",
            "Learning outcomes": "[text]",
            "Course content": "[text]",
            "Sub-courses": "[text]",
            "Form of teaching": "[text]",
            "Assessment": "[text]",
            "Grades": "[text]",
            "Course evaluation": "[text]",
            "Additional information": "[text]"
          }
        }
        
        Only return valid JSON, no explanations or other text.
        """
    
    def get_markdown_prompt(self):
        """Get the prompt for Markdown extraction."""
        return """
        You are an expert at extracting structured information from course syllabus markdown files.
        
        Extract the following information from the markdown:
        1. Metadata: 
           - course_code (from the filename which is always course_code.md)
           - course_title
           - swedish_title
           - department (if available)
           - credits (only the number, not the text)
           - cycle
           - language_of_instruction
           - confirmation_date (may be called "Decision date")
           - valid_from_date (may be called "Valid from semester" or similar)
           - programmes (as a list of strings, look in the "Position" section)
        
        2. Sections (map to these exact keys in the output): 
           - Position in the educational system (from "Position")
           - Entry requirements
           - Course content (may be just "Content")
           - Learning outcomes (may be "Objectives")
           - Sub-courses
           - Form of teaching
           - Assessment (from "Examination formats")
           - Grades
           - Course evaluation
           - Additional information (from "Other regulations")
        
        Return the information in the following JSON format:
        {
          "metadata": {
            "source_document": "[filename]",
            "course_code": "[code]",
            "course_title": "[title]",
            "swedish_title": "[swedish title]",
            "department": "[department]",
            "credits": "[credits]",
            "cycle": "[cycle]",
            "language_of_instruction": "[language]",
            "confirmation_date": "[date]",
            "valid_from_date": "[date]",
            "programmes": [
              "[programme names as list items]"
            ]
          },
          "sections": {
            "Position in the educational system": "[text]",
            "Entry requirements": "[text]",
            "Learning outcomes": "[text]",
            "Course content": "[text]",
            "Sub-courses": "[text]",
            "Form of teaching": "[text]",
            "Assessment": "[text]",
            "Grades": "[text]",
            "Course evaluation": "[text]",
            "Additional information": "[text]"
          }
        }
        
        Only return valid JSON, no explanations or other text. Be sure to map the section names correctly even if they have different names in the original markdown.
        """
    
    def process_pdf(self, pdf_path):
        """Process a single PDF file with Gemini API."""
        filename = os.path.basename(pdf_path)
        print(f"Processing PDF: {filename}...")
        
        # Check if output file already exists
        output_path = os.path.join(self.output_dir, f"{os.path.splitext(filename)[0]}.json")
        if os.path.exists(output_path):
            print(f"Output file already exists for {filename}, skipping.")
            return
            
        try:
            # Encode PDF file
            pdf_base64 = self.encode_pdf(pdf_path)
            
            # Create prompt for Gemini
            prompt = self.get_pdf_prompt()
            
            # Create the content parts for multimodal generation
            content_parts = [
                {"text": prompt},
                {
                    "inline_data": {
                        "mime_type": "application/pdf",
                        "data": pdf_base64
                    }
                }
            ]
            
            # Generate response from Gemini
            response = self.model.generate_content(content_parts)
            
            # Extract JSON from response
            json_str = response.text
            
            # Clean up the response to ensure it's valid JSON
            # Remove markdown code block markers if present
            json_str = json_str.replace("```json", "").replace("```", "").strip()
            
            # Parse JSON to validate
            parsed_json = json.loads(json_str)
            
            # Add source document to metadata if not present
            if "metadata" in parsed_json and "source_document" not in parsed_json["metadata"]:
                parsed_json["metadata"]["source_document"] = filename
                
            # Write to output file
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(parsed_json, f, indent=2, ensure_ascii=False)
                
            print(f"Successfully extracted and saved data for {filename}")
            return parsed_json
                
        except Exception as e:
            print(f"Error processing {filename}: {e}")
            return None
    
    def process_markdown(self, md_path):
        """Process a single Markdown file with Gemini API."""
        filename = os.path.basename(md_path)
        print(f"Processing Markdown: {filename}...")
        
        # Check if output file already exists
        output_path = os.path.join(self.output_dir, f"{os.path.splitext(filename)[0]}.json")
        if os.path.exists(output_path):
            print(f"Output file already exists for {filename}, skipping.")
            return
            
        try:
            # Read markdown file
            md_content = self.read_markdown(md_path)
            
            # Create prompt for Gemini
            prompt = self.get_markdown_prompt()
            
            # Create the content parts for generation
            content_parts = [
                {"text": prompt + "\n\nHere is the markdown content:\n\n" + md_content}
            ]
            
            # Generate response from Gemini
            response = self.model.generate_content(content_parts)
            
            # Extract JSON from response
            json_str = response.text
            
            # Clean up the response to ensure it's valid JSON
            # Remove markdown code block markers if present
            json_str = json_str.replace("```json", "").replace("```", "").strip()
            
            # Parse JSON to validate
            parsed_json = json.loads(json_str)
            
            # Add source document to metadata if not present
            if "metadata" in parsed_json and "source_document" not in parsed_json["metadata"]:
                parsed_json["metadata"]["source_document"] = filename
                
            # Write to output file
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(parsed_json, f, indent=2, ensure_ascii=False)
                
            print(f"Successfully extracted and saved data for {filename}")
            return parsed_json
                
        except Exception as e:
            print(f"Error processing {filename}: {e}")
            return None
    
    def process_directory(self, file_type="pdf"):
        """Process all files of specified type in the directory."""
        if file_type == "pdf" and self.pdf_dir:
            files = list(Path(self.pdf_dir).glob("*.pdf"))
            process_func = self.process_pdf
        elif file_type == "md" and self.md_dir:
            files = list(Path(self.md_dir).glob("*.md"))
            process_func = self.process_markdown
        else:
            raise ValueError(f"Invalid file type: {file_type} or directory not specified")
        
        results = []
        for file in tqdm(files, desc=f"Processing {file_type.upper()} files"):
            result = process_func(file)
            if result:
                results.append(result)
        
        print(f"Processed {len(results)} {file_type.upper()} files out of {len(files)} files")
        return results


def main():
    """Main execution function."""
    # Load environment variables from .env file
    load_dotenv()
    
    parser = argparse.ArgumentParser(description="Process course documents using Gemini API")
    parser.add_argument("--api_key", help="Google API key for Gemini (optional if set in .env file)")
    parser.add_argument("--pdf", action="store_true", help="Process PDF files")
    parser.add_argument("--md", action="store_true", help="Process Markdown files")
    parser.add_argument("--pdf_dir", default="data/courses/pdf/", help="Directory containing PDF files")
    parser.add_argument("--md_dir", default="data/firecrawl_courses_syllabus/", help="Directory containing Markdown files")
    parser.add_argument("--output_dir", default="data/courses/json/", help="Directory for JSON output")
    
    args = parser.parse_args()
    
    # Ensure at least one file type is selected
    if not (args.pdf or args.md):
        parser.error("You must specify at least one file type to process (--pdf or --md)")
    
    processor = GeminiParser(
        api_key=args.api_key,
        pdf_dir=args.pdf_dir if args.pdf else None,
        md_dir=args.md_dir if args.md else None,
        output_dir=args.output_dir
    )
    
    results = []
    
    # Process PDF files if requested
    if args.pdf:
        pdf_results = processor.process_directory(file_type="pdf")
        results.extend(pdf_results)
    
    # Process Markdown files if requested
    if args.md:
        md_results = processor.process_directory(file_type="md")
        results.extend(md_results)
    
    # Display sample of first result if available
    if results:
        sample = results[0]
        print("\nSample result:")
        print(f"Course: {sample['metadata']['course_code']} - {sample['metadata']['course_title']}")
        print(f"Sections extracted: {len(sample['sections'])}")


if __name__ == "__main__":
    main() 