import os
import json
import sqlite3
from typing import Annotated, Sequence, TypedDict, Literal, Optional

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, AIMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field
from langgraph.prebuilt import create_react_agent

# Import existing core functions to reuse them
from core.agent import load_all_tools, init_llm, SYSTEM_PROMPT, global_callbacks

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    next: str

# Define Routing output for Supervisor
class RouteResponse(BaseModel):
    next: Literal["PM", "Coder", "Researcher", "QC", "Generalist", "FINISH"] = Field(
        description="The next subagent to route to. Choose FINISH if the user's overall request is fully completed."
    )
    response: Optional[str] = Field(
        None, 
        description="Isi pesan ini HANYA jika user mengajak ngobrol biasa (chit-chat), bertanya hal umum, atau meminta penjelasan yang tidak butuh coding/project (dan set next='FINISH')."
    )

from langgraph.checkpoint.sqlite import SqliteSaver

# Setup Memory Store
MEMORY_STORE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "memory_store")
os.makedirs(MEMORY_STORE_DIR, exist_ok=True)
CHECKPOINT_DB = os.path.join(MEMORY_STORE_DIR, "checkpoints.sqlite")

def create_multi_agent(active_project: str = None):
    all_tools = load_all_tools()
    llm = init_llm().with_config(callbacks=global_callbacks)
    
    # Categorize tools
    pm_tools = []
    researcher_tools = []
    coder_tools = []
    qc_tools = []
    
    # Find specific shared tools
    sys_cmd_tool = None
    memory_tools = []
    for t in all_tools:
        name = t.name.lower()
        if "execute_system_command" in name:
            sys_cmd_tool = t
        if "memory" in name or "remember" in name or "recall" in name:
            memory_tools.append(t)
            
    for t in all_tools:
        name = t.name.lower()
        if t in memory_tools:
            continue
            
        if any(keyword in name for keyword in ["fsd", "project", "task"]):
            pm_tools.append(t)
        elif any(keyword in name for keyword in ["search", "http", "fetch", "url"]):
            researcher_tools.append(t)
            qc_tools.append(t) # QC also needs to fetch URLs for testing APIs
        elif "qc" in name:
            qc_tools.append(t)
        else:
            coder_tools.append(t)
            
    # Berikan tools memori (buku catatan) ke semua pekerja
    pm_tools.extend(memory_tools)
    coder_tools.extend(memory_tools)
    qc_tools.extend(memory_tools)
    researcher_tools.extend(memory_tools)
            
    # Give QC agent system command access to run tests (e.g. pytest, curl)
    if sys_cmd_tool and sys_cmd_tool not in qc_tools:
        qc_tools.append(sys_cmd_tool)
            
    # Subagent node generator
    def make_node(agent_name, tools, system_prompt_extra=""):
        # We append project context
        prompt = SYSTEM_PROMPT + f"\n\nKAMU ADALAH SUB-AGENT: {agent_name}."
        prompt += f"\n{system_prompt_extra}"
        
        if active_project:
            prompt += f"\n\n[KONTEKS PROYEK AKTIF]\nKamu sedang bekerja pada proyek: {active_project}\n"
            prompt += f"Semua file/kode untuk proyek ini WAJIB diletakkan di dalam folder `projects/{active_project}/`.\n"
        
        # Create a basic react agent for this subagent
        agent = create_react_agent(model=llm, tools=tools, prompt=SystemMessage(content=prompt))
        
        def node_function(state: AgentState):
            # Limit the context given to the subagent to prevent token explosion
            recent_messages = state["messages"][-10:]
            result = agent.invoke({"messages": recent_messages})
            # The result from create_react_agent has a 'messages' key
            # We return only the last message (the AI's output) to be added to the shared state
            out_msg = result["messages"][-1]
            out_msg.name = agent_name.replace(" ", "_") # Attach name so supervisor knows who spoke
            return {"messages": [out_msg]}
            
        return node_function

    # 1. PM Node
    pm_node = make_node(
        "Project Manager", 
        pm_tools,
        "Fokus kamu adalah mengelola FSD, membuat task list rinci, dan berinteraksi dengan memori. Jangan melakukan coding.\n"
        "ATURAN PENTING PM (FSD BERKUALITAS TINGGI):\n"
        "1. FSD WAJIB KOMPREHENSIF: Jangan buat FSD alakadarnya! FSD harus memuat: Latar belakang proyek, fitur lengkap, struktur menu Frontend, sistem Auth & Role pengguna, serta arsitektur teknis.\n"
        "2. DESAIN DATABASE & ALUR (FLOW): Wajib sertakan relasi tabel database (Schema/ERD) yang matang, beserta alur bisnis (business flow) dari fitur-fitur utama yang jelas.\n"
        "3. KUALITAS PRODUKSI: FSD yang kamu buat adalah panduan mutlak bagi Coder. Pastikan strukturnya rumit, aman, dan siap pakai untuk skala produksi sesungguhnya.\n"
        "4. KONSISTENSI FOLDER PROYEK: Jangan sembarangan membuat folder baru! Cek folder yang sudah ada sebelumnya. Jika proyek bernama 'bengkel' sudah ada, gunakan folder itu. JANGAN membuat duplikat seperti 'bengkel_app'."
    )
    
    # 2. Coder Node
    coder_node = make_node(
        "Coder Engineer", 
        coder_tools,
        "Fokus kamu adalah membaca panduan lokal, menulis kode, mengeksekusi command terminal, dan menyelesaikan masalah teknis.\n"
        "ATURAN PENTING CODING:\n"
        "1. KUALITAS PRODUKSI (PRODUCTION-READY): Jangan menulis kode contoh (boilerplate/MVP) yang terlalu sederhana. Tulislah logika backend yang tangguh, aman, dengan error handling dan struktur data yang kompleks jika diperlukan.\n"
        "2. DESAIN FRONTEND MODERN: Jika membuat UI, pastikan tampilannya estetis, elegan, responsif, dan modern (misal menggunakan CSS Variables, animasi halus, layout rapi). JANGAN membuat desain alakadarnya bergaya tahun 2000-an!\n"
        "3. MODULARITAS: JANGAN MENUMPUK KODE! Pisahkan kode berdasarkan fitur atau fungsi (misal: pisahkan routes, controller, model, dan view ke direktori terpisah).\n"
        "4. UNIT TESTING: Wajib menyertakan file unit test terpisah untuk setiap fitur/komponen utama yang dibangun (misalnya dengan Jest/PHPUnit/Pytest) agar sistem mudah diverifikasi oleh QC.\n"
        "5. KONSISTENSI FOLDER PROYEK: SEBELUM membuat direktori baru, cek selalu folder proyek yang sudah eksis (jangan membuat folder baru seperti 'bengkel_app' jika 'bengkel' sudah ada). Lanjutkan pekerjaan di folder aslinya.\n"
        "6. UPDATE TASK PROGRESS: Setiap kali kamu selesai menyelesaikan suatu fitur atau kode, kamu WAJIB membaca dan mengubah status di file task list (seperti tasks.json atau tasks.md) menjadi 'done' atau 'completed' agar progress ter-update."
    )
    
    # 3. QC Node
    qc_node = make_node(
        "Quality Control (QC)", 
        qc_tools,
        "Fokus kamu adalah MENGUJI KODE yang baru saja selesai ditulis oleh Coder. Jalankan script testing (misal pytest), gunakan curl untuk mengecek API, atau panggil QC tools. Jika ada error atau hasil tidak sesuai, laporkan secara detail agar bisa diperbaiki oleh Coder."
    )
    
    # 4. Researcher Node
    researcher_node = make_node(
        "Researcher", 
        researcher_tools,
        "Fokus kamu adalah mencari informasi dari internet, membaca URL, dan melakukan scraping data jika diperlukan."
    )
    
    # 5. Generalist Node
    generalist_node = make_node(
        "Generalist", 
        all_tools,
        "Fokus kamu adalah membantu user melakukan tugas-tugas umum, eksperimen, membuat tool baru, atau menjalankan script acak di luar konteks proyek perangkat lunak besar. Kamu bebas menggunakan seluruh tools yang tersedia."
    )
    
    # 6. Supervisor Node
    # The supervisor decides who goes next. It does NOT have tools, it just outputs JSON to route.
    supervisor_llm = llm.with_structured_output(RouteResponse)
    
    def supervisor_node(state: AgentState):
        supervisor_prompt = """Kamu adalah SUPERVISOR AGENT. 
Tugasmu adalah melihat histori percakapan dan memutuskan siapa yang harus bekerja selanjutnya.
Kamu membawahi 5 pekerja:
1. PM: Mengurus FSD, task list lokal, dan manajemen manajemen proyek.
2. Coder: Menulis kode aplikasi modular, menjalankan command terminal, dan membaca guidelines lokal.
3. QC: Menguji kode yang telah dibuat Coder, menjalankan test, mengecek error API.
4. Researcher: Mencari referensi dari internet atau membaca dokumentasi online.
5. Generalist: Menangani tugas-tugas umum, eksperimen, tanya jawab, atau pembuatan tool baru yang tidak terkait langsung dengan pembuatan proyek besar.

Catatan: SEMUA pekerja di atas memiliki akses ke Buku Catatan (Memory) untuk mencatat histori bug/solusi!
- Jika user meminta tugas umum, bereksperimen, atau membuat tool baru, rute-kan ke 'Generalist'.

ATURAN PENTING (HUMAN IN THE LOOP):
- WAJIB MINTA PERSETUJUAN: Jangan mengeksekusi seluruh task secara otomatis sekaligus. 
- FSD / Plan Review: Setelah PM selesai merancang FSD/Trello, SEGERA pilih 'FINISH' untuk meminta user mereview dan menyetujui plan tersebut sebelum Coder mulai menulis kode.
- Coder Step-by-Step: Setelah Coder menyelesaikan SATU bagian/fitur, SEGERA pilih 'FINISH' untuk meminta persetujuan dan feedback user sebelum lanjut ke fitur berikutnya atau QC.
- QC Review: Setelah QC melaporkan hasil test, pilih 'FINISH' agar user tahu hasilnya dan memutuskan langkah selanjutnya.
- Intinya, pilih 'FINISH' jika agen sudah menyelesaikan sub-task, butuh konfirmasi, persetujuan, atau input dari user. Jangan biarkan agen bekerja berantai terlalu panjang (maksimal 2-3 step) tanpa bertanya ke user.
- Jika agen terus-terusan error atau looping, SEGERA pilih 'FINISH' untuk melapor ke user.

ATURAN OUTPUT JSON (SANGAT PENTING):
- Kamu WAJIB merespons HANYA dengan format JSON yang valid.
- JANGAN menambahkan awalan atau akhiran markdown seperti ```json atau teks tambahan apapun.
- Contoh balasan 1: {"next": "Generalist", "response": "Halo! Ada yang bisa dibantu?"}
- Contoh balasan 2: {"next": "PM", "response": null}

Percakapan sejauh ini (perhatikan nama pengirim pesan):
"""
        # Guard against empty loops: if the last worker returned absolutely nothing, force FINISH
        last_msg = state["messages"][-1]
        if not getattr(last_msg, "content", "").strip() and not getattr(last_msg, "tool_calls", None):
            return {"next": "FINISH"}
            
        # STRICT HUMAN-IN-THE-LOOP (Optimization): 
        # Jika pesan terakhir berasal dari pekerja, LEWATI pemanggilan LLM Supervisor dan langsung potong ke User.
        # Ini mencegah agen berantai (recursive) dan menghemat banyak token.
        worker_names = ["Project Manager", "Coder Engineer", "Quality Control", "Researcher", "Generalist"]
        if getattr(last_msg, "name", "") in worker_names:
            return {"next": "FINISH"}
            
        messages_text = "\n".join([f"{m.name or m.type}: {m.content}" for m in state["messages"][-10:]]) # limit context to last 10
        try:
            result = supervisor_llm.invoke([
                SystemMessage(content=supervisor_prompt),
                HumanMessage(content=messages_text)
            ])
        except Exception as e:
            # Jika LLM gagal memformat JSON (Pydantic validation error), kembalikan fallback
            return {
                "next": "FINISH", 
                "messages": [AIMessage(content=f"Oops, sistem routing agak bingung memproses permintaan ini. Bisa diperjelas lagi?", name="Supervisor")]
            }
            
        # Asumsi model mengembalikan object RouteResponse
        if not result or not hasattr(result, 'next'):
            return {"next": "FINISH"}
            
        return_payload = {"next": result.next}
        if getattr(result, "response", None) and result.next == "FINISH":
            return_payload["messages"] = [AIMessage(content=result.response, name="Supervisor")]
            
        return return_payload

    # Build Graph
    workflow = StateGraph(AgentState)
    
    workflow.add_node("Supervisor", supervisor_node)
    workflow.add_node("PM", pm_node)
    workflow.add_node("Coder", coder_node)
    workflow.add_node("QC", qc_node)
    workflow.add_node("Researcher", researcher_node)
    workflow.add_node("Generalist", generalist_node)
    
    # Add Edges
    # Worker selalu lapor balik ke supervisor setelah selesai
    workflow.add_edge("PM", "Supervisor")
    workflow.add_edge("Coder", "Supervisor")
    workflow.add_edge("QC", "Supervisor")
    workflow.add_edge("Researcher", "Supervisor")
    workflow.add_edge("Generalist", "Supervisor")
    
    # Supervisor bisa ke 4 worker, atau selesai
    workflow.add_conditional_edges(
        "Supervisor",
        lambda state: state["next"],
        {
            "PM": "PM",
            "Coder": "Coder",
            "QC": "QC",
            "Researcher": "Researcher",
            "Generalist": "Generalist",
            "FINISH": END
        }
    )
    
    workflow.set_entry_point("Supervisor")
    
    conn = sqlite3.connect(CHECKPOINT_DB, check_same_thread=False)
    memory_saver = SqliteSaver(conn)
    return workflow.compile(checkpointer=memory_saver)

def get_agent_executor(active_project: str = None):
    # This wrapper returns the compiled StateGraph
    # We maintain the same function name so drop-in replacement is easy.
    return create_multi_agent(active_project=active_project)
