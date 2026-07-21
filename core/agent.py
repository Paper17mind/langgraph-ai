import os
import json

from dotenv import load_dotenv
load_dotenv()  # Load .env SEBELUM import tools

from core.dynamic_prompt import build_dynamic_prompt
from core.dynamic_tools import load_all_tools, select_relevant_tools
from langchain_openai import ChatOpenAI
from langchain_groq import ChatGroq
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import SystemMessage
from langchain_core.callbacks import BaseCallbackHandler

from core.logger import log_internal_step, log_token_usage



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

    raise ValueError(
        "No LLM API keys configured (NINEROUTER_API_KEY/9ROUTER_API_KEY or GROQ_API_KEY)."
    )



# ---------------------------------------------------------------------------
# Logging callback
# ---------------------------------------------------------------------------

class AgentLoggingCallback(BaseCallbackHandler):
    def on_llm_end(self, response, **kwargs):
        """Called when any LLM (including ChatModels) finishes generating."""
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
                if not usage:
                    message = getattr(gen, "message", None)
                    meta = getattr(message, "usage_metadata", None) if message else None
                    if meta:
                        usage = {
                            "prompt_tokens": getattr(meta, "input_tokens", 0),
                            "completion_tokens": getattr(meta, "output_tokens", 0),
                            "total_tokens": getattr(meta, "total_tokens", 0),
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

# ---------------------------------------------------------------------------
# Agent executor factory
# ---------------------------------------------------------------------------

def get_agent_executor(active_project: str = None, user_query: str = None):
    current_tools = load_all_tools()
    if user_query:
        current_tools = select_relevant_tools(current_tools, user_query)

    current_llm = init_llm()

    final_prompt = build_dynamic_prompt(active_project=active_project, user_query=user_query)

    memories = retrieve_memories(user_query) if user_query else ""
    if memories:
        final_prompt += f"\n\n[INGATAN MASA LALU (ChromaDB)]\n{memories}\n"

    return create_react_agent(
        model=current_llm.with_config(callbacks=global_callbacks),
        tools=current_tools,
        prompt=SystemMessage(content=final_prompt),
    )