import os
import json
from fastapi import FastAPI, Request
from dotenv import load_dotenv
import telebot
from langchain_core.messages import HumanMessage

# Load tools and agent
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agent import get_agent_executor

load_dotenv()

app = FastAPI(title="AI Telebot Webhook Receiver")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_USER_ID = os.getenv("ALLOWED_USER_ID")

if BOT_TOKEN:
    bot = telebot.TeleBot(BOT_TOKEN)
else:
    bot = None

@app.post("/webhook/{source}")
async def receive_webhook(source: str, request: Request):
    """
    Menerima webhook dari sistem eksternal (misal: trello, github)
    dan menyuruh agen AI untuk merangkum serta mengirimkannya ke Telegram.
    """
    try:
        # Get raw payload
        body_bytes = await request.body()
        payload = body_bytes.decode('utf-8')
        
        # Build prompt for AI
        prompt = (
            f"Kamu menerima WEBHOOK otomatis dari sistem '{source}'.\n"
            f"Ini adalah payload datanya: {payload}\n\n"
            f"Tugasmu: Analisa data tersebut, buatlah ringkasan yang jelas dan mudah dibaca manusia "
            f"tentang apa yang terjadi (misal: kartu baru dibuat, ada error, dll), "
            f"dan balas pesan ini dengan ringkasan tersebut."
        )
        
        # Invoke agent
        messages = [HumanMessage(content=prompt)]
        # Get fresh agent executor (Hot Reload)
        agent_executor = get_agent_executor()
        result = agent_executor.invoke({"messages": messages})
        
        ai_response = result["messages"][-1].content
        
        # Send proactive notification to Telegram
        if bot and ALLOWED_USER_ID:
            # Menggunakan parse_mode Markdown agar hasil dari AI terlihat rapi
            bot.send_message(ALLOWED_USER_ID, f"🔔 **Webhook Alert ({source})**\n\n{ai_response}", parse_mode="Markdown")
            
        return {"status": "success", "message": "Webhook processed and sent to Telegram"}
        
    except Exception as e:
        if bot and ALLOWED_USER_ID:
            bot.send_message(ALLOWED_USER_ID, f"⚠️ Webhook error dari '{source}': {str(e)}")
        return {"status": "error", "message": str(e)}

def run_webhook_server(host="0.0.0.0", port=8000):
    import uvicorn
    print(f"🚀 Menyalakan Webhook Server di http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)

if __name__ == "__main__":
    run_webhook_server()
