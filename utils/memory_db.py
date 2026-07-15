import os
import uuid
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

# Define the local path where ChromaDB will store its data
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEMORY_STORE_PATH = os.path.join(BASE_DIR, "memory_store")

class MemoryDB:
    def __init__(self):
        # We use a lightweight, fast local embedding model
        # The first run will download the model (~80MB) automatically.
        self.embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
        
        # Initialize the Chroma vector store
        self.vector_store = Chroma(
            collection_name="ai_long_term_memory",
            embedding_function=self.embeddings,
            persist_directory=MEMORY_STORE_PATH
        )
        
    def save_fact(self, fact_text: str) -> str:
        """Saves a single fact into the vector database."""
        try:
            doc_id = str(uuid.uuid4())
            self.vector_store.add_texts(texts=[fact_text], ids=[doc_id])
            return f"Berhasil menyimpan memori: '{fact_text}'"
        except Exception as e:
            return f"Gagal menyimpan memori: {e}"
            
    def search_facts(self, query: str, k: int = 3) -> str:
        """Searches for relevant facts in the database."""
        try:
            results = self.vector_store.similarity_search(query, k=k)
            if not results:
                return "Tidak ada memori yang relevan ditemukan."
            
            facts = [doc.page_content for doc in results]
            return "Memori terkait yang ditemukan:\n" + "\n".join(f"- {f}" for f in facts)
        except Exception as e:
            return f"Gagal mencari memori: {e}"

# Singleton instance
memory_db = MemoryDB()
