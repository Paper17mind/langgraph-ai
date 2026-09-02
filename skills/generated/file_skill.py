"""Skill for reading file content, specific line, and searching keywords."""

import os
from langchain_core.tools import tool


@tool
def read_file(path: str) -> str:
    """Read entire content of a file."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error reading file {path}: {e}"


@tool
def read_specific_line(path: str, line_no: int) -> str:
    """Read specific 1-based line number from file."""
    if line_no < 1:
        return "Error: line_no must be >= 1"
    try:
        with open(path, "r", encoding="utf-8") as f:
            for idx, line in enumerate(f, start=1):
                if idx == line_no:
                    return line.rstrip("\n").rstrip("\r")
        return f"Error: Line {line_no} out of range"
    except Exception as e:
        return f"Error reading file {path}: {e}"


@tool
def search_in_file(path: str, keyword: str, case_sensitive: bool = False) -> str:
    """Search keyword in file, return list of line matches with line numbers."""
    try:
        target = keyword if case_sensitive else keyword.lower()
        results = []
        with open(path, "r", encoding="utf-8") as f:
            for idx, line in enumerate(f, start=1):
                check = line if case_sensitive else line.lower()
                if target in check:
                    clean_line = line.rstrip("\n").rstrip("\r")
                    results.append(f"{idx}: {clean_line}")
        if not results:
            return f"Keyword '{keyword}' tidak ditemukan di {path}"
        return "\n".join(results)
    except Exception as e:
        return f"Error searching file {path}: {e}"


@tool
def write_specific_line(path: str, line_no: int, content: str) -> str:
    """Write or replace content at a specific 1-based line number in a file."""
    if line_no < 1:
        return "Error: line_no must be >= 1"
    try:
        lines = []
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()

        new_line = content if content.endswith("\n") else content + "\n"

        if line_no <= len(lines):
            lines[line_no - 1] = new_line
        else:
            while len(lines) < line_no - 1:
                lines.append("\n")
            lines.append(new_line)

        parent_dir = os.path.dirname(os.path.abspath(path))
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines)

        return f"Berhasil menulis baris {line_no} pada file {path}"
    except Exception as e:
        return f"Error writing specific line to {path}: {e}"


