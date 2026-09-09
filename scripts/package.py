"""Build a deterministic Lambda zip. Dependencies must already be staged."""

import hashlib
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
dependencies = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "build" / "dependencies"
if not (dependencies / "boto3" / "__init__.py").exists():
    raise SystemExit("First: python -m pip install -r requirements.txt --target build/dependencies")
output = ROOT / "infra" / "lambda.zip"
output.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
    for root, prefix in [(dependencies, ""), (ROOT / "mimamori", "mimamori")]:
        for path in sorted(root.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
                continue
            name = (Path(prefix) / path.relative_to(root)).as_posix()
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.external_attr = 0o644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())
print(f"Built {output.name}; SHA256={hashlib.sha256(output.read_bytes()).hexdigest()}")
