"""Entry point for jamovi MCP server."""

from __future__ import annotations

import argparse
import asyncio
import importlib.metadata
import logging
import sys
from pathlib import Path

if sys.version_info < (3, 10):
    sys.stderr.write(
        "jamovi-mcp requires Python 3.10 or newer. "
        "Use a Python 3.10+ runtime, or run through uvx which "
        "automatically provisions the correct Python version:\n"
        "  uvx --from jamovi-mcp jamovi-mcp\n"
    )
    raise SystemExit(1)

_project_root = Path(__file__).resolve().parent.parent.parent
_lib_dir = _project_root / "lib"
if _lib_dir.exists():
    sys.path.insert(0, str(_lib_dir))


def _package_version() -> str:
    try:
        return importlib.metadata.version("jamovi-mcp")
    except importlib.metadata.PackageNotFoundError:
        return "0.0.0+local"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jamovi-mcp",
        description="Run the jamovi MCP server over stdio.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check Python and jamovi discovery without starting the MCP server.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"jamovi-mcp {_package_version()}",
    )
    return parser


def _run_check() -> int:
    print("jamovi-mcp diagnostics")
    print(f"Python: {sys.version.split()[0]} ({sys.executable})")
    try:
        from .config import find_jamovi_home, read_jamovi_env, validate_jamovi_home

        jamovi_home = validate_jamovi_home(find_jamovi_home())
        jamovi_env = read_jamovi_env(jamovi_home)
    except Exception as exc:
        print(f"jamovi: ERROR - {exc}", file=sys.stderr)
        return 1

    print(f"jamovi: {jamovi_home}")
    print(f"jamovi env: OK ({len(jamovi_env)} values)")
    print("MCP transport: stdio")
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.check:
        raise SystemExit(_run_check())

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )

    from .server import run_server

    asyncio.run(run_server())


if __name__ == "__main__":
    main()
