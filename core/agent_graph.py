import os
import json
import re
import time
import operator
from typing import TypedDict, List, Annotated, Any

from dotenv import load_dotenv
load_dotenv()

from langchain_openai import ChatOpenAI
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage, BaseMessage, AIMessage
from langchain_core.callbacks import BaseCallbackHandler
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import create_react_agent
from rich.console import Console
from rich.panel import Panel
from rich.live import Live
from rich.markdown import Markdown
from rich.spinner import Spinner
from rich.text import Text

from core.logger import log_internal_step, log_token_usage
from core.dynamic_prompt import build_dynamic_prompt
from core.dynamic_tools import load_all_tools, select_relevant_tools

console = Console()

# ── Environment Helpers ───────────────────────────────────────────────────────

def _get_env_first(*names, default=""):
    for name in names:
        val = os.getenv(name)
        if val:
            return val
    return default

def retrieve_memories(query: str, k: int = 3) -> str:
    if not query:
        return ""
    try:
        from utils.memory_db import memory_db
        return memory_db.search_facts(query, k=k) or ""
    except Exception as e:
        print(f"[memory] retrieval failed: {e}")
        return ""

# ── LLM Init ──────────────────────────────────────────────────────────────────

def init_master_llm():
    """
    Master LLM mencoba Groq (openai/gpt-oss-120b) sebagai primary.
    Jika Groq error / token habis / rate limit, otomatis fallback ke 9Router (antigravity).
    """
    ninerouter_key = _get_env_first("NINEROUTER_API_KEY", "9ROUTER_API_KEY", default="")
    ninerouter_url = _get_env_first(
        "NINEROUTER_URL", "9ROUTER_URL", default="http://localhost:20128/v1/chat/completions"
    )
    base_url = ninerouter_url.replace("/chat/completions", "")
    ninerouter_model = _get_env_first("NINEROUTER_MODEL", "9ROUTER_MODEL", default="antigravity")

    fallback_llm = ChatOpenAI(
        api_key=ninerouter_key,
        base_url=base_url,
        model=ninerouter_model,
        temperature=0.4,
        timeout=300,
        max_retries=1,
    )

    groq_key = os.getenv("GROQ_API_KEY", "")
    if not groq_key:
        return fallback_llm

    try:
        primary_llm = ChatGroq(
            api_key=groq_key,
            model_name="openai/gpt-oss-120b",
            temperature=0.4,
            timeout=300,
            max_retries=1,
        )
        return primary_llm.with_fallbacks([fallback_llm])
    except Exception as e:
        print(f"[Master LLM] Primary Groq init error, using fallback 9Router: {e}")
        return fallback_llm

def init_reviewer_llm():
    """Reviewer LLM mencoba 9Router (antigravity), jika error fallback ke Groq"""
    ninerouter_key = _get_env_first("NINEROUTER_API_KEY", "9ROUTER_API_KEY", default="")
    ninerouter_url = _get_env_first(
        "NINEROUTER_URL", "9ROUTER_URL", default="http://localhost:20128/v1/chat/completions"
    )
    base_url = ninerouter_url.replace("/chat/completions", "")
    ninerouter_model = _get_env_first("NINEROUTER_MODEL", "9ROUTER_MODEL", default="antigravity")

    primary_llm = ChatOpenAI(
        api_key=ninerouter_key,
        base_url=base_url,
        model=ninerouter_model,
        temperature=0.1,
        timeout=300,
        max_retries=1,
    )

    groq_key = os.getenv("GROQ_API_KEY", "")
    if groq_key:
        try:
            fallback_llm = ChatGroq(
                api_key=groq_key,
                model_name="openai/gpt-oss-120b",
                temperature=0.1,
                timeout=300,
                max_retries=1,
            )
            return primary_llm.with_fallbacks([fallback_llm])
        except Exception:
            pass
    return primary_llm

def init_tools_llm():
    """Tools LLM menggunakan 9Router (dari .env)"""
    ninerouter_key = _get_env_first("NINEROUTER_API_KEY", "9ROUTER_API_KEY", default="")
    ninerouter_url = _get_env_first(
        "NINEROUTER_URL", "9ROUTER_URL", default="http://localhost:20128/v1/chat/completions"
    )
    base_url = ninerouter_url.replace("/chat/completions", "")
    ninerouter_model = _get_env_first("NINEROUTER_MODEL", "9ROUTER_MODEL", default="antigravity")

    return ChatOpenAI(
        api_key=ninerouter_key,
        base_url=base_url,
        model=ninerouter_model,
        temperature=0.2,
        timeout=300,
        max_retries=1,
    )

# ── Logging callback ──────────────────────────────────────────────────────────

def format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = seconds % 60
        return f"{minutes}m {secs:.1f}s"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        return f"{hours}h {minutes}m {secs:.1f}s"

class TimerSpinner:
    def __init__(self, get_start_time):
        self.get_start_time = get_start_time
        self.spinner = Spinner("dots")
        
    def __rich__(self):
        elapsed = time.time() - self.get_start_time()
        formatted_time = format_duration(elapsed)
        self.spinner.text = Text.from_markup(f"[cyan]Thinking... {formatted_time}[/]")
        return self.spinner

class AgentLoggingCallback(BaseCallbackHandler):
    def __init__(self):
        self.live = None
        self.current_text = ""
        self.last_tool_name = "unknown"
        self.has_started_streaming = False
        self.start_time = time.time()

    def reset_timer(self):
        self.start_time = time.time()

    def on_chat_model_start(self, serialized, messages, **kwargs):
        self.current_text = ""
        self.has_started_streaming = False
        self.live = Live(TimerSpinner(lambda: self.start_time), console=console, refresh_per_second=15, transient=False)
        self.live.start()

    def on_llm_new_token(self, token: str, **kwargs) -> None:
        self.current_text += token
        if self.live:
            if not self.current_text.strip():
                return
            if not self.has_started_streaming:
                self.has_started_streaming = True
            
            elapsed = time.time() - self.start_time
            formatted_time = format_duration(elapsed)
            self.live.update(Panel(Markdown(self.current_text), title="Response", subtitle=f"⏱️ {formatted_time}", subtitle_align="right", border_style="blue"))

    def reset(self):
        if self.live:
            try:
                self.live.stop()
            except Exception:
                pass
            finally:
                self.live = None
        self.current_text = ""

    def on_llm_end(self, response, **kwargs):
        final_text = ""
        if response.generations and len(response.generations) > 0 and len(response.generations[0]) > 0:
            final_text = response.generations[0][0].text
            if not final_text:
                msg = getattr(response.generations[0][0], "message", None)
                if msg:
                    final_text = getattr(msg, "content", "")

        if self.live:
            self.live.stop()
            self.live = None

        if final_text.strip():
            elapsed = time.time() - self.start_time
            formatted_time = format_duration(elapsed)
            console.print(Panel(Markdown(final_text), title="Response", subtitle=f"⏱️ {formatted_time}", subtitle_align="right", border_style="blue"))
        try:
            usage = None
            if response.llm_output and "token_usage" in response.llm_output:
                usage = response.llm_output["token_usage"]
            if not usage and response.generations:
                gen = response.generations[0][0]
                message = getattr(gen, "message", None)
                meta = getattr(message, "usage_metadata", None) if message else None
                if meta:
                    usage = {
                        "prompt_tokens": getattr(meta, "input_tokens", 0),
                        "completion_tokens": getattr(meta, "output_tokens", 0),
                        "total_tokens": getattr(meta, "total_tokens", 0),
                    }
            if usage:
                p, c, t = usage.get("prompt_tokens",0), usage.get("completion_tokens",0), usage.get("total_tokens",0)
                print(f"\n🪙 [Token Usage] Prompt: {p} | Completion: {c} | Total: {t}")
                log_token_usage(usage)
        except Exception as e:
            print(f"[Callback Error] on_llm_end: {e}")

    def on_tool_start(self, serialized, input_str, **kwargs):
        try:
            tool_name = serialized.get("name", "unknown")
            self.last_tool_name = tool_name
            args = json.loads(input_str) if isinstance(input_str, str) else input_str
            log_internal_step("tool_start", {"tool_name": tool_name, "args": args})
            console.print(f"\n[bold yellow]🛠️ [Tool Start]:[/] {tool_name} {args}")
        except Exception:
            pass

    def on_tool_end(self, output, **kwargs):
        try:
            log_internal_step("tool_end", {"output": str(output)[:1000]})
            tool_name = kwargs.get("name", getattr(self, "last_tool_name", "Tool"))
            console.print(Panel(str(output)[:1000], title=f"✅ Result: {tool_name}", border_style="orange3"))
        except Exception as e:
            pass

global_callbacks = [AgentLoggingCallback()]

# ── State ─────────────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]
    active_project: str
    user_query: str
    intent: str
    review_status: str
    retry_count: int

# ── Nodes ─────────────────────────────────────────────────────────────────────

def master_intent_node(state: AgentState):
    """
    Master LLM memeriksa intent user dan memutuskan apakah butuh tools.
    """
    print("\n🧠 [Master Node] Mengevaluasi Intent...")
    llm = init_master_llm().with_config(callbacks=global_callbacks)
    
    # Ambil pesan terakhir dari user
    user_query = state.get("user_query")
    if not user_query and state.get("messages"):
        for msg in reversed(state["messages"]):
            if isinstance(msg, HumanMessage):
                user_query = msg.content
                break
        
    system = build_dynamic_prompt(
        active_project=state.get("active_project"),
        user_query=user_query
    )
    
    memories = retrieve_memories(user_query)
    if memories:
        system += f"\n\n[MEMORI]\n{memories}"
        
    # Format chat history for context
    chat_history = ""
    if state.get("messages") and len(state["messages"]) > 1:
        chat_history = "Riwayat Percakapan Sebelumnya:\n"
        # Ambil maksimal 4 pesan terakhir agar tidak terlalu panjang
        recent_msgs = state["messages"][-5:-1]
        for msg in recent_msgs:
            role = "User" if isinstance(msg, HumanMessage) else "Assistant"
            # Potong pesan jika terlalu panjang (khususnya untuk log riwayat tool)
            content = str(msg.content)
            if len(content) > 1000:
                content = content[:1000] + "... [dipotong]"
            chat_history += f"[{role}]: {content}\n"
            
    all_tools = load_all_tools()
    tools_summary = ", ".join([t.name for t in all_tools])

    prompt = f"""
{system}

{chat_history}

DAFTAR TOOLS TERSEDIA DI SISTEM:
[{tools_summary}]

Tugas Utama Anda: 
Analisis permintaan pengguna terbaru berikut berdasarkan konteks riwayat percakapan, memori, dan daftar tools di atas.

ATURAN PENTING:
1. ATURAN MEMORI (STRICT): jika pengguna memberikan perintah untuk mengingat ("ingat", "catat", "simpan di memori", "jangan lupa") ATAU memberikan aturan/preferensi baru (misal: "kalau suruh buat gambar gunakan tool X"), Anda WAJIB memanggil `remember_fact` menggunakan USE_TOOLS_BATCH:
   USE_TOOLS_BATCH:
   [
     {{"tool": "remember_fact", "args": {{"fact": "<fakta/aturan lengkap dari user>"}}}}
   ]
   DILARANG HARAM HANYA MENJAWAB "Iya siap aku catat" TANPA MEMANGGIL TOOL `remember_fact`!

2. EKSEKUSI TUGAS & SYSTEM DATA: Jika pengguna meminta tindakan, analisis data, eksekusi script/command, atau informasi sistem (seperti cek token, baca file, dsb), Anda WAJIB memilih Opsi 1 (USE_TOOLS_BATCH) atau Opsi 2 (USE_TOOLS). DILARANG MENJAWAB "Saya tidak memiliki akses" jika tindakan tersebut bisa dilakukan dengan tools di atas!
3. Jika intent User larangan atau pengingat, Anda WAJIB panggil tool remember_fact !
4. KETEPATAN PARAMETER TOOL (STRICT): Anda WAJIB memeriksa DAFTAR TOOLS TERSEDIA di atas dan menggunakan nama parameter argument yang PRESISI/PERSIS sesuai definisi tool (misal: untuk `generate_image_tool` gunakan nama argument `filename`, BUKAN `output_path`).

Opsi Respon:
1. BATCH PIPELINE MODE (EKSEKUSI CEPAT TERSTRUKTUR - UTAMAKAN INI):
   Jika permintaan memerlukan 1 atau beberapa langkah tool yang jelas/sekuensial (misal: simpan memori, jalankan command python, baca file, dsb), balas DENGAN FORMAT BATCH TOOL PIPELINE JSON:
   USE_TOOLS_BATCH:
   [
     {{"tool": "nama_tool_1", "args": {{"param1": "val1"}}}},
     {{"tool": "nama_tool_2", "args": {{"param2": "$PREV_RESULT"}}}}
   ]
   (Gunakan placeholder "$PREV_RESULT" di args jika membutuhkan output dari tool sebelumnya).

2. REACT WORKER MODE (UNTUK EKSPLORASI INTERAKTIF):
   Jika urutan langkah belum pasti dan memerlukan analisis/trial-and-error interaktif, balas:
   "USE_TOOLS: <rencana singkat apa yang harus dilakukan>"

3. DIRECT CHAT MODE (HANYA UNTUK PERCAKAPAN BIASA):
   HANYA untuk obrolan santai/sapaan ("halo", "apa kabar") atau pertanyaan umum tanpa perintah mengingat/tindakan sistem.

Permintaan User Terbaru: {user_query}
"""
    response = llm.invoke([HumanMessage(content=prompt)])
    
    return {"intent": response.content}

def router(state: AgentState):
    intent_val = state.get("intent", "").strip()
    if "USE_TOOLS_BATCH:" in intent_val or (intent_val.startswith("[") and '"tool"' in intent_val):
        return "batch_worker"
    elif "USE_TOOLS" in intent_val:
        return "tool_worker"
    return "summarizer"

def batch_worker_node(state: AgentState):
    """
    Mengeksekusi sekelompok tool call dari JSON pipeline secara berurutan
    langsung di Python tanpa perlu memanggil LLM berulang kali.
    """
    print("\n⚡ [Batch Worker Node] Mengeksekusi Tool Pipeline secara Lokal...")
    intent_val = state.get("intent", "").strip()
    json_str = intent_val.replace("USE_TOOLS_BATCH:", "").strip()
    
    if json_str.startswith("```"):
        json_str = re.sub(r"^```[a-zA-Z]*\n?", "", json_str)
        json_str = re.sub(r"\n?```$", "", json_str).strip()

    pipeline = []
    try:
        pipeline = json.loads(json_str)
    except Exception as e:
        print(f"⚠️ [Batch Worker] Gagal parse JSON pipeline: {e}. Mengalihkan ke standard tool worker...")
        state["intent"] = "USE_TOOLS: " + json_str
        return tool_worker_node(state)

    if not isinstance(pipeline, list):
        pipeline = [pipeline]

    tool_map = {t.name: t for t in load_all_tools()}
    tools_called = []
    prev_output = ""

    for i, step in enumerate(pipeline, start=1):
        if not isinstance(step, dict):
            continue
        tool_name = step.get("tool")
        tool_args = step.get("args", {})

        if not tool_name or tool_name not in tool_map:
            tools_called.append(f"- Step {i}: ❌ Tool '{tool_name}' tidak ditemukan.")
            continue

        # Replace $PREV_RESULT placeholder jika ada
        for k, v in list(tool_args.items()):
            if isinstance(v, str) and "$PREV_RESULT" in v:
                tool_args[k] = v.replace("$PREV_RESULT", prev_output)

        tools_called.append(f"- Tool Called: {tool_name}({tool_args})")
        log_internal_step("tool_start", {"tool_name": tool_name, "args": tool_args})
        console.print(f"\n[bold yellow]⚡ [Batch Tool {i}/{len(pipeline)}]:[/] {tool_name} {tool_args}")

        try:
            tool_obj = tool_map[tool_name]
            output = tool_obj.invoke(tool_args)
            prev_output = str(output)
            tools_called.append(f"  Output [{tool_name}]: {prev_output[:1000]}")
            console.print(Panel(prev_output[:1000], title=f"✅ Result: {tool_name}", border_style="orange3"))
            log_internal_step("tool_end", {"output": prev_output[:1000]})
        except Exception as ex:
            err_msg = f"Error executing {tool_name}: {ex}"
            tools_called.append(f"  Output [{tool_name}]: {err_msg}")
            prev_output = err_msg
            console.print(Panel(err_msg, title=f"❌ Error: {tool_name}", border_style="red"))
            # Auto-save error into memory
            try:
                from utils.memory_db import memory_db
                memory_db.save_fact(f"BUG LOG [{tool_name}]: {err_msg[:250]}")
                print(f"📌 [Auto Memory] Recorded bug log for {tool_name}")
            except Exception:
                pass

    audit_trail = "\n".join(tools_called) if tools_called else "TIDAK ADA TOOL YANG DIPANGGIL."
    final_output = f"Batch Tool Pipeline selesai mengeksekusi {len(pipeline)} langkah.\n\nHasil Akhir:\n{prev_output}"
    
    return {"messages": [AIMessage(content=f"[Riwayat Tools & Output]:\n{audit_trail}\n\n[Hasil dari Tool Worker]:\n{final_output}")]}

def tool_worker_node(state: AgentState):
    """
    Menggunakan Tools LLM (9Router) dengan mekanisme ReAct agent
    untuk mengeksekusi instruksi dari Master.
    """
    print("\n🛠️ [Worker Node] Menjalankan Tools...")
    tools_llm = init_tools_llm().with_config(callbacks=global_callbacks)
    
    user_query = state.get("user_query")
    if not user_query and state.get("messages"):
        for msg in reversed(state["messages"]):
            if isinstance(msg, HumanMessage):
                user_query = msg.content
                break
    
    current_tools = load_all_tools()
    # current_tools = select_relevant_tools(load_all_tools(), user_query)
    intent_plan = state.get("intent", "").replace("USE_TOOLS:", "").strip()
    
    react_agent = create_react_agent(
        model=tools_llm,
        tools=current_tools,
        prompt=SystemMessage(content=f"""Anda adalah Agen Pekerja (Tool Executor).
Fokus utama Anda adalah menjalankan tools untuk menyelesaikan masalah.

Pesan Asli User: {user_query}
Rencana / Instruksi dari Master: {intent_plan}

PENTING UNTUK DIPERHATIKAN:
- JANGAN pernah menuliskan blok JSON secara manual di dalam teks respons Anda (seperti `{{ "name": "write_code_to_file", ... }}`).
- Anda WAJIB memanggil tools menggunakan mekanisme 'Function Calling' / 'Tool Calling' bawaan (native tool calls), pastikan argument pemanggilan tools sesuai.
- Jika Anda tidak memanggil tools secara native, tindakan Anda tidak akan tereksekusi!
- ATURAN ERROR: Jika pemanggilan tool menghasilkan error/SyntaxError/gagal, PANGGIL tool `remember_fact` untuk mencatat bug tersebut ke memori serta alasan nya lalu perbaiki kodenya.

Jalankan tools yang sesuai dan berikan kesimpulan akhir tindakan Anda.""")
    )
    
    worker_messages = [HumanMessage(content=user_query)]
    if state.get("review_status") == "REJECTED" and len(state.get("messages", [])) >= 2:
        worker_messages.append(state["messages"][-2]) # AIMessage dari worker sebelumnya
        worker_messages.append(state["messages"][-1]) # HumanMessage feedback dari reviewer

    result = react_agent.invoke({"messages": worker_messages})
    final_output = result["messages"][-1].content
    
    # Kumpulkan riwayat pemanggilan tool & hasilnya untuk diaudit oleh reviewer
    tools_called = []
    for msg in result["messages"][len(worker_messages):]:
        if getattr(msg, "tool_calls", None):
            for tc in msg.tool_calls:
                tools_called.append(f"- Tool Called: {tc['name']}({tc['args']})")
        if getattr(msg, "name", None) or getattr(msg, "content", None):
            if msg.type == "tool":
                tool_output = str(msg.content)[:1000]
                tools_called.append(f"  Output [{getattr(msg, 'name', 'tool')}]: {tool_output}")
                
                # Auto-save error into ChromaDB long-term memory
                if any(err_kw in tool_output.lower() for err_kw in ["syntaxerror", "syntax error", "traceback", "error:", "failed"]):
                    try:
                        from utils.memory_db import memory_db
                        t_name = getattr(msg, "name", "tool")
                        memory_db.save_fact(f"BUG LOG [{t_name}]: {tool_output[:250]}")
                        print(f"📌 [Auto Memory] Recorded tool error for {t_name} into ChromaDB")
                    except Exception as ex:
                        print(f"[Auto Memory Error] {ex}")
                
    audit_trail = "\n".join(tools_called) if tools_called else "TIDAK ADA TOOL YANG DIPANGGIL."
    
    return {"messages": [AIMessage(content=f"[Riwayat Tools & Output]:\n{audit_trail}\n\n[Hasil dari Tool Worker]:\n{final_output}")]}

def reviewer_node(state: AgentState):
    """
    Mengevaluasi hasil dari tool_worker_node sebagai Quality Control (QC) Agent.
    """
    print("\n🔍 [Reviewer Node] Mengevaluasi Pekerjaan Worker (QC Check)...")
    llm = init_reviewer_llm()
    
    retry_count = state.get("retry_count", 0)
    if retry_count >= 3:
        print("⚠️ [Reviewer] Batas maksimum retry tercapai. Lanjut ke summarizer.")
        return {"review_status": "APPROVED", "retry_count": retry_count}
        
    worker_result = str(state["messages"][-1].content).replace('"', "'")
    user_query = state.get("user_query")
    intent_plan = state.get("intent", "")
    
    prompt = f"""
Tugas Anda adalah mengevaluasi hasil kerja (Tool Worker) berdasarkan permintaan pengguna.
Anda adalah Quality Control (QC) Agent yang SANGAT TEGAS, TELITI, dan TANPA KOMPROMI.

Permintaan Pengguna: {user_query}
Instruksi/Rencana: {intent_plan}

Laporan Eksekusi Worker: 
{worker_result}

EVALUASI KRITIS (QUALITY CONTROL):
1. KEGAGALAN SINTAKS / ERROR KODE (CRITICAL):
   - Periksa seluruh [Riwayat Tools & Output] dan [Hasil dari Tool Worker] di atas.
   - Jika terdapat pesan "Syntax Error", "SyntaxError", "unterminated string literal", "Traceback", "Error:", "BLOCKED:", atau kesalahan sintaksis Python, maka pekerjaan Worker GAGAL!
   - Anda WAJIB menolak dengan "STATUS: REJECTED" dan tuliskan pesan error sintaks tersebut secara jelas agar Worker memperbaiki kodenya sampai benar-benar valid tanpa error!

2. TOOL CALLING / BEBAS HALUSINASI:
   - Apakah instruksi mensyaratkan Worker melakukan tindakan (misal: simpan file, baca file, jalankan perintah)?
   - Jika YA dan di [Riwayat Tools & Output] tertulis "TIDAK ADA TOOL YANG DIPANGGIL.", atau Worker hanya mengklaim sudah membuat/menyimpan file tetapi tidak memanggil tool, maka Anda WAJIB REJECT!

Jika KODE BEBAS SYNTAX ERROR & TOOL DIPANGGIL DENGAN BENAR, balas HANYA dengan: "STATUS: APPROVED"
Jika TERDAPAT ERROR SINTAKS ATAU HALUSINASI, balas dengan: "STATUS: REJECTED" dan di baris berikutnya tuliskan instruksi/koreksi spesifik yang mejelaskan perbaikan.
"""
    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        content = response.content.strip()
    except Exception as ex:
        print(f"⚠️ [Reviewer] QC LLM Error: {ex}. Auto-approving...")
        return {"review_status": "APPROVED", "retry_count": retry_count}
    
    if content.startswith("STATUS: APPROVED"):
        print("✅ [Reviewer] Hasil disetujui.")
        return {"review_status": "APPROVED", "retry_count": retry_count}
    else:
        feedback = content.replace("STATUS: REJECTED", "").strip()
        print(f"❌ [Reviewer] Hasil ditolak. Feedback: {feedback}")
        return {
            "review_status": "REJECTED", 
            "retry_count": retry_count + 1,
            "messages": [HumanMessage(content=f"[Koreksi dari Reviewer]:\n{feedback}")]
        }

def reviewer_router(state: AgentState):
    status = state.get("review_status", "")
    if status == "REJECTED":
        return "tool_worker"
    return "summarizer"

def summarizer_node(state: AgentState):
    """
    Master LLM memberikan format hasil akhir yang natural kepada user.
    """
    intent_val = state.get("intent", "")
    
    if "USE_TOOLS" not in intent_val:
        # Jika Master langsung merespons tanpa tools
        return {"messages": [AIMessage(content=intent_val)]}
        
    print("\n📝 [Summarizer Node] Memformulasikan Jawaban Akhir...")
    llm = init_tools_llm().with_config(callbacks=global_callbacks)
    
    user_query = state.get("user_query")
    if not user_query and state.get("messages"):
        for msg in reversed(state["messages"]):
            if isinstance(msg, HumanMessage):
                user_query = msg.content
                break
                
    worker_result = state["messages"][-1].content
    
    prompt = f"""
Anda adalah Asisten AI Utama (Master).
Berikut adalah ringkasan tindakan yang baru saja diselesaikan oleh sub-agen pekerja (Tool Worker) Anda untuk menjawab pertanyaan pengguna.

Pertanyaan Pengguna: "{user_query}"
Laporan Pekerja: 
{worker_result}

Tugas Anda:
Sampaikan hasil ini kepada pengguna dengan bahasa yang natural, ramah, dan ringkas. JANGAN menyebutkan hal-hal teknis mengenai "pekerja" atau "sub-agen", anggap Anda sendiri yang telah menyelesaikannya.
"""
    response = llm.invoke([HumanMessage(content=prompt)])
    
    return {"messages": [response]}


# ── Graph Building ────────────────────────────────────────────────────────────

def build_graph():
    graph = StateGraph(AgentState)
    
    graph.add_node("master_intent", master_intent_node)
    graph.add_node("batch_worker", batch_worker_node)
    graph.add_node("tool_worker", tool_worker_node)
    graph.add_node("reviewer", reviewer_node)
    graph.add_node("summarizer", summarizer_node)
    
    graph.set_entry_point("master_intent")
    
    graph.add_conditional_edges("master_intent", router, {
        "batch_worker": "batch_worker",
        "tool_worker": "tool_worker",
        "summarizer": "summarizer"
    })
    
    graph.add_edge("batch_worker", "reviewer")
    graph.add_edge("tool_worker", "reviewer")
    
    graph.add_conditional_edges("reviewer", reviewer_router, {
        "tool_worker": "tool_worker",
        "summarizer": "summarizer"
    })
    
    graph.add_edge("summarizer", END)
    
    return graph.compile()

def get_agent_executor(active_project: str = None, user_query: str = None):
    # Mengembalikan graph yang sudah di-compile.
    # Karena telegram_bot dkk mungkin mengandalkan input {"messages": [...]},
    # StateGraph ini kompatibel.
    return build_graph()

