import os
import json
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
    """Master LLM menggunakan Groq"""
    groq_key = os.getenv("GROQ_API_KEY", "")
    if not groq_key:
        raise ValueError("GROQ_API_KEY tidak dikonfigurasi di .env")
    return ChatGroq(
        api_key=groq_key,
        model_name="llama-3.3-70b-versatile",
        temperature=0.4,
        timeout=300,
        max_retries=1,
    )

def init_reviewer_llm():
    """Reviewer LLM menggunakan Groq model yang lebih hemat token (llama-3.1-8b-instant)"""
    groq_key = os.getenv("GROQ_API_KEY", "")
    if not groq_key:
        raise ValueError("GROQ_API_KEY tidak dikonfigurasi di .env")
    return ChatGroq(
        api_key=groq_key,
        model_name="llama-3.1-8b-instant",
        temperature=0.1,
        timeout=300,
        max_retries=1,
    )

def init_tools_llm():
    """Tools LLM menggunakan 9Router / Ollama (dari .env)"""
    ninerouter_key = _get_env_first("NINEROUTER_API_KEY", "9ROUTER_API_KEY", default="ollama")
    ninerouter_url = _get_env_first(
        "NINEROUTER_URL", "9ROUTER_URL", default="http://127.0.0.1:11434/v1/chat/completions"
    )
    base_url = ninerouter_url.replace("/chat/completions", "")
    ninerouter_model = _get_env_first("NINEROUTER_MODEL", "9ROUTER_MODEL", default="hermes3:3b")

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
            
    prompt = f"""
{system}

{chat_history}

Tugas Utama Anda: 
Analisis permintaan pengguna terbaru berikut berdasarkan konteks riwayat percakapan.
Jika permintaan tersebut memerlukan tindakan eksternal / penggunaan tools (misalnya: membaca file yang disebutkan sebelumnya, menjalankan script, eksekusi shell command, melakukan operasi pada sistem, dsb), balas HANYA dengan format:
"USE_TOOLS: <rencana singkat apa yang harus dilakukan>"

PENTING: Jika pengguna merujuk pada sesuatu yang dikerjakan sebelumnya ("file yang tadi", "script yang baru dibuat", dll), Anda WAJIB menggunakan tool untuk membaca/mengecek file tersebut jika Anda belum tahu isinya!

Jika permintaan hanya percakapan biasa atau Anda bisa langsung menjawabnya dari memori/riwayat di atas tanpa alat bantuan apa pun, berikan jawaban langsung kepada pengguna (jangan menggunakan format USE_TOOLS).

Permintaan User Terbaru: {user_query}
"""
    response = llm.invoke([HumanMessage(content=prompt)])
    
    return {"intent": response.content}

def router(state: AgentState):
    intent_val = state.get("intent", "")
    if "USE_TOOLS" in intent_val:
        return "tool_worker"
    return "summarizer"

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
- Anda WAJIB memanggil tools menggunakan mekanisme 'Function Calling' / 'Tool Calling' bawaan (native tool calls).
- Jika Anda tidak memanggil tools secara native, tindakan Anda tidak akan tereksekusi!

Jalankan tools yang sesuai dan berikan kesimpulan akhir tindakan Anda.""")
    )
    
    worker_messages = [HumanMessage(content=user_query)]
    if state.get("review_status") == "REJECTED" and len(state.get("messages", [])) >= 2:
        worker_messages.append(state["messages"][-2]) # AIMessage dari worker sebelumnya
        worker_messages.append(state["messages"][-1]) # HumanMessage feedback dari reviewer

    result = react_agent.invoke({"messages": worker_messages})
    final_output = result["messages"][-1].content
    
    # Kumpulkan riwayat pemanggilan tool untuk diaudit oleh reviewer
    tools_called = []
    for msg in result["messages"][len(worker_messages):]:
        if getattr(msg, "tool_calls", None):
            for tc in msg.tool_calls:
                tools_called.append(f"- {tc['name']}: {tc['args']}")
                
    audit_trail = "\n".join(tools_called) if tools_called else "TIDAK ADA TOOL YANG DIPANGGIL."
    
    return {"messages": [AIMessage(content=f"[Riwayat Tools]:\n{audit_trail}\n\n[Hasil dari Tool Worker]:\n{final_output}")]}

def reviewer_node(state: AgentState):
    """
    Mengevaluasi hasil dari tool_worker_node menggunakan Groq llama-3.1-8b-instant.
    """
    print("\n🔍 [Reviewer Node] Mengevaluasi Pekerjaan Worker...")
    llm = init_reviewer_llm()
    
    retry_count = state.get("retry_count", 0)
    if retry_count >= 3:
        print("⚠️ [Reviewer] Batas maksimum retry tercapai. Lanjut ke summarizer.")
        return {"review_status": "APPROVED", "retry_count": retry_count}
        
    worker_result = state["messages"][-1].content
    user_query = state.get("user_query")
    intent_plan = state.get("intent", "")
    
    prompt = f"""
Tugas Anda adalah mengevaluasi hasil kerja (Tool Worker) berdasarkan permintaan pengguna.
Anda harus bersikap SANGAT TEGAS. Pastikan Worker benar-benar memanggil tool yang diperlukan, bukan sekadar berhalusinasi atau memberikan jawaban teoritis tanpa bertindak.

Permintaan Pengguna: {user_query}
Instruksi/Rencana: {intent_plan}

Laporan Eksekusi Worker: 
{worker_result}

EVALUASI KRITIS:
1. Apakah instruksi mensyaratkan Worker untuk melakukan tindakan fisik (menyimpan file, membaca file, mencari web, dll)?
2. Jika YA, periksa [Riwayat Tools] di atas. Apakah tertulis "TIDAK ADA TOOL YANG DIPANGGIL."? Jika ya, berarti Worker GAGAL/BERHALUSINASI, dan Anda wajib melakukan REJECT!
3. Jika Worker hanya berkata "Saya telah menyimpannya" tapi di [Riwayat Tools] kosong, itu adalah halusinasi. Tolak!

Jika BERHASIL/BENAR (tools dipanggil dengan benar atau permintaan tidak butuh tool spesifik), balas HANYA dengan: "STATUS: APPROVED"
Jika GAGAL/HALUSINASI, balas dengan: "STATUS: REJECTED" dan di baris berikutnya tuliskan instruksi/marahan spesifik apa yang harus diperbaiki oleh Worker (misal: "Anda tidak menggunakan tool apapun! Gunakan tool write_file untuk menyimpan script tersebut!").
"""
    response = llm.invoke([HumanMessage(content=prompt)])
    content = response.content.strip()
    
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
    graph.add_node("tool_worker", tool_worker_node)
    graph.add_node("reviewer", reviewer_node)
    graph.add_node("summarizer", summarizer_node)
    
    graph.set_entry_point("master_intent")
    
    graph.add_conditional_edges("master_intent", router, {
        "tool_worker": "tool_worker",
        "summarizer": "summarizer"
    })
    
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

