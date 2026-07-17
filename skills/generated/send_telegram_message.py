from smolagents import tool
import urllib.request, urllib.parse, json

@tool
def send_telegram_message(bot_token: str, chat_id: str, text: str) -> str:
    """
    Kirim pesan ke Telegram.
    Args:
        bot_token: Token bot Telegram.
        chat_id: ID chat tujuan.
        text: Isi pesan.
    """
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    data = urllib.parse.urlencode({'chat_id': chat_id, 'text': text}).encode('utf-8')
    req = urllib.request.Request(url, data=data)
    try:
        with urllib.request.urlopen(req) as response:
            return "Terkirim"
    except Exception as e:
        return f"Error: {str(e)}"
