import os
import sys
import json
import history_manager
from logger import log_request
from multi_agent import get_agent_executor
from langchain_core.messages import HumanMessage, AIMessage
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.prompt import Prompt
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich import print as rprint

console = Console()

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cli_sessions.json")

def load_configs():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {}

def save_configs(configs):
    with open(CONFIG_FILE, "w") as f:
        json.dump(configs, f)

def run_cli_bot():
    console.print(Panel.fit("🤖 AI Assistant CLI Mode Started\nType [bold red]exit[/] or [bold red]quit[/] to close", title="Welcome", border_style="green"))
    
    configs = load_configs()
    active_session = "default"
    active_project = configs.get(active_session, None)
    
    if active_project:
        console.print(f"[bold dim]Memuat proyek terakhir untuk sesi '{active_session}': {active_project}[/]")
    
    while True:
        try:
            # Use rich Prompt for beautiful input
            proj_str = f" [green]({active_project})[/]" if active_project else ""
            text = Prompt.ask(f"\n[bold cyan]Assistant[/][dim]({active_session})[/]{proj_str}")
            if text.strip().lower() in ['exit', 'quit']:
                break
                
            if not text.strip():
                continue
                
            if text.strip().startswith("/"):
                command_parts = text.strip().split()
                cmd = command_parts[0].lower()
                
                if cmd == "/project":
                    if len(command_parts) > 1:
                        active_project = command_parts[1].lower()
                        configs[active_session] = active_project
                        save_configs(configs)
                        console.print(f"[bold green]✅ Proyek aktif disetel ke:[/] {active_project}")
                    else:
                        # List projects
                        proj_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "projects")
                        if os.path.exists(proj_dir):
                            projs = [d for d in os.listdir(proj_dir) if os.path.isdir(os.path.join(proj_dir, d))]
                            if projs:
                                console.print("[bold cyan]📁 Daftar Proyek:[/]")
                                for p in projs:
                                    console.print(f"- {p}")
                                console.print("\n[dim]Gunakan /project <nama> untuk memilih.[/dim]")
                            else:
                                console.print("[bold yellow]Belum ada proyek yang dibuat.[/]")
                        else:
                            console.print("[bold yellow]Folder projects/ belum ada.[/]")
                    continue
                
                elif cmd == "/session":
                    if len(command_parts) > 1:
                        active_session = command_parts[1].lower()
                        active_project = configs.get(active_session, None)
                        console.print(f"[bold green]✅ Berpindah ke sesi:[/] {active_session}")
                        if active_project:
                            console.print(f"[bold dim]Memuat proyek terakhir: {active_project}[/]")
                    else:
                        # List sessions
                        sessions = history_manager.get_all_sessions("cli_")
                        if sessions:
                            console.print("[bold cyan]📂 Daftar Sesi Obrolan:[/]")
                            for s in sessions:
                                marker = " *(aktif)" if s == active_session else ""
                                console.print(f"- {s}{marker}")
                            console.print("\n[dim]Gunakan /session <nama> untuk memilih.[/dim]")
                        else:
                            console.print("[bold yellow]Belum ada sesi yang terekam.[/]")
                    continue
                
                elif cmd == "/model":
                    if len(command_parts) > 1:
                        new_model = command_parts[1]
                        os.environ["9ROUTER_MODEL"] = new_model
                        console.print(f"[bold green]✅ Model diubah menjadi:[/] {new_model}")
                    else:
                        console.print("[bold yellow]⚠️ Gunakan format: /model <nama_model>[/]")
                    continue
                    
                elif cmd == "/memory":
                    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                    from utils.memory_db import memory_db
                    facts = memory_db.get_all_facts()
                    if not facts:
                        console.print("[bold yellow]Memori (ChromaDB) saat ini kosong.[/]")
                    else:
                        console.print(Panel(
                            "\n".join(f"- {f}" for f in facts),
                            title="🧠 Long-Term Memory (ChromaDB)",
                            border_style="magenta"
                        ))
                    continue
                    
                elif cmd == "/clear":
                    os.system('cls' if os.name == 'nt' else 'clear')
                    continue
                    
                elif cmd == "/help":
                    help_text = """
**Daftar Perintah (Slash Commands):**
- `/project [nama]` : Memilih proyek aktif atau melihat daftar proyek.
- `/session <nama_sesi>` : Berpindah ke ruang/konteks obrolan yang berbeda (contoh: `/session livin`).
- `/model <nama_model>` : Mengubah model LLM yang digunakan secara real-time.
- `/memory` : Menampilkan seluruh isi memori jangka panjang (ChromaDB).
- `/clear` : Membersihkan riwayat layar terminal.
- `/help` : Menampilkan pesan bantuan ini.
- `exit` atau `quit` : Menutup aplikasi.
                    """
                    console.print(Panel(Markdown(help_text), title="Bantuan", border_style="cyan"))
                    continue
                else:
                    console.print(f"[bold red]❌ Perintah {cmd} tidak dikenal. Ketik /help untuk daftar perintah.[/]")
                    continue
                    
            # Fetch history
            session_id = f"cli_{active_session}"
            past_messages = history_manager.get_history(session_id, limit=6)
            messages = []
            for msg in past_messages:
                if msg["role"] == "user":
                    messages.append(HumanMessage(content=msg["content"]))
                else:
                    messages.append(AIMessage(content=msg["content"]))
                    
            messages.append(HumanMessage(content=text))
            
            final_message = ""
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                transient=True,
            ) as progress:
                task = progress.add_task("[cyan]Thinking...", total=None)
                # Get fresh agent executor (Hot Reload)
                from agent import global_callbacks
                agent_executor = get_agent_executor(active_project=active_project)
                
                # Stream the agent's steps
                for event in agent_executor.stream(
                    {"messages": messages}, 
                    config={"callbacks": global_callbacks, "configurable": {"thread_id": session_id}, "recursion_limit": 100}
                ):
                    for key, value in event.items():
                        # key is the node name (e.g., 'Supervisor', 'Coder', 'PM', 'QC')
                        progress.console.print(f"[bold magenta]🤖 Node Finished:[/] {key}")
                        
                        if "next" in value:
                            progress.console.print(f"[bold blue]🔀 Routing to:[/] {value['next']}")
                            
                        if "messages" in value:
                            agent_msgs = value.get("messages", [])
                            if not isinstance(agent_msgs, list):
                                agent_msgs = [agent_msgs]
                                
                            for msg in agent_msgs:
                                # Print text content
                                content_preview = str(getattr(msg, "content", "")).strip()
                                if content_preview:
                                    progress.console.print(f"   [dim]{content_preview}[/]")
                                    
                                # Print tool calls if any
                                tool_calls = getattr(msg, "tool_calls", [])
                                if tool_calls:
                                    for tool in tool_calls:
                                        progress.console.print(f"   [dim cyan]🛠️  Calling Tool: {tool.get('name', 'unknown')}({tool.get('args', {})})[/]")
                                    
                                if getattr(msg, "content", "") and not getattr(msg, "tool_calls", None):
                                    # Since Supervisor is the brain, we often get the final text from the last node
                                    final_message = msg.content
            
            # Save User Message and Assistant Response
            history_manager.add_message(session_id, "user", text)
            history_manager.add_message(session_id, "assistant", final_message)
            
            # Log the request
            log_request("langgraph_agent", text, final_message)
            
            # Output beautifully using Markdown
            console.print("\n")
            console.print(Panel(Markdown(final_message), title="Response", border_style="blue"))
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            console.print(f"[bold red]Error:[/] {e}")
            
    console.print("\n[bold green]Exiting CLI... Goodbye![/]")
