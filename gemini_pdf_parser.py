import os
import json
import base64
from pathlib import Path
import google.generativeai as genai
from tqdm import tqdm
import argparse
from dotenv import load_dotenv

class GeminiPDFParser:
    """Process course PDFs using Gemini API to extract structured content."""
    
    def __init__(self, pdf_dir="data/courses/pdf/", output_dir="data/courses/json/", api_key=None):
        self.pdf_dir = pdf_dir
        self.output_dir = output_dir
        self.model_name = "gemini-2.5-pro-exp-03-25"
        
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
    
    def process_pdf(self, pdf_path):
        """Process a single PDF file with Gemini API."""
        filename = os.path.basename(pdf_path)
        print(f"Processing {filename}...")
        
        # Check if output file already exists
        output_path = os.path.join(self.output_dir, f"{os.path.splitext(filename)[0]}.json")
        if os.path.exists(output_path):
            print(f"Output file already exists for {filename}, skipping.")
            return
            
        try:
            # Encode PDF file
            pdf_base64 = self.encode_pdf(pdf_path)
            
            # Create prompt for Gemini
            prompt = """
            You are an expert at extracting structured information from course syllabus PDFs.
            
            Extract the following information from the PDF:
            1. Metadata: 
               - course_code (from the filename which is always course_code.pdf)
               - course_title
               - swedish_title
               - department
               - field_of_education
               - credits
               - swedish_credits
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
                "swedish_credits": "[swedish credits]",
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
    
    def process_directory(self):
        """Process all PDFs in the directory."""
        pdf_files = list(Path(self.pdf_dir).glob("*.pdf"))
        
        results = []
        for pdf_file in tqdm(pdf_files, desc="Processing PDFs"):
            result = self.process_pdf(pdf_file)
            if result:
                results.append(result)
        
        print(f"Processed {len(results)} PDFs out of {len(pdf_files)} files")
        return results


def main():
    """Main execution function."""
    # Load environment variables from .env file
    load_dotenv()
    
    parser = argparse.ArgumentParser(description="Process course PDFs using Gemini API")
    parser.add_argument("--api_key", help="Google API key for Gemini (optional if set in .env file)")
    parser.add_argument("--pdf", default="data/courses/pdf/", help="Directory containing PDF files")
    parser.add_argument("--output", default="data/courses/json/", help="Directory for JSON output")
    
    args = parser.parse_args()
    
    processor = GeminiPDFParser(
        api_key=args.api_key,
        pdf_dir=args.pdf,
        output_dir=args.output
    )
    
    results = processor.process_directory()
    
    # Display sample of first result if available
    if results:
        sample = results[0]
        print("\nSample result:")
        print(f"Course: {sample['metadata']['course_code']} - {sample['metadata']['course_title']}")
        print(f"Sections extracted: {len(sample['sections'])}")


if __name__ == "__main__":
    main() 