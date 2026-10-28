# AI Telebot — Autonomous Maintainer & Coding Assistant

Asisten AI otonom berbasis **LangGraph** yang beroperasi ganda: sebagai asisten terminal (CLI) dan bot Telegram yang selalu siaga. Selain interaksi percakapan dan eksekusi coding, asisten ini dirancang sebagai **Autonomous Codebase Maintainer** untuk memantau keamanan CVE runtime/dependensi, mendeteksi bug source code, dan melakukan scaffold proyek secara mandiri.

---

## 🌟 Fitur Utama

1. **Autonomous Codebase Maintainer (Baru)**
   - **Monorepo / Multi-App Auto-Discovery:** Daftarkan root direktori project (`register_project`), bot otomatis mengenali sub-folder (seperti `backend/` PHP & `frontend/` Node.js).
   - **Runtime Vulnerability Checks:** Mendeteksi kerentanan pada versi bahasa pemrograman target maupun host (misal: RCE PHP CGI `CVE-2024-4577`, versi EOL).
   - **Batch Dependency CVE Queries:** Query ribuan dependensi ke OSV.dev (Packagist, npm, PyPI, Go) dalam hitungan detik.
   - **Lightweight AST/Regex Symbol Index:** Mengindeks rute, kelas, dan fungsi ke SQLite lokal untuk penelusuran dampak bug instan tanpa RAG vector yang berat.
   - **SAST Bug Pattern Scanner:** Memindai potensi injeksi SQL, eksekusi command shell berbahaya (`system`, `shell_exec`), dan kredensial/token yang bocor di kode sumber.

2. **Core Capabilities — Schema-Driven Codegen (`core/capabilities/codegen/`)**
   - Menghasilkan arsitektur backend lengkap (Express, FastAPI, Laravel) dan Frontend HTML dari schema JSON (Phase 1 deterministik + Phase 2 LLM injection).
   - Dilengkapi validasi schema bebas dependensi dan CLI runner mandiri:
     ```bash
     python -m core.capabilities.codegen --schema project.json --framework express --out ./output --frontend
     ```

3. **Multi-Interface (CLI & Telegram)**
   - Antarmuka interaktif CLI berbasis `rich` dan kendali penuh dari jarak jauh via Telegram (`pyTelegramBotAPI`).

4. **Proactive Webhook Server (FastAPI)**
   - Menerima event webhook eksternal (GitHub, Trello, CVE alerts) dan proaktif mengirim ringkasan analisis ke Telegram.

5. **Dynamic Tool Loader & Memory**
   - Hot-reload tools dari folder `skills/` tanpa perlu restart manual.
   - Long-term memory dengan SQLite & ChromaDB untuk menyimpan riwayat dan preferensi konteks.

---

## 🏗️ Struktur Arsitektur

```text
ai-telebot/
│
├── main.py                     # Entry point (--cli, --telegram, --webhook)
├── requirements.txt            # Daftar pustaka dependensi
├── .env                        # Konfigurasi token & API keys
│
├── core/                       # Otak Utama & Engine
│   ├── agent_graph.py          # StateGraph LangGraph & streaming
│   ├── dynamic_tools.py        # Hot-reload & tool caching
│   ├── maintainer_db.py        # Database SQLite untuk registry project, deps, & symbols
│   ├── maintainer_scanner.py   # Nested monorepo discovery & manifest parser
│   ├── maintainer_inspector.py # AST indexer, OSV.dev batch query, & SAST scanner
│   └── capabilities/
│       └── codegen/            # Engine scaffold aplikasi (Express, FastAPI, Laravel, HTML)
│
├── interfaces/                 # Antarmuka Pengguna
│   ├── cli_bot.py              # Interface terminal interaktif (Rich UI)
│   ├── telegram_bot.py         # Bot Telegram
│   └── webhook_server.py       # FastAPI webhook receiver (Port 8000)
│
├── skills/                     # Tools LangChain yang Tersedia untuk AI
│   ├── maintainer_skill.py     # register_project, list_registered_projects, audit_project
│   ├── codegen_skill.py        # validate_project_schema, scaffold_project_from_schema
│   ├── coder_skill.py          # Read, write, patch file sistem
│   ├── system_skill.py         # Terminal bash execution
│   ├── security_audit_skill.py # SAST & web vulnerability scanner
│   ├── web_search_skill.py     # DuckDuckGo search
│   └── ...
│
└── data/                       # Local database storage (maintainer.db, memory_store)
```

---

## 🛠️ Instalasi & Persiapan

1. **Clone repository dan masuk ke direktori proyek:**
   ```bash
   git clone https://github.com/Paper17mind/langgraph-ai.git
   cd langgraph-ai
   ```

2. **Instal dependensi:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Konfigurasi Environment (`.env`):**
   Buat file `.env` sejajar dengan `main.py`:
   ```env
   TELEGRAM_BOT_TOKEN="token_dari_botfather"
   ALLOWED_USER_ID="id_telegram_anda"
   NINEROUTER_API_KEY="api_key_ninerouter"
   NINEROUTER_MODEL="antigravity"
   GROQ_API_KEY="api_key_groq_fallback"
   ```

---

## 🚀 Panduan Penggunaan

### 1. Menjalankan Asisten

* **Mode Telegram Bot:**
  ```bash
  python main.py --telegram
  ```
* **Mode Terminal Interaktif (CLI):**
  ```bash
  python main.py --cli
  ```
* **Mode Webhook Receiver:**
  ```bash
  python main.py --webhook
  ```

---

### 2. Menggunakan Fitur Codebase Maintainer

Anda dapat berinteraksi langsung melalui chat Telegram atau CLI:

* **Mendaftarkan Project (Termasuk Monorepo / Multi-Target):**
  > *"Tolong daftarkan project di `/var/www/projects/my-app` dengan nama `my-app`"*
  
  Bot akan memindai folder secara rekursif, mendeteksi manifest (`composer.json`, `package.json`, `requirements.txt`), mengindeks simbol kode, dan menyimpan daftar dependensi ke database.

* **Melihat Daftar Project Terdaftar:**
  > *"Tampilkan daftar project yang sedang dipantau"*

* **Menjalankan Security & Bug Audit:**
  > *"Audit project `my-app`"*
  
  Bot akan melakukan pemeriksaan 3 lapis:
  1. **Runtime Target:** Memeriksa kesesuaian versi PHP/Node dengan database CVE runtime.
  2. **Dependencies:** Mengirim batch query ke OSV.dev untuk mendeteksi library yang rentan.
  3. **Code SAST:** Memindai file kode lokal untuk pola bahaya (SQL injection, `system()`, secret keys).

---

### 3. Menggunakan Codegen Capability

Menghasilkan kerangka aplikasi backend dari JSON schema:
```bash
# Validasi schema saja
python -m core.capabilities.codegen --schema ./schema.json --framework express --validate-only

# Generate full project (Express + Frontend HTML)
python -m core.capabilities.codegen --schema ./schema.json --framework express --out ./output_project --frontend
```
Atau minta langsung ke bot Telegram:
> *"Buatkan scaffold project dari file schema `projects/schema.json` memakai framework Express"*
