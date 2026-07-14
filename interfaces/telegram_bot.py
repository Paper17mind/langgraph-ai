import os
import history_manager
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from router import detect_skill

# Import skills dynamically based on router output, or just import all and map them
import skills.chat_skill as chat_skill
import skills.system_skill as system_skill
import skills.scheduler_skill as scheduler_skill
import skills.http_skill as http_skill
import skills.web_search_skill as web_search_skill
import skills.coder_skill as coder_skill

SKILL_MAP = {
    "chat_skill": chat_skill,
    "system_skill": system_skill,
    "scheduler_skill": scheduler_skill,
    "http_skill": http_skill,
    "web_search_skill": web_search_skill,
    "coder_skill": coder_skill
}

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.message.from_user.id)
    allowed_user = os.getenv("ALLOWED_USER_ID")
    
    if allowed_user and user_id != allowed_user:
        await update.message.reply_text("Unauthorized user.")
        return

    text = update.message.text
    
    # Send "typing" action
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
    
    # 1. Route the intent
    skill_name = detect_skill(text)
    
    # Save User Message
    session_id = f"telegram_{user_id}"
    history_manager.add_message(session_id, "user", text)
    
    # 2. Execute the skill
    skill_module = SKILL_MAP.get(skill_name, chat_skill)
    try:
        response = skill_module.execute(text, session_id=session_id)
    except Exception as e:
        response = f"Error executing {skill_name}: {e}"
        
    # Save Assistant Response
    history_manager.add_message(session_id, "assistant", response)
        
    # 3. Send response
    # Telegram max message length is 4096
    if len(response) > 4000:
        response = response[:4000] + "\n...[truncated]"
        
    await update.message.reply_text(response, parse_mode=None)

def run_telegram_bot():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token or token == "your_telegram_bot_token_here":
        print("Please set TELEGRAM_BOT_TOKEN in .env")
        return
        
    application = Application.builder().token(token).build()
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("Starting Telegram Bot (Polling)...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)
