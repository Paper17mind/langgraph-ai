import streamlit as st
import os
import sys

# Tambahkan root path proyek agar bisa melakukan import dari utils
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from utils.memory_db import memory_db

st.set_page_config(page_title="ChromaDB Memory GUI", page_icon="🧠", layout="centered")

st.title("🧠 AI Memory Management (ChromaDB)")
st.markdown("Dashboard interaktif untuk mengelola memori jangka panjang (*Long-Term Memory*) dari agen AI.")

# Gunakan Tabs untuk memisahkan fitur
tab1, tab2, tab3, tab4 = st.tabs(["📂 View All", "🔍 Search", "➕ Add Data", "🗑️ Delete Data"])

with tab1:
    st.header("Semua Data Memori")
    if st.button("Refresh Data"):
        pass # Streamlit otomatis rerun
        
    facts = memory_db.get_all_facts()
    if facts:
        st.success(f"Total memori tersimpan: {len(facts)}")
        for i, fact in enumerate(facts):
            st.info(f"**{i+1}.** {fact}")
    else:
        st.warning("Database memori saat ini kosong.")

with tab2:
    st.header("Pencarian Semantik")
    st.markdown("Ketik sesuatu dan AI akan mencari memori yang memiliki kedekatan makna (bukan hanya kecocokan kata).")
    search_query = st.text_input("Kueri pencarian:")
    
    if st.button("Cari", type="primary"):
        if search_query.strip():
            with st.spinner("Mencari..."):
                result = memory_db.search_facts(search_query)
                st.write(result)
        else:
            st.warning("Kueri tidak boleh kosong.")

with tab3:
    st.header("Tambah Memori Manual")
    new_fact = st.text_area("Ketik fakta baru yang ingin diingat AI:", height=100)
    
    if st.button("Simpan ke Database", type="primary"):
        if new_fact.strip():
            with st.spinner("Menyimpan..."):
                result = memory_db.save_fact(new_fact)
            if "Berhasil" in result:
                st.success(result)
            else:
                st.error(result)
        else:
            st.warning("Fakta tidak boleh kosong.")

with tab4:
    st.header("Hapus Memori")
    st.markdown("⚠️ Peringatan: Anda akan menghapus dokumen memori jika dokumen tersebut **mengandung** penggalan teks yang Anda ketik di bawah ini.")
    fact_to_delete = st.text_input("Teks yang ingin dihapus:")
    
    if st.button("Hapus Data", type="primary"):
        if fact_to_delete.strip():
            with st.spinner("Menghapus..."):
                result = memory_db.forget_fact(fact_to_delete)
            if "Berhasil" in result:
                st.success(result)
            else:
                st.error(result)
        else:
            st.warning("Input teks penghapusan tidak boleh kosong.")
