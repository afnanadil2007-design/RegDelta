"""Build the review ZIP: the committed source plus selected, sanitised evidence.

    python3 scripts/package_review.py --previous 0dc9437 \\
        --results docs/maintenance/regdelta-release-results.json \\
        --out ../RegDelta-review-v2.zip

What goes in, under ``RegDelta/``:

* ``git archive HEAD``: exactly the committed tree (no .git, no ignored or
  untracked files, so no .env, virtual environments, node_modules, caches,
  model weights or databases);
* ``review-evidence/``: the files listed in ``EVIDENCE`` that exist, copied
  from the git-ignored ``.artifacts/r2/`` with local paths and anything
  shaped like a credential redacted; a diff and commit list against the
  previous review revision; and ``MANIFEST.json`` (UTC time, code and head
  revisions, tool versions, the recorded results table, a SHA-256 for
  every entry, and the redaction counts).

It refuses to write the archive when an entry looks like something that must
not ship (a real .env, a key file, a virtualenv, node_modules, a database
dump, model weights) or when the sensitive-content scan finds a match; it
prints file names and pattern names, never the matched text. Standard
library only.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import subprocess
import sys
import tarfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / ".artifacts" / "r2"
PREFIX = "RegDelta/"
# Paths whose commits are evidence about the code, not code: the code
# revision is the last commit that touched anything else.
EVIDENCE_ONLY = ("docs/maintenance", "docs/screenshots")
# Text evidence is redacted; images are copied as they are (they were
# captured from synthetic data and inspected).
EVIDENCE_GLOBS = (
    "logs/**/*.log",
    "logs/**/*.txt",
    "audit/*.json",
    "container*/*.json",
    "screenshots/*.yml",
    "screenshots/*.log",
)
BINARY_GLOBS = ("container*/*.png", "screenshots/*.png")

FORBIDDEN = [
    (re.compile(r"(^|/)\.git/"), "git metadata"),
    (re.compile(r"(^|/)\.env(\.(?!example$)[^/]*)?$"), "an environment file"),
    (
        re.compile(r"(^|/)(node_modules|\.venv|venv|__pycache__|\.mypy_cache|\.pytest_cache)/"),
        "an installed or cached tree",
    ),
    (re.compile(r"\.(safetensors|ckpt|pt|onnx|gguf)$"), "model weights"),
    (re.compile(r"\.(dump|sql\.gz|pgdump|sqlite3?|db)$"), "a database file"),
    (re.compile(r"\.(pem|key|p12|pfx)$|(^|/)id_(rsa|ed25519)"), "a key file"),
]
# Shapes of real credentials. The documented local defaults (regdelta /
# regdelta) and placeholders are not matched.
SECRETS = [
    (re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private key block"),
    (re.compile(rb"\bsk-ant-[A-Za-z0-9_-]{20,}"), "Anthropic key"),
    (re.compile(rb"\bgsk_[A-Za-z0-9]{20,}"), "Groq key"),
    (re.compile(rb"\bsk-[A-Za-z0-9]{32,}"), "OpenAI-style key"),
    (re.compile(rb"\bgh[pousr]_[A-Za-z0-9]{30,}"), "GitHub token"),
    (re.compile(rb"\bAKIA[0-9A-Z]{16}\b"), "AWS access key"),
    (re.compile(rb"\bhf_[A-Za-z0-9]{30,}"), "Hugging Face token"),
    (
        re.compile(
            rb"(?i)(api[_-]?key|secret|token|password)\s*[=:]\s*['\"]?(?!regdelta\b|change-me|example|placeholder|\$\{|<)[A-Za-z0-9/+_-]{16,}"
        ),
        "assigned secret",
    ),
]
REDACTIONS = [
    (re.compile(r"postgresql(\+\w+)?://[^:@/\s]+:[^@/\s]+@"), r"postgresql\1://<user>:<redacted>@"),
    (
        re.compile(
            r"(?i)((?:api[_-]?key|password|secret|token)\s*[=:]\s*)(?!regdelta\b)[^\s'\",]{6,}"
        ),
        r"\1<redacted>",
    ),
    (re.compile(r"/tmp/claude-\d+/[^\s'\"]*?/scratchpad"), "<scratch>"),
    (re.compile(r"/home/[A-Za-z0-9._-]+"), "~"),
]


def git(*args: str) -> bytes:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=True).stdout


def version(*command: str) -> str:
    try:
        out = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    except OSError:
        return "not available"
    return (out.stdout or out.stderr).strip().splitlines()[0] if (out.stdout or out.stderr) else "?"


def sanitise(text: str) -> tuple[str, int]:
    count = 0
    for pattern, replacement in REDACTIONS:
        text, n = pattern.subn(replacement, text)
        count += n
    return text, count


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--previous", required=True, help="the previous review revision")
    parser.add_argument("--results", type=Path, required=True, help="recorded results JSON")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    if git("status", "--porcelain", "--untracked-files=no").strip():
        print("REFUSED: tracked files have uncommitted changes; commit them first.")
        return 1
    head = git("rev-parse", "HEAD").decode().strip()
    code = (
        git("log", "-1", "--format=%H", "--", ".", *[f":(exclude){p}" for p in EVIDENCE_ONLY])
        .decode()
        .strip()
    )

    entries: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(git("archive", "--format=tar", "HEAD"))) as tar:
        for member in tar.getmembers():
            if member.isfile():
                handle = tar.extractfile(member)
                assert handle is not None
                entries[PREFIX + member.name] = handle.read()

    redacted: dict[str, int] = {}
    for pattern in EVIDENCE_GLOBS:
        for path in sorted(ARTIFACTS.glob(pattern)):
            text, n = sanitise(path.read_text(encoding="utf-8", errors="replace"))
            name = f"{PREFIX}review-evidence/{path.relative_to(ARTIFACTS)}"
            entries[name] = text.encode("utf-8")
            if n:
                redacted[name] = n

    for pattern in BINARY_GLOBS:
        for path in sorted(ARTIFACTS.glob(pattern)):
            entries[f"{PREFIX}review-evidence/{path.relative_to(ARTIFACTS)}"] = path.read_bytes()

    previous = args.previous
    entries[f"{PREFIX}review-evidence/diff-{previous}..{code[:7]}.patch"] = git(
        "diff", f"{previous}..{code}"
    )
    entries[f"{PREFIX}review-evidence/commits-since-{previous}.txt"] = git(
        "log", "--reverse", "--stat", "--format=%n%H %s%n%b", f"{previous}..{head}"
    )

    problems = [
        f"{name}: {why}"
        for name in entries
        for pattern, why in FORBIDDEN
        if pattern.search(name.removeprefix(PREFIX))
    ]
    for name, data in entries.items():
        for pattern, what in SECRETS:
            if pattern.search(data):
                problems.append(f"{name}: looks like it contains a {what}")
    if problems:
        for problem in problems:
            print(f"REFUSED: {problem}")
        return 1

    manifest = {
        "prepared_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "code_revision": code,
        "head_revision": head,
        "head_is_evidence_only": head != code,
        "evidence_only_paths": list(EVIDENCE_ONLY),
        "previous_review_revision": git("rev-parse", previous).decode().strip(),
        "tools": {
            "git": version("git", "--version"),
            "python3": version("python3", "--version"),
            "node": version("node", "--version"),
            "npm": version("npm", "--version"),
            "docker": version("docker", "--version"),
            "compose": version("docker", "compose", "version"),
        },
        "results": json.loads(args.results.read_text(encoding="utf-8")),
        "redactions": redacted,
        "files": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(entries.items())},
    }
    entries[f"{PREFIX}review-evidence/MANIFEST.json"] = (
        json.dumps(manifest, indent=2) + "\n"
    ).encode()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(entries):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, entries[name])
    digest = hashlib.sha256(args.out.read_bytes()).hexdigest()
    print(f"{args.out} {args.out.stat().st_size} bytes sha256 {digest}")
    print(f"{len(entries)} entries; code {code[:7]}, head {head[:7]}")
    print(f"redactions in {len(redacted)} evidence file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
