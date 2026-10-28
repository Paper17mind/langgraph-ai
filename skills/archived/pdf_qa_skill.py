import os
import pickle
import numpy as np
import pypdf
from sentence_transformers import SentenceTransformer
import faiss
from langchain_core.tools import tool

_EMBED_MODEL = None
_STORE_DIR = "vector_stores"
_PDF_LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "logs", "pdf_qa")

def _get_model():
    global _EMBED_MODEL
    if _EMBED_MODEL is None:
        _EMBED_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
    return _EMBED_MODEL

def _get_store_paths(collection_name: str):
    os.makedirs(_STORE_DIR, exist_ok=True)
    idx_path = os.path.join(_STORE_DIR, f"{collection_name}.index")
    data_path = os.path.join(_STORE_DIR, f"{collection_name}.pkl")
    return idx_path, data_path

@tool
def process_pdf(file_path: str, collection_name: str) -> str:
    """Process PDF file, chunk text, generate embeddings, store in FAISS, and save text log to logs/pdf_qa/."""
    if not os.path.exists(file_path):
        return f"Error: File not found at {file_path}"
    
    reader = pypdf.PdfReader(file_path)
    chunks = []
    chunk_size = 500
    chunk_overlap = 50
    
    pages_formatted = []
    pages_text = []
    for idx, page in enumerate(reader.pages, start=1):
        text = page.extract_text()
        if text:
            pages_text.append(text)
            pages_formatted.append(f"--- [Halaman {idx}] ---\n{text}")
            
    full_text = "\n".join(pages_text)
            
    start = 0
    while start < len(full_text):
        end = start + chunk_size
        chunks.append(full_text[start:end])
        start += chunk_size - chunk_overlap
        
    if not chunks:
        return "Error: No text extracted from PDF."

    # Save plaintext log to logs/pdf_qa/<collection_name>.txt
    os.makedirs(_PDF_LOGS_DIR, exist_ok=True)
    safe_name = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in collection_name)
    log_file_path = os.path.join(_PDF_LOGS_DIR, f"{safe_name}.txt")
    rel_log_path = f"logs/pdf_qa/{safe_name}.txt"
    
    try:
        with open(log_file_path, "w", encoding="utf-8") as f:
            f.write("\n\n".join(pages_formatted))
    except Exception as e:
        print(f"[pdf_qa] Warning saving log file: {e}")
        
    model = _get_model()
    embeddings = model.encode(chunks, convert_to_numpy=True)
    
    dimension = embeddings.shape[1]
    index = faiss.IndexFlatL2(dimension)
    index.add(np.array(embeddings, dtype=np.float32))
    
    idx_path, data_path = _get_store_paths(collection_name)
    faiss.write_index(index, idx_path)
    with open(data_path, "wb") as f:
        pickle.dump(chunks, f)
        
    return (
        f"Successfully processed {file_path}. Created collection '{collection_name}' with {len(chunks)} chunks.\n"
        f"📄 Plaintext log tersimpan di: {rel_log_path} (Anda dapat mencari keyword di file ini menggunakan search_in_file atau read_specific_line)."
    )

@tool
def query_pdf(collection_name: str, question: str) -> str:
    """Query stored PDF collection using vector similarity search."""
    idx_path, data_path = _get_store_paths(collection_name)
    if not os.path.exists(idx_path) or not os.path.exists(data_path):
        return f"Error: Collection '{collection_name}' not found."
        
    index = faiss.read_index(idx_path)
    with open(data_path, "rb") as f:
        chunks = pickle.load(f)
        
    model = _get_model()
    q_embed = model.encode([question], convert_to_numpy=True)
    
    k = min(3, len(chunks))
    distances, indices = index.search(np.array(q_embed, dtype=np.float32), k)
    
    results = [chunks[i] for i in indices[0] if i < len(chunks)]
    sep = chr(10) + "---" + chr(10)
    return sep.join(results) if results else "No relevant content found."
