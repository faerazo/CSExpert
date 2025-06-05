import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from parent directory
load_dotenv(dotenv_path="../.env")

def check_environment():
    """Check if the environment is properly set up."""
    # Check if Gemini API key is set
    if not os.getenv("GEMINI_API_KEY"):
        print("❌ Error: GEMINI_API_KEY environment variable not set")
        print("Please set your Google API key in a .env file or environment variable")
        print("Example: export GEMINI_API_KEY='your_api_key_here'")
        return False
    
    # Check if data directories exist
    data_dirs = [
        "../data/json/courses_syllabus",
        "../data/json/course_webpages"
    ]
    
    missing_dirs = []
    for dir_path in data_dirs:
        if not Path(dir_path).exists():
            missing_dirs.append(dir_path)
    
    if missing_dirs:
        print("❌ Error: Missing required data directories:")
        for missing_dir in missing_dirs:
            print(f"  - {missing_dir}")
        print("\nPlease ensure your JSON course data is available in the correct directories.")
        return False
    
    print("✅ Environment check passed")
    return True

def main():
    """Main startup function."""
    print("🚀 Starting CSExpert Backend Server...")
    
    # Check environment
    if not check_environment():
        sys.exit(1)
    
    # Set default environment variables
    os.environ.setdefault("APP_HOST", "0.0.0.0")
    os.environ.setdefault("APP_PORT", "8000")
    os.environ.setdefault("DEBUG", "True")
    
    print(f"📍 Server will run on http://{os.getenv('APP_HOST')}:{os.getenv('APP_PORT')}")
    print("📚 Loading course and program data...")
    print("🔄 This may take a few moments on first startup...")
    
    # Import and run the server
    try:
        import uvicorn
        
        # Use import string format to enable reload properly
        uvicorn.run(
            "main:app",  # Import string format instead of importing app directly
            host=os.getenv("APP_HOST"),
            port=int(os.getenv("APP_PORT")),
            reload=os.getenv("DEBUG").lower() == "true",
            log_level="info"
        )
    except ImportError as e:
        print(f"❌ Error: Missing required package: {e}")
        print("Please install required packages: pip install -r requirements.txt")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error starting server: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 