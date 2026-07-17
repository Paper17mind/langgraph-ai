from smolagents import tool
import urllib.request, json, os

@tool
def send_stock_movers_to_telegram(count: int = 3) -> str:
    """Fetches top stock gainers and sends them to Telegram.
    Args:
        count: Number of top stocks to fetch.
    """
    url = f"https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?scrIds=day_gainers&count={count}"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        res = json.loads(urllib.request.urlopen(req).read())
        quotes = res['finance']['result'][0]['quotes']
        msg = "Top Saham:\n" + "\n".join([f"{q['symbol']}: {q['regularMarketChangePercent']:.2f}%" for q in quotes])
    except Exception as e:
        return f"Gagal fetch saham: {e}"

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "8658152540:AAE0KIxEENQHBLAB6fWo7Om8bMhj4Aslr_U")
    chat_id = os.environ.get("ALLOWED_USER_ID", "8351384218")
    
    tg_url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = json.dumps({"chat_id": chat_id, "text": msg}).encode('utf-8')
    tg_req = urllib.request.Request(tg_url, data=data, headers={'Content-Type': 'application/json'})
    try:
        urllib.request.urlopen(tg_req)
        return "Berhasil kirim ke Telegram."
    except Exception as e:
        return f"Gagal kirim telegram: {e}"
