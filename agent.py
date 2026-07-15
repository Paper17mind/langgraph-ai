import os
from dotenv import load_dotenv
load_dotenv()  # Load .env SEBELUM import tools

from langchain_openai import ChatOpenAI
from langchain_groq import ChatGroq
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import SystemMessage

import importlib
import inspect
from langchain_core.tools import BaseTool

def load_all_tools():
    dynamic_tools = []
    base_skills_dir = os.path.join(os.path.dirname(__file__), "skills")
    generated_skills_dir = os.path.join(base_skills_dir, "generated")
    
    # Define directories and their respective module prefixes
    dirs_to_scan = [
        (base_skills_dir, "skills"),
        (generated_skills_dir, "skills.generated")
    ]
    
    for directory, module_prefix in dirs_to_scan:
        if not os.path.exists(directory):
            continue
            
        for filename in os.listdir(directory):
            if filename.endswith("_skill.py") and not filename.startswith("__"):
                module_name = f"{module_prefix}.{filename[:-3]}"
                try:
                    module = importlib.import_module(module_name)
                    for name, obj in inspect.getmembers(module):
                        if isinstance(obj, BaseTool):
                            if obj.name not in [t.name for t in dynamic_tools]:
                                dynamic_tools.append(obj)
                except Exception as e:
                    print(f"Warning: Failed to load {module_name}: {e}")
                    
    return dynamic_tools

# Dynamically load tools
tools = load_all_tools()

def init_llm():
    ninerouter_key = os.getenv("9ROUTER_API_KEY", "")
    ninerouter_url = os.getenv("9ROUTER_URL", "https://9router.com/api/v1/chat/completions")
    base_url = ninerouter_url.replace("/chat/completions", "")
    ninerouter_model = os.getenv("9ROUTER_MODEL", "google/gemini-pro")
    groq_key = os.getenv("GROQ_API_KEY", "")

    if ninerouter_key:
        llm = ChatOpenAI(
            api_key=ninerouter_key,
            base_url=base_url,
            model=ninerouter_model,
            temperature=0.0
        )
        if groq_key:
            groq_llm = ChatGroq(
                api_key=groq_key,
                model_name="llama-3.3-70b-versatile",
                temperature=0.0
            )
            llm = llm.with_fallbacks([groq_llm])
        return llm

    if groq_key:
        return ChatGroq(
            api_key=groq_key,
            model_name="llama-3.3-70b-versatile",
            temperature=0.0
        )

    raise ValueError("No LLM API keys configured (9ROUTER_API_KEY or GROQ_API_KEY).")

llm = init_llm()

SYSTEM_PROMPT = """You are a highly capable AI assistant running on the user's desktop.
You have access to several tools. Use them to help the user.
Kamu memiliki memori jangka panjang (Buku Catatan). Simpanlah informasi penting secara otomatis menggunakan tool 'remember_fact', termasuk: fakta personal user, konteks/arsitektur project, dependensi yang digunakan, dan terutama KESALAHAN/BUG dari kodemu sebelumnya agar tidak diulangi.
Jika kamu menghadapi masalah coding atau butuh konteks, gunakan tool 'recall_facts' untuk mencari solusi masa lalumu.
Jika kamu diminta melakukan sesuatu dan kamu tidak punya tool yang sesuai, kamu diizinkan untuk menulis kode python skill baru. PENTING:
1. Selalu simpan file kode/script baru HANYA di folder `skills/generated/`. DILARANG KERAS membuat file python di folder root (`/`).
2. Jangan membuat script sekali pakai. Buatlah tool dengan decorator `@tool` yang DINAMIS (reusable) dengan parameter/argumen. Jangan membuat tool yang di-hardcode untuk 1 tugas spesifik (contoh: buat tool `search_email(query, limit)` bukan `cek_email_livin_hari_ini()`).
3. Jika kamu butuh membuat file temporary atau script cakar-cakaran untuk testing (seperti melalui terminal bash `cat << EOF`), kamu WAJIB menyimpannya di dalam folder `scratch/` (buat foldernya jika belum ada). DILARANG KERAS menaruh file temporary di folder root!
Skill baru tersebut otomatis aktif pada sesi berikutnya menggunakan tool coder_skill.
If a tool returns an error, read the error carefully and try again to fix the problem.
PENTING (Efisiensi Token): Jika kamu membutuhkan beberapa data sekaligus, panggillah beberapa tool secara BERSAMAAN (Parallel Tool Calling) dalam satu kali respons. Jangan memanggilnya satu-satu secara berurutan agar menghemat waktu dan request ke LLM.
Do not stop until you have either succeeded or fundamentally cannot proceed.
Reply in the same language as the user (default Indonesian)."""

from langchain_core.callbacks import BaseCallbackHandler
from logger import log_internal_step
import json

class AgentLoggingCallback(BaseCallbackHandler):
    def on_chat_model_end(self, response, **kwargs):
        try:
            message = response.generations[0][0].message
            content = message.content
            tool_calls = getattr(message, "tool_calls", [])
            log_internal_step("llm_response", {"content": content, "tool_calls": tool_calls})
        except Exception as e:
            pass

    def on_tool_start(self, serialized, input_str, **kwargs):
        try:
            tool_name = serialized.get("name", "unknown")
            args = json.loads(input_str) if isinstance(input_str, str) else input_str
            log_internal_step("tool_start", {"tool_name": tool_name, "args": args})
        except:
            pass

    def on_tool_end(self, output, **kwargs):
        try:
            log_internal_step("tool_end", {"output": str(output)[:1000]})
        except:
            pass

global_callbacks = [AgentLoggingCallback()]

def get_agent_executor():
    """
    Creates and returns a new agent executor with dynamically loaded tools.
    This allows for hot-reloading of newly generated skills.
    """
    current_tools = load_all_tools()
    
    return create_react_agent(
        model=llm.with_config(callbacks=global_callbacks),
        tools=current_tools,
        prompt=SystemMessage(content=SYSTEM_PROMPT)
    )
