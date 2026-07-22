# agent.py (Plan-and-Execute version)
import os
import json
from dotenv import load_dotenv
load_dotenv()
from core.llm_client import llm
from core.dynamic_prompt import build_dynamic_prompt
from core.dynamic_tools import load_all_tools, select_relevant_tools
from langchain_openai import ChatOpenAI
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.callbacks import BaseCallbackHandler
from langgraph.graph import StateGraph, END
from typing import TypedDict, List, Any

from core.logger import log_internal_step, log_token_usage

# ── Reuse fungsi yang sudah ada ─────────────────────────────────────────────
from langgraph.graph import StateGraph, END
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from typing import TypedDict, List, Annotated
import operator

# ── State dengan compressed context ──────────────────────────────────────────

class HybridState(TypedDict):
    user_input: str
    active_project: str
    available_tools: dict
    
    messages: List          # full messages (hanya untuk LLM call ini)
    tool_results: List[str] # ringkasan hasil tool — ini yang dibawa antar step
    iteration: int          # berapa kali LLM sudah dipanggil
    max_iterations: int     # batas max (anti infinite loop)
    final_answer: str


# ── Node: LLM decide + call tool ─────────────────────────────────────────────

def llm_node(state: HybridState) -> dict:
    llm = init_llm().with_config(callbacks=global_callbacks)
    
    iteration = state.get("iteration", 0)
    max_iter = state.get("max_iterations", 5)
    tool_results = state.get("tool_results", [])

    # ── Bangun prompt — hanya bawa RINGKASAN hasil, bukan full history ────
    system = build_dynamic_prompt(
        active_project=state.get("active_project"),
        user_query=state["user_input"]
    )
    
    # Inject memory
    memories = retrieve_memories(state["user_input"])
    if memories:
        system += f"\n\n[MEMORI]\n{memories}"

    # Inject hasil tool sebelumnya — RINGKAS, bukan full chat history
    if tool_results:
        results_summary = "\n".join(f"- {r}" for r in tool_results[-3:])  # max 3 hasil terakhir
        system += f"\n\n[HASIL TOOL SEBELUMNYA]\n{results_summary}"
        system += "\n\nLanjutkan berdasarkan hasil di atas. Jika sudah selesai, jawab langsung."

    # Tools yang tersedia
    tool_list = list(state["available_tools"].keys())
    system += f"\n\nTools tersedia: {tool_list}"
    system += "\n\nJika perlu tool, balas dengan format:\nUSE_TOOL: <nama_tool>\nPARAMS: <json params>"
    system += "\n\nJika sudah bisa jawab langsung, balas dengan:\nFINAL: <jawaban kamu>"

    messages = [
        SystemMessage(content=system),
        HumanMessage(content=state["user_input"])
    ]

    response = llm.invoke(messages)
    content = response.content.strip()

    print(f"\n🤖 [LLM iter={iteration}]\n{content[:300]}")

    return {
        "messages": [response],
        "iteration": iteration + 1,
        "_llm_output": content  # simpan untuk router
    }


# ── Node: Eksekusi tool ───────────────────────────────────────────────────────

def tool_node(state: HybridState) -> dict:
    llm_output = state.get("_llm_output", "")
    tool_results = state.get("tool_results", [])

    try:
        # Parse USE_TOOL dan PARAMS dari output LLM
        lines = llm_output.strip().split("\n")
        tool_name = ""
        params_str = ""
        
        for i, line in enumerate(lines):
            if line.startswith("USE_TOOL:"):
                tool_name = line.replace("USE_TOOL:", "").strip()
            if line.startswith("PARAMS:"):
                # Ambil semua setelah PARAMS: (bisa multiline JSON)
                params_str = "\n".join(lines[i:]).replace("PARAMS:", "", 1).strip()
                break

        if not tool_name:
            return {"tool_results": tool_results + ["ERROR: LLM tidak specify tool"]}

        # Normalize params
        params_str = params_str.replace("```json", "").replace("```", "").strip()
        params = json.loads(params_str) if params_str else {}

        # Auto-fix alias param
        ALIASES = {
            "cwd": "working_dir",
            "dir": "working_dir",
            "cmd": "command",
        }
        for wrong, correct in ALIASES.items():
            if wrong in params and correct not in params:
                params[correct] = params.pop(wrong)
                print(f"🔧 Auto-fix param: '{wrong}' → '{correct}'")

        print(f"\n⚙️  [Tool] {tool_name} | params={params}")

        # Jalankan tool
        tool_fn = state["available_tools"].get(tool_name)
        if not tool_fn:
            result = f"ERROR: Tool '{tool_name}' tidak ada. Tersedia: {list(state['available_tools'].keys())}"
        else:
            result = str(tool_fn.invoke(params))

        # ── Yang penting: simpan RINGKASAN, bukan raw output ──────────
        compressed = compress_tool_result(tool_name, params, result)
        
        print(f"   ✅ Result (compressed): {compressed[:200]}")
        return {"tool_results": tool_results + [compressed]}

    except json.JSONDecodeError as e:
        error = f"ERROR parse params: {e} | raw: {params_str[:100]}"
        return {"tool_results": tool_results + [error]}
    except Exception as e:
        return {"tool_results": tool_results + [f"ERROR: {e}"]}


def compress_tool_result(tool_name: str, params: dict, result: str) -> str:
    """
    Compress hasil tool jadi ringkasan singkat.
    Ini yang dibawa ke LLM berikutnya — bukan raw output yang panjang.
    """
    # Kalau error, bawa full error message
    if result.startswith("ERROR"):
        return f"{tool_name}: {result}"
    
    # Kalau output panjang, potong + summary
    if len(result) > 500:
        return f"{tool_name}({params}): [OK] {result[:300]}... [truncated {len(result)} chars]"
    
    return f"{tool_name}({params}): {result}"


# ── Router: LLM mau tool atau sudah selesai? ─────────────────────────────────

def router(state: HybridState) -> str:
    llm_output = state.get("_llm_output", "")
    iteration = state.get("iteration", 0)
    max_iter = state.get("max_iterations", 5)

    # Batas iterasi
    if iteration >= max_iter:
        print(f"\n⛔ Max iterations ({max_iter}) reached")
        return "summarize"

    if llm_output.startswith("FINAL:"):
        return "summarize"
    
    if "USE_TOOL:" in llm_output:
        return "tool"
    
    # Default: anggap sudah final
    return "summarize"


# ── Node: Summarizer ──────────────────────────────────────────────────────────

def summarizer_node(state: HybridState) -> dict:
    llm_output = state.get("_llm_output", "")
    
    # Kalau LLM sudah kasih FINAL answer, pakai itu langsung — 0 token lagi
    if llm_output.startswith("FINAL:"):
        answer = llm_output.replace("FINAL:", "").strip()
        return {"final_answer": answer}
    
    # Kalau kena max iteration, baru panggil LLM untuk wrap up
    tool_results = state.get("tool_results", [])
    llm = init_llm().with_config(callbacks=global_callbacks)
    
    response = llm.invoke([HumanMessage(
        content=f"Buat summary dari hasil ini untuk user:\n" + "\n".join(tool_results)
    )])
    return {"final_answer": response.content}


# ── Build Graph ───────────────────────────────────────────────────────────────

def build_hybrid_graph():
    graph = StateGraph(HybridState)
    
    graph.add_node("llm", llm_node)
    graph.add_node("tool", tool_node)
    graph.add_node("summarize", summarizer_node)

    graph.set_entry_point("llm")
    
    graph.add_conditional_edges("llm", router, {
        "tool": "tool",
        "summarize": "summarize",
    })
    
    # Setelah tool → balik ke LLM, tapi dengan compressed context
    graph.add_edge("tool", "llm")
    graph.add_edge("summarize", END)

    return graph.compile()
def retrieve_memories(query: str, k: int = 3) -> str:
    if not query:
        return ""
    try:
        from utils.memory_db import memory_db
        return memory_db.search_facts(query, k=k) or ""
    except Exception as e:
        print(f"[memory] retrieval failed: {e}")
        return ""


def _get_env_first(*names, default=""):
    for name in names:
        val = os.getenv(name)
        if val:
            return val
    return default


def init_llm():
    # Sama persis dengan kode lamamu
    ninerouter_key = _get_env_first("NINEROUTER_API_KEY", "9ROUTER_API_KEY")
    ninerouter_url = _get_env_first(
        "NINEROUTER_URL", "9ROUTER_URL",
        default="https://9router.com/api/v1/chat/completions"
    )
    base_url = ninerouter_url.replace("/chat/completions", "")
    ninerouter_model = _get_env_first("NINEROUTER_MODEL", "9ROUTER_MODEL", default="google/gemini-pro")
    groq_key = os.getenv("GROQ_API_KEY", "")

    if ninerouter_key:
        llm = ChatOpenAI(
            api_key=ninerouter_key,
            base_url=base_url,
            model=ninerouter_model,
            temperature=0.4,
            timeout=30,
            max_retries=1,
        )
        if groq_key:
            groq_llm = ChatGroq(
                api_key=groq_key,
                model_name="llama-3.3-70b-versatile",
                temperature=0.4,
                timeout=30,
                max_retries=1,
            )
            llm = llm.with_fallbacks([groq_llm])
        return llm

    if groq_key:
        return ChatGroq(
            api_key=groq_key,
            model_name="llama-3.3-70b-versatile",
            temperature=0.4,
            timeout=30,
            max_retries=1,
        )

    raise ValueError("No LLM API keys configured.")


# ── Logging callback (sama dengan kode lamamu) ───────────────────────────────

class AgentLoggingCallback(BaseCallbackHandler):
    def on_llm_end(self, response, **kwargs):
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
            print(f"[Callback Error] {e}")

    def on_tool_start(self, serialized, input_str, **kwargs):
        try:
            tool_name = serialized.get("name", "unknown")
            args = json.loads(input_str) if isinstance(input_str, str) else input_str
            log_internal_step("tool_start", {"tool_name": tool_name, "args": args})
        except Exception:
            pass

    def on_tool_end(self, output, **kwargs):
        try:
            log_internal_step("tool_end", {"output": str(output)[:1000]})
        except Exception:
            pass


global_callbacks = [AgentLoggingCallback()]


# ── State ─────────────────────────────────────────────────────────────────────
class AgentState(TypedDict):
    user_input: str
    active_project: str
    plan: List[dict]
    results: List[str]
    summary: str
    available_tools: dict
    warnings: List[str]   # ← tambah ini


# ── Node 1: PLANNER (1x LLM call) ────────────────────────────────────────────

def planner_node(state: AgentState) -> dict:
    user_input = state["user_input"]
    tool_names = list(state["available_tools"].keys())
    system_prompt = ""

    planner_prompt = f"""
Kamu adalah planner AI. Buat execution plan untuk permintaan user.

Tools yang tersedia: {json.dumps(tool_names)}

RULES:
- Jika perlu tool → list step dengan action = nama tool
- Output HANYA JSON array, tanpa penjelasan apapun
- Jika tools tidak ada, buat script yang bisa dijalankan di terminal, kemudian jalankan script tersebut dengan tool execute_system_command
- Jangan jawab user secara langsung, selalu gunakan tool

Contoh output:
[
  {{"step": 1, "action": "read_file", "params": {{"path": "data.txt"}}}},
  {{"step": 2, "action": "summarize_text", "params": {{"text": "{{result_step_1}}"}}}}
]

Permintaan user: {user_input}
"""

    content = llm.ask(user_input, system_prompt)
    

    # Parse JSON, bersihkan kalau ada markdown fence
    content = content.replace("```json", "").replace("```", "").strip()
    try:
        plan = json.loads(content)
    except json.JSONDecodeError:
        # Fallback: direct answer kalau JSON gagal parse
        plan = [{"step": 1, "action": "direct_answer", "params": {"query": user_input}}]

    print(f"\n📋 [Plan] {json.dumps(plan, indent=2, ensure_ascii=False)}")
    return {"plan": plan}


# ── Node 2: EXECUTOR (0x LLM call, jalan lokal) ──────────────────────────────

def executor_node(state: AgentState) -> dict:
    results = []
    last_result = ""

    for step in state["plan"]:
        action = step.get("action", "")
        params = step.get("params", {})
        step_num = step.get("step", "?")
        status = step.get("_status", "OK")

        # ── Skip step yang bermasalah ─────────────────────────────────
        if status == "SKIP":
            issue = step.get("_issue", "unknown")
            result = f"SKIPPED: {issue}"
            print(f"\n⏭️  [Step {step_num}] SKIP — {issue}")
            results.append(f"Step {step_num} ({action}): {result}")
            continue

        # ── Step butuh konfirmasi manual ──────────────────────────────
        if status == "NEEDS_CONFIRMATION":
            issue = step.get("_issue", "")
            result = f"NEEDS_CONFIRMATION: {issue}"
            print(f"\n❓ [Step {step_num}] PERLU KONFIRMASI — {issue}")
            results.append(f"Step {step_num} ({action}): {result}")
            continue

        # Kalau ada fix, info ke user
        if "_fix" in step:
            print(f"\n🔧 [Step {step_num}] {step['_fix']}")

        # Inject hasil step sebelumnya
        params = {
            k: v.replace("{result_step_" + str(step_num - 1) + "}", last_result)
            if isinstance(v, str) else v
            for k, v in params.items()
        }

        print(f"\n⚙️  [Step {step_num}] action={action} params={params}")

        if action == "direct_answer":
            result = f"DIRECT: {params.get('query', '')}"
        elif action in state["available_tools"]:
            tool_fn = state["available_tools"][action]
            try:
                result = str(tool_fn.invoke(params))
            except Exception as e:
                result = f"ERROR: {e}"
                print(f"   ❌ Tool error: {e}")
        else:
            result = f"Tool '{action}' tidak ditemukan"

        results.append(f"Step {step_num} ({action}): {result}")
        last_result = result

    return {"results": results}


# ── Node 3: SUMMARIZER (1x LLM call) ─────────────────────────────────────────

def summarizer_node(state: AgentState) -> dict:
    llm = init_llm().with_config(callbacks=global_callbacks)

    results_text = "\n".join(state["results"])
    user_input = state["user_input"]

    # Kalau direct answer, LLM jawab langsung dengan konteks penuh
    is_direct = any("DIRECT:" in r for r in state["results"])

    if is_direct:
        prompt = f"Jawab pertanyaan user secara langsung dan helpful.\n\nPertanyaan: {user_input}"
    else:
        prompt = f"""Berikut hasil eksekusi untuk permintaan: "{user_input}"

{results_text}

Buat summary yang jelas dan actionable untuk user. Highlight hal penting.
"""

    response = llm.invoke([HumanMessage(content=prompt)])
    summary = response.content
    print(f"\n✅ [Summary] {summary[:200]}...")
    return {"summary": summary}


# ── Build Graph ───────────────────────────────────────────────────────────────

# Di AgentState, tambah field warnings
class AgentState(TypedDict):
    user_input: str
    active_project: str
    plan: List[dict]
    results: List[str]
    summary: str
    available_tools: dict
    warnings: List[str]   # ← tambah ini

# Di build_graph()
def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("planner", planner_node)
    graph.add_node("verifier", verifier_node)   # ← tambah ini
    graph.add_node("executor", executor_node)
    graph.add_node("summarizer", summarizer_node)

    graph.set_entry_point("planner")
    graph.add_edge("planner", "verifier")       # ← planner → verifier
    graph.add_edge("verifier", "executor")      # ← verifier → executor
    graph.add_edge("executor", END)
    # graph.add_edge("executor", "summarizer")
    # graph.add_edge("summarizer", END)

    return graph.compile()


def verifier_node(state: AgentState) -> dict:
    plan = state["plan"]
    
    # Alias mapping — param yang sering salah nama dari LLM
    PARAM_ALIASES = {
        "execute_system_command": {
            "cwd": "working_dir",
            "dir": "working_dir", 
            "directory": "working_dir",
            "work_dir": "working_dir",
            "cmd": "command",
            "shell": "command",
        },
        # Tambah tool lain kalau ada alias serupa
    }

    for step in plan:
        action = step.get("action", "")
        params = step.get("params", {})

        # ── Auto-rename param alias ───────────────────────────────────
        if action in PARAM_ALIASES:
            aliases = PARAM_ALIASES[action]
            for wrong_key, correct_key in aliases.items():
                if wrong_key in params and correct_key not in params:
                    params[correct_key] = params.pop(wrong_key)
                    step["_fix"] = step.get("_fix", "") + f" | renamed '{wrong_key}'→'{correct_key}'"
                    print(f"🔧 [Verifier] Step {step['step']}: '{wrong_key}' → '{correct_key}'")

            step["params"] = params  # pastikan update

        # ... sisa verifier logic seperti sebelumnya

    return {"plan": plan, "warnings": []}
# ── Public API (sama interface dengan versi lama) ─────────────────────────────

def get_agent_executor(active_project: str = None, user_query: str = None):
    all_tools = load_all_tools()
    if user_query:
        all_tools = select_relevant_tools(all_tools, user_query)

    # Buat dict nama → tool object
    tools_dict = {tool.name: tool for tool in all_tools}

    return build_graph(), {
        "user_input": user_query or "",
        "active_project": active_project or "",
        "plan": [],
        "results": [],
        "summary": "",
        "available_tools": tools_dict,
    }
