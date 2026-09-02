import os
from collections import deque
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup
from langchain_core.tools import tool

@tool
def crawl(url: str, max_pages: int = 10, output_path: str = "logs/crawl-result.txt") -> str:
    """Crawl pages starting from url using BFS up to max_pages, saving visited URLs to output_path."""
    dir_name = os.path.dirname(output_path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)

    visited = []
    queue = deque([url])
    seen = {url}

    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

    while queue and len(visited) < max_pages:
        current_url = queue.popleft()
        try:
            resp = session.get(current_url, timeout=10)
            if resp.status_code != 200 or "text/html" not in resp.headers.get("Content-Type", ""):
                continue
            visited.append(current_url)

            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
                    continue
                full_url = urljoin(current_url, href)
                parsed = urlparse(full_url)
                if parsed.scheme in ("http", "https"):
                    clean_url = parsed._replace(fragment="").geturl()
                    if clean_url not in seen:
                        seen.add(clean_url)
                        queue.append(clean_url)
        except Exception:
            continue

    with open(output_path, "w", encoding="utf-8") as f:
        for item in visited:
            print(item, file=f)

    return f"Crawled {len(visited)} pages. Saved to {output_path}"

# ponytail: inline check only. upgrade to mock web server tests if crawler behavior changes.
if __name__ == "__main__":
    assert callable(crawl)
