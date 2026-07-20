import os
from langchain.tools import tool

BASE_PROJECTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "projects")

@tool
def init_project(project_name: str, description: str) -> str:
    """Initialize new project scaffolding in /projects/."""
    try:
        if not os.path.exists(BASE_PROJECTS_DIR):
            os.makedirs(BASE_PROJECTS_DIR)
            
        proj_dir = os.path.join(BASE_PROJECTS_DIR, project_name)
        if os.path.exists(proj_dir):
            return f"Proyek '{project_name}' sudah ada. Silakan edit file yang sudah ada."
            
        # Bikin struktur standar
        os.makedirs(os.path.join(proj_dir, "backend"))
        os.makedirs(os.path.join(proj_dir, "frontend"))
        os.makedirs(os.path.join(proj_dir, "docs"))
        
        # Bikin README
        readme_path = os.path.join(proj_dir, "README.md")
        with open(readme_path, "w") as f:
            f.write(f"# {project_name}\n\n{description}\n\n## Struktur\n- backend/: API Service\n- frontend/: UI App\n- docs/: Dokumen FSD dan Desain")
            
        return f"Berhasil inisialisasi proyek '{project_name}'.\nLokasi: {proj_dir}\nSelanjutnya, buat file FSD (Functional Specification Document) di dalam folder docs/."
    except Exception as e:
        return f"Gagal membuat proyek: {e}"

@tool
def save_fsd_document(project_name: str, fsd_content: str) -> str:
    """Save FSD document to docs/ folder."""
    try:
        docs_dir = os.path.join(BASE_PROJECTS_DIR, project_name, "docs")
        if not os.path.exists(docs_dir):
            return f"Error: Folder proyek '{project_name}' tidak ditemukan. Gunakan init_project terlebih dahulu."
            
        fsd_path = os.path.join(docs_dir, "FSD.md")
        with open(fsd_path, "w") as f:
            f.write(fsd_content)
            
        return f"Berhasil menyimpan FSD.md di proyek {project_name}. Kamu bisa gunakan konten FSD ini untuk meng-update Trello Board menggunakan tool trello_skill yang kamu buat sebelumnya."
    except Exception as e:
        return f"Gagal menyimpan FSD: {e}"
