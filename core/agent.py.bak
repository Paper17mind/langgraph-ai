import os
import json
import time

from dotenv import load_dotenv
load_dotenv()  # Load .env SEBELUM import tools

from core.dynamic_prompt import build_dynamic_prompt
from core.dynamic_tools import load_all_tools, select_relevant_tools
from langchain_openai import ChatOpenAI
from langchain_groq import ChatGroq
from langchain_ollama import ChatOllama
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import SystemMessage
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.globals import set_debug
from core.logger import log_internal_step, log_token_usage
from rich.live import Live
from rich.markdown import Markdown
from rich.console import Console
from rich.panel import Panel
from rich.spinner import Spinner
from rich.text import Text

console = Console()


# ---------------------------------------------------------------------------
# Dynamic memory retrieval
# ---------------------------------------------------------------------------
# Unlike tool selection above, this is just a vector-DB lookup (not an LLM
# call), so it's cheap enough to run every turn like v1 did. Wrapped so a
# missing/broken memory_db never takes the whole agent down with it.

def retrieve_memories(query: str, k: int = 3) -> str:
    if not query:
        return ""
    try:
        from utils.memory_db import memory_db
    except Exception as e:
        print(f"[memory] memory_db unavailable: {e}")
        return ""
    try:
        facts = memory_db.search_facts(query, k=k)
        return facts or ""
    except Exception as e:
        print(f"[memory] retrieval failed: {e}")
        return ""


# ---------------------------------------------------------------------------
# LLM init
# ---------------------------------------------------------------------------

def _get_env_first(*names, default=""):
    """
    Look up the first set env var among `names`. This exists because env
    vars starting with a digit (e.g. 9ROUTER_API_KEY) are invalid/rejected
    by some shells and .env loaders. We keep reading the legacy name for
    backward compatibility but prefer a valid identifier if present.
    """
    for name in names:
        val = os.getenv(name)
        if val:
            return val
    return default


def init_llm():
    ninerouter_key = _get_env_first("NINEROUTER_API_KEY", "9ROUTER_API_KEY")
    ninerouter_url = _get_env_first(
        "NINEROUTER_URL", "9ROUTER_URL", default="https://9router.com/api/v1/chat/completions"
    )
    base_url = ninerouter_url.replace("/chat/completions", "")
    ninerouter_model = _get_env_first("NINEROUTER_MODEL", "9ROUTER_MODEL", default="google/gemini-pro")
    groq_key = os.getenv("GROQ_API_KEY", "")

    if ninerouter_key:
        llm = ChatOpenAI(
            api_key=ninerouter_key,
            base_url=base_url,
            model=ninerouter_model,
            streaming=True,
            temperature=0.4,
            timeout=600,
            max_retries=1,
            extra_body={
                "options": {
                    "num_ctx": 8192
                }
            },
            model_kwargs={
                "stream_options": {"include_usage": True}
            }
        )
        if groq_key:
            groq_llm = ChatGroq(
                api_key=groq_key,
                model_name="llama-3.3-70b-versatile",
                temperature=0.4,
                timeout=300,
                max_retries=1,
            )
            llm = llm.with_fallbacks([groq_llm])
        return llm

    if groq_key:
        return ChatGroq(
            api_key=groq_key,
            model_name="llama-3.3-70b-versatile",
            temperature=0.4,
            timeout=300,
            max_retries=1,
        )

    raise ValueError(
        "No LLM API keys configured (NINEROUTER_API_KEY/9ROUTER_API_KEY or GROQ_API_KEY)."
    )



# ---------------------------------------------------------------------------
# Logging callback
# ---------------------------------------------------------------------------

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
        """Dipanggil setiap kali user mengirim pesan baru untuk mengukur total waktu."""
        self.start_time = time.time()

    def on_chat_model_start(self, serialized, messages, **kwargs):
        self.current_text = ""
        self.has_started_streaming = False
        self.live = Live(TimerSpinner(lambda: self.start_time), console=console, refresh_per_second=15, transient=False)
        self.live.start()

    def on_llm_new_token(self, token: str, **kwargs) -> None:
        """Dipanggil setiap kali ada token baru dari LLM (streaming)."""
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
        """Paksa hentikan Live display — dipanggil saat KeyboardInterrupt."""
        if self.live:
            try:
                self.live.stop()
            except Exception:
                pass
            finally:
                self.live = None
        self.current_text = ""

    def on_llm_end(self, response, **kwargs):
        """Called when any LLM (including ChatModels) finishes generating."""
        if self.live:
            if not self.current_text.strip():
                self.live.update("")
            self.live.stop()
            self.live = None
        try:
            # Extract token usage - try multiple locations
            usage = None

            # 1. Standard LangChain location (ChatOpenAI, ChatGroq, etc.)
            if response.llm_output and "token_usage" in response.llm_output:
                usage = response.llm_output["token_usage"]

            # 2. Some providers put it directly in generation_info
            if not usage and response.generations:
                gen = response.generations[0][0]
                gen_info = getattr(gen, "generation_info", None) or {}
                if "usage" in gen_info:
                    raw = gen_info["usage"]
                    usage = {
                        "prompt_tokens": raw.get("prompt_tokens", 0),
                        "completion_tokens": raw.get("completion_tokens", 0),
                        "total_tokens": raw.get("total_tokens", 0),
                    }

                # 3. usage_metadata on the message (newer LangChain ChatGeneration)
                if not usage or usage.get("total_tokens", 0) == 0:
                    message = getattr(gen, "message", None)
                    meta = getattr(message, "usage_metadata", None) if message else None
                    if isinstance(meta, dict) and meta:
                        usage = {
                            "prompt_tokens": meta.get("input_tokens", 0),
                            "completion_tokens": meta.get("output_tokens", 0),
                            "total_tokens": meta.get("total_tokens", 0),
                        }

                # 4. Ollama specific in message.response_metadata
                if not usage or usage.get("total_tokens", 0) == 0:
                    message = getattr(gen, "message", None)
                    resp_meta = getattr(message, "response_metadata", {}) if message else {}
                    if "prompt_eval_count" in resp_meta or "eval_count" in resp_meta:
                        p_count = resp_meta.get("prompt_eval_count", 0)
                        c_count = resp_meta.get("eval_count", 0)
                        usage = {
                            "prompt_tokens": p_count,
                            "completion_tokens": c_count,
                            "total_tokens": p_count + c_count
                        }

            if usage:
                prompt_tokens = usage.get("prompt_tokens", 0)
                comp_tokens = usage.get("completion_tokens", 0)
                total_tokens = usage.get("total_tokens", 0)
                print(f"\n🪙 [Token Usage] Prompt: {prompt_tokens} | Completion: {comp_tokens} | Total: {total_tokens}")
                log_token_usage(usage)
            else:
                # Debug: show raw structure so we can trace the right location
                print(f"\n⚠️ [Token Usage] Not found. llm_output keys: {list((response.llm_output or {}).keys())}")

            # Log LLM response content
            if response.generations:
                gen = response.generations[0][0]
                message = getattr(gen, "message", None)
                content = getattr(message, "content", getattr(gen, "text", ""))
                tool_calls = getattr(message, "tool_calls", []) if message else []
                log_internal_step("llm_response", {
                    "content": content,
                    "tool_calls": tool_calls
                })
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

# ---------------------------------------------------------------------------
# Agent executor factory
# ---------------------------------------------------------------------------

def get_agent_executor(active_project: str = None, user_query: str = None):
    current_tools = load_all_tools()
    # if user_query:
    #     current_tools = select_relevant_tools(current_tools, user_query)

    current_llm = init_llm()

    final_prompt = build_dynamic_prompt(active_project=active_project, user_query=user_query)

    # Injeksi daftar tools secara dinamis agar model tahu apa saja tools-nya jika ditanya
    tool_list_str = "\n".join([f"- **{t.name}**: {t.description}" for t in current_tools])
    final_prompt += f"\n\n[DAFTAR TOOLS AKTIF]\nBerikut adalah fungsi (tools) yang bisa kamu gunakan. Jika user bertanya tentang tools atau kemampuanmu, bacakan daftar ini secara santai:\n{tool_list_str}\n"

    memories = retrieve_memories(user_query) if user_query else ""
    if memories:
        final_prompt += f"\n\n[INGATAN MASA LALU (ChromaDB)]\n{memories}\n"
    print(f"memories {memories}")
    return create_react_agent(
        model=current_llm.with_config(callbacks=global_callbacks),
        tools=current_tools,
        prompt=SystemMessage(content=final_prompt),
    )
