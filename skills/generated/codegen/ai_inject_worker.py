"""
Background worker for Phase 2 ai_inject_logic code generation.

Uses a SQLite queue table to process jobs one at a time with a configurable
delay between each LLM call to avoid TPM (tokens per minute) rate limits.
Sends Telegram notifications after each completed job.
"""
import os
import sqlite3
import time
import threading
import json
import re
from datetime import datetime

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)
    )))),
    "data", "codegen_jobs.db"
)


def _ensure_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS codegen_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            schema_path TEXT,
            framework TEXT,
            output_dir TEXT,
            controller TEXT,
            function_name TEXT,
            ai_inject_logic TEXT,
            model_name TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT (datetime('now')),
            completed_at TEXT
        )
    """)
    conn.commit()
    conn.close()


def queue_jobs(
    schema_path: str,
    framework: str,
    output_dir: str,
    jobs: list[dict],
) -> int:
    """Insert ai_inject_logic jobs into the queue. Returns number queued."""
    _ensure_db()
    conn = sqlite3.connect(DB_PATH)
    count = 0
    for job in jobs:
        conn.execute(
            """INSERT INTO codegen_jobs
               (schema_path, framework, output_dir, controller,
                function_name, ai_inject_logic, model_name, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')""",
            (
                schema_path,
                framework,
                output_dir,
                job["controller"],
                job["function_name"],
                job["ai_inject_logic"],
                job["model_name"],
            )
        )
        count += 1
    conn.commit()
    conn.close()
    return count


def get_pending_jobs() -> list[dict]:
    _ensure_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM codegen_jobs WHERE status = 'pending' ORDER BY id ASC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_job(job_id: int, status: str):
    _ensure_db()
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "UPDATE codegen_jobs SET status=?, completed_at=datetime('now') WHERE id=?",
        (status, job_id)
    )
    conn.commit()
    conn.close()


def _send_telegram(message: str):
    """Send a Telegram message using env vars (non-blocking best-effort)."""
    try:
        import requests as req
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.environ.get("CURRENT_CHAT_ID", "")
        if not token or not chat_id:
            print(f"[codegen worker] (no telegram) {message}")
            return
        req.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"},
            timeout=5,
        )
    except Exception as e:
        print(f"[codegen worker] telegram error: {e}")


def _call_llm(prompt: str) -> str:
    """Call the LLM via environment-configured API (same as agent)."""
    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage

        llm = ChatOpenAI(
            model=os.environ.get("9ROUTER_MODEL", "gpt-4o-mini"),
            openai_api_base=os.environ.get("9ROUTER_BASE_URL", "https://api.openai.com/v1"),
            openai_api_key=os.environ.get("9ROUTER_API_KEY", ""),
            temperature=0.2,
        )
        response = llm.invoke([HumanMessage(content=prompt)])
        # Strip markdown code fences if LLM wraps output
        code = response.content.strip()
        code = re.sub(r'^```[\w]*\n?', '', code)
        code = re.sub(r'\n?```$', '', code)
        return code.strip()
    except Exception as e:
        return f"// LLM error: {e}"


def _write_file(path: str, content: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _inject_code(adapter, output_dir: str, job: dict, generated_code: str):
    """Find the right file and inject the AI-generated code."""
    ctrl = job["controller"]
    fn_name = job["function_name"]
    framework = job["framework"]

    # Determine file path based on framework
    if framework == "laravel":
        file_path = os.path.join(output_dir, f"app/Http/Controllers/API/{ctrl}.php")
    elif framework == "fastapi":
        snake = re.sub(r'(?<!^)(?=[A-Z])', '_', ctrl.replace("Controller","")).lower()
        file_path = os.path.join(output_dir, f"app/routers/{snake}.py")
    elif framework == "express":
        file_path = os.path.join(output_dir, f"src/controllers/{ctrl}.js")
    else:
        return

    if not os.path.exists(file_path):
        print(f"[codegen worker] File not found: {file_path}")
        return

    adapter.inject_ai_code(file_path, fn_name, generated_code)

    # Append test case to test file
    _append_test(adapter, output_dir, framework, ctrl, fn_name, job["model_name"], generated_code)


def _append_test(adapter, output_dir, framework, ctrl, fn_name, model_name, code):
    """Generate and append a test case for the AI-injected function."""
    if framework == "laravel":
        test_path = os.path.join(output_dir, f"tests/Feature/{ctrl}Test.php")
        test_case = (
            f"\n\ntest('{ctrl}.{fn_name}: ai-generated logic test', function () {{\n"
            f"    // Auto-generated test for: {fn_name}\n"
            f"    $this->markTestIncomplete('Review generated logic and fill in assertions.');\n"
            f"}});"
        )
    elif framework == "fastapi":
        test_path = os.path.join(output_dir, "tests/test_api.py")
        test_case = (
            f"\n\ndef test_{ctrl.lower()}_{fn_name}():\n"
            f"    # Auto-generated test for: {fn_name}\n"
            f"    pass  # TODO: fill assertions\n"
        )
    elif framework == "express":
        test_path = os.path.join(output_dir, "tests/api.test.js")
        test_case = (
            f"\n  test('{ctrl}.{fn_name} - ai generated', async () => {{\n"
            f"    // TODO: fill assertions for {fn_name}\n"
            f"  }});\n"
        )
    else:
        return

    if os.path.exists(test_path):
        with open(test_path, "a", encoding="utf-8") as f:
            f.write(test_case)


def run_worker(delay_seconds: int = 3):
    """
    Main worker loop — runs in a background thread.
    Processes one job at a time with `delay_seconds` sleep between each.
    """
    print(f"[codegen worker] Starting — delay={delay_seconds}s between jobs")
    schema_cache: dict[str, dict] = {}
    adapter_cache: dict[str, object] = {}

    while True:
        jobs = get_pending_jobs()
        if not jobs:
            print("[codegen worker] Queue empty — stopping.")
            break

        job = jobs[0]
        job_id = job["id"]
        schema_path = job["schema_path"]
        framework = job["framework"]
        output_dir = job["output_dir"]
        ctrl = job["controller"]
        fn_name = job["function_name"]
        logic = job["ai_inject_logic"]
        model_name = job["model_name"]

        mark_job(job_id, "running")
        print(f"[codegen worker] Processing: {ctrl}.{fn_name} ({framework})")

        try:
            # Load schema + adapter (cached)
            cache_key = f"{schema_path}::{framework}::{output_dir}"
            if cache_key not in adapter_cache:
                import json as _json
                with open(schema_path, "r") as f:
                    schema = _json.load(f)
                from codegen import ADAPTERS
                adapter = ADAPTERS[framework](schema, output_dir)
                adapter_cache[cache_key] = adapter
            adapter = adapter_cache[cache_key]

            # Add framework to job for _inject_code
            job["framework"] = framework

            # Build prompt with focused context
            prompt = adapter.build_ai_inject_prompt(ctrl, fn_name, logic, model_name)

            # Call LLM
            generated_code = _call_llm(prompt)

            # Inject into file
            _inject_code(adapter, output_dir, job, generated_code)

            mark_job(job_id, "done")
            ts = datetime.now().strftime("%H:%M:%S")
            _send_telegram(
                f"✅ *[Codegen]* `{ctrl}.{fn_name}` selesai di-generate\n"
                f"Framework: `{framework}` | {ts}"
            )
            print(f"[codegen worker] ✅ Done: {ctrl}.{fn_name}")

        except Exception as e:
            mark_job(job_id, "failed")
            _send_telegram(
                f"❌ *[Codegen]* `{ctrl}.{fn_name}` gagal\nError: `{str(e)[:200]}`"
            )
            print(f"[codegen worker] ❌ Failed {ctrl}.{fn_name}: {e}")

        remaining = len(jobs) - 1
        if remaining > 0:
            print(f"[codegen worker] Waiting {delay_seconds}s... ({remaining} jobs remaining)")
            time.sleep(delay_seconds)

    print("[codegen worker] Worker done.")


def start_worker_thread(delay_seconds: int = 3) -> threading.Thread:
    """Start the worker in a daemon background thread."""
    t = threading.Thread(
        target=run_worker,
        args=(delay_seconds,),
        daemon=True,
        name="codegen-worker"
    )
    t.start()
    return t
