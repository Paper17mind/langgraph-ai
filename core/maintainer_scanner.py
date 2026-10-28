"""
Scanner for discovering nested project targets, parsing manifests (composer, package.json, requirements, etc.),
and extracting runtime requirements (PHP, Node.js, Python, Go).
"""
import os
import json
import re
import subprocess
from typing import Dict, Any, List, Optional

IGNORE_DIRS = {
    "node_modules", "vendor", ".git", ".venv", "venv", "__pycache__",
    "dist", "build", "coverage", ".next", ".nuxt", "storage", "cache",
    ".idea", ".vscode"
}

MANIFEST_FILES = {
    "composer.json": "php",
    "package.json": "node",
    "requirements.txt": "python",
    "pyproject.toml": "python",
    "Pipfile": "python",
    "go.mod": "go",
    "Dockerfile": "docker",
}


def get_installed_host_runtimes() -> Dict[str, Optional[str]]:
    """Probe active runtimes installed on host (php, node, python)."""
    runtimes = {}
    
    # PHP
    try:
        res = subprocess.run(["php", "-v"], capture_output=True, text=True, timeout=3)
        if res.returncode == 0:
            m = re.search(r"PHP\s+([0-9]+\.[0-9]+\.[0-9]+)", res.stdout)
            runtimes["php"] = m.group(1) if m else "installed"
    except Exception:
        runtimes["php"] = None

    # Node
    try:
        res = subprocess.run(["node", "-v"], capture_output=True, text=True, timeout=3)
        if res.returncode == 0:
            runtimes["node"] = res.stdout.strip().lstrip("v")
    except Exception:
        runtimes["node"] = None

    # Python
    try:
        res = subprocess.run(["python3", "-V"], capture_output=True, text=True, timeout=3)
        if res.returncode == 0:
            m = re.search(r"Python\s+([0-9]+\.[0-9]+\.[0-9]+)", res.stdout)
            runtimes["python"] = m.group(1) if m else "installed"
    except Exception:
        runtimes["python"] = None

    return runtimes


def parse_composer_json(file_path: str) -> Dict[str, Any]:
    """Parse composer.json for runtime requirements and dependencies."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {"runtime": None, "dependencies": []}

    reqs = data.get("require", {})
    reqs_dev = data.get("require-dev", {})
    php_version = reqs.get("php") or data.get("config", {}).get("platform", {}).get("php")

    deps = []
    for pkg, ver in reqs.items():
        if pkg.lower() != "php":
            deps.append({"package": pkg, "version": str(ver), "is_dev": 0})
    for pkg, ver in reqs_dev.items():
        if pkg.lower() != "php":
            deps.append({"package": pkg, "version": str(ver), "is_dev": 1})

    return {
        "runtime": f"PHP {php_version}" if php_version else None,
        "dependencies": deps,
    }


def parse_package_json(file_path: str) -> Dict[str, Any]:
    """Parse package.json for engines (node) and dependencies."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {"runtime": None, "dependencies": []}

    node_engine = data.get("engines", {}).get("node")
    deps_prod = data.get("dependencies", {})
    deps_dev = data.get("devDependencies", {})

    deps = []
    for pkg, ver in deps_prod.items():
        deps.append({"package": pkg, "version": str(ver), "is_dev": 0})
    for pkg, ver in deps_dev.items():
        deps.append({"package": pkg, "version": str(ver), "is_dev": 1})

    return {
        "runtime": f"Node {node_engine}" if node_engine else None,
        "dependencies": deps,
    }


def parse_requirements_txt(file_path: str) -> Dict[str, Any]:
    """Parse Python requirements.txt for dependencies."""
    deps = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("-"):
                    continue
                parts = re.split(r"[><=~!]", line, maxsplit=1)
                pkg = parts[0].strip()
                ver = line[len(pkg):].strip() if len(parts) > 1 else ""
                if pkg:
                    deps.append({"package": pkg, "version": ver, "is_dev": 0})
    except Exception:
        pass

    return {
        "runtime": None,
        "dependencies": deps,
    }


def parse_dockerfile(file_path: str) -> Dict[str, Any]:
    """Extract base image / runtime from Dockerfile."""
    runtime = None
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.upper().startswith("FROM "):
                    image = line.split()[1]
                    runtime = f"Docker {image}"
                    break
    except Exception:
        pass
    return {"runtime": runtime, "dependencies": []}


def discover_project_targets(root_path: str, max_depth: int = 3) -> List[Dict[str, Any]]:
    """
    Shallow recursive discovery of project sub-targets (monorepo or single app).
    Returns list of discovered sub-targets with manifest and dependencies.
    """
    root_path = os.path.abspath(root_path)
    if not os.path.exists(root_path):
        raise FileNotFoundError(f"Project path does not exist: {root_path}")

    discovered = []
    base_depth = root_path.rstrip(os.sep).count(os.sep)

    for current_root, dirs, files in os.walk(root_path):
        # Prune ignored directories in-place
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith(".")]

        depth = current_root.count(os.sep) - base_depth
        if depth > max_depth:
            dirs.clear()
            continue

        rel_dir = os.path.relpath(current_root, root_path)
        rel_label = "." if rel_dir == "." else rel_dir

        for manifest, ecosystem in MANIFEST_FILES.items():
            if manifest in files:
                manifest_path = os.path.join(current_root, manifest)
                parsed_info: Dict[str, Any] = {"runtime": None, "dependencies": []}

                if manifest == "composer.json":
                    parsed_info = parse_composer_json(manifest_path)
                elif manifest == "package.json":
                    parsed_info = parse_package_json(manifest_path)
                elif manifest == "requirements.txt":
                    parsed_info = parse_requirements_txt(manifest_path)
                elif manifest == "Dockerfile":
                    parsed_info = parse_dockerfile(manifest_path)

                discovered.append({
                    "rel_path": rel_label,
                    "full_path": current_root,
                    "ecosystem": ecosystem,
                    "manifest_file": manifest,
                    "manifest_path": manifest_path,
                    "runtime_target": parsed_info.get("runtime"),
                    "dependencies": parsed_info.get("dependencies", []),
                })

    return discovered
