import os
import sys
import ssl
import socket
import re
import json
import shutil
import tempfile
import subprocess
from urllib.parse import urlparse
from datetime import datetime
import requests
from langchain.tools import tool

# Add root directory to sys.path to import utils
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.text_helper import truncate_or_save

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# Suppress urllib3 InsecureRequestWarning when probing security endpoints
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

@tool
def audit_web_security(url: str) -> str:
    """Audit web security for a URL: security headers, CORS, sensitive exposed files (.env/.git), and SSL status."""
    clean_url = url.strip()
    if not clean_url.startswith("http://") and not clean_url.startswith("https://"):
        clean_url = "https://" + clean_url

    parsed = urlparse(clean_url)
    hostname = parsed.hostname or clean_url
    scheme = parsed.scheme
    port = parsed.port or (443 if scheme == "https" else 80)

    report_lines = [f"🛡️ **Web Security Audit Report**: `{clean_url}`\n"]

    # 1. Fetch main URL response
    try:
        res = requests.get(clean_url, headers=HEADERS, timeout=10, allow_redirects=True, verify=False)
        headers = res.headers
    except Exception as e:
        return f"❌ Failed to connect to {clean_url}: {e}"

    # 2. Security Headers Evaluation
    recommended_headers = {
        "Strict-Transport-Security": "Protects against SSL-stripping / downgrade attacks (HSTS).",
        "Content-Security-Policy": "Prevents Cross-Site Scripting (XSS) and data injection.",
        "X-Frame-Options": "Prevents Clickjacking attacks by controlling iframe embeds.",
        "X-Content-Type-Options": "Prevents MIME-type sniffing (nosniff).",
        "Referrer-Policy": "Controls information passed in the Referer header.",
        "Permissions-Policy": "Restricts browser features like camera, microphone, geolocation."
    }

    present_headers = []
    missing_headers = []

    for h_name, desc in recommended_headers.items():
        val = headers.get(h_name)
        if val:
            present_headers.append(f"• ✅ `{h_name}`: `{val}`")
        else:
            missing_headers.append(f"• ❌ `{h_name}` (Missing): {desc}")

    score = round((len(present_headers) / len(recommended_headers)) * 100)
    grade = "A+" if score >= 90 else "A" if score >= 80 else "B" if score >= 60 else "C" if score >= 40 else "F"

    report_lines.append(f"📊 **Security Headers Score: {score}% (Grade: {grade})**")
    if present_headers:
        report_lines.append("\n**Implemented Headers:**\n" + "\n".join(present_headers))
    if missing_headers:
        report_lines.append("\n**Missing Headers (Vulnerabilities/Recommendations):**\n" + "\n".join(missing_headers))

    # 3. Information Disclosure (Server / Technology banner)
    info_leaks = []
    for h in ["Server", "X-Powered-By", "X-AspNet-Version", "X-Generator"]:
        if h in headers:
            info_leaks.append(f"`{h}: {headers[h]}`")

    report_lines.append("\n🔍 **Information Disclosure / Fingerprinting:**")
    if info_leaks:
        report_lines.append("• ⚠️ Server membocorkan versi/teknologi software:")
        for leak in info_leaks:
            report_lines.append(f"  - {leak}")
        report_lines.append("  *Saran: Sembunyikan header 'Server' & 'X-Powered-By' di konfigurasi web server (Nginx/Apache/Cloudflare).*")
    else:
        report_lines.append("• ✅ Bersih! Tidak ada header server/framework yang bocor.")

    # 4. CORS Misconfiguration Check
    cors_origin = headers.get("Access-Control-Allow-Origin")
    cors_creds = headers.get("Access-Control-Allow-Credentials")
    report_lines.append("\n🌐 **CORS Configuration:**")
    if cors_origin == "*" and cors_creds == "true":
        report_lines.append("• 🔴 **CRITICAL CORS VULNERABILITY**: `Access-Control-Allow-Origin: *` aktif bersama `Allow-Credentials: true`!")
    elif cors_origin == "*":
        report_lines.append("• ⚠️ `Access-Control-Allow-Origin: *` (Akses publik terbuka untuk semua origin).")
    elif cors_origin:
        report_lines.append(f"• ✅ CORS dibatasi ke: `{cors_origin}`")
    else:
        report_lines.append("• ✅ CORS default (Origin tidak dibuka secara longgar).")

    # 5. Exposed Sensitive Files Check
    report_lines.append("\n📂 **Sensitive Endpoints Exposure Check:**")
    sensitive_paths = [
        ("/.env", "Environment configuration file containing credentials"),
        ("/.git/HEAD", "Exposed Git repository metadata"),
        ("/robots.txt", "Robots crawler file (review for hidden paths)"),
        ("/phpinfo.php", "PHP diagnostic file leaking server config"),
        ("/.well-known/security.txt", "Security vulnerability contact policy")
    ]

    base_origin = f"{parsed.scheme}://{parsed.netloc}"
    exposed_finds = []

    for path, note in sensitive_paths:
        target_path_url = base_origin + path
        try:
            chk = requests.get(target_path_url, headers=HEADERS, timeout=4, verify=False, allow_redirects=False)
            if chk.status_code == 200:
                body_sample = chk.text[:100].lower()
                if path == "/.env" and ("app_key" in body_sample or "db_" in body_sample or "=" in body_sample):
                    exposed_finds.append(f"• 🔴 **CRITICAL**: `{path}` TERBUKA! (Status 200 - File konfigurasi rahasia terekspos)")
                elif path == "/.git/HEAD" and "ref: refs/" in body_sample:
                    exposed_finds.append(f"• 🔴 **CRITICAL**: `{path}` TERBUKA! (Status 200 - Source code git dapat didownload)")
                elif path == "/phpinfo.php" and ("php version" in body_sample or "phpinfo()" in body_sample):
                    exposed_finds.append(f"• ⚠️ `{path}` TERBUKA! (Status 200 - Informasi detail PHP terekspos)")
                elif path == "/robots.txt":
                    exposed_finds.append(f"• ℹ️ `{path}` ditemukan (Status 200 - Silakan tinjau daftar Disallow).")
                elif path == "/.well-known/security.txt":
                    exposed_finds.append(f"• ✅ `{path}` ditemukan (Praktik kepatuhan keamanan yang baik).")
        except Exception:
            pass

    if exposed_finds:
        report_lines.extend(exposed_finds)
    else:
        report_lines.append("• ✅ Tidak ditemukan file sensitif umum (.env, .git) yang terbuka.")

    # 6. SSL/TLS Certificate Check
    if scheme == "https":
        report_lines.append("\n🔒 **SSL/TLS Certificate Status:**")
        try:
            ctx = ssl.create_default_context()
            with socket.create_connection((hostname, port), timeout=5) as sock:
                with ctx.wrap_socket(sock, server_hostname=hostname) as ssock:
                    cert = ssock.getpeercert()
                    not_after_str = cert.get("notAfter")
                    if not_after_str:
                        expire_date = datetime.strptime(not_after_str, "%b %d %H:%M:%S %Y %Z")
                        days_left = (expire_date - datetime.utcnow()).days
                        subject = dict(x[0] for x in cert.get("subject", []))
                        common_name = subject.get("commonName", hostname)
                        
                        if days_left < 0:
                            report_lines.append(f"• 🔴 **EXPIRED**: Sertifikat SSL telah kedaluwarsa {abs(days_left)} hari yang lalu!")
                        elif days_left < 15:
                            report_lines.append(f"• ⚠️ **WARNING**: Sertifikat SSL akan kedaluwarsa dalam {days_left} hari! ({expire_date.strftime('%Y-%m-%d')})")
                        else:
                            report_lines.append(f"• ✅ Sertifikat Valid: `{common_name}` (Sisa masa aktif: {days_left} hari, hingga {expire_date.strftime('%Y-%m-%d')})")
        except Exception as ssl_err:
            report_lines.append(f"• ⚠️ Peringatan SSL: {ssl_err}")

    final_report = "\n".join(report_lines)
    return truncate_or_save(final_report, max_length=2500, context_name="web_security")


@tool
def scan_local_code_security(path: str) -> str:
    """Scan local code files or directory for vulnerabilities (SAST): SQL injection, hardcoded secrets, and dangerous functions."""
    target_path = os.path.abspath(path.strip().strip("'").strip('"'))
    if not os.path.exists(target_path):
        return f"Path `{target_path}` does not exist."

    results = [f"🛡️ **Local Code Security Audit Report**: `{target_path}`\n"]

    # 1. Run Bandit if Python file or directory containing Python files
    is_py = target_path.endswith(".py") or os.path.isdir(target_path)
    bandit_bin = shutil.which("bandit") or "/home/papermind/.local/bin/bandit" or "/home/papermind/.pyenv/shims/bandit"

    if is_py and bandit_bin and os.path.exists(bandit_bin):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            tmp_json = tmp.name

        cmd = [bandit_bin, "-r" if os.path.isdir(target_path) else target_path, "-f", "json", "-o", tmp_json, "-q"]
        if os.path.isdir(target_path):
            cmd.extend([target_path, "-x", ".venv,node_modules,vendor,.git,__pycache__"])

        try:
            subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if os.path.exists(tmp_json) and os.path.getsize(tmp_json) > 0:
                with open(tmp_json, "r", encoding="utf-8") as f:
                    b_data = json.load(f)

                b_issues = b_data.get("results", [])
                metrics = b_data.get("metrics", {}).get("_totals", {})
                high = metrics.get("SEVERITY.HIGH", 0)
                med = metrics.get("SEVERITY.MEDIUM", 0)
                low = metrics.get("SEVERITY.LOW", 0)

                results.append(f"🐍 **Bandit Python Security Scanner:**")
                results.append(f"• Temuan Kerentanan: **{high} High**, **{med} Medium**, **{low} Low** ({len(b_issues)} total isu)")

                for issue in b_issues[:8]:
                    sev = issue.get("issue_severity")
                    text = issue.get("issue_text")
                    fname = os.path.basename(issue.get("filename", ""))
                    line_no = issue.get("line_number")
                    sev_icon = "🔴" if sev == "HIGH" else "🟠" if sev == "MEDIUM" else "🟡"
                    results.append(f"  {sev_icon} [{sev}] `{fname}:{line_no}`: {text}")

                if len(b_issues) > 8:
                    results.append(f"  ... dan {len(b_issues) - 8} temuan lainnya.")
        except Exception:
            pass
        finally:
            if os.path.exists(tmp_json):
                try:
                    os.remove(tmp_json)
                except Exception:
                    pass

    # 2. Multi-language Heuristics SAST (Secret scanning & Dangerous patterns)
    results.append("\n🔑 **Pattern-Based Secret & Vulnerability Inspection:**")
    patterns = [
        (re.compile(r"""(?i)(?:api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token|app[_-]?secret)\s*[:=]\s*['"][a-zA-Z0-9_\-]{16,}['"]"""), "Hardcoded Secret / API Key"),
        (re.compile(r"""(?i)(?:password|passwd|pwd)\s*[:=]\s*['"][^'"]{4,}['"]"""), "Hardcoded Password"),
        (re.compile(r"""(?i)SELECT\s+.*\s+FROM\s+.*\s*\+\s*|\$_(?:GET|POST|REQUEST)\[.*\]\s*\.\s*"""), "Potential SQL Injection Concatenation"),
        (re.compile(r"""(?i)\b(?:eval|exec)\s*\("""), "Dangerous Dynamic Code Execution (eval/exec)"),
        (re.compile(r"""(?i)(?:shell_exec|passthru|system)\s*\("""), "Direct System Command Execution (PHP/RCE risk)"),
        (re.compile(r"""(?i)subprocess\.(?:run|Popen|call)\(.*shell\s*=\s*True"""), "Subprocess with shell=True (Command Injection risk)")
    ]

    files_to_scan = []
    if os.path.isfile(target_path):
        files_to_scan.append(target_path)
    else:
        for root, dirs, files in os.walk(target_path):
            dirs[:] = [d for d in dirs if d not in [".git", "node_modules", "vendor", ".venv", "__pycache__", "dist"]]
            for f in files:
                if f.endswith((".py", ".php", ".js", ".ts", ".env", ".json", ".go")):
                    files_to_scan.append(os.path.join(root, f))

    pattern_findings = []
    for fpath in files_to_scan[:60]: # Limit scan up to 60 files
        rel_f = os.path.relpath(fpath, target_path) if os.path.isdir(target_path) else os.path.basename(fpath)
        try:
            with open(fpath, "r", encoding="utf-8", errors="ignore") as f_obj:
                for line_idx, line in enumerate(f_obj, 1):
                    for pat, desc in patterns:
                        if pat.search(line):
                            # Redact sensitive matches
                            clean_snippet = line.strip()[:80]
                            pattern_findings.append(f"• ⚠️ `{rel_f}:{line_idx}` [{desc}]: `{clean_snippet}`")
                            break
        except Exception:
            pass

    if pattern_findings:
        results.extend(pattern_findings[:10])
        if len(pattern_findings) > 10:
            results.append(f"\n... dan {len(pattern_findings) - 10} pola rawan lainnya.")
    else:
        results.append("• ✅ Tidak ditemukan hardcoded secret atau pola fungsi rawan yang jelas.")

    final_report = "\n".join(results)
    return truncate_or_save(final_report, max_length=2500, context_name="code_security")


@tool
def audit_dependencies(project_path: str = ".") -> str:
    """Audit project dependencies (requirements.txt or packages) for known CVEs and security advisories."""
    base_path = os.path.abspath(project_path.strip().strip("'").strip('"'))
    req_file = None

    if os.path.isfile(base_path) and base_path.endswith(".txt"):
        req_file = base_path
    elif os.path.isdir(base_path):
        candidate = os.path.join(base_path, "requirements.txt")
        if os.path.exists(candidate):
            req_file = candidate

    results = [f"📦 **Dependency Vulnerability Audit Report** ({req_file or 'Installed Packages'})\n"]

    # 1. Fast direct check via OSV.dev API if requirements file exists
    if req_file and os.path.exists(req_file):
        try:
            packages_to_check = []
            with open(req_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and not line.startswith("-"):
                        # Parse package name and version if pinned (== or >=)
                        parts = re.split(r"[><=~]", line)
                        pkg_name = parts[0].strip()
                        pkg_ver = None
                        if "==" in line:
                            pkg_ver = line.split("==")[1].strip()
                        elif ">=" in line:
                            pkg_ver = line.split(">=")[1].strip()
                        if pkg_name:
                            packages_to_check.append((pkg_name, pkg_ver))

            if packages_to_check:
                vuln_count = 0
                vuln_items = []
                # Check top packages via OSV API concurrently or batched
                for pkg_name, pkg_ver in packages_to_check[:30]:
                    try:
                        payload = {"package": {"name": pkg_name, "ecosystem": "PyPI"}}
                        if pkg_ver:
                            payload["version"] = pkg_ver
                        r = requests.post("https://api.osv.dev/v1/query", json=payload, headers=HEADERS, timeout=4)
                        if r.status_code == 200:
                            v_list = r.json().get("vulns", [])
                            if v_list:
                                vuln_count += len(v_list)
                                for v in v_list[:2]:
                                    cve = v.get("id")
                                    summary = v.get("summary", v.get("details", ""))[:120].replace("\n", " ")
                                    vuln_items.append(f"• 🔴 **{pkg_name}** ({pkg_ver or 'any'}) — `{cve}`: {summary}")
                    except Exception:
                        pass

                if vuln_count == 0:
                    results.append("✅ **Pemeriksaan OSV.dev:** Tidak ditemukan kerentanan CVE kritis pada pustaka yang diperiksa.")
                else:
                    results.append(f"⚠️ **Ditemukan {vuln_count} celah keamanan terdaftar (OSV/CVE):**\n")
                    results.extend(vuln_items[:10])
                    if len(vuln_items) > 10:
                        results.append(f"\n... dan {len(vuln_items) - 10} CVE lainnya.")

                return truncate_or_save("\n".join(results), max_length=2500, context_name="dependency_audit")
        except Exception:
            pass

    # 2. Fallback to pip-audit binary if OSV check is not applicable
    pip_audit_bin = shutil.which("pip-audit") or "/home/papermind/.local/bin/pip-audit"
    if pip_audit_bin and os.path.exists(pip_audit_bin):
        cmd = [pip_audit_bin, "-f", "json"]
        if req_file:
            cmd.extend(["-r", req_file])
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            output_str = proc.stdout.strip()
            if output_str:
                data = json.loads(output_str)
                deps = data.get("dependencies", []) if isinstance(data, dict) else data
                vuln_count = 0
                for dep in deps:
                    if dep.get("vulns"):
                        vuln_count += len(dep.get("vulns"))
                results.append(f"Hasil pip-audit: Ditemukan {vuln_count} kerentanan.")
                return truncate_or_save("\n".join(results), max_length=2500, context_name="dependency_audit")
        except Exception:
            pass

    return "Audit selesai. Tidak ditemukan kerentanan signifikan atau proses timeout."

