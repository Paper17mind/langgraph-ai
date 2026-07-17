import os
import uuid

# Suppress HuggingFace logging spam before importing HuggingFaceEmbeddings
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEMORY_STORE_PATH = os.path.join(BASE_DIR, "data", "memory_store")

class MemoryDB:
    def __init__(self):
        self._embeddings = None
        self._vector_store = None
        
    def _init_db(self):
        """Lazily initialize the embedding model and vector store only when needed."""
        if self._vector_store is None:
            # Set to offline mode since we already have the model cached locally
            os.environ["HF_HUB_OFFLINE"] = "1"
            self._embeddings = HuggingFaceEmbeddings(
                model_name="all-MiniLM-L6-v2",
                model_kwargs={"local_files_only": True}
            )
            self._vector_store = Chroma(
                collection_name="ai_long_term_memory",
                embedding_function=self._embeddings,
                persist_directory=MEMORY_STORE_PATH
            )

    def save_fact(self, fact_text: str) -> str:
        """Saves a single fact into the vector database."""
        try:
            self._init_db()
            doc_id = str(uuid.uuid4())
            self._vector_store.add_texts(texts=[fact_text], ids=[doc_id])
            return f"Berhasil menyimpan memori: '{fact_text}'"
        except Exception as e:
            return f"Gagal menyimpan memori: {e}"
            
    def search_facts(self, query: str, k: int = 3) -> str:
        """Searches for relevant facts in the database."""
        try:
            self._init_db()
            results = self._vector_store.similarity_search(query, k=k)
            if not results:
                return "Tidak ada memori yang relevan ditemukan."
            
            facts = [doc.page_content for doc in results]
            return "Memori terkait yang ditemukan:\n" + "\n".join(f"- {f}" for f in facts)
        except Exception as e:
            return f"Gagal mencari memori: {e}"

    def get_all_facts(self) -> list:
        """Retrieves all facts from the database."""
        try:
            self._init_db()
            results = self._vector_store.get()
            return results.get("documents", [])
        except Exception as e:
            print(f"Error reading memory: {e}")
            return []

# Singleton instance
memory_db = MemoryDB()
