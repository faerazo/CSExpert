from firecrawl import FirecrawlApp
import os
import time
from dotenv import load_dotenv
import re

load_dotenv()

app = FirecrawlApp(api_key=os.getenv('FIRECRAWL_API_KEY'))

os.makedirs('data/firecrawl_courses_pages', exist_ok=True)

RATE_LIMIT_DELAY = 6.5  # seconds between requests
RATE_LIMIT_EXCEEDED_DELAY = 31  # seconds to wait when rate limit is hit

with open('data/urls/course_pages_urls.txt', 'r') as file:
    for url in file:
        url = url.strip()
        
        # Extract course code using patterns that work for both URL formats
        # Format 1: .../course-name-dit123/syllabus/...
        # Format 2: .../course-name-dit123
        
        # Try to match pattern 1 (syllabus URLs)
        course_code_match = re.search(r'-(dit\d+|msg\d+|mma\d+|tia\d+|lt\d+)/syllabus/', url, re.IGNORECASE)
        
        # If no match, try pattern 2 (course page URLs ending with course code)
        if not course_code_match:
            course_code_match = re.search(r'-(dit\d+|msg\d+|mma\d+|tia\d+|lt\d+)$', url, re.IGNORECASE)
        
        if course_code_match:
            course_code = course_code_match.group(1).upper()
            filename = f"{course_code}.md"
        else:
            # Fallback to original method if no course code found
            filename = url.rstrip('/').split('/')[-1] + '.md'
            print(f"Warning: Could not extract course code from {url}")
            
        filepath = os.path.join('data', 'firecrawl_courses_pages', filename)
        
        # Skip if file already exists
        if os.path.exists(filepath):
            print(f"Skipping {filename} - already exists")
            continue
            
        try:
            print(f"Processing URL: {url}")
            response = app.scrape_url(url=url, params={
                'formats': ['markdown'],
            })
            with open(filepath, 'w') as f:
                f.write(response['markdown'])
            print(f"Successfully saved: {filename}")
            time.sleep(RATE_LIMIT_DELAY)
        except Exception as e:
            print(f"Error processing URL {url}: {str(e)}")
            if "429" in str(e):  # Rate limit exceeded
                print(f"Rate limit exceeded. Waiting {RATE_LIMIT_EXCEEDED_DELAY} seconds...")
                time.sleep(RATE_LIMIT_EXCEEDED_DELAY)
            else:
                time.sleep(RATE_LIMIT_DELAY)