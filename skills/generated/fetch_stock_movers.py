import urllib.request
import json

# Asumsi menggunakan decorator @tool bawaan sistem
def tool(func):
    return func

@tool
def fetch_stock_movers(category: str = "day_gainers", count: int = 3) -> str:
    """
    Fetch top stock movers dari Yahoo Finance.
    Args:
        category: Kategori saham ('day_gainers' atau 'day_losers').
        count: Jumlah saham.
    """
    url = f"https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?scrIds={category}&count={count}"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        res = json.loads(urllib.request.urlopen(req).read())
        quotes = res['finance']['result'][0]['quotes']
        return ", ".join([f"{q['symbol']} ({q['regularMarketChangePercent']:.2f}%)" for q in quotes])
    except Exception as e:
        return f"Error: {str(e)}"