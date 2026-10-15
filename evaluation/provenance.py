"""Where a measurement came from: code, models, data and machine.

Every result file carries this block so a number can be traced to the exact
code that produced it. A dirty working tree is never attributed to its clean
base commit: the digest covers the uncommitted changes to the evaluated
sources, including untracked files.
"""

from __future__ import annotations

import hashlib
import os
import platform
import subprocess
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent

# The sources whose behaviour an evaluation measures. Frontend and docs changes
# cannot move a retrieval number, so they do not make a result "dirty".
EVALUATED_PATHS = (
    "backend/app",
    "backend/pyproject.toml",
    "evaluation",
    "ingestion",
    # Outputs of evaluation are not inputs to it.
    ":(exclude)evaluation/results",
)


def _git(*args: str) -> str:
    try:
        out = subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, timeout=20, check=True
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout


def code_identity(paths: tuple[str, ...] = EVALUATED_PATHS) -> dict[str, Any]:
    """Commit, whether the evaluated sources differ from it, and a digest if so."""
    sha = _git("rev-parse", "HEAD").strip() or "unknown"
    status = _git("status", "--porcelain", "--untracked-files=all", "--", *paths)
    changed = sorted(line[3:] for line in status.splitlines() if line.strip())
    identity: dict[str, Any] = {
        "git_sha": sha,
        "evaluated_paths": list(paths),
        "dirty": bool(changed),
        "dirty_files": changed,
        "dirty_digest": None,
    }
    if changed:
        digest = hashlib.sha256(_git("diff", "HEAD", "--binary", "--", *paths).encode())
        for name in changed:
            file = REPO_ROOT / name
            if file.is_file() and _git("ls-files", "--error-unmatch", name) == "":
                digest.update(name.encode() + b"\0" + file.read_bytes())
        identity["dirty_digest"] = digest.hexdigest()
    return identity


def model_revision(repo_id: str) -> str | None:
    """The Hugging Face commit of the locally cached model, if it is cached."""
    try:
        from huggingface_hub import snapshot_download

        return Path(snapshot_download(repo_id, local_files_only=True)).name
    except Exception:  # noqa: BLE001 - absence is reported as None, not raised
        return None


def machine() -> dict[str, Any]:
    cpu = platform.processor() or "unknown"
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                cpu = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    memory_gib = None
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal"):
                memory_gib = round(int(line.split()[1]) / 1024 / 1024, 1)
                break
    except OSError:
        pass
    info: dict[str, Any] = {
        "cpu": cpu,
        "logical_cpus": os.cpu_count(),
        "memory_gib": memory_gib,
        "os": f"{platform.system()} {platform.release()}",
        "python": platform.python_version(),
    }
    try:
        import sentence_transformers
        import torch

        info["torch"] = torch.__version__
        info["torch_threads"] = torch.get_num_threads()
        info["sentence_transformers"] = sentence_transformers.__version__
    except ImportError:
        pass
    return info


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
