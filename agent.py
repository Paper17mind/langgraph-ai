import os
from dotenv import load_dotenv
load_dotenv()  # Load .env SEBELUM import tools

from langchain_openai import ChatOpenAI
from langchain_groq import ChatGroq
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import SystemMessage

# Import our converted tools
from skills.system_skill import execute_system_command
from skills.coder_skill import write_code_to_file
from skills.web_search_skill import search_duckduckgo
from skills.http_skill import fetch_url_content
from skills.scheduler_skill import schedule_task
from skills.trello_skill import (
    trello_create_board,
    trello_add_list,
    trello_add_card,
    trello_get_board,
)

# Tools list
tools = [
    execute_system_command,
    write_code_to_file,
    search_duckduckgo,
    fetch_url_content,
    schedule_task,
    trello_create_board,
    trello_add_list,
    trello_add_card,
    trello_get_board,
]

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
If a tool returns an error, read the error carefully and try again to fix the problem.
Do not stop until you have either succeeded or fundamentally cannot proceed.
Reply in the same language as the user (default Indonesian)."""

agent_executor = create_react_agent(
    model=llm,
    tools=tools,
    prompt=SystemMessage(content=SYSTEM_PROMPT)
)
