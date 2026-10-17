"""Show what the local Docker stack will touch, and refuse when it is not ours.

    python3 scripts/stack_check.py                   # postgres, api and web
    python3 scripts/stack_check.py postgres          # only the services named
    python3 scripts/stack_check.py --ownership-only  # before stopping: skip port checks

Prints the Compose project this checkout resolves to, the containers and
volumes that project owns, the loopback ports it publishes and the database
that host commands (make db, seed, dev-api, tests) will use. Passwords are
never printed. Exits 1, before anything is started or stopped, when:

* a port the stack publishes is already taken by something outside it;
* the project's containers were created from another directory, or its
  volumes by another project, so using them here would take over someone
  else's stack or data.

Settings resolve as everywhere else in RegDelta: the process environment,
then .env, then the defaults in docker-compose.yml and app/core/config.py.
Standard library only, so it runs before the virtualenv exists.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOOPBACK = ("127.0.0.1", "::1")


def dotenv(path: Path) -> dict[str, str]:
    """KEY=VALUE lines, with comments and surrounding quotes removed."""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) > 1 and value[0] in "\"'" and value[-1] == value[0]:
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        values[key.strip()] = value
    return values


def docker(*args: str, check: bool = True) -> str:
    result = subprocess.run(["docker", *args], capture_output=True, text=True, cwd=ROOT)
    if check and result.returncode != 0:
        raise SystemExit(f"docker {' '.join(args[:2])} failed: {result.stderr.strip()}")
    return result.stdout if result.returncode == 0 else ""


def listening(port: int) -> bool:
    with socket.socket() as probe:
        probe.settimeout(0.5)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def main(argv: list[str]) -> int:
    env_file = dotenv(ROOT / ".env")

    def setting(name: str, default: str) -> str:
        return os.environ.get(name) or env_file.get(name) or default

    ownership_only = "--ownership-only" in argv
    names = [a for a in argv if not a.startswith("--")]
    config = json.loads(docker("compose", "config", "--format", "json"))
    project = config["name"]
    services = names or list(config["services"])
    problems: list[str] = []

    if os.environ.get("COMPOSE_PROJECT_NAME"):
        source = "COMPOSE_PROJECT_NAME in the environment"
    elif env_file.get("COMPOSE_PROJECT_NAME"):
        source = "COMPOSE_PROJECT_NAME in .env"
    else:
        source = "docker-compose.yml"
    print(f"compose project: {project} (from {source})")

    label = f"label=com.docker.compose.project={project}"
    fields = '{{.ID}}\t{{.Names}}\t{{.State}}\t{{.Label "com.docker.compose.project.working_dir"}}'
    for line in docker("ps", "-a", "--filter", label, "--format", fields).splitlines():
        cid, name, state, workdir = line.split("\t")
        owner = "this checkout" if Path(workdir) == ROOT else workdir
        print(f"  container {name} ({cid}, {state}), created from {owner}")
        if Path(workdir) != ROOT:
            problems.append(
                f"container {name} belongs to a {project!r} stack created from {workdir}; "
                "set COMPOSE_PROJECT_NAME to another name for this checkout"
            )
    running_ports = docker("ps", "--filter", label, "--format", "{{.Ports}}")

    for volume in config.get("volumes", {}).values():
        name = volume["name"]
        found = docker("volume", "inspect", name, "--format", "{{json .Labels}}", check=False)
        if not found:
            print(f"  volume {name} will be created")
            continue
        labels = json.loads(found) or {}
        created = docker("volume", "inspect", name, "--format", "{{.CreatedAt}}").strip()
        print(f"  volume {name} exists (created {created})")
        if labels.get("com.docker.compose.project") != project:
            problems.append(f"volume {name} exists but was not created by project {project!r}")

    published: dict[str, int] = {}
    for service in services:
        for port in config["services"].get(service, {}).get("ports", []):
            number, host_ip = int(port["published"]), port.get("host_ip", "")
            published[service] = number
            print(f"  {service}: {host_ip or '0.0.0.0'}:{number} -> {port['target']}")
            if host_ip not in LOOPBACK:
                problems.append(f"{service} would publish port {number} beyond loopback")
            held_by_stack = f":{number}->" in running_ports
            if not ownership_only and listening(number) and not held_by_stack:
                problems.append(
                    f"port {number} for {service} is already in use outside this stack; "
                    "choose a free port in .env"
                )

    host = setting("POSTGRES_HOST", "localhost")
    port = int(setting("POSTGRES_PORT", "5432"))
    user, name = setting("POSTGRES_USER", "regdelta"), setting("POSTGRES_DB", "regdelta")
    target = f"{user}@{host}:{port}/{name}"
    if setting("DATABASE_URL", ""):
        print("host commands refuse to start: DATABASE_URL is set (not shown); unset it")
    elif host in ("localhost", *LOOPBACK) and port == published.get("postgres"):
        print(f"host commands use: {target}, this stack's postgres")
    else:
        print(f"host commands use: {target}, not this stack's postgres")

    sys.stdout.flush()
    for problem in problems:
        print(f"REFUSED: {problem}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
