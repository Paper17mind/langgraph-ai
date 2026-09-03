import os
import subprocess
from langchain.tools import tool

@tool
def write_code_to_file(filename: str, content: str) -> str:
    """
    Creates or overwrites a file with the provided code or text content.
    Returns a success message or an error if it fails (e.g. syntax errors).

    ATURAN LOKASI FILE (STRICT):
    - Temporary / scratch scripts: WAJIB disimpan di folder `scratch/` (misal: `scratch/generate_car.py`).
    - Asset gambar / media: WAJIB disimpan di folder `data/images/` (misal: `data/images/mobil.png`).
    - Skill / Tools baru: WAJIB disimpan di `skills/generated/<nama>_skill.py` (WAJIB berakhiran `_skill.py` dan fungsi utama WAJIB menggunakan decorator `@tool` dari `langchain_core.tools`).
    - Kode Proyek Aplikasi: WAJIB disimpan di `projects/<project_name>/`.
    DILARANG MENULIS FILE TEMPORARY/SCRATCH DI ROOT FOLDER PROYEK!
    """
    try:
        abs_path = os.path.abspath(filename)
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        # Block writing temporary standalone python scripts directly in root
        rel_path = os.path.relpath(abs_path, root_dir)
        if not rel_path.startswith("..") and "/" not in rel_path and "\\" not in rel_path:
            if filename.endswith(".py") and filename not in ["main.py", "server.py"]:
                filename = os.path.join("scratch", filename)
                abs_path = os.path.abspath(filename)

        dir_name = os.path.dirname(abs_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        
        # Block OVERWRITING an existing schema.json to prevent agent from corrupting project schemas
        if os.path.basename(abs_path) == "schema.json" and os.path.exists(abs_path):
            return (
                "❌ DILARANG: Tidak boleh menimpa schema.json yang sudah ada menggunakan tool ini. "
                "Schema adalah file konfigurasi project yang sensitif dan tidak boleh ditimpa sembarangan. "
                "Gunakan read_project_schema untuk membaca schema yang sudah ada, "
                "lalu gunakan generate_project_from_schema untuk generate kode dari schema tersebut."
            )

        # Perbaikan untuk model kecil (seperti Qwen/Llama) yang terkadang
        # mencetak literal "\n" (dua karakter) alih-alih karakter baris baru (newline).
        content = content.replace("\\n", "\n")

        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(content)
            
        # Optional: Try to run python -m py_compile to check syntax if it's a python file
        if filename.endswith(".py"):
            try:
                subprocess.run(f"python -m py_compile {filename}", shell=True, check=True, capture_output=True, text=True)
            except subprocess.CalledProcessError as e:
                return f"File saved, but there is a Syntax Error:\n{e.stderr.strip()}"

        return f"Successfully wrote {len(content.splitlines())} lines to {filename}."
    except Exception as e:
        return f"Failed to write file: {e}"
