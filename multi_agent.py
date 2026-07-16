import os
import json
from typing import Annotated, Sequence, TypedDict, Literal

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field
from langgraph.prebuilt import create_react_agent

# Import existing core functions to reuse them
from agent import load_all_tools, init_llm, SYSTEM_PROMPT, global_callbacks

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    next: str

# Define Routing output for Supervisor
class RouteResponse(BaseModel):
    next: Literal["PM", "Coder", "Researcher", "QC", "FINISH"] = Field(
        description="The next subagent to route to. Choose FINISH if the user's overall request is fully completed."
    )

from langgraph.checkpoint.sqlite import SqliteSaver

# Setup Memory Store
MEMORY_STORE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memory_store")
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
            
        if any(keyword in name for keyword in ["trello", "fsd", "project"]):
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
            return {"messages": [result["messages"][-1]]}
            
        return node_function

    # 1. PM Node
    pm_node = make_node(
        "Project Manager", 
        pm_tools,
        "Fokus kamu adalah mengelola FSD, membuat Trello tasks, dan berinteraksi dengan memori (Buku Catatan). Jangan melakukan coding."
    )
    
    # 2. Coder Node
    coder_node = make_node(
        "Coder Engineer", 
        coder_tools,
        "Fokus kamu adalah membaca panduan lokal, menulis kode, mengeksekusi command terminal, dan menyelesaikan masalah teknis.\n"
        "ATURAN PENTING CODING: JANGAN MENUMPUK KODE! Hindari membuat satu file monolithic besar (seperti satu app.js raksasa). "
        "Gunakan prinsip modularity: pisahkan kode berdasarkan fitur, komponen, atau fungsi ke dalam file/direktori terpisah (Modular Architecture)."
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
    
    # 5. Supervisor Node
    # The supervisor decides who goes next. It does NOT have tools, it just outputs JSON to route.
    supervisor_llm = llm.with_structured_output(RouteResponse)
    
    def supervisor_node(state: AgentState):
        supervisor_prompt = f"""Kamu adalah SUPERVISOR AGENT. 
Tugasmu adalah melihat histori percakapan dan memutuskan siapa yang harus bekerja selanjutnya.
Kamu membawahi 4 pekerja:
1. PM: Mengurus FSD, Trello, dan manajemen task proyek.
2. Coder: Menulis kode aplikasi modular, menjalankan command terminal, dan membaca guidelines lokal.
3. QC: Menguji kode yang telah dibuat Coder, menjalankan test, mengecek error API.
4. Researcher: Mencari referensi dari internet atau membaca dokumentasi online.

Catatan: SEMUA pekerja di atas (PM, Coder, QC, Researcher) memiliki akses ke Buku Catatan (Memory) untuk mencatat atau mengingat histori bug/solusi!

ATURAN PENTING:
- Panggil QC HANYA SETELAH Coder melaporkan bahwa ia sudah selesai menulis/mengubah kode.
- Jika QC menemukan error, KEMBALIKAN tugas ke Coder untuk diperbaiki.
- Tentukan 'next' worker yang tepat, atau pilih 'FINISH' jika permintaan user sudah SELESAI dikerjakan sepenuhnya (termasuk sudah lulus uji QC jika ada perubahan kode).

Percakapan sejauh ini:
"""
        messages_text = "\n".join([f"{m.type}: {m.content}" for m in state["messages"][-5:]]) # limit context to last 5
        result = supervisor_llm.invoke([
            SystemMessage(content=supervisor_prompt),
            HumanMessage(content=messages_text)
        ])
        
        # Asumsi model mengembalikan object RouteResponse
        if not result or not hasattr(result, 'next'):
            return {"next": "FINISH"}
            
        # We can also add a message from supervisor if we want, but usually just routing is enough
        return {"next": result.next}

    # Build Graph
    workflow = StateGraph(AgentState)
    
    workflow.add_node("Supervisor", supervisor_node)
    workflow.add_node("PM", pm_node)
    workflow.add_node("Coder", coder_node)
    workflow.add_node("QC", qc_node)
    workflow.add_node("Researcher", researcher_node)
    
    # Add Edges
    # Worker selalu lapor balik ke supervisor setelah selesai
    workflow.add_edge("PM", "Supervisor")
    workflow.add_edge("Coder", "Supervisor")
    workflow.add_edge("QC", "Supervisor")
    workflow.add_edge("Researcher", "Supervisor")
    
    # Supervisor bisa ke 4 worker, atau selesai
    workflow.add_conditional_edges(
        "Supervisor",
        lambda state: state["next"],
        {
            "PM": "PM",
            "Coder": "Coder",
            "QC": "QC",
            "Researcher": "Researcher",
            "FINISH": END
        }
    )
    
    workflow.set_entry_point("Supervisor")
    
    memory_saver = SqliteSaver.from_conn_string(CHECKPOINT_DB)
    return workflow.compile(checkpointer=memory_saver)

def get_agent_executor(active_project: str = None):
    # This wrapper returns the compiled StateGraph
    # We maintain the same function name so drop-in replacement is easy.
    return create_multi_agent(active_project=active_project)
