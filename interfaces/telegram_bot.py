import os
import asyncio
from core import history_manager
from core import scheduler_db
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from core.agent_graph import get_agent_executor
from langchain_core.messages import HumanMessage, AIMessage

user_sessions = {}
user_projects = {}

async def check_auth(update: Update) -> bool:
    user_id = str(update.message.from_user.id)
    allowed_user = os.getenv("ALLOWED_USER_ID")
    if allowed_user and user_id != allowed_user:
        await update.message.reply_text("Unauthorized user.")
        return False
    return True

async def cmd_project(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_auth(update): return
    user_id = str(update.message.from_user.id)
    args = context.args
    if args:
        new_proj = args[0].lower()
        user_projects[user_id] = new_proj
        await update.message.reply_text(f"✅ Proyek aktif disetel ke: {new_proj}")
    else:
        # List projects
        import os
        proj_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "projects")
        if os.path.exists(proj_dir):
            projs = [d for d in os.listdir(proj_dir) if os.path.isdir(os.path.join(proj_dir, d))]
            if projs:
                response = "📁 Daftar Proyek:\n" + "\n".join(f"- {p}" for p in projs)
                response += "\n\nGunakan /project <nama> untuk memilih."
                await update.message.reply_text(response)
            else:
                await update.message.reply_text("Belum ada proyek yang dibuat.")
        else:
            await update.message.reply_text("Folder projects/ belum ada.")

async def cmd_session(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_auth(update): return
    user_id = str(update.message.from_user.id)
    args = context.args
    if args:
        new_session = args[0].lower()
        user_sessions[user_id] = new_session
        await update.message.reply_text(f"✅ Berpindah ke sesi (konteks): {new_session}")
    else:
        # List sessions
        prefix = f"telegram_{user_id}_"
        sessions = history_manager.get_all_sessions(prefix)
        if sessions:
            active_session = user_sessions.get(user_id, "default")
            response = "📂 Daftar Sesi Obrolan:\n"
            for s in sessions:
                marker = " *(aktif)" if s == active_session else ""
                response += f"- {s}{marker}\n"
            response += "\nGunakan /session <nama> untuk memilih."
            await update.message.reply_text(response)
        else:
            await update.message.reply_text("Belum ada sesi yang terekam.")

async def cmd_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_auth(update): return
    args = context.args
    if args:
        new_model = args[0]
        os.environ["9ROUTER_MODEL"] = new_model
        await update.message.reply_text(f"✅ Model diubah menjadi: {new_model}")
    else:
        await update.message.reply_text("⚠️ Gunakan format: /model <nama_model>")

async def cmd_memory(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_auth(update): return
    import sys
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from utils.memory_db import memory_db
    facts = memory_db.get_all_facts()
    if not facts:
        await update.message.reply_text("Memori (ChromaDB) saat ini kosong.")
    else:
        response = "🧠 Long-Term Memory (ChromaDB):\n\n" + "\n".join(f"- {f}" for f in facts)
        # Handle long responses if memory is huge
        if len(response) > 4000:
            response = response[:4000] + "\n...[truncated]"
        await update.message.reply_text(response)

async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_auth(update): return
    user_id = str(update.message.from_user.id)
    active_session = user_sessions.get(user_id, "default")
    session_id = f"telegram_{user_id}_{active_session}"
    history_manager.clear_history(session_id)
    await update.message.reply_text(f"✅ Riwayat chat untuk sesi '{active_session}' telah dihapus dari database lokal.")

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_auth(update): return
    help_text = (
        "**Daftar Perintah (Slash Commands):**\n"
        "- `/register <path>` : Daftarkan project untuk dipantau AI Maintainer.\n"
        "- `/projects` : Daftar seluruh project yang terdaftar dan statusnya.\n"
        "- `/audit <nama>` : Jalankan audit CVE runtime, dependensi, dan SAST kode.\n"
        "- `/project [nama]` : Memilih proyek aktif atau melihat daftar proyek.\n"
        "- `/session <nama_sesi>` : Berpindah ke ruang/konteks obrolan yang berbeda.\n"
        "- `/model <nama_model>` : Mengubah model LLM yang digunakan secara real-time.\n"
        "- `/memory` : Menampilkan seluruh isi memori jangka panjang (ChromaDB).\n"
        "- `/clear` : Membersihkan riwayat chat pada sesi yang sedang aktif.\n"
        "- `/help` : Menampilkan pesan bantuan ini.\n"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def cmd_projects(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_auth(update): return
    from skills.maintainer_skill import list_registered_projects
    msg = list_registered_projects.invoke({})
    await update.message.reply_text(msg, parse_mode="Markdown")

async def cmd_audit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_auth(update): return
    args = context.args
    if not args:
        await update.message.reply_text("Penggunaan: /audit <nama_project>\nContoh: /audit my-app")
        return
    proj_name = args[0]
    await update.message.reply_text(f"⏳ Sedang menjalankan audit komprehensif untuk `{proj_name}`...", parse_mode="Markdown")
    from skills.maintainer_skill import audit_project
    report = await asyncio.to_thread(audit_project.invoke, {"project_name": proj_name})
    if len(report) > 4000:
        report = report[:4000] + "\n...[dipotong karena batas pesan Telegram]"
    try:
        await update.message.reply_text(report, parse_mode="Markdown")
    except Exception:
        await update.message.reply_text(report, parse_mode=None)

async def cmd_register(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_auth(update): return
    args = context.args
    if not args:
        await update.message.reply_text("Penggunaan: /register <path_project> [nama_opsional]\nContoh: /register /var/www/projects/my-api")
        return
    path_target = args[0]
    name_target = args[1] if len(args) > 1 else None
    await update.message.reply_text(f"⏳ Memindai dan mendaftarkan `{path_target}`...", parse_mode="Markdown")
    from skills.maintainer_skill import register_project
    res = await asyncio.to_thread(register_project.invoke, {"project_path": path_target, "custom_name": name_target})
    await update.message.reply_text(res, parse_mode="Markdown")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_auth(update): return
    
    text = update.message.text
    user_id = str(update.message.from_user.id)
    
    # Session ID is just the user ID for simplicity in telegram
    session_id = user_sessions.get(user_id, f"tg_{user_id}")
    active_project = user_projects.get(user_id, None)
    
    # Inject current session ID and chat ID for tools (like scheduler)
    os.environ["CURRENT_SESSION_ID"] = session_id
    os.environ["CURRENT_CHAT_ID"] = user_id
    
    # Show typing indicator
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
    
    # Format history — use smart sliding window for token efficiency
    history_limit = int(os.getenv("HISTORY_LIMIT", "4"))
    history = history_manager.get_smart_history(session_id, recent_count=history_limit)
    messages = []
    for msg in history:
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "system":
            # Summary block from older messages — inject as AI context
            messages.append(AIMessage(content=msg["content"]))
        else:
            messages.append(AIMessage(content=msg["content"]))
            
    messages.append(HumanMessage(content=text))
    
    try:
        from core.agent_graph import global_callbacks
        agent_executor = get_agent_executor(active_project=active_project, user_query=text)
        
        recursion_limit = int(os.getenv("RECURSION_LIMIT", "20"))
        config = {
            "callbacks": global_callbacks,
            "configurable": {"thread_id": session_id, "chat_id": user_id},
            "recursion_limit": recursion_limit,
        }
        
        # Non-blocking async execution: run agent_executor.invoke off the asyncio loop
        def _run_agent():
            return agent_executor.invoke({"messages": messages}, config=config)
            
        result = await asyncio.to_thread(_run_agent)
        final_message = ""
        if result and "messages" in result and result["messages"]:
            last_m = result["messages"][-1]
            final_message = getattr(last_m, "content", "")
            
        if not final_message:
            final_message = "⚠️ Maaf, agent tidak memberikan respons (pesan kosong). Silakan coba lagi."
        response = final_message
    except Exception as e:
        response = f"Error executing agent: {e}"
    # Save to history
    await asyncio.to_thread(history_manager.add_message, session_id, "user", text)
    await asyncio.to_thread(history_manager.add_message, session_id, "assistant", response)
    # Send response
    # Telegram max message length is 4096
    if len(response) > 4000:
        response = response[:4000] + "\n...[truncated]"
        
    try:
        await update.message.reply_text(response, parse_mode="Markdown")
    except Exception:
        # Fallback to plain text if Markdown parsing fails (e.g. unclosed tags)
        await update.message.reply_text(response, parse_mode=None)
async def check_schedules_job(context: ContextTypes.DEFAULT_TYPE):
    """Background job to check and trigger scheduled tasks."""
    pending_tasks = scheduler_db.get_pending_schedules()
    for task in pending_tasks:
        try:
            # Task session_id might be "tg_12345", extract numeric ID if needed
            chat_id = task["session_id"].replace("tg_", "")
            message = f"⏰ <b>PENGINGAT OTOMATIS:</b>\n\n{task['task']}"
            await context.bot.send_message(chat_id=chat_id, text=message, parse_mode="HTML")
            scheduler_db.mark_schedule_done(task["id"])
        except Exception as e:
            print(f"Failed to send scheduled task {task['id']}: {e}")

def run_telegram_bot():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token or token == "your_telegram_bot_token_here":
        print("Please set TELEGRAM_BOT_TOKEN in .env")
        return
        
    application = Application.builder().token(token).build()
    
    # Register Slash Commands
    application.add_handler(CommandHandler("register", cmd_register))
    application.add_handler(CommandHandler("projects", cmd_projects))
    application.add_handler(CommandHandler("audit", cmd_audit))
    application.add_handler(CommandHandler("project", cmd_project))
    application.add_handler(CommandHandler("session", cmd_session))
    application.add_handler(CommandHandler("model", cmd_model))
    application.add_handler(CommandHandler("memory", cmd_memory))
    application.add_handler(CommandHandler("clear", cmd_clear))
    application.add_handler(CommandHandler("help", cmd_help))
    
    # Register normal text handler
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Register background scheduler poller
    application.job_queue.run_repeating(check_schedules_job, interval=10, first=5)
    
    print("Starting Telegram Bot (Polling)...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)
