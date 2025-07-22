# CSExpert Backend

A RAG-powered (Retrieval Augmented Generation) backend API for Gothenburg University's Computer Science course and program information system.

## Overview

CSExpert Backend provides an intelligent conversational interface for querying course and program information. It uses a vector database for semantic search and Google's Gemini LLM for natural language understanding and response generation.

### Key Features
- 🤖 Natural language queries about courses and programs
- 🔍 Semantic search across 4500+ course documents
- 📚 Comprehensive course and program information
- 🔗 Direct links to syllabi and course pages
- ⚡ Fast response with intelligent caching
- 🛡️ Rate limiting for API protection

## Architecture

**Data Flow:**
1. **SQLite Database** → stores course/program data
2. **Document Loader** → converts database records to searchable documents
3. **ChromaDB** → stores document embeddings for semantic search
4. **RAG System** → retrieves relevant documents and generates responses
5. **FastAPI** → serves HTTP endpoints to clients
6. **Gemini LLM** → generates natural language responses

## Components

### `main.py`
FastAPI application serving REST endpoints for:
- Chat interactions
- Course/program data retrieval
- System health and status

### `rag_system.py`
Core RAG implementation featuring:
- Intelligent query routing (course/program/both)
- Multi-query semantic search
- Context-aware response generation
- Response caching

### `database_document_loader.py`
Converts SQLite data into searchable documents:
- Course overviews with metadata
- Course sections (prerequisites, content, etc.)
- Program information and course lists
- URL integration (syllabus/course pages)

### `config.py`
Centralized configuration management:
- LLM settings (model, temperature, tokens)
- Search parameters
- Cache configuration
- Rate limiting settings

### `rate_limiter.py`
Token bucket rate limiting implementation:
- Per-client request limiting
- Configurable time windows

## API Endpoints

### Chat
- `POST /chat` - Main conversational endpoint
- `POST /chat/stream` - Streaming chat (placeholder)

### Data Retrieval
- `GET /courses` - List all current courses
- `GET /courses/by-department/{department}` - Filter by department
- `GET /courses/by-program/{program_code}` - Filter by program
- `GET /courses/with-tuition` - Courses with fees
- `GET /programs` - List all programs
- `GET /departments` - List all departments
- `GET /search?q={query}` - Search documents

### System
- `GET /health` - Basic health check
- `GET /health/detailed` - Detailed system diagnostics
- `GET /system/status` - System statistics
- `POST /system/reload` - Reload vector store

## Setup & Installation

### Prerequisites
```bash
# Python 3.8+
python --version

# Install dependencies
pip install fastapi uvicorn langchain chromadb google-generativeai python-dotenv
```

### Environment Variables
Create a `.env` file:
```env
# Required
GEMINI_API_KEY=your_google_api_key_here

# Optional (defaults shown)
TEMPERATURE=0.1
MAX_TOKENS=1000
LLM_MODEL=gemini-2.5-flash
EMBEDDING_MODEL=models/text-embedding-004
DEFAULT_K=20
CACHE_SIZE=100
CACHE_TTL=3600
RATE_LIMIT_REQUESTS=10
RATE_LIMIT_WINDOW=60
```

### Running the Server
```bash
# Development
python main.py

# Production
uvicorn main:app --host 0.0.0.0 --port 8000
```

## Database Integration

The system uses SQLite database at `/home/student/Repositories/CSExpert/data/csexpert.db` containing:
- **courses**: 404 current courses (is_current=1, is_replaced=0)
- **course_sections**: Detailed course content
- **course_details**: Tuition and application info
- **programs**: 4 programs (N2COS, N2SOF, N1SOF, N2GDT)
- **extraction_urls**: Syllabus and course page URLs

### Document Generation
Each course generates multiple documents:
1. **Course Overview** - Basic info, credits, department
2. **Course Sections** - Prerequisites, content, assessment, etc.
3. **Course Details** - Tuition, application periods
4. **Program Documents** - Program info and complete course lists

## Features

### Natural Language Queries
Supports queries like:
- "What is the Computer Science Master program about?"
- "Which courses are in Software Engineering program?"
- "Tell me about machine learning prerequisites"
- "What courses have tuition fees?"

### Smart Filtering
- By department
- By program (using names or codes)
- By cycle (Bachelor/Master/PhD)
- By tuition presence
- By term (e.g., "Autumn 2025")

### Program Name Recognition
Maps natural language to program codes:
- "computer science master" → N2COS
- "software engineering bachelor" → N1SOF
- "game design" → N2GDT

## Configuration

### Adjustable Parameters
Via environment variables or `config.py`:
- **Search**: `DEFAULT_K`, `MAX_SEARCH_K`, `SIMILARITY_THRESHOLD`
- **LLM**: `TEMPERATURE`, `MAX_TOKENS`, `LLM_MODEL`
- **Cache**: `CACHE_SIZE`, `CACHE_TTL`, `ENABLE_CACHE`
- **Context**: `MAX_CONTEXT_LENGTH`, `MAX_DOCUMENTS_FOR_CONTEXT`
- **Rate Limiting**: `RATE_LIMIT_REQUESTS`, `RATE_LIMIT_WINDOW`

## Development

### Project Structure
```
backend/
├── chroma_db/                 # Vector database storage
├── config.py                  # Configuration
├── database_document_loader.py # Document generation
├── main.py                    # FastAPI app
├── rag_system.py             # RAG implementation
├── rate_limiter.py           # Rate limiting
├── .gitignore                # Git ignore rules
├── .env                      # Environment variables (create this)
└── README.md                 # This file
```

### Adding Features
1. **New Endpoints**: Add to `main.py`
2. **New Query Types**: Update query routing in `rag_system.py`
3. **New Document Types**: Extend `database_document_loader.py`
4. **New Filters**: Add methods to `rag_system.py`

### Testing
```python
# Test database loader
from database_document_loader import DatabaseDocumentLoader
loader = DatabaseDocumentLoader()
stats = loader.get_statistics()
print(stats)

# Test RAG system
from rag_system import GothenburgUniversityRAG
rag = GothenburgUniversityRAG(use_database=True)
rag.initialize_vector_store()
result = rag.query("What is DIT084 about?")
print(result)
```

## Performance

- **Documents**: ~4,500 searchable documents
- **Cache Hit Rate**: ~30% for common queries
- **Vector Store**: ChromaDB with persistence
- **Rate Limit**: 10 requests/minute per client
