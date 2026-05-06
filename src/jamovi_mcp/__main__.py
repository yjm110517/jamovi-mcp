"""Entry point for jamovi MCP server."""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

if sys.version_info < (3, 12):
    sys.stderr.write(
        "jamovi-mcp requires Python 3.12 or newer. "
        r"Use C:\Python312\python.exe -m jamovi_mcp."
        "\n"
    )
    raise SystemExit(1)

_project_root = Path(__file__).resolve().parent.parent.parent
_lib_dir = _project_root / "lib"
if _lib_dir.exists():
    sys.path.insert(0, str(_lib_dir))

from .server import run_server


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )
    asyncio.run(run_server())


if __name__ == "__main__":
    main()
