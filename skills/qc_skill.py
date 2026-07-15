import os, re, urllib.request, sys
from langchain.tools import tool

@tool
def qc_article(file_path: str) -> str:
    """Simple quality‑check for an article.
    - Title line must start with '#'.
    - Minimum 300 words.
    - Must contain a line exactly 'Related reference'.
    - All URLs must return HTTP 2xx.
    Returns a short report.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        return f"✗ cannot read file: {e}"

    lines = content.splitlines()
    report = []
    # 1. title
    if lines and lines[0].lstrip().startswith('#'):
        report.append('✅ title')
    else:
        report.append('✗ title must start with #')
    # 2. word count
    words = re.findall(r"\b\w+\b", content)
    if len(words) >= 300:
        report.append('✅ word count')
    else:
        report.append(f"✗ only {len(words)} words (need >=300)")
    # 3. related reference section
    if any(line.strip().lower() == 'related reference' for line in lines):
        report.append('✅ related reference')
    else:
        report.append('✗ missing "Related reference" section')
    # 4. URL check
    urls = re.findall(r"https?://[^\s)]+", content)
    bad = []
    for u in urls:
        try:
            req = urllib.request.Request(u, method='HEAD')
            with urllib.request.urlopen(req, timeout=5) as resp:
                if not (200 <= resp.status < 300):
                    bad.append(f"{u} -> {resp.status}")
        except Exception:
            bad.append(u)
    if not bad:
        report.append('✅ all URLs reachable')
    else:
        report.append('✗ bad URLs: ' + ', '.join(bad))
    return "\n".join(report)

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print('Usage: python qc_skill.py <article_file>')
        sys.exit(1)
    print(qc_article(sys.argv[1]))
