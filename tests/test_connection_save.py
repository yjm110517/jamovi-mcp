from __future__ import annotations

import json

import pytest

from jamovi_mcp import connection as connection_module
from jamovi_mcp.connection import ConnectionError, JamoviConnection


class FakeContent:
    def __init__(self, lines: list[dict]) -> None:
        self._lines = [json.dumps(line).encode("utf-8") + b"\n" for line in lines]
        self._index = 0

    def __aiter__(self):
        return self

    async def __anext__(self) -> bytes:
        if self._index >= len(self._lines):
            raise StopAsyncIteration
        line = self._lines[self._index]
        self._index += 1
        return line


class FakeResponse:
    def __init__(self, status: int, lines: list[dict], text: str = "") -> None:
        self.status = status
        self.content = FakeContent(lines)
        self._text = text

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def text(self) -> str:
        return self._text


class FakeSession:
    def __init__(self, cookies=None, response: FakeResponse | None = None) -> None:
        self.cookies = cookies
        self.response = response or FakeResponse(200, [])
        self.post_calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    def post(self, url: str, data: dict):
        self.post_calls.append((url, data))
        return self.response


@pytest.mark.asyncio
async def test_save_file_posts_to_instance_save_endpoint(monkeypatch) -> None:
    response = FakeResponse(
        200,
        [
            {"status": "in-progress", "p": 0, "n": 1000},
            {
                "status": "OK",
                "path": "C:/data/out.omv",
                "filename": "out.omv",
                "title": "out",
                "saveFormat": "jamovi",
            },
        ],
    )
    session = FakeSession(response=response)

    def make_session(cookies=None):
        session.cookies = cookies
        return session

    monkeypatch.setattr(
        connection_module.aiohttp,
        "ClientSession",
        make_session,
    )

    conn = JamoviConnection("http://127.0.0.1:1234", "ws://127.0.0.1:1234", "key")
    conn._instance_id = "abc"

    result = await conn.save_file("C:/data/out.omv", overwrite=False)

    assert session.cookies == {"access_key": "key"}
    assert session.post_calls == [
        (
            "http://127.0.0.1:1234/abc/save",
            {"options": json.dumps({"path": "C:/data/out.omv", "overwrite": False})},
        )
    ]
    assert result["status"] == "OK"
    assert result["path"] == "C:/data/out.omv"
    assert result["saveFormat"] == "jamovi"


@pytest.mark.asyncio
async def test_save_file_raises_on_jamovi_error(monkeypatch) -> None:
    session = FakeSession(
        response=FakeResponse(200, [{"status": "error", "message": "Access denied"}])
    )
    def make_session(cookies=None):
        session.cookies = cookies
        return session

    monkeypatch.setattr(
        connection_module.aiohttp,
        "ClientSession",
        make_session,
    )

    conn = JamoviConnection("http://127.0.0.1:1234", "ws://127.0.0.1:1234", "key")
    conn._instance_id = "abc"

    with pytest.raises(ConnectionError, match="Access denied"):
        await conn.save_file("C:/data/out.omv")
