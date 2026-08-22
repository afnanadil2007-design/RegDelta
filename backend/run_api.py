"""Start the API server.

Use this rather than invoking ``uvicorn`` directly.

psycopg's async driver cannot run on Windows' ``ProactorEventLoop``, and uvicorn
hands Windows exactly that. Its loop factory is:

    if sys.platform == "win32" and not use_subprocess:
        return asyncio.ProactorEventLoop
    return asyncio.SelectorEventLoop

so the loop depends on whether uvicorn is supervising subprocesses. ``--reload``
sets ``use_subprocess`` and quietly works; running without it does not, and
every query fails with "cannot use the 'ProactorEventLoop'".

Setting an event loop *policy* does not fix it on its own either: modern
uvicorn calls ``asyncio.run(..., loop_factory=...)``, and an explicit
``loop_factory`` bypasses the policy. Rather than depend on which uvicorn
version is installed, this entrypoint owns loop creation itself for the normal
case — ``asyncio.run`` on a loop we chose, so uvicorn's factory is never
consulted.

``--reload`` still goes through ``uvicorn.run``, because reloading needs
uvicorn's supervisor process. That path is safe: supervising subprocesses is
exactly the case where uvicorn already picks ``SelectorEventLoop``.

On Linux both paths are unchanged.

    python run_api.py
    python run_api.py --reload
"""

from __future__ import annotations

import argparse
import asyncio
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the RegDelta API.")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args(argv)

    import uvicorn

    from app.core.config import get_settings

    settings = get_settings()
    host = args.host or settings.api_host
    port = args.port or settings.api_port
    log_level = settings.log_level.lower()

    if args.reload:
        uvicorn.run(
            "app.main:app", host=host, port=port, reload=True, log_level=log_level
        )
        return 0

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    config = uvicorn.Config("app.main:app", host=host, port=port, log_level=log_level)
    asyncio.run(uvicorn.Server(config).serve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
