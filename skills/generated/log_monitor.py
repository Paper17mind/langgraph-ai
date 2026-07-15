import os
import sys
import subprocess

# Asumsi decorator @tool di-import dari framework yang berjalan
def tool(func):
    return func

@tool
def start_log_monitor(log_path: str, use_telegram: bool = True, webhook_url: str = "") -> str:
    """
    Memantau log file di background dan mengirimkan output baru ke Telegram atau Webhook.
    Pastikan env TELEGRAM_BOT_TOKEN dan TELEGRAM_CHAT_ID ada.
    """
    os.makedirs("scratch", exist_ok=True)
    watcher_path = os.path.join("scratch", f"watcher_{os.path.basename(log_path)}.py")
    
    script_content = f'''import subprocess, os, json, urllib.request

log_path = "{log_path}"
use_tg = {use_telegram}
webhook = "{webhook_url}"
bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

if not os.path.exists(log_path):
    open(log_path, 'a').close()

p = subprocess.Popen(["tail", "-F", log_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
for line in iter(p.stdout.readline, b""):
    msg = line.decode().strip()
    if not msg: continue
    
    if use_tg and bot_token and chat_id:
        url = f"https://api.telegram.org/bot{{bot_token}}/sendMessage"
        data = json.dumps({{"chat_id": chat_id, "text": f"LOG:\\n{{msg}}" }}).encode()
        req = urllib.request.Request(url, data=data, headers={{"Content-Type": "application/json"}})
        try: urllib.request.urlopen(req)
        except: pass
        
    if webhook:
        data = json.dumps({{"text": msg}}).encode()
        req = urllib.request.Request(webhook, data=data, headers={{"Content-Type": "application/json"}})
        try: urllib.request.urlopen(req)
        except: pass
'''
    with open(watcher_path, "w") as f:
        f.write(script_content)
        
    subprocess.Popen([sys.executable, watcher_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return f"Monitor log jalan di background untuk: {log_path}"
