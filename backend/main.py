import os
import logging
from typing import Dict, List, Optional
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import uvicorn
from dotenv import load_dotenv

# Load environment variables from parent directory
load_dotenv()

from rag_system import GothenburgUniversityRAG
from config import RAGConfig
from rate_limiter import RateLimitInfo

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global RAG instance
rag_system: Optional[GothenburgUniversityRAG] = None

class ChatMessage(BaseModel):
    message: str
    session_id: Optional[str] = None

class ChatResponse(BaseModel):
    answer: str
    content_type: str
    sources: List[Dict]
    num_documents_retrieved: int
    session_id: Optional[str] = None

class SystemStatus(BaseModel):
    status: str
    total_documents: Optional[int] = None
    course_documents: Optional[int] = None
    program_documents: Optional[int] = None
    embedding_model: Optional[str] = None
    llm_model: Optional[str] = None
    collection_name: Optional[str] = None
    error: Optional[str] = None

async def initialize_rag_system():
    """Initialize the RAG system on startup."""
    global rag_system
    try:
        logger.info("🚀 Initializing enhanced RAG system...")
        
        # Log configuration summary
        config_summary = RAGConfig.get_config_summary()
        logger.info(f"📊 Configuration: {config_summary}")
        
        # Use the configured JSON directories from RAGConfig
        json_dirs = RAGConfig.DEFAULT_JSON_DIRS
        
        # Initialize with default client ID for startup and use database by default
        rag_system = GothenburgUniversityRAG(json_dirs=json_dirs, client_id="system", use_database=True)
        
        # Initialize vector store
        num_docs = rag_system.initialize_vector_store()
        logger.info(f"✅ RAG system initialized successfully with {num_docs} documents")
        
        # Validate configuration
        config_validation = RAGConfig.validate_config()
        failed_checks = [check for check, passed in config_validation.items() if not passed]
        if failed_checks:
            logger.warning(f"⚠️ Configuration warnings: {failed_checks}")
        
    except Exception as e:
        logger.error(f"❌ Failed to initialize RAG system: {e}")
        rag_system = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan."""
    # Startup
    await initialize_rag_system()
    yield
    # Shutdown
    logger.info("Shutting down...")

# Create FastAPI app
app = FastAPI(
    title="CSExpert - Gothenburg University Assistant API",
    description="RAG-powered chatbot for Gothenburg University Computer Science and Engineering course and program information",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # React dev server
        "http://localhost:5173",  # Vite dev server
        "http://localhost:8080",  # Alternative dev server
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8080",
        "https://csexpert-1247159b5377.herokuapp.com",  # Your Heroku app
        "*"  # Allow all origins for API testing (remove in production if needed)
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Routes (defined first to take precedence)
@app.get("/health", tags=["Health"])
async def health_check():
    """Basic health check endpoint."""
    if rag_system is None or not rag_system.is_initialized:
        return {"status": "unhealthy", "reason": "RAG system not initialized"}
    return {"status": "healthy"}

@app.get("/health/detailed", tags=["Health"])
async def detailed_health_check():
    """Detailed health check with system diagnostics."""
    if rag_system is None:
        return {"status": "unhealthy", "reason": "RAG system not initialized"}
    
    try:
        health_info = rag_system.health_check()
        return health_info
    except Exception as e:
        logger.error(f"Error in detailed health check: {e}")
        return {
            "status": "unhealthy", 
            "reason": f"Health check failed: {str(e)}"
        }

@app.get("/system/status", response_model=SystemStatus, tags=["System"])
async def get_system_status():
    """Get system status and statistics."""
    if rag_system is None:
        return SystemStatus(status="not_initialized", error="RAG system not initialized")
    
    try:
        info = rag_system.get_system_info()
        return SystemStatus(**info)
    except Exception as e:
        logger.error(f"Error getting system status: {e}")
        return SystemStatus(status="error", error=str(e))

@app.post("/system/reload", tags=["System"])
async def reload_system(background_tasks: BackgroundTasks):
    """Reload the RAG system with fresh data."""
    if rag_system is None:
        raise HTTPException(status_code=500, detail="RAG system not initialized")
    
    try:
        # Reload in background
        background_tasks.add_task(reload_rag_system)
        return {"message": "System reload initiated", "status": "in_progress"}
    except Exception as e:
        logger.error(f"Error initiating reload: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to initiate reload: {str(e)}")

async def reload_rag_system():
    """Background task to reload the RAG system."""
    global rag_system
    try:
        if rag_system:
            rag_system.initialize_vector_store(force_reload=True)
            logger.info("RAG system reloaded successfully")
    except Exception as e:
        logger.error(f"Error reloading RAG system: {e}")

@app.post("/chat", response_model=ChatResponse, tags=["Chat"])
async def chat(message: ChatMessage, request: Request):
    """
    Send a message to the chatbot and get a response.
    
    This endpoint processes user questions about Gothenburg University courses and programs.
    Includes rate limiting per client IP.
    """
    if rag_system is None or not rag_system.is_initialized:
        raise HTTPException(
            status_code=503, 
            detail="RAG system not initialized. Please check system status."
        )
    
    if not message.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    
    # Get client identifier for rate limiting
    client_ip = request.client.host if request.client else "unknown"
    client_id = message.session_id or client_ip
    
    # Log the incoming request
    logger.info(f"=== CHAT REQUEST ===")
    logger.info(f"Message: {message.message}")
    logger.info(f"Session ID: {message.session_id}")
    logger.info(f"Client ID: {client_id}")
    logger.info(f"Message length: {len(message.message)} characters")
    
    try:
        # Create client-specific RAG instance for rate limiting
        # (In production, you might want to cache these instances)
        client_rag = GothenburgUniversityRAG(
            json_dirs=rag_system.json_dirs,
            client_id=client_id,
            use_database=rag_system.use_database
        )
        
        # Share the vector store from the global instance
        client_rag.vector_store = rag_system.vector_store
        client_rag.is_initialized = rag_system.is_initialized
        
        # Process the query with client-specific rate limiting
        result = client_rag.query(message.message.strip())
        
        # Log the response details
        logger.info(f"=== CHAT RESPONSE ===")
        logger.info(f"Answer length: {len(result['answer'])} characters")
        logger.info(f"Content type: {result['content_type']}")
        logger.info(f"Sources found: {len(result['sources'])}")
        logger.info(f"Documents retrieved: {result['num_documents_retrieved']}")
        logger.info(f"Answer preview: {result['answer'][:200]}...")
        
        if len(result['answer'].strip()) == 0:
            logger.warning("WARNING: Empty answer generated!")
        
        response = ChatResponse(
            answer=result["answer"],
            content_type=result["content_type"],
            sources=result["sources"],
            num_documents_retrieved=result["num_documents_retrieved"],
            session_id=message.session_id
        )
        
        # Log final response being sent
        logger.info(f"Final response answer length: {len(response.answer)}")
        logger.info(f"=== END CHAT RESPONSE ===")
        
        return response
        
    except Exception as e:
        logger.error(f"=== CHAT ERROR ===")
        logger.error(f"Error processing chat message: {e}")
        logger.error(f"Error type: {type(e).__name__}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        # Return a fallback response
        fallback_response = ChatResponse(
            answer="I apologize, but I encountered an error while processing your question. For more information, please visit the official Gothenburg University website at https://www.gu.se/en/study-in-gothenburg",
            content_type="error",
            sources=[],
            num_documents_retrieved=0,
            session_id=message.session_id
        )
        
        logger.info(f"Returning fallback response")
        return fallback_response

@app.post("/chat/stream", tags=["Chat"])
async def chat_stream(message: ChatMessage):
    """
    Stream chat response (placeholder for future implementation).
    Currently returns the same as regular chat.
    """
    return await chat(message)

@app.get("/courses", tags=["Data"])
async def get_courses():
    """Get list of available current courses only."""
    if rag_system is None or not rag_system.is_initialized:
        raise HTTPException(status_code=503, detail="RAG system not initialized")
    
    try:
        # Get all documents and extract course information
        collection = rag_system.vector_store.get()
        courses = {}
        
        for metadata in collection['metadatas']:
            # Only include current courses (all documents in our new system are from current courses)
            if metadata.get('course_code') and metadata.get('course_code') not in courses:
                # Check if it's a course-related document
                if metadata.get('doc_type') in ['course_overview', 'course_section', 'course_details']:
                    courses[metadata['course_code']] = {
                        'code': metadata.get('course_code'),
                        'title': metadata.get('course_title', ''),
                        'department': metadata.get('department', ''),
                        'credits': metadata.get('credits', ''),
                        'cycle': metadata.get('cycle', '')
                    }
        
        # Convert to list and sort
        course_list = list(courses.values())
        course_list.sort(key=lambda x: x.get('code', ''))
        
        return {"courses": course_list, "total": len(course_list), "note": "Only current courses are included"}
        
    except Exception as e:
        logger.error(f"Error getting courses: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get courses: {str(e)}")

@app.get("/programs", tags=["Data"])
async def get_programs():
    """Get list of available programs."""
    if rag_system is None or not rag_system.is_initialized:
        raise HTTPException(status_code=503, detail="RAG system not initialized")
    
    try:
        # Get program information from metadata
        programs = [
            {"code": "N2COS", "name": "Computer Science Master's Programme"},
            {"code": "N2SOF", "name": "Software Engineering and Management Master's Programme"},
            {"code": "N1SOF", "name": "Software Engineering and Management Bachelor's Programme"},
            {"code": "N2GDT", "name": "Game Design Technology Master's Programme"}
        ]
        
        return {"programs": programs, "total": len(programs)}
        
    except Exception as e:
        logger.error(f"Error getting programs: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get programs: {str(e)}")

@app.get("/search", tags=["Search"])
async def search_documents(q: str, doc_type: Optional[str] = None, limit: int = 10):
    """
    Search through documents.
    
    Args:
        q: Search query
        doc_type: Filter by document type ("course" or "program")
        limit: Maximum number of results to return
    """
    if rag_system is None or not rag_system.is_initialized:
        raise HTTPException(status_code=503, detail="RAG system not initialized")
    
    if not q.strip():
        raise HTTPException(status_code=400, detail="Search query cannot be empty")
    
    try:
        # Use the RAG system's retrieval method
        content_type = doc_type if doc_type in ["course", "program"] else "both"
        documents = rag_system.retrieve_documents(q.strip(), content_type, k=limit)
        
        # Format results
        results = []
        for doc in documents:
            result = {
                "content": doc.page_content[:500] + "..." if len(doc.page_content) > 500 else doc.page_content,
                "metadata": {
                    "course_code": doc.metadata.get("course_code", ""),
                    "course_title": doc.metadata.get("course_title", ""),
                    "section": doc.metadata.get("section", ""),
                    "doc_type": doc.metadata.get("doc_type", ""),
                    "department": doc.metadata.get("department", ""),
                }
            }
            results.append(result)
        
        return {
            "query": q,
            "results": results,
            "total": len(results),
            "doc_type_filter": doc_type
        }
        
    except Exception as e:
        logger.error(f"Error searching documents: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

@app.get("/courses/by-department/{department}", tags=["Data"])
async def get_courses_by_department(department: str):
    """Get courses by department (current courses only)."""
    if rag_system is None or not rag_system.is_initialized:
        raise HTTPException(status_code=503, detail="RAG system not initialized")
    
    try:
        # Clean up department name
        dept_clean = department.replace("-", " ").title()
        if "Department of" not in dept_clean:
            dept_clean = f"Department of {dept_clean}"
        
        docs = rag_system.find_courses_by_department(dept_clean)
        
        # Extract unique courses from documents
        courses = {}
        for doc in docs:
            course_code = doc.metadata.get('course_code')
            if course_code and course_code not in courses:
                courses[course_code] = {
                    'code': course_code,
                    'title': doc.metadata.get('course_title', ''),
                    'credits': doc.metadata.get('credits', ''),
                    'cycle': doc.metadata.get('cycle', '')
                }
        
        course_list = list(courses.values())
        course_list.sort(key=lambda x: x['code'])
        
        return {
            "department": dept_clean,
            "courses": course_list,
            "total": len(course_list)
        }
        
    except Exception as e:
        logger.error(f"Error getting courses by department: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get courses: {str(e)}")

@app.get("/courses/by-program/{program_code}", tags=["Data"])
async def get_courses_by_program(program_code: str):
    """Get courses by program (current courses only)."""
    if rag_system is None or not rag_system.is_initialized:
        raise HTTPException(status_code=503, detail="RAG system not initialized")
    
    try:
        docs = rag_system.find_courses_by_program(program_code.upper())
        
        # Extract unique courses from documents
        courses = {}
        for doc in docs:
            course_code = doc.metadata.get('course_code')
            if course_code and course_code not in courses:
                courses[course_code] = {
                    'code': course_code,
                    'title': doc.metadata.get('course_title', ''),
                    'credits': doc.metadata.get('credits', ''),
                    'cycle': doc.metadata.get('cycle', ''),
                    'department': doc.metadata.get('department', '')
                }
        
        course_list = list(courses.values())
        course_list.sort(key=lambda x: x['code'])
        
        return {
            "program_code": program_code.upper(),
            "courses": course_list,
            "total": len(course_list)
        }
        
    except Exception as e:
        logger.error(f"Error getting courses by program: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get courses: {str(e)}")

@app.get("/courses/with-tuition", tags=["Data"])
async def get_courses_with_tuition():
    """Get courses that have tuition fees (current courses only)."""
    if rag_system is None or not rag_system.is_initialized:
        raise HTTPException(status_code=503, detail="RAG system not initialized")
    
    try:
        docs = rag_system.find_courses_with_tuition()
        
        # Extract unique courses with tuition information
        courses = {}
        for doc in docs:
            if doc.metadata.get('doc_type') == 'course_details' or doc.metadata.get('has_tuition'):
                course_code = doc.metadata.get('course_code')
                if course_code and course_code not in courses:
                    courses[course_code] = {
                        'code': course_code,
                        'title': doc.metadata.get('course_title', ''),
                        'credits': doc.metadata.get('credits', ''),
                        'cycle': doc.metadata.get('cycle', ''),
                        'department': doc.metadata.get('department', ''),
                        'tuition_fee': doc.metadata.get('tuition_fee', 'Information available')
                    }
        
        course_list = list(courses.values())
        course_list.sort(key=lambda x: x['code'])
        
        return {
            "courses": course_list,
            "total": len(course_list)
        }
        
    except Exception as e:
        logger.error(f"Error getting courses with tuition: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get courses: {str(e)}")

@app.get("/departments", tags=["Data"])
async def get_departments():
    """Get list of all departments."""
    if rag_system is None or not rag_system.is_initialized:
        raise HTTPException(status_code=503, detail="RAG system not initialized")
    
    try:
        metadata_summary = rag_system.get_metadata_summary()
        departments = metadata_summary.get('departments', [])
        
        return {
            "departments": departments,
            "total": len(departments)
        }
        
    except Exception as e:
        logger.error(f"Error getting departments: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get departments: {str(e)}")

# Frontend serving (defined last to avoid conflicts)
frontend_dist_path = Path("../frontend/dist")
if frontend_dist_path.exists():
    # Mount static assets
    app.mount("/assets", StaticFiles(directory=str(frontend_dist_path / "assets")), name="static")
    
    @app.get("/", response_class=FileResponse)
    async def serve_frontend():
        """Serve the React frontend."""
        index_file = frontend_dist_path / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        else:
            # Fallback to API info if frontend not built
            return {
                "message": "CSExpert - Gothenburg University Assistant API",
                "status": "running",
                "docs": "/docs",
                "note": "Frontend not built. Visit /docs for API documentation."
            }
    
    @app.get("/{full_path:path}", response_class=FileResponse)
    async def serve_frontend_routes(full_path: str):
        """Catch-all route to serve React app for client-side routing."""
        # First, try to serve static files from dist directory
        file_path = frontend_dist_path / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        
        # For all other routes, serve the React app (client-side routing)
        index_file = frontend_dist_path / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        else:
            raise HTTPException(status_code=404, detail="Frontend not available")
else:
    @app.get("/", tags=["Health"])
    async def root():
        """Root endpoint when frontend is not built."""
        return {
            "message": "CSExpert - Gothenburg University Assistant API",
            "status": "running",
            "docs": "/docs",
            "note": "Frontend not built. Visit /docs for API documentation."
        }

if __name__ == "__main__":
    # Get configuration from environment
    host = os.getenv("APP_HOST", "0.0.0.0")
    # Use Heroku's PORT environment variable if available, otherwise default to 8000
    port = int(os.getenv("PORT", os.getenv("APP_PORT", "8000")))
    debug = os.getenv("DEBUG", "False").lower() == "true"
    
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=debug,
        log_level="info"
    ) 