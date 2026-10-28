"""
Maintainer Skill — tools for project registration, codebase indexing, CVE and bug audits.
"""
import os
import time
from typing import Dict, Any, List, Optional
from langchain_core.tools import tool

from core.maintainer_db import get_connection, init_maintainer_db
from core.maintainer_scanner import discover_project_targets, get_installed_host_runtimes
from core.maintainer_inspector import (
    index_code_symbols,
    query_osv_vulnerabilities,
    check_runtime_vulnerabilities,
    scan_source_bugs,
)


def _resolve_path(path: str) -> str:
    path_clean = path.strip().strip("'").strip('"')
    if os.path.isabs(path_clean):
        return path_clean
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, path_clean)


@tool
def register_project(project_path: str, custom_name: Optional[str] = None) -> str:
    """
    Register a project directory (single app or nested monorepo with backend/frontend).
    Discovers manifests, extracts runtime targets, dependencies, and indexes symbols.
    """
    full_path = _resolve_path(project_path)
    if not os.path.exists(full_path):
        return f"❌ Path tidak ditemukan: {full_path}"

    project_name = custom_name.strip() if custom_name else os.path.basename(full_path.rstrip("/\\"))
    if not project_name:
        project_name = "unnamed_project"

    try:
        targets = discover_project_targets(full_path)
    except Exception as e:
        return f"❌ Gagal memindai target project: {e}"

    if not targets:
        return f"⚠️ Tidak ditemukan manifest proyek yang didukung (composer.json, package.json, requirements.txt, Dockerfile) di `{full_path}`."

    conn = get_connection()
    cursor = conn.cursor()
    now = time.time()

    # Insert or update project
    cursor.execute("""
        INSERT INTO projects (name, root_path, created_at, last_scanned_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(name) DO UPDATE SET root_path=excluded.root_path, last_scanned_at=excluded.last_scanned_at
    """, (project_name, full_path, now, now))
    
    cursor.execute("SELECT id FROM projects WHERE name = ?", (project_name,))
    project_id = cursor.fetchone()[0]

    total_deps = 0
    total_symbols = 0
    target_summaries = []

    for t in targets:
        # Insert or replace subtarget
        cursor.execute("""
            INSERT INTO project_subtargets (project_id, rel_path, full_path, ecosystem, manifest_file, runtime_target, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id, rel_path) DO UPDATE SET
                full_path=excluded.full_path,
                ecosystem=excluded.ecosystem,
                manifest_file=excluded.manifest_file,
                runtime_target=excluded.runtime_target
        """, (project_id, t["rel_path"], t["full_path"], t["ecosystem"], t["manifest_file"], t["runtime_target"], now))

        cursor.execute("SELECT id FROM project_subtargets WHERE project_id=? AND rel_path=?", (project_id, t["rel_path"]))
        subtarget_id = cursor.fetchone()[0]

        # Insert dependencies
        deps = t.get("dependencies", [])
        total_deps += len(deps)
        for d in deps:
            cursor.execute("""
                INSERT INTO project_dependencies (subtarget_id, package_name, version_spec, is_dev)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(subtarget_id, package_name) DO UPDATE SET version_spec=excluded.version_spec, is_dev=excluded.is_dev
            """, (subtarget_id, d["package"], d.get("version"), d.get("is_dev", 0)))

        # Lightweight symbol indexing
        symbols = index_code_symbols(t["full_path"])
        total_symbols += len(symbols)
        cursor.execute("DELETE FROM code_symbols WHERE subtarget_id=?", (subtarget_id,))
        for s in symbols:
            cursor.execute("""
                INSERT INTO code_symbols (subtarget_id, file_rel_path, symbol_type, symbol_name, line_no)
                VALUES (?, ?, ?, ?, ?)
            """, (subtarget_id, s["file_rel_path"], s["symbol_type"], s["symbol_name"], s["line_no"]))

        rt_label = f" ({t['runtime_target']})" if t.get("runtime_target") else ""
        target_summaries.append(f"  • `{t['rel_path']}`: {t['ecosystem'].upper()}{rt_label} — {len(deps)} deps, {len(symbols)} symbols")

    conn.commit()
    conn.close()

    return (
        f"✅ **Project '{project_name}' Berhasil Didaftarkan!**\n"
        f"Root Path: `{full_path}`\n\n"
        f"**Target & Sub-Project Terdeteksi ({len(targets)}):**\n"
        + "\n".join(target_summaries) +
        f"\n\nTotal {total_deps} dependensi dan {total_symbols} simbol (class/function/route) telah diindeks untuk pencarian cepat."
    )


@tool
def list_registered_projects() -> str:
    """List all registered projects monitored by the AI Maintainer."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.id, p.name, p.root_path, COUNT(s.id) as subtarget_count
        FROM projects p
        LEFT JOIN project_subtargets s ON p.id = s.project_id
        GROUP BY p.id
        ORDER BY p.id DESC
    """)
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return "Belum ada project yang didaftarkan. Gunakan `register_project(path)` untuk mendaftarkan project."

    lines = ["📋 **Daftar Project Terdaftar (AI Maintainer):**\n"]
    for r in rows:
        lines.append(f"• **{r['name']}** ({r['subtarget_count']} target): `{r['root_path']}`")
    return "\n".join(lines)


@tool
def audit_project(project_name: str) -> str:
    """
    Run full maintenance audit on a registered project:
    1. Check runtime vulnerabilities (e.g. PHP CGI/RCE, EOL runtimes).
    2. Batch query OSV.dev for known library CVEs across backend & frontend.
    3. SAST code pattern scan for SQL injection, command execution, and leaked secrets.
    """
    clean_name = project_name.strip()
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id, name, root_path FROM projects WHERE name = ?", (clean_name,))
    proj = cursor.fetchone()
    if not proj:
        conn.close()
        return f"❌ Project '{clean_name}' tidak ditemukan di registry. Gunakan `list_registered_projects()` untuk melihat daftar."

    proj_id, name, root_path = proj[0], proj[1], proj[2]
    host_runtimes = get_installed_host_runtimes()

    cursor.execute("SELECT id, rel_path, full_path, ecosystem, runtime_target FROM project_subtargets WHERE project_id=?", (proj_id,))
    subtargets = cursor.fetchall()

    report_lines = [f"🛡️ **Maintainer Audit Report: `{name}`**\n"]
    total_issues = 0

    for st in subtargets:
        st_id, rel_path, full_path, ecosystem, rt_target = st[0], st[1], st[2], st[3], st[4]
        report_lines.append(f"📁 **Target: `{rel_path}` ({ecosystem.upper()})**")

        # 1. Runtime checks
        rt_alerts = check_runtime_vulnerabilities(rt_target, host_runtimes)
        for rta in rt_alerts:
            total_issues += 1
            report_lines.append(f"  • 🔴 [{rta['severity']}] Runtime Vulnerability: **{rta['title']}**\n    Saran: {rta['recommendation']}")

        # 2. Dependency CVE checks
        cursor.execute("SELECT package_name, version_spec FROM project_dependencies WHERE subtarget_id=?", (st_id,))
        dep_rows = cursor.fetchall()
        deps = [{"package": r[0], "version": r[1]} for r in dep_rows]

        cves = query_osv_vulnerabilities(deps, ecosystem)
        if cves:
            for c in cves[:5]:
                total_issues += 1
                report_lines.append(f"  • ⚠️ [{c['severity']}] `{c['cve_id']}` in **{c['package']}** ({c['current_version']}): {c['summary']}")
            if len(cves) > 5:
                report_lines.append(f"  ... dan {len(cves) - 5} CVE lainnya.")
        else:
            report_lines.append("  • ✅ Dependensi: Bebas dari CVE terdaftar di OSV.dev.")

        # 3. Code SAST bug scan
        code_bugs = scan_source_bugs(full_path)
        if code_bugs:
            for b in code_bugs[:4]:
                total_issues += 1
                report_lines.append(f"  • 🔍 [{b['severity']}] Bug/Risk: `{b['file']}:{b['line']}` — {b['title']}")
            if len(code_bugs) > 4:
                report_lines.append(f"  ... dan {len(code_bugs) - 4} temuan kode lainnya.")
        else:
            report_lines.append("  • ✅ Source Code: Tidak ditemukan pola bug/injeksi berbahaya.")

        report_lines.append("")

    cursor.execute("UPDATE projects SET last_scanned_at=? WHERE id=?", (time.time(), proj_id))
    conn.commit()
    conn.close()

    summary_status = f"⚠️ Ditemukan **{total_issues}** potensi isu/CVE yang perlu perhatian." if total_issues > 0 else "✅ Semua target dalam kondisi prima & aman!"
    report_lines.insert(1, summary_status + "\n")
    return "\n".join(report_lines)
