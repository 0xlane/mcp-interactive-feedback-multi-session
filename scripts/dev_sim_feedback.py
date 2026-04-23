"""Dev helper: trigger a single interactive_feedback session via the running HTTP daemon.

Usage::

    uv run python scripts/dev_sim_feedback.py \\
        --url http://127.0.0.1:8765/mcp \\
        --title "Session A" \\
        --summary "Phase 3 sidebar smoke test"

The script is intentionally minimal — it only initializes an MCP session, calls
the ``interactive_feedback`` tool, and then blocks waiting for the user to
submit (or the session to expire).  It is meant for ad-hoc frontend verification,
not as part of the automated test suite.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))


async def run(
    url: str, title: str, summary: str, project_dir: str, timeout: int
) -> None:
    try:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client
    except ImportError as e:  # pragma: no cover - dev helper
        raise SystemExit(
            "mcp client not available in this environment; run via `uv run`"
        ) from e

    print(f"connecting to MCP endpoint: {url}", flush=True)

    async with streamablehttp_client(url) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            print("MCP session initialized", flush=True)

            print(f"calling interactive_feedback (title={title!r})", flush=True)
            result = await session.call_tool(
                "interactive_feedback",
                {
                    "project_directory": project_dir,
                    "summary": summary,
                    "title": title,
                    "timeout": timeout,
                },
            )
            print("call_tool result:", result, flush=True)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--url", default="http://127.0.0.1:8765/mcp/")
    p.add_argument("--title", default="Dev session")
    p.add_argument("--summary", default="Dev summary for sidebar smoke test")
    p.add_argument("--project-dir", default=str(ROOT))
    p.add_argument("--timeout", type=int, default=1800, help="tool timeout seconds")
    args = p.parse_args()

    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(
            run(args.url, args.title, args.summary, args.project_dir, args.timeout)
        )


if __name__ == "__main__":
    main()
