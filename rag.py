# Standard library imports
import os
import json
import time
from typing import List, Dict, Literal, Optional
from datetime import datetime

# Third-party imports
import numpy as np
import gradio as gr
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# LangChain imports
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_chroma import Chroma
from langchain.chains import ConversationalRetrievalChain
from langchain.memory import ConversationBufferWindowMemory
from langchain.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser

# Load environment variables
load_dotenv()

#######################
# Constants and Templates
#######################

# Prompt Templates
COURSE_QUERY_TEMPLATE = """You are an AI language model assistant. Your task is to generate five
different versions of the given user question to retrieve relevant documents about university COURSES. 

Follow these guidelines:
1. Focus on different aspects: content, prerequisites, learning outcomes, examination methods
2. Use different phrasings and synonyms
3. Include the course code or name if present in the original question
4. Make queries both more specific and more general than the original
5. Ensure each query is semantically meaningful and complete

Original question: {question}

Generate 5 different versions, one per line."""

PROGRAM_QUERY_TEMPLATE = """You are an AI language model assistant. Your task is to generate five
different versions of the given user question to retrieve relevant documents about university PROGRAMS. 

Follow these guidelines:
1. Focus on different aspects: program structure, career opportunities, admission requirements, outcomes
2. Use different phrasings and synonyms
3. Include the program name if present in the original question
4. Make queries both more specific and more general than the original
5. Consider both overall program information and specific details

Original question: {question}

Generate 5 different versions, one per line."""

GENERAL_QUERY_TEMPLATE = """You are an AI language model assistant. Your task is to generate five
different versions of the given user question to retrieve relevant documents about both university COURSES and PROGRAMS. 

Follow these guidelines:
1. Balance between course-specific and program-level information
2. Include variations that focus on how courses fit into programs
3. Use different phrasings and synonyms
4. Make queries both more specific and more general than the original
5. Maintain the original intent while exploring different aspects

Original question: {question}

Generate 5 different versions, one per line."""

ROUTER_SYSTEM_TEMPLATE = """You are an expert at routing user questions about university education to the appropriate content type.
Your task is to determine whether the question is about:
1. A specific COURSE or course-related information
2. A specific PROGRAM or program-related information
3. BOTH when the question involves both courses and programs or when it's unclear

Examples:
- "What are the prerequisites for DIT134?" -> course
- "Tell me about the Software Engineering program" -> program
- "What courses are included in the Data Science master's?" -> both
- "How many credits do I need?" -> both"""

SYSTEM_TEMPLATE = """You are a helpful course and program information assistant for Gothenburg University. 
Your role is to provide accurate information about courses and programs based ONLY on the provided course and program documents.

Important rules to follow:
1. Only answer questions about courses that are explicitly mentioned in the provided documents
2. If a course is not in the documents, clearly state that you don't have information about that course
3. Base your answers solely on the content from the course documents
4. If you're unsure about any information, say so explicitly
5. When discussing course content, prerequisites, or evaluation methods, quote directly from the source documents when possible
6. Include the course code (e.g., DIT123) when referring to courses
7. For listing questions (e.g., "What programs are available?", "List all courses in X"):
   - ALWAYS check the sources list first
   - THOROUGHLY examine EACH source document listed in the sources
   - List EVERY program or course mentioned in ANY of the retrieved documents
   - Do not skip any programs even if they seem similar to others
   - Include program/course codes when available
   - Group items logically (e.g., by degree level: Bachelor's, Master's)
   - Double-check the sources list against your response to ensure no programs were missed
8. For questions asking about all programs from a specific school/department:
   - List ALL programs from the retrieved documents
   - Cross-reference the sources list with your response to ensure completeness
   - Include full program names and codes
   - Organize by degree level (Bachelor's/Master's)
   - Specify the credit amount if available
   - Before finishing your response, verify that you've included every program from every source listed

Context from documents: {context}

Current conversation history: {chat_history}

Human question: {question}

Remember: 
1. When asked to list programs or courses, THOROUGHLY check all retrieved documents and include EVERY relevant item. 
2. Do not summarize or skip any programs/courses found in the sources.
3. Always cross-reference your final list against the sources to ensure nothing was missed.
4. If you see a source in the list that contains "programme" or "program" in its name, make sure that program is included in your response.

Please provide a response based strictly on the above context. If the information isn't in the context, say so."""

#######################
# Helper Classes
#######################

class RouteQuery(BaseModel):
    """Route a user query to the most relevant content type."""
    content_type: Literal["course", "program", "both"] = Field(
        ...,
        description="Route to: 'course' for specific course questions, 'program' for program questions, 'both' when the question involves both or is unclear"
    )

class ChatLogger:
    """Handles logging of chat interactions."""
    def __init__(self, log_file: str = "chat_history.json"):
        self.log_file = log_file
        self._initialize_log_file()
    
    def _initialize_log_file(self):
        """Create log file if it doesn't exist."""
        if not os.path.exists(self.log_file):
            with open(self.log_file, 'w') as f:
                json.dump([], f)
    
    def log_interaction(self, data: Dict):
        """Log a single interaction to the JSON file."""
        try:
            # Read existing logs
            with open(self.log_file, 'r') as f:
                logs = json.load(f)
            
            # Add new log
            logs.append(data)
            
            # Write back to file
            with open(self.log_file, 'w') as f:
                json.dump(logs, f, indent=2)
        except Exception as e:
            print(f"Error logging interaction: {str(e)}")

#######################
# Document Processing
#######################

def get_unique_union(documents: List[List[Document]]) -> List[Document]:
    """Get unique union of retrieved documents."""
    seen = set()
    unique_docs = []
    
    for doc_list in documents:
        for doc in doc_list:
            # Create a unique identifier from content and metadata
            doc_id = f"{doc.page_content}_{json.dumps(doc.metadata, sort_keys=True)}"
            if doc_id not in seen:
                seen.add(doc_id)
                unique_docs.append(doc)
    
    return unique_docs

def process_documents(base_path: str) -> List[Document]:
    """Process both markdown and PDF documents from courses and programs directories.
    
    This function maintains a clear separation between course and program documents
    by properly tagging them with metadata and organizing them by type.
    
    Args:
        base_path: The base path where the data directories are located
        
    Returns:
        List of processed documents with proper metadata
    """
    documents = {
        'courses': [],
        'programs': []
    }
    
    # Define paths for different document types
    md_paths = {
        'courses': os.path.join(base_path, 'data/courses/md'),
        'programs': os.path.join(base_path, 'data/programs/md')
    }
    
    pdf_paths = {
        'courses': os.path.join(base_path, 'data/courses/pdf'),
        'programs': os.path.join(base_path, 'data/programs/pdf')
    }

    # Create directories if they don't exist
    for path_dict in [md_paths, pdf_paths]:
        for path in path_dict.values():
            if not os.path.exists(path):
                os.makedirs(path, exist_ok=True)
                print(f"Created directory: {path}")

    # Process documents by category
    for category in ['courses', 'programs']:
        # Process markdown files
        if os.path.exists(md_paths[category]):
            documents[category].extend(_process_markdown_files(md_paths[category], category))

        # Process PDF files
        if os.path.exists(pdf_paths[category]):
            documents[category].extend(_process_pdf_files(pdf_paths[category], category))
        
        print(f"Processed {len(documents[category])} {category} documents")

    # Combine all documents while maintaining their metadata
    all_documents = documents['courses'] + documents['programs']
    print(f"Total documents processed: {len(all_documents)}")
    print(f"Courses: {len(documents['courses'])}, Programs: {len(documents['programs'])}")
    
    return all_documents

def _process_markdown_files(path: str, category: str) -> List[Document]:
    """Helper function to process markdown files.
    
    Args:
        path: Path to the markdown files directory
        category: Type of documents ('courses' or 'programs')
        
    Returns:
        List of processed markdown documents with metadata
    """
    documents = []
    for filename in os.listdir(path):
        if filename.endswith('.md'):
            file_path = os.path.join(path, filename)
            try:
                content = _read_file_with_fallback_encoding(file_path)
                # Extract code if it's a course document
                metadata = {
                    'source': file_path,
                    'type': 'markdown',
                    'category': category,
                    'doc_type': category.rstrip('s'),  # 'course' or 'program'
                    'filename': filename
                }
                
                if category == 'courses':
                    code = _extract_course_code(filename, content)
                    if code:  # Only add course_code to metadata if it exists
                        metadata['course_code'] = code
                
                doc = Document(
                    page_content=content,
                    metadata=metadata
                )
                documents.append(doc)
            except Exception as e:
                print(f"Error processing markdown file {filename}: {str(e)}")
    return documents

def _process_pdf_files(path: str, category: str) -> List[Document]:
    """Helper function to process PDF files.
    
    Args:
        path: Path to the PDF files directory
        category: Type of documents ('courses' or 'programs')
        
    Returns:
        List of processed PDF documents with metadata
    """
    documents = []
    for filename in os.listdir(path):
        if filename.endswith('.pdf'):
            file_path = os.path.join(path, filename)
            try:
                loader = PyPDFLoader(file_path)
                pdf_docs = loader.load()
                
                # Create base metadata
                metadata = {
                    'type': 'pdf',
                    'category': category,
                    'doc_type': category.rstrip('s'),  # 'course' or 'program'
                    'filename': filename
                }
                
                # Add course code if it exists and it's a course document
                if category == 'courses' and pdf_docs:
                    code = _extract_course_code(filename, pdf_docs[0].page_content)
                    if code:  # Only add course_code to metadata if it exists
                        metadata['course_code'] = code
                
                # Add metadata to each page
                for doc in pdf_docs:
                    doc.metadata.update(metadata)
                documents.extend(pdf_docs)
            except Exception as e:
                print(f"Error processing PDF {filename}: {str(e)}")
    return documents

def _read_file_with_fallback_encoding(file_path: str) -> str:
    """Helper function to read files with different encodings."""
    encodings = ['utf-8', 'iso-8859-1', 'latin1']
    for encoding in encodings:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError(f"Failed to read {file_path} with any encoding")

def _extract_course_code(filename: str, content: str) -> Optional[str]:
    """Extract course code from filename or content if possible.
    
    Args:
        filename: Name of the file
        content: Content of the document
        
    Returns:
        Course code if found, None otherwise
    """
    # Try to extract from filename first (e.g., "DIT134-advanced-programming.pdf")
    import re
    code_match = re.search(r'([A-Z]{3}\d{3})', filename)
    if code_match:
        return code_match.group(1)
    
    # Try to extract from content
    code_match = re.search(r'([A-Z]{3}\d{3})', content)
    if code_match:
        return code_match.group(1)
    
    return None

#######################
# Main RAG Model Class
#######################

class RAGModel:
    """Main RAG (Retrieval-Augmented Generation) model class."""
    
    def __init__(self, pdf_folder_path: str):
        """Initialize the RAG model with the path to PDF documents."""
        self.pdf_folder_path = pdf_folder_path
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        if not self.openai_api_key:
            raise ValueError("OpenAI API key not found in environment variables")
        
        self._initialize_components()
        self._setup_prompts()
        
    def _initialize_components(self):
        """Initialize all necessary components."""
        # Initialize AI models
        self.llm = ChatOpenAI(
            model_name="gpt-4o-mini",  # do not change this
            temperature=0.1,
            openai_api_key=self.openai_api_key
        )
        self.embeddings = OpenAIEmbeddings(
            openai_api_key=self.openai_api_key, 
            model="text-embedding-3-small"
        )
        
        # Initialize text splitter
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=2000,
            chunk_overlap=200,
            length_function=len,
            separators=["\n\n", "\n", " ", ""]
        )
        
        # Initialize memory
        self.memory = ConversationBufferWindowMemory(
            memory_key="chat_history",
            output_key="answer",
            return_messages=True,
            k=3
        )
        
        # Initialize other components
        self.vector_store = None
        self.qa_chain = None
        self.model_version = "gpt-4o-mini"  # do not change this
        self.embedding_version = "text-embedding-3-small"
        
        # Add chat logger
        self.chat_logger = ChatLogger()

    def _setup_prompts(self):
        """Set up all prompt templates."""
        # Router prompt
        self.router_prompt = ChatPromptTemplate.from_messages([
            ("system", ROUTER_SYSTEM_TEMPLATE),
            ("human", "{question}")
        ])
        self.router = self.router_prompt | self.llm.with_structured_output(RouteQuery)
        
        # Query prompts
        self.query_prompts = {
            "course": ChatPromptTemplate.from_template(COURSE_QUERY_TEMPLATE),
            "program": ChatPromptTemplate.from_template(PROGRAM_QUERY_TEMPLATE),
            "both": ChatPromptTemplate.from_template(GENERAL_QUERY_TEMPLATE)
        }
        
        # Answer prompt
        messages = [
            SystemMessagePromptTemplate.from_template(SYSTEM_TEMPLATE),
            HumanMessagePromptTemplate.from_template("{question}")
        ]
        self.prompt = ChatPromptTemplate.from_messages(messages)

    def route_query(self, question: str) -> str:
        """Route the query to the appropriate content type."""
        result = self.router.invoke({"question": question})
        return result.content_type

    def generate_queries(self, question: str, content_type: str) -> List[str]:
        """Generate multiple versions of the input question based on content type.
        
        This method creates semantically diverse query variations to improve retrieval:
        1. Uses different phrasings and synonyms
        2. Focuses on different aspects based on content type
        3. Maintains the original intent while exploring variations
        
        Args:
            question: The original user question
            content_type: The type of content to focus on ('course', 'program', or 'both')
            
        Returns:
            List of query variations (usually 5)
        """
        # Select appropriate prompt template
        prompt = self.query_prompts[content_type]
        
        # Generate variations using the LLM
        chain = prompt | self.llm | StrOutputParser()
        variations = chain.invoke({"question": question})
        
        # Process and clean the variations
        queries = [q.strip() for q in variations.split('\n') if q.strip()]
        
        # Always include the original question
        if question not in queries:
            queries.append(question)
        
        # Store for logging
        self.last_generated_queries = queries
        
        # Ensure we have at least 3 queries
        if len(queries) < 3:
            print("Warning: Generated fewer than 3 query variations")
        
        return queries

    def retrieve_documents(self, question: str, content_type: str) -> List[Document]:
        """Retrieve documents using multiple queries and content type.
        
        This method implements:
        1. Multi-query generation based on content type
        2. Document filtering based on content type
        3. MMR-based retrieval for diversity
        
        Args:
            question: The original user question
            content_type: The routing type ('course', 'program', or 'both')
            
        Returns:
            List of relevant documents
        """
        # Generate multiple variations of the query
        queries = self.generate_queries(question, content_type)
        print(f"\nGenerated queries for '{question}':")
        for q in queries:
            print(f"  • {q}")
        
        # Set retrieval parameters based on content type
        k_values = {
            "course": 6,     # More focused for specific course info
            "program": 15,   # Increased from 8 to 15 for better program coverage
            "both": 15       # Increased from 10 to 15 for better coverage
        }
        
        # Create metadata filter based on content type
        metadata_filter = None
        if content_type != "both":
            metadata_filter = {"doc_type": content_type}
        
        # Configure the retriever for MMR
        retriever = self.vector_store.as_retriever(
            search_type="mmr",
            search_kwargs={
                "k": k_values[content_type],
                "filter": metadata_filter,
                "fetch_k": k_values[content_type] * 3  # Fetch more candidates for MMR to choose from
            }
        )
        
        # Retrieve documents for each query variation
        all_docs = []
        for query in queries:
            # Use the retriever to get documents
            docs = retriever.get_relevant_documents(query)
            all_docs.append(docs)
        
        # Get unique union of documents
        unique_docs = get_unique_union(all_docs)
        
        # Log retrieval statistics
        doc_types = [doc.metadata.get('doc_type') for doc in unique_docs]
        print(f"\nRetrieved {len(unique_docs)} unique documents:")
        print(f"  • Courses: {doc_types.count('course')}")
        print(f"  • Programs: {doc_types.count('program')}")
        
        return unique_docs

    def query(self, question: str) -> Dict:
        """Process a user query and return the response."""
        if not self.qa_chain:
            raise ValueError("Model not initialized. Please load documents first.")
        
        start_time = time.time()
        try:
            result = self._process_query(question, start_time)
            
            # Log the interaction with enhanced information
            log_data = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "query": {
                    "original_question": question,
                    "content_type": result["content_type"],
                    "generated_queries": self.last_generated_queries if hasattr(self, 'last_generated_queries') else []
                },
                "retrieval": {
                    "total_documents": len(result["source_documents"]),
                    "documents": [
                        {
                            "content": doc.page_content,
                            "metadata": doc.metadata,
                            "source": os.path.basename(doc.metadata.get("source", ""))
                        }
                        for doc in result["source_documents"]
                    ],
                    "document_types": {
                        "course": sum(1 for doc in result["source_documents"] if doc.metadata.get("doc_type") == "course"),
                        "program": sum(1 for doc in result["source_documents"] if doc.metadata.get("doc_type") == "program")
                    }
                },
                "response": {
                    "answer": result["answer"]
                },
                "performance": {
                    "processing_time": time.time() - start_time,
                    "tokens_used": None  # TODO: Add token usage if available
                },
                "chat_context": {
                    "chat_history": [
                        {"role": msg.type, "content": msg.content}
                        for msg in self.memory.chat_memory.messages[-3:]  # Last 3 messages
                    ],
                    "memory_window_size": self.memory.k
                },
                "system_info": {
                    "model_version": self.model_version,
                    "embedding_version": self.embedding_version,
                    "search_config": {
                        "search_type": "mmr",
                        "k_value": result.get("k_value", None),
                        "metadata_filter": result.get("metadata_filter", None)
                    }
                }
            }
            
            self.chat_logger.log_interaction(log_data)
            return result
            
        except Exception as e:
            return {
                "answer": f"Error processing query: {str(e)}",
                "source_documents": [],
                "content_type": None,
                "evaluation_metrics": None
            }

    def _process_query(self, question: str, start_time: float) -> Dict:
        """Helper method to process a query."""
        # Route and retrieve
        content_type = self.route_query(question)
        docs = self.retrieve_documents(question, content_type)
        docs_content = "\n\n".join([d.page_content for d in docs])
        
        # Generate answer
        chain = self.prompt | self.llm | StrOutputParser()
        answer = chain.invoke({
            "context": docs_content,
            "question": question,
            "chat_history": self.memory.chat_memory.messages
        })
        
        # Update memory
        self.memory.save_context({"question": question}, {"answer": answer})
        
        # Format sources
        sources = list(set(os.path.basename(doc.metadata.get("source", "")) for doc in docs if doc.metadata.get("source")))
        sources = sorted(sources)  # Sort alphabetically
        
        if sources:
            if len(sources) > 2:
                # Show only first 2 sources with a note about more
                visible_sources = sources[:2]
                hidden_sources = sources[2:]
                answer += "\n\nSources:"
                for source in visible_sources:
                    answer += f"\n• {source}"
                answer += f"\n<details><summary>**See {len(hidden_sources)} more sources...**</summary>\n"
                for source in hidden_sources:
                    answer += f"\n• {source}"
                answer += "\n</details>"
            else:
                # If 2 or fewer sources, show all
                answer += "\n\nSources:"
                for source in sources:
                    answer += f"\n• {source}"
        
        # Update metrics
        query_time = time.time() - start_time
        
        return {
            "answer": answer,
            "source_documents": docs,
            "content_type": content_type
        }

    def load_documents(self) -> int:
        """Load and process PDF documents."""
        try:
            start_time = time.time()
            
            if os.path.exists("./data/chroma") and os.listdir("./data/chroma"):
                return self._load_existing_database()
            else:
                return self._create_new_database()
            
        except Exception as e:
            print(f"Error loading documents: {str(e)}")
            raise

    def _load_existing_database(self) -> int:
        """Helper method to load existing database."""
        print("Loading existing embeddings from Chroma database...")
        self.vector_store = Chroma(
            persist_directory="./data/chroma",
            embedding_function=self.embeddings,
            collection_metadata={"hnsw:space": "cosine"},
            collection_name="course_docs"
        )
        collection_size = len(self.vector_store.get()['ids'])
        print(f"Loaded {collection_size} existing document chunks from database.")
        self._initialize_qa_chain()
        return collection_size

    def _create_new_database(self) -> int:
        """Helper method to create new database."""
        print("Creating new embeddings (this will incur OpenAI API costs)...")
        documents = process_documents(".")
        chunks = self.text_splitter.split_documents(documents)
        
        self.vector_store = Chroma.from_documents(
            documents=chunks,
            embedding=self.embeddings,
            persist_directory="./data/chroma",
            collection_metadata={"hnsw:space": "cosine"},
            collection_name="course_docs"
        )
        
        self._initialize_qa_chain()
        return len(chunks)

    def _initialize_qa_chain(self):
        """Initialize the QA chain with specific configuration."""
        self.qa_chain = ConversationalRetrievalChain.from_llm(
            llm=self.llm,
            retriever=self.vector_store.as_retriever(
                search_type="mmr",
                search_kwargs={"k": 8}
            ),
            memory=self.memory,
            return_source_documents=True,
            combine_docs_chain_kwargs={"prompt": self.prompt},
            verbose=True
        )

#######################
# Gradio Interface
#######################

def create_gradio_interface(rag_model: RAGModel) -> gr.Blocks:
    """Create and configure the Gradio interface."""
    
    def process_query(message: str, history: List[List[str]]) -> str:
        """Process a single query in the chat interface."""
        try:
            response = rag_model.query(message)
            content_type = response["content_type"]
            answer = response["answer"]
            
            # Add routing information
            routing_info = {
                "course": "🎓 Course-specific response:",
                "program": "📚 Program-specific response:",
                "both": "🏫 General education response:"
            }
            
            return f"{routing_info.get(content_type, '')} \n\n{answer}"
        except Exception as e:
            return f"Error: {str(e)}"

    # Create the interface
    with gr.Blocks(theme=gr.themes.Soft()) as interface:
        gr.Markdown("""
        # GuPT: Gothenburg University Information Assistant
        Ask questions about Gothenburg University's courses and programs.
        """)
        
        with gr.Row(equal_height=True):
            # Chat column (2/3 of width)
            with gr.Column(scale=2):
                chat_interface = gr.ChatInterface(
                    fn=process_query,
                    examples=[
                        "What is the Applied Data Science program about?",
                        "What are the prerequisites for Applied Machine Learning?",
                        "Tell me about courses in the Master's Program in Management.",
                        "List all master's programs in the School of Business, Economics and Law.",
                        "What programs are available in Computer Science?"
                    ],
                    css="""
                    div.message-wrap { height: 600px !important; overflow-y: auto; }
                    details { margin-top: 10px; }
                    summary { cursor: pointer; color: #2A6BB0; }
                    summary:hover { text-decoration: underline; }
                    """,
                    type="messages"
                )
            
            # Info column (1/3 of width)
            with gr.Column(scale=1):
                # Get initial collection info
                collection = rag_model.vector_store.get()
                doc_metadata = [m.get('doc_type', 'unknown') for m in collection['metadatas']]
                course_count = sum(1 for t in doc_metadata if t == 'course')
                program_count = sum(1 for t in doc_metadata if t == 'program')
                
                gr.Markdown(f"""
                ### Document Collection
                - Course Documents: {course_count}
                - Program Documents: {program_count}
                - Total Documents: {len(doc_metadata)}
                
                ### Search Configuration
                - Using MMR for diverse results
                - Course queries: top 6 matches
                - Program queries: top 15 matches
                - Mixed queries: top 15 matches
                
                ### Query Types
                
                🎓 **Course Queries**
                - Specific course information
                - Prerequisites and requirements
                - Learning outcomes
                
                📚 **Program Queries**
                - Program overviews
                - Available programs by department
                - Program requirements
                
                🏫 **General Queries**
                - Courses within programs
                - Department offerings
                - Combined course/program information
                """)

    return interface

#######################
# Main Entry Point
#######################

def main():
    """Main entry point of the application."""
    # Initialize RAG model
    rag_model = RAGModel(".")
    
    # Load and process documents
    print("Loading and processing documents...")
    num_chunks = rag_model.load_documents()
    print(f"Processed {num_chunks} document chunks")
    
    # Create and launch Gradio interface
    interface = create_gradio_interface(rag_model)
    interface.launch(share=False)

if __name__ == "__main__":
    main()
