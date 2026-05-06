"""Engine manager: start/stop jamovi server as a subprocess."""

from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path

from .config import (
    ConfigError,
    JAMOVI_HOME,
    read_jamovi_env,
    validate_jamovi_home,
)

PORT_LINE_RE = re.compile(
    r"ports:\s*(\d+),\s*(\d+),\s*(\d+),\s*access_key:\s*([a-f0-9]+)"
)
SERVER_READY_RE = re.compile(r"jamovi\nversion:")


class EngineError(Exception):
    """Raised when the jamovi engine fails to start."""


class EngineManager:
    """Manages the jamovi server subprocess lifecycle."""

    def __init__(self, port: int = 0, jamovi_home: Path | None = None) -> None:
        self._port = port
        try:
            self._jamovi_home = validate_jamovi_home(jamovi_home or JAMOVI_HOME)
        except ConfigError as exc:
            raise EngineError(str(exc)) from exc
        self._bin = self._jamovi_home / "bin"
        self._resources = self._jamovi_home / "Resources"
        self._frameworks = self._jamovi_home / "Frameworks"
        self._process: asyncio.subprocess.Process | None = None
        self._main_port: int = 0
        self._analysis_port: int = 0
        self._results_port: int = 0
        self._access_key: str = ""
        self._ready = asyncio.Event()

    @property
    def main_port(self) -> int:
        return self._main_port

    @property
    def analysis_port(self) -> int:
        return self._analysis_port

    @property
    def results_port(self) -> int:
        return self._results_port

    @property
    def access_key(self) -> str:
        return self._access_key

    @property
    def jamovi_home(self) -> Path:
        return self._jamovi_home

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._main_port}"

    @property
    def ws_url(self) -> str:
        return f"ws://127.0.0.1:{self._main_port}"

    def _build_env(self) -> dict[str, str]:
        env = os.environ.copy()
        jamovi_env = read_jamovi_env(self._jamovi_home)
        path_parts = [
            jamovi_env.pop("PATH", ""),
            env.get("PATH", ""),
        ]
        env.update(jamovi_env)
        env["PATH"] = os.pathsep.join(path_parts)
        return env

    async def start(self) -> None:
        python_exe = self._frameworks / "python" / "python.exe"
        server_path = self._resources / "server"

        env = self._build_env()
        env["PYTHONPATH"] = str(server_path)

        self._process = await asyncio.create_subprocess_exec(
            str(python_exe),
            "-u",
            "-Xutf8",
            "-m",
            "jamovi.server",
            str(self._port),
            "--stdin-slave",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        await self._parse_startup_output()

    async def _parse_startup_output(self) -> None:
        assert self._process is not None
        assert self._process.stdout is not None

        lines_read: list[str] = []
        error_lines: list[str] = []

        async def read_stderr() -> None:
            assert self._process is not None
            assert self._process.stderr is not None
            while True:
                line = await self._process.stderr.readline()
                if not line:
                    break
                decoded = line.decode("utf-8", errors="replace").rstrip()
                if decoded:
                    error_lines.append(decoded)

        stderr_task = asyncio.ensure_future(read_stderr())

        try:
            while True:
                line = await self._process.stdout.readline()
                if not line:
                    break
                decoded = line.decode("utf-8", errors="replace").rstrip()
                if decoded:
                    lines_read.append(decoded)

                match = PORT_LINE_RE.search(decoded)
                if match:
                    self._main_port = int(match.group(1))
                    self._analysis_port = int(match.group(2))
                    self._results_port = int(match.group(3))
                    self._access_key = match.group(4)
                    self._ready.set()
                    return

                if "Error" in decoded or "Traceback" in decoded:
                    error_lines.append(decoded)
        finally:
            stderr_task.cancel()
            try:
                await stderr_task
            except asyncio.CancelledError:
                pass

        if self._process.returncode is not None and self._process.returncode != 0:
            raise EngineError(
                f"jamovi engine exited with code {self._process.returncode}\n"
                + "\n".join(error_lines[-20:])
            )

        if not self._access_key:
            raise EngineError(
                "jamovi engine started but did not report ports.\n"
                "stdout:\n" + "\n".join(lines_read[-10:]) + "\n"
                "stderr:\n" + "\n".join(error_lines[-10:])
            )

    async def stop(self) -> None:
        if self._process is None:
            return
        try:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=10)
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()
        except ProcessLookupError:
            pass
        self._process = None
        self._ready.clear()

    async def wait(self) -> None:
        """Wait until the engine has started and reported its ports."""
        await self._ready.wait()
