import os
import history_manager
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from agent import get_agent_executor
from langchain_core.messages import HumanMessage, AIMessage

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.message.from_user.id)
    allowed_user = os.getenv("ALLOWED_USER_ID")
    
    if allowed_user and user_id != allowed_user:
        await update.message.reply_text("Unauthorized user.")
        return

    text = update.message.text
    
    # Send "typing" action
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
    
    session_id = f"telegram_{user_id}"
    
    # Fetch history
    past_messages = history_manager.get_history(session_id, limit=10)
    messages = []
    for msg in past_messages:
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        else:
            messages.append(AIMessage(content=msg["content"]))
            
    messages.append(HumanMessage(content=text))
    
    try:
        # Get fresh agent executor (Hot Reload)
        agent_executor = get_agent_executor()
        
        # Invoke Agent
        # Note: Depending on deployment, a long agent run might block if not using async invoke (ainvoke)
        # But for simplicity we'll just run it synchronously in the handler.
        result = agent_executor.invoke({"messages": messages})
        response = result["messages"][-1].content
    except Exception as e:
        response = f"Error executing agent: {e}"
        
    # Save to history
    history_manager.add_message(session_id, "user", text)
    history_manager.add_message(session_id, "assistant", response)
        
    # Send response
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
