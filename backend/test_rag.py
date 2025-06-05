import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from parent directory
load_dotenv(dotenv_path="../.env")

# Add backend directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_environment():
    """Test if environment is set up correctly."""
    print("🧪 Testing Environment Setup...")
    
    # Check Gemini API key
    if not os.getenv("GEMINI_API_KEY"):
        print("❌ GEMINI_API_KEY not set")
        return False
    else:
        print("✅ GEMINI_API_KEY is set")
    
    # Check data directories
    json_dirs = {
        "courses_syllabus": "../data/json/courses_syllabus",
        "course_webpages": "../data/json/course_webpages"
    }
    
    for name, path in json_dirs.items():
        if Path(path).exists():
            files = list(Path(path).glob("*.json"))
            print(f"✅ {name}: {len(files)} JSON files found")
        else:
            print(f"❌ {name}: Directory not found at {path}")
            return False
    
    return True

def test_rag_system():
    """Test the RAG system initialization and basic functionality."""
    print("\n🧪 Testing RAG System...")
    
    try:
        from rag_system import GothenburgUniversityRAG
        
        # Initialize RAG system
        print("📚 Initializing RAG system...")
        json_dirs = {
            "courses_syllabus": "../data/json/courses_syllabus",
            "course_webpages": "../data/json/course_webpages"
        }
        
        rag = GothenburgUniversityRAG(json_dirs=json_dirs)
        print("✅ RAG system created")
        
        # Initialize vector store
        print("🔄 Initializing vector store (this may take a while)...")
        num_docs = rag.initialize_vector_store()
        print(f"✅ Vector store initialized with {num_docs} document chunks")
        
        # Test system info
        info = rag.get_system_info()
        print(f"📊 System Status: {info['status']}")
        print(f"📋 Total Documents: {info.get('total_documents', 'N/A')}")
        print(f"📖 Course Documents: {info.get('course_documents', 'N/A')}")
        print(f"🎓 Program Documents: {info.get('program_documents', 'N/A')}")
        
        return rag
        
    except Exception as e:
        print(f"❌ Error initializing RAG system: {e}")
        return None

def test_queries(rag):
    """Test various types of queries."""
    print("\n🧪 Testing Queries...")
    
    test_queries = [
        "What is DIT005 about?",
        "Tell me about the prerequisites for TIA560",
        "What are the learning outcomes for Project Management for Strategic Communication?",
        "List all Computer Science courses",
        "What programs are available?"
    ]
    
    for i, query in enumerate(test_queries, 1):
        print(f"\n🔍 Test Query {i}: {query}")
        try:
            result = rag.query(query)
            print(f"📝 Answer: {result['answer'][:200]}...")
            print(f"🎯 Content Type: {result['content_type']}")
            print(f"📚 Sources: {len(result['sources'])}")
            print(f"📄 Documents Retrieved: {result['num_documents_retrieved']}")
        except Exception as e:
            print(f"❌ Error: {e}")

def test_specific_courses():
    """Test queries about specific courses from the JSON data."""
    print("\n🧪 Testing Specific Courses...")
    
    # Get a few course codes from the data
    courses_dir = Path("../data/json/courses_syllabus")
    if courses_dir.exists():
        json_files = list(courses_dir.glob("*.json"))[:3]  # Test first 3 courses
        
        for json_file in json_files:
            course_code = json_file.stem
            print(f"\n📖 Testing course: {course_code}")
            
            # Load the JSON to see what's available
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    title = data.get('metadata', {}).get('course_title', 'Unknown')
                    print(f"📚 Title: {title}")
            except Exception as e:
                print(f"❌ Error reading {json_file}: {e}")

def main():
    """Main test function."""
    print("🚀 CSExpert RAG System Test Suite")
    print("=" * 50)
    
    # Test environment
    if not test_environment():
        print("\n❌ Environment test failed. Please check your setup.")
        sys.exit(1)
    
    # Test RAG system
    rag = test_rag_system()
    if not rag:
        print("\n❌ RAG system test failed.")
        sys.exit(1)
    
    # Test queries
    test_queries(rag)
    
    # Test specific courses
    test_specific_courses()
    
    print("\n✅ All tests completed!")
    print("🎉 Your CSExpert system is ready to use!")

if __name__ == "__main__":
    main() 