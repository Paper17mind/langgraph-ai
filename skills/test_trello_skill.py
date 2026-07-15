#!/usr/bin/env python3
# test_trello_skill.py – minimal self‑check for trello_skill
import os, subprocess, sys

# Ensure the skill file is importable
skill_path = "/var/www/projects/ai-telebot/skills/trello_skill.py"

def run_cmd(env):
    cmd = ["python3", skill_path]
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    return result.stdout.strip(), result.stderr.strip(), result.returncode

# 1️⃣ No credentials – should print warning and exit 0
out, err, rc = run_cmd({})
assert "TRELLO_KEY/TRELLO_TOKEN not set" in out, "missing credential message"
assert rc == 0, "should exit cleanly"

# 2️⃣ Dummy credentials – API returns 401, we still get warning
env = os.environ.copy()
env.update({"TRELLO_KEY": "dummy", "TRELLO_TOKEN": "dummy"})
out, err, rc = run_cmd(env)
assert "HTTP Error 401" in out, "should show unauthorized"
print("✅ trello_skill self‑test passed")
