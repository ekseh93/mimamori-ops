"""Check tracked text for local metadata and recognizable credential patterns."""

import re
import subprocess
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    files = subprocess.check_output(["git", "ls-files", "-z"], cwd=root).decode().split("\0")
    patterns = {
        "local home directory": re.compile(r"C:[/\\]Users[/\\]", re.I),
        "AWS access key": re.compile(r"(?:AKIA|ASIA)[A-Z0-9]{16}"),
        "GitHub token": re.compile(r"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{50,})"),
        "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    }
    problems = []
    for name in filter(None, files):
        if name == "docs/pipeline/registry.json" or name.startswith(".codex-local/"):
            problems.append((name, "local coordination metadata must not be tracked"))
        path = root / name
        if not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for label, pattern in patterns.items():
            if pattern.search(content):
                problems.append((name, label))
    for name, label in problems:
        print(f"FAIL: {name}: {label}")  # Never print the matched credential.
    if not problems:
        print(f"Public-content check passed ({len(list(filter(None, files)))} tracked paths).")
    return int(bool(problems))


if __name__ == "__main__":
    raise SystemExit(main())
