"""
Lightweight symbol indexer and vulnerability/bug inspector.
Indexed symbols: routes, controllers, functions, classes (fast regex/ast, zero heavy embeddings).
Checks: CVE OSV.dev batch queries, runtime CVE alerts, and SAST code quality bugs.
"""
import os
import re
import ast
import json
import urllib.request
import urllib.error
from typing import Dict, Any, List, Optional, Tuple

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; AIMaintainer/1.0; +https://github.com/Paper17mind/langgraph-ai)"
}

# ─────────────────────────────────────────────────────────────────────────────
# 1. Lightweight Code Indexer
# ─────────────────────────────────────────────────────────────────────────────

def index_code_symbols(root_dir: str, max_files: int = 200) -> List[Dict[str, Any]]:
    """
    Scan source files (Python, JS/TS, PHP) and extract classes, functions, routes.
    Fast, deterministic, and lightweight.
    """
    symbols = []
    scanned_count = 0

    re_php_fn = re.compile(r"^\s*(?:public|protected|private|static)?\s*function\s+([a-zA-Z0-9_]+)\s*\(", re.MULTILINE)
    re_php_cls = re.compile(r"^\s*(?:abstract|final)?\s*class\s+([a-zA-Z0-9_]+)", re.MULTILINE)
    re_php_route = re.compile(r"Route::(get|post|put|patch|delete)\s*\(\s*['\"]([^'\"]+)['\"]", re.IGNORECASE)

    re_js_fn = re.compile(r"(?:function\s+([a-zA-Z0-9_]+)\s*\(|(?:const|let|var)\s+([a-zA-Z0-9_]+)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>)", re.MULTILINE)
    re_js_cls = re.compile(r"class\s+([a-zA-Z0-9_]+)", re.MULTILINE)
    re_js_route = re.compile(r"(?:app|router)\.(get|post|put|patch|delete)\s*\(\s*['\"]([^'\"]+)['\"]", re.IGNORECASE)

    for current_dir, dirs, files in os.walk(root_dir):
        dirs[:] = [d for d in dirs if d not in {"node_modules", "vendor", ".git", ".venv", "venv", "__pycache__", "dist", "build", "coverage"}]
        
        for f in files:
            if scanned_count >= max_files:
                break

            file_ext = os.path.splitext(f)[1].lower()
            if file_ext not in {".py", ".js", ".ts", ".php"}:
                continue

            full_path = os.path.join(current_dir, f)
            rel_path = os.path.relpath(full_path, root_dir)
            scanned_count += 1

            try:
                with open(full_path, "r", encoding="utf-8", errors="ignore") as src:
                    content = src.read()
            except Exception:
                continue

            # Python AST parsing
            if file_ext == ".py":
                try:
                    tree = ast.parse(content)
                    for node in ast.walk(tree):
                        if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                            symbols.append({
                                "file_rel_path": rel_path,
                                "symbol_type": "function",
                                "symbol_name": node.name,
                                "line_no": getattr(node, "lineno", 1),
                            })
                        elif isinstance(node, ast.ClassDef):
                            symbols.append({
                                "file_rel_path": rel_path,
                                "symbol_type": "class",
                                "symbol_name": node.name,
                                "line_no": getattr(node, "lineno", 1),
                            })
                except Exception:
                    pass

            # PHP regex parsing
            elif file_ext == ".php":
                for m in re_php_cls.finditer(content):
                    symbols.append({
                        "file_rel_path": rel_path,
                        "symbol_type": "class",
                        "symbol_name": m.group(1),
                        "line_no": content[:m.start()].count("\n") + 1,
                    })
                for m in re_php_fn.finditer(content):
                    symbols.append({
                        "file_rel_path": rel_path,
                        "symbol_type": "function",
                        "symbol_name": m.group(1),
                        "line_no": content[:m.start()].count("\n") + 1,
                    })
                for m in re_php_route.finditer(content):
                    symbols.append({
                        "file_rel_path": rel_path,
                        "symbol_type": "route",
                        "symbol_name": f"{m.group(1).upper()} {m.group(2)}",
                        "line_no": content[:m.start()].count("\n") + 1,
                    })

            # JS/TS regex parsing
            elif file_ext in {".js", ".ts"}:
                for m in re_js_cls.finditer(content):
                    symbols.append({
                        "file_rel_path": rel_path,
                        "symbol_type": "class",
                        "symbol_name": m.group(1),
                        "line_no": content[:m.start()].count("\n") + 1,
                    })
                for m in re_js_fn.finditer(content):
                    name = m.group(1) or m.group(2)
                    if name:
                        symbols.append({
                            "file_rel_path": rel_path,
                            "symbol_type": "function",
                            "symbol_name": name,
                            "line_no": content[:m.start()].count("\n") + 1,
                        })
                for m in re_js_route.finditer(content):
                    symbols.append({
                        "file_rel_path": rel_path,
                        "symbol_type": "route",
                        "symbol_name": f"{m.group(1).upper()} {m.group(2)}",
                        "line_no": content[:m.start()].count("\n") + 1,
                    })

    return symbols


# ─────────────────────────────────────────────────────────────────────────────
# 2. Dependency CVE Inspector (OSV.dev Batch Query)
# ─────────────────────────────────────────────────────────────────────────────

def _map_ecosystem_to_osv(eco: str) -> str:
    eco_lower = eco.lower()
    if eco_lower == "php":
        return "Packagist"
    if eco_lower == "node":
        return "npm"
    if eco_lower == "python":
        return "PyPI"
    if eco_lower == "go":
        return "Go"
    return ""


def clean_version_for_osv(ver_spec: str) -> Optional[str]:
    """Extract clean semver from spec like ^1.2.3, >=2.0.0, ==1.0.4."""
    if not ver_spec:
        return None
    m = re.search(r"(\d+\.\d+(?:\.\d+)?)", ver_spec)
    return m.group(1) if m else None


def query_osv_vulnerabilities(dependencies: List[Dict[str, Any]], ecosystem: str) -> List[Dict[str, Any]]:
    """
    Batch query OSV.dev API for open source vulnerabilities.
    Falls back gracefully on network or API limits.
    """
    osv_eco = _map_ecosystem_to_osv(ecosystem)
    if not osv_eco:
        return []

    queries = []
    dep_map = {}
    for dep in dependencies[:40]:  # Limit query batch size for speed
        pkg = dep["package"]
        ver = clean_version_for_osv(dep.get("version", ""))
        q = {"package": {"name": pkg, "ecosystem": osv_eco}}
        if ver:
            q["version"] = ver
        queries.append(q)
        dep_map[len(queries) - 1] = dep

    if not queries:
        return []

    try:
        req = urllib.request.Request(
            "https://api.osv.dev/v1/querybatch",
            data=json.dumps({"queries": queries}).encode("utf-8"),
            headers={"Content-Type": "application/json", **HEADERS},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        vulns = []
        results = data.get("results", [])
        for i, res in enumerate(results):
            vuln_list = res.get("vulns", [])
            if vuln_list:
                origin_dep = dep_map.get(i, {})
                for v in vuln_list[:2]:
                    vulns.append({
                        "package": origin_dep.get("package"),
                        "current_version": origin_dep.get("version"),
                        "cve_id": v.get("id"),
                        "summary": v.get("summary") or v.get("details", "")[:120].replace("\n", " "),
                        "severity": (v.get("database_specific", {}).get("severity") or "HIGH").upper(),
                    })
        return vulns
    except Exception:
        return []


# ─────────────────────────────────────────────────────────────────────────────
# 3. Runtime Version & SAST Code Bug Inspector
# ─────────────────────────────────────────────────────────────────────────────

KNOWN_RUNTIME_CVES = [
    {
        "runtime": "php",
        "vuln_versions": [("<", "8.1.29"), ("<", "8.2.20"), ("<", "8.3.8")],
        "cve": "CVE-2024-4577",
        "title": "PHP CGI Argument Injection (RCE Risk)",
        "recommendation": "Upgrade PHP runtime ke versi patched (>=8.1.29, >=8.2.20, atau >=8.3.8).",
    },
    {
        "runtime": "php",
        "vuln_versions": [("<", "8.0.0")],
        "cve": "EOL-PHP",
        "title": "PHP End-Of-Life Unsupported Runtime",
        "recommendation": "PHP versi < 8.0 sudah mencapai EOL dan tidak menerima patch keamanan resmi.",
    },
]


def _compare_semver_less(ver_a: str, ver_b: str) -> bool:
    """Compare two semantic versions: returns True if ver_a < ver_b."""
    try:
        p_a = [int(x) for x in re.findall(r"\d+", ver_a)[:3]]
        p_b = [int(x) for x in re.findall(r"\d+", ver_b)[:3]]
        while len(p_a) < 3: p_a.append(0)
        while len(p_b) < 3: p_b.append(0)
        return p_a < p_b
    except Exception:
        return False


def check_runtime_vulnerabilities(runtime_spec: Optional[str], host_runtimes: Dict[str, Optional[str]]) -> List[Dict[str, Any]]:
    """Check if project runtime target or active host runtime matches known dangerous CVEs."""
    alerts = []
    
    # Check PHP
    php_ver = None
    if runtime_spec and "php" in runtime_spec.lower():
        php_ver = clean_version_for_osv(runtime_spec)
    elif host_runtimes.get("php"):
        php_ver = host_runtimes["php"]

    if php_ver:
        for r_cve in KNOWN_RUNTIME_CVES:
            if r_cve["runtime"] == "php":
                for op, bound in r_cve["vuln_versions"]:
                    if op == "<" and _compare_semver_less(php_ver, bound):
                        alerts.append({
                            "cve_id": r_cve["cve"],
                            "title": f"{r_cve['title']} on PHP {php_ver}",
                            "severity": "CRITICAL" if "RCE" in r_cve["title"] else "HIGH",
                            "recommendation": r_cve["recommendation"],
                        })
                        break

    return alerts


def scan_source_bugs(target_dir: str, max_files: int = 100) -> List[Dict[str, Any]]:
    """Scan local files for dangerous bugs (SQLi, command injection, hardcoded secrets)."""
    bug_alerts = []
    scanned = 0

    patterns = [
        (re.compile(r"""(?i)(?:api[_-]?key|secret[_-]?key|auth[_-]?token)\s*[:=]\s*['"][a-zA-Z0-9_\-]{20,}['"]"""), "CRITICAL", "Hardcoded Secret / API Key"),
        (re.compile(r"""(?i)SELECT\s+.*\s+FROM\s+.*\s*\+\s*|\$_(?:GET|POST|REQUEST)\[.*\]\s*\.\s*"""), "HIGH", "Potential SQL Injection Concatenation"),
        (re.compile(r"""(?i)(?:shell_exec|passthru|system)\s*\("""), "HIGH", "Direct System Command Execution (RCE risk)"),
        (re.compile(r"""(?i)subprocess\.(?:run|Popen|call)\(.*shell\s*=\s*True"""), "MEDIUM", "Subprocess with shell=True"),
    ]

    for current_dir, dirs, files in os.walk(target_dir):
        dirs[:] = [d for d in dirs if d not in {"node_modules", "vendor", ".git", ".venv", "venv", "__pycache__", "dist"}]
        for f in files:
            if scanned >= max_files:
                break
            ext = os.path.splitext(f)[1].lower()
            if ext not in {".py", ".php", ".js", ".ts"}:
                continue

            full_path = os.path.join(current_dir, f)
            rel_path = os.path.relpath(full_path, target_dir)
            scanned += 1

            try:
                with open(full_path, "r", encoding="utf-8", errors="ignore") as fp:
                    for line_idx, line in enumerate(fp, 1):
                        for p, sev, desc in patterns:
                            if p.search(line):
                                bug_alerts.append({
                                    "severity": sev,
                                    "title": f"{desc} in {rel_path}:{line_idx}",
                                    "file": rel_path,
                                    "line": line_idx,
                                    "snippet": line.strip()[:100],
                                })
            except Exception:
                continue

    return bug_alerts
