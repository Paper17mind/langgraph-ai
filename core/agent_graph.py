from typing import Annotated, TypedDict
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from core.agent import load_all_tools, select_relevant_tools, retrieve_memories, build_dynamic_prompt, init_llm, global_callbacks

# ---------------------------------------------------------------------------
# Custom StateGraph Agent Executor
# ---------------------------------------------------------------------------

# 1. Definisikan struktur State
# `add_messages` memastikan pesan baru selalu ditambahkan (append) ke riwayat, bukan menimpanya.
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    active_project: str


def get_custom_agent_executor(active_project: str = None):
    """
    Creates and returns a compiled StateGraph.
    Menggantikan create_react_agent dengan custom state graph untuk kontrol lebih baik.
    """
    
    # 2. Definisikan Node Agent (Reasoning)
    def agent_node(state: AgentState):
        print("--- [Graph] Menjalankan Agent Node ---")
        
        # Ambil pesan terakhir dari user untuk evaluasi context (memory & tools)
        user_query = ""
        for msg in reversed(state["messages"]):
            if isinstance(msg, HumanMessage):
                user_query = msg.content
                break

        # A. Siapkan Tools & Memory secara dinamis berdasarkan user_query
        all_tools = load_all_tools()
        relevant_tools = select_relevant_tools(all_tools, user_query) if user_query else all_tools
        memories = retrieve_memories(user_query) if user_query else ""

        # B. Bangun System Prompt
        current_project = state.get("active_project") or active_project
        final_prompt = build_dynamic_prompt(active_project=current_project, user_query=user_query)
        
        if memories:
            final_prompt += f"\n\n[INGATAN MASA LALU (ChromaDB)]\n{memories}\n"

        system_msg = SystemMessage(content=final_prompt)

        # C. Inisialisasi LLM & Bind Tools
        llm = init_llm().with_config(callbacks=global_callbacks)
        
        # Bind tools ke LLM (hanya relevant_tools agar hemat context window)
        if relevant_tools:
            llm_with_tools = llm.bind_tools(relevant_tools)
        else:
            llm_with_tools = llm

        # D. Eksekusi LLM (Kirim prompt sistem + riwayat pesan)
        response = llm_with_tools.invoke([system_msg] + state["messages"])
        
        # Kembalikan response untuk ditambahkan ke state "messages"
        return {"messages": [response]}

    # 3. Definisikan Node Tools (Action)
    # Kita memasukkan *semua* tools ke dalam ToolNode agar node ini bisa mengeksekusi 
    # apa pun yang diminta LLM, meskipun LLM menggunakan memori tool dari iterasi sebelumnya.
    all_available_tools = load_all_tools()
    tool_node = ToolNode(all_available_tools)

    # 4. Rangkai StateGraph
    workflow = StateGraph(AgentState)

    # Daftarkan node
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", tool_node)

    # Tentukan alur eksekusi (Edges)
    workflow.add_edge(START, "agent")

    # Conditional Edge: 
    # tools_condition akan mengecek apakah response dari "agent" mengandung tool_calls.
    # Jika ADA tool_calls -> arahkan ke node "tools".
    # Jika TIDAK ADA -> arahkan ke END.
    workflow.add_conditional_edges(
        "agent",
        tools_condition,
    )

    # Setelah tools dieksekusi, kembalikan hasil ke agent untuk dianalisis ulang
    workflow.add_edge("tools", "agent")

    # Compile menjadi aplikasi yang bisa dijalankan
    return workflow.compile()

