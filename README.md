# AI Telebot & Desktop Assistant

Proyek ini adalah asisten AI otonom berbasis **LangGraph** yang dirancang untuk beroperasi ganda: sebagai asisten *desktop* interaktif (CLI) dan bot Telegram yang selalu siap siaga. Asisten ini tidak hanya bisa mengobrol, tetapi memiliki kemampuan *agentic* yang *advanced* seperti mengingat memori jangka panjang, menerima *webhook* secara proaktif, hingga menulis kemampuannya (tools/skills) sendiri.

---

## 🌟 Fitur Utama

1. **Multi-Interface (CLI & Telegram)**
   - Jalankan AI di terminal (dengan antarmuka *rich* berwarna dan informasi status *real-time*), atau akses dari jarak jauh melalui Telegram.
2. **Long-Term Memory (RAG Vector DB)**
   - Menggunakan *ChromaDB* dan *Sentence Transformers* (100% lokal, tanpa API luar). AI dapat "mengingat" arsitektur proyek, preferensi pengguna, dan bug masa lalu, lalu memanggilnya secara dinamis hanya saat dibutuhkan untuk menghemat token.
3. **Proactive Webhook Server (FastAPI)**
   - Dilengkapi dengan *web server* pendamping. AI bisa di- *trigger* oleh aplikasi eksternal (seperti GitHub, Trello, dsb) untuk secara proaktif mengirimkan laporan analisis ke Telegram Anda tanpa Anda memintanya terlebih dahulu.
4. **Dynamic Tool Loader (Self-Extending AI)**
   - Anda dapat menyuruh AI untuk menciptakan *skill* (kode Python) baru. Kode tersebut akan disimpan, dan pada *restart* berikutnya, AI akan secara otomatis mengenali dan dapat menggunakan kemampuannya yang baru dibuat berkat mekanisme pemindaian otomatis di folder `/skills/`.
5. **Robust Tooling**
   - Mendukung manipulasi file sistem (`coder_skill`), eksekusi perintah terminal (`system_skill`), pencarian web (`web_search_skill`), pengambilan konten internet (`http_skill`), manajemen Trello (`trello_skill`), dan penjadwalan.

---

## 🏗️ Arsitektur Proyek

```text
ai-telebot/
│
├── main.py                     # Entry point utama (Argumen: --cli, --telegram, --webhook)
├── agent.py                    # Otak utama LangGraph (LLM initialization, Dynamic Tool Loader)
├── requirements.txt            # Daftar dependensi library
├── .env                        # Konfigurasi rahasia (API Keys, Token)
│
├── interfaces/                 # Modul antar-muka pengguna
│   ├── cli_bot.py              # Interface terminal interaktif (menggunakan rich)
│   ├── telegram_bot.py         # Interface bot Telegram (menggunakan telebot)
│   └── webhook_server.py       # Pintu masuk HTTP (FastAPI) untuk proaktif AI
│
├── skills/                     # Folder kemampuan AI (Tools)
│   ├── coder_skill.py          # Kemampuan menulis dan memodifikasi file
│   ├── system_skill.py         # Kemampuan menjalankan bash command (ls, curl, dll)
│   ├── memory_skill.py         # Tool untuk mengingat dan memanggil fakta (ChromaDB)
│   ├── web_search_skill.py     # Pencarian DuckDuckGo
│   ├── trello_skill.py         # Integrasi API Trello
│   └── http_skill.py           # Fetch content dari URL
│
├── utils/                      # Helper & konfigurasi pendukung
│   ├── history_manager.py      # SQLite manager untuk 10 riwayat percakapan terakhir
│   ├── memory_db.py            # ChromaDB engine untuk memori jangka panjang
│   └── text_helper.py          # Penahan error LLM 413 (Truncate output panjang ke file)
│
├── memory_store/               # Database Vektor (ChromaDB) otomatis terbuat di sini
└── logs/                       # Folder untuk menyimpan riwayat jsonl & output terminal panjang
```

---

## 🛠️ Instalasi

1. **Clone repository ini** (jika ada) dan arahkan ke folder proyek.
2. **Instal versi PyTorch CPU** (Sangat direkomendasikan agar tidak mendownload driver NVIDIA/GPU berukuran raksasa jika Anda tidak menggunakan GPU):
   ```bash
   pip install torch --index-url https://download.pytorch.org/whl/cpu
   ```
3. **Instal sisa dependensi:**
   ```bash
   pip install -r requirements.txt
   ```
4. **Siapkan Konfigurasi:**
   Buat file `.env` di folder utama (sejajar dengan `main.py`) dan isi dengan *keys* berikut:
   ```env
   TELEGRAM_BOT_TOKEN="token_dari_botfather"
   ALLOWED_USER_ID="id_telegram_anda"
   9ROUTER_API_KEY="api_key_gateway_llm"
   9ROUTER_MODEL="google/gemini-pro"
   GROQ_API_KEY="api_key_groq_fallback"
   TRELLO_KEY="trello_api_key"
   TRELLO_TOKEN="trello_api_token"
   ```

---

## 🚀 Cara Menjalankan

Proyek ini sangat modular. Anda bisa menjalankan satu atau beberapa *service* ini secara bersamaan di terminal yang berbeda.

### 1. Menjalankan CLI Mode (Desktop Assistant)
Mode interaktif yang indah di terminal Anda.
```bash
python main.py --cli
```

### 2. Menjalankan Telegram Bot
Menunggu pesan dari Telegram Anda.
```bash
python main.py --telegram
```

### 3. Menjalankan Webhook Server (Proactive Mode)
Menyalakan *server* lokal di port `8000` untuk menangkap webhook dari luar dan mem- *forward* hasil rangkuman AI ke Telegram.
```bash
python main.py --webhook
```
*(Contoh test webhook via curl:)*
```bash
curl -X POST http://localhost:8000/webhook/github -H "Content-Type: application/json" -d '{"event": "push", "message": "Memperbaiki bug"}'
```
