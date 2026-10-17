"""requirements.lock is the one dependency authority, and it honours pyproject.

The API image and CI install the lock with ``--no-deps``, so nothing checks
the ranges in pyproject.toml at install time. These tests do: every declared
dependency (and extra) must be pinned in the lock at a version inside its
range, and the lock must pin each package exactly once.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

BACKEND = Path(__file__).resolve().parents[1]


def _lock() -> dict[str, str]:
    pins: dict[str, str] = {}
    for line in (BACKEND / "requirements.lock").read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        name, _, version = line.partition("==")
        assert version, f"lock line is not an exact pin: {line!r}"
        key = canonicalize_name(name)
        assert key not in pins, f"{name} is pinned twice"
        pins[key] = version
    return pins


def _declared() -> list[Requirement]:
    project = tomllib.loads((BACKEND / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    requirements = list(project["dependencies"])
    for extra in project.get("optional-dependencies", {}).values():
        requirements += extra
    return [Requirement(r) for r in requirements]


def test_every_declared_dependency_is_pinned_inside_its_range() -> None:
    pins = _lock()
    outside = []
    for requirement in _declared():
        version = pins.get(canonicalize_name(requirement.name))
        if version is None:
            outside.append(f"{requirement.name}: not in the lock")
        elif not requirement.specifier.contains(version, prereleases=True):
            outside.append(f"{requirement.name}=={version} is outside {requirement.specifier}")
    assert outside == []


def test_torch_is_the_cpu_build() -> None:
    # The image and CI pass the PyTorch CPU index; a CUDA pin would pull
    # gigabytes of NVIDIA wheels instead.
    pins = _lock()
    assert pins["torch"].endswith("+cpu")
    assert not [name for name in pins if name.startswith("nvidia-")]
