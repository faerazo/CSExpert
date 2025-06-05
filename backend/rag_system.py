import os
import json
import logging
from typing import List, Dict, Optional, Literal
from pathlib import Path
from datetime import datetime

import numpy as np
from tqdm import tqdm
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# LangChain imports
from langchain_community.document_loaders import JSONLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain_chroma import Chroma
from langchain.memory import ConversationBufferWindowMemory
from langchain.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser

# Load environment variables
load_dotenv(dotenv_path="../.env")  # Look for .env file in parent directory

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RouteQuery(BaseModel):
    """Route a user query to the most relevant content type."""
    content_type: Literal["course", "program", "both"] = Field(
        ...,
        description="Route to: 'course' for specific course questions, 'program' for program questions, 'both' when the question involves both or is unclear"
    )

class GothenburgUniversityRAG:
    """
    RAG system for Gothenburg University course and program information.
    Uses Google's text-embedding-004 for embeddings and Gemini Pro for generation.
    """
    
    def __init__(self, json_dirs: Dict[str, str] = None):
        """
        Initialize the RAG system.
        
        Args:
            json_dirs: Dictionary with paths to JSON directories
                      {"courses_syllabus": "path", "course_webpages": "path", "programs": "path"}
        """
        self.google_api_key = os.getenv("GEMINI_API_KEY")  # Changed from GOOGLE_API_KEY
        if not self.google_api_key:
            raise ValueError("GEMINI_API_KEY not found in environment variables")
        
        # Default JSON directories
        self.json_dirs = json_dirs or {
            "courses_syllabus": "data/json/courses_syllabus",
            "course_webpages": "data/json/course_webpages"
        }
        
        # Configuration
        self.embedding_model = os.getenv("EMBEDDING_MODEL", "models/text-embedding-004")
        self.llm_model = os.getenv("LLM_MODEL", "gemini-2.5-flash-preview-05-20")
        self.temperature = float(os.getenv("TEMPERATURE", "0.1"))
        self.max_tokens = int(os.getenv("MAX_TOKENS", "1000"))
        self.chroma_persist_dir = os.getenv("CHROMA_PERSIST_DIRECTORY", "./data/chroma_db")
        self.collection_name = os.getenv("COLLECTION_NAME", "gu_courses_programs")
        
        self._initialize_components()
        self._setup_prompts()
        
    def _initialize_components(self):
        """Initialize all necessary components."""
        # Initialize Google AI models
        self.embeddings = GoogleGenerativeAIEmbeddings(
            model=self.embedding_model,
            google_api_key=self.google_api_key
        )
        
        self.llm = ChatGoogleGenerativeAI(
            model=self.llm_model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            google_api_key=self.google_api_key
        )
        
        # Initialize text splitter
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1500,
            chunk_overlap=150,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""]
        )
        
        # Initialize memory
        self.memory = ConversationBufferWindowMemory(
            memory_key="chat_history",
            output_key="answer",
            return_messages=True,
            k=5
        )
        
        # Initialize vector store
        self.vector_store = None
        self.is_initialized = False
        
    def _setup_prompts(self):
        """Set up all prompt templates."""
        # Router system template
        router_system_template = """You are an expert at routing user questions about university education to the appropriate content type.
Your task is to determine whether the question is about:
1. A specific COURSE or course-related information (prerequisites, content, assessment, etc.)
2. A specific PROGRAM or program-related information (program structure, admission, overview, etc.)
3. BOTH when the question involves both courses and programs or when it's unclear

Examples:
- "What are the prerequisites for DIT134?" -> course
- "Tell me about the Master's in Applied Data Science program" -> program
- "What courses are included in the Computer Science program?" -> both
- "How many credits do I need for graduation?" -> both"""

        self.router_prompt = ChatPromptTemplate.from_messages([
            ("system", router_system_template),
            ("human", "{question}")
        ])
        
        # Main system template
        system_template = """You are an experienced and knowledgeable student counselor for Gothenburg University's Department of Computer Science and Engineering. Your role is to guide both prospective and current students through their academic journey with comprehensive, accurate, and supportive advice.

## YOUR EXPERTISE AREAS:
- **Program Information**: Bachelor's and Master's degree programs, admission requirements, curriculum structure
- **Course Guidance**: Course content, prerequisites, learning outcomes, assessment methods, course sequencing
- **Academic Planning**: Study pathways, specialization tracks, course recommendations
- **Program Status**: Current availability, application deadlines, program changes

## COMMUNICATION STYLE:
- **Professional yet Friendly**: Maintain a warm, approachable tone while being thorough and precise
- **Student-Focused**: Consider both academic requirements and student goals/interests
- **Structured Responses**: Organize information clearly with bullet points, course codes, and logical flow
- **Encouraging**: Support students in making informed decisions about their academic journey

## PROGRAM-SPECIFIC KNOWLEDGE:
When discussing programs, provide relevant details about:

**Master's Programs:**
- **Computer Science Master's Programme (N2COS)**: Advanced computer science with research opportunities
- **Software Engineering and Management Master's Programme (N2SOF)**: Combines technical skills with business acumen
- **Game Design and Technology Master's Programme (N2GDT)**: Interdisciplinary program combining technology and design
- **Applied Data Science Master's Programme (N2ADS)**: ⚠️ **IMPORTANT**: This program is no longer accepting new applications

**Bachelor's Programs:**
- **Software Engineering and Management Bachelor's Programme (N1SOF)**: Balance of technical and management skills

## RESPONSE GUIDELINES:

### 1. ACCURACY & SOURCE-BASED ANSWERS
- Base ALL information on the provided course documents
- Include specific course codes (e.g., DIT005, TIA102) when discussing courses
- Quote directly from course documents when providing specific details
- If information isn't in the provided context, clearly state: "I don't have specific information about [topic] in my current course database."

### 2. COMPREHENSIVE COURSE INFORMATION
When discussing courses, include:
- **Course Code & Title**: Always start with the official designation
- **Credits & Level**: Academic level (First/Second cycle) and credit value
- **Prerequisites**: Specific requirements and recommended preparation
- **Learning Outcomes**: What students will achieve
- **Assessment Methods**: How students are evaluated
- **Program Relevance**: Which programs include this course

### 3. STRUCTURED PROGRAM GUIDANCE
For program-related questions:
- **Core Courses**: Required courses for the program
- **Electives**: Optional courses and specialization tracks  
- **Course Sequences**: Recommended order and prerequisites
- **Career Pathways**: How courses prepare students for different career directions

### 4. PRACTICAL ACADEMIC ADVICE
- **Prerequisites Planning**: Help students understand course dependencies
- **Workload Considerations**: Balance course difficulty and credit loads
- **Specialization Guidance**: Recommend courses based on student interests
- **Alternative Options**: Suggest similar courses if specific ones aren't available

### 5. HANDLING COMMON STUDENT QUESTIONS
Be prepared to address:
- "What courses are available in [specific area]?"
- "What are the prerequisites for [course/program]?"
- "How do I plan my studies for [specialization]?"
- "What's the difference between [Program A] and [Program B]?"
- "Which courses should I take if I'm interested in [career field]?"

## RESPONSE STRUCTURE:
1. **Direct Answer**: Address the specific question clearly
2. **Detailed Information**: Provide comprehensive details from course documents
3. **Additional Guidance**: Suggest related courses or considerations
4. **Next Steps**: Recommend actions or further information sources when appropriate

## IMPORTANT REMINDERS:
- Always verify your information against the provided course documents
- Include course codes and specific details from the source materials
- If recommending a sequence of courses, consider prerequisites and course availability
- Be honest about limitations in your knowledge and suggest where students can find additional information

---

**Context from course documents:**
{context}

**Previous conversation:**
{chat_history}

**Student Question:** {question}

**Your Response:** [Provide comprehensive, accurate guidance based on the course documents above]"""

        # Create the main prompt
        self.system_prompt = ChatPromptTemplate.from_messages([
            SystemMessagePromptTemplate.from_template(system_template),
            HumanMessagePromptTemplate.from_template("{question}")
        ])
        
        # Query generation prompts
        self.query_generation_prompts = {
            "course": """Generate 5 different versions of this question to find relevant course information:
Original: {question}

Focus on: course content, prerequisites, learning outcomes, assessment methods, course structure.
Generate 5 variations, one per line:""",
            
            "program": """Generate 5 different versions of this question to find relevant program information:
Original: {question}

Focus on: program structure, admission requirements, career opportunities, program overview, degree requirements.
Generate 5 variations, one per line:""",
            
            "both": """Generate 5 different versions of this question to find relevant course and program information:
Original: {question}

Focus on: how courses fit into programs, general academic information, cross-cutting topics.
Generate 5 variations, one per line:"""
        }

    def route_query(self, question: str) -> str:
        """Route the query to determine content type."""
        try:
            router_with_structured_output = self.router_prompt | self.llm.with_structured_output(RouteQuery)
            result = router_with_structured_output.invoke({"question": question})
            return result.content_type
        except Exception as e:
            logger.warning(f"Router failed, defaulting to 'both': {e}")
            return "both"

    def generate_query_variations(self, question: str, content_type: str) -> List[str]:
        """Generate multiple variations of the input question."""
        import re
        
        # Extract course code if present
        course_code_match = re.search(r'\b([A-Z]{2,4}\d{3})\b', question.upper())
        found_course_code = course_code_match.group(1) if course_code_match else None
        
        queries = [question]
        
        # If we found a course code, create targeted variations
        if found_course_code:
            base_variations = [
                f"{found_course_code}",  # Just the course code
                f"course {found_course_code}",  # Course + code
                f"{found_course_code} course information",  # More specific
            ]
            queries.extend(base_variations)
        
        # Detect what aspect they're asking about and create section-specific queries
        question_lower = question.lower()
        section_keywords = {
            'assessment': ['assessment', 'exam', 'grade', 'grading', 'evaluation', 'test'],
            'prerequisites': ['prerequisite', 'requirement', 'entry requirement', 'requirement'],
            'learning_outcomes': ['learning outcome', 'objective', 'goal', 'learning goal'],
            'course_content': ['content', 'about', 'topic', 'cover', 'material', 'syllabus'],
            'form_of_teaching': ['teaching', 'lecture', 'seminar', 'format', 'how is', 'delivery'],
            'entry_requirements': ['entry', 'admission', 'eligibility', 'qualify'],
            'grades': ['grade', 'grading', 'scale', 'pass', 'fail']
        }
        
        # Find relevant sections based on keywords
        relevant_sections = []
        for section, keywords in section_keywords.items():
            if any(keyword in question_lower for keyword in keywords):
                relevant_sections.append(section)
        
        # Add section-specific variations
        if found_course_code and relevant_sections:
            for section in relevant_sections:
                section_readable = section.replace('_', ' ')
                queries.extend([
                    f"{found_course_code} {section_readable}",
                    f"{section_readable} {found_course_code}",
                    f"{found_course_code} course {section_readable}"
                ])
        
        # Try LLM-based query generation as fallback/addition
        try:
            prompt_template = self.query_generation_prompts.get(content_type, self.query_generation_prompts["both"])
            prompt = ChatPromptTemplate.from_template(prompt_template)
            chain = prompt | self.llm | StrOutputParser()
            
            llm_variations = chain.invoke({"question": question})
            llm_queries = [q.strip() for q in llm_variations.split('\n') if q.strip() and len(q.strip()) > 5]
            queries.extend(llm_queries[:3])  # Limit LLM variations
            
        except Exception as e:
            logger.warning(f"LLM query generation failed, using manual variations: {e}")
            # Manual fallback variations based on content type
            if content_type == "course":
                if "prerequisite" in question.lower():
                    queries.extend(["entry requirements", "prerequisites", "required courses"])
                elif "about" in question.lower() or "what is" in question.lower():
                    queries.extend(["course description", "course overview", "course content"])
                elif "assessment" in question.lower():
                    queries.extend(["grading", "examination", "evaluation"])
        
        # Remove duplicates while preserving order and clean up
        seen = set()
        unique_queries = []
        for q in queries:
            q_clean = q.strip()
            if q_clean and q_clean.lower() not in seen and len(q_clean) > 2:
                seen.add(q_clean.lower())
                unique_queries.append(q_clean)
        
        # Ensure we have at least a few queries
        if len(unique_queries) < 3:
            unique_queries.extend([
                question.replace("?", ""),  # Remove question mark
                question.split()[-1] if len(question.split()) > 1 else question,  # Last word
                " ".join(question.split()[:3])  # First few words
            ])
        
        # Remove duplicates again and limit
        final_queries = []
        seen = set()
        for q in unique_queries:
            if q.lower() not in seen:
                seen.add(q.lower())
                final_queries.append(q)
                if len(final_queries) >= 10:  # Increased limit for section-specific queries
                    break
        
        return final_queries

    def load_json_documents(self) -> List[Document]:
        """Load and process JSON documents using LangChain's JSONLoader."""
        all_documents = []
        
        for doc_type, json_dir in self.json_dirs.items():
            if not os.path.exists(json_dir):
                logger.warning(f"Directory not found: {json_dir}")
                continue
                
            json_files = list(Path(json_dir).glob("*.json"))
            logger.info(f"Loading {len(json_files)} files from {json_dir}")
            
            for json_file in tqdm(json_files, desc=f"Loading {doc_type}"):
                try:
                    documents = self._load_single_json_file(json_file, doc_type)
                    all_documents.extend(documents)
                except Exception as e:
                    logger.error(f"Error loading {json_file}: {e}")
                    
        logger.info(f"Loaded {len(all_documents)} documents total")
        return all_documents

    def _load_single_json_file(self, json_file: Path, doc_type: str) -> List[Document]:
        """Load a single JSON file and create focused documents for each section."""
        documents = []
        
        # Load the JSON file
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Extract metadata
        metadata = data.get("metadata", {})
        sections = data.get("sections", {})
        
        # Create base metadata
        base_metadata = {
            "source": str(json_file),
            "doc_type": "course" if "course" in doc_type else "program",
            "category": doc_type,
            "course_code": metadata.get("course_code", ""),
            "course_title": metadata.get("course_title", ""),
            "department": metadata.get("department", ""),
            "credits": metadata.get("credits", ""),
            "language": metadata.get("language_of_instruction", ""),
            "cycle": metadata.get("cycle", ""),
            "programmes": ", ".join(metadata.get("programmes", [])) if isinstance(metadata.get("programmes"), list) else metadata.get("programmes", "")
        }
        
        # Create overview document with just metadata
        overview_content = self._format_overview_content(metadata)
        if overview_content.strip():
            doc = Document(
                page_content=overview_content,
                metadata={**base_metadata, "section": "overview", "section_type": "metadata"}
            )
            documents.append(doc)
        
        # Create focused documents for each section with complete context
        for section_name, section_content in sections.items():
            if section_content and str(section_content).strip():
                # Create a focused chunk with metadata context + specific section
                focused_content = self._format_section_content(metadata, section_name, section_content)
                doc = Document(
                    page_content=focused_content,
                    metadata={
                        **base_metadata, 
                        "section": section_name.lower().replace(" ", "_"),
                        "section_type": "content",
                        "section_name": section_name
                    }
                )
                documents.append(doc)
        
        return documents

    def _format_overview_content(self, metadata: Dict) -> str:
        """Format metadata into a concise overview."""
        content_parts = []
        
        # Course/Program title and code
        if metadata.get("course_code") and metadata.get("course_title"):
            content_parts.append(f"Course {metadata['course_code']}: {metadata['course_title']}")
        
        # Swedish title
        if metadata.get("swedish_title"):
            content_parts.append(f"Swedish: {metadata['swedish_title']}")
            
        # Key details in structured format
        details = []
        if metadata.get("department"):
            details.append(f"Department: {metadata['department']}")
        if metadata.get("credits"):
            details.append(f"Credits: {metadata['credits']}")
        if metadata.get("cycle"):
            details.append(f"Level: {metadata['cycle']}")
        if metadata.get("language_of_instruction"):
            details.append(f"Language: {metadata['language_of_instruction']}")
            
        if details:
            content_parts.append(" | ".join(details))
            
        # Programs
        if metadata.get("programmes"):
            programmes = metadata["programmes"]
            if isinstance(programmes, list):
                content_parts.append(f"Available in programs: {', '.join(programmes)}")
            else:
                content_parts.append(f"Available in program: {programmes}")
        
        return "\n".join(content_parts)

    def _format_section_content(self, metadata: Dict, section_name: str, section_content: str) -> str:
        """Format a section with metadata context for focused retrieval."""
        content_parts = []
        
        # Course identification
        course_code = metadata.get("course_code", "")
        course_title = metadata.get("course_title", "")
        if course_code and course_title:
            content_parts.append(f"Course: {course_code} - {course_title}")
        
        # Section header
        content_parts.append(f"\n{section_name}:")
        
        # Section content
        content_parts.append(section_content)
        
        # Add relevant metadata context at the end
        context_parts = []
        if metadata.get("credits"):
            context_parts.append(f"Credits: {metadata['credits']}")
        if metadata.get("department"):
            context_parts.append(f"Department: {metadata['department']}")
        if metadata.get("cycle"):
            context_parts.append(f"Level: {metadata['cycle']}")
            
        if context_parts:
            content_parts.append(f"\n[Course Details: {' | '.join(context_parts)}]")
        
        return "\n".join(content_parts)

    def initialize_vector_store(self, force_reload: bool = False) -> int:
        """Initialize the vector store with documents."""
        # Check if vector store already exists
        if os.path.exists(self.chroma_persist_dir) and not force_reload:
            try:
                logger.info("Loading existing vector store...")
                self.vector_store = Chroma(
                    persist_directory=self.chroma_persist_dir,
                    embedding_function=self.embeddings,
                    collection_name=self.collection_name
                )
                collection_size = len(self.vector_store.get()['ids'])
                logger.info(f"Loaded existing vector store with {collection_size} documents")
                self.is_initialized = True
                return collection_size
            except Exception as e:
                logger.warning(f"Failed to load existing vector store: {e}. Creating new one...")
        
        # Create new vector store
        logger.info("Creating new vector store...")
        documents = self.load_json_documents()
        
        if not documents:
            raise ValueError("No documents loaded. Check your JSON directories.")
        
        # Use natural section-based chunking - no artificial splitting needed
        # The JSON data is already optimally organized into meaningful sections
        logger.info(f"Using {len(documents)} naturally chunked sections")
        logger.info("Each section contains complete information for its specific aspect")
        
        # Create vector store with the naturally chunked sections
        self.vector_store = Chroma.from_documents(
            documents=documents,
            embedding=self.embeddings,
            persist_directory=self.chroma_persist_dir,
            collection_name=self.collection_name
        )
        
        self.is_initialized = True
        logger.info(f"Created vector store with {len(documents)} naturally chunked sections")
        return len(documents)

    def retrieve_documents(self, question: str, content_type: str, k: int = 20) -> List[Document]:
        """Retrieve relevant documents using multi-query approach with improved search."""
        if not self.is_initialized:
            raise ValueError("Vector store not initialized. Call initialize_vector_store() first.")
        
        # Extract course code if present in question (e.g., DIT005, TIA560)
        import re
        course_code_match = re.search(r'\b([A-Z]{2,4}\d{3})\b', question.upper())
        found_course_code = course_code_match.group(1) if course_code_match else None
        
        # Generate query variations
        queries = self.generate_query_variations(question, content_type)
        logger.info(f"Generated {len(queries)} query variations")
        if found_course_code:
            logger.info(f"Detected course code: {found_course_code}")
        
        # Strategy 1: Direct course code search if found
        direct_match_docs = []
        if found_course_code:
            try:
                # Search with course code filter
                direct_retriever = self.vector_store.as_retriever(
                    search_type="similarity",
                    search_kwargs={
                        "k": 50,  # Get more candidates
                        "filter": {"course_code": found_course_code}
                    }
                )
                direct_match_docs = direct_retriever.invoke(question)
                logger.info(f"Direct course code search found {len(direct_match_docs)} documents")
            except Exception as e:
                logger.warning(f"Direct course code search failed: {e}")
        
        # Strategy 2: Multi-query semantic search
        semantic_docs = []
        search_k = max(30, k * 2)  # Increased from 10
        
        # Set up metadata filter
        metadata_filter = None
        if content_type != "both":
            metadata_filter = {"doc_type": content_type}
        
        # Use both similarity and MMR search
        for search_type in ["similarity", "mmr"]:
            search_kwargs = {
                "k": search_k,
                "filter": metadata_filter
            }
            
            # Only add fetch_k for MMR search (not supported by similarity search in this ChromaDB version)
            if search_type == "mmr":
                search_kwargs["fetch_k"] = search_k * 3
            
            retriever = self.vector_store.as_retriever(
                search_type=search_type,
                search_kwargs=search_kwargs
            )
            
            # Retrieve documents for each query variation
            for query in queries:
                try:
                    docs = retriever.invoke(query)
                    semantic_docs.extend(docs)
                except Exception as e:
                    logger.warning(f"Failed to retrieve for query '{query}' with {search_type}: {e}")
        
        # Strategy 3: Keyword-based search for course titles
        keyword_docs = []
        if found_course_code:
            # Try searching for course title in content
            try:
                title_retriever = self.vector_store.as_retriever(
                    search_type="similarity",
                    search_kwargs={"k": 20}
                )
                title_query = f"course title {found_course_code}"
                keyword_docs = title_retriever.invoke(title_query)
            except Exception as e:
                logger.warning(f"Keyword search failed: {e}")
        
        # Combine all results with prioritization
        all_docs = []
        
        # Priority 1: Direct course code matches (highest priority)
        all_docs.extend(direct_match_docs)
        
        # Priority 2: Semantic search results
        all_docs.extend(semantic_docs)
        
        # Priority 3: Keyword search results
        all_docs.extend(keyword_docs)
        
        # Remove duplicates while preserving order (prioritized)
        seen = set()
        unique_docs = []
        for doc in all_docs:
            # Create unique identifier
            doc_id = f"{doc.page_content[:100]}_{doc.metadata.get('course_code', '')}_{doc.metadata.get('section', '')}"
            if doc_id not in seen:
                seen.add(doc_id)
                unique_docs.append(doc)
        
        logger.info(f"Retrieved {len(unique_docs)} unique documents (from {len(all_docs)} total)")
        
        # Log some debug info about what was found
        course_codes_found = set()
        for doc in unique_docs[:10]:  # Check first 10 docs
            if doc.metadata.get('course_code'):
                course_codes_found.add(doc.metadata['course_code'])
        
        if course_codes_found:
            logger.info(f"Top courses found: {', '.join(list(course_codes_found)[:5])}")
        
        # Return more documents but cap at reasonable limit
        return unique_docs[:max(k * 3, 50)]  # Return up to 3x requested or 50, whichever is higher

    def generate_answer(self, question: str, documents: List[Document]) -> str:
        """Generate answer using retrieved documents."""
        logger.info(f"=== GENERATE ANSWER START ===")
        logger.info(f"Question: {question}")
        logger.info(f"Number of documents: {len(documents)}")
        
        # Prepare context
        context_parts = []
        for i, doc in enumerate(documents):
            logger.info(f"Document {i+1}: {doc.page_content[:100]}... (length: {len(doc.page_content)})")
            context_parts.append(doc.page_content)
        
        context = "\n\n".join(context_parts)
        logger.info(f"Total context length: {len(context)} characters")
        
        # Get chat history
        chat_history = self.memory.chat_memory.messages
        logger.info(f"Chat history length: {len(chat_history)} messages")
        
        # Generate answer
        chain = self.system_prompt | self.llm | StrOutputParser()
        
        try:
            logger.info("Calling LLM...")
            answer = chain.invoke({
                "context": context,
                "question": question,
                "chat_history": chat_history
            })
            
            logger.info(f"=== LLM RESPONSE ===")
            logger.info(f"Answer length: {len(answer)} characters")
            logger.info(f"Answer preview: {answer[:300]}...")
            
            if not answer or len(answer.strip()) == 0:
                logger.warning("WARNING: LLM returned empty answer!")
                logger.warning(f"Raw answer: '{answer}'")
                # Return a fallback response instead of empty
                answer = "I apologize, but I wasn't able to generate a response to your question. Please try rephrasing your question or visit the official Gothenburg University website at https://www.gu.se/en/study-in-gothenburg for more information."
                logger.info(f"Using fallback answer: {answer}")
            
            # Update memory
            self.memory.save_context({"question": question}, {"answer": answer})
            
            logger.info(f"=== GENERATE ANSWER END ===")
            return answer
            
        except Exception as e:
            logger.error(f"=== LLM ERROR ===")
            logger.error(f"Error generating answer: {e}")
            logger.error(f"Error type: {type(e).__name__}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            
            fallback_answer = f"I apologize, but I encountered an error while processing your question. For more information, please visit the official Gothenburg University website at https://www.gu.se/en/study-in-gothenburg"
            logger.info(f"Returning fallback answer due to error")
            return fallback_answer

    def query(self, question: str) -> Dict:
        """Main query method."""
        if not self.is_initialized:
            raise ValueError("RAG system not initialized. Call initialize_vector_store() first.")
        
        try:
            # Route the query
            content_type = self.route_query(question)
            logger.info(f"Routed query to: {content_type}")
            
            # Retrieve documents
            documents = self.retrieve_documents(question, content_type)
            
            # Generate answer
            answer = self.generate_answer(question, documents)
            
            # Prepare sources
            sources = []
            for doc in documents:
                source_info = {
                    "course_code": doc.metadata.get("course_code", ""),
                    "course_title": doc.metadata.get("course_title", ""),
                    "section": doc.metadata.get("section", ""),
                    "doc_type": doc.metadata.get("doc_type", "")
                }
                if source_info not in sources:
                    sources.append(source_info)
            
            return {
                "answer": answer,
                "content_type": content_type,
                "sources": sources[:5],  # Limit sources
                "num_documents_retrieved": len(documents)
            }
            
        except Exception as e:
            logger.error(f"Error in query processing: {e}")
            return {
                "answer": f"I apologize, but I encountered an error while processing your question. For more information, please visit the official Gothenburg University website at https://www.gu.se/en/study-in-gothenburg",
                "content_type": "error",
                "sources": [],
                "num_documents_retrieved": 0
            }

    def get_system_info(self) -> Dict:
        """Get system information and statistics."""
        if not self.is_initialized:
            return {"status": "not_initialized"}
        
        try:
            collection = self.vector_store.get()
            total_docs = len(collection['ids'])
            
            # Count by document type
            doc_types = [metadata.get('doc_type', 'unknown') for metadata in collection['metadatas']]
            course_count = sum(1 for t in doc_types if t == 'course')
            program_count = sum(1 for t in doc_types if t == 'program')
            
            return {
                "status": "initialized",
                "total_documents": total_docs,
                "course_documents": course_count,
                "program_documents": program_count,
                "embedding_model": self.embedding_model,
                "llm_model": self.llm_model,
                "collection_name": self.collection_name
            }
        except Exception as e:
            logger.error(f"Error getting system info: {e}")
            return {"status": "error", "error": str(e)} 