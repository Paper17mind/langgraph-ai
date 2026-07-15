import os
import sys
from langchain.tools import tool

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.memory_db import memory_db

@tool
def remember_fact(fact: str) -> str:
    """
    Simpan informasi penting ke dalam memori jangka panjang (Buku Catatan).
    Gunakan tool ini untuk menyimpan nama user, preferensi, informasi arsitektur proyek, 
    bug/kesalahan yang pernah terjadi, dan solusi dari masalah tersebut agar tidak diulangi.
    """
    return memory_db.save_fact(fact)

@tool
def recall_facts(query: str) -> str:
    """
    Cari memori masa lalu berdasarkan kata kunci atau pertanyaan semantik.
    Gunakan tool ini jika kamu membutuhkan konteks lama yang tidak ada di percakapan saat ini.
    """
    return memory_db.search_facts(query)
