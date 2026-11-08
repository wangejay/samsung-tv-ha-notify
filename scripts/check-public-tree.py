#!/usr/bin/env python3
"""Check publication paths and common secret patterns; never prints matched values.

This is a bounded hygiene check, not a guarantee that every possible secret can
be detected. Review the allowlisted public tree before publishing.
"""
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SKIP = {".git", ".venv", "venv", "__pycache__", "dist", ".build", "bin", "obj", "node_modules"}
BAD_SUFFIXES = {".p12", ".pfx", ".pem", ".key", ".crt", ".cer", ".csr", ".jks", ".tpk", ".wgt"}
PATTERNS = {
    "private-key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "github-token": re.compile(rb"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})"),
    "gitlab-token": re.compile(rb"glpat-[A-Za-z0-9_.-]{20,}"),
    "jwt": re.compile(rb"eyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}"),
}
if (ROOT / ".git").exists():
    output = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    paths = [ROOT / name.decode() for name in output.split(b"\0") if name]
else:
    paths = []
if not paths:
    paths = [p for p in ROOT.rglob("*") if p.is_file() and not set(p.relative_to(ROOT).parts) & SKIP]
issues = []
for path in paths:
    rel = path.relative_to(ROOT)
    if path.is_symlink():
        issues.append(f"{rel}: symlink is not allowed")
        continue
    if path.suffix.lower() in BAD_SUFFIXES or ".private" in rel.parts or path.name in {"profiles.xml", "author-signature.xml", ".env"} or path.name.startswith(".env.") and path.name != ".env.example":
        issues.append(f"{rel}: private/device-specific publication path")
    if path.suffix.lower() in {".ttf", ".png"}:
        continue
    data = path.read_bytes()
    for label, pattern in PATTERNS.items():
        if pattern.search(data):
            issues.append(f"{rel}: possible {label} (value suppressed)")
if issues:
    print("\n".join(issues), file=sys.stderr)
    raise SystemExit(1)
print(f"PASS: {len(paths)} public files checked for risky paths and common secret patterns")
