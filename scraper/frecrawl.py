from firecrawl import FirecrawlApp
import os
import time
from dotenv import load_dotenv

load_dotenv()

app = FirecrawlApp(api_key=os.getenv('FIRECRAWL_API_KEY'))

os.makedirs('data/website', exist_ok=True)

RATE_LIMIT_DELAY = 6.5  # seconds between requests
RATE_LIMIT_EXCEEDED_DELAY = 31  # seconds to wait when rate limit is hit

with open('course_urls_formatted1.txt', 'r') as file:
    for url in file:
        url = url.strip()
        filename = url.rstrip('/').split('/')[-1] + '.md'
        filepath = os.path.join('data', 'website', filename)
        
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