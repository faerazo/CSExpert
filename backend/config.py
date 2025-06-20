"""
Configuration settings for the RAG system.
Centralizes all magic numbers and settings for better maintainability.
"""
import os
from typing import Dict, List
from pathlib import Path


class RAGConfig:
    """Centralized configuration for the RAG system."""
    
    # === LLM SETTINGS ===
    TEMPERATURE = float(os.getenv("TEMPERATURE", "0.1"))
    MAX_TOKENS = int(os.getenv("MAX_TOKENS", "1000"))
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "models/text-embedding-004")
    LLM_MODEL = os.getenv("LLM_MODEL", "gemini-2.5-flash-preview-05-20")
    
    # === SEARCH SETTINGS ===
    DEFAULT_K = int(os.getenv("DEFAULT_K", "20"))
    MAX_SEARCH_K = int(os.getenv("MAX_SEARCH_K", "50"))
    MIN_SEARCH_K = int(os.getenv("MIN_SEARCH_K", "5"))
    SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", "0.7"))
    
    # === CACHE SETTINGS ===
    CACHE_SIZE = int(os.getenv("CACHE_SIZE", "100"))
    CACHE_TTL = int(os.getenv("CACHE_TTL", "3600"))  # 1 hour in seconds
    ENABLE_CACHE = os.getenv("ENABLE_CACHE", "true").lower() == "true"
    
    # === CONTEXT MANAGEMENT ===
    MAX_CONTEXT_LENGTH = int(os.getenv("MAX_CONTEXT_LENGTH", "8000"))
    MAX_QUESTION_LENGTH = int(os.getenv("MAX_QUESTION_LENGTH", "5000"))
    MIN_QUESTION_LENGTH = int(os.getenv("MIN_QUESTION_LENGTH", "3"))
    MAX_DOCUMENTS_FOR_CONTEXT = int(os.getenv("MAX_DOCUMENTS_FOR_CONTEXT", "15"))
    
    # === QUERY VARIATIONS ===
    MAX_QUERY_VARIATIONS = int(os.getenv("MAX_QUERY_VARIATIONS", "6"))
    MIN_QUERY_VARIATIONS = int(os.getenv("MIN_QUERY_VARIATIONS", "2"))
    
    # === MEMORY SETTINGS ===
    CONVERSATION_MEMORY_K = int(os.getenv("CONVERSATION_MEMORY_K", "5"))
    
    # === DATABASE SETTINGS ===
    CHROMA_PERSIST_DIRECTORY = os.getenv("CHROMA_PERSIST_DIRECTORY", "./data/chroma_db")
    COLLECTION_NAME = os.getenv("COLLECTION_NAME", "gu_courses_programs")
    
    # === RATE LIMITING ===
    RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "10"))  # requests per minute
    RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))  # seconds
    
    # === TOKEN COST ESTIMATION ===
    # Rough cost per token for different models (in USD)
    TOKEN_COSTS = {
        "gemini-2.5-flash": 0.00002,
        "gemini-pro": 0.0005,
        "text-embedding-004": 0.00001
    }
    
    # === SECTION MAPPINGS ===
    # User terminology → JSON section names
    SECTION_MAPPINGS = {
        # Prerequisites/Requirements
        'prerequisite': ['entry requirements', 'prerequisites', 'required courses'],
        'requirement': ['entry requirements', 'prerequisites'], 
        'need': ['entry requirements', 'prerequisites'],
        
        # Assessment/Grading
        'assessment': ['examination', 'grading', 'assessment methods'],
        'exam': ['examination', 'assessment', 'grading'],
        'grade': ['grading', 'examination', 'assessment'],
        'test': ['examination', 'assessment'],
        
        # Course content
        'about': ['course content', 'learning outcomes', 'course overview'],
        'content': ['course content', 'learning outcomes'],
        'topic': ['course content', 'learning outcomes'],
        'cover': ['course content', 'learning outcomes'],
        'syllabus': ['course content', 'learning outcomes'],
        
        # Teaching format
        'teaching': ['form of teaching', 'teaching methods'],
        'lecture': ['form of teaching', 'teaching methods'],
        'format': ['form of teaching', 'teaching methods'],
    }
    
    # === CYCLE MAPPINGS ===
    CYCLE_MAPPINGS = {
        'bachelor': 'First cycle',
        'master': 'Second cycle', 
        'phd': 'Third cycle',
        'first cycle': 'First cycle',
        'second cycle': 'Second cycle', 
        'third cycle': 'Third cycle'
    }
    
    # === COMMON TYPO CORRECTIONS ===
    TYPO_CORRECTIONS = {
        'programm': 'program',
        'programme': 'program',
        'cours': 'course',
        'prerequisit': 'prerequisite',
        'assesment': 'assessment',
        'machien': 'machine',
        'learing': 'learning',
        'algoritm': 'algorithm'
    }
    
    # === VALIDATION SETTINGS ===
    SUSPICIOUS_PATTERNS = [
        r'<script',
        r'javascript:',
        r'eval\(',
        r'exec\(',
    ]
    
    # === DEFAULT JSON DIRECTORIES ===
    # Use absolute path based on this file's location to avoid working directory issues
    _BASE_DIR = Path(__file__).parent.parent  # Go up from backend/ to project root
    DEFAULT_JSON_DIRS = {
        "courses_combined": str(_BASE_DIR / "data" / "json" / "courses_combined")
    }
    
    @classmethod
    def get_token_cost(cls, model_name: str) -> float:
        """Get token cost for a specific model."""
        for model_key, cost in cls.TOKEN_COSTS.items():
            if model_key in model_name.lower():
                return cost
        return cls.TOKEN_COSTS["gemini-2.5-flash"]  # Default
    
    @classmethod
    def validate_config(cls) -> Dict[str, bool]:
        """Validate configuration settings."""
        validations = {}
        
        # Check required environment variables
        required_env_vars = ["GEMINI_API_KEY"]
        for var in required_env_vars:
            validations[f"env_{var}"] = bool(os.getenv(var))
        
        # Check numeric ranges
        validations["cache_size_valid"] = 1 <= cls.CACHE_SIZE <= 1000
        validations["max_tokens_valid"] = 100 <= cls.MAX_TOKENS <= 8000
        validations["temperature_valid"] = 0.0 <= cls.TEMPERATURE <= 2.0
        
        # Check paths
        validations["chroma_dir_exists"] = Path(cls.CHROMA_PERSIST_DIRECTORY).parent.exists()
        
        return validations
    
    @classmethod
    def get_config_summary(cls) -> Dict:
        """Get a summary of current configuration."""
        return {
            "llm_settings": {
                "model": cls.LLM_MODEL,
                "temperature": cls.TEMPERATURE,
                "max_tokens": cls.MAX_TOKENS
            },
            "search_settings": {
                "default_k": cls.DEFAULT_K,
                "max_search_k": cls.MAX_SEARCH_K,
                "similarity_threshold": cls.SIMILARITY_THRESHOLD
            },
            "cache_settings": {
                "enabled": cls.ENABLE_CACHE,
                "size": cls.CACHE_SIZE,
                "ttl": cls.CACHE_TTL
            },
            "rate_limiting": {
                "requests_per_minute": cls.RATE_LIMIT_REQUESTS,
                "window_seconds": cls.RATE_LIMIT_WINDOW
            }
        } 