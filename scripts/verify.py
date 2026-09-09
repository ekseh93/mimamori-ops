"""Repeatable local validation. No cloud login, writes, or deployment."""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts" / "local"
OUTPUT.mkdir(parents=True, exist_ok=True)
checks = [
    ("lint", [sys.executable, "-m", "ruff", "check", "."]),
    ("tests", [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]),
    ("demo", [sys.executable, "-m", "mimamori", "demo", "--output", "artifacts/local/demo.md"]),
    ("package", [sys.executable, "scripts/package.py"]),
    ("terraform-fmt", ["terraform", "-chdir=infra", "fmt", "-check", "-recursive"]),
    ("terraform-validate", ["terraform", "-chdir=infra", "validate", "-no-color"]),
    ("terraform-mock-tests", ["terraform", "-chdir=infra", "test", "-no-color"]),
]
results = []
for name, command in checks:
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    (OUTPUT / f"{name}.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    results.append({"check": name, "exit_code": result.returncode})
    print(f"{name}: {'PASS' if result.returncode == 0 else 'FAIL'}")
    if result.returncode:
        print(result.stdout + result.stderr)
record = {"verified_at_utc": datetime.now(timezone.utc).isoformat(),
          "scope": "local + mocked AWS only", "checks": results}
(OUTPUT / "verification.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
raise SystemExit(int(any(result["exit_code"] for result in results)))
