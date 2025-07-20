from google import genai
from google.genai import types
import json
import os
from pathlib import Path
import numpy as np # Still useful for some operations if needed, but not core for Chroma
import logging
import textwrap
import chromadb
from chromadb import Documents, EmbeddingFunction, Embeddings

# --- Configuration ---
# Try GEMINI_API_KEY first for backwards compatibility, then GOOGLE_API_KEY
API_KEY = os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
if not API_KEY:
    raise ValueError("GEMINI_API_KEY or GOOGLE_API_KEY environment variable not set.")

# Create the client - using the new SDK approach
client = genai.Client(api_key=API_KEY)

EMBEDDING_MODEL_NAME = 'text-embedding-004'
GENERATIVE_MODEL_NAME = 'gemini-2.5-flash-preview-05-20'

# Path to your JSON course data - using relative path from current directory
COURSE_DATA_PATH = Path("data") / "json" / "courses_syllabus"
# For local testing, you might use:
# COURSE_DATA_PATH = Path("./course_data") 
# COURSE_DATA_PATH.mkdir(parents=True, exist_ok=True) # Ensure it exists if testing locally

# Optional: Path for ChromaDB persistence
CHROMA_PERSIST_DIRECTORY = Path("./chroma_db_store")  # Enable persistence
if CHROMA_PERSIST_DIRECTORY:
    CHROMA_PERSIST_DIRECTORY.mkdir(parents=True, exist_ok=True)


# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Student Counselor System Prompt ---
SYSTEM_TEMPLATE = """You are an experienced and knowledgeable student counselor for Gothenburg University's Department of Computer Science and Engineering. Your role is to guide both prospective and current students through their academic journey with comprehensive, accurate, and supportive advice.

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

**Your Response:** [Provide comprehensive, accurate guidance based on the course documents above]
"""

# --- Helper Functions ---

def load_and_prepare_course_data(data_path: Path) -> list[dict]:
    """Loads JSON files and prepares them for embedding and storage with section-based chunking."""
    prepared_docs = []
    if not data_path.exists() or not data_path.is_dir():
        logger.error(f"Data path {data_path} does not exist or is not a directory.")
        return []

    total_sections = 0
    for file_path in data_path.glob("*.json"):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                course_data = json.load(f)

            metadata = course_data.get("metadata", {})
            course_code = metadata.get('course_code', file_path.stem)
            course_title = metadata.get('course_title', 'N/A')
            
            # Create base metadata that will be shared across all sections
            base_chroma_metadata = {}
            for k, v in metadata.items():
                if isinstance(v, (list, dict)):
                    try:
                        base_chroma_metadata[k] = json.dumps(v) # Serialize lists/dicts
                    except TypeError:
                        base_chroma_metadata[k] = str(v) # Fallback
                elif v is None:
                    base_chroma_metadata[k] = "" # Chroma doesn't like None
                else:
                    base_chroma_metadata[k] = v
            
            base_chroma_metadata['source_doc_filename'] = metadata.get('source_document', file_path.name)

            # Process each section as a separate document
            sections = course_data.get("sections", {})
            course_sections_count = 0
            
            for section_title, section_content in sections.items():
                if not section_content or not section_content.strip():
                    continue  # Skip empty sections
                
                # Create section-specific ID and content
                section_id_safe = section_title.lower().replace(" ", "_").replace("/", "_").replace("-", "_")
                section_id_safe = "".join(c for c in section_id_safe if c.isalnum() or c == "_")
                document_id = f"{course_code}_{section_id_safe}"
                
                # Create content with course context + section content
                section_text = f"""Course: {course_code} - {course_title}
Section: {section_title}

{section_content}"""

                # Create section-specific metadata (copy base + add section info)
                section_metadata = base_chroma_metadata.copy()
                section_metadata['section_title'] = section_title
                section_metadata['document_type'] = 'course_section'
                
                prepared_docs.append({
                    "id": document_id,
                    "content": section_text,
                    "metadata": section_metadata,
                    "original_metadata": metadata,
                    "source_document": metadata.get('source_document', file_path.name),
                    "section_title": section_title
                })
                course_sections_count += 1
                total_sections += 1
            
            logger.info(f"Loaded {file_path.name}: {course_sections_count} sections from {course_code}")
            
        except json.JSONDecodeError:
            logger.error(f"Error decoding JSON from {file_path}")
        except Exception as e:
            logger.error(f"Error processing file {file_path}: {e}")
    
    logger.info(f"📚 Total: {total_sections} sections prepared for embedding from {len(list(data_path.glob('*.json')))} course files")
    
    # Check for duplicate course titles and warn user
    title_groups = {}
    for doc in prepared_docs:
        title = doc['original_metadata'].get('course_title', 'Unknown')
        course_code = doc['original_metadata'].get('course_code', 'Unknown')
        if title not in title_groups:
            title_groups[title] = []
        title_groups[title].append(course_code)
    
    duplicates_found = []
    for title, codes in title_groups.items():
        unique_codes = list(set(codes))  # Remove duplicates from sections
        if len(unique_codes) > 1:
            duplicates_found.append((title, unique_codes))
    
    if duplicates_found:
        logger.warning("⚠️ DUPLICATE COURSE TITLES DETECTED:")
        for title, codes in duplicates_found:
            logger.warning(f"   '{title}' appears in courses: {', '.join(codes)}")
        logger.warning("   Consider keeping only the most recent version of each course.")
        logger.warning("   Check confirmation_date and valid_from_date to identify latest versions.")
    
    return prepared_docs

# --- ChromaDB Integration ---

class GoogleGenAiEmbeddingFunction(EmbeddingFunction):
    """Custom embedding function for ChromaDB using Google GenAI."""
    def __init__(self, client: genai.Client, model_name: str = EMBEDDING_MODEL_NAME):
        self._client = client
        self._model_name = model_name
        logger.info(f"GoogleGenAiEmbeddingFunction initialized with model: {self._model_name}")

    def __call__(self, input_texts: Documents) -> Embeddings:
        # Default task_type for general batch embedding (usually for documents)
        # Chroma typically calls this for adding documents.
        logger.debug(f"Embedding {len(input_texts)} texts with task_type RETRIEVAL_DOCUMENT")
        response = self._client.models.embed_content(
            model=self._model_name,
            contents=input_texts,
            config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT")
        )
        if not hasattr(response, 'embeddings') or response.embeddings is None:
            logger.error(f"Embedding failed for {len(input_texts)} texts. Response: {response}")
            # Return list of empty lists or raise error
            raise ValueError(f"Embedding failed. Check API logs. Response attributes: {dir(response)}")
        
        # Extract the values from ContentEmbedding objects
        return [embedding.values for embedding in response.embeddings]

    # It's good practice for Chroma embedding functions to handle single text and list of texts for queries
    def embed_query(self, query_text: str) -> list[float]:
        """Embeds a single query text."""
        logger.debug(f"Embedding query with task_type RETRIEVAL_QUERY: '{textwrap.shorten(query_text, 50)}'")
        response = self._client.models.embed_content(
            model=self._model_name,
            contents=query_text, # Single string for query
            config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY")
        )
        if not hasattr(response, 'embeddings') or response.embeddings is None:
            logger.error(f"Query embedding failed. Response: {response}")
            raise ValueError("Query embedding failed.")
        return response.embeddings[0].values # Return the values from the first ContentEmbedding

    def embed_documents(self, doc_texts: list[str]) -> list[list[float]]:
        """Embeds a list of document texts."""
        logger.debug(f"Embedding {len(doc_texts)} documents with task_type RETRIEVAL_DOCUMENT")
        response = self._client.models.embed_content(
            model=self._model_name,
            contents=doc_texts,
            config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT")
        )
        if not hasattr(response, 'embeddings') or response.embeddings is None:
            logger.error(f"Document list embedding failed. Response: {response}")
            raise ValueError("Document list embedding failed.")
        
        # Extract the values from ContentEmbedding objects
        return [embedding.values for embedding in response.embeddings]


class ChromaVectorStore:
    def __init__(self, genai_client: genai.Client, collection_name="course_syllabi_collection", persist_directory=None):
        self.collection_name = collection_name
        self.embedding_function = GoogleGenAiEmbeddingFunction(genai_client)

        if persist_directory:
            self.client = chromadb.PersistentClient(path=str(persist_directory))
            logger.info(f"Using persistent ChromaDB client at {persist_directory}")
        else:
            self.client = chromadb.Client() # In-memory client
            logger.info("Using in-memory ChromaDB client.")

        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            embedding_function=self.embedding_function,
            metadata={"hnsw:space": "cosine"} # Explicitly set cosine distance
        )
        logger.info(f"ChromaDB collection '{self.collection_name}' ready. Initial item count: {self.collection.count()}")

    def build_store(self, prepared_docs: list[dict]):
        if not prepared_docs:
            logger.warning("No documents provided to build the Chroma vector store.")
            return

        doc_ids = [doc['id'] for doc in prepared_docs]
        doc_contents = [doc['content'] for doc in prepared_docs]
        doc_metadatas = [doc['metadata'] for doc in prepared_docs] # Already prepped for Chroma

        # Smart embedding: Check for existing documents to avoid re-embedding
        total_docs_to_process = len(doc_ids)
        existing_count = self.collection.count()
        
        if existing_count > 0:
            logger.info(f"Found existing ChromaDB collection with {existing_count} documents. Checking for duplicates...")
            try:
                # Get all existing IDs in the collection to avoid duplicates
                existing_docs_result = self.collection.get(ids=doc_ids)
                existing_ids_in_db = set(existing_docs_result['ids'])
                logger.info(f"Found {len(existing_ids_in_db)} documents that are already embedded from the current batch.")

                # Filter out docs that are already in the DB
                new_doc_ids = []
                new_doc_contents = []
                new_doc_metadatas = []
                skipped_docs = []
                
                for i, doc_id in enumerate(doc_ids):
                    if doc_id not in existing_ids_in_db:
                        new_doc_ids.append(doc_id)
                        new_doc_contents.append(doc_contents[i])
                        new_doc_metadatas.append(doc_metadatas[i])
                    else:
                        skipped_docs.append(doc_id)
                
                doc_ids, doc_contents, doc_metadatas = new_doc_ids, new_doc_contents, new_doc_metadatas
                
                if skipped_docs:
                    logger.info(f"Skipping {len(skipped_docs)} already embedded documents: {skipped_docs[:5]}{'...' if len(skipped_docs) > 5 else ''}")
                
                if not doc_ids:
                    logger.info("✅ All documents are already embedded! No new embeddings needed.")
                    logger.info(f"📊 Database status: {existing_count} total documents in collection.")
                    return
                    
                logger.info(f"📝 Will embed {len(doc_ids)} new documents out of {total_docs_to_process} total files.")

            except Exception as e: # Handle cases where get might fail if some IDs not found etc.
                logger.warning(f"Could not check for existing documents, will proceed to add all: {e}")
        else:
            logger.info(f"🔄 Empty database detected. Will embed all {total_docs_to_process} documents for the first time.")
        
        if not doc_ids:
            logger.info("No new documents to add after filtering existing ones.")
            return

        # Batch documents to avoid Google's 100 request limit per batch
        batch_size = 50  # Conservative batch size to stay well under the 100 limit
        total_docs = len(doc_ids)
        
        try:
            for i in range(0, total_docs, batch_size):
                end_idx = min(i + batch_size, total_docs)
                batch_ids = doc_ids[i:end_idx]
                batch_contents = doc_contents[i:end_idx]
                batch_metadatas = doc_metadatas[i:end_idx]
                
                logger.info(f"Adding batch {i//batch_size + 1} of {(total_docs + batch_size - 1)//batch_size}: documents {i+1}-{end_idx} of {total_docs}")
                
                # ChromaDB's add method will use the collection's embedding_function
                # to generate embeddings for doc_contents.
                self.collection.add(
                    ids=batch_ids,
                    documents=batch_contents, # These are the texts to be embedded by Chroma
                    metadatas=batch_metadatas
                )
                
                logger.info(f"Successfully added batch {i//batch_size + 1} ({len(batch_ids)} documents)")
            
            final_count = self.collection.count()
            logger.info(f"✅ Successfully embedded {total_docs} new documents!")
            logger.info(f"📊 Database now contains {final_count} total documents in collection '{self.collection_name}'")
        except Exception as e:
            logger.error(f"Error adding documents to Chroma: {e}", exc_info=True)

    def find_relevant_documents(self, query_text: str, top_k: int = 3, custom_filter: dict = None) -> list[dict]:
        if self.collection.count() == 0:
            logger.warning("Chroma collection is empty. Cannot find relevant documents.")
            return []

        try:
            # Chroma's query method uses the collection's embedding_function
            # to embed the query_texts.
            results = self.collection.query(
                query_texts=[query_text], # Expects a list of query texts
                n_results=min(top_k, self.collection.count()), # Don't ask for more than available
                where=custom_filter,
                include=['metadatas', 'documents', 'distances']
            )
        except Exception as e:
            logger.error(f"Error querying Chroma collection: {e}", exc_info=True)
            return []

        relevant_docs = []
        if results and results.get('ids') and results['ids'][0]: # Check if results for the first query exist
            retrieved_ids = results['ids'][0]
            retrieved_documents_content = results['documents'][0]
            retrieved_metadatas = results['metadatas'][0]
            retrieved_distances = results['distances'][0]

            for i in range(len(retrieved_ids)):
                # Deserialize metadata (e.g., 'programmes' list)
                original_style_metadata = {}
                if retrieved_metadatas[i]:
                    for k, v_json_str in retrieved_metadatas[i].items():
                        # Attempt to parse known list/dict fields (e.g., "programmes")
                        if k == "programmes" and isinstance(v_json_str, str):
                            try:
                                original_style_metadata[k] = json.loads(v_json_str)
                            except json.JSONDecodeError:
                                original_style_metadata[k] = v_json_str # Keep as string if not valid JSON
                        else:
                            original_style_metadata[k] = v_json_str
                
                doc_detail = {
                    "id": retrieved_ids[i],
                    "content": retrieved_documents_content[i], # The text that was embedded
                    "metadata": original_style_metadata, # Original structure metadata
                    "source_document": original_style_metadata.get('source_doc_filename', 'N/A'),
                    "distance": retrieved_distances[i] # Cosine distance
                }
                relevant_docs.append(doc_detail)
            
            logger.info(f"Retrieved {len(relevant_docs)} relevant sections from Chroma for query: '{query_text}'")
            for i, doc in enumerate(relevant_docs):
                course_code = doc['metadata'].get('course_code', 'N/A')
                section_title = doc['metadata'].get('section_title', 'Unknown Section')
                logger.debug(f"  Doc {i+1}: {course_code} - {section_title}, Distance: {doc.get('distance', 'N/A'):.4f}")
        else:
            logger.info(f"No documents found in Chroma for query: '{query_text}'")

        return relevant_docs

    def find_courses_by_program(self, program_name: str, top_k: int = 10) -> list[dict]:
        """Find courses that belong to a specific program."""
        try:
            # Try different matching strategies for program names
            filter_options = [
                {"programmes": {"$contains": program_name.lower()}},
                {"programmes": {"$contains": program_name}},
            ]
            
            # Add keyword-based filters for flexible matching
            keywords = [word for word in program_name.lower().split() if len(word) > 3]
            for keyword in keywords[:2]:  # Try first 2 significant keywords
                filter_options.append({"programmes": {"$contains": keyword}})
            
            results = None
            for filter_option in filter_options:
                try:
                    results = self.collection.query(
                        query_texts=[program_name],
                        n_results=min(top_k, self.collection.count()),
                        where=filter_option,
                        include=['metadatas', 'documents', 'distances']
                    )
                    if results and results.get('ids') and results['ids'][0]:
                        logger.info(f"✅ Found program matches using filter: {filter_option}")
                        break
                except Exception as filter_error:
                    logger.debug(f"Filter {filter_option} failed: {filter_error}")
                    continue
            
            if not results or not results.get('ids') or not results['ids'][0]:
                logger.warning(f"No direct program matches found for '{program_name}', falling back to semantic search")
                return self.find_relevant_documents(f"programme program {program_name}", top_k)
            
            return self._process_query_results(results, f"program '{program_name}'")
        except Exception as e:
            logger.warning(f"Program filter failed, falling back to semantic search: {e}")
            return self.find_relevant_documents(f"programme program {program_name}", top_k)

    def find_courses_by_credits(self, credits: str, top_k: int = 10) -> list[dict]:
        """Find courses with specific credit values."""
        try:
            results = self.collection.query(
                query_texts=[f"{credits} credits course"],
                n_results=min(top_k, self.collection.count()),
                where={"credits": credits},
                include=['metadatas', 'documents', 'distances']
            )
            return self._process_query_results(results, f"courses with {credits} credits")
        except Exception as e:
            logger.warning(f"Credits filter failed: {e}")
            return []

    def find_courses_by_cycle(self, cycle: str, query_text: str = "", top_k: int = 10) -> list[dict]:
        """Find courses by academic cycle (First cycle, Second cycle, Third cycle)."""
        try:
            search_query = query_text if query_text else f"{cycle} level courses"
            results = self.collection.query(
                query_texts=[search_query],
                n_results=min(top_k, self.collection.count()),
                where={"cycle": cycle},
                include=['metadatas', 'documents', 'distances']
            )
            return self._process_query_results(results, f"{cycle.lower()} courses")
        except Exception as e:
            logger.warning(f"Cycle filter failed: {e}")
            return []

    def find_courses_by_language(self, language: str, query_text: str = "", top_k: int = 10) -> list[dict]:
        """Find courses taught in a specific language."""
        try:
            search_query = query_text if query_text else f"courses taught in {language}"
            results = self.collection.query(
                query_texts=[search_query],
                n_results=min(top_k, self.collection.count()),
                where={"language_of_instruction": language},
                include=['metadatas', 'documents', 'distances']
            )
            return self._process_query_results(results, f"courses in {language}")
        except Exception as e:
            logger.warning(f"Language filter failed: {e}")
            return []

    def find_courses_by_department(self, department: str, query_text: str = "", top_k: int = 10) -> list[dict]:
        """Find courses from a specific department."""
        try:
            search_query = query_text if query_text else f"courses from {department}"
            results = self.collection.query(
                query_texts=[search_query],
                n_results=min(top_k, self.collection.count()),
                where={"department": {"$contains": department}},
                include=['metadatas', 'documents', 'distances']
            )
            return self._process_query_results(results, f"courses from {department}")
        except Exception as e:
            logger.warning(f"Department filter failed: {e}")
            return []

    def get_all_programs(self) -> list[str]:
        """Get a list of all available programs from the metadata."""
        try:
            # Get a sample of documents to extract program information
            all_docs = self.collection.get(limit=1000, include=['metadatas'])
            programs = set()
            
            for metadata in all_docs['metadatas']:
                if metadata and 'programmes' in metadata:
                    try:
                        # Deserialize the programmes list
                        programmes_list = json.loads(metadata['programmes'])
                        if isinstance(programmes_list, list):
                            programs.update(programmes_list)
                    except (json.JSONDecodeError, TypeError):
                        # Handle cases where programmes is already a string
                        if isinstance(metadata['programmes'], str):
                            programs.add(metadata['programmes'])
            
            return sorted(list(programs))
        except Exception as e:
            logger.error(f"Error retrieving programs: {e}")
            return []

    def get_metadata_summary(self) -> dict:
        """Get a summary of available metadata values for filtering."""
        try:
            # Get a representative sample
            sample_docs = self.collection.get(limit=500, include=['metadatas'])
            summary = {
                'programs': set(),
                'credits': set(),
                'cycles': set(),
                'languages': set(),
                'departments': set(),
                'total_sections': self.collection.count()
            }
            
            for metadata in sample_docs['metadatas']:
                if not metadata:
                    continue
                    
                # Extract unique values
                if 'programmes' in metadata:
                    try:
                        programmes_list = json.loads(metadata['programmes'])
                        if isinstance(programmes_list, list):
                            summary['programs'].update(programmes_list)
                    except (json.JSONDecodeError, TypeError):
                        if isinstance(metadata['programmes'], str):
                            summary['programs'].add(metadata['programmes'])
                
                for key, summary_key in [
                    ('credits', 'credits'),
                    ('cycle', 'cycles'), 
                    ('language_of_instruction', 'languages'),
                    ('department', 'departments')
                ]:
                    if key in metadata and metadata[key]:
                        summary[summary_key].add(metadata[key])
            
            # Convert sets to sorted lists
            for key in ['programs', 'credits', 'cycles', 'languages', 'departments']:
                summary[key] = sorted(list(summary[key]))
            
            return summary
        except Exception as e:
            logger.error(f"Error generating metadata summary: {e}")
            return {}

    def _process_query_results(self, results, search_description: str) -> list[dict]:
        """Helper method to process ChromaDB query results."""
        relevant_docs = []
        if results and results.get('ids') and results['ids'][0]:
            retrieved_ids = results['ids'][0]
            retrieved_documents_content = results['documents'][0]
            retrieved_metadatas = results['metadatas'][0]
            retrieved_distances = results['distances'][0]

            for i in range(len(retrieved_ids)):
                # Deserialize metadata
                original_style_metadata = {}
                if retrieved_metadatas[i]:
                    for k, v_json_str in retrieved_metadatas[i].items():
                        if k == "programmes" and isinstance(v_json_str, str):
                            try:
                                original_style_metadata[k] = json.loads(v_json_str)
                            except json.JSONDecodeError:
                                original_style_metadata[k] = v_json_str
                        else:
                            original_style_metadata[k] = v_json_str
                
                doc_detail = {
                    "id": retrieved_ids[i],
                    "content": retrieved_documents_content[i],
                    "metadata": original_style_metadata,
                    "source_document": original_style_metadata.get('source_doc_filename', 'N/A'),
                    "distance": retrieved_distances[i]
                }
                relevant_docs.append(doc_detail)
            
            logger.info(f"Retrieved {len(relevant_docs)} sections for {search_description}")
        else:
            logger.info(f"No sections found for {search_description}")

        return relevant_docs


def format_chat_history(history: list[dict]) -> str:
    """Formats the chat history for the prompt."""
    if not history:
        return "No previous conversation."
    formatted_history = []
    for entry in history:
        role = "User" if entry.get("role") == "user" else "Assistant"
        text = entry.get("text", "[non-text content]")
        formatted_history.append(f"{role}: {text}")
    return "\n".join(formatted_history)


# --- Main Chatbot Logic ---
def run_chatbot():
    logger.info("Initializing chatbot with ChromaDB...")

    if not COURSE_DATA_PATH.exists() or not any(COURSE_DATA_PATH.iterdir()):
        logger.error(f"Course data path {COURSE_DATA_PATH} is empty or does not exist. Please add your JSON syllabus files.")
        return

    prepared_documents = load_and_prepare_course_data(COURSE_DATA_PATH)
    if not prepared_documents:
        logger.error("No course documents loaded. Exiting.")
        return

    vector_store = ChromaVectorStore(
        genai_client=client,
        collection_name="cse_course_syllabi_v1", # Give a versioned name
        persist_directory=CHROMA_PERSIST_DIRECTORY
    )
    vector_store.build_store(prepared_documents) # This will add docs if not present

    if vector_store.collection.count() == 0:
        logger.error("Chroma vector store is empty after build. Exiting.")
        return

    # Use the new client-based approach
    chat_history = []  # Simple list to track conversation

    # Show metadata summary to user
    metadata_summary = vector_store.get_metadata_summary()
    
    logger.info("Chatbot initialized. Type 'quit' to exit.")
    print("\n🎓 Welcome to Your Computer Science & Engineering Student Counselor!")
    print("=" * 80)
    print("🏛️  Gothenburg University - Department of Computer Science and Engineering")
    print(f"📚 Course Database: {metadata_summary.get('total_sections', 0)} sections from current course offerings")
    
    if metadata_summary:
        print(f"\n📊 Programs & Courses Available:")
        print(f"   🎯 Academic Programs: {len(metadata_summary.get('programs', []))} different degree programs")
        print(f"   📈 Credit Levels: {', '.join(metadata_summary.get('credits', []))} credits")
        print(f"   🎓 Study Cycles: {', '.join(metadata_summary.get('cycles', []))}")
        print(f"   🌍 Languages: {', '.join(metadata_summary.get('languages', []))}")
    
    print(f"\n💬 Ask Me About:")
    print(f"   📚 'What courses are in the Computer Science master's program?'")
    print(f"   🎯 'What are the prerequisites for DIT620?'")
    print(f"   📝 'Show me all data science related courses'")
    print(f"   🏗️ 'Which software engineering courses should I take first?'")
    print(f"   ⚖️ 'What's the difference between CS and Software Engineering programs?'")
    print(f"   🎮 'Tell me about the Game Design and Technology program'")
    print(f"   📊 'What bachelor level programming courses are available?'")
    
    print(f"\n⚠️  Important: The Applied Data Science Master's Programme (N2ADS) is no longer accepting applications.")
    print(f"\n   💡 Type 'help' for more guidance or 'quit' to exit.")
    print("=" * 80)

    while True:
        try:
            user_query = input("\nYou: ").strip()
            if user_query.lower() == 'quit':
                print("Goodbye!")
                break
            if user_query.lower() == 'help':
                print("\n🎓 Student Counselor - How I Can Help You")
                print("=" * 70)
                print("📚 PROGRAM GUIDANCE:")
                print("   • 'What courses are in the Computer Science master's program?'")
                print("   • 'Tell me about the Software Engineering bachelor's program'")
                print("   • 'Which master's programs are available?'")
                print("   • 'What's the difference between CS and Software Engineering?'")
                print("\n🎯 COURSE INFORMATION:")
                print("   • 'What are the prerequisites for DIT620?'")
                print("   • 'Show me all machine learning courses'")
                print("   • 'Which programming courses should I take first?'")
                print("   • 'What 7.5 credit courses are available?'")
                print("\n📝 ACADEMIC PLANNING:")
                print("   • 'How should I plan my studies for data science?'")
                print("   • 'What courses prepare me for software development?'")
                print("   • 'Which electives complement my core courses?'")
                print("   • 'What bachelor level courses should I start with?'")
                print("\n⚠️  IMPORTANT PROGRAMS STATUS:")
                print("   • Applied Data Science Master's (N2ADS) - No longer accepting applications")
                print("\nCOMMANDS:")
                print("   • 'help' - Show this guidance")
                print("   • 'quit' - End our conversation")
                print("=" * 70)
                continue
            if not user_query:
                continue

            # Smart query routing based on detected patterns
            relevant_docs = []
            query_lower = user_query.lower()
            
            # Pattern detection for metadata-based searches
            if any(phrase in query_lower for phrase in ['program', 'programme', 'master', 'bachelor']):
                # Try to extract program name with flexible matching
                programs = vector_store.get_all_programs()
                detected_program = None
                
                # Try exact keyword matching first
                for program in programs:
                    program_words = program.lower().split()
                    query_words = query_lower.split()
                    
                    # Check if significant program keywords appear in query
                    significant_words = [word for word in program_words if len(word) > 3 and word not in ['programme', 'program', 'masters', 'bachelor']]
                    matches = sum(1 for word in significant_words if word in query_lower)
                    
                    if matches >= min(2, len(significant_words)):  # At least 2 matches or all if fewer
                        detected_program = program
                        break
                
                # Fallback to any word matching
                if not detected_program:
                    for program in programs:
                        if any(word in query_lower for word in program.lower().split() if len(word) > 3):
                            detected_program = program
                            break
                
                if detected_program:
                    logger.info(f"🎯 Detected program query: '{detected_program}'")
                    relevant_docs = vector_store.find_courses_by_program(detected_program, top_k=50)  # Get many more results
                    
                    # For program queries, prioritize course overview sections
                    if relevant_docs and any(word in query_lower for word in ['list', 'show', 'all', 'courses']):
                        # Filter to get one section per course (preferably course overview/content sections)
                        unique_courses = {}
                        for doc in relevant_docs:
                            course_code = doc['metadata'].get('course_code', 'unknown')
                            section_title = doc['metadata'].get('section_title', '').lower()
                            
                            # Prioritize overview sections
                            if course_code not in unique_courses:
                                unique_courses[course_code] = doc
                            elif any(keyword in section_title for keyword in ['course content', 'learning outcomes', 'position']):
                                unique_courses[course_code] = doc
                        
                        relevant_docs = list(unique_courses.values())[:15]  # Limit to 15 courses max
                        logger.info(f"📚 Filtered to {len(relevant_docs)} unique courses for program overview")
                    
                    if not relevant_docs:
                        relevant_docs = vector_store.find_relevant_documents(user_query, top_k=3)
                
            elif any(phrase in query_lower for phrase in ['credit', 'hp', '7.5', '15', '30']):
                # Extract credit value
                import re
                credit_match = re.search(r'(\d+\.?\d*)', query_lower)
                if credit_match:
                    credits = credit_match.group(1)
                    logger.info(f"💳 Detected credits query: {credits}")
                    relevant_docs = vector_store.find_courses_by_credits(credits, top_k=15)
                    if not relevant_docs:
                        relevant_docs = vector_store.find_relevant_documents(user_query, top_k=8)
            
            elif any(phrase in query_lower for phrase in ['bachelor', 'master', 'phd', 'first cycle', 'second cycle', 'third cycle']):
                # Detect academic cycle
                cycle_mapping = {
                    'bachelor': 'First cycle',
                    'master': 'Second cycle', 
                    'phd': 'Third cycle',
                    'first cycle': 'First cycle',
                    'second cycle': 'Second cycle',
                    'third cycle': 'Third cycle'
                }
                
                detected_cycle = None
                for keyword, cycle in cycle_mapping.items():
                    if keyword in query_lower:
                        detected_cycle = cycle
                        break
                
                if detected_cycle:
                    logger.info(f"🎓 Detected cycle query: '{detected_cycle}'")
                    relevant_docs = vector_store.find_courses_by_cycle(detected_cycle, user_query, top_k=15)
                    if not relevant_docs:
                        relevant_docs = vector_store.find_relevant_documents(user_query, top_k=8)
            
            elif any(phrase in query_lower for phrase in ['swedish', 'english', 'language']):
                # Detect language query
                if 'swedish' in query_lower:
                    logger.info(f"🇸🇪 Detected Swedish language query")
                    relevant_docs = vector_store.find_courses_by_language('Swedish', user_query, top_k=15)
                elif 'english' in query_lower:
                    logger.info(f"🇬🇧 Detected English language query")
                    relevant_docs = vector_store.find_courses_by_language('English', user_query, top_k=15)
                
                if not relevant_docs:
                    relevant_docs = vector_store.find_relevant_documents(user_query, top_k=8)
            
            # Check for section-specific queries
            if not relevant_docs and any(section_keyword in query_lower for section_keyword in [
                'entry requirements', 'prerequisites', 'learning outcomes', 'assessment', 'course content', 
                'grading', 'evaluation', 'teaching', 'sub-courses', 'position', 'confirmation']):
                logger.info(f"🎯 Detected section-specific query")
                relevant_docs = vector_store.find_relevant_documents(user_query, top_k=10)  # Get more sections
            
            # Check for course-specific queries (e.g., "DIT620 entry requirements")
            if not relevant_docs:
                import re
                course_code_match = re.search(r'\b([A-Z]{2,3}\d{3,4})\b', user_query.upper())
                if course_code_match:
                    course_code = course_code_match.group(1)
                    logger.info(f"🎯 Detected course-specific query for: {course_code}")
                    # Get more results and prioritize sections from the specified course
                    all_results = vector_store.find_relevant_documents(user_query, top_k=15)
                    
                    # Separate results from the target course vs other courses
                    target_course_docs = []
                    other_docs = []
                    
                    for doc in all_results:
                        if doc['metadata'].get('course_code') == course_code:
                            target_course_docs.append(doc)
                        else:
                            other_docs.append(doc)
                    
                    # Prioritize target course sections, then add others
                    relevant_docs = target_course_docs[:5] + other_docs[:3]
                    logger.info(f"📚 Found {len(target_course_docs)} sections from {course_code}, {len(other_docs)} from other courses")
            
            # Default to semantic search if no special patterns detected or no results
            if not relevant_docs:
                relevant_docs = vector_store.find_relevant_documents(user_query, top_k=8)  # Increased from 3 to 8

            if not relevant_docs:
                context_for_llm = "No relevant course documents found in the knowledge base for this query."
                logger.warning("No relevant documents found by Chroma vector store for the query.")
            else:
                context_parts = []
                context_parts.append("Here is information from relevant course sections:")
                for i, doc in enumerate(relevant_docs):
                    course_code = doc['metadata'].get('course_code', 'N/A')
                    section_title = doc['metadata'].get('section_title', 'Unknown Section')
                    context_parts.append(f"\n--- Document {i+1}: {course_code} - {section_title} ---")
                    content_to_add = doc['content']
                    # Truncate if too long for the LLM context window
                    # A more sophisticated approach would be to summarize or select key sections.
                    if len(content_to_add.split()) > 7000: # Adjust based on actual token limits
                        content_to_add = " ".join(content_to_add.split()[:7000]) + "\n... [Content Truncated]"
                    context_parts.append(content_to_add)
                context_for_llm = "\n".join(context_parts)

            logger.info(f"\n--- Context for LLM (first 500 chars) ---\n{textwrap.shorten(context_for_llm, width=500, placeholder='...')}\n----------------------")

            formatted_history = format_chat_history(chat_history)

            # Construct the full prompt for the LLM, including system instructions, dynamic context, history, and query
            full_prompt = SYSTEM_TEMPLATE.format(
                context=context_for_llm,
                chat_history=formatted_history,
                question=user_query
            )
            
            logger.debug(f"Sending to LLM. Prompt length approx: {len(full_prompt)} chars")
            if len(full_prompt) > 30000: # Gemini 1.5 Flash has large context, but good to monitor
                 logger.warning("Prompt is very long. Consider summarizing context or using fewer retrieved docs.")

            # Using the new client-based approach
            response = client.models.generate_content(
                model=GENERATIVE_MODEL_NAME,
                contents=full_prompt,
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    safety_settings=[
                        types.SafetySetting(
                            category="HARM_CATEGORY_HARASSMENT",
                            threshold="BLOCK_MEDIUM_AND_ABOVE"
                        ),
                        types.SafetySetting(
                            category="HARM_CATEGORY_HATE_SPEECH", 
                            threshold="BLOCK_MEDIUM_AND_ABOVE"
                        ),
                        types.SafetySetting(
                            category="HARM_CATEGORY_SEXUALLY_EXPLICIT",
                            threshold="BLOCK_MEDIUM_AND_ABOVE"
                        ),
                        types.SafetySetting(
                            category="HARM_CATEGORY_DANGEROUS_CONTENT",
                            threshold="BLOCK_MEDIUM_AND_ABOVE"
                        ),
                    ]
                )
            )

            # Update chat history manually
            chat_history.append({"role": "user", "text": user_query})
            
            assistant_response_text = ""
            if response and hasattr(response, 'text'):
                assistant_response_text = response.text
            else:
                assistant_response_text = "I'm sorry, I couldn't generate a response."
                logger.error(f"LLM response issue: {response}")
            
            chat_history.append({"role": "assistant", "text": assistant_response_text})

            print(f"\nAssistant: {assistant_response_text}")

        except Exception as e:
            if "blocked" in str(e).lower():
                logger.error(f"Content generation blocked by API: {e}")
                print(f"\nAssistant: My response was blocked. This might be due to safety settings or other policy. Details: {e}")
                chat_history.append({"role": "user", "text": user_query})
                chat_history.append({"role": "assistant", "text": "[Response blocked by API due to safety/policy reasons]"})
            else:
                logger.error(f"An error occurred: {e}", exc_info=True)
                print("\nAssistant: I'm sorry, an unexpected error occurred. Please try again.")


if __name__ == '__main__':
    logging.getLogger('google.api_core.bidi').setLevel(logging.WARNING) # Quieten verbose gRPC logs
    logging.getLogger('chromadb.telemetry.posthog').setLevel(logging.WARNING) # Quieten Chroma telemetry
    run_chatbot()