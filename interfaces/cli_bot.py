import os
import history_manager
from logger import log_request
from agent import get_agent_executor
from langchain_core.messages import HumanMessage, AIMessage
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.prompt import Prompt
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich import print as rprint

console = Console()

def run_cli_bot():
    console.print(Panel.fit("🤖 AI Assistant CLI Mode Started\nType [bold red]exit[/] or [bold red]quit[/] to close", title="Welcome", border_style="green"))
    
    session_id = "cli_default"
    
    while True:
        try:
            # Use rich Prompt for beautiful input
            text = Prompt.ask("\n[bold cyan]Assistant[/]")
            if text.strip().lower() in ['exit', 'quit']:
                break
                
            if not text.strip():
                continue
                
            # Fetch history
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
                agent_executor = get_agent_executor()
                
                # Stream the agent's steps
                for event in agent_executor.stream({"messages": messages}, config={"callbacks": global_callbacks}):
                    for key, value in event.items():
                        if key == "agent":
                            # The agent returned something
                            agent_msgs = value.get("messages", [])
                            for msg in agent_msgs:
                                # Check if agent is calling a tool
                                if getattr(msg, "tool_calls", None):
                                    for tool_call in msg.tool_calls:
                                        tool_name = tool_call.get("name")
                                        args = tool_call.get("args", {})
                                        # Temporarily print the tool call outside the progress
                                        progress.console.print(f"[bold yellow]🛠️  Calling Tool:[/] {tool_name}\n[dim]Args: {args}[/dim]")
                                        progress.update(task, description=f"[cyan]Executing {tool_name}...")
                                        
                                # If it has content, it might be the final text
                                if getattr(msg, "content", "") and not getattr(msg, "tool_calls", None):
                                    final_message = msg.content
                                    
                        elif key == "tools":
                            # A tool finished executing
                            tool_msgs = value.get("messages", [])
                            for msg in tool_msgs:
                                content_preview = str(msg.content).replace('\n', ' ')[:100]
                                progress.console.print(f"[bold green]✅ Tool '{getattr(msg, 'name', 'unknown')}' finished.[/]\n[dim]Output: {content_preview}...[/dim]")
                            progress.update(task, description="[cyan]Analyzing results...")
            
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
