#!/usr/bin/env python3
import sys, urllib.request, xml.etree.ElementTree as ET, pathlib

def fetch_and_save(rss_url: str = "https://news.google.com/rss/search?q=technology&hl=id&gl=ID&ceid=ID:id",
                 out_path: str = "news.txt",
                 limit: int = 10):
    try:
        data = urllib.request.urlopen(rss_url, timeout=10).read()
    except Exception as e:
        sys.exit(f"Gagal ambil RSS: {e}")
    root = ET.fromstring(data)
    lines = []
    for item in root.findall('.//item')[:limit]:
        title = item.findtext('title') or ''
        link = item.findtext('link') or ''
        lines.append(f"• {title}\n  {link}\n")
    pathlib.Path(out_path).write_text('\n'.join(lines), encoding='utf-8')

if __name__ == '__main__':
    fetch_and_save()
